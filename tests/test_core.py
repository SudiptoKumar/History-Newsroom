from datetime import date

from config import normalize_telegram_channel
from content_ai import enrich_event
from dataset import events_for_date, load_all, validate_dataset
from formatter import build_rich_message, build_rich_message_with_photo, date_line, format_fallback_caption
from main import choose_batch


def test_dataset_valid():
    events = load_all()
    assert len(events) == 6879
    assert validate_dataset(events) == []


def test_standard_day_has_two_batches():
    events = load_all()
    day_events = events_for_date(events, 9, 21)
    assert len(day_events) == 20
    assert len(choose_batch(day_events, 1)) == 10
    assert len(choose_batch(day_events, 2)) == 10


def test_incomplete_day_is_not_filled():
    events = load_all()
    day_events = events_for_date(events, 4, 1)
    assert len(day_events) == 6
    assert len(choose_batch(day_events, 1)) == 6
    assert len(choose_batch(day_events, 2)) == 0


def test_new_date_line_format():
    event = events_for_date(load_all(), 9, 21)[0]
    line = date_line(event)
    assert line.startswith("September 21, ")
    assert " " in line
    assert "\n" not in line


def test_rich_message_structure():
    event = events_for_date(load_all(), 9, 21)[0]
    enriched = enrich_event(event)
    rich = build_rich_message(event, enriched)
    blocks = rich["blocks"]
    assert [b["type"] for b in blocks] == ["paragraph", "heading", "paragraph", "paragraph", "paragraph", "paragraph"]
    assert "Today in History" in str(rich)
    assert {"type": "bold", "text": "Today in History"} in rich["blocks"][3]["text"][0]["text"]
    assert len(enriched.hashtags) == 3
    assert 45 <= len(enriched.story.split()) <= 70
    assert all("#TodayInHistory".lower() != tag.lower() for tag in enriched.hashtags)
    assert "People:" not in str(rich)
    assert "Entity:" not in str(rich)
    assert "Category:" not in str(rich)


def test_rich_photo_block_uses_uploaded_media():
    event = events_for_date(load_all(), 9, 21)[0]
    rich = build_rich_message_with_photo(event, "photo")
    assert rich["blocks"][0] == {"type": "photo", "photo": {"type": "photo", "media": "attach://photo"}}



def test_fallback_caption_is_clean():
    event = events_for_date(load_all(), 9, 21)[0]
    caption = format_fallback_caption(event)
    assert "People:" not in caption
    assert "Entity:" not in caption
    assert "Category:" not in caption
    assert "<b>Today in History</b>" in caption
    assert caption.count("#") >= 3
    assert len(caption) <= 1024


def test_channel_normalization():
    assert normalize_telegram_channel("@HistoryNewsroom") == "@HistoryNewsroom"
    assert normalize_telegram_channel("https://t.me/HistoryNewsroom") == "@HistoryNewsroom"
    assert normalize_telegram_channel("t.me/HistoryNewsroom") == "@HistoryNewsroom"
    assert normalize_telegram_channel("-1001234567890") == "-1001234567890"


def test_story_length_ceiling_and_footer_order():
    event = events_for_date(load_all(), 9, 21)[0]
    enriched = enrich_event(event)
    assert len(enriched.story.split()) <= 70
    rich = build_rich_message(event, enriched)
    block_types = [b["type"] for b in rich["blocks"]]
    today_index = next(i for i, b in enumerate(rich["blocks"]) if "Today in History" in str(b))
    source_index = next(i for i, b in enumerate(rich["blocks"]) if "Source:" in str(b))
    hashtag_index = next(i for i, b in enumerate(rich["blocks"]) if "#" in str(b))
    assert today_index < hashtag_index < source_index


def test_fallback_story_expands_short_description():
    from content_ai import _fallback
    events = events_for_date(load_all(), 9, 21)
    for event in events:
        enriched = _fallback(event, [{"snippet": "The event occurred as part of a wider historical development involving the people and place identified in the record."}])
        assert 45 <= len(enriched.story.split()) <= 70


def test_footer_order_in_fallback_caption():
    event = events_for_date(load_all(), 9, 21)[0]
    from content_ai import _fallback
    enriched = _fallback(event)
    caption = format_fallback_caption(event, enriched)
    assert caption.index("#") < caption.index("Source:")


def test_parse_json_response_handles_code_fence():
    from content_ai import _parse_json_response
    result = _parse_json_response("```json\n{\"title\":\"Example\"}\n```")
    assert result["title"] == "Example"


def test_cerebras_retries_rate_limit(monkeypatch):
    import content_ai
    from dataclasses import replace
    from content_ai import _cerebras_generate

    class Response:
        def __init__(self, status, payload, headers=None):
            self.status_code = status
            self._payload = payload
            self.headers = headers or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return self._payload

    valid_story = (
        "During the French Revolution, the National Convention voted to abolish the French monarchy. "
        "The decision ended the constitutional monarchy created in 1791 and established the republic "
        "as France's new form of government. The vote came as revolutionary institutions were reshaping "
        "the country's rapidly changing political system."
    )
    responses = [
        Response(429, {"error": {"message": "rate limited"}}, {"Retry-After": "0"}),
        Response(200, {"choices": [{"message": {"content": "{\"title\":\"Abolition of the French Monarchy\",\"story\":\"" + valid_story + "\",\"hashtags\":[\"#SovietUnion\",\"#politics\",\"#leadership\"]}"}}]}),
    ]

    def fake_post(*args, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(content_ai.requests, "post", fake_post)
    monkeypatch.setattr(content_ai, "SETTINGS", replace(content_ai.SETTINGS, cerebras_api_key="test", use_cerebras=True, cerebras_min_interval_seconds=0.0, cerebras_retry_attempts=4))
    monkeypatch.setattr(content_ai, "_wait_for_cerebras_slot", lambda: None)
    monkeypatch.setattr(content_ai.time, "sleep", lambda *_: None)

    event = events_for_date(load_all(), 9, 21)[0]
    result = _cerebras_generate(event, [])
    assert result.title == "Abolition of the French Monarchy"
    assert len(result.story.split()) >= 45
    assert len(responses) == 0
