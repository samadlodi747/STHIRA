import json
from functools import lru_cache
from pathlib import Path
import re


PROFILE_DATA_PATH = Path(__file__).with_name("profiles.json")


@lru_cache(maxsize=1)
def load_profiles() -> list[dict]:
    with PROFILE_DATA_PATH.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def find_profile(name: str) -> dict | None:
    clean_name = str(name or "").strip()
    for profile in load_profiles():
        if profile.get("n") == clean_name:
            return profile
    return None


def group_family(name: str) -> str:
    value = str(name or "").strip().upper()
    if value.startswith("HEAA"):
        return "HEAA"
    if value.startswith("HEA"):
        return "HEA"
    if value.startswith("HEB"):
        return "HEB"
    if value.startswith("HEM"):
        return "HEM"
    if value.startswith("HLAA"):
        return "HLAA"
    if value.startswith("HL "):
        return "HL"
    if value.startswith("IPE"):
        return "IPE"
    if value.startswith("IPN"):
        return "IPN"
    if value.startswith("UPN"):
        return "UPN"
    if re.match(r"^B\d", value):
        return "CHS"
    if re.match(r"^K\d", value):
        return "BOX"
    if re.match(r"^U\d", value):
        return "U"
    match = re.match(r"^[A-Z]+", value)
    return match.group(0) if match else "OTHER"
