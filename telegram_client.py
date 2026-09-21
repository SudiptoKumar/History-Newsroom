from __future__ import annotations

import logging
from pathlib import Path

import requests

from config import SETTINGS

logger = logging.getLogger("today-in-history.telegram")


def _url(method: str) -> str:
    return f"https://api.telegram.org/bot{SETTINGS.telegram_bot_token}/{method}"


def _post(method: str, *, data=None, files=None) -> dict:
    if not SETTINGS.telegram_bot_token.strip():
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured.")
    if not SETTINGS.telegram_channel.strip():
        raise RuntimeError("TELEGRAM_CHANNEL is not configured. Use @HistoryNewsroom or a numeric channel ID.")
    last = None
    for attempt in range(1, 4):
        try:
            r = requests.post(_url(method), data=data, files=files, timeout=40)
            r.raise_for_status()
            payload = r.json()
            if not payload.get("ok"):
                raise RuntimeError(payload.get("description", "Telegram API error"))
            return payload["result"]
        except (requests.RequestException, ValueError, RuntimeError) as exc:
            last = exc
            logger.warning("Telegram %s attempt %d failed: %s", method, attempt, exc)
    raise RuntimeError(f"Telegram {method} failed: {last}")


def send_photo(path: str, caption: str) -> int:
    with open(path, "rb") as handle:
        result = _post("sendPhoto", data={"chat_id": SETTINGS.telegram_channel, "caption": caption, "parse_mode": "HTML"}, files={"photo": handle})
    return int(result["message_id"])


def send_message(caption: str) -> int:
    result = _post("sendMessage", data={"chat_id": SETTINGS.telegram_channel, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": "false"})
    return int(result["message_id"])
