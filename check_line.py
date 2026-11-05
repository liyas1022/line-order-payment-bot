"""Validate credentials and native LINE cards without sending chat messages."""
import argparse
import json
from pathlib import Path

from app import app, LineAPIError, line_request, menu_message, order_message


def example_messages():
    order = {
        "data_id": "DEMO-ORDER-300", "display_channel": "速3", "amount": 300,
        "ibon_no": "123456789012", "pay_end_date": "建立後 2 小時內",
        "is_paid": 0, "paid_at": None,
    }
    return {
        "menu": menu_message(),
        "unpaid": order_message(order),
        "paid": order_message({**order, "is_paid": 1, "paid_at": "模擬付款完成"}),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--export-only", action="store_true")
    parser.add_argument("--test-webhook", action="store_true")
    args = parser.parse_args()
    examples = example_messages()
    folder = Path(__file__).resolve().parent / "examples"
    folder.mkdir(exist_ok=True)
    for name, message in examples.items():
        (folder / f"{name}-flex.json").write_text(json.dumps(message, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Flex Message JSON exported: examples/")
    if args.export_only:
        return
    token = app.config["LINE_CHANNEL_ACCESS_TOKEN"]
    info = line_request(token, "/v2/bot/info")
    print("LINE bot:", info.get("displayName", "unknown"))
    print("Basic ID:", info.get("basicId", "unknown"))
    line_request(token, "/v2/bot/message/validate/reply", {"messages": list(examples.values())})
    print("LINE native menu, unpaid card, paid card: API validation PASS")
    endpoint = line_request(token, "/v2/bot/channel/webhook/endpoint")
    print("Current webhook:", endpoint.get("endpoint") or "not configured")
    print("Webhook active:", endpoint.get("active", False))
    if args.test_webhook:
        result = line_request(token, "/v2/bot/channel/webhook/test", {})
        print("Webhook test:", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except LineAPIError as error:
        print(str(error))
        raise SystemExit(1)
