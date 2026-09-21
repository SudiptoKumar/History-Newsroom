from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
GENERATED_DIR = BASE_DIR / "generated"
STATE_DIR = BASE_DIR / "state"
STATE_FILE = STATE_DIR / "posted_state.json"

def normalize_telegram_channel(value: str) -> str:
    """Accept @username, t.me/username, or https://t.me/username forms."""
    value = (value or "").strip()
    if not value:
        return ""
    for prefix in ("https://t.me/", "http://t.me/", "https://telegram.me/", "http://telegram.me/", "t.me/", "telegram.me/"):
        if value.lower().startswith(prefix):
            value = value[len(prefix):].split("/", 1)[0].strip()
            break
    if value and not value.startswith("@") and not value.startswith("-") and not value.isdigit():
        value = "@" + value
    return value

MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December",
}

@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_channel: str = normalize_telegram_channel(os.getenv("TELEGRAM_CHANNEL", "@HistoryNewsroom"))
    timezone: str = os.getenv("TIMEZONE", "Asia/Dhaka")
    max_events_per_day: int = int(os.getenv("MAX_EVENTS_PER_DAY", "20"))
    batch_size: int = int(os.getenv("BATCH_SIZE", "10"))
    batch_index: int = int(os.getenv("BATCH_INDEX", "1"))
    use_cerebras: bool = os.getenv("USE_CEREBRAS", "true").lower() == "true"
    use_exa_context: bool = os.getenv("USE_EXA_CONTEXT", "true").lower() == "true"
    cerebras_model: str = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
    cerebras_api_key: str = os.getenv("CEREBRAS_API_KEY", "")
    cerebras_min_interval_seconds: float = float(os.getenv("CEREBRAS_MIN_INTERVAL_SECONDS", "6"))
    cerebras_retry_attempts: int = int(os.getenv("CEREBRAS_RETRY_ATTEMPTS", "4"))
    cerebras_story_min_words: int = int(os.getenv("CEREBRAS_STORY_MIN_WORDS", "45"))
    cerebras_story_max_words: int = int(os.getenv("CEREBRAS_STORY_MAX_WORDS", "70"))
    bot_name: str = os.getenv("BOT_NAME", "Today in History")
    exa_api_key: str = os.getenv("EXA_API_KEY", "")

SETTINGS = Settings()

# Common historical-country aliases for flag rendering.
COUNTRY_CODE_ALIASES = {
    "United States": "US", "United Kingdom": "GB", "Soviet Union": "RU",
    "Russia": "RU", "Russian Empire": "RU", "German Empire": "DE",
    "West Germany": "DE", "East Germany": "DE", "Czechoslovakia": "CZ",
    "Yugoslavia": "RS", "Ottoman Empire": "TR", "Austro-Hungarian Empire": "AT",
    "Persia": "IR", "Iran": "IR", "Burma": "MM", "Myanmar": "MM",
    "Siam": "TH", "Thailand": "TH", "Korea": "KR", "South Korea": "KR",
    "North Korea": "KP", "China": "CN", "Japan": "JP", "India": "IN",
    "Pakistan": "PK", "Bangladesh": "BD", "Nepal": "NP", "Bhutan": "BT",
    "Sri Lanka": "LK", "Afghanistan": "AF", "Israel": "IL", "Palestine": "PS",
    "Egypt": "EG", "South Africa": "ZA", "Nigeria": "NG", "Ghana": "GH",
    "Kenya": "KE", "Ethiopia": "ET", "France": "FR", "Spain": "ES",
    "Portugal": "PT", "Italy": "IT", "Netherlands": "NL", "Belgium": "BE",
    "Switzerland": "CH", "Austria": "AT", "Greece": "GR", "Turkey": "TR",
    "Türkiye": "TR", "Sweden": "SE", "Norway": "NO", "Denmark": "DK",
    "Finland": "FI", "Poland": "PL", "Ukraine": "UA", "Ireland": "IE",
    "Canada": "CA", "Mexico": "MX", "Cuba": "CU", "Brazil": "BR",
    "Argentina": "AR", "Chile": "CL", "Peru": "PE", "Colombia": "CO",
    "Australia": "AU", "New Zealand": "NZ", "Philippines": "PH",
    "Indonesia": "ID", "Malaysia": "MY", "Singapore": "SG", "Vietnam": "VN",
}
