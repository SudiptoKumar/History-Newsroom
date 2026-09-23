from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

import requests

from config import SETTINGS
from dataset import Event

logger = logging.getLogger("today-in-history.ai")

CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
EXA_URL = "https://api.exa.ai/search"
UA = "TodayInHistoryBot/1.0 (+https://github.com/)"
TIMEOUT = 25


@dataclass(frozen=True)
class EnrichedContent:
    title: str
    story: str
    hashtags: list[str]


def _fallback(event: Event) -> EnrichedContent:
    """Keep the working V1 fallback, but make very short dataset descriptions readable.

    This is deliberately local and deterministic. It does not introduce a new API or
    alter the existing discovery/publishing pipeline.
    """
    title = event.event_title.strip() or "Historical Event"
    story = re.sub(r"\s+", " ", event.description.strip())
    if not story:
        story = f"A historical event recorded for {event.month} {event.day}."

    # Only use facts already present in the supplied dataset. This prevents a failed
    # AI request from reverting to an overly terse one-line description.
    additions: list[str] = []
    if event.people_involved.strip():
        additions.append(f"The event involved {event.people_involved.strip()}.")
    if event.historical_entity.strip():
        additions.append(f"It was connected with {event.historical_entity.strip()}.")
    if event.city_location.strip():
        additions.append(f"It took place in {event.city_location.strip()}.")
    if event.modern_country.strip() and event.city_location.strip():
        additions.append(f"The event is recorded in the historical context of {event.modern_country.strip()}.")
    if event.event_category.strip():
        additions.append(f"It is recorded under {event.event_category.strip()}.")
    if event.region.strip():
        additions.append(f"The event occurred in {event.region.strip()}.")

    if len(story.split()) < 45:
        for addition in additions:
            if addition.lower() not in story.lower():
                story = f"{story} {addition}".strip()
            if len(story.split()) >= 45:
                break

    story = story[:900].rstrip()
    tags = relevant_hashtags(event)
    return EnrichedContent(title=title, story=story, hashtags=tags)


def relevant_hashtags(event: Event) -> list[str]:
    values = [event.event_category, event.event_type, event.modern_country]
    tags: list[str] = []
    for value in values:
        cleaned = re.sub(r"[^A-Za-z0-9]+", "", value.replace("&", "and"))
        if not cleaned:
            continue
        tag = "#" + cleaned[:42]
        if tag.lower() not in {t.lower() for t in tags}:
            tags.append(tag)
        if len(tags) == 3:
            break
    # Avoid generic date tags; use a stable history tag only when the dataset has fewer than 3 signals.
    if len(tags) < 3:
        for fallback_tag in ("#History", "#HistoricalEvent"):
            if fallback_tag.lower() not in {t.lower() for t in tags}:
                tags.append(fallback_tag)
            if len(tags) == 3:
                break
    return tags[:3]


def needs_web_context(event: Event) -> bool:
    description_words = len(event.description.split())
    if description_words < 28:
        return True
    text = f"{event.description} {event.notes}".lower()
    gap_markers = (
        "details unavailable", "limited details", "context missing", "unclear", "needs context",
        "insufficient context", "not enough information", "more context",
    )
    return any(marker in text for marker in gap_markers)


def _exa_context(event: Event) -> list[dict[str, str]]:
    if not SETTINGS.exa_api_key or not SETTINGS.use_exa_context:
        return []
    query_parts = [
        f'"{event.event_title}"',
        event.year,
        event.city_location,
        event.modern_country,
        event.people_involved,
        "historical event context",
    ]
    query = " ".join(p.strip() for p in query_parts if p and p.strip())
    if not query:
        return []
    payload = {
        "query": query,
        "type": "auto",
        "numResults": 4,
        "contents": {"highlights": {"maxCharacters": 1400}},
    }
    try:
        response = requests.post(
            EXA_URL,
            headers={"x-api-key": SETTINGS.exa_api_key, "Content-Type": "application/json", "User-Agent": UA},
            json=payload,
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Exa context lookup failed for %s: %s", event.event_id, exc)
        return []

    context: list[dict[str, str]] = []
    for item in results:
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        highlights = item.get("highlights") or []
        if isinstance(highlights, list):
            snippet = " ".join(str(x).strip() for x in highlights if str(x).strip())
        else:
            snippet = str(highlights).strip()
        if title and snippet:
            context.append({"title": title, "url": url, "snippet": snippet[:1600]})
    return context[:4]


def _trim_title(title: str, fallback: str) -> str:
    words = re.findall(r"\S+", title.strip())
    if len(words) < 3:
        return fallback
    return " ".join(words[:10]).rstrip(" .:;,-")


def _trim_story(story: str) -> str:
    story = re.sub(r"\s+", " ", story.strip())
    words = story.split()
    if len(words) <= 70:
        return story
    clipped = " ".join(words[:70])
    # Prefer a clean sentence boundary when one is nearby.
    sentence_end = max(clipped.rfind(". "), clipped.rfind("! "), clipped.rfind("? "))
    if sentence_end >= 42:
        return clipped[:sentence_end + 1]
    return clipped.rstrip(" ,;:") + "…"


def _cerebras_generate(event: Event, web_context: list[dict[str, str]]) -> EnrichedContent:
    if not SETTINGS.cerebras_api_key or not SETTINGS.use_cerebras:
        return _fallback(event)

    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "story": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 3},
        },
        "required": ["title", "story", "hashtags"],
        "additionalProperties": False,
    }

    record = {
        "date": f"{event.month} {event.day}",
        "year": f"{event.year} {event.era}".strip(),
        "event_title": event.event_title,
        "description": event.description,
        "city": event.city_location,
        "region": event.region,
        "country": event.modern_country,
        "people": event.people_involved,
        "entity": event.historical_entity,
        "category": event.event_category,
        "type": event.event_type,
        "source_name": event.source_1_name,
        "source_url": event.source_1_url,
        "verification_status": event.verification_status,
        "date_certainty": event.date_certainty,
        "significance_score": event.significance_score,
    }

    context_text = "No external context was needed."
    if web_context:
        context_text = "\n\n".join(
            f"SOURCE: {item['title']}\nURL: {item['url']}\nEXCERPT: {item['snippet']}"
            for item in web_context
        )

    system = """You write short, factual historical posts for a Telegram history channel.

Rules:
- Keep the supplied event date and event identity unchanged.
- Explain what actually happened, who or what was involved, and enough context for a general reader to understand it.
- Use the dataset as the primary factual source. External excerpts may add missing context only when supported.
- Never invent a date, person, casualty figure, quote, motive, or political judgment.
- Keep a neutral historical tone with no present-day editorializing.
- Title: 4-10 words, natural news-history headline, no period.
- Story: 45-70 words, usually 3-4 sentences, readable on a phone. Write a compact mini-narrative so a reader can understand what actually happened without needing the metadata. Explain the event, identify the key people or groups when relevant, and add only the essential historical context supported by the record or supplied context. Do not simply repeat the dataset description when it is too short. Do not use labels such as People, Entity, Category, Context, or Significance.
- Return exactly 3 relevant hashtags. Do not include #TodayInHistory or date-number hashtags.
"""

    user = (
        "Rewrite the historical record into a concise reader-friendly post.\n\n"
        f"RECORD:\n{json.dumps(record, ensure_ascii=False, indent=2)}\n\n"
        f"OPTIONAL WEB CONTEXT:\n{context_text}"
    )

    payload = {
        "model": SETTINGS.cerebras_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "history_post", "strict": True, "schema": schema},
        },
        "max_completion_tokens": 500,
        "temperature": 0.35,
    }

    headers = {
        "Authorization": f"Bearer {SETTINGS.cerebras_api_key}",
        "Content-Type": "application/json",
        "User-Agent": UA,
    }

    try:
        for attempt in range(2):
            current_payload = dict(payload)
            messages = list(payload["messages"])
            if attempt == 1:
                messages[0] = {
                    "role": "system",
                    "content": system + "\nThe previous draft was too short. Rewrite it again and make the story at least 45 words while staying factual and concise.",
                }
            current_payload["messages"] = messages
            response = requests.post(
                CEREBRAS_URL,
                headers=headers,
                json=current_payload,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            raw = response.json()["choices"][0]["message"]["content"]
            data = json.loads(raw)
            title = _trim_title(str(data.get("title") or "").strip(), event.event_title.strip() or "Historical Event")
            story = _trim_story(str(data.get("story") or "").strip())
            tags = []
            forbidden = {"todayinhistory", "history", "history21"}
            for tag in data.get("hashtags", []):
                cleaned = re.sub(r"[^A-Za-z0-9]+", "", str(tag).replace("#", "").strip())
                if not cleaned or cleaned.lower() in forbidden:
                    continue
                candidate = "#" + cleaned[:42]
                if candidate.lower() not in {item.lower() for item in tags}:
                    tags.append(candidate)
            for fallback_tag in relevant_hashtags(event):
                if len(tags) == 3:
                    break
                if fallback_tag.lower() not in {item.lower() for item in tags} and fallback_tag.lstrip("#").lower() not in forbidden:
                    tags.append(fallback_tag)
            tags = tags[:3]
            if len(tags) != 3 or not title or not story:
                raise ValueError("Structured output was incomplete")
            if len(story.split()) < 45 and attempt == 0:
                continue
            return EnrichedContent(title=title, story=story, hashtags=tags)
        raise ValueError("Cerebras returned a story shorter than 45 words after retry")
    except (requests.RequestException, ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("Cerebras enrichment failed for %s: %s", event.event_id, exc)
        return _fallback(event)


def enrich_event(event: Event) -> EnrichedContent:
    context = _exa_context(event) if needs_web_context(event) else []
    return _cerebras_generate(event, context)
