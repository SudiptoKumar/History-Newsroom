from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("CEREBRAS_API_KEY", "test-key-1")
os.environ["CEREBRAS_API_KEY"] = "test-key-1"
os.environ["CEREBRAS_API_KEY_2"] = "test-key-2"

import requests

import cerebras_keys
import content_ai
from config import SETTINGS
from dataset import Event

KEY1, KEY2 = "test-key-1", "test-key-2"
STORY = " ".join(["word"] * 55)
AI_BODY = {"choices": [{"message": {"content": json.dumps({"title": "AI Event Title", "story": STORY, "hashtags": ["Alpha", "Beta", "Gamma"]})}}]}


def _event() -> Event:
    return Event(
        day=30, era="AD", year="1969", month="October", event_id="TEST-1",
        event_type="Event", description="A test historical event happened on this day.",
        event_title="Test Event Title", date_display="October 30", source_1_url="https://example.com",
        source_2_url="", calendar_date="1969-10-30", city_location="", original_date="October 30, 1969",
        source_1_name="Example", source_2_name="", date_certainty="exact", event_category="General",
        modern_country="", calendar_system="Gregorian", coverage_status="ok", people_involved="",
        historical_entity="", significance_scope="", source_reliability="", target_event_count="",
        verification_status="Verified", verified_event_count="", significance_score=50.0,
        notes="", region="",
    )


class FakeResponse:
    def __init__(self, status: int):
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return AI_BODY


class FakeTransport:
    def __init__(self, script):
        self.script = {k: list(v) for k, v in script.items()}
        self.cerebras_auth = []
        self.alerts = []

    def __call__(self, url, **kwargs):
        if "api.telegram.org" in url:
            self.alerts.append(kwargs.get("data", {}).get("text", ""))
            return FakeResponse(200)
        key = (kwargs.get("headers") or {}).get("Authorization", "").replace("Bearer ", "")
        self.cerebras_auth.append(key)
        statuses = self.script.get(key) or [200]
        return FakeResponse(statuses.pop(0) if len(statuses) > 1 else statuses[0])


def _prime() -> None:
    # Other test modules may import config first with no keys in the
    # environment, so force the test keys onto the frozen SETTINGS directly.
    object.__setattr__(SETTINGS, "cerebras_api_key", KEY1)
    object.__setattr__(SETTINGS, "cerebras_api_key_2", KEY2)
    object.__setattr__(SETTINGS, "use_cerebras", True)
    cerebras_keys._reset_state()


def _run(script):
    transport = FakeTransport(script)
    original = requests.post
    requests.post = transport
    try:
        return content_ai._cerebras_generate(_event(), []), transport
    finally:
        requests.post = original


def test_failover_to_second_key() -> None:
    _prime()
    result, transport = _run({KEY1: [402], KEY2: [200]})
    assert result.title == "AI Event Title", result
    assert transport.cerebras_auth == [KEY1, KEY2], transport.cerebras_auth
    assert SETTINGS.cerebras_api_key == KEY2


def test_non_quota_error_falls_back_without_rotating() -> None:
    _prime()
    result, transport = _run({KEY1: [400], KEY2: [200]})
    assert result.title != "AI Event Title", result
    assert transport.cerebras_auth == [KEY1], transport.cerebras_auth
    assert SETTINGS.cerebras_api_key == KEY1


def test_both_keys_dead_falls_back() -> None:
    _prime()
    result, transport = _run({KEY1: [402], KEY2: [402]})
    assert result.title != "AI Event Title", result
    assert transport.cerebras_auth == [KEY1, KEY2], transport.cerebras_auth
    cerebras_keys._reset_state()
