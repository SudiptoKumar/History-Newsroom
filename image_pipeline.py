from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps

from config import GENERATED_DIR
from dataset import Event
from image_resolver import ResolvedImage, resolve_event_image

WIDTH, HEIGHT = 1600, 900


def _output_path(event: Event) -> Path:
    return GENERATED_DIR / f"{event.event_id}.jpg"


def _normalize_source_image(source: Path, output: Path) -> Path:
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        image = ImageOps.fit(image, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        image.save(output, "JPEG", quality=94, optimize=True)
    return output


def prepare_event_image(event: Event, resolved: ResolvedImage | None = None) -> Path | None:
    """Resolve and normalize a real historical source image. No text or branding is composited."""
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    result = resolved or resolve_event_image(event)
    if not result:
        return None
    return _normalize_source_image(result.path, _output_path(event))
