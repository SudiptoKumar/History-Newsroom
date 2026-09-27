from io import BytesIO
from pathlib import Path

import image_resolver
from PIL import Image



def _jpeg_bytes(size=(900, 600)):
    buffer = BytesIO()
    with Image.new("RGB", size, "white") as image:
        image.save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeResponse:
    def __init__(self, *, payload=None, content=None, content_type="image/jpeg", url="https://upload.wikimedia.org/test.jpg"):
        self._payload = payload or {}
        self.content = _jpeg_bytes() if content is None else content
        self.headers = {"content-type": content_type}
        self.url = url
        self.text = ""

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload



def _event():
    from dataset import Event

    return Event(
        day=24,
        era="",
        year="1645",
        month="September",
        event_id="TEST-1",
        event_type="Battle",
        description="Battle of Rowton Heath.",
        event_title="Battle of Rowton Heath",
        date_display="September 24, 1645",
        source_1_url="https://en.wikipedia.org/wiki/September_24",
        source_2_url="",
        calendar_date="",
        city_location="Rowton Heath",
        original_date="",
        source_1_name="Wikipedia — September 24",
        source_2_name="",
        date_certainty="Exact",
        event_category="Warfare",
        modern_country="United Kingdom",
        calendar_system="Gregorian",
        coverage_status="",
        people_involved="Charles I",
        historical_entity="Kingdom of England",
        significance_scope="International",
        source_reliability="",
        target_event_count="",
        verification_status="Verified",
        verified_event_count="",
        significance_score=90.0,
        notes="",
        region="Europe",
    )


def test_download_rejects_html_even_when_content_type_claims_image(monkeypatch, tmp_path: Path):
    def fake_get(url, **kwargs):
        return FakeResponse(content=b"<html>blocked page</html>" + b"x" * 5000, content_type="image/jpeg")

    monkeypatch.setattr(image_resolver.requests, "get", fake_get)

    destination = tmp_path / "source"
    assert image_resolver._download_image("https://upload.wikimedia.org/bad.jpg", destination) is False
    assert not destination.exists()


def test_commons_accepts_open_image_without_license_metadata(monkeypatch, tmp_path: Path):
    event = _event()
    payload = {
        "query": {
            "pages": {
                "1": {
                    "title": "File:Battle of Rowton Heath.jpg",
                    "imageinfo": [{
                        "mime": "image/jpeg",
                        "width": 1200,
                        "height": 800,
                        "thumburl": "https://upload.wikimedia.org/test.jpg",
                        "extmetadata": {
                            "Artist": {"value": "Example"},
                            "ImageDescription": {"value": "Battle of Rowton Heath in England"},
                        },
                    }],
                }
            }
        }
    }

    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        if "w/api.php" in url:
            return FakeResponse(payload=payload)
        return FakeResponse()

    monkeypatch.setattr(image_resolver.requests, "get", fake_get)

    destination = tmp_path / "source"
    result = image_resolver._commons_search(event, "Battle of Rowton Heath", destination)

    assert result is not None
    assert result.source_name.startswith("Wikimedia Commons")
    assert destination.exists()
    assert len(calls) == 2


def test_commons_skips_invalid_top_candidate_and_uses_next(monkeypatch, tmp_path: Path):
    event = _event()
    payload = {
        "query": {
            "pages": {
                "1": {
                    "title": "File:Battle of Rowton Heath best.jpg",
                    "imageinfo": [{
                        "mime": "image/jpeg", "width": 1200, "height": 800,
                        "thumburl": "https://upload.wikimedia.org/bad.jpg",
                        "extmetadata": {"ImageDescription": {"value": "Battle of Rowton Heath, 1645"}},
                    }],
                },
                "2": {
                    "title": "File:Battle of Rowton Heath alternate.jpg",
                    "imageinfo": [{
                        "mime": "image/jpeg", "width": 1000, "height": 700,
                        "thumburl": "https://upload.wikimedia.org/good.jpg",
                        "extmetadata": {"ImageDescription": {"value": "A battle scene in England"}},
                    }],
                },
            }
        }
    }

    image_calls = []

    def fake_get(url, **kwargs):
        if "w/api.php" in url:
            return FakeResponse(payload=payload)
        image_calls.append(url)
        if "bad.jpg" in url:
            return FakeResponse(content=b"<html>not an image</html>" + b"x" * 5000)
        return FakeResponse(content=_jpeg_bytes())

    monkeypatch.setattr(image_resolver.requests, "get", fake_get)

    destination = tmp_path / "source"
    result = image_resolver._commons_search(event, "Battle of Rowton Heath", destination)

    assert result is not None
    assert result.source_url.endswith("good.jpg")
    assert image_calls == ["https://upload.wikimedia.org/bad.jpg", "https://upload.wikimedia.org/good.jpg"]
    with Image.open(destination) as image:
        image.verify()


def test_wikipedia_search_is_used_as_fallback(monkeypatch, tmp_path: Path):
    event = _event()
    search_payload = {
        "query": {
            "pages": {
                "1": {
                    "title": "Battle of Rowton Heath",
                    "fullurl": "https://en.wikipedia.org/wiki/Battle_of_Rowton_Heath",
                    "thumbnail": {"source": "https://upload.wikimedia.org/test.jpg", "width": 900, "height": 600},
                }
            }
        }
    }

    def fake_get(url, **kwargs):
        params = kwargs.get("params") or {}
        if params.get("titles") == event.event_title:
            return FakeResponse(payload={"query": {"pages": {"-1": {"title": event.event_title}}}})
        return FakeResponse(payload=search_payload)

    monkeypatch.setattr(image_resolver.requests, "get", fake_get)

    destination = tmp_path / "source"
    result = image_resolver._wikipedia_page_image(event, destination)

    assert result is not None
    assert result.source_name == "Wikipedia"
    assert destination.exists()


def test_wikipedia_search_skips_invalid_candidate(monkeypatch, tmp_path: Path):
    event = _event()
    search_payload = {
        "query": {
            "pages": {
                "1": {
                    "title": "Battle of Rowton Heath",
                    "fullurl": "https://en.wikipedia.org/wiki/Battle_of_Rowton_Heath",
                    "thumbnail": {"source": "https://upload.wikimedia.org/bad.jpg", "width": 1200, "height": 800},
                },
                "2": {
                    "title": "Charles I of England",
                    "fullurl": "https://en.wikipedia.org/wiki/Charles_I_of_England",
                    "thumbnail": {"source": "https://upload.wikimedia.org/good.jpg", "width": 1200, "height": 800},
                },
            }
        }
    }

    def fake_get(url, **kwargs):
        params = kwargs.get("params") or {}
        if params.get("titles") == event.event_title:
            return FakeResponse(payload={"query": {"pages": {"-1": {"title": event.event_title}}}})
        if "w/api.php" in url:
            return FakeResponse(payload=search_payload)
        if "bad.jpg" in url:
            return FakeResponse(content=b"<html>not an image</html>" + b"x" * 5000)
        return FakeResponse(content=_jpeg_bytes())

    monkeypatch.setattr(image_resolver.requests, "get", fake_get)

    destination = tmp_path / "source"
    result = image_resolver._wikipedia_page_image(event, destination)

    assert result is not None
    assert result.source_url.endswith("good.jpg")
