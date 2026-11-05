import base64
from contextlib import closing
import hashlib
import hmac
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import app as bot


class LineBotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = str(Path(self.temp.name) / "orders.db")
        self.settings = {
            "TESTING": True, "DATABASE": self.database,
            "LINE_CHANNEL_SECRET": "test-secret", "LINE_CHANNEL_ACCESS_TOKEN": "test-token",
            "DEMO_ADMIN_KEY": "test-admin", "ENABLE_MOCK_PAYMENT": True,
        }
        self.app = bot.create_app(self.settings)
        self.client = self.app.test_client()
        self.network = patch("app.line_request", return_value={})
        self.send = self.network.start()
        self.event_number = 0

    def tearDown(self):
        self.network.stop()
        self.temp.cleanup()

    def rows(self, sql="SELECT * FROM orders", values=()):
        with closing(sqlite3.connect(self.database)) as connection:
            connection.row_factory = sqlite3.Row
            return [dict(row) for row in connection.execute(sql, values)]

    def event(self, text="", user="U-alice", postback="", event_id=None):
        self.event_number += 1
        event = {
            "type": "postback" if postback else "message",
            "webhookEventId": event_id or f"event-{self.event_number}",
            "replyToken": f"reply-{self.event_number}",
            "source": {"type": "user", "userId": user},
        }
        if postback:
            event["postback"] = {"data": postback}
        else:
            event["message"] = {"type": "text", "id": str(self.event_number), "text": text}
        return event

    def deliver(self, *events):
        raw = json.dumps({"events": list(events)}, ensure_ascii=False).encode("utf-8")
        signature = base64.b64encode(hmac.new(b"test-secret", raw, hashlib.sha256).digest()).decode()
        return self.client.post("/line/webhook", data=raw, content_type="application/json", headers={"X-Line-Signature": signature})

    def test_signature_and_verification(self):
        self.assertEqual(self.deliver().status_code, 200)
        self.assertEqual(self.client.post("/line/webhook", json={"events": [self.event("+300")]}).status_code, 400)
        self.assertFalse(self.rows())
        self.send.assert_not_called()

    def test_three_modes_query_payment_and_owner_isolation(self):
        for index, (mode, details) in enumerate(bot.MODES.items()):
            user = f"U-owner-{index}"
            self.assertEqual(self.deliver(self.event("/" + details[0], user=user)).status_code, 200)
            self.assertEqual(self.deliver(self.event("+300", user=user)).status_code, 200)
            order = self.rows("SELECT * FROM orders ORDER BY id DESC LIMIT 1")[0]
            self.assertEqual(order["profile"], details[1])
            self.assertEqual(order["is_paid"], 0)
            for identifier in [order["data_id"], order["ibon_no"], order["smilepay_no"]]:
                self.deliver(self.event(identifier, user=user))
                self.assertEqual(self.send.call_args.args[2]["messages"][0]["type"], "flex")
            forged = bot.postback("pay", "pay", order=order["data_id"])["data"]
            self.deliver(self.event(user="U-stranger", postback=forged))
            self.assertEqual(self.rows("SELECT * FROM orders WHERE data_id=?", (order["data_id"],))[0]["is_paid"], 0)
            self.deliver(self.event(user=user, postback=forged))
            paid = self.rows("SELECT * FROM orders WHERE data_id=?", (order["data_id"],))[0]
            self.assertEqual(paid["is_paid"], 1)
            self.assertEqual(paid["status"], "已付款")
            self.assertIn("已付款", self.send.call_args.args[2]["messages"][0]["altText"])
            self.deliver(self.event(user=user, postback=forged))
            self.assertEqual(self.rows("SELECT * FROM orders WHERE data_id=?", (order["data_id"],))[0], paid)
        self.deliver(self.event("我的訂單", user="U-stranger"))
        self.assertEqual(self.send.call_args.args[2]["messages"][0]["type"], "text")

    def test_event_redelivery_and_network_failure_do_not_duplicate_orders(self):
        event = self.event("+300", event_id="retry-event")
        self.send.side_effect = bot.LineAPIError("test timeout")
        self.assertEqual(self.deliver(event).status_code, 503)
        first_payload = self.send.call_args.args[2]
        self.assertEqual(len(self.rows()), 1)
        self.send.side_effect = None
        event["deliveryContext"] = {"isRedelivery": True}
        self.assertEqual(self.deliver(event).status_code, 200)
        self.assertEqual(self.send.call_args.args[2], first_payload)
        self.assertEqual(len(self.rows()), 1)
        sent = self.send.call_count
        self.assertEqual(self.deliver(event).status_code, 200)
        self.assertEqual(self.send.call_count, sent)

    def test_modes_persist_across_restart(self):
        self.deliver(self.event("/速3"))
        self.app = bot.create_app(self.settings)
        self.client = self.app.test_client()
        self.deliver(self.event("+300"))
        self.assertEqual(self.rows()[0]["profile"], "smse4")

    def test_callback_validation_notification_and_safe_retry(self):
        self.deliver(self.event("+300"))
        order = self.rows()[0]
        headers = {"X-Demo-Admin-Key": "test-admin"}
        callback = {"Data_id": order["data_id"], "Amount": 300, "Status": "PAID", "Payment_no": "TEST-PAID"}
        self.assertEqual(self.client.post("/smse1/roturl", json=callback).status_code, 401)
        for payload in [{**callback, "Amount": 301}, {**callback, "Amount": "300.00"}, {**callback, "Amount": "abc"}, {**callback, "Status": "FAILED"}]:
            self.assertEqual(self.client.post("/smse1/roturl", json=payload, headers=headers).status_code, 400)
            self.assertEqual(self.rows()[0]["is_paid"], 0)
        self.assertEqual(self.client.post("/smse3/roturl", json=callback, headers=headers).status_code, 400)
        self.send.side_effect = bot.LineAPIError("push timeout")
        self.assertEqual(self.client.post("/smse1/roturl", json=callback, headers=headers).status_code, 503)
        retry_key = self.send.call_args.args[3]
        self.assertEqual(self.rows()[0]["is_paid"], 1)
        self.send.side_effect = None
        self.assertEqual(self.client.post("/smse1/roturl", json=callback, headers=headers).status_code, 200)
        self.assertEqual(self.send.call_args.args[3], retry_key)
        self.assertEqual(self.send.call_args.args[2]["to"], "U-alice")
        sent = self.send.call_count
        self.client.post("/smse1/roturl", json=callback, headers=headers)
        self.assertEqual(self.send.call_count, sent)

    def test_admin_routes_amounts_and_mock_toggle(self):
        self.assertEqual(self.client.get("/api/orders").status_code, 401)
        for value in [0, -1, 300.5, True, "300.5", 1000001]:
            self.assertEqual(self.client.post("/api/orders", json={"amount": value}, headers={"X-Demo-Admin-Key": "test-admin"}).status_code, 400)
        self.deliver(self.event("+300"))
        self.app.config["ENABLE_MOCK_PAYMENT"] = False
        action = bot.postback("pay", "pay", order=self.rows()[0]["data_id"])["data"]
        self.deliver(self.event(postback=action))
        self.assertEqual(self.rows()[0]["is_paid"], 0)


if __name__ == "__main__":
    unittest.main()
