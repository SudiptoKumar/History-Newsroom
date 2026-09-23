from __future__ import annotations

import argparse
import logging
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config import SETTINGS
from content_ai import enrich_event
from dataset import Event, events_for_date, load_all, validate_dataset
from formatter import build_rich_message, build_rich_message_with_photo, format_fallback_caption
from image_pipeline import prepare_event_image
from image_resolver import resolve_event_image
from state_store import add_run, is_published, load_state, mark_published, save_state
from telegram_client import send_message, send_photo, send_rich_message, send_rich_photo

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("today-in-history")


def today_in_timezone() -> date:
    return datetime.now(ZoneInfo(SETTINGS.timezone)).date()


def resolve_run_date(value: str | None) -> date:
    if not value:
        return today_in_timezone()
    return date.fromisoformat(value)


def choose_batch(events: list[Event], batch_index: int) -> list[Event]:
    limited = events[: SETTINGS.max_events_per_day]
    start = max(0, (batch_index - 1) * SETTINGS.batch_size)
    end = start + SETTINGS.batch_size
    return limited[start:end]


def run(run_date: date, batch_index: int, dry_run: bool = False) -> None:
    events = load_all()
    errors = validate_dataset(events)
    if errors:
        raise RuntimeError("Dataset validation failed:\n" + "\n".join(errors[:30]))

    day_events = events_for_date(events, run_date.month, run_date.day)
    if not day_events:
        raise RuntimeError(f"No dataset records found for {run_date.isoformat()}")

    state = load_state()
    batch = choose_batch(day_events, batch_index)
    pending = [e for e in batch if not is_published(state, e.event_id)]
    logger.info("Date=%s | dataset_events=%d | selected_batch=%d | pending=%d", run_date, len(day_events), batch_index, len(pending))

    for index, event in enumerate(pending, start=1):
        enriched = enrich_event(event)
        resolved = resolve_event_image(event)
        image = prepare_event_image(event, resolved) if resolved else None
        if dry_run:
            logger.info("DRY RUN | %s | %s | image=%s | title=%s", event.event_id, event.event_title, image, enriched.title)
            logger.info("STORY | %s", enriched.story)
            continue

        message_id: int
        send_mode = "text"
        try:
            if image:
                rich = build_rich_message_with_photo(event, "photo", enriched)
                message_id = send_rich_photo(str(image), rich)
                send_mode = "rich_photo"
            else:
                rich = build_rich_message(event, enriched)
                message_id = send_rich_message(rich)
                send_mode = "rich_text"
        except Exception as exc:
            logger.warning("Rich publish failed for %s: %s", event.event_id, exc)
            # Fall back to the standard Bot API path so one Rich Message incompatibility does not stop a batch.
            fallback = format_fallback_caption(event, enriched)
            if image:
                message_id = send_photo(str(image), fallback)
                send_mode = "photo_fallback"
            else:
                message_id = send_message(fallback)
                send_mode = "text_fallback"

        mark_published(
            state,
            event.event_id,
            message_id,
            image_page=resolved.source_page if resolved else "",
            image_credit=resolved.source_name if resolved else "",
            send_mode=send_mode,
        )
        save_state(state)
        logger.info("Published %s -> message %s (%s)", event.event_id, message_id, send_mode)

    if not dry_run:
        add_run(state, {
            "date": run_date.isoformat(),
            "batch_index": batch_index,
            "selected": len(batch),
            "published_now": len(pending),
        })
        save_state(state)

    if len(day_events) < SETTINGS.max_events_per_day:
        logger.warning("Only %d events exist for %s; no filler events will be invented.", len(day_events), run_date.strftime("%B %d"))


def self_test() -> None:
    events = load_all()
    errors = validate_dataset(events)
    assert not errors, "\n".join(errors[:10])
    assert len(events) == 6879, f"Unexpected dataset size: {len(events)}"
    today = date(2026, 9, 21)
    todays = events_for_date(events, today.month, today.day)
    assert len(todays) == 20
    batch1 = choose_batch(todays, 1)
    batch2 = choose_batch(todays, 2)
    assert len(batch1) == SETTINGS.batch_size
    assert len(batch2) == SETTINGS.batch_size
    enriched = enrich_event(batch1[0])
    rich = build_rich_message(batch1[0], enriched)
    text_blocks = rich["blocks"]
    assert text_blocks[0]["type"] == "paragraph"
    assert text_blocks[1]["type"] == "heading"
    assert len(enriched.hashtags) == 3
    assert not any(x.startswith("People:") for x in [enriched.story])
    assert "Today in History" in str(rich)
    assert (Path(__file__).resolve().parent / "assets" / "today-in-history-logo.png").exists()
    logger.info("Self-test passed: %d events loaded.", len(events))


def preview(run_date: date, batch_index: int) -> None:
    events = load_all()
    day_events = events_for_date(events, run_date.month, run_date.day)
    batch = choose_batch(day_events, batch_index)
    print(f"{run_date.strftime('%B %d')} | {len(day_events)} total | batch {batch_index} | {len(batch)} selected")
    for i, e in enumerate(batch, 1):
        enriched = enrich_event(e)
        print(f"{i:02d}. [{e.event_id}] {e.year} {e.era} | {enriched.title} | {len(enriched.story.split())} words | {' '.join(enriched.hashtags)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Today in History Telegram bot")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--date", dest="run_date")
    parser.add_argument("--batch", dest="batch", type=int, default=SETTINGS.batch_index)
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    run_date = resolve_run_date(args.run_date)
    if args.preview:
        preview(run_date, args.batch)
        return
    run(run_date, args.batch, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
