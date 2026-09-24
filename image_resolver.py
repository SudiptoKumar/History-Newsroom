from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import requests

from config import GENERATED_DIR
from dataset import Event

logger = logging.getLogger("today-in-history.images")

UA = "TodayInHistoryBot/1.1 (historical image resolver; https://github.com/SudiptoKumar/History-Newsroom)"
TIMEOUT = 20
MIN_DOWNLOAD_BYTES = 4_000
MIN_EDGE = 250


@dataclass(frozen=True)
class ResolvedImage:
    path: Path
    source_url: str
    source_page: str
    source_name: str


def _safe_name(event: Event) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", event.event_id or event.event_title)[:100]


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", (value or "").lower()) if len(token) > 2]


def _get(url: str, *, params: dict | None = None) -> requests.Response | None:
    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": UA, "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        logger.debug("GET failed %s: %s", url, exc)
        return None


def _download_image(url: str, destination: Path) -> bool:
    response = _get(url)
    if not response or len(response.content) < MIN_DOWNLOAD_BYTES:
        return False

    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    suffix = Path(urlparse(response.url).path).suffix.lower()
    looks_like_image = content_type.startswith("image/") or suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
    if not looks_like_image:
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    return True


def _image_url_from_html(page_url: str, body: str) -> str | None:
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, body, flags=re.I)
        if match:
            value = html.unescape(match.group(1)).strip()
            return urljoin(page_url, value)
    return None


def _page_text(page: dict, info: dict) -> str:
    meta = info.get("extmetadata") or {}
    fields = [
        str(page.get("title", "")),
        str(meta.get("ObjectName", {}).get("value", "")),
        str(meta.get("ImageDescription", {}).get("value", "")),
        str(meta.get("Categories", {}).get("value", "")),
    ]
    return re.sub(r"<[^>]+>", " ", " ".join(fields)).lower()


def _score_candidate(event: Event, text: str, *, title_text: str = "") -> int:
    score = 0
    title = event.event_title.strip().lower()
    title_tokens = _tokens(event.event_title)
    people_tokens = _tokens(event.people_involved)
    location_tokens = _tokens(event.city_location or event.modern_country)
    entity_tokens = _tokens(event.historical_entity)
    year = event.year.strip()

    if title and title in text:
        score += 12
    if title and title in title_text.lower():
        score += 8
    for token in title_tokens:
        if token in text:
            score += 2
    for token in people_tokens:
        if token in text:
            score += 3
    for token in location_tokens:
        if token in text:
            score += 2
    for token in entity_tokens:
        if token in text:
            score += 1
    if year and year in text:
        score += 3

    generic_terms = (
        "map", "flag", "coat of arms", "logo", "symbol", "icon",
        "location map", "diagram", "route map", "blank map",
    )
    if any(term in text for term in generic_terms):
        score -= 6
    return score


def _commons_search(event: Event, query: str, destination: Path) -> ResolvedImage | None:
    api = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": 6,
        "gsrlimit": 30,
        "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata",
        "iiurlwidth": 2400,
        "format": "json",
    }
    try:
        response = _get(api, params=params)
        if not response:
            return None
        pages = response.json().get("query", {}).get("pages", {})
    except (ValueError, TypeError) as exc:
        logger.debug("Commons JSON parsing failed for %r: %s", query, exc)
        return None

    candidates: list[tuple[int, int, str, str, str, str]] = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        mime = (info.get("mime") or "").lower()
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        url = info.get("thumburl") or info.get("url")
        if not (mime.startswith("image/") and url and min(width, height) >= MIN_EDGE):
            continue
        if mime in {"image/svg+xml", "image/x-icon"}:
            continue

        title = str(page.get("title", ""))
        text = _page_text(page, info)
        score = _score_candidate(event, text, title_text=title)
        author = re.sub(r"<[^>]+>", "", str((info.get("extmetadata") or {}).get("Artist", {}).get("value", ""))).strip()
        license_name = re.sub(r"<[^>]+>", "", str((info.get("extmetadata") or {}).get("LicenseShortName", {}).get("value", ""))).strip()
        candidates.append((score, width * height, url, title, author, license_name))

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if not candidates or candidates[0][0] < 3:
        return None

    score, _, image_url, page_title, author, license_name = candidates[0]
    if not _download_image(image_url, destination):
        return None

    page_url = "https://commons.wikimedia.org/wiki/" + quote_plus(page_title.replace(" ", "_"))
    credit = "Wikimedia Commons"
    if author:
        credit += f" · {author}"
    if license_name:
        credit += f" · {license_name}"
    logger.info("Historical image selected for %s from Wikimedia Commons: %s", event.event_id, page_title)
    return ResolvedImage(destination, image_url, page_url, credit)


def _commons_image(event: Event, destination: Path) -> ResolvedImage | None:
    title = event.event_title.strip()
    context_parts = [
        event.city_location,
        event.modern_country,
        event.people_involved,
        event.historical_entity,
    ]
    context = " ".join(part.strip() for part in context_parts if part and part.strip())

    queries: list[str] = []
    if title:
        queries.append(title)
        if event.year.strip():
            queries.append(f"{title} {event.year.strip()}")
        if context:
            queries.append(f"{title} {context}")
    for people in _tokens(event.people_involved)[:3]:
        queries.append(f"{title} {people}".strip())
    if event.city_location.strip():
        queries.append(event.city_location.strip())

    seen: set[str] = set()
    for query in queries:
        query = re.sub(r"\s+", " ", query).strip()
        if not query or query.lower() in seen:
            continue
        seen.add(query.lower())
        result = _commons_search(event, query, destination)
        if result:
            return result
    return None


def _wikipedia_page_image(event: Event, destination: Path) -> ResolvedImage | None:
    api = "https://en.wikipedia.org/w/api.php"

    # 1) Try the event title as an exact article title.
    exact_params = {
        "action": "query",
        "titles": event.event_title.strip(),
        "prop": "pageimages|info",
        "inprop": "url",
        "piprop": "thumbnail|original",
        "pithumbsize": 2400,
        "format": "json",
    }
    response = _get(api, params=exact_params)
    if response:
        try:
            pages = response.json().get("query", {}).get("pages", {})
        except (ValueError, TypeError):
            pages = {}
        for page in pages.values():
            image = (page.get("original") or {}).get("source") or (page.get("thumbnail") or {}).get("source")
            if not image:
                continue
            width = int((page.get("original") or {}).get("width") or (page.get("thumbnail") or {}).get("width") or 0)
            height = int((page.get("original") or {}).get("height") or (page.get("thumbnail") or {}).get("height") or 0)
            if min(width, height) < MIN_EDGE:
                continue
            page_title = str(page.get("title", event.event_title))
            if _download_image(image, destination):
                page_url = str(page.get("fullurl") or f"https://en.wikipedia.org/wiki/{quote_plus(page_title.replace(' ', '_'))}")
                logger.info("Historical image selected for %s from Wikipedia: %s", event.event_id, page_title)
                return ResolvedImage(destination, image, page_url, "Wikipedia")

    # 2) Search Wikipedia when the event title is not itself an article.
    search_params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": event.event_title.strip(),
        "gsrnamespace": 0,
        "gsrlimit": 10,
        "prop": "pageimages|info",
        "inprop": "url",
        "piprop": "thumbnail|original",
        "pithumbsize": 2400,
        "format": "json",
    }
    response = _get(api, params=search_params)
    if not response:
        return None
    try:
        pages = response.json().get("query", {}).get("pages", {})
    except (ValueError, TypeError):
        return None

    candidates: list[tuple[int, int, str, str, str]] = []
    for page in pages.values():
        image = (page.get("original") or {}).get("source") or (page.get("thumbnail") or {}).get("source")
        if not image:
            continue
        width = int((page.get("original") or {}).get("width") or (page.get("thumbnail") or {}).get("width") or 0)
        height = int((page.get("original") or {}).get("height") or (page.get("thumbnail") or {}).get("height") or 0)
        if min(width, height) < MIN_EDGE:
            continue
        title = str(page.get("title", ""))
        score = _score_candidate(event, title.lower(), title_text=title)
        candidates.append((score, width * height, image, title, str(page.get("fullurl") or "")))

    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if not candidates or candidates[0][0] < 3:
        return None

    score, _, image, page_title, page_url = candidates[0]
    if not _download_image(image, destination):
        return None
    if not page_url:
        page_url = f"https://en.wikipedia.org/wiki/{quote_plus(page_title.replace(' ', '_'))}"
    logger.info("Historical image selected for %s from Wikipedia search: %s (score=%d)", event.event_id, page_title, score)
    return ResolvedImage(destination, image, page_url, "Wikipedia")


def _exa_commons_image(event: Event, destination: Path) -> ResolvedImage | None:
    from config import SETTINGS

    if not SETTINGS.exa_api_key:
        return None
    query = " ".join(
        part.strip()
        for part in [event.event_title, event.year, event.historical_entity, event.city_location, event.modern_country]
        if part and part.strip()
    )
    if not query:
        return None
    try:
        response = requests.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": SETTINGS.exa_api_key, "Content-Type": "application/json", "User-Agent": UA},
            json={"query": query + " historical photograph site:commons.wikimedia.org", "type": "auto", "numResults": 8},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
    except (requests.RequestException, ValueError, TypeError) as exc:
        logger.debug("Exa Commons search failed for %s: %s", event.event_id, exc)
        return None

    for result in results:
        page_url = result.get("url") or ""
        host = urlparse(page_url).netloc.lower()
        if not (host == "commons.wikimedia.org" or host.endswith(".commons.wikimedia.org")):
            continue
        page_response = _get(page_url)
        if not page_response:
            continue
        image_url = _image_url_from_html(page_response.url, page_response.text[:2_000_000])
        if image_url and _download_image(image_url, destination):
            logger.info("Historical image selected for %s through Exa -> Wikimedia Commons", event.event_id)
            return ResolvedImage(destination, image_url, page_response.url, "Wikimedia Commons")
    return None


def resolve_event_image(event: Event) -> ResolvedImage | None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    destination = GENERATED_DIR / f"{_safe_name(event)}.source"

    # Prefer Wikimedia Commons, then a matching Wikipedia article, and only then Exa discovery.
    for resolver in (_commons_image, _wikipedia_page_image, _exa_commons_image):
        try:
            result = resolver(event, destination)
            if result:
                return result
        except Exception as exc:
            logger.warning("Image resolver %s failed for %s: %s", resolver.__name__, event.event_id, exc)

    logger.warning("No historical image found for %s (%s)", event.event_id, event.event_title)
    return None
