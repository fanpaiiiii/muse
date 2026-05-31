#!/usr/bin/env python3
"""Direct Telegram message sender (bypasses Hermes Cron format)"""
import os, sys, json, urllib.request, urllib.error

CHAT_ID = "8081746929"
BOT_TOKEN = ""

def load_token():
    global BOT_TOKEN
    if BOT_TOKEN:
        return
    env_path = os.path.expanduser("~/.hermes/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN=") and not line.startswith("#"):
                    BOT_TOKEN = line.split("=", 1)[1].strip()
                    break


def send_message(text, parse_mode=None):
    load_token()
    if not BOT_TOKEN:
        return {"error": "TELEGRAM_BOT_TOKEN not configured"}
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode())
            return {"ok": True, "message_id": result.get("result", {}).get("message_id")}
    except urllib.error.URLError as e:
        return {"error": str(e)}


if __name__ == "__main__":
    text = sys.argv[1] if len(sys.argv) > 1 else "test"
    result = send_message(text)
    print(json.dumps(result, ensure_ascii=False))
