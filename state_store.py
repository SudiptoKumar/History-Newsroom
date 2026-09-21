from __future__ import annotations

import json
from datetime import datetime, timezone

from config import STATE_DIR, STATE_FILE

DEFAULT_STATE = {"published_event_ids": {}, "runs": []}


def _fresh_state() -> dict:
    return {"published_event_ids": {}, "runs": []}


def load_state() -> dict:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not STATE_FILE.exists():
        return _fresh_state()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _fresh_state()
        # Migrate the temporary/legacy "published" key used by early V1 builds.
        published = data.get("published_event_ids")
        if not isinstance(published, dict):
            legacy = data.get("published")
            published = legacy if isinstance(legacy, dict) else {}
        runs = data.get("runs")
        if not isinstance(runs, list):
            runs = []
        return {"published_event_ids": published, "runs": runs[-100:]}
    except (OSError, json.JSONDecodeError):
        return _fresh_state()


def save_state(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    normalized = {
        "published_event_ids": state.get("published_event_ids", {}),
        "runs": state.get("runs", [])[-100:],
    }
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
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
