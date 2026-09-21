from __future__ import annotations

import html
import re

from dataset import Event
from flags import country_flag


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
    parts = [event.city_location, event.modern_country, event.region]
    for part in parts:
        if part.strip():
            return part.strip()
    return "Historical record"


def hashtags(event: Event) -> str:
    raw = [event.event_category, event.event_type, event.modern_country]
    tags = []
    for item in raw:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "", item.replace("&", "and")).strip()
        if cleaned:
            tags.append("#" + cleaned[:40])
    tags.extend(["#TodayInHistory", f"#History{event.day:02d}"])
    return " ".join(dict.fromkeys(tags))


MAX_CAPTION_CHARS = 1024

def _truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    clipped = text[: max(0, limit - 1)].rsplit(" ", 1)[0].rstrip()
    return clipped + "…"


def format_caption(event: Event, index: int, total: int, image_credit: str = "", image_page: str = "") -> str:
    flag = country_flag(event.modern_country)
    description = _truncate(event.description, 620)

    lines = [
        f"<b>{esc(event.date_display or f'{event.month} {event.day}')}</b>",
        f"<b>{esc(year_label(event))}</b> · {esc(flag)} {esc(primary_location(event))}",
        "",
        f"<b>{esc(event.event_title)}</b>",
        "",
        esc(description),
    ]
    if event.people_involved.strip():
        lines += ["", f"<b>People:</b> {esc(event.people_involved)}"]
    if event.historical_entity.strip():
        lines += [f"<b>Entity:</b> {esc(event.historical_entity)}"]
    if event.event_category.strip():
        lines += [f"<b>Category:</b> {esc(event.event_category)}"]
    lines += ["", f"<b>Source:</b> <a href=\"{html.escape(event.source_1_url, quote=True)}\">{esc(event.source_1_name)}</a>"]
    if event.source_2_url.strip() and event.source_2_name.strip():
        lines[-1] += f" · <a href=\"{html.escape(event.source_2_url, quote=True)}\">{esc(event.source_2_name)}</a>"
    if image_credit and image_page:
        lines += [f"<b>Image:</b> <a href=\"{html.escape(image_page, quote=True)}\">{esc(image_credit)}</a>"]
    lines += ["", hashtags(event), f"<i>{index}/{total}</i>"]

    caption = "\n".join(lines)
    if len(caption) > MAX_CAPTION_CHARS:
        # Remove optional metadata before shortening the core historical description further.
        lines = [
            f"<b>{esc(event.date_display or f'{event.month} {event.day}')}</b>",
            f"<b>{esc(year_label(event))}</b> · {esc(flag)} {esc(primary_location(event))}",
            "",
            f"<b>{esc(event.event_title)}</b>",
            "",
            esc(_truncate(event.description, 480)),
            "",
            f"<b>Source:</b> <a href=\"{html.escape(event.source_1_url, quote=True)}\">{esc(event.source_1_name)}</a>",
            "", hashtags(event), f"<i>{index}/{total}</i>",
        ]
        caption = "\n".join(lines)

    if len(caption) > MAX_CAPTION_CHARS:
        caption = _truncate(caption, MAX_CAPTION_CHARS)
    return caption
