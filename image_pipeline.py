from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, UnidentifiedImageError

from config import ASSETS_DIR, GENERATED_DIR
from dataset import Event
from image_resolver import ResolvedImage, resolve_event_image

logger = logging.getLogger("today-in-history.images")

MAX_BYTES = 10 * 1024 * 1024
HANDLE = "@HistoryNewsroom"

# The network specimen-label template (Karn's final design, 2026-11-12,
# first shipped in DailyFacts): cream paper, dashed ink border, badge +
# channel-name header, red kicker, DM Serif Display content type with
# Archivo label type. Card width is always 1200; height follows the
# content: 800 (3:2) for short events, then 1200 (1:1), 1500 (4:5),
# 1800 (2:3). The 800 tier (Karn, 2026-11-12) uses the compact
# geometry of the approved sample; taller tiers keep the original layout.
CARD_WIDTH = 1200
CARD_HEIGHTS = (800, 1200, 1500, 1800)
# Compact (800) tier: content zone between the kicker and the footer
# rule. A card only earns the tier if its whole stack fits this zone
# with the title at 56px or larger.
COMPACT_TEXT_TOP = 262
COMPACT_TEXT_BOTTOM = 800 - 144 - 32
COMPACT_MIN_FONT = 56
PAPER = (247, 242, 231)
INK = (24, 22, 19)
TEXT_INK = (28, 25, 21)
MUTED = (110, 100, 86)
RED = (224, 26, 44)

_FONT_URLS = {
    "serif": "https://raw.githubusercontent.com/google/fonts/main/ofl/playfairdisplay/PlayfairDisplay%5Bwght%5D.ttf",
    "sans": "https://raw.githubusercontent.com/google/fonts/main/ofl/plusjakartasans/PlusJakartaSans%5Bwght%5D.ttf",
    # Specimen-label card type (2026-11-12 rollout, same files as DailyFacts).
    "display": "https://fonts.gstatic.com/s/dmserifdisplay/v17/-nFnOHM81r4j6k0gjAW3mujVU2B2K_c.ttf",
    "archivo": "https://fonts.gstatic.com/s/archivo/v25/k3k6o8UDI-1M0wlSV9XAw6lQkqWY8Q82sJaRE-NWIDdgffTT0zRp8A.ttf",
    "archivo_medium": "https://fonts.gstatic.com/s/archivo/v25/k3k6o8UDI-1M0wlSV9XAw6lQkqWY8Q82sJaRE-NWIDdgffTTBjNp8A.ttf",
    "archivo_black": "https://fonts.gstatic.com/s/archivo/v25/k3k6o8UDI-1M0wlSV9XAw6lQkqWY8Q82sJaRE-NWIDdgffTTnTRp8A.ttf",
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


def _tracked_width(draw: ImageDraw.ImageDraw, s: str, font, tracking: int) -> float:
    return sum(draw.textlength(ch, font=font) + tracking for ch in s) - (tracking if s else 0)


def _draw_tracked(draw: ImageDraw.ImageDraw, x: float, y: float, s: str, font, fill, tracking: int) -> float:
    for ch in s:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking
    return x


def _tracked_strip(text: str, font, fill, tracking: int) -> Image.Image:
    """Render tracked text on its own strip, cropped to the real pixel
    box, so callers can align it by measured height (e.g. centered on a
    badge's midline) instead of guessing from font metrics."""
    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    w = int(_tracked_width(probe, text, font, tracking)) + 8
    strip = Image.new("RGBA", (w, font.size * 2), (0, 0, 0, 0))
    _draw_tracked(ImageDraw.Draw(strip), 4, font.size // 2, text, font, fill, tracking)
    bbox = strip.getbbox()
    return strip.crop(bbox) if bbox else strip


def _dashed_rectangle(draw: ImageDraw.ImageDraw, box, fill, width: int = 3, dash: int = 18, gap: int = 12) -> None:
    x0, y0, x1, y1 = box
    x = x0
    while x < x1:
        nxt = min(x + dash, x1)
        draw.line((x, y0, nxt, y0), fill=fill, width=width)
        draw.line((x, y1, nxt, y1), fill=fill, width=width)
        x += dash + gap
    y = y0
    while y < y1:
        nxt = min(y + dash, y1)
        draw.line((x0, y, x0, nxt), fill=fill, width=width)
        draw.line((x1, y, x1, nxt), fill=fill, width=width)
        y += dash + gap


def _logo_mark(height: int = 60) -> Image.Image | None:
    """The TH logo with its white margins cropped away, resized to the
    badge height; None when the asset is unavailable."""
    logo_path = ASSETS_DIR / "today-in-history-logo.png"
    if not logo_path.exists():
        return None
    try:
        with Image.open(logo_path) as opened:
            img = opened.convert("RGB")
    except Exception:
        return None
    bg = Image.new("RGB", img.size, (255, 255, 255))
    diff = ImageChops.difference(img, bg).convert("L")
    bbox = diff.point(lambda p: 255 if p > 18 else 0).getbbox()
    if bbox:
        img = img.crop(bbox)
    return img.resize((round(img.width * height / img.height), height), Image.Resampling.LANCZOS)


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
    """The generated card for events with no usable photo, in the network
    specimen-label template (Karn's final design, 2026-11-12): a cream
    label with a dashed ink border — the TH logo in a white badge beside
    the channel name, the event's date as the red kicker (category at the
    row's right), the headline and essence in DM Serif Display, and a
    source + handle footer. Height follows the content, 1:1 minimum."""
    from formatter import story_parts, year_label

    essence, _ = story_parts(event, enriched)
    category = (event.event_category or "History").strip()
    date_text = f"{event.month.strip()} {event.day} · {year_label(event)}"
    title = (enriched.title or event.event_title).strip()
    domain = urlparse(event.source_1_url).netloc.lower().removeprefix("www.") or "History"

    probe = ImageDraw.Draw(Image.new("RGB", (8, 8)))
    text_w = CARD_WIDTH - 184

    # Never print the same sentence twice on one card: when the essence is
    # just the headline restated (one-line dataset records), the card runs
    # headline-only.
    if essence.strip().lower().rstrip(".") == title.lower().rstrip("."):
        essence = ""
    essence_size = 34
    essence_lines = _wrap(probe, essence, _font("display", essence_size), text_w) if essence else []
    if len(essence_lines) > 5:
        essence_size = 30
        essence_lines = _wrap(probe, essence, _font("display", essence_size), text_w)
    essence_lh = round(essence_size * 1.38)
    essence_h = (36 + len(essence_lines) * essence_lh) if essence_lines else 0

    # Title: auto-fit the largest DM Serif size whose block, together
    # with the essence, fits the tallest card tier.
    title_size, title_lines = 40, []
    for candidate in range(88, 39, -2):
        lines = _wrap(probe, title, _font("display", candidate), text_w)
        total = 292 + len(lines) * candidate * 1.24 + essence_h + 214 + 24
        if total <= CARD_HEIGHTS[-1]:
            title_size, title_lines = candidate, lines
            break
    else:
        title_lines = _wrap(probe, title, _font("display", 40), text_w)
    title_lh = title_size * 1.24

    needed = 292 + len(title_lines) * title_lh + essence_h + 214 + 24
    if needed > CARD_HEIGHTS[-1] and essence_lines:
        # Pathological length: trim the essence (never the headline)
        # until the pair fits the tallest tier.
        words = essence.split()
        while words and needed > CARD_HEIGHTS[-1]:
            words = words[:-1]
            trimmed = " ".join(words).rstrip(" ,.;") + "…"
            essence_lines = _wrap(probe, trimmed, _font("display", essence_size), text_w)
            essence_h = 36 + len(essence_lines) * essence_lh
            needed = 292 + len(title_lines) * title_lh + essence_h + 214 + 24

    # Compact (800) tier: re-measure the title and essence at the
    # compact width against the compact middle zone; the card earns the
    # tier only if the whole stack fits with the title still at a
    # readable size (>= 56px).
    c_text_w = CARD_WIDTH - 80 - 80
    c_essence_size = essence_size
    c_essence_lines = _wrap(probe, essence, _font("display", c_essence_size), c_text_w) if essence else []
    if len(c_essence_lines) > 5:
        c_essence_size = 30
        c_essence_lines = _wrap(probe, essence, _font("display", c_essence_size), c_text_w)
    c_essence_lh = round(c_essence_size * 1.38)
    c_essence_h = (36 + len(c_essence_lines) * c_essence_lh) if c_essence_lines else 0
    c_zone_h = COMPACT_TEXT_BOTTOM - COMPACT_TEXT_TOP
    c_title_size, c_title_lines = 40, []
    for candidate in range(88, COMPACT_MIN_FONT - 1, -2):
        lines = _wrap(probe, title, _font("display", candidate), c_text_w)
        if len(lines) * candidate * 1.24 + c_essence_h <= c_zone_h:
            c_title_size, c_title_lines = candidate, lines
            break
    compact = bool(c_title_lines)
    if compact:
        title_size, title_lines = c_title_size, c_title_lines
        title_lh = title_size * 1.24
        essence_size, essence_lines = c_essence_size, c_essence_lines
        essence_lh, essence_h = c_essence_lh, c_essence_h
        height = CARD_HEIGHTS[0]
    else:
        height = next((h for h in CARD_HEIGHTS[1:] if h >= needed), CARD_HEIGHTS[-1])

    # Per-tier geometry: the compact tier tightens every spacing
    # (Karn's approved sample); taller tiers keep the original layout.
    inset = 36 if compact else 44
    badge_x, badge_y, logo_h = (72, 56, 54) if compact else (84, 72, 60)
    badge_pad = 12 if compact else 14
    mx = 80 if compact else 92

    img = Image.new("RGB", (CARD_WIDTH, height), PAPER)
    draw = ImageDraw.Draw(img)

    # Dashed label border.
    _dashed_rectangle(draw, (inset, inset, CARD_WIDTH - inset, height - inset), INK)

    # Header: the TH logo in a white badge; the channel name centered on
    # the badge's midline by its measured pixel box.
    logo = _logo_mark(logo_h)
    badge_w = (logo.width if logo is not None else 97) + badge_pad * 2
    badge_h = logo_h + badge_pad * 2
    badge = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    bd.rounded_rectangle((1, 1, badge_w - 2, badge_h - 2), radius=18 if compact else 20, fill=(255, 255, 255), outline=INK, width=3)
    if logo is not None:
        badge.alpha_composite(logo.convert("RGBA"), (badge_pad, badge_pad))
    else:
        tf = _font("archivo_black", 30 if compact else 34)
        tb = bd.textbbox((0, 0), "TH", font=tf)
        bd.text(((badge_w - (tb[2] - tb[0])) / 2 - tb[0], (badge_h - (tb[3] - tb[1])) / 2 - tb[1]), "TH", font=tf, fill=RED)
    base = img.convert("RGBA")
    base.alpha_composite(badge, (badge_x, badge_y))
    name = _tracked_strip("TODAY IN HISTORY", _font("archivo_black", 42 if compact else 46), INK, 9)
    base.alpha_composite(name, (badge_x + badge_w + (38 if compact else 42), badge_y + badge_h // 2 - name.height // 2))
    img = base.convert("RGB")
    draw = ImageDraw.Draw(img)

    # Header rule, then the kicker row: the date in red at the left, the
    # category quiet at the right.
    draw.line((mx, 168 if compact else 200, CARD_WIDTH - mx, 168 if compact else 200), fill=INK, width=3)
    _draw_tracked(draw, mx, 196 if compact else 238, date_text, _font("archivo", 30 if compact else 32), RED, 5)
    cat_size = 24
    while cat_size > 18 and _tracked_width(probe, category, _font("archivo", cat_size), 4) > 620:
        cat_size -= 2
    cat = _tracked_strip(category, _font("archivo", cat_size), MUTED, 4)
    base = img.convert("RGBA")
    base.alpha_composite(cat, (CARD_WIDTH - mx - cat.width, 200 if compact else 242))
    img = base.convert("RGB")
    draw = ImageDraw.Draw(img)

    # Headline, then the essence line under it. The compact tier centers
    # the whole stack in its middle zone; taller tiers start at the top.
    if compact:
        stack_h = len(title_lines) * title_lh + essence_h
        y = COMPACT_TEXT_TOP + (c_zone_h - stack_h) / 2
    else:
        y = 292
    title_font = _font("display", title_size)
    for line in title_lines:
        draw.text((mx, y), line, font=title_font, fill=TEXT_INK)
        y += title_lh
    if essence_lines:
        y += 36
        essence_font = _font("display", essence_size)
        for line in essence_lines:
            draw.text((mx, y), line, font=essence_font, fill=TEXT_INK)
            y += essence_lh

    # Footer: ink rule, source left and handle right on one baseline.
    rule_y = height - 144 if compact else height - 214
    draw.line((mx, rule_y, CARD_WIDTH - mx, rule_y), fill=INK, width=3)
    baseline = rule_y + (62 if compact else 74)
    hf = _font("archivo_black", 34 if compact else 38)
    draw.text((CARD_WIDTH - mx - draw.textlength(HANDLE, font=hf), baseline - hf.getmetrics()[0]), HANDLE, font=hf, fill=INK)
    sf = _font("archivo_medium", 28 if compact else 30)
    draw.text((mx, baseline - sf.getmetrics()[0]), f"Source: {domain}", font=sf, fill=MUTED)

    output.parent.mkdir(parents=True, exist_ok=True)
    _save_jpeg(img, output, 92)
    return output
