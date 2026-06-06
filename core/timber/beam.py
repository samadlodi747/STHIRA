"""Timber beam design (EN 1995-1-1 / EC5).

Verifies bending, shear and deflection for rectangular timber sections using the
central material database (materials.json) and the extensible section library
(sections.json). No steel logic is touched; load INPUTS reuse the steel beam model.
"""
from __future__ import annotations

import math

from core.timber.sections import find_material, find_section, load_sections
from models.steel import SteelBeamLoads
from models.timber import TimberBeamRequest
from utils.serialization import clean_for_json

# Partial factors for actions (EN 1990). Simple, standard ULS combination
# 1.35*G + 1.50*Q is used; direct UDL is treated as a variable action (conservative).
GAMMA_G = 1.35
GAMMA_Q = 1.50


def _gravity_self_weight_kN_m(density_kg_m3: float, area_mm2: float) -> float:
    area_m2 = area_mm2 / 1_000_000.0
    return density_kg_m3 * area_m2 * 9.81 / 1000.0


def _resolve_loads(loads: SteelBeamLoads, self_weight_kN_m: float) -> dict:
    """Split the (reused) steel beam loads into permanent / variable characteristic
    actions for a simply supported timber beam."""
    g_udl = self_weight_kN_m
    q_udl = 0.0
    for row in loads.line_loads:
        if row.type == "G":
            g_udl += row.w_kN_m
        else:
            q_udl += row.w_kN_m
    if loads.mode == "direct":
        # A directly entered UDL has no dead/live split; treat as variable (conservative).
        q_udl += float(loads.direct_w_kN_m or 0.0)

    g_points: list[dict] = []
    q_points: list[dict] = []
    for load in loads.point_loads:
        if abs(load.P_kN) < 1e-12:
            continue
        (g_points if load.type == "G" else q_points).append({"P_kN": load.P_kN, "a_m": load.a_m})
    return {"g_udl": g_udl, "q_udl": q_udl, "g_points": g_points, "q_points": q_points}


def _udl_effects(w_kN_m: float, span_m: float) -> tuple[float, float]:
    return (w_kN_m * span_m * span_m / 8.0, w_kN_m * span_m / 2.0)


def _point_effects(P_kN: float, a_m: float, span_m: float) -> tuple[float, float]:
    a = max(0.0, min(a_m, span_m))
    b = span_m - a
    moment = P_kN * a * b / span_m if span_m > 0.0 else 0.0
    shear = P_kN * max(a, b) / span_m if span_m > 0.0 else 0.0
    return moment, shear


def _udl_deflection_mm(w_kN_m: float, span_m: float, E_N_mm2: float, I_mm4: float) -> float:
    if E_N_mm2 <= 0.0 or I_mm4 <= 0.0:
        return math.inf
    w_N_mm = w_kN_m  # kN/m is numerically N/mm
    L_mm = span_m * 1000.0
    return 5.0 * w_N_mm * L_mm**4 / (384.0 * E_N_mm2 * I_mm4)


def _point_deflection_mm(P_kN: float, a_m: float, span_m: float, E_N_mm2: float, I_mm4: float) -> float:
    if E_N_mm2 <= 0.0 or I_mm4 <= 0.0 or span_m <= 0.0:
        return math.inf
    clamped = max(0.0, min(a_m, span_m))
    a = clamped * 1000.0
    b = (span_m - clamped) * 1000.0
    L_mm = span_m * 1000.0
    P_N = P_kN * 1000.0
    # Deflection under the load point: P a^2 b^2 / (3 E I L).
    return P_N * a * a * b * b / (3.0 * E_N_mm2 * I_mm4 * L_mm)


def _evaluate_section(section: dict, material: dict, resolved: dict, span_m: float, kmod: float, defl_ratio: float, effects: dict | None = None) -> dict:
    A = float(section["area_mm2"])
    W = float(section["W_mm3"])
    I = float(section["Iy_mm4"])
    fm_k = float(material["fm_k"])
    fv_k = float(material["fv_k"])
    E_mean = float(material["E_mean"])
    gamma_M = float(material["gamma_M"])

    fm_d = kmod * fm_k / gamma_M
    fv_d = kmod * fv_k / gamma_M

    # ULS effects (1.35 G + 1.50 Q).
    m_uls, v_uls = 0.0, 0.0
    for w, factor in ((resolved["g_udl"], GAMMA_G), (resolved["q_udl"], GAMMA_Q)):
        m, v = _udl_effects(w * factor, span_m)
        m_uls += m
        v_uls += v
    for p in resolved["g_points"]:
        m, v = _point_effects(p["P_kN"] * GAMMA_G, p["a_m"], span_m)
        m_uls += m
        v_uls += v
    for p in resolved["q_points"]:
        m, v = _point_effects(p["P_kN"] * GAMMA_Q, p["a_m"], span_m)
        m_uls += m
        v_uls += v

    # SLS (characteristic) deflection.
    delta = _udl_deflection_mm(resolved["g_udl"] + resolved["q_udl"], span_m, E_mean, I)
    for p in resolved["g_points"] + resolved["q_points"]:
        delta += _point_deflection_mm(p["P_kN"], p["a_m"], span_m, E_mean, I)

    # Effects supplied by the original timber take-down override the load-derived effects;
    # EC5 resistances (below) are still used for the bending/shear/deflection checks.
    if effects is not None:
        m_uls = float(effects.get("MEd", m_uls))
        v_uls = float(effects.get("VEd", v_uls))
        delta = float(effects.get("delta", delta))

    sigma_m_d = (m_uls * 1_000_000.0) / W if W > 0.0 else math.inf
    tau_d = 1.5 * (v_uls * 1000.0) / A if A > 0.0 else math.inf
    delta_allow = span_m * 1000.0 / defl_ratio if defl_ratio > 0.0 else math.inf

    util_bending = sigma_m_d / fm_d if fm_d > 0.0 else math.inf
    util_shear = tau_d / fv_d if fv_d > 0.0 else math.inf
    util_defl = delta / delta_allow if delta_allow > 0.0 else math.inf
    control = max(util_bending, util_shear, util_defl)

    MRd = fm_d * W / 1_000_000.0
    VRd = fv_d * A / 1.5 / 1000.0

    fails = []
    if util_bending > 1.0:
        fails.append("Bending capacity exceeded")
    if util_shear > 1.0:
        fails.append("Shear capacity exceeded")
    if util_defl > 1.0:
        fails.append("Deflection limit exceeded")
    passing = math.isfinite(control) and control <= 1.0

    return {
        "section": section,
        "MEd_kNm": m_uls,
        "VEd_kN": v_uls,
        "MRd_kNm": MRd,
        "VRd_kN": VRd,
        "fm_d": fm_d,
        "fv_d": fv_d,
        "sigma_m_d": sigma_m_d,
        "tau_d": tau_d,
        "delta_max_mm": delta,
        "delta_allow_mm": delta_allow,
        "util_bending": util_bending,
        "util_shear": util_shear,
        "util_deflection": util_defl,
        "control": control,
        "pass": passing,
        "fails": fails,
    }


def _recommend_sections(material: dict, resolved: dict, span_m: float, kmod: float, defl_ratio: float, limit: int, effects: dict | None = None, ref_I: float | None = None) -> list[dict]:
    candidates = []
    for section in load_sections():
        section_effects = None
        if effects is not None:
            # Reuse the take-down moment/shear; deflection scales inversely with I.
            scaled_delta = effects.get("delta", 0.0)
            if ref_I and section.get("Iy_mm4"):
                scaled_delta = effects.get("delta", 0.0) * (ref_I / float(section["Iy_mm4"]))
            section_effects = {"MEd": effects.get("MEd", 0.0), "VEd": effects.get("VEd", 0.0), "delta": scaled_delta}
        result = _evaluate_section(section, material, resolved, span_m, kmod, defl_ratio, section_effects)
        if result["pass"]:
            candidates.append(result)
    # Smallest passing section first (by cross-sectional area) — same "lightest that passes"
    # philosophy as the steel beam recommendation engine.
    candidates.sort(key=lambda r: (r["section"]["area_mm2"], r["section"]["name"]))
    payload = []
    for r in candidates[: max(limit, 0)]:
        payload.append(
            {
                "section": r["section"]["name"],
                "width_mm": r["section"]["width_mm"],
                "depth_mm": r["section"]["depth_mm"],
                "area_mm2": r["section"]["area_mm2"],
                "utilization": r["control"],
                "util_bending": r["util_bending"],
                "util_shear": r["util_shear"],
                "util_deflection": r["util_deflection"],
            }
        )
    return payload


def calculate_timber_beam(request: TimberBeamRequest) -> dict:
    print("[timber-beam] request payload:", request.model_dump(mode="json"))
    material = find_material(request.material.grade)
    if material is None:
        raise ValueError(f"Unknown timber grade: {request.material.grade}")

    # Custom user-entered dimensions take precedence (original UI behaviour); the section
    # library is reserved for recommendations. Fall back to a named library section.
    width = request.geometry.width_mm
    height = request.geometry.height_mm
    if width and height and width > 0.0 and height > 0.0:
        section = {
            "name": f"{int(round(width))}x{int(round(height))}",
            "width_mm": float(width),
            "depth_mm": float(height),
            "area_mm2": float(width) * float(height),
            "Iy_mm4": float(width) * float(height) ** 3 / 12.0,
            "W_mm3": float(width) * float(height) ** 2 / 6.0,
        }
    else:
        section = find_section(request.section_name)
        if section is None:
            raise ValueError("Provide timber width and height, or a valid library section.")

    span_m = request.geometry.span_m
    defl_ratio = request.geometry.deflection_limit_ratio
    kmod = request.design.kmod
    self_weight = (
        _gravity_self_weight_kN_m(float(material["density"]), float(section["area_mm2"]))
        if request.loads.include_self_weight
        else 0.0
    )
    resolved = _resolve_loads(request.loads, self_weight)

    effects_override = None
    if request.effects is not None:
        effects_override = {
            "MEd": request.effects.MEd_kNm,
            "VEd": request.effects.VEd_kN,
            "delta": request.effects.delta_mm,
        }
    result = _evaluate_section(section, material, resolved, span_m, kmod, defl_ratio, effects_override)
    recommendations = _recommend_sections(
        material, resolved, span_m, kmod, defl_ratio, request.design.recommendation_limit,
        effects_override, ref_I=float(section["Iy_mm4"]),
    )

    warnings: list[str] = []
    if request.loads.include_self_weight:
        warnings.append(f"Self-weight included: {self_weight:.3f} kN/m ({material['grade']} {section['name']}).")
    if material["type"] == "solid" and span_m > 8.0:
        warnings.append("Span exceeds 8 m for solid timber; verify availability and deflection assumptions.")

    control = result["control"]
    status_kind = "ok"
    status_text = "OK"
    if result["fails"]:
        status_kind = "bad"
        status_text = result["fails"][0]
    elif math.isfinite(control) and control > 0.90:
        status_kind = "warn"
        status_text = "High utilization"

    detail = {
        "member_type": "Timber Beam",
        "material": {
            "grade": material["grade"],
            "type": material["type"],
            "fm_k": material["fm_k"],
            "fv_k": material["fv_k"],
            "E_mean": material["E_mean"],
            "density": material["density"],
            "gamma_M": material["gamma_M"],
            "kmod": kmod,
        },
        "section": {
            "name": section["name"],
            "width_mm": section["width_mm"],
            "depth_mm": section["depth_mm"],
            "area_mm2": section["area_mm2"],
            "Iy_mm4": section["Iy_mm4"],
            "W_mm3": section["W_mm3"],
        },
        "geometry": {"span_m": span_m, "deflection_limit_ratio": defl_ratio},
        "MEd_kNm": result["MEd_kNm"],
        "VEd_kN": result["VEd_kN"],
        "resistance": {
            "MRd_kNm": result["MRd_kNm"],
            "VRd_kN": result["VRd_kN"],
            "fm_d": result["fm_d"],
            "fv_d": result["fv_d"],
        },
        "utilization_detail": {
            "bending": result["util_bending"],
            "shear": result["util_shear"],
            "deflection": result["util_deflection"],
            "control": control,
        },
        "deflection": {
            "delta_max_mm": result["delta_max_mm"],
            "delta_allow_mm": result["delta_allow_mm"],
        },
        "utilization": control,
        "status": status_text,
        "status_kind": status_kind,
        "status_detail": {"kind": status_kind, "text": status_text, "failures": result["fails"]},
        "recommendations": recommendations,
        "eurocode": {
            "standard": "EN 1995-1-1",
            "bending_clause": "6.1.6",
            "shear_clause": "6.1.7",
            "deflection_clause": "7.2",
        },
        "warnings": warnings,
    }

    response = {"success": True, "results": detail, "warnings": warnings, "errors": []}
    print(
        "[timber-beam] result:",
        {
            "grade": material["grade"],
            "section": section["name"],
            "MEd_kNm": round(result["MEd_kNm"], 3),
            "VEd_kN": round(result["VEd_kN"], 3),
            "status": status_text,
            "recommended_top": [r["section"] for r in recommendations[:3]],
        },
    )
    return clean_for_json(response)
