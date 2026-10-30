from __future__ import annotations

import html
import re
from urllib.parse import urlparse

from content_ai import EnrichedContent, enrich_event, relevant_hashtags
from dataset import Event
from flags import country_flag

CHANNEL_URL = "https://t.me/HistoryNewsroom"
_TAG_STOPWORDS = {"and", "of", "the"}


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


def _camel_tag(value: str) -> str:
    """Readable CamelCase hashtag: 'Military and political history' ->
    '#MilitaryPoliticalHistory' (stopwords dropped, word case preserved)."""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", (value or "").replace("&", " and ")) if w.lower() not in _TAG_STOPWORDS]
    if not words:
        return ""
    return "#" + "".join(w[:1].upper() + w[1:] for w in words)[:42]


def source_display_name(event: Event) -> str:
    """Human-readable source name. The dataset sometimes stores a date-like
    page title ('October 30') as the source name; that reads as nonsense in
    the footer, so fall back to the site behind the source URL."""
    name = event.source_1_name.strip()
    # Dataset names look like "October 30 — Wikipedia" or "Wikipedia —
    # November date page": keep the site part, drop the date qualifier.
    parts = [part.strip() for part in re.split(r"\s+[—–]\s+", name) if part.strip()]
    months = "January|February|March|April|May|June|July|August|September|October|November|December"
    kept = [
        part
        for part in parts
        if not re.fullmatch(rf"(?:{months})\s+\d{{1,2}}", part)
        and not re.fullmatch(rf"(?:{months})\s+date page", part, re.IGNORECASE)
    ]
    if kept:
        name = kept[0]
    date_like = re.fullmatch(rf"(?:{months})\s+\d{{1,2}}", name)
    if name and not date_like and name.lower() != "source":
        return name
    domain = urlparse(event.source_1_url).netloc.lower().removeprefix("www.")
    if domain.endswith("wikipedia.org"):
        return "Wikipedia"
    if domain:
        return domain
    return name or "Source"


def _safe_tags(tags: list[str] | None, event: Event) -> list[str]:
    raw = tags or relevant_hashtags(event)
    clean: list[str] = []
    for tag in raw:
        candidate = _camel_tag(str(tag).replace("#", ""))
        if not candidate:
            continue
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


_SENTENCE_END = re.compile(r"[^.!?]+(?:[.!?]+[\"'”’]*)")
_ABBREVIATIONS = {"u.s", "u.k", "e.g", "i.e", "mr", "mrs", "ms", "dr", "st", "vs", "approx", "b.c", "a.d"}
_FILLER_PATTERNS = (
    re.compile(r"^it is recorded under .+\.$", re.IGNORECASE),
    re.compile(r"^the event occurred in .+\.$", re.IGNORECASE),
)


def _split_sentences(text: str) -> list[str]:
    """Sentence split that does not break on abbreviations (U.S., B.C.)
    or single-letter initials."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts: list[str] = []
    buf = ""
    for match in _SENTENCE_END.finditer(text):
        buf += match.group(0)
        words = buf.rstrip().rstrip(".!?\"'”’").split()
        tail = words[-1].lower() if words else ""
        if tail in _ABBREVIATIONS or len(tail) == 1:
            continue
        parts.append(buf.strip())
        buf = ""
    if buf.strip():
        parts.append(buf.strip())
    return [part for part in parts if part]


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def story_parts(event: Event, content: EnrichedContent) -> tuple[str, str]:
    """Split the story into the Postcard essence (first real sentence) and
    the FULL STORY body.

    Two dataset habits are cleaned here, whoever wrote the text:
    - the backup writer's metadata filler fragments ('It is recorded
      under…', 'The event occurred in…') are stripped wherever they appear
      — the category travels in the hashtags, the place in the date line;
    - a story that opens by repeating the headline has that prefix removed.
    Field sentences (people / entity / place) that the story does not
    already contain are appended to the FULL STORY body as real context."""
    text = re.sub(r"\s+", " ", content.story or "").strip()
    text = re.sub(r"\s*It is recorded under [^.]*\.", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*The event occurred in [^.]*\.", "", text, flags=re.IGNORECASE)
    text = text.strip()
    for candidate in (content.title, event.event_title):
        plain = (candidate or "").strip().rstrip(".")
        if plain and text.lower().startswith(plain.lower()):
            text = text[len(plain):].lstrip(" .—–-:;").strip()
            break

    sentences = _split_sentences(text)
    story_norm = _norm(content.story)
    extras: list[str] = []
    for value, template in (
        (event.people_involved, "The event involved {}."),
        (event.historical_entity, "It was connected with {}."),
        (event.city_location, "It took place in {}."),
    ):
        cleaned_value = (value or "").strip()
        if cleaned_value and _norm(cleaned_value) not in story_norm:
            extras.append(template.format(cleaned_value))

    if sentences:
        essence = sentences[0]
        rest = sentences[1:]
    elif extras:
        essence = extras[0]
        rest = []
        extras = extras[1:]
    else:
        essence = ""
        rest = []
    full_story = " ".join(rest + extras).strip()
    if not essence:
        essence = (event.event_title or content.title).strip()
    if not full_story:
        full_story = essence
    return essence, full_story


def build_rich_message(event: Event, enriched: EnrichedContent | None = None) -> dict:
    """The Postcard (network standard, 2026-10-30): date line, headline,
    one bold essence line, the whole story inside one expandable FULL
    STORY block, hashtags, source footer. No visible section headers."""
    content = enriched or enrich_event(event)
    hashtags = " ".join(_safe_tags(content.hashtags, event))
    essence, full_story = story_parts(event, content)

    blocks = [
        {"type": "paragraph", "text": [{"type": "bold", "text": date_line(event)}]},
        {"type": "heading", "size": 3, "text": content.title},
        {"type": "paragraph", "text": [{"type": "bold", "text": essence}]},
        {
            "type": "expandable_blockquote",
            "text": [{"type": "bold", "text": "FULL STORY"}, "\n" + full_story],
        },
        {"type": "paragraph", "text": hashtags},
        {
            "type": "footer",
            "text": [
                "Source: ",
                {"type": "url", "text": source_display_name(event), "url": event.source_1_url},
            ],
        },
    ]

    return {"blocks": blocks}


def build_rich_message_with_photo(event: Event, image_field: str, enriched: EnrichedContent | None = None) -> dict:
    payload = build_rich_message(event, enriched)
    payload["blocks"].insert(0, {
        "type": "photo",
        "photo": {"type": "photo", "media": f"attach://{image_field}"},
    })
    return payload


def build_card_rich_message() -> dict:
    """Card posts carry only the card image (same as the Facts quote
    cards): the card itself holds the date, headline and source."""
    return {"blocks": [{"type": "photo", "photo": {"type": "photo", "media": "attach://photo"}}]}


def format_fallback_caption(event: Event, enriched: EnrichedContent | None = None) -> str:
    """Fallback for API/client paths where Rich Messages cannot be used.
    Mirrors the Postcard: date line, headline, bold essence, story,
    hashtags, source."""
    content = enriched or enrich_event(event)
    hashtags = " ".join(_safe_tags(content.hashtags, event))
    source_url = html.escape(event.source_1_url, quote=True)
    essence, full_story = story_parts(event, content)
    prefix = "\n\n".join([
        f"<b>{esc(date_line(event))}</b>",
        f"<b>{esc(content.title)}</b>",
        f"<b>{esc(essence)}</b>",
    ])
    footer = "\n\n".join([
        hashtags,
        f'<b>Source:</b> <a href="{source_url}">{esc(source_display_name(event))}</a>',
    ])
    available = 1024 - len(prefix) - len(footer) - 4
    story = esc(full_story)
    if len(story) > available:
        story = story[:max(0, available - 1)].rsplit(" ", 1)[0].rstrip() + "…"
    return "\n\n".join([prefix, story, footer])
