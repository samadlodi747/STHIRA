from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent
_MATERIALS_FILE = _DATA_DIR / "materials.json"
_SECTIONS_FILE = _DATA_DIR / "sections.json"


def _section_with_derived(section: dict) -> dict:
    """Return a section dict with area/Iy/W guaranteed. Only width and depth are
    mandatory in the JSON; derived properties are computed when missing so new
    sections can be added with just w x d and no code changes."""
    width = float(section.get("width_mm", 0.0) or 0.0)
    depth = float(section.get("depth_mm", 0.0) or 0.0)
    enriched = dict(section)
    enriched.setdefault("area_mm2", width * depth)
    enriched.setdefault("Iy_mm4", width * depth**3 / 12.0)
    enriched.setdefault("W_mm3", width * depth**2 / 6.0)
    return enriched


@lru_cache(maxsize=1)
def load_materials() -> list[dict]:
    data = json.loads(_MATERIALS_FILE.read_text(encoding="utf-8"))
    return [m for m in data.get("materials", []) if isinstance(m, dict) and m.get("grade")]


@lru_cache(maxsize=1)
def load_sections() -> list[dict]:
    data = json.loads(_SECTIONS_FILE.read_text(encoding="utf-8"))
    return [_section_with_derived(s) for s in data.get("sections", []) if isinstance(s, dict) and s.get("name")]


def material_grades() -> list[str]:
    return [m["grade"] for m in load_materials()]


def find_material(grade: str) -> dict | None:
    target = str(grade or "").strip().lower()
    for material in load_materials():
        if str(material.get("grade", "")).strip().lower() == target:
            return material
    return None


def find_section(name: str) -> dict | None:
    target = str(name or "").strip().lower()
    for section in load_sections():
        if str(section.get("name", "")).strip().lower() == target:
            return section
    return None
