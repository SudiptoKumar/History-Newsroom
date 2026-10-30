from pathlib import Path

from PIL import Image

from image_pipeline import _prepare_image


def test_image_ratio_preserved_without_crop(tmp_path: Path):
    source = tmp_path / "source.png"
    output = tmp_path / "output.jpg"
    with Image.new("RGB", (1200, 700), "white") as image:
        image.save(source)
    _prepare_image(source, output)
    with Image.open(output) as result:
        assert abs((result.width / result.height) - (1200 / 700)) < 0.01


def test_invalid_source_image_returns_none(tmp_path: Path):
    from dataset import events_for_date, load_all
    from image_pipeline import prepare_event_image
    from image_resolver import ResolvedImage

    event = events_for_date(load_all(), 9, 21)[0]
    source = tmp_path / "broken.source"
    source.write_bytes(b"not a real image")
    result = ResolvedImage(
        path=source,
        source_url="https://example.test/broken.jpg",
        source_page="https://example.test/page",
        source_name="Test",
    )

    assert prepare_event_image(event, result) is None


def test_generated_card_is_content_fit(tmp_path: Path):
    from content_ai import _fallback
    from dataset import events_for_date, load_all
    from image_pipeline import generate_event_card

    event = events_for_date(load_all(), 9, 21)[0]
    output = tmp_path / "card.jpg"
    generate_event_card(event, _fallback(event), output)
    with Image.open(output) as result:
        assert result.width == 1200
        assert result.height in (1200, 1500, 1800)
