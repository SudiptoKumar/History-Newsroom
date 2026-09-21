from datetime import date

from dataset import events_for_date, load_all, validate_dataset
from formatter import format_caption
from main import choose_batch
from config import normalize_telegram_channel


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


def test_caption_contains_source_and_fits_telegram_limit():
    events = load_all()
    for event in events:
        caption = format_caption(event, 1, 10)
        assert len(caption) <= 1024
    event = events_for_date(events, 9, 21)[0]
    caption = format_caption(event, 1, 10)
    assert event.event_title in caption
    assert event.source_1_name in caption
    assert "#TodayInHistory" in caption


def test_telegram_channel_normalization():
    assert normalize_telegram_channel("@HistoryNewsroom") == "@HistoryNewsroom"
    assert normalize_telegram_channel("https://t.me/HistoryNewsroom") == "@HistoryNewsroom"
    assert normalize_telegram_channel("t.me/HistoryNewsroom") == "@HistoryNewsroom"
    assert normalize_telegram_channel("-1001234567890") == "-1001234567890"
