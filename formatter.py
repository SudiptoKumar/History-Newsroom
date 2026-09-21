from __future__ import annotations

import html
import re

from content_ai import EnrichedContent, enrich_event, relevant_hashtags
from dataset import Event
from flags import country_flag

CHANNEL_URL = "https://t.me/HistoryNewsroom"


def esc(value: str) -> str:
    return html.escape(value or "", quote=False)


def year_label(event: Event) -> str:
    year = event.year.strip()
    if not year:
        return "Date not specified"
    if event.era.upper() == "BCE":
        return f"{year} BCE"
    return year


def primary_location(event: Event) -> str:
    for part in (event.city_location, event.modern_country, event.region):
        if part.strip():
            return part.strip()
    return "Historical record"


def date_line(event: Event) -> str:
    return f"{event.month.strip()} {event.day}, {year_label(event)} {country_flag(event.modern_country)} {primary_location(event)}"


def source_display_name(event: Event) -> str:
    name = event.source_1_name.strip() or "Source"
    if " — " in name:
        return name.split(" — ", 1)[0].strip()
    if " – " in name:
        return name.split(" – ", 1)[0].strip()
    return name


def _safe_tags(tags: list[str] | None, event: Event) -> list[str]:
    raw = tags or relevant_hashtags(event)
    clean: list[str] = []
    for tag in raw:
        value = re.sub(r"[^A-Za-z0-9]+", "", tag.replace("#", "").strip())
        if not value:
            continue
        candidate = "#" + value[:42]
        if candidate.lower() not in {item.lower() for item in clean}:
            clean.append(candidate)
        if len(clean) == 3:
            break
    for fallback in ("#History", "#HistoricalEvent"):
        if len(clean) == 3:
            break
        if fallback.lower() not in {item.lower() for item in clean}:
            clean.append(fallback)
    return clean[:3]


def build_rich_message(event: Event, enriched: EnrichedContent | None = None) -> dict:
    content = enriched or enrich_event(event)
    hashtags = " ".join(_safe_tags(content.hashtags, event))
    title = esc(content.title)
    story = esc(content.story)
    date_text = esc(date_line(event))
    source_url = html.escape(event.source_1_url, quote=True)
    source_name = esc(source_display_name(event))

    blocks = [
        {"type": "paragraph", "text": [{"type": "bold", "text": date_text}]},
        {"type": "heading", "size": 3, "text": title},
        {"type": "paragraph", "text": story},
        {
            "type": "paragraph",
            "text": [
                {"type": "url", "text": [{"type": "bold", "text": "Today in History"}], "url": CHANNEL_URL}
            ],
        },
        {
            "type": "paragraph",
            "text": [
                "Source: ",
                {"type": "url", "text": source_name, "url": event.source_1_url},
            ],
        },
        {"type": "paragraph", "text": hashtags},
    ]

    return {"blocks": blocks}


def build_rich_message_with_photo(event: Event, image_field: str, enriched: EnrichedContent | None = None) -> dict:
    payload = build_rich_message(event, enriched)
    payload["blocks"].insert(0, {
        "type": "photo",
        "photo": {"type": "photo", "media": f"attach://{image_field}"},
    })
    return payload


def format_fallback_caption(event: Event, enriched: EnrichedContent | None = None) -> str:
    """Fallback for API/client paths where Rich Messages cannot be used."""
    content = enriched or enrich_event(event)
    hashtags = " ".join(_safe_tags(content.hashtags, event))
    source_url = html.escape(event.source_1_url, quote=True)
    prefix = "\n\n".join([
        f"<b>{esc(date_line(event))}</b>",
        f"<b>{esc(content.title)}</b>",
    ])
    footer = "\n\n".join([
        f'<a href="{CHANNEL_URL}"><b>Today in History</b></a>',
        f'<b>Source:</b> <a href="{source_url}">{esc(source_display_name(event))}</a>',
        hashtags,
    ])
    available = 1024 - len(prefix) - len(footer) - 4
    story = esc(content.story)
    if len(story) > available:
        story = story[:max(0, available - 1)].rsplit(" ", 1)[0].rstrip() + "…"
    return "\n\n".join([prefix, story, footer])
