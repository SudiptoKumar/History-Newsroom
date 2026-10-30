from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from config import ASSETS_DIR, GENERATED_DIR
from dataset import Event
from image_resolver import ResolvedImage, resolve_event_image

logger = logging.getLogger("today-in-history.images")

MAX_BYTES = 10 * 1024 * 1024
HANDLE = "@HistoryNewsroom"

# The network's house template (Vocabulary/Sports/Facts cards): warm paper,
# ink, one red accent, hairline frame, Playfair display type. Card width is
# always 1200; height follows the content with a 1:1 minimum (Karn,
# 2026-10-30): 1200 (1:1), 1500 (4:5), 1800 (2:3).
CARD_WIDTH = 1200
CARD_HEIGHTS = (1200, 1500, 1800)
PAPER = (252, 251, 248)
INK = (23, 23, 23)
MUTED = (108, 104, 99)
RED = (227, 27, 46)
HAIRLINE = (238, 234, 228)

_FONT_URLS = {
    "serif": "https://raw.githubusercontent.com/google/fonts/main/ofl/playfairdisplay/PlayfairDisplay%5Bwght%5D.ttf",
    "sans": "https://raw.githubusercontent.com/google/fonts/main/ofl/plusjakartasans/PlusJakartaSans%5Bwght%5D.ttf",
}
_FONT_FILES: dict[str, str] = {}


def _font_file(family: str) -> str:
    """Download the display font once per process (same approach as the
    other network bots); return "" when unavailable so callers fall back."""
    if family in _FONT_FILES:
        return _FONT_FILES[family]
    path = ""
    url = _FONT_URLS.get(family)
    if url:
        target = os.path.join(tempfile.gettempdir(), f"history_font_{family}.ttf")
        try:
            if os.path.isfile(target) and os.path.getsize(target) > 10000:
                path = target
            else:
                response = requests.get(url, timeout=30, headers={"User-Agent": "TodayInHistory/1.0"})
                response.raise_for_status()
                with open(target, "wb") as fh:
                    fh.write(response.content)
                if os.path.getsize(target) > 10000:
                    path = target
        except Exception:
            path = ""
    _FONT_FILES[family] = path
    return path


def _font(family: str, size: int, weight: int = 700):
    path = _font_file(family)
    if path:
        try:
            font = ImageFont.truetype(path, size=size)
            try:
                font.set_variation_by_axes([weight])
            except Exception:
                pass
            return font
        except Exception:
            pass
    candidate = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if os.path.isfile(candidate):
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=size)
    except Exception:
        return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, s: str, font, max_w: int) -> list[str]:
    lines, cur = [], ""
    for word in s.split():
        trial = (cur + " " + word).strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _output_path(event: Event) -> Path:
    return GENERATED_DIR / f"{event.event_id}.jpg"


def _save_jpeg(image: Image.Image, output: Path, quality: int) -> None:
    image.save(output, "JPEG", quality=quality, optimize=True, progressive=True)


def _fit_width(img: Image.Image) -> Image.Image:
    """Resize to the fixed publish width of 1200, keeping the original
    aspect ratio — the full photo stays visible, nothing is cropped."""
    scale = CARD_WIDTH / img.width
    return img.resize((CARD_WIDTH, max(1, round(img.height * scale))), Image.Resampling.LANCZOS)


def _stamp(rgba: Image.Image) -> Image.Image:
    """Adaptive handle chip, bottom-right (the network's photo treatment):
    light chip on dark images, dark chip on light images."""
    W, H = rgba.size
    brightness = rgba.convert("L").resize((1, 1)).getpixel((0, 0))
    if brightness < 125:
        bg, fg = (245, 245, 245, 225), (20, 24, 28, 255)
    else:
        bg, fg = (18, 22, 28, 205), (245, 245, 245, 255)
    overlay = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _font("sans", 24, 700)
    bbox = draw.textbbox((0, 0), HANDLE, font=font)
    chip_w = (bbox[2] - bbox[0]) + 44
    chip_h = (bbox[3] - bbox[1]) + 20
    x2, y2 = W - 28, H - 24
    draw.rounded_rectangle((x2 - chip_w, y2 - chip_h, x2, y2), radius=18, fill=bg)
    draw.text((x2 - chip_w + 22, y2 - chip_h + 10 - bbox[1]), HANDLE, font=font, fill=fg)
    return Image.alpha_composite(rgba, overlay)


def _prepare_image(source: Path, output: Path) -> Path:
    """Network photo treatment: width 1200 with the original ratio kept
    (never cropped) plus the @HistoryNewsroom stamp."""
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        image = _stamp(_fit_width(image).convert("RGBA")).convert("RGB")

        quality = 95
        _save_jpeg(image, output, quality)
        while output.stat().st_size > MAX_BYTES and quality > 70:
            quality -= 5
            _save_jpeg(image, output, quality)

        if output.stat().st_size > MAX_BYTES:
            current = image
            for _ in range(6):
                new_size = (max(1, int(current.width * 0.88)), max(1, int(current.height * 0.88)))
                current = current.resize(new_size, Image.Resampling.LANCZOS)
                _save_jpeg(current, output, 85)
                if output.stat().st_size <= MAX_BYTES:
                    break

    return output


def prepare_event_image(event: Event, resolved: ResolvedImage | None = None) -> Path | None:
    """Prepare a real historical image: resized to width 1200 with its
    ratio kept and stamped with the channel handle.

    Image decode/processing failures are treated as a normal "no usable image"
    condition so a single bad source can never terminate an entire batch.
    """
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    result = resolved or resolve_event_image(event)
    if not result or not result.path.exists():
        return None

    output = _output_path(event)
    try:
        prepared = _prepare_image(result.path, output)
        # Verify the final JPEG can actually be decoded before it reaches Telegram.
        with Image.open(prepared) as check:
            check.verify()
        return prepared
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        output.unlink(missing_ok=True)
        logger.warning("Image preparation failed for %s: %s", event.event_id, exc)
        return None


def generate_event_card(event: Event, enriched, output: Path) -> Path:
    """The generated card for events with no usable photo, in the network's
    house template: TH logo header, the date as a red eyebrow, the headline
    in Playfair, the essence line under it, and a source footer. Height
    follows the content with a 1:1 minimum."""
    from formatter import story_parts, year_label

    essence, _ = story_parts(event, enriched)
    category = (event.event_category or "History").strip().upper()
    date_text = f"{event.month.strip()} {event.day} · {year_label(event)}".upper()
    title = (enriched.title or event.event_title).strip()
    domain = urlparse(event.source_1_url).netloc.lower().removeprefix("www.") or "History"

    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    text_w = CARD_WIDTH - 184

    title_size = 56
    title_lines = _wrap(probe, title, _font("serif", title_size, 700), text_w)
    if len(title_lines) > 3:
        title_size = 46
        title_lines = _wrap(probe, title, _font("serif", title_size, 700), text_w)
    title_lh = round(title_size * 1.22)

    # Never print the same sentence twice on one card: when the essence is
    # just the headline restated (one-line dataset records), the card runs
    # headline-only.
    if essence.strip().lower().rstrip(".") == title.lower().rstrip("."):
        essence = ""
    essence_size = 34
    essence_lines = _wrap(probe, essence, _font("serif", essence_size, 400), text_w) if essence else []
    if len(essence_lines) > 5:
        essence_size = 30
        essence_lines = _wrap(probe, essence, _font("serif", essence_size, 400), text_w)
    essence_lh = round(essence_size * 1.38)

    content_h = 44 + len(title_lines) * title_lh + (30 + len(essence_lines) * essence_lh if essence_lines else 0)
    needed = 190 + content_h + 140
    height = next((h for h in CARD_HEIGHTS if h >= needed), CARD_HEIGHTS[-1])

    img = Image.new("RGB", (CARD_WIDTH, height), PAPER)
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((26, 26, CARD_WIDTH - 26, height - 26), radius=30, outline=HAIRLINE, width=2)

    # Header: TH logo + wordmark left, category right.
    logo_path = ASSETS_DIR / "today-in-history-logo.png"
    if logo_path.exists():
        with Image.open(logo_path) as logo:
            mark = logo.convert("RGBA")
            mark.thumbnail((58, 58), Image.Resampling.LANCZOS)
            img.paste(mark, (92, 54), mark)
    draw.text((92 + 74, 68), "TODAY IN HISTORY", font=_font("sans", 29, 800), fill=INK)
    cat_font = _font("sans", 22, 700)
    draw.text((CARD_WIDTH - 92 - draw.textlength(category, font=cat_font), 72), category, font=cat_font, fill=MUTED)

    # Content group, centred in the zone between header and footer.
    zone_top, zone_bottom = 190, height - 140
    y = zone_top + max(0, (zone_bottom - zone_top - content_h) / 2)
    draw.rectangle((92, y + 6, 98, y + 34), fill=RED)
    draw.text((118, y), date_text, font=_font("sans", 27, 800), fill=RED)
    y += 44 + 14
    for line in title_lines:
        draw.text((92, y), line, font=_font("serif", title_size, 700), fill=INK)
        y += title_lh
    if essence_lines:
        y += 30
    for line in essence_lines:
        draw.text((92, y), line, font=_font("serif", essence_size, 400), fill=INK)
        y += essence_lh

    # Footer.
    draw.line((92, height - 118, CARD_WIDTH - 92, height - 118), fill=HAIRLINE, width=2)
    draw.text((92, height - 92), HANDLE, font=_font("sans", 26, 800), fill=INK)
    source_text = f"Source: {domain}"
    src_font = _font("sans", 24, 400)
    draw.text((CARD_WIDTH - 92 - draw.textlength(source_text, font=src_font), height - 90), source_text, font=src_font, fill=MUTED)

    output.parent.mkdir(parents=True, exist_ok=True)
    _save_jpeg(img, output, 92)
    return output
