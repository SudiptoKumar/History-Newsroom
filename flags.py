from __future__ import annotations

from config import COUNTRY_CODE_ALIASES


def iso_to_flag(code: str) -> str:
    code = code.upper().strip()
    if len(code) != 2 or not code.isalpha():
        return "🌍"
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code)


def country_flag(country: str) -> str:
    country = (country or "").strip()
    if not country:
        return "🌍"
    return iso_to_flag(COUNTRY_CODE_ALIASES.get(country, ""))
