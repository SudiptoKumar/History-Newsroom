from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass

import requests

from config import SETTINGS
from dataset import Event

logger = logging.getLogger("today-in-history.ai")

CEREBRAS_URL = "https://api.cerebras.ai/v1/chat/completions"
EXA_URL = "https://api.exa.ai/search"
UA = "TodayInHistoryBot/1.7 (+https://github.com/)"
TIMEOUT = 25


@dataclass(frozen=True)
class EnrichedContent:
    title: str
    story: str
    hashtags: list[str]


def _fallback(event: Event, web_context: list[dict[str, str]] | None = None) -> EnrichedContent:
    """Build a useful fallback without inventing facts when AI is unavailable."""
    title = event.event_title.strip() or "Historical Event"
    story = re.sub(r"\s+", " ", event.description.strip())
    sentences: list[str] = []
    if story:
        sentences.append(story.rstrip())

    # When the dataset description is too terse, prefer factual context returned by Exa.
    if web_context:
        base = story.lower()
        for item in web_context:
            snippet = re.sub(r"\s+", " ", str(item.get("snippet") or "").strip())
            if not snippet:
                continue
            snippet_sentences = re.split(r"(?<=[.!?])\s+", snippet)
            for sentence in snippet_sentences:
                sentence = sentence.strip(" \t\r\n-–•")
                if len(sentence.split()) < 7:
                    continue
                if sentence.lower() in base:
                    continue
                sentences.append(sentence)
                base += " " + sentence.lower()
                if len(" ".join(sentences).split()) >= SETTINGS.cerebras_story_min_words:
                    break
            if len(" ".join(sentences).split()) >= SETTINGS.cerebras_story_min_words:
                break

    # Last-resort expansion uses only fields already present in the dataset.
    if len(" ".join(sentences).split()) < SETTINGS.cerebras_story_min_words:
        details: list[str] = []
        if event.people_involved.strip():
            details.append(f"The event involved {event.people_involved.strip()}.")
        if event.historical_entity.strip() and event.historical_entity.strip().lower() not in event.event_title.lower():
            details.append(f"It was connected with {event.historical_entity.strip()}.")
        if event.city_location.strip():
            details.append(f"The event took place in {event.city_location.strip()}.")
        if event.event_type.strip():
            details.append(f"The event is recorded as a {event.event_type.strip()}.")
        if event.event_category.strip():
            details.append(f"It is associated with {event.event_category.strip()} in the historical record.")
        if event.region.strip() and event.region.strip().lower() not in {"world", "global"}:
            details.append(f"The event is placed in the {event.region.strip()} region.")
        for detail in details:
            if detail.lower() not in " ".join(sentences).lower():
                sentences.append(detail)
            if len(" ".join(sentences).split()) >= SETTINGS.cerebras_story_min_words:
                break

    if not sentences:
        sentences.append(f"A historical event recorded for {event.month} {event.day}.")

    story = re.sub(r"\s+", " ", " ".join(sentences).strip())
    if len(story.split()) < SETTINGS.cerebras_story_min_words:
        date_context = f"The record places this event on {event.month} {event.day}, {event.year} in its historical timeline."
        if date_context.lower() not in story.lower():
            story = f"{story} {date_context}".strip()
    if len(story.split()) > SETTINGS.cerebras_story_max_words:
        story = _trim_story(story)
    return EnrichedContent(title=title, story=story, hashtags=relevant_hashtags(event))

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
    max_words = SETTINGS.cerebras_story_max_words
    if len(words) <= max_words:
        return story
    clipped = " ".join(words[:max_words])
    sentence_end = max(clipped.rfind(". "), clipped.rfind("! "), clipped.rfind("? "))
    if sentence_end >= max(35, int(max_words * 0.58)):
        return clipped[:sentence_end + 1]
    return clipped.rstrip(" ,;:") + "…"

_last_cerebras_request_at = 0.0


def _wait_for_cerebras_slot() -> None:
    global _last_cerebras_request_at
    minimum = max(0.0, SETTINGS.cerebras_min_interval_seconds)
    elapsed = time.monotonic() - _last_cerebras_request_at
    if elapsed < minimum:
        time.sleep(minimum - elapsed)
    _last_cerebras_request_at = time.monotonic()


def _parse_json_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        first = text.find("{")
        last = text.rfind("}")
        if first >= 0 and last > first:
            return json.loads(text[first:last + 1])
        raise


def _cerebras_generate(event: Event, web_context: list[dict[str, str]]) -> EnrichedContent:
    if not SETTINGS.cerebras_api_key or not SETTINGS.use_cerebras:
        return _fallback(event, web_context)

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
- Story: 45-70 words, usually 3-4 sentences, readable on a phone. Write a compact mini-narrative that explains what actually happened, who or what mattered, and the immediate historical context needed to understand it. Expand a short dataset description using supported external context when supplied. Do not merely repeat the dataset description. Do not use labels such as People, Entity, Category, Context, or Significance.
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

    last_error: Exception | None = None
    max_attempts = max(1, SETTINGS.cerebras_retry_attempts)
    for attempt in range(max_attempts):
        try:
            _wait_for_cerebras_slot()
            current_payload = dict(payload)
            messages = list(payload["messages"])
            if attempt > 0:
                messages[0] = {
                    "role": "system",
                    "content": system + f"\nRewrite the draft. The story must be at least {SETTINGS.cerebras_story_min_words} words, but never exceed {SETTINGS.cerebras_story_max_words} words. Keep it factual and concise.",
                }
            current_payload["messages"] = messages
            response = requests.post(
                CEREBRAS_URL,
                headers=headers,
                json=current_payload,
                timeout=TIMEOUT,
            )
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    wait_seconds = max(1.0, float(retry_after)) if retry_after else min(20.0, 3.0 * (2 ** attempt))
                except ValueError:
                    wait_seconds = min(20.0, 3.0 * (2 ** attempt))
                logger.warning("Cerebras rate limit for %s; retrying in %.1fs (%d/%d)", event.event_id, wait_seconds, attempt + 1, max_attempts)
                time.sleep(wait_seconds)
                continue
            response.raise_for_status()
            body = response.json()
            choices = body.get("choices") or []
            if not choices:
                raise ValueError("Cerebras response contained no choices")
            message = choices[0].get("message") or {}
            raw = message.get("content")
            if not raw:
                refusal = message.get("refusal") or body.get("error", {}).get("message")
                raise ValueError(f"Cerebras returned no content{': ' + str(refusal) if refusal else ''}")
            data = _parse_json_response(str(raw))
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
            word_count = len(story.split())
            if word_count < SETTINGS.cerebras_story_min_words:
                raise ValueError(f"Cerebras story too short: {word_count} words")
            return EnrichedContent(title=title, story=story, hashtags=tags)
        except (requests.RequestException, ValueError, KeyError, json.JSONDecodeError, TypeError) as exc:
            last_error = exc
            if attempt + 1 < max_attempts:
                logger.warning("Cerebras enrichment retry for %s: %s", event.event_id, exc)
                time.sleep(min(5.0, 1.0 + attempt))
                continue
            break

    logger.warning("Cerebras enrichment failed for %s after %d attempts: %s", event.event_id, max_attempts, last_error)
    return _fallback(event, web_context)


def enrich_event(event: Event) -> EnrichedContent:
    context = _exa_context(event) if needs_web_context(event) else []
    return _cerebras_generate(event, context)
