from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PointLoad:
    P_kN: float
    a_m: float


@dataclass(frozen=True)
class BeamEffects:
    RA_kN: float
    RB_kN: float
    Vmax_kN: float
    Mmax_kNm: float
    dmax_mm: float


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def scale_point_loads(loads: list[dict], factors: dict[str, float]) -> list[PointLoad]:
    grouped: dict[float, float] = {}
    for load in loads:
        action = str(load.get("type", "live")).lower()
        factor = factors.get(action, factors.get(load.get("type", ""), 0.0))
        value = float(load.get("P_kN", 0.0) or 0.0) * factor
        if abs(value) < 1e-12:
            continue
        position = round(float(load.get("a_m", 0.0) or 0.0), 6)
        grouped[position] = grouped.get(position, 0.0) + value
    return [PointLoad(P_kN=P, a_m=a) for a, P in grouped.items()]


def reactions_simply_supported(span_m: float, w_kN_m: float, point_loads: list[PointLoad]) -> tuple[float, float]:
    left = w_kN_m * span_m / 2.0
    right = w_kN_m * span_m / 2.0
    for load in point_loads:
        left += load.P_kN * (span_m - load.a_m) / span_m
        right += load.P_kN * load.a_m / span_m
    return left, right


def shear_at(x_m: float, w_kN_m: float, point_loads: list[PointLoad], reaction_left_kN: float) -> float:
    shear = reaction_left_kN - w_kN_m * x_m
    for load in point_loads:
        if x_m >= load.a_m:
            shear -= load.P_kN
    return shear


def moment_at(x_m: float, w_kN_m: float, point_loads: list[PointLoad], reaction_left_kN: float) -> float:
    moment = reaction_left_kN * x_m - w_kN_m * x_m * x_m / 2.0
    for load in point_loads:
        if x_m >= load.a_m:
            moment -= load.P_kN * (x_m - load.a_m)
    return moment


def deflection_at(
    x_mm: float,
    span_mm: float,
    w_kN_m: float,
    point_loads: list[PointLoad],
    E_N_mm2: float,
    I_mm4: float,
) -> float:
    # 1 kN/m is numerically equal to 1 N/mm.
    uniform = (
        w_kN_m
        * x_mm
        * (span_mm**3 - 2.0 * span_mm * x_mm**2 + x_mm**3)
        / (24.0 * E_N_mm2 * I_mm4)
    )
    deflection = uniform
    for load in point_loads:
        P_N = load.P_kN * 1000.0
        a_mm = load.a_m * 1000.0
        b_mm = span_mm - a_mm
        bracket = max(0.0, x_mm - a_mm)
        term = (
            b_mm * x_mm * (span_mm**2 - b_mm**2 - x_mm**2)
            + span_mm * bracket**3
        )
        deflection += P_N * term / (6.0 * E_N_mm2 * I_mm4 * span_mm)
    return deflection


def max_effects(
    span_m: float,
    w_kN_m: float,
    point_loads: list[PointLoad],
    E_N_mm2: float | None = None,
    I_mm4: float | None = None,
    samples: int = 2001,
) -> BeamEffects:
    left, right = reactions_simply_supported(span_m, w_kN_m, point_loads)
    eps = max(1e-6 * span_m, 1e-6)
    shear_positions = [0.0, span_m]
    for load in point_loads:
        shear_positions.append(clamp(load.a_m - eps, 0.0, span_m))
        shear_positions.append(clamp(load.a_m + eps, 0.0, span_m))

    max_shear = max(abs(shear_at(x, w_kN_m, point_loads, left)) for x in shear_positions)
    max_moment = 0.0
    max_deflection = 0.0
    span_mm = span_m * 1000.0

    for index in range(samples):
        x_m = span_m * index / max(samples - 1, 1)
        max_moment = max(max_moment, abs(moment_at(x_m, w_kN_m, point_loads, left)))
        if E_N_mm2 and I_mm4:
            d_mm = deflection_at(x_m * 1000.0, span_mm, w_kN_m, point_loads, E_N_mm2, I_mm4)
            max_deflection = max(max_deflection, abs(d_mm))

    return BeamEffects(
        RA_kN=left,
        RB_kN=right,
        Vmax_kN=max_shear,
        Mmax_kNm=max_moment,
        dmax_mm=max_deflection if math.isfinite(max_deflection) else math.inf,
    )
