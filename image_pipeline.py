from __future__ import annotations

import logging
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from config import GENERATED_DIR
from dataset import Event
from image_resolver import ResolvedImage, resolve_event_image

logger = logging.getLogger("today-in-history.images")

MAX_BYTES = 10 * 1024 * 1024
MAX_DIM_SUM = 10_000
MAX_DIM = 10_000


def _output_path(event: Event) -> Path:
    return GENERATED_DIR / f"{event.event_id}.jpg"


def _save_jpeg(image: Image.Image, output: Path, quality: int) -> None:
    image.save(output, "JPEG", quality=quality, optimize=True, progressive=True)


def _prepare_without_crop(source: Path, output: Path) -> Path:
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        width, height = image.size

        # Preserve the original aspect ratio. Resize only when Telegram's photo limits require it.
        scale = min(1.0, MAX_DIM_SUM / max(1, width + height), MAX_DIM / max(1, width), MAX_DIM / max(1, height))
        if scale < 1.0:
            image = image.resize((max(1, int(width * scale)), max(1, int(height * scale))), Image.Resampling.LANCZOS)

        # First try a high-quality JPEG at the preserved ratio.
        quality = 95
        _save_jpeg(image, output, quality)

        # File-size reduction never crops or changes the ratio.
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
    """Prepare a real historical image without cropping or branded overlays.

    Image decode/processing failures are treated as a normal "no usable image"
    condition so a single bad source can never terminate an entire batch.
    """
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    result = resolved or resolve_event_image(event)
    if not result or not result.path.exists():
        return None

    output = _output_path(event)
    try:
        prepared = _prepare_without_crop(result.path, output)
        # Verify the final JPEG can actually be decoded before it reaches Telegram.
        with Image.open(prepared) as check:
            check.verify()
        return prepared
    except (OSError, ValueError, UnidentifiedImageError) as exc:
        output.unlink(missing_ok=True)
        logger.warning("Image preparation failed for %s: %s", event.event_id, exc)
        return None
