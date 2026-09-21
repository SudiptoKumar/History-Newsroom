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

UA = "TodayInHistoryBot/1.1 (+https://github.com/)"
TIMEOUT = 15

@dataclass(frozen=True)
class ResolvedImage:
    path: Path
    source_url: str
    source_page: str
    source_name: str


def _safe_name(event: Event) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", event.event_id or event.event_title)[:100]


def _get(url: str) -> requests.Response | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=True)
        r.raise_for_status()
        return r
    except requests.RequestException as exc:
        logger.debug("GET failed %s: %s", url, exc)
        return None


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


def _download_image(url: str, destination: Path) -> bool:
    r = _get(url)
    if not r:
        return False
    content_type = r.headers.get("content-type", "").lower()
    if not content_type.startswith("image/"):
        return False
    if len(r.content) < 10_000:
        return False
    destination.write_bytes(r.content)
    return True


def _commons_image(event: Event, destination: Path) -> ResolvedImage | None:
    query_parts = [event.event_title, event.historical_entity, event.modern_country]
    query = " ".join(p.strip() for p in query_parts if p.strip())
    if not query:
        return None
    api = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query", "generator": "search", "gsrsearch": query,
        "gsrnamespace": 6, "gsrlimit": 12, "prop": "imageinfo",
        "iiprop": "url|mime|size|extmetadata", "iiurlwidth": 1800, "format": "json",
    }
    try:
        r = requests.get(api, params=params, headers={"User-Agent": UA}, timeout=TIMEOUT)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})
    except (requests.RequestException, ValueError) as exc:
        logger.debug("Commons lookup failed: %s", exc)
        return None

    candidates = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        mime = (info.get("mime") or "").lower()
        width = int(info.get("width") or 0)
        height = int(info.get("height") or 0)
        url = info.get("thumburl") or info.get("url")
        meta = info.get("extmetadata") or {}
        license_name = (meta.get("LicenseShortName", {}).get("value") or "").lower()
        author = re.sub(r"<[^>]+>", "", meta.get("Artist", {}).get("value") or "").strip()
        if mime.startswith("image/") and url and width >= 500 and height >= 300 and license_name:
            title = page.get("title", "")
            score = 0
            lower = title.lower()
            for token in re.findall(r"[a-z0-9]+", event.event_title.lower()):
                if len(token) > 3 and token in lower:
                    score += 1
            candidates.append((score, width * height, url, title, author, license_name))
    candidates.sort(reverse=True)
    if not candidates:
        return None
    _, _, image_url, page_title, author, license_name = candidates[0]
    if _download_image(image_url, destination):
        page_url = "https://commons.wikimedia.org/wiki/" + quote_plus(page_title.replace(" ", "_"))
        credit = "Wikimedia Commons"
        if author:
            credit += f" · {author}"
        if license_name:
            credit += f" · {license_name}"
        return ResolvedImage(destination, image_url, page_url, credit)
    return None


def _exa_commons_image(event: Event, destination: Path) -> ResolvedImage | None:
    from config import SETTINGS
    if not SETTINGS.exa_api_key:
        return None
    query = " ".join(p for p in [event.event_title, event.year, event.historical_entity, event.modern_country] if p.strip())
    if not query:
        return None
    try:
        r = requests.post(
            "https://api.exa.ai/search",
            headers={"x-api-key": SETTINGS.exa_api_key, "Content-Type": "application/json", "User-Agent": UA},
            json={"query": query + " site:commons.wikimedia.org historical photograph", "type": "auto", "numResults": 8},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        results = r.json().get("results", [])
    except (requests.RequestException, ValueError) as exc:
        logger.debug("Exa Commons search failed: %s", exc)
        return None
    for result in results:
        page_url = result.get("url") or ""
        host = urlparse(page_url).netloc.lower()
        if not (host == "commons.wikimedia.org" or host.endswith(".commons.wikimedia.org")):
            continue
        response = _get(page_url)
        if not response:
            continue
        image_url = _image_url_from_html(response.url, response.text[:2_000_000])
        if image_url and _download_image(image_url, destination):
            return ResolvedImage(destination, image_url, response.url, "Wikimedia Commons")
    return None


def resolve_event_image(event: Event) -> ResolvedImage | None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    destination = GENERATED_DIR / f"{_safe_name(event)}.source"
    # Actual source image first, then reputable public/open historical repositories.
    for resolver in (_commons_image, _exa_commons_image):
        try:
            result = resolver(event, destination)
            if result:
                return result
        except Exception as exc:
            logger.warning("Image resolver %s failed for %s: %s", resolver.__name__, event.event_id, exc)
    return None
