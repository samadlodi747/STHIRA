from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Callable

from core.steel.sections import find_profile, group_family, load_profiles
from models.steel import SteelColumnLoadCase, SteelColumnRequest
from utils.serialization import clean_for_json


COMBOS_K = [
    {"id": 1, "kind": "ULS", "name": "UGT 1", "perm": 1.20, "snow": 1.50, "wind": 0.00, "variable": 0.75},
    {"id": 2, "kind": "ULS", "name": "UGT 2", "perm": 1.20, "snow": 0.00, "wind": 1.50, "variable": 0.75},
    {"id": 3, "kind": "ULS", "name": "UGT 3", "perm": 1.20, "snow": 0.00, "wind": 0.00, "variable": 1.50},
    {"id": 4, "kind": "ULS", "name": "UGT 4", "perm": 1.35, "snow": 0.00, "wind": 0.00, "variable": 0.00},
    {"id": 5, "kind": "SLS", "name": "GGT 5", "perm": 1.00, "snow": 1.00, "wind": 0.00, "variable": 0.50},
    {"id": 6, "kind": "SLS", "name": "GGT 6", "perm": 1.00, "snow": 0.00, "wind": 1.00, "variable": 0.50},
    {"id": 7, "kind": "SLS", "name": "GGT 7", "perm": 1.00, "snow": 0.00, "wind": 0.00, "variable": 1.00},
]

BUCKLING_CURVE_ALPHA = {
    "a": 0.21,
    "b": 0.34,
    "c": 0.49,
    "d": 0.76,
}

# Upper bound used only for *reporting* a governing utilization. Some non-physical
# interaction terms can diverge (inf / very large) for heavily overstressed members;
# capping them keeps the reported ratio numeric instead of collapsing to 0.000 / "-" / "inf".
UTILIZATION_REPORT_CAP = 999.0

# Engineering description of each governing column check, keyed by the internal check name.
# Tuple = (description, resistance_label, axis, failure_text).
CHECK_ENGINEERING = {
    "compression": (
        "Cross-section compression",
        "Nc,Rd",
        "section",
        "Compression resistance Nc,Rd exceeded",
    ),
    "shear_y": (
        "Shear resistance about y-axis",
        "Vc,Rd,y",
        "y",
        "Shear resistance about the y-axis exceeded",
    ),
    "shear_z": (
        "Shear resistance about z-axis",
        "Vc,Rd,z",
        "z",
        "Shear resistance about the z-axis exceeded",
    ),
    "N_V_My": (
        "Axial + bending interaction, y-axis",
        "My,V,Rd",
        "y",
        "Combined axial and bending resistance about the y-axis exceeded",
    ),
    "N_V_Mz": (
        "Axial + bending interaction, z-axis",
        "Mz,V,Rd",
        "z",
        "Combined axial and bending resistance about the z-axis exceeded",
    ),
    "N_V_My_Mz": (
        "Biaxial bending + axial interaction",
        "My/Mz interaction",
        "both",
        "Biaxial bending and axial interaction exceeded",
    ),
    "stability_y": (
        "Flexural buckling about y-axis",
        "Nb,Rd,y",
        "y",
        "Flexural buckling resistance about the y-axis (Nb,Rd,y) exceeded",
    ),
    "stability_z": (
        "Flexural buckling about z-axis",
        "Nb,Rd,z",
        "z",
        "Flexural buckling resistance about the z-axis (Nb,Rd,z) exceeded",
    ),
}

SECTION_CLASSIFICATION_ASSUMPTION = (
    "Explicit EN 1993-1-1 cross-section classification is not calculated in this module yet; "
    "plastic section properties from the profile table are used, so Class 1/2 resistance is assumed."
)


@dataclass(frozen=True)
class ColumnParams:
    length_m: float
    buckling_length_y_m: float
    buckling_length_z_m: float
    ltb_length_m: float
    deflection_limit_ratio: float
    fy_MPa: float
    E_N_mm2: float
    gamma_M0: float
    gamma_M1: float
    finish_type: int
    load_position: int
    include_self_weight: bool


@dataclass(frozen=True)
class ColumnLoad:
    N: float
    py: float
    pz: float
    Py: float
    ay: float
    Pz: float
    az: float


def calculate_steel_column(request: SteelColumnRequest) -> dict:
    print("[steel-column] request payload:", request.model_dump(mode="json"))
    profile = find_profile(request.profile_name)
    if profile is None:
        raise ValueError(f"Unknown steel profile: {request.profile_name}")

    params = _params_from_request(request)
    load_cases = _loads_from_request(request)
    result = _evaluate_profile(profile, params, load_cases, include_detail=True, recommendation_limit=request.design.recommendation_limit)
    if result is None:
        raise ValueError("Selected section has incomplete geometry or section properties for steel column design.")

    detail = result["detail"]
    recommendations, rejected_sections = _recommend_columns(request, params, load_cases)
    detail["recommendations"] = _recommendation_payload(recommendations[: request.design.recommendation_limit])
    detail["recommendation_debug"] = {
        "filtered_sections": [item.get("section") for item in detail["recommendations"]],
        "rejected_sections": rejected_sections[:50],
    }
    for warning in _validate_result_structure(detail):
        if warning not in detail["warnings"]:
            detail["warnings"].append(warning)

    response = {
        "success": True,
        "results": detail,
        "warnings": detail.get("warnings", []),
        "errors": [],
    }
    print(
        "[steel-column] governing checks:",
        {
            "governing": detail.get("governing_check"),
            "utilization": detail.get("utilization"),
            "status": detail.get("status"),
        },
    )
    # TODO(diagnostic): temporary governing-utilization audit log; remove once verified in the field.
    _summary = detail.get("stability_summary") or {}
    print(
        "[steel-column] governing utilization audit:",
        {
            "candidates": detail.get("utilization_detail"),
            "selected_check": detail.get("governing_check"),
            "selected_check_type": detail.get("governing_check_type"),
            "report_utilization": detail.get("utilization"),
            "raw_utilization": detail.get("utilization_raw"),
            "utilization_capped": detail.get("utilization_capped"),
            "governing_axis": _summary.get("governing_axis"),
            "governing_resistance_label": _summary.get("governing_resistance_label"),
            "governing_resistance_kN": _summary.get("governing_resistance_kN"),
            "failure_reason": _summary.get("governing_failure_reason"),
            "pass_fail": _summary.get("pass_fail"),
        },
    )
    print("[steel-column] buckling calculations:", detail.get("stability_summary"))
    print(
        "[steel-column] recommendation generation:",
        {
            "passing": len(recommendations),
            "rejected": len(rejected_sections),
            "top": [item.get("section") for item in detail["recommendations"][:5]],
        },
    )
    print(
        "[steel-column] returned response:",
        {
            "success": response["success"],
            "NEd": detail["effects"]["NEd_kN"],
            "MyEd": detail["effects"]["MyEd_kNm"],
            "VzEd": detail["effects"]["VzEd_kN"],
            "status": detail["status"],
        },
    )
    return clean_for_json(response)


def _params_from_request(request: SteelColumnRequest) -> ColumnParams:
    geometry = request.geometry
    material = request.material
    return ColumnParams(
        length_m=geometry.length_m,
        buckling_length_y_m=geometry.buckling_length_y_m,
        buckling_length_z_m=geometry.buckling_length_z_m,
        ltb_length_m=geometry.ltb_length_m,
        deflection_limit_ratio=geometry.deflection_limit_ratio,
        fy_MPa=material.fy_MPa,
        E_N_mm2=material.E_GPa * 1000.0,
        gamma_M0=material.gamma_M0,
        gamma_M1=request.design.gamma_M1,
        finish_type=request.design.finish_type,
        load_position=request.design.load_position,
        include_self_weight=request.loads.include_self_weight,
    )


def _loads_from_request(request: SteelColumnRequest) -> dict[str, ColumnLoad]:
    length = request.geometry.length_m
    return {
        "perm": _load_case(request.loads.permanent, length),
        "snow": _load_case(request.loads.snow, length),
        "wind": _load_case(request.loads.wind, length),
        "variable": _load_case(request.loads.variable, length),
    }


def _load_case(source: SteelColumnLoadCase, length_m: float) -> ColumnLoad:
    midspan = _clamp(length_m / 2.0, 0.0, length_m)
    return ColumnLoad(
        N=source.N_kN,
        py=source.py_kN_m,
        pz=source.pz_kN_m,
        Py=source.Py_kN,
        ay=_clamp(source.ay_m if source.ay_m > 0.0 else midspan, 0.0, length_m),
        Pz=source.Pz_kN,
        az=_clamp(source.az_m if source.az_m > 0.0 else midspan, 0.0, length_m),
    )


def _section_classification(profile: dict) -> dict:
    return {
        "method": "assumed",
        "assumed_class": "Class 1/2",
        "basis": "Profile table plastic moduli Wpl_y and Wpl_z are used for resistance checks.",
        "assumption": SECTION_CLASSIFICATION_ASSUMPTION,
        "profile_family": group_family(profile.get("n", "")),
    }


def _buckling_curve_selection(profile: dict, params: ColumnParams, axis: str) -> dict:
    family = group_family(profile.get("n", ""))
    if family == "BOX" and params.finish_type == 1:
        curve = "a"
        basis = "Hot finished hollow section, EN 1993-1-1 Table 6.2."
    elif family == "BOX" and params.finish_type == 2:
        curve = "c"
        basis = "Cold formed and welded hollow section, EN 1993-1-1 Table 6.2."
    else:
        curve = "c"
        basis = "Conservative default for non-box sections in this column workflow."
    return {
        "axis": axis,
        "curve": curve,
        "alpha": BUCKLING_CURVE_ALPHA[curve],
        "basis": basis,
    }


def _stability_summary(
    *,
    profile: dict,
    params: ColumnParams,
    governing_combo: dict,
    control_name: str,
    control_utilization: float,
    passing: bool,
    classification: dict,
) -> dict:
    report_util = _report_utilization(control_utilization)
    capped = report_util != control_utilization
    axis = _governing_axis(control_name, governing_combo)
    curve = governing_combo.get("bucklingCurveY") if axis == "y" else governing_combo.get("bucklingCurveZ")
    resistance = governing_combo.get("NbRdy") if axis == "y" else governing_combo.get("NbRdz")
    failure_mode = _check_label(control_name)
    description, _default_res_label, _default_axis, failure_text = CHECK_ENGINEERING.get(
        control_name,
        (failure_mode, "-", axis, f"{failure_mode} resistance exceeded"),
    )
    resistance_label, resistance_value = _governing_resistance(control_name, governing_combo, axis)
    if passing:
        reason = (
            f"PASS - governing check: {description} (axis {axis}); "
            f"utilization {report_util:.3f} <= 1.0; governing resistance {resistance_label}."
        )
        failure_reason = "None - member passes all column checks."
    else:
        extra = " Resistance is effectively exhausted (utilization beyond reporting cap)." if capped else ""
        reason = (
            f"FAIL - {failure_text}; governing utilization {report_util:.3f} > 1.0 "
            f"(axis {axis}, governing resistance {resistance_label}).{extra}"
        )
        failure_reason = failure_text
    return {
        "section_classification": classification,
        "buckling_curve_y": governing_combo.get("bucklingCurveY"),
        "buckling_curve_z": governing_combo.get("bucklingCurveZ"),
        "imperfection_factor_alpha_y": governing_combo.get("alphaY"),
        "imperfection_factor_alpha_z": governing_combo.get("alphaZ"),
        "lambda_bar_y": governing_combo.get("lambdaBarY"),
        "lambda_bar_z": governing_combo.get("lambdaBarZ"),
        "chi_y": governing_combo.get("chiY"),
        "chi_z": governing_combo.get("chiZ"),
        "NbRdy_kN": governing_combo.get("NbRdy"),
        "NbRdz_kN": governing_combo.get("NbRdz"),
        "governing_axis": axis,
        "governing_buckling_curve": curve,
        "governing_buckling_resistance_kN": resistance,
        "governing_failure_mode": failure_mode,
        "governing_check": description,
        "governing_check_type": control_name,
        "governing_resistance_label": resistance_label,
        "governing_resistance_kN": resistance_value,
        "governing_failure_reason": failure_reason,
        "governing_combination": (governing_combo.get("combo") or {}).get("name"),
        "governing_utilization": report_util,
        "governing_utilization_raw": control_utilization if math.isfinite(control_utilization) else None,
        "utilization_capped": capped,
        "pass_fail": "PASS" if passing else "FAIL",
        "reason": reason,
        "effective_buckling_length_y_m": params.buckling_length_y_m,
        "effective_buckling_length_z_m": params.buckling_length_z_m,
        "selected_section": profile.get("n"),
    }


def _evaluate_profile(
    profile: dict,
    params: ColumnParams,
    loads: dict[str, ColumnLoad],
    *,
    include_detail: bool,
    recommendation_limit: int = 8,
) -> dict | None:
    if not _has_required_column_properties(profile):
        return None

    combos = [_compute_column_combo(profile, combo, loads, params) for combo in COMBOS_K]
    uls = [item for item in combos if item["combo"]["kind"] == "ULS"]
    sls = [item for item in combos if item["combo"]["kind"] == "SLS"]
    if not uls or not sls:
        return None

    worst_uls = _max_by(uls, _control_from_combo)
    worst_sls = _max_by(sls, lambda item: max(abs(item["uy"]), abs(item["uz"])))
    worst_vz = _max_by(uls, lambda item: abs(item["VzEd"]))
    worst_my = _max_by(uls, lambda item: abs(item["MyEd"]))
    max_n = _max_by(uls, lambda item: item["N"])
    max_vy = _max_by(uls, lambda item: item["VyEd"])
    max_mz = _max_by(uls, lambda item: item["MzEd"])

    checks = {
        "compression": _max_by(uls, lambda item: item["ucComp"]),
        "shear_y": _max_by(uls, lambda item: item["ucShearY"]),
        "shear_z": _max_by(uls, lambda item: item["ucShearZ"]),
        "N_V_My": _max_by(uls, lambda item: item["ucMy"]),
        "N_V_Mz": _max_by(uls, lambda item: item["ucMz"]),
        "N_V_My_Mz": _max_by(uls, lambda item: item["ucMyMz"]),
        "stability_y": _max_by(uls, lambda item: item["ucStabY"]),
        "stability_z": _max_by(uls, lambda item: item["ucStabZ"]),
    }
    control_name, control_combo = max(checks.items(), key=lambda pair: _check_value(pair[0], pair[1]))
    control_util = _check_value(control_name, control_combo)
    pass_checks = math.isfinite(control_util) and control_util <= 1.0

    item = {
        "profile": profile,
        "section": profile.get("n"),
        "pass": pass_checks,
        "governing": control_util,
        "governing_check": _check_label(control_name),
        "control_combo": control_combo,
        "weight": profile.get("g") or math.inf,
    }
    if not include_detail:
        return item

    warnings = []
    classification = _section_classification(profile)
    warnings.append(classification["assumption"])
    if group_family(profile.get("n", "")) != "BOX":
        warnings.append("This column mode is intended for box / hollow sections.")
    if params.finish_type not in (1, 2):
        warnings.append("Finish type must be 1 or 2.")
    if params.fy_MPa < 235.0 or params.fy_MPa > 420.0:
        warnings.append("Check that the selected steel grade and section data are within the intended EC3 design range.")
    if float(profile.get("Wpl_y", 0.0) or 0.0) <= 0.0 or float(profile.get("Wpl_z", 0.0) or 0.0) <= 0.0:
        warnings.append("Profile plastic modulus data is missing.")
    if float(profile.get("It", 0.0) or 0.0) <= 0.0 or float(profile.get("Iw", 0.0) or 0.0) <= 0.0:
        warnings.append("Profile torsion or warping data is missing; LTB-related column terms may be unreliable.")
    if not any(abs(item["py"]) > 1e-12 or abs(item["pz"]) > 1e-12 or abs(item["Py"]) > 1e-12 or abs(item["Pz"]) > 1e-12 for item in sls):
        warnings.append("y/z deflection is driven by lateral loads py, pz, Py and Pz. Enable self-weight if member weight should contribute automatically.")
    if worst_uls["slenderY"] > 200.0 or worst_uls["slenderZ"] > 200.0:
        warnings.append("Slenderness exceeds 200; verify applicability and stability assumptions.")

    defl_allow = params.length_m * 1000.0 / params.deflection_limit_ratio
    util_defl_y = abs(worst_sls["uy"]) / defl_allow if defl_allow > 0.0 else math.inf
    util_defl_z = abs(worst_sls["uz"]) / defl_allow if defl_allow > 0.0 else math.inf
    if max(util_defl_y, util_defl_z) > 1.0:
        warnings.append("Column lateral deflection limit exceeded.")
    if control_util > 0.90:
        warnings.append("High utilization ratio.")

    reaction_left = (worst_uls["pz"] or 0.0) * params.length_m / 2.0 + (worst_uls["Pz"] or 0.0) * (
        params.length_m - (worst_uls["az"] or 0.0)
    ) / max(params.length_m, 1e-9)
    reaction_right = (worst_uls["pz"] or 0.0) * params.length_m / 2.0 + (worst_uls["Pz"] or 0.0) * (
        worst_uls["az"] or 0.0
    ) / max(params.length_m, 1e-9)

    report_util = _report_utilization(control_util)
    failure_text = CHECK_ENGINEERING.get(
        control_name, (None, None, None, f"{_check_label(control_name)} resistance exceeded")
    )[3]
    status_kind = "ok"
    status_text = "OK"
    if not pass_checks:
        status_kind = "bad"
        status_text = f"{failure_text} (UC {report_util:.2f})"
    elif control_util > 0.90:
        status_kind = "warn"
        status_text = "High utilization"

    stability_summary = _stability_summary(
        profile=profile,
        params=params,
        governing_combo=control_combo,
        control_name=control_name,
        control_utilization=control_util,
        passing=pass_checks,
        classification=classification,
    )

    item["detail"] = {
        "utilization": report_util,
        "utilization_raw": control_util if math.isfinite(control_util) else None,
        "utilization_capped": stability_summary["utilization_capped"],
        "status": status_text,
        "status_kind": status_kind,
        "governing_failure_mode": stability_summary["governing_failure_mode"],
        "governing_axis": stability_summary["governing_axis"],
        "governing_check": _check_label(control_name),
        "governing_check_description": stability_summary["governing_check"],
        "governing_check_type": stability_summary["governing_check_type"],
        "governing_resistance_label": stability_summary["governing_resistance_label"],
        "governing_resistance_kN": stability_summary["governing_resistance_kN"],
        "governing_failure_reason": stability_summary["governing_failure_reason"],
        "governing_combination": f"{control_combo['combo']['name']}; {worst_sls['combo']['name']}",
        "section": {
            "name": profile.get("n"),
            "family": group_family(profile.get("n", "")),
            "height_mm": profile.get("h"),
            "width_mm": profile.get("b"),
            "weight_kg_m": profile.get("g"),
            "classification": classification,
        },
        "geometry": asdict(params),
        "loads": {key: asdict(value) for key, value in loads.items()},
        "effects": {
            "NEd_kN": max_n["N"],
            "VyEd_kN": max_vy["VyEd"],
            "VzEd_kN": abs(worst_vz["VzEd"]),
            "MyEd_kNm": abs(worst_my["MyEd"]),
            "MzEd_kNm": max_mz["MzEd"],
            "RA_kN": abs(reaction_left),
            "RB_kN": abs(reaction_right),
            "uy_mm": worst_sls["uy"],
            "uz_mm": worst_sls["uz"],
        },
        "resistance": {
            "NcRd_kN": checks["compression"]["NcRd"],
            "VcRdy_kN": checks["shear_y"]["VcRdy"],
            "VcRdz_kN": checks["shear_z"]["VcRdz"],
            "MyVRd_kNm": checks["N_V_My"]["MyVRd"],
            "MzVRd_kNm": checks["N_V_Mz"]["MzVRd"],
            "NbRdy_kN": control_combo["NbRdy"],
            "NbRdz_kN": control_combo["NbRdz"],
            "NbRd_governing_kN": stability_summary["governing_buckling_resistance_kN"],
        },
        "utilization_detail": {
            "compression": _report_utilization(checks["compression"]["ucComp"]),
            "shear_y": _report_utilization(checks["shear_y"]["ucShearY"]),
            "shear_z": _report_utilization(checks["shear_z"]["ucShearZ"]),
            "N_V_My": _report_utilization(checks["N_V_My"]["ucMy"]),
            "N_V_Mz": _report_utilization(checks["N_V_Mz"]["ucMz"]),
            "N_V_My_Mz": _report_utilization(checks["N_V_My_Mz"]["ucMyMz"]),
            "stability_y": _report_utilization(checks["stability_y"]["ucStabY"]),
            "stability_z": _report_utilization(checks["stability_z"]["ucStabZ"]),
            "control": report_util,
        },
        "buckling": {
            "buckling_curve_y": control_combo["bucklingCurveY"],
            "buckling_curve_z": control_combo["bucklingCurveZ"],
            "alpha_y": control_combo["alphaY"],
            "alpha_z": control_combo["alphaZ"],
            "Ncr_y_kN": control_combo["NcrY"],
            "Ncr_z_kN": control_combo["NcrZ"],
            "lambda_bar_y": control_combo["lambdaBarY"],
            "lambda_bar_z": control_combo["lambdaBarZ"],
            "chi_y": control_combo["chiY"],
            "chi_z": control_combo["chiZ"],
            "chi_lt": control_combo["chiLT"],
            "slender_y": control_combo["slenderY"],
            "slender_z": control_combo["slenderZ"],
            "NbRdy_kN": control_combo["NbRdy"],
            "NbRdz_kN": control_combo["NbRdz"],
            "governing_axis": stability_summary["governing_axis"],
            "governing_buckling_resistance_kN": stability_summary["governing_buckling_resistance_kN"],
            "Mcr_kNm": worst_uls["Mcr"],
        },
        "stability_summary": stability_summary,
        "eurocode": {
            "standard": "EN 1993-1-1",
            "compression_member_clause": "6.3.1",
            "interaction_clause": "6.3.3",
            "section_classification": classification,
            "assumptions": [
                classification["assumption"],
                "Buckling curve is selected from the section type input: hot finished hollow sections use curve a; cold formed welded hollow sections use curve c.",
            ],
        },
        "deflection": {
            "uy_mm": worst_sls["uy"],
            "uz_mm": worst_sls["uz"],
            "allow_mm": defl_allow,
            "utilization_y": util_defl_y,
            "utilization_z": util_defl_z,
        },
        "status_detail": {
            "kind": status_kind,
            "text": status_text,
            "failures": [stability_summary["governing_failure_reason"]] if not pass_checks else [],
        },
        "combos": {
            "governing_uls": worst_uls,
            "governing_sls": worst_sls,
        },
        "recommendations": [],
        "warnings": warnings,
    }
    return item


def _compute_column_combo(profile: dict, combo: dict, loads: dict[str, ColumnLoad], params: ColumnParams) -> dict:
    A = float(profile.get("A", 0.0) or 0.0) * 100.0
    h = float(profile.get("h", 0.0) or 0.0)
    b = float(profile.get("b", 0.0) or 0.0)
    tw = float(profile.get("tw", 0.0) or 0.0)
    tf = float(profile.get("tf", 0.0) or 0.0)
    Iy = float(profile.get("Iy", 0.0) or 0.0) * 10000.0
    Iz = float(profile.get("Iz", 0.0) or 0.0) * 10000.0
    WplY = float(profile.get("Wpl_y", 0.0) or 0.0) * 1000.0
    WplZ = float(profile.get("Wpl_z", 0.0) or 0.0) * 1000.0
    ry_mm = float(profile.get("ry", 0.0) or 0.0) * 10.0
    rz_mm = float(profile.get("rz", 0.0) or 0.0) * 10.0
    It = float(profile.get("It", 0.0) or 0.0) * 10000.0
    Iw = float(profile.get("Iw", 0.0) or 0.0) * 1_000_000_000.0

    perm = loads["perm"]
    snow = loads["snow"]
    wind = loads["wind"]
    variable = loads["variable"]
    self_pz = (float(profile.get("g", 0.0) or 0.0) / 100.0) if params.include_self_weight else 0.0

    N = perm.N * combo["perm"] + snow.N * combo["snow"] + wind.N * combo["wind"] + variable.N * combo["variable"]
    py = perm.py * combo["perm"] + snow.py * combo["snow"] + wind.py * combo["wind"] + variable.py * combo["variable"]
    pz = self_pz * combo["perm"] + perm.pz * combo["perm"] + snow.pz * combo["snow"] + wind.pz * combo["wind"] + variable.pz * combo["variable"]
    Py = perm.Py * combo["perm"] + snow.Py * combo["snow"] + wind.Py * combo["wind"] + variable.Py * combo["variable"]
    Pz = perm.Pz * combo["perm"] + snow.Pz * combo["snow"] + wind.Pz * combo["wind"] + variable.Pz * combo["variable"]
    ay = perm.ay
    az = perm.az

    VyEd = py * params.length_m / 2.0 + Py * max(ay, params.length_m - ay) / params.length_m
    VzEd = pz * params.length_m / 2.0 + Pz * max(az, params.length_m - az) / params.length_m
    xMy = _column_moment_position(pz, Pz, az, params.length_m)
    xMz = _column_moment_position(py, Py, ay, params.length_m)
    MyEd = pz * params.length_m / 2.0 * (xMy - xMy * xMy / params.length_m) + (
        Pz * (params.length_m - az) / params.length_m * xMy
        if xMy < az
        else Pz * az / params.length_m * (params.length_m - xMy)
    )
    MzEd = py * params.length_m / 2.0 * (xMz - xMz * xMz / params.length_m) + (
        Py * (params.length_m - ay) / params.length_m * xMz
        if xMz < ay
        else Py * ay / params.length_m * (params.length_m - xMz)
    )

    NcRd = _div(A * params.fy_MPa, params.gamma_M0 * 1000.0)
    Avy = A * tf / (tf + tw) if tw > 0.0 and tf > 0.0 else 0.0
    Avz = A * tw / (tf + tw) if tw > 0.0 and tf > 0.0 else 0.0
    VcRdy = _div(Avy * (params.fy_MPa / math.sqrt(3.0)), params.gamma_M0 * 1000.0)
    VcRdz = _div(Avz * (params.fy_MPa / math.sqrt(3.0)), params.gamma_M0 * 1000.0)

    ucComp = _div(N, NcRd)
    ucShearY = _div(VyEd, VcRdy)
    ucShearZ = _div(VzEd, VcRdz)
    rzFac = (2.0 * VyEd / VcRdy - 1.0) ** 2 if VcRdy > 0.0 and VyEd / VcRdy >= 0.5 else 0.0
    ryFac = (2.0 * VzEd / VcRdz - 1.0) ** 2 if VcRdz > 0.0 and VzEd / VcRdz >= 0.5 else 0.0

    MplYRd = _div(WplY * (1.0 - ryFac) * params.fy_MPa, params.gamma_M0 * 1_000_000.0)
    MplZRd = _div(WplZ * (1.0 - rzFac) * params.fy_MPa, params.gamma_M0 * 1_000_000.0)
    MyVRd = min(
        _div((WplY - ryFac * Avz * Avy / (4.0 * max(tw, 1e-9))) * params.fy_MPa, params.gamma_M0 * 1_000_000.0),
        MplYRd,
    )
    qz = 1.03 * math.sqrt(max(0.0, 1.0 - (VzEd / VcRdz) ** 2)) if VcRdz > 0.0 and abs(VzEd) <= VcRdz else 0.0
    NVzRd = NcRd - _div(2.0 * (1.0 - qz) * tf * h * params.fy_MPa, params.gamma_M0 * 1000.0)
    a3 = min((A - 2.0 * b * tw) / A, 0.5) if A > 0.0 else 0.0
    a4z = qz * a3

    MzVRd = MplZRd - _div((1.0 - rzFac) * tw * b * b * params.fy_MPa, 2.0 * 1_000_000.0 * params.gamma_M0)
    qy = 1.03 * math.sqrt(max(0.0, 1.0 - (VyEd / VcRdy) ** 2)) if VcRdy > 0.0 and abs(VyEd) <= VcRdy else 0.0
    NVyRd = NcRd - _div(2.0 * (1.0 - qy) * b * tf * params.fy_MPa, params.gamma_M0 * 1000.0)
    a4y = qy * a3

    ucMy = _column_bending_utilization(N, MyEd, MyVRd, NVzRd, a4z)
    ucMz = _column_bending_utilization(N, MzEd, MzVRd, NVyRd, a4y)
    MyNVRd = _div(MyVRd * (1.0 - _div(N, NVzRd)), 1.0 - a4z / 2.0)
    MzNVRd = _div(MzVRd * (1.0 - _div(N, NVyRd)), 1.0 - a4y / 2.0)
    my_ratio = _div(MyEd, MyNVRd)
    mz_ratio = _div(MzEd, MzNVRd)
    a1 = 1 if my_ratio <= 2.0 / 3.0 else 2
    a2 = 2 if mz_ratio <= 2.0 / 3.0 else 1
    b0 = 1 if my_ratio <= 2.0 / 3.0 else 0.75
    b1 = 0.75 if mz_ratio <= 2.0 / 3.0 else 1
    ucMyMz = b0 * _safe_pow(my_ratio, a1) + b1 * _safe_pow(mz_ratio, a2)

    curve_y = _buckling_curve_selection(profile, params, "y")
    curve_z = _buckling_curve_selection(profile, params, "z")
    alphaY = curve_y["alpha"]
    alphaZ = curve_z["alpha"]
    Nycr = math.pi * math.pi * params.E_N_mm2 * Iy / (params.buckling_length_y_m**2) / 1_000_000_000.0 if params.buckling_length_y_m > 0.0 else 0.0
    Nzcr = math.pi * math.pi * params.E_N_mm2 * Iz / (params.buckling_length_z_m**2) / 1_000_000_000.0 if params.buckling_length_z_m > 0.0 else 0.0
    lamY = math.sqrt(_div(A * params.fy_MPa, Nycr * 1000.0)) if Nycr > 0.0 else math.inf
    lamZ = math.sqrt(_div(A * params.fy_MPa, Nzcr * 1000.0)) if Nzcr > 0.0 else math.inf
    chiY = _buckling_reduction(lamY, alphaY)
    chiZ = _buckling_reduction(lamZ, alphaZ)
    NRk = A * params.fy_MPa / 1000.0

    Ay = _column_ay(pz, Pz, params.length_m)
    By = _column_by(pz, Pz, params.length_m)
    Az = _column_ay(py, Py, params.length_m)
    Bz = _column_by(py, Py, params.length_m)
    C1 = 1.13 * Ay + 1.35 * By
    C2 = 0.0 if params.load_position == 0 else (0.45 * Ay + 0.55 * By if params.load_position == 1 else -0.45 * Ay - 0.55 * By)
    G = params.E_N_mm2 / 2.6
    S = math.sqrt((params.E_N_mm2 * Iw) / (G * It)) if It > 0.0 and Iw > 0.0 and G > 0.0 else 0.0
    C = (
        math.pi
        * C1
        * params.length_m
        / params.ltb_length_m
        * (
            math.sqrt(max(0.0, 1.0 + math.pi * math.pi * S * S / (params.ltb_length_m * params.ltb_length_m) * (C2 * C2 + 1.0)))
            + math.pi * C2 * S / params.ltb_length_m
        )
        if params.ltb_length_m > 0.0
        else 0.0
    )
    Mcr = C / params.length_m * math.sqrt(max(0.0, params.E_N_mm2 * Iz * G * It)) / 1_000_000.0 if params.length_m > 0.0 else 0.0
    lamLT = math.sqrt(_div(WplY * params.fy_MPa, Mcr * 1_000_000.0)) if Mcr > 0.0 else math.inf
    PhiLT = 0.5 * (1.0 + (0.34 if b > 0.0 and h / b <= 2.0 else 0.49) * (lamLT - 0.4) + 0.75 * lamLT * lamLT)
    kc = 0.94 * Ay + 0.86 * By
    fRed = min(1.0 - 0.5 * (1.0 - kc) * (1.0 - 2.0 * (lamLT - 0.8) ** 2), 1.0)
    chiLT = 1.0
    if h != b:
        base = _div(1.0, (PhiLT + math.sqrt(max(0.0, PhiLT * PhiLT - 0.75 * lamLT * lamLT))) * max(fRed, 1e-9))
        chiLT = min(base, 1.0, _div(1.0, lamLT * lamLT * max(fRed, 1e-9)))

    Cmy = 0.95 * Ay + 0.9 * By
    Cmz = 0.95 * Az + 0.9 * Bz
    NbRdy = chiY * NRk / params.gamma_M1
    NbRdz = chiZ * NRk / params.gamma_M1
    chiYNRd = max(NbRdy, 1e-9)
    chiZNRd = max(NbRdz, 1e-9)
    kyy = min(Cmy * (1.0 + (lamY - 0.2) * N / chiYNRd), Cmy * (1.0 + 0.8 * N / chiYNRd))
    kyz = 0.6 * Cmz
    kzy = 0.6 * kyy
    kzz = min(Cmz * (1.0 + (2.0 * lamZ - 0.6) * N / chiZNRd), Cmz * (1.0 + 1.4 * N / chiZNRd))
    # B3: the EN 1993-1-1 6.3.3 stability interaction denominators must use the
    # characteristic resistance divided by gamma_M1. MyVRd and NVzRd are *design*
    # resistances that already carry gamma_M0, so multiply by gamma_M0 to recover the
    # characteristic (shear-reduced) value before applying gamma_M1. This keeps gamma_M0
    # confined to the cross-section checks (6.2) and gamma_M1 to the stability checks
    # (6.3). When gamma_M0 == gamma_M1 == 1.0 the factor is unity, so verified default
    # results are unchanged; only non-unity gamma_M0 cases are corrected.
    MyRk_shear = MyVRd * params.gamma_M0
    NVRk_shear = NVzRd * params.gamma_M0
    ucStabY = N / chiYNRd + kyy * MyEd / max(chiLT * MyRk_shear / params.gamma_M1, 1e-9) + kyz * MzEd / max(NVRk_shear / params.gamma_M1, 1e-9)
    ucStabZ = N / chiZNRd + kzy * MyEd / max(chiLT * MyRk_shear / params.gamma_M1, 1e-9) + kzz * MzEd / max(NVRk_shear / params.gamma_M1, 1e-9)

    slenderY = params.buckling_length_y_m * 1000.0 / ry_mm if ry_mm > 0.0 else math.inf
    slenderZ = params.buckling_length_z_m * 1000.0 / rz_mm if rz_mm > 0.0 else math.inf
    uy = _lateral_deflection(combo, py, Py, ay, params.length_m, params.E_N_mm2, Iz)
    uz = _lateral_deflection(combo, pz, Pz, az, params.length_m, params.E_N_mm2, Iy)

    return {
        "combo": combo,
        "N": N,
        "py": py,
        "pz": pz,
        "Py": Py,
        "Pz": Pz,
        "ay": ay,
        "az": az,
        "VyEd": VyEd,
        "VzEd": VzEd,
        "MyEd": MyEd,
        "MzEd": MzEd,
        "NcRd": NcRd,
        "VcRdy": VcRdy,
        "VcRdz": VcRdz,
        "ucComp": ucComp,
        "ucShearY": ucShearY,
        "ucShearZ": ucShearZ,
        "ucMy": ucMy,
        "ucMz": ucMz,
        "ucMyMz": ucMyMz,
        "ucStabY": ucStabY,
        "ucStabZ": ucStabZ,
        "NcrY": Nycr,
        "NcrZ": Nzcr,
        "lambdaBarY": lamY,
        "lambdaBarZ": lamZ,
        "bucklingCurveY": curve_y["curve"],
        "bucklingCurveZ": curve_z["curve"],
        "bucklingCurveBasisY": curve_y["basis"],
        "bucklingCurveBasisZ": curve_z["basis"],
        "alphaY": alphaY,
        "alphaZ": alphaZ,
        "NbRdy": NbRdy,
        "NbRdz": NbRdz,
        "governingAxis": "y" if ucStabY >= ucStabZ else "z",
        "chiY": chiY,
        "chiZ": chiZ,
        "chiLT": chiLT,
        "slenderY": slenderY,
        "slenderZ": slenderZ,
        "uy": uy,
        "uz": uz,
        "MyVRd": MyVRd,
        "MzVRd": MzVRd,
        "Mcr": Mcr,
    }


def _recommend_columns(
    request: SteelColumnRequest,
    params: ColumnParams,
    loads: dict[str, ColumnLoad],
) -> tuple[list[dict], list[dict]]:
    recommendations = []
    rejected = []
    for profile in load_profiles():
        name = profile.get("n", "")
        if group_family(name) != "BOX":
            continue
        item = _evaluate_profile(profile, params, loads, include_detail=False)
        if item is None:
            rejected.append({"section": name, "reason": "Incomplete section geometry or properties."})
            continue
        if not item["pass"]:
            rejected.append(
                {
                    "section": name,
                    "reason": "Fails steel column strength or stability checks.",
                    "utilization": item.get("governing"),
                    "governing_check": item.get("governing_check"),
                }
            )
            continue
        recommendations.append(item)

    recommendations.sort(key=lambda item: (item.get("weight", math.inf), item.get("governing", math.inf), item.get("section", "")))
    return recommendations, rejected


def _recommendation_payload(items: list[dict]) -> list[dict]:
    payload = []
    for item in items:
        combo = item.get("control_combo") or {}
        profile = item.get("profile") or {}
        payload.append(
            {
                "section": profile.get("n"),
                "family": group_family(profile.get("n", "")),
                "weight_kg_m": item.get("weight"),
                "utilization": item.get("governing"),
                "governing": item.get("governing_check"),
                "governing_combination": (combo.get("combo") or {}).get("name"),
                "NEd_kN": combo.get("N"),
                "NbRdy_kN": combo.get("NbRdy"),
                "NbRdz_kN": combo.get("NbRdz"),
                "governing_axis": combo.get("governingAxis"),
                "buckling_curve_y": combo.get("bucklingCurveY"),
                "buckling_curve_z": combo.get("bucklingCurveZ"),
                "lambda_bar_y": combo.get("lambdaBarY"),
                "lambda_bar_z": combo.get("lambdaBarZ"),
                "chi_y": combo.get("chiY"),
                "chi_z": combo.get("chiZ"),
                "slender_y": combo.get("slenderY"),
                "slender_z": combo.get("slenderZ"),
                "rank_reason": "Lightest passing section after strength and stability filtering.",
            }
        )
    return payload


def _has_required_column_properties(profile: dict) -> bool:
    required = ("A", "Iy", "Iz", "Wpl_y", "Wpl_z", "ry", "rz")
    return all(float(profile.get(key, 0.0) or 0.0) > 0.0 for key in required)


def _validate_result_structure(detail: dict) -> list[str]:
    warnings = []
    checks = {
        "section": dict,
        "effects": dict,
        "resistance": dict,
        "utilization_detail": dict,
        "buckling": dict,
        "stability_summary": dict,
        "eurocode": dict,
        "deflection": dict,
        "recommendations": list,
    }
    for key, expected in checks.items():
        value = detail.get(key)
        print(
            "[steel-column] response field check:",
            {
                "field": key,
                "type": type(value).__name__,
                "length": len(value) if hasattr(value, "__len__") else None,
            },
        )
        if not isinstance(value, expected):
            warnings.append(f"Backend response field '{key}' was not in the expected structure.")
    return warnings


def _control_from_combo(item: dict) -> float:
    return max(
        item["ucComp"],
        item["ucShearY"],
        item["ucShearZ"],
        item["ucMy"],
        item["ucMz"],
        item["ucMyMz"],
        item["ucStabY"],
        item["ucStabZ"],
    )


def _check_value(name: str, combo: dict) -> float:
    keys = {
        "compression": "ucComp",
        "shear_y": "ucShearY",
        "shear_z": "ucShearZ",
        "N_V_My": "ucMy",
        "N_V_Mz": "ucMz",
        "N_V_My_Mz": "ucMyMz",
        "stability_y": "ucStabY",
        "stability_z": "ucStabZ",
    }
    return float(combo.get(keys[name], math.inf))


def _check_label(name: str) -> str:
    return {
        "compression": "Compression",
        "shear_y": "Shear y",
        "shear_z": "Shear z",
        "N_V_My": "N+V+My",
        "N_V_Mz": "N+V+Mz",
        "N_V_My_Mz": "N+V+My+Mz",
        "stability_y": "Stability y",
        "stability_z": "Stability z",
    }.get(name, name)


def _report_utilization(value: float) -> float:
    """Coerce a governing utilization into an always-finite, reportable number.

    Pass/fail logic keeps using the raw value; this only governs what the engineer
    sees so an overstressed member never reports 0.000, "-", "inf" or NaN.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return UTILIZATION_REPORT_CAP
    if math.isnan(number):
        return UTILIZATION_REPORT_CAP
    if number < 0.0:
        return 0.0
    if not math.isfinite(number) or number > UTILIZATION_REPORT_CAP:
        return UTILIZATION_REPORT_CAP
    return number


def _governing_axis(control_name: str, combo: dict) -> str:
    axis = CHECK_ENGINEERING.get(control_name, ("", "", "y", ""))[2]
    if axis in ("y", "z"):
        return axis
    if control_name == "compression":
        # The weaker buckling axis controls the compression member.
        return "y" if combo.get("NbRdy", math.inf) <= combo.get("NbRdz", math.inf) else "z"
    # Biaxial interaction: report the axis carrying the higher stability demand.
    return "y" if combo.get("ucStabY", 0.0) >= combo.get("ucStabZ", 0.0) else "z"


def _governing_resistance(control_name: str, combo: dict, axis: str) -> tuple[str, float | None]:
    table = {
        "compression": ("Nc,Rd", combo.get("NcRd")),
        "shear_y": ("Vc,Rd,y", combo.get("VcRdy")),
        "shear_z": ("Vc,Rd,z", combo.get("VcRdz")),
        "N_V_My": ("My,V,Rd", combo.get("MyVRd")),
        "N_V_Mz": ("Mz,V,Rd", combo.get("MzVRd")),
        "stability_y": ("Nb,Rd,y", combo.get("NbRdy")),
        "stability_z": ("Nb,Rd,z", combo.get("NbRdz")),
    }
    if control_name in table:
        return table[control_name]
    # Biaxial interaction is buckling-driven in this regime; point at the controlling axis.
    if axis == "y":
        return "Nb,Rd,y", combo.get("NbRdy")
    return "Nb,Rd,z", combo.get("NbRdz")


def _max_by(items: list[dict], key: Callable[[dict], float]) -> dict:
    best = items[0]
    best_value = -math.inf
    for item in items:
        value = key(item)
        if value > best_value:
            best = item
            best_value = value
    return best


def _column_ay(py: float, Py: float, length_m: float) -> float:
    denominator = py * length_m + 2.0 * Py
    return 1.0 if denominator == 0.0 else py * length_m / denominator


def _column_by(py: float, Py: float, length_m: float) -> float:
    denominator = py * length_m + 2.0 * Py
    return 1.0 if denominator == 0.0 else 2.0 * Py / denominator


def _column_moment_position(udl: float, point_load: float, position_m: float, length_m: float) -> float:
    if udl == 0.0:
        return position_m
    if position_m > length_m / 2.0:
        x = length_m / 2.0 + point_load / udl * (length_m - position_m) / length_m
        return position_m if x > position_m else x
    x = length_m / 2.0 - point_load * position_m / udl / length_m
    return position_m if x < position_m else x


def _column_bending_utilization(N: float, MEd: float, MVRd: float, NVRd: float, a4: float) -> float:
    base = _div(MEd, MVRd)
    if N <= a4 * NVRd / 2.0:
        return base
    return base + _div(_div(N, NVRd) - a4 / 2.0, 1.0 - a4 / 2.0)


def _buckling_reduction(lambda_bar: float, alpha: float) -> float:
    if not math.isfinite(lambda_bar):
        return 0.0
    phi = 0.5 * (1.0 + alpha * (lambda_bar - 0.2) + lambda_bar * lambda_bar)
    return min(1.0, _div(1.0, phi + math.sqrt(max(0.0, phi * phi - lambda_bar * lambda_bar))))


def _lateral_deflection(combo: dict, udl: float, point_load: float, position_m: float, length_m: float, E_N_mm2: float, I_mm4: float) -> float:
    if combo["kind"] != "SLS":
        return 0.0
    uniform = 5.0 * udl * length_m**4 / 384.0 / E_N_mm2 / max(I_mm4, 1e-9) * 1000.0**4
    a = position_m
    b = length_m - position_m
    if a > b:
        point = point_load * a * b / (27.0 * E_N_mm2 * max(I_mm4, 1e-9) * length_m) * (a + 2.0 * b) * math.sqrt(3.0 * a * (a + 2.0 * b)) * 1000.0**4
    else:
        point = point_load * a * b / (27.0 * E_N_mm2 * max(I_mm4, 1e-9) * length_m) * (b + 2.0 * a) * math.sqrt(3.0 * b * (b + 2.0 * a)) * 1000.0**4
    return uniform + point


def _safe_pow(value: float, exponent: float) -> float:
    if value < 0.0 or not math.isfinite(value):
        return math.inf
    return value**exponent


def _div(numerator: float, denominator: float) -> float:
    if not math.isfinite(numerator) or not math.isfinite(denominator) or abs(denominator) <= 1e-12:
        return math.inf
    return numerator / denominator


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
