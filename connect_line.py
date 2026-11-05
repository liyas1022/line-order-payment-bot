"""Prepare a webhook switch; --apply explicitly switches this LINE channel."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from app import app, LineAPIError, line_request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Switch the channel to PUBLIC_BASE_URL/line/webhook")
    args = parser.parse_args()
    origin = app.config["PUBLIC_BASE_URL"]
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        raise SystemExit("請先在 .env 設定 PUBLIC_BASE_URL=https://你的公開網址")
    target = origin + "/line/webhook"
    token = app.config["LINE_CHANNEL_ACCESS_TOKEN"]
    current = line_request(token, "/v2/bot/channel/webhook/endpoint")
    print("Current webhook:", current.get("endpoint") or "not configured")
    print("New webhook:", target)
    result = line_request(token, "/v2/bot/channel/webhook/test", {"endpoint": target})
    print("LINE webhook verification:", json.dumps(result, ensure_ascii=False))
    if not result.get("success"):
        raise SystemExit("LINE 驗證未通過，未變更 Webhook。")
    if not args.apply:
        print("Preparation complete. Webhook has not been changed. Use --apply to switch.")
        return
    folder = Path(__file__).resolve().parent / ".demo-run"
    folder.mkdir(exist_ok=True)
    backup = folder / "webhook-before-line-bot.json"
    if not backup.exists():
        backup.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    line_request(token, "/v2/bot/channel/webhook/endpoint", {"endpoint": target}, method="PUT")
    updated = line_request(token, "/v2/bot/channel/webhook/endpoint")
    if updated.get("endpoint") != target:
        raise SystemExit("設定回讀與目標不符，請檢查 LINE Developers Console。")
    print("Webhook switched:", updated["endpoint"])
    print("Use webhook:", updated.get("active", False))
    if not updated.get("active"):
        print("請在 LINE Developers Console > Messaging API 開啟 Use webhook。")


if __name__ == "__main__":
    try:
        main()
    except LineAPIError as error:
        print(str(error))
        raise SystemExit(1)
