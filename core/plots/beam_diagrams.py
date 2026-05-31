from __future__ import annotations

from dataclasses import asdict
import math
from typing import Iterable

from core.loads.statics import BeamEffects, PointLoad, deflection_at, moment_at, shear_at


def build_simply_supported_beam_plots(
    *,
    span_m: float,
    span_mm: float,
    w_uls_kN_m: float,
    w_sls_kN_m: float,
    point_loads_uls: list[PointLoad],
    point_loads_sls: list[PointLoad],
    reaction_left_uls_kN: float,
    E_N_mm2: float,
    I_mm4: float,
    governing_uls: str,
    governing_sls: str,
    effects_uls: BeamEffects,
    effects_sls: BeamEffects,
    samples: int = 301,
) -> dict:
    """Generate backend-owned diagram data for a simply supported beam.

    Input units:
    - span_m: m
    - span_mm: mm
    - line loads: kN/m, downward positive
    - point loads: kN at position a_m from the left support
    - E_N_mm2: N/mm2
    - I_mm4: mm4

    Output units:
    - x: m
    - shear: kN
    - moment: kNm
    - deflection: mm, downward positive

    The same governing load cases used for the design result are sampled here:
    ULS for shear/moment and SLS for deflection.
    """
    print(
        "[steel-beam-plots] generation inputs:",
        {
            "span_m": span_m,
            "w_uls_kN_m": w_uls_kN_m,
            "w_sls_kN_m": w_sls_kN_m,
            "point_loads_uls": [asdict(load) for load in point_loads_uls],
            "point_loads_sls": [asdict(load) for load in point_loads_sls],
            "reaction_left_uls_kN": reaction_left_uls_kN,
            "governing_uls": governing_uls,
            "governing_sls": governing_sls,
        },
    )

    if not (span_m > 0.0 and span_mm > 0.0):
        raise ValueError("Beam plot generation requires a positive span.")
    if not (E_N_mm2 > 0.0 and I_mm4 > 0.0):
        raise ValueError("Beam deflection plot generation requires positive E and I.")

    x_values = _diagram_positions(
        span_m=span_m,
        samples=samples,
        point_loads=[*point_loads_uls, *point_loads_sls],
        w_uls_kN_m=w_uls_kN_m,
        reaction_left_uls_kN=reaction_left_uls_kN,
        point_loads_uls=point_loads_uls,
    )

    shear_values = [
        _round(shear_at(x, w_uls_kN_m, point_loads_uls, reaction_left_uls_kN), 6)
        for x in x_values
    ]
    _apply_support_shear_jumps(x_values, shear_values, span_m)
    moment_values = [
        _round(moment_at(x, w_uls_kN_m, point_loads_uls, reaction_left_uls_kN), 6)
        for x in x_values
    ]
    deflection_values = [
        _round(deflection_at(x * 1000.0, span_mm, w_sls_kN_m, point_loads_sls, E_N_mm2, I_mm4), 6)
        for x in x_values
    ]

    plot_data = {
        "x": [_round(x, 6) for x in x_values],
        "shear": shear_values,
        "moment": moment_values,
        "deflection": deflection_values,
        "meta": {
            "x_unit": "m",
            "shear_unit": "kN",
            "moment_unit": "kNm",
            "deflection_unit": "mm",
            "samples": len(x_values),
            "uls_source": governing_uls,
            "sls_source": governing_sls,
            "line_loads": {
                "uls_kN_m": w_uls_kN_m,
                "sls_kN_m": w_sls_kN_m,
            },
            "point_loads": {
                "uls": [asdict(load) for load in point_loads_uls],
                "sls": [asdict(load) for load in point_loads_sls],
            },
        },
        "markers": {
            "max_shear": _marker_from_effect("shear", x_values, shear_values, effects_uls.Vmax_kN, "kN"),
            "max_moment": _marker_from_effect("moment", x_values, moment_values, effects_uls.Mmax_kNm, "kNm"),
            "max_deflection": _marker_from_effect(
                "deflection",
                x_values,
                deflection_values,
                effects_sls.dmax_mm,
                "mm",
            ),
        },
    }

    print(
        "[steel-beam-plots] generated arrays:",
        {
            "points": len(x_values),
            "x_first_last": [plot_data["x"][0], plot_data["x"][-1]],
            "shear_min_max": _min_max(shear_values),
            "moment_min_max": _min_max(moment_values),
            "deflection_min_max": _min_max(deflection_values),
            "markers": plot_data["markers"],
        },
    )
    return plot_data


def _diagram_positions(
    *,
    span_m: float,
    samples: int,
    point_loads: Iterable[PointLoad],
    w_uls_kN_m: float,
    reaction_left_uls_kN: float,
    point_loads_uls: list[PointLoad],
) -> list[float]:
    sample_count = max(41, min(int(samples or 301), 801))
    eps = max(span_m / 100000.0, 1e-6)
    positions = {span_m * index / (sample_count - 1) for index in range(sample_count)}
    positions.add(0.0)
    positions.add(span_m)

    for load in point_loads:
        if 0.0 <= load.a_m <= span_m:
            positions.add(load.a_m)
            positions.add(_clamp(load.a_m - eps, 0.0, span_m))
            positions.add(_clamp(load.a_m + eps, 0.0, span_m))

    for root in _moment_peak_positions(span_m, w_uls_kN_m, point_loads_uls, reaction_left_uls_kN):
        positions.add(root)

    ordered = sorted(positions)

    # Duplicated end stations render the support reaction jumps on the SFD.
    if ordered and ordered[0] == 0.0:
        ordered.insert(0, 0.0)
    if ordered and ordered[-1] == span_m:
        ordered.append(span_m)
    return ordered


def _apply_support_shear_jumps(x_values: list[float], shear_values: list[float | None], span_m: float) -> None:
    # The SFD starts and ends at zero outside the supports; duplicate stations draw the vertical reaction jumps.
    if len(x_values) >= 2 and abs(x_values[0]) < 1e-9 and abs(x_values[1]) < 1e-9:
        shear_values[0] = 0.0
    if len(x_values) >= 2 and abs(x_values[-1] - span_m) < 1e-9 and abs(x_values[-2] - span_m) < 1e-9:
        shear_values[-1] = 0.0


def _moment_peak_positions(
    span_m: float,
    w_kN_m: float,
    point_loads: list[PointLoad],
    reaction_left_kN: float,
) -> list[float]:
    if abs(w_kN_m) < 1e-12:
        return []

    boundaries = sorted({0.0, span_m, *[load.a_m for load in point_loads if 0.0 <= load.a_m <= span_m]})
    roots: list[float] = []
    for start, end in zip(boundaries, boundaries[1:]):
        if end < start:
            continue
        loads_before = sum(load.P_kN for load in point_loads if load.a_m <= start + 1e-9)
        root = (reaction_left_kN - loads_before) / w_kN_m
        if start - 1e-9 <= root <= end + 1e-9:
            roots.append(_clamp(root, 0.0, span_m))
    return roots


def _marker_from_effect(name: str, xs: list[float], ys: list[float], exact_abs_value: float, unit: str) -> dict:
    index = _index_of_abs_max(ys)
    y = ys[index] if index is not None else 0.0
    x = xs[index] if index is not None else 0.0
    return {
        "series": name,
        "x_m": _round(x, 6),
        "value": _round(y, 6),
        "abs_value": _round(abs(float(exact_abs_value or 0.0)), 6),
        "unit": unit,
        "index": index,
    }


def _index_of_abs_max(values: list[float]) -> int | None:
    if not values:
        return None
    return max(range(len(values)), key=lambda index: abs(values[index]))


def _min_max(values: list[float]) -> dict:
    if not values:
        return {"min": None, "max": None}
    return {
        "min": _round(min(values), 6),
        "max": _round(max(values), 6),
    }


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _round(value: float, digits: int) -> float | None:
    value = float(value)
    if not math.isfinite(value):
        return None
    return round(value, digits)
