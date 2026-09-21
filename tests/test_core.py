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
    assert " - " in line
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
    assert today_index < source_index < hashtag_index
