from pathlib import Path

import image_resolver


class FakeResponse:
    def __init__(self, *, payload=None, content=b"x" * 5000, content_type="image/jpeg"):
        self._payload = payload or {}
        self.content = content
        self.headers = {"content-type": content_type}
        self.url = "https://commons.wikimedia.org/wiki/File:Example.jpg"
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
