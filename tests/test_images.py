from pathlib import Path

from PIL import Image

from image_pipeline import _prepare_without_crop


def test_image_ratio_preserved_without_crop(tmp_path: Path):
    source = tmp_path / "source.png"
    output = tmp_path / "output.jpg"
    with Image.new("RGB", (1200, 700), "white") as image:
        image.save(source)
    _prepare_without_crop(source, output)
    with Image.open(output) as result:
        assert abs((result.width / result.height) - (1200 / 700)) < 0.01
