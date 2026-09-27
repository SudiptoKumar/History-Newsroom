from __future__ import annotations

import csv
from urllib.parse import urlparse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from config import DATA_DIR, MONTHS

COLUMN_ALIASES = {
    "day": ["Day"],
    "era": ["Era"],
    "year": ["Year"],
    "month": ["Month"],
    "event_id": ["Event ID"],
    "event_type": ["Event type"],
    "description": ["Description"],
    "event_title": ["Event title"],
    "date_display": ["Date display"],
    "source_1_url": ["Source 1 URL"],
    "source_2_url": ["Source 2 URL"],
    "calendar_date": ["Calendar date"],
    "city_location": ["City location"],
    "original_date": ["Original date"],
    "source_1_name": ["Source 1 name"],
    "source_2_name": ["Source 2 name"],
    "date_certainty": ["Date certainty"],
    "event_category": ["Event category"],
    "modern_country": ["Modern country"],
    "calendar_system": ["Calendar system"],
    "coverage_status": ["Coverage status"],
    "people_involved": ["People involved"],
    "historical_entity": ["Historical entity"],
    "significance_scope": ["Significance scope"],
    "source_reliability": ["Source reliability"],
    "target_event_count": ["Target event count"],
    "verification_status": ["Verification status"],
    "verified_event_count": ["Verified event count"],
    "significance_score": ["Historical significance score"],
    "notes": ["Notes"],
    "region": ["Region"],
}

@dataclass(frozen=True)
class Event:
    day: int
    era: str
    year: str
    month: str
    event_id: str
    event_type: str
    description: str
    event_title: str
    date_display: str
    source_1_url: str
    source_2_url: str
    calendar_date: str
    city_location: str
    original_date: str
    source_1_name: str
    source_2_name: str
    date_certainty: str
    event_category: str
    modern_country: str
    calendar_system: str
    coverage_status: str
    people_involved: str
    historical_entity: str
    significance_scope: str
    source_reliability: str
    target_event_count: str
    verification_status: str
    verified_event_count: str
    significance_score: float
    notes: str
    region: str

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(value: str | None) -> str:
    return (value or "").strip()


def _pick(row: dict[str, str], key: str) -> str:
    for source_col in COLUMN_ALIASES[key]:
        if source_col in row:
            return _clean(row.get(source_col))
    return ""


def _score(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _day(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        raise ValueError(f"Invalid Day value: {value!r}")


def load_month(path: Path) -> list[Event]:
    rows: list[Event] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"No CSV header found in {path}")
        for row in reader:
            rows.append(
                Event(
                    day=_day(_pick(row, "day")),
                    era=_pick(row, "era"), year=_pick(row, "year"),
                    month=_pick(row, "month") or path.stem,
                    event_id=_pick(row, "event_id"),
                    event_type=_pick(row, "event_type"), description=_pick(row, "description"),
                    event_title=_pick(row, "event_title"), date_display=_pick(row, "date_display"),
                    source_1_url=_pick(row, "source_1_url"), source_2_url=_pick(row, "source_2_url"),
                    calendar_date=_pick(row, "calendar_date"), city_location=_pick(row, "city_location"),
                    original_date=_pick(row, "original_date"), source_1_name=_pick(row, "source_1_name"),
                    source_2_name=_pick(row, "source_2_name"), date_certainty=_pick(row, "date_certainty"),
                    event_category=_pick(row, "event_category"), modern_country=_pick(row, "modern_country"),
                    calendar_system=_pick(row, "calendar_system"), coverage_status=_pick(row, "coverage_status"),
                    people_involved=_pick(row, "people_involved"), historical_entity=_pick(row, "historical_entity"),
                    significance_scope=_pick(row, "significance_scope"), source_reliability=_pick(row, "source_reliability"),
                    target_event_count=_pick(row, "target_event_count"), verification_status=_pick(row, "verification_status"),
                    verified_event_count=_pick(row, "verified_event_count"),
                    significance_score=_score(_pick(row, "significance_score")),
                    notes=_pick(row, "notes"), region=_pick(row, "region"),
                )
            )
    return rows


def load_all() -> list[Event]:
    events: list[Event] = []
    for month_num in range(1, 13):
        path = DATA_DIR / f"{MONTHS[month_num]}.csv"
        if path.exists():
            events.extend(load_month(path))
    return events


def events_for_date(events: Iterable[Event], month: int, day: int) -> list[Event]:
    month_name = MONTHS[month]
    filtered = [e for e in events if e.month.strip().lower() == month_name.lower() and e.day == day]
    # Dataset significance scores are the first-order ranking signal. Event ID gives stable ordering.
    return sorted(filtered, key=lambda e: (-e.significance_score, e.event_id, e.event_title.lower()))


def validate_dataset(events: list[Event]) -> list[str]:
    errors: list[str] = []
    ids: set[str] = set()
    for e in events:
        if not e.event_id:
            errors.append("Event with missing Event ID")
        elif e.event_id in ids:
            errors.append(f"Duplicate Event ID: {e.event_id}")
        ids.add(e.event_id)
        if not e.event_title:
            errors.append(f"{e.event_id}: missing title")
        if not e.description:
            errors.append(f"{e.event_id}: missing description")
        if not e.source_1_url:
            errors.append(f"{e.event_id}: missing Source 1 URL")
        else:
            parsed = urlparse(e.source_1_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(f"{e.event_id}: invalid Source 1 URL: {e.source_1_url}")
        if not e.source_1_name:
            errors.append(f"{e.event_id}: missing Source 1 name")
        if not 1 <= e.day <= 31:
            errors.append(f"{e.event_id}: invalid day {e.day}")
    return errors
