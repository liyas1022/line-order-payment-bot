# -*- coding: utf-8 -*-
"""LINE 原生訂單與付款展示：Webhook、Flex Message、SQLite、模擬付款。"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode
from urllib.request import Request, urlopen
import uuid

from dotenv import dotenv_values
from flask import Flask, g, jsonify, render_template_string, request

BASE_DIR = Path(__file__).resolve().parent
TAIPEI = dt.timezone(dt.timedelta(hours=8))
MODES = {
    "smse1_api": ("速1", "smse1_api", "S1", "/smse1/roturl"),
    "smse3_api": ("速2", "smse3", "S3", "/smse3/roturl"),
    "smse4_api": ("速3", "smse4", "S4", "/smse4/roturl"),
}


def now_text() -> str:
    return dt.datetime.now(TAIPEI).strftime("%Y-%m-%d %H:%M:%S")


def postback(label: str, action: str, **values) -> dict:
    return {"type": "postback", "label": label,
            "data": urlencode({"action": action, **values}), "displayText": label}


def quick_reply() -> dict:
    actions = [postback(mode[0], "mode", mode=key) for key, mode in MODES.items()]
    actions += [{"type": "message", "label": "+300 開單", "text": "+300"},
                postback("我的訂單", "recent"), postback("操作選單", "menu")]
    return {"items": [{"type": "action", "action": action} for action in actions]}


def text_message(text: str) -> dict:
    return {"type": "text", "text": text, "quickReply": quick_reply()}


def flex_row(label: str, value: str) -> dict:
    return {"type": "box", "layout": "baseline", "spacing": "sm", "contents": [
        {"type": "text", "text": label, "size": "xs", "color": "#7C8795", "flex": 3},
        {"type": "text", "text": str(value), "size": "xs", "color": "#253044",
         "flex": 7, "wrap": True},
    ]}


def order_bubble(order: dict, mock_enabled: bool = True) -> dict:
    paid = bool(order["is_paid"])
    status = "已付款" if paid else "未入帳"
    color = "#06A66B" if paid else "#C58116"
    buttons = []
    if not paid and mock_enabled:
        buttons.append({"type": "button", "style": "primary", "color": "#06C755",
                        "action": postback("模擬付款（不扣款）", "pay", order=order["data_id"])})
    buttons.append({"type": "button", "style": "secondary",
                    "action": postback("查詢最新狀態", "query", order=order["data_id"])})
    return {
        "type": "bubble", "size": "mega",
        "header": {"type": "box", "layout": "vertical", "backgroundColor": "#F0FAF4",
                   "spacing": "sm", "contents": [
                       {"type": "text", "text": "訂單付款助手 · 展示模式", "size": "xs", "color": "#54816A"},
                       {"type": "text", "text": "付款完成" if paid else "繳費通知", "weight": "bold", "size": "xl", "color": "#173D2A"},
                   ]},
        "body": {"type": "box", "layout": "vertical", "spacing": "md", "contents": [
            {"type": "box", "layout": "baseline", "contents": [
                {"type": "text", "text": f"NT$ {order['amount']:,}", "weight": "bold", "size": "xxl", "color": "#172A20", "flex": 7},
                {"type": "text", "text": status, "weight": "bold", "size": "sm", "color": color, "align": "end", "flex": 3},
            ]},
            {"type": "separator"},
            flex_row("付款通道", order["display_channel"]),
            flex_row("訂單編號", order["data_id"]),
            {"type": "box", "layout": "vertical", "backgroundColor": "#F5F7F9", "paddingAll": "lg", "spacing": "sm", "contents": [
                {"type": "text", "text": "模擬繳費代碼", "size": "xs", "color": "#7C8795"},
                {"type": "text", "text": order["ibon_no"], "weight": "bold", "size": "xl", "color": "#253044", "wrap": True},
            ]},
            flex_row("付款時間" if paid else "繳費期限", order.get("paid_at") if paid else order["pay_end_date"]),
            {"type": "text", "text": "✓ 訂單成立  →  ✓ 付款入帳" if paid else "✓ 訂單成立  →  等待付款", "size": "xs", "color": color, "wrap": True},
        ]},
        "footer": {"type": "box", "layout": "vertical", "spacing": "sm", "contents": buttons + [
            {"type": "text", "text": "作品集模擬流程，代碼不可實際繳費。", "size": "xxs", "color": "#87918E", "wrap": True, "align": "center"},
        ]},
    }


def order_message(order: dict, mock_enabled: bool = True) -> dict:
    return {"type": "flex", "altText": f"{order['display_channel']} 訂單 NT$ {order['amount']:,}｜{'已付款' if order['is_paid'] else '未入帳'}",
            "contents": order_bubble(order, mock_enabled), "quickReply": quick_reply()}


def menu_message(mode: str = "smse1_api") -> dict:
    return {"type": "flex", "altText": "訂單助手：選擇模式、開單、查詢訂單",
            "contents": {"type": "bubble", "body": {
                "type": "box", "layout": "vertical", "spacing": "md", "contents": [
                    {"type": "text", "text": "LINE 訂單助手", "weight": "bold", "size": "xl", "color": "#173D2A"},
                    {"type": "text", "text": f"目前模式：{MODES[mode][0]}", "size": "sm", "color": "#06A66B"},
                    {"type": "text", "text": "選擇通道後輸入 +300，即可建立訂單。\n也可以輸入其他整數金額，例如 +500。", "size": "sm", "wrap": True, "color": "#53615A"},
                    {"type": "box", "layout": "horizontal", "spacing": "sm", "contents": [
                        {"type": "button", "style": "primary" if key == mode else "secondary",
                         **({"color": "#06C755"} if key == mode else {}), "height": "sm",
                         "action": postback(item[0], "mode", mode=key)} for key, item in MODES.items()
                    ]},
                    {"type": "button", "style": "primary", "color": "#06C755",
                     "action": {"type": "message", "label": "+300 建立訂單", "text": "+300"}},
                    {"type": "button", "style": "secondary", "action": postback("查看我的訂單", "recent")},
                    {"type": "text", "text": "模擬付款展示 · 不會產生真實扣款", "size": "xxs", "color": "#87918E", "wrap": True},
                ]}}, "quickReply": quick_reply()}


class LineAPIError(RuntimeError):
    pass


def line_request(token: str, path: str, payload: Optional[dict] = None, retry_key: str = "", method: str = "") -> dict:
    if not token:
        raise LineAPIError("尚未設定 LINE_CHANNEL_ACCESS_TOKEN")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    if retry_key:
        headers["X-Line-Retry-Key"] = retry_key
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    outbound = Request("https://api.line.me" + path, data=body, headers=headers,
                       method=method or ("POST" if payload is not None else "GET"))
    try:
        with urlopen(outbound, timeout=10) as response:
            content = response.read()
            return json.loads(content) if content else {}
    except HTTPError as exc:
        if retry_key and exc.code == 409 and exc.headers.get("x-line-accepted-request-id"):
            return {"accepted": True}
        raise LineAPIError(f"LINE API HTTP {exc.code}，request-id={exc.headers.get('x-line-request-id', 'unknown')}") from None
    except (URLError, TimeoutError, OSError) as exc:
        raise LineAPIError(f"LINE API 連線失敗（{type(exc).__name__}）") from None


def create_app(overrides: Optional[dict] = None) -> Flask:
    app = Flask(__name__)
    env = dotenv_values(BASE_DIR / ".env")

    def setting(key: str, default=""):
        return os.environ.get(key, env.get(key) or default)

    app.config.update(
        DATABASE=str(BASE_DIR / "portfolio_orders.db"),
        LINE_CHANNEL_SECRET=setting("LINE_CHANNEL_SECRET"),
        LINE_CHANNEL_ACCESS_TOKEN=setting("LINE_CHANNEL_ACCESS_TOKEN"),
        PUBLIC_BASE_URL=setting("PUBLIC_BASE_URL").rstrip("/"),
        DEMO_ADMIN_KEY=setting("DEMO_ADMIN_KEY"),
        ENABLE_MOCK_PAYMENT=setting("ENABLE_MOCK_PAYMENT", "true").lower() == "true",
        MAX_CONTENT_LENGTH=1024 * 1024,
        MAX_ORDER_AMOUNT=1000000,
    )
    if overrides:
        app.config.update(overrides)

    def db() -> sqlite3.Connection:
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"], timeout=15)
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_db(_error=None):
        connection = g.pop("db", None)
        if connection is not None:
            connection.close()

    with app.app_context():
        with db() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    data_id TEXT NOT NULL UNIQUE, profile TEXT NOT NULL,
                    display_channel TEXT NOT NULL, smilepay_no TEXT, ibon_no TEXT,
                    payment_no TEXT, amount INTEGER NOT NULL, pay_end_date TEXT,
                    status TEXT NOT NULL DEFAULT '未入帳', is_paid INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, paid_at TEXT, callback_at TEXT, raw_callback TEXT,
                    owner_user_id TEXT
                );
                CREATE TABLE IF NOT EXISTS user_modes (user_id TEXT PRIMARY KEY, mode TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS webhook_events (
                    event_id TEXT PRIMARY KEY, reply_json TEXT NOT NULL,
                    received_at TEXT NOT NULL, replied_at TEXT
                );
                CREATE TABLE IF NOT EXISTS payment_notifications (
                    data_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    retry_key TEXT NOT NULL, sent_at TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_orders_ibon_no ON orders(ibon_no);
            """)
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(orders)")}
            if "owner_user_id" not in columns:
                connection.execute("ALTER TABLE orders ADD COLUMN owner_user_id TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_orders_owner ON orders(owner_user_id, id)")

    def current_mode(user_id: str) -> str:
        row = db().execute("SELECT mode FROM user_modes WHERE user_id=?", (user_id,)).fetchone()
        return row["mode"] if row and row["mode"] in MODES else "smse1_api"

    def find_order(identifier: str, owner: Optional[str] = None) -> Optional[dict]:
        sql = "SELECT * FROM orders WHERE (data_id=? OR smilepay_no=? OR ibon_no=? OR payment_no=?)"
        values = [identifier] * 4
        if owner is not None:
            sql += " AND owner_user_id=?"
            values.append(owner)
        row = db().execute(sql + " LIMIT 1", values).fetchone()
        return dict(row) if row else None

    def create_order(amount, mode: str, owner: str) -> dict:
        if isinstance(amount, bool) or not re.fullmatch(r"[0-9]{1,7}", str(amount)):
            raise ValueError("請輸入整數金額，例如 +300。")
        amount = int(amount)
        if not 1 <= amount <= app.config["MAX_ORDER_AMOUNT"]:
            raise ValueError("金額需介於 1 至 1,000,000 元。")
        if mode not in MODES:
            raise ValueError("未知開單模式。")
        display, profile, prefix, _callback = MODES[mode]
        data_id = prefix + dt.datetime.now(TAIPEI).strftime("%y%m%d%H%M%S") + secrets.token_hex(3).upper()
        codes = ["".join(str(secrets.randbelow(10)) for _ in range(12)) for _ in range(2)]
        deadline = (dt.datetime.now(TAIPEI) + dt.timedelta(hours=2)).strftime("%Y/%m/%d %H:%M:%S")
        db().execute("""INSERT INTO orders (data_id, profile, display_channel, smilepay_no,
            ibon_no, amount, pay_end_date, created_at, owner_user_id) VALUES (?,?,?,?,?,?,?,?,?)""",
            (data_id, profile, display, *codes, amount, deadline, now_text(), owner))
        return find_order(data_id, owner)

    def apply_payment(profile: str, payload: dict, push_notification: bool = False) -> dict:
        identifier = str(payload.get("Data_id") or payload.get("data_id") or "").strip()
        order = find_order(identifier)
        if not order or order["profile"] != profile:
            raise ValueError("訂單或付款通道不符。")
        amount = str(payload.get("Amount", payload.get("Purchamt", "")))
        if not re.fullmatch(r"[0-9]+", amount) or int(amount) != order["amount"]:
            raise ValueError("付款金額與訂單不符。")
        if str(payload.get("Status", "")).upper() != "PAID":
            raise ValueError("僅接受 PAID 付款通知。")
        paid_at = now_text()
        payment_no = str(payload.get("Payment_no") or "MOCK" + secrets.token_hex(6).upper())
        changed = db().execute("""UPDATE orders SET status='已付款', is_paid=1, paid_at=?,
            payment_no=?, callback_at=?, raw_callback=? WHERE data_id=? AND is_paid=0""",
            (paid_at, payment_no, paid_at, json.dumps(payload, ensure_ascii=False), identifier)).rowcount
        if changed and push_notification and order["owner_user_id"]:
            db().execute("INSERT OR IGNORE INTO payment_notifications VALUES (?,?,?,NULL)",
                         (identifier, order["owner_user_id"], str(uuid.uuid4())))
        return find_order(identifier)

    def simulate_payment(order: dict) -> dict:
        if not app.config["ENABLE_MOCK_PAYMENT"]:
            raise ValueError("目前未啟用模擬付款。")
        payload = {"Data_id": order["data_id"], "Smseid": order["smilepay_no"],
                   "Payment_no": "MOCK" + secrets.token_hex(6).upper(),
                   "Amount": order["amount"], "Status": "PAID"}
        return apply_payment(order["profile"], payload)

    def recent_messages(user_id: str) -> list[dict]:
        rows = db().execute("SELECT * FROM orders WHERE owner_user_id=? ORDER BY id DESC LIMIT 5", (user_id,)).fetchall()
        if not rows:
            return [text_message("你還沒有訂單。選擇模式後輸入 +300，即可建立第一筆訂單。")]
        return [{"type": "flex", "altText": f"你的最近 {len(rows)} 筆訂單",
                 "contents": {"type": "carousel", "contents": [order_bubble(dict(row), app.config["ENABLE_MOCK_PAYMENT"]) for row in rows]},
                 "quickReply": quick_reply()}]

    def respond(user_id: str, text: str = "", action_data: str = "") -> list[dict]:
        text = text.strip()
        action = {}
        if action_data:
            action = {key: values[0] for key, values in parse_qs(action_data).items()}
        if text in ("/模式", "/開始", "選單") or action.get("action") == "menu":
            return [menu_message(current_mode(user_id))]
        switches = {"/" + item[0]: key for key, item in MODES.items()}
        mode = switches.get(text)
        if action.get("action") == "mode":
            mode = action.get("mode")
            if mode not in MODES:
                raise ValueError("未知開單模式。")
        if mode:
            db().execute("INSERT INTO user_modes VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET mode=excluded.mode", (user_id, mode))
            return [text_message(f"已切換為 {MODES[mode][0]}。\n輸入 +300 或按下方按鈕建立訂單。")]
        if text in ("/最近", "我的訂單", "查詢訂單") or action.get("action") == "recent":
            return recent_messages(user_id)
        if re.fullmatch(r"\+[0-9]+", text):
            return [order_message(create_order(text[1:], current_mode(user_id), user_id), app.config["ENABLE_MOCK_PAYMENT"])]
        if action.get("action") in ("query", "pay"):
            identifier = action.get("order", "")
        else:
            identifier = text.removeprefix("/查單 ").strip()
        order = find_order(identifier, user_id)
        if order:
            if action.get("action") == "pay":
                order = simulate_payment(order)
            return [order_message(order, app.config["ENABLE_MOCK_PAYMENT"])]
        return [text_message("找不到你的訂單或指令。\n輸入 /模式 查看選單，或輸入繳費代碼、訂單編號查詢。")]

    def send_reply(reply_token: str, messages: list[dict]):
        line_request(app.config["LINE_CHANNEL_ACCESS_TOKEN"], "/v2/bot/message/reply",
                     {"replyToken": reply_token, "messages": messages})

    def deliver_payment_notification(identifier: str):
        row = db().execute("SELECT * FROM payment_notifications WHERE data_id=? AND sent_at IS NULL", (identifier,)).fetchone()
        if row:
            order = find_order(identifier)
            line_request(app.config["LINE_CHANNEL_ACCESS_TOKEN"], "/v2/bot/message/push",
                         {"to": row["user_id"], "messages": [order_message(order, app.config["ENABLE_MOCK_PAYMENT"])]}, row["retry_key"])
            with db():
                db().execute("UPDATE payment_notifications SET sent_at=? WHERE data_id=?", (now_text(), identifier))

    @app.before_request
    def protect_admin_routes():
        if request.path.startswith("/api/") or request.path in {item[3] for item in MODES.values()}:
            configured = app.config["DEMO_ADMIN_KEY"]
            supplied = request.headers.get("X-Demo-Admin-Key", "")
            if not configured or not hmac.compare_digest(configured.encode(), supplied.encode()):
                return jsonify(ok=False, error="此端點需要管理金鑰。請從 LINE 聊天室操作。"), 401

    @app.errorhandler(LineAPIError)
    def line_error(error):
        app.logger.warning("%s", error)
        return jsonify(ok=False, error="LINE API 呼叫未完成。請檢查本機設定與服務日誌。"), 503

    @app.errorhandler(ValueError)
    def value_error(error):
        return jsonify(ok=False, error=str(error)), 400

    @app.get("/health")
    def health():
        row = db().execute("SELECT MAX(received_at), MAX(replied_at) FROM webhook_events").fetchone()
        return jsonify(ok=True, service="LINE Order Bot", demo_mode=True,
                       line_credentials_present=bool(app.config["LINE_CHANNEL_SECRET"] and app.config["LINE_CHANNEL_ACCESS_TOKEN"]),
                       last_webhook_at=row[0], last_reply_at=row[1])

    @app.get("/")
    def home():
        configured = bool(app.config["LINE_CHANNEL_SECRET"] and app.config["LINE_CHANNEL_ACCESS_TOKEN"])
        webhook = app.config["PUBLIC_BASE_URL"] + "/line/webhook" if app.config["PUBLIC_BASE_URL"] else "https://你的公開網址/line/webhook"
        return render_template_string("""<!doctype html><html lang="zh-Hant"><meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1"><title>LINE 訂單助手</title>
        <style>body{margin:0;background:#f2f6f3;color:#20372b;font:16px/1.8 system-ui,sans-serif}main{max-width:640px;margin:10vh auto;padding:32px;background:white;border-radius:24px}h1{margin:0}code{overflow-wrap:anywhere}strong{color:#079d49}@media(max-width:720px){main{margin:24px 16px;padding:24px}}</style>
        <main><strong>LINE MESSAGING API</strong><h1>LINE 訂單助手</h1>
        <p>請在 LINE 官方帳號的聊天室中操作：<br>選擇速1／速2／速3 → 輸入 +300 → 收到繳費卡片 → 模擬付款 → 收到已付款卡片。</p>
        <p>本機金鑰：{{ '已填入（尚需 LINE 驗證）' if configured else '待填入 .env' }}<br>Webhook：<code>{{ webhook }}</code></p>
        <p>作品集模擬付款，不會產生真實扣款。</p></main></html>""", configured=configured, webhook=webhook)

    @app.post("/line/webhook")
    @app.post("/callback")
    def webhook():
        secret = app.config["LINE_CHANNEL_SECRET"]
        if not secret:
            return jsonify(ok=False, error="尚未設定 LINE_CHANNEL_SECRET"), 503
        raw = request.get_data()
        expected = base64.b64encode(hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).digest())
        signature = request.headers.get("X-Line-Signature", "").encode("utf-8")
        if not hmac.compare_digest(expected, signature):
            return jsonify(ok=False, error="Invalid LINE signature"), 400
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError):
            return jsonify(ok=False, error="Invalid JSON"), 400
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            return jsonify(ok=False, error="Invalid webhook events"), 400
        for event in payload["events"]:
            if not isinstance(event, dict):
                return jsonify(ok=False, error="Invalid webhook event"), 400
            event_type = event.get("type")
            if event_type not in ("message", "postback", "follow") or event.get("mode") == "standby":
                continue
            reply_token = event.get("replyToken")
            if not reply_token:
                continue
            source = event.get("source", {})
            user_id = source.get("userId", "")
            stable_event = {key: value for key, value in event.items() if key != "deliveryContext"}
            event_id = event.get("webhookEventId") or hashlib.sha256(json.dumps(stable_event, sort_keys=True).encode()).hexdigest()
            with db() as connection:
                connection.execute("BEGIN IMMEDIATE")
                cached = connection.execute("SELECT * FROM webhook_events WHERE event_id=?", (event_id,)).fetchone()
                if cached and cached["replied_at"]:
                    continue
                if cached:
                    messages = json.loads(cached["reply_json"])
                else:
                    try:
                        if source.get("type") != "user" or not user_id:
                            messages = [text_message("請在此官方帳號的一對一聊天室中開單與查單。")]
                        elif event_type == "follow":
                            messages = [menu_message(current_mode(user_id))]
                        elif event_type == "postback":
                            messages = respond(user_id, action_data=str(event.get("postback", {}).get("data", "")))
                        elif event.get("message", {}).get("type") == "text":
                            messages = respond(user_id, str(event["message"].get("text", "")))
                        else:
                            messages = [text_message("請輸入 /模式，或使用下方按鈕操作訂單。")]
                    except ValueError as error:
                        messages = [text_message(str(error))]
                    connection.execute("INSERT INTO webhook_events VALUES (?,?,?,NULL)",
                                       (event_id, json.dumps(messages, ensure_ascii=False), now_text()))
            send_reply(reply_token, messages)
            with db():
                db().execute("UPDATE webhook_events SET replied_at=? WHERE event_id=?", (now_text(), event_id))
        return jsonify(ok=True)

    def json_body() -> dict:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            raise ValueError("請提供 JSON 物件。")
        return body

    @app.post("/api/line")
    def local_line():
        body = json_body()
        with db():
            messages = respond(str(body.get("user_id") or "local-demo"), str(body.get("text", "")), str(body.get("action_data", "")))
        return jsonify(ok=True, messages=messages)

    @app.get("/api/orders")
    def local_orders():
        return jsonify(ok=True, orders=[dict(row) for row in db().execute("SELECT * FROM orders ORDER BY id DESC LIMIT 100")])

    @app.post("/api/orders")
    def local_create():
        body = json_body()
        with db():
            order = create_order(body.get("amount"), str(body.get("mode", "smse1_api")), str(body.get("user_id") or "local-demo"))
        return jsonify(ok=True, order=order), 201

    @app.get("/api/orders/<identifier>")
    def local_order(identifier):
        order = find_order(identifier)
        return (jsonify(ok=True, order=order), 200) if order else (jsonify(ok=False, error="找不到訂單"), 404)

    @app.post("/api/mock/pay/<identifier>")
    def local_pay(identifier):
        order = find_order(identifier)
        if not order:
            return jsonify(ok=False, error="找不到訂單"), 404
        with db():
            updated = simulate_payment(order)
            if not order["is_paid"] and order["owner_user_id"]:
                db().execute("INSERT OR IGNORE INTO payment_notifications VALUES (?,?,?,NULL)",
                             (identifier, order["owner_user_id"], str(uuid.uuid4())))
        deliver_payment_notification(identifier)
        return jsonify(ok=True, order=updated)

    def payment_callback(profile: str):
        data = {**request.args.to_dict(), **request.form.to_dict()}
        body = request.get_json(silent=True)
        if isinstance(body, dict):
            data.update(body)
        with db() as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = apply_payment(profile, data, push_notification=True)
        deliver_payment_notification(updated["data_id"])
        return "<Roturlstatus>SmilePay_OK</Roturlstatus>", 200, {"Content-Type": "application/xml; charset=utf-8"}

    for mode_key, (_display, profile, _prefix, callback_path) in MODES.items():
        app.add_url_rule(callback_path, mode_key + "_callback", lambda profile=profile: payment_callback(profile), methods=["POST"])

    return app


app = create_app()

if __name__ == "__main__":
    env = dotenv_values(BASE_DIR / ".env")
    port = int(os.environ.get("PORT", env.get("PORT") or "5000"))
    host = os.environ.get("HOST", env.get("HOST") or "127.0.0.1")
    print(f"LINE 訂單助手：http://127.0.0.1:{port}/")
    print("LINE Webhook：公開 HTTPS 網址 + /line/webhook")
    print("付款服務：Mock（不會產生真實扣款）")
    app.run(host=host, port=port, debug=False)
