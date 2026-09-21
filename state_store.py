from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from config import STATE_DIR, STATE_FILE

DEFAULT_STATE = {"published_event_ids": {}, "runs": []}


def load_state() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        return {"published_event_ids": {}, "runs": []}
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"published_event_ids": {}, "runs": []}
        data.setdefault("published_event_ids", {})
        data.setdefault("runs", [])
        return data
    except (OSError, json.JSONDecodeError):
        return {"published_event_ids": {}, "runs": []}


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)


def is_published(state: dict, event_id: str) -> bool:
    return event_id in state.get("published_event_ids", {})


def mark_published(state: dict, event_id: str, message_id: int | None) -> None:
    state.setdefault("published_event_ids", {})[event_id] = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "message_id": message_id,
    }


def add_run(state: dict, payload: dict) -> None:
    state.setdefault("runs", []).append(payload)
    state["runs"] = state["runs"][-100:]
