"""Automatic floor and wall load take-down for beam line loads.

Input units:
- slab surface loads: kN/m2
- slab supported span: m
- wall thickness: cm
- wall density: kN/m3
- wall height: m

Internal/output units:
- line loads: kN/m
"""

from dataclasses import dataclass

from models.steel import AutomaticLoadTakedown


POTTEN_TYPE_DEAD_LOADS_KN_M2 = {
    "12+4": 2.27,
    "D12+4": 2.475,
    "16+4": 2.67,
    "D16+4": 2.945,
    "20+4": 2.955,
    "D20+4": 3.325,
    "25+4": 3.89,
    "D25+4": 4.295,
}

WELFSELS_TYPE_DEAD_LOADS_KN_M2 = {
    "FS130-600": 1.92,
    "FS150-600": 2.38,
    "FS200-600": 2.92,
    "FS150-1200": 2.60,
    "FS180-1200": 2.76,
    "FS200-1200": 2.71,
    "FS265-1200": 3.35,
    "FS320-1200": 3.78,
    "FS400-1200": 4.32,
    "FS500-1200": 5.50,
    "FL200-1200": 3.59,
    "FS200-1200ISO": 2.71,
    "FS265-1200ISO": 3.35,
    "FD200-1200-6C": 3.35,
    "FD200-1200-8C": 3.20,
    "FD265-1200-8C": 3.90,
    "FD320-1200-4C": 4.29,
    "FD400-1200-4C": 4.85,
}


@dataclass(frozen=True)
class LoadTakedownResult:
    enabled: bool
    floor_dead_kN_m: float
    floor_live_kN_m: float
    wall_kN_m: float
    dead_kN_m: float
    live_kN_m: float
    warnings: list[str]


def calculate_floor_load_takedown(automatic: AutomaticLoadTakedown) -> LoadTakedownResult:
    warnings: list[str] = []
    floor_dead = 0.0
    floor_live = 0.0

    for row in automatic.floor_rows:
        tributary_width_m = row.span_m / 2.0
        if tributary_width_m <= 0.0:
            continue

        # Beam line load from slab area load: q_line = q_area * tributary_width.
        dead_surface = _floor_dead_load_kN_m2(row.slab_type, row.subtype, row.dead_kN_m2, warnings)
        floor_dead += (dead_surface + row.additional_dead_kN_m2) * tributary_width_m
        floor_live += _floor_live_load_kN_m2(row.accessible) * tributary_width_m

    wall = 0.0
    if automatic.include_wall:
        for row in automatic.wall_rows:
            if not (row.thickness_cm > 0.0 and row.density_kN_m3 > 0.0 and row.height_m > 0.0):
                continue
            # Wall line load: density * thickness * height * effective percentage.
            wall += (
                row.density_kN_m3
                * (row.thickness_cm / 100.0)
                * row.height_m
                * (row.percent / 100.0)
            )

    if not automatic.enabled:
        return LoadTakedownResult(False, floor_dead, floor_live, wall, 0.0, 0.0, warnings)

    return LoadTakedownResult(
        enabled=True,
        floor_dead_kN_m=floor_dead,
        floor_live_kN_m=floor_live,
        wall_kN_m=wall if automatic.include_wall else 0.0,
        dead_kN_m=floor_dead + (wall if automatic.include_wall else 0.0),
        live_kN_m=floor_live,
        warnings=warnings,
    )


def _floor_dead_load_kN_m2(slab_type: str, subtype: str, user_dead_kN_m2: float, warnings: list[str]) -> float:
    if slab_type == "wood":
        return 1.0
    if slab_type == "potten":
        if subtype not in POTTEN_TYPE_DEAD_LOADS_KN_M2:
            warnings.append(f"Unknown Potten en Balken subtype '{subtype}', using 12+4.")
        return POTTEN_TYPE_DEAD_LOADS_KN_M2.get(subtype, POTTEN_TYPE_DEAD_LOADS_KN_M2["12+4"])
    if slab_type == "welfsels":
        if subtype not in WELFSELS_TYPE_DEAD_LOADS_KN_M2:
            warnings.append(f"Unknown Welfsels subtype '{subtype}', using FS130-600.")
        return WELFSELS_TYPE_DEAD_LOADS_KN_M2.get(subtype, WELFSELS_TYPE_DEAD_LOADS_KN_M2["FS130-600"])
    return user_dead_kN_m2


def _floor_live_load_kN_m2(accessible: str) -> float:
    return 2.0 if accessible == "accessible" else 1.0
