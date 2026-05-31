from __future__ import annotations

from dataclasses import asdict, dataclass
import math

from core.combinations.eurocode import ACTIONS
from core.eurocode.ec3 import (
    SectionClass,
    SectionProps,
    area_cm2,
    axial_resistance_kN,
    bending_resistance_kNm,
    compute_bending_class,
    get_section_props,
    high_shear_reduced_bending_kNm,
    ltb_check,
    shear_resistance_kN,
)
from core.loads.statics import PointLoad, max_effects, scale_point_loads
from core.loads.takedown import LoadTakedownResult, calculate_floor_load_takedown
from core.plots.beam_diagrams import build_simply_supported_beam_plots
from core.plots.serialization import validate_beam_plot_payload
from core.recommendations.steel import beam_recommendation_sort_key
from core.steel.sections import find_profile, group_family, load_profiles
from models.steel import SteelBeamRequest
from utils.serialization import clean_for_json
from utils.units import cm4_to_mm4, steel_self_weight_kN_m


SUPPORT_WIDTH_GAP_LIMIT_MM = 30.0
SUPPORT_WIDTH_ALLOWED_FAMILIES = {"IPE", "HEA", "HEB", "HEM"}
SUPPORT_WIDTH_FAMILY_ORDER = {"HEA": 0, "HEB": 1, "HEM": 2, "IPE": 3}


@dataclass(frozen=True)
class BeamLoadSetup:
    span_m: float
    span_mm: float
    axis: str
    E_N_mm2: float
    fy_MPa: float
    gamma_M0: float
    deflection_limit_ratio: float
    axial_NEd_kN: float
    section_class: SectionClass
    section_props: SectionProps
    I_mm4: float
    w_ULS_kN_m: float
    w_SLS_kN_m: float
    point_loads_ULS: list[PointLoad]
    point_loads_SLS: list[PointLoad]
    support_reaction_breakdown: dict | None
    automatic_takedown: LoadTakedownResult | None
    governing_uls: str
    governing_sls: str
    warnings: list[str]


def calculate_steel_beam(request: SteelBeamRequest) -> dict:
    print("[steel-beam] request payload:", request.model_dump(mode="json"))
    profile = find_profile(request.profile_name)
    if profile is None:
        raise ValueError(f"Unknown steel profile: {request.profile_name}")

    setup = _build_load_setup(request, profile)
    result = _evaluate_profile(profile, request, setup, include_detail=True)
    if result is None:
        raise ValueError("Selected section has incomplete geometry or section properties for steel beam design.")

    recommendation_result = _recommend_sections(request)
    print(
        "[steel-beam] recommendation workflow contract:",
        {
            "type": type(recommendation_result).__name__,
            "length": len(recommendation_result) if hasattr(recommendation_result, "__len__") else None,
            "item_types": [type(item).__name__ for item in recommendation_result[:3]]
            if isinstance(recommendation_result, (list, tuple))
            else None,
        },
    )
    recommendations, support_width_candidates, rejected_sections = _validate_recommendation_contract(
        recommendation_result
    )
    recommendation_payload = _recommendation_payload(recommendations[: request.design.recommendation_limit])
    detail = result["detail"]
    detail["recommendations"] = recommendation_payload
    detail["support_width_recommendations"] = _support_width_recommendation_payload(
        support_width_candidates[: request.design.recommendation_limit]
    )
    detail["support_width_recommendation_status"] = _support_width_recommendation_status(
        request.design.effective_support_width_cm,
        detail["support_width_recommendations"],
    )
    detail["recommendation_debug"] = {
        "filtered_sections": [item.get("section") for item in recommendation_payload],
        "rejected_sections": rejected_sections[:50],
        "support_width_candidate_count": len(support_width_candidates),
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
        "[steel-beam] calculated reactions:",
        {
            "RA_kN": detail["reactions"]["left_kN"],
            "RB_kN": detail["reactions"]["right_kN"],
        },
    )
    print("[steel-beam] governing load combination:", detail["governing_combination"])
    print(
        "[steel-beam] support widths received:",
        {
            "left_cm": request.design.left_width_cm,
            "right_cm": request.design.right_width_cm,
            "effective_min_cm": request.design.effective_support_width_cm,
        },
    )
    print("[steel-beam] auto load breakdown values:", detail.get("auto_load_breakdown"))
    print(
        "[steel-beam] plot payload:",
        {
            "keys": sorted((detail.get("plots") or {}).keys()),
            "points": len((detail.get("plots") or {}).get("x") or []),
            "markers": (detail.get("plots") or {}).get("markers"),
        },
    )
    print("[steel-beam] filtered sections:", detail["recommendation_debug"]["filtered_sections"][:10])
    print("[steel-beam] rejected sections:", rejected_sections[:10])
    print(
        "[steel-beam] recommendation ranking:",
        [
            {
                "section": item.get("section"),
                "support_fit": item.get("support_width_fit"),
                "utilization": item.get("utilization"),
            }
            for item in recommendation_payload[:10]
        ],
    )
    print("[steel-beam] governing checks:", detail.get("utilization_detail"))
    print(
        "[steel-beam] returned response:",
        {
            "success": response["success"],
            "MEd": detail["MEd"],
            "VEd": detail["VEd"],
            "status": detail["status"],
            "recommendations": len(recommendation_payload),
            "support_width_recommendations": len(detail["support_width_recommendations"]),
        },
    )
    return clean_for_json(response)


def _build_load_setup(request: SteelBeamRequest, profile: dict) -> BeamLoadSetup:
    warnings: list[str] = []
    span_m = request.geometry.span_m
    span_mm = span_m * 1000.0
    E_N_mm2 = request.material.E_GPa * 1000.0
    fy_MPa = request.material.fy_MPa
    gamma_M0 = request.material.gamma_M0
    section_class = compute_bending_class(profile, fy_MPa)
    section_props = get_section_props(request.geometry.axis, profile, section_class)
    I_mm4 = cm4_to_mm4(section_props.I_cm4)

    point_loads_raw = _read_point_loads(request, warnings)

    include_self_weight = request.loads.include_self_weight if request.loads.mode == "comb" else True
    self_weight = steel_self_weight_kN_m(section_props.weight_kg_m) if include_self_weight else 0.0

    if request.loads.mode == "direct":
        w_ULS = request.loads.direct_w_kN_m + self_weight
        w_SLS = request.loads.direct_w_kN_m + self_weight
        point_loads = [PointLoad(load["P_kN"], load["a_m"]) for load in point_loads_raw]
        return BeamLoadSetup(
            span_m=span_m,
            span_mm=span_mm,
            axis=request.geometry.axis,
            E_N_mm2=E_N_mm2,
            fy_MPa=fy_MPa,
            gamma_M0=gamma_M0,
            deflection_limit_ratio=request.geometry.deflection_limit_ratio,
            axial_NEd_kN=request.design.axial_NEd_kN,
            section_class=section_class,
            section_props=section_props,
            I_mm4=I_mm4,
            w_ULS_kN_m=w_ULS,
            w_SLS_kN_m=w_SLS,
            point_loads_ULS=point_loads,
            point_loads_SLS=point_loads,
            support_reaction_breakdown=None,
            automatic_takedown=None,
            governing_uls="Direct load",
            governing_sls="Direct load",
            warnings=warnings,
        )

    line_loads = _line_loads_by_type(request)
    automatic_takedown = calculate_floor_load_takedown(request.loads.automatic)
    if automatic_takedown.enabled:
        line_loads["G"] += automatic_takedown.dead_kN_m
        line_loads["live"] += automatic_takedown.live_kN_m
    warnings.extend(automatic_takedown.warnings)

    Gk = line_loads["G"]
    Gtot = Gk + self_weight
    variable_loads = {action: line_loads[action] for action in ACTIONS}
    gamma_G = request.loads.gamma_G
    gamma_Q = request.loads.gamma_Q
    psi0 = request.loads.psi0
    psi1 = request.loads.psi1
    psi2 = request.loads.psi2

    candidates = _candidate_lead_actions(variable_loads, point_loads_raw)

    def factors_uls(lead: str) -> dict[str, float]:
        return {
            "G": gamma_G,
            "live": gamma_Q * (1.0 if lead == "live" else psi0.get("live", 0.0)),
            "wind": gamma_Q * (1.0 if lead == "wind" else psi0.get("wind", 0.0)),
            "snow": gamma_Q * (1.0 if lead == "snow" else psi0.get("snow", 0.0)),
        }

    def factors_sls(lead: str) -> dict[str, float]:
        factors = {"G": 1.0, "live": 0.0, "wind": 0.0, "snow": 0.0}
        if request.loads.sls_case == "qp":
            for action in ACTIONS:
                factors[action] = psi2.get(action, 0.0)
            return factors
        for action in ACTIONS:
            if action == lead:
                factors[action] = 1.0 if request.loads.sls_case == "rare" else psi1.get(action, 0.0)
            else:
                factors[action] = psi0.get(action, 0.0) if request.loads.sls_case == "rare" else psi2.get(action, 0.0)
        return factors

    def uls_line_load(lead: str) -> float:
        total = gamma_G * Gtot
        for action in ACTIONS:
            value = variable_loads.get(action, 0.0)
            if abs(value) < 1e-12:
                continue
            total += gamma_Q * (value if action == lead else psi0.get(action, 0.0) * value)
        return total

    def sls_line_load(lead: str) -> float:
        total = Gtot
        if request.loads.sls_case == "qp":
            for action in ACTIONS:
                total += psi2.get(action, 0.0) * variable_loads.get(action, 0.0)
            return total
        for action in ACTIONS:
            value = variable_loads.get(action, 0.0)
            if abs(value) < 1e-12:
                continue
            if action == lead:
                total += value if request.loads.sls_case == "rare" else psi1.get(action, 0.0) * value
            else:
                total += psi0.get(action, 0.0) * value if request.loads.sls_case == "rare" else psi2.get(action, 0.0) * value
        return total

    def best_lead_for_uls() -> str:
        best = candidates[0] if candidates else "live"
        best_moment = -math.inf
        for lead in candidates or ["live"]:
            effects = max_effects(span_m, uls_line_load(lead), scale_point_loads(point_loads_raw, factors_uls(lead)))
            if effects.Mmax_kNm > best_moment:
                best_moment = effects.Mmax_kNm
                best = lead
        return best

    def best_lead_for_sls() -> str:
        if request.loads.sls_case == "qp":
            return "live"
        best = candidates[0] if candidates else "live"
        best_deflection = -math.inf
        for lead in candidates or ["live"]:
            effects = max_effects(
                span_m,
                sls_line_load(lead),
                scale_point_loads(point_loads_raw, factors_sls(lead)),
                E_N_mm2,
                I_mm4,
            )
            if effects.dmax_mm > best_deflection:
                best_deflection = effects.dmax_mm
                best = lead
        return best

    lead_uls = best_lead_for_uls() if request.loads.lead_action == "auto" else request.loads.lead_action
    lead_sls = best_lead_for_sls() if request.loads.lead_action == "auto" else request.loads.lead_action

    support_reaction_breakdown = {
        "dead": {
            "w_kN_m": Gtot,
            "point_loads": [asdict(load) for load in scale_point_loads(point_loads_raw, {"G": 1.0, "g": 1.0})],
        },
        "live": {
            "w_kN_m": variable_loads.get("live", 0.0),
            "point_loads": [asdict(load) for load in scale_point_loads(point_loads_raw, {"live": 1.0})],
        },
    }

    return BeamLoadSetup(
        span_m=span_m,
        span_mm=span_mm,
        axis=request.geometry.axis,
        E_N_mm2=E_N_mm2,
        fy_MPa=fy_MPa,
        gamma_M0=gamma_M0,
        deflection_limit_ratio=request.geometry.deflection_limit_ratio,
        axial_NEd_kN=request.design.axial_NEd_kN,
        section_class=section_class,
        section_props=section_props,
        I_mm4=I_mm4,
        w_ULS_kN_m=uls_line_load(lead_uls),
        w_SLS_kN_m=sls_line_load(lead_sls),
        point_loads_ULS=scale_point_loads(point_loads_raw, factors_uls(lead_uls)),
        point_loads_SLS=scale_point_loads(point_loads_raw, factors_sls(lead_sls)),
        support_reaction_breakdown=support_reaction_breakdown,
        automatic_takedown=automatic_takedown,
        governing_uls=f"ULS lead {lead_uls}",
        governing_sls=f"SLS {request.loads.sls_case} lead {lead_sls}",
        warnings=warnings,
    )


def _evaluate_profile(
    profile: dict,
    request: SteelBeamRequest,
    setup: BeamLoadSetup | None = None,
    include_detail: bool = False,
) -> dict | None:
    setup = setup or _build_load_setup(request, profile)
    section_props = setup.section_props
    if not (section_props.I_cm4 > 0.0 and section_props.Wuse_cm3 > 0.0):
        return None

    effects_uls = max_effects(setup.span_m, setup.w_ULS_kN_m, setup.point_loads_ULS)
    effects_sls = max_effects(
        setup.span_m,
        setup.w_SLS_kN_m,
        setup.point_loads_SLS,
        setup.E_N_mm2,
        setup.I_mm4,
    )

    A_cm2 = area_cm2(profile)
    NRd_kN = axial_resistance_kN(A_cm2, setup.fy_MPa, setup.gamma_M0)
    shear_area_cm2 = (
        request.design.shear_area_override_cm2
        if request.design.shear_area_override_cm2 is not None
        else section_props.Avz_cm2
    )
    VRd_kN = shear_resistance_kN(shear_area_cm2 or 0.0, setup.fy_MPa, setup.gamma_M0)
    MRd_raw_kNm = bending_resistance_kNm(section_props.Wuse_cm3, setup.fy_MPa, setup.gamma_M0)
    MRd_kNm = MRd_raw_kNm
    high_shear_rho = 0.0
    warnings = list(setup.warnings)

    if request.design.reduce_bending_for_high_shear:
        MRd_kNm, high_shear_rho = high_shear_reduced_bending_kNm(MRd_raw_kNm, effects_uls.Vmax_kN, VRd_kN)
        if high_shear_rho > 0.0:
            warnings.append("High shear present: MRd reduced using the simplified EC3 shear interaction model.")

    util_M = effects_uls.Mmax_kNm / MRd_kNm if MRd_kNm > 0.0 else math.inf
    util_V = effects_uls.Vmax_kN / VRd_kN if VRd_kN > 0.0 else math.inf
    util_N = abs(setup.axial_NEd_kN) / NRd_kN if NRd_kN > 0.0 else math.inf
    util_NM = (
        setup.axial_NEd_kN / NRd_kN + effects_uls.Mmax_kNm / MRd_kNm
        if setup.axial_NEd_kN > 0.0 and NRd_kN > 0.0 and MRd_kNm > 0.0
        else util_M
    )

    ltb_result = None
    util_LTB = 0.0
    if request.design.ltb.enabled:
        if setup.axis != "major":
            warnings.append("LTB is implemented only for major-axis bending.")
        else:
            ltb_result = ltb_check(
                profile=profile,
                section_props=section_props,
                MEd_kNm=effects_uls.Mmax_kNm,
                fy_MPa=setup.fy_MPa,
                E_N_mm2=setup.E_N_mm2,
                unrestrained_length_m=request.design.ltb.unrestrained_length_m,
                C1=request.design.ltb.C1,
                alpha_LT=request.design.ltb.alpha_LT,
                gamma_M1=request.design.ltb.gamma_M1,
                lambda_LT0=request.design.ltb.lambda_LT0,
                beta_LT=request.design.ltb.beta_LT,
                poisson_ratio=request.design.ltb.poisson_ratio,
            )
            if ltb_result is None:
                warnings.append("Missing LTB inputs or torsion properties; LTB skipped.")
            else:
                util_LTB = ltb_result["utilization"]
                warnings.append("LTB uses a simplified Mcr plus chi_LT model.")

    delta_allow_mm = setup.span_mm / setup.deflection_limit_ratio
    util_D = effects_sls.dmax_mm / delta_allow_mm if delta_allow_mm > 0.0 else math.inf
    control_util = max(util_N, util_NM, util_M, util_V, util_LTB or 0.0)
    governing = max(control_util, util_D)
    pass_checks = (
        util_M <= 1.0
        and util_V <= 1.0
        and util_D <= 1.0
        and util_N <= 1.0
        and util_NM <= 1.0
        and util_LTB <= 1.0
        and setup.section_class.overall != 4
    )

    def add_warning(message: str) -> None:
        if message not in warnings:
            warnings.append(message)

    if util_D > 1.0:
        add_warning("Deflection limit exceeded.")
    if governing > 0.90:
        add_warning("High utilization ratio.")
    if request.design.ltb.enabled and 0.90 <= util_LTB <= 1.0:
        add_warning("LTB check approaching limit.")

    if not (shear_area_cm2 and shear_area_cm2 > 0.0):
        add_warning("Shear area Av is not available; provide Av override.")
    if setup.axis == "minor":
        add_warning("Minor-axis bending selected: Avz may not match the real shear direction.")
    if setup.section_class.overall == 4:
        add_warning("Class 4 section: effective section properties are not implemented.")
    if setup.axial_NEd_kN > 0.0:
        add_warning("Beam axial compression check is section-only; member buckling is not included in beam mode.")
    if util_M + util_V > 1.0:
        add_warning("Simple M + V interaction exceeds 1.0.")

    item = {
        "profile": profile,
        "pass": pass_checks,
        "governing": governing,
        "controlUtil": control_util,
        "utilD": util_D,
        "delta_max_mm": effects_sls.dmax_mm,
        "delta_allow_mm": delta_allow_mm,
        "weight": profile.get("g") or math.inf,
        "MEd_kNm": effects_uls.Mmax_kNm,
        "VEd_kN": effects_uls.Vmax_kN,
    }
    selected_support_width_fit = _best_support_width_fit(item, request.design.effective_support_width_cm)
    if selected_support_width_fit:
        item["support_width_fit"] = selected_support_width_fit
    if not include_detail:
        return item

    fails = []
    if util_N > 1.0:
        fails.append("Axial capacity exceeded")
    if util_NM > 1.0:
        fails.append("Combined N + M exceeded")
    if util_M > 1.0:
        fails.append("Bending capacity exceeded")
    if util_V > 1.0:
        fails.append("Shear capacity exceeded")
    if request.design.ltb.enabled and util_LTB > 1.0:
        fails.append("LTB capacity exceeded")
    if util_D > 1.0:
        fails.append("Deflection limit exceeded")
    if setup.section_class.overall == 4:
        fails.append("Class 4 not implemented")

    support_width_warning = bool(request.design.effective_support_width_cm and not selected_support_width_fit)
    if support_width_warning:
        add_warning("Selected section does not satisfy the support-width fit rule used by the backend recommendation engine.")

    status_kind = "ok"
    status_text = "OK"
    if fails:
        status_kind = "bad"
        status_text = fails[0]
    elif support_width_warning:
        status_kind = "warn"
        status_text = "Support width fit warning"
    elif max(util_N, util_NM, util_V, util_M + util_V, util_LTB or 0.0) > 0.90:
        status_kind = "warn"
        status_text = "High utilization"

    load_takedown = _automatic_takedown_payload(setup.automatic_takedown)
    plots = build_simply_supported_beam_plots(
        span_m=setup.span_m,
        span_mm=setup.span_mm,
        w_uls_kN_m=setup.w_ULS_kN_m,
        w_sls_kN_m=setup.w_SLS_kN_m,
        point_loads_uls=setup.point_loads_ULS,
        point_loads_sls=setup.point_loads_SLS,
        reaction_left_uls_kN=effects_uls.RA_kN,
        E_N_mm2=setup.E_N_mm2,
        I_mm4=setup.I_mm4,
        governing_uls=setup.governing_uls,
        governing_sls=setup.governing_sls,
        effects_uls=effects_uls,
        effects_sls=effects_sls,
    )

    item["detail"] = {
        "MEd": effects_uls.Mmax_kNm,
        "VEd": effects_uls.Vmax_kN,
        "delta": effects_sls.dmax_mm,
        "utilization": control_util,
        "status": status_text,
        "status_kind": status_kind,
        "failures": fails,
        "governing_combination": f"{setup.governing_uls}; {setup.governing_sls}",
        "auto_load_breakdown": load_takedown,
        "auto_dead_load_kN_m": load_takedown["auto_dead_load_kN_m"],
        "auto_live_load_kN_m": load_takedown["auto_live_load_kN_m"],
        "floor_contribution_kN_m": load_takedown["floor_contribution_kN_m"],
        "wall_contribution_kN_m": load_takedown["wall_contribution_kN_m"],
        "reactions": {
            "left_kN": effects_uls.RA_kN,
            "right_kN": effects_uls.RB_kN,
            "dead": _display_support_reaction(setup.support_reaction_breakdown, "dead", setup.span_m),
            "live": _display_support_reaction(setup.support_reaction_breakdown, "live", setup.span_m),
        },
        "section": {
            "name": profile.get("n"),
            "height_mm": profile.get("h"),
            "width_mm": profile.get("b"),
            "class": _section_class_payload(setup.section_class),
            "Wuse_cm3": section_props.Wuse_cm3,
            "Wuse_kind": section_props.Wuse_kind,
            "weight_kg_m": section_props.weight_kg_m,
        },
        "loads": {
            "w_ULS_kN_m": setup.w_ULS_kN_m,
            "w_SLS_kN_m": setup.w_SLS_kN_m,
            "automatic_takedown": load_takedown,
        },
        "plots": plots,
        "effects": {
            "MEd_kNm": effects_uls.Mmax_kNm,
            "VEd_kN": effects_uls.Vmax_kN,
            "RA_kN": effects_uls.RA_kN,
            "RB_kN": effects_uls.RB_kN,
            "dead_reactions": _display_support_reaction(setup.support_reaction_breakdown, "dead", setup.span_m),
            "live_reactions": _display_support_reaction(setup.support_reaction_breakdown, "live", setup.span_m),
        },
        "resistance": {
            "NEd_kN": setup.axial_NEd_kN,
            "NRd_kN": NRd_kN,
            "MRd_kNm": MRd_kNm,
            "MRd_raw_kNm": MRd_raw_kNm,
            "VRd_kN": VRd_kN,
            "high_shear_rho": high_shear_rho,
        },
        "utilization_detail": {
            "M": util_M,
            "V": util_V,
            "M_plus_V": util_M + util_V,
            "N": util_N,
            "N_plus_M": util_NM,
            "LTB": util_LTB if request.design.ltb.enabled else None,
            "deflection": util_D,
            "control": control_util,
        },
        "deflection": {
            "delta_max_mm": effects_sls.dmax_mm,
            "delta_allow_mm": delta_allow_mm,
        },
        "ltb": ltb_result,
        # Slof is computed independently per support: each side uses its own support
        # width with the governing reaction. The governing reaction is the same
        # max(|RA|, |RB|) used previously, so reinforcement values are unchanged.
        "support_bearing": _beam_slof_from_support_reaction(
            max(abs(effects_uls.RA_kN), abs(effects_uls.RB_kN)),
            request.design.left_width_cm,
        ),
        "support_bearing_left": _beam_slof_from_support_reaction(
            max(abs(effects_uls.RA_kN), abs(effects_uls.RB_kN)),
            request.design.left_width_cm,
        ),
        "support_bearing_right": _beam_slof_from_support_reaction(
            max(abs(effects_uls.RA_kN), abs(effects_uls.RB_kN)),
            request.design.right_width_cm,
        ),
        "support_width_fit": selected_support_width_fit
        or _support_width_miss_payload(item, request.design.effective_support_width_cm),
        "status_detail": {
            "kind": status_kind,
            "text": status_text,
            "failures": fails,
        },
        "warnings": warnings,
    }
    return item


def _line_loads_by_type(request: SteelBeamRequest) -> dict[str, float]:
    loads = {"G": 0.0, "live": 0.0, "wind": 0.0, "snow": 0.0}
    for row in request.loads.line_loads:
        loads[row.type] += row.w_kN_m
    return loads


def _read_point_loads(request: SteelBeamRequest, warnings: list[str]) -> list[dict]:
    out = []
    for load in request.loads.point_loads:
        if abs(load.P_kN) < 1e-12:
            continue
        if load.a_m < 0.0 or load.a_m > request.geometry.span_m:
            raise ValueError("Point load position az must be within 0 to L.")
        if load.P_kN < 0.0:
            warnings.append("One or more point loads are negative (uplift).")
        out.append({"P_kN": load.P_kN, "a_m": load.a_m, "type": load.type})
    return out


def _candidate_lead_actions(variable_loads: dict[str, float], point_loads: list[dict]) -> list[str]:
    point_presence = {action: False for action in ACTIONS}
    for load in point_loads:
        action = str(load.get("type", "")).lower()
        if action in point_presence:
            point_presence[action] = True
    return [
        action
        for action in ACTIONS
        if abs(variable_loads.get(action, 0.0)) > 1e-12 or point_presence[action]
    ]


def _section_class_payload(section_class: SectionClass) -> dict:
    return {
        "eps": section_class.eps,
        "flange": section_class.flange_class,
        "web": section_class.web_class,
        "overall": section_class.overall,
        "c_over_t": section_class.c_over_t,
        "d_over_t": section_class.d_over_t,
    }


def _display_support_reaction(breakdown: dict | None, key: str, span_m: float) -> dict | None:
    if not breakdown or key not in breakdown:
        return None
    part = breakdown[key]
    w_kN_m = float(part.get("w_kN_m", 0.0) or 0.0)
    point_sum = sum(float(load.get("P_kN", 0.0) or 0.0) for load in part.get("point_loads", []))
    reaction = w_kN_m * (span_m / 2.0) + point_sum
    return {"RA_kN": reaction, "RB_kN": reaction}


def _beam_slof_from_support_reaction(reaction_kN: float, support_width_cm: float | None) -> dict:
    width_cm = support_width_cm if support_width_cm and support_width_cm > 0.0 else 14.0
    gamma = 1.35
    concrete_stress = 10.0
    steel_stress = 3.0
    reaction = max(0.0, reaction_kN)
    return {
        "width_cm": width_cm,
        "length_cm": reaction * 100.0 / (concrete_stress * width_cm * gamma),
        "reinforcement_mid_cm2": reaction / (concrete_stress * gamma * steel_stress * 2.0),
        "reinforcement_head_cm2": reaction / (concrete_stress * gamma * steel_stress),
    }


def _automatic_takedown_payload(takedown: LoadTakedownResult | None) -> dict:
    if takedown is None:
        enabled = False
        floor_dead = floor_live = wall = dead = live = 0.0
    else:
        enabled = takedown.enabled
        floor_dead = takedown.floor_dead_kN_m
        floor_live = takedown.floor_live_kN_m
        wall = takedown.wall_kN_m
        dead = takedown.dead_kN_m
        live = takedown.live_kN_m

    return {
        "enabled": enabled,
        "auto_dead_load_kN_m": dead,
        "auto_live_load_kN_m": live,
        "floor_contribution_kN_m": floor_dead,
        "wall_contribution_kN_m": wall,
        "floor_dead_kN_m": floor_dead,
        "floor_live_kN_m": floor_live,
        "wall_kN_m": wall,
        "dead_kN_m": dead,
        "live_kN_m": live,
    }


def _recommend_sections(request: SteelBeamRequest) -> tuple[list[dict], list[dict], list[dict]]:
    recommendations: list[dict] = []
    support_width_candidates: list[dict] = []
    rejected_sections: list[dict] = []
    support_width_cm = request.design.effective_support_width_cm

    for profile in load_profiles():
        profile_name = profile.get("n", "")
        if group_family(profile.get("n", "")) == "BOX":
            rejected_sections.append({"section": profile_name, "reason": "Box sections are excluded from beam recommendations."})
            continue

        item = _evaluate_profile(profile, request, include_detail=False)
        if item is None:
            rejected_sections.append({"section": profile_name, "reason": "Incomplete section geometry or properties."})
            continue
        if not item["pass"]:
            rejected_sections.append(
                {
                    "section": profile_name,
                    "reason": "Fails strength, stability, section-class or deflection checks.",
                    "governing": item.get("governing"),
                    "utilization": item.get("controlUtil"),
                    "deflection_utilization": item.get("utilD"),
                }
            )
            continue

        width_candidates = _support_width_fit_candidates(item, support_width_cm)
        if support_width_cm and not width_candidates:
            rejected_sections.append(
                {
                    "section": profile_name,
                    "reason": "No single/twin section support-width fit within the 0-30 mm support gap rule.",
                    "support_width_cm": support_width_cm,
                    "section_width_mm": profile.get("b"),
                }
            )
            continue

        if width_candidates:
            item["support_width_fit"] = width_candidates[0]
            support_width_candidates.extend(width_candidates)

        recommendations.append(item)

    if support_width_cm:
        recommendations.sort(key=_support_width_item_sort_key)
    else:
        recommendations.sort(key=beam_recommendation_sort_key)
    support_width_candidates.sort(key=_support_width_candidate_sort_key)

    print(
        "[steel-beam] recommendation structures before return:",
        {
            "passing_count": len(recommendations),
            "support_width_candidate_count": len(support_width_candidates),
            "rejected_count": len(rejected_sections),
            "support_width_cm": support_width_cm,
        },
    )
    return recommendations, support_width_candidates, rejected_sections


def _recommendation_payload(items: list[dict]) -> list[dict]:
    return [
        {
            "section": item["profile"].get("n"),
            "family": group_family(item["profile"].get("n", "")),
            "weight_kg_m": item.get("weight"),
            "utilization": item.get("controlUtil"),
            "governing": item.get("governing"),
            "delta_mm": item.get("delta_max_mm"),
            "delta_allow_mm": item.get("delta_allow_mm"),
            "MEd_kNm": item.get("MEd_kNm"),
            "VEd_kN": item.get("VEd_kN"),
            "support_width_fit": item.get("support_width_fit"),
        }
        for item in items
    ]


def _support_width_fit_candidates(item: dict, support_width_cm: float | None) -> list[dict]:
    if support_width_cm is None or support_width_cm <= 0.0:
        return []

    profile = item.get("profile") or {}
    family = group_family(profile.get("n", ""))
    if family not in SUPPORT_WIDTH_ALLOWED_FAMILIES:
        return []

    target_width_mm = support_width_cm * 10.0
    section_width_mm = float(profile.get("b") or 0.0)
    section_weight = float(profile.get("g") or math.inf)
    control_util = float(item.get("controlUtil") or math.inf)
    delta_mm = float(item.get("delta_max_mm") or math.inf)
    delta_allow_mm = float(item.get("delta_allow_mm") or math.inf)
    if not (
        target_width_mm > 0.0
        and section_width_mm > 0.0
        and math.isfinite(section_weight)
        and math.isfinite(control_util)
        and math.isfinite(delta_mm)
        and math.isfinite(delta_allow_mm)
        and delta_allow_mm > 0.0
    ):
        return []

    candidates = []
    for multiplier in (1, 2):
        total_width_mm = section_width_mm * multiplier
        remaining_gap_mm = target_width_mm - total_width_mm
        if remaining_gap_mm < 0.0 or remaining_gap_mm > SUPPORT_WIDTH_GAP_LIMIT_MM:
            continue

        # Twin members are ranked with half the demand per section, matching the legacy support-width workflow.
        share_factor = 0.5 if multiplier == 2 else 1.0
        candidate_control = control_util * share_factor
        candidate_delta = delta_mm * share_factor
        if candidate_control > 1.0 or candidate_delta > delta_allow_mm:
            continue

        section_name = profile.get("n")
        label = f"2x {section_name}" if multiplier == 2 else section_name
        candidates.append(
            {
                "key": f"{section_name}__{multiplier}",
                "section": section_name,
                "section_name": section_name,
                "label": label,
                "family": family,
                "multiplier": multiplier,
                "type": "twin" if multiplier == 2 else "single",
                "type_text": "Twin section" if multiplier == 2 else "Single section",
                "target_width_mm": target_width_mm,
                "section_width_mm": section_width_mm,
                "total_width_mm": total_width_mm,
                "remaining_gap_mm": remaining_gap_mm,
                "gap_limit_mm": SUPPORT_WIDTH_GAP_LIMIT_MM,
                "weight_kg_m": section_weight * multiplier,
                "utilization": candidate_control,
                "delta_mm": candidate_delta,
                "delta_allow_mm": delta_allow_mm,
                "MEd_kNm": item.get("MEd_kNm"),
                "VEd_kN": item.get("VEd_kN"),
                "reasoning": (
                    f"{'Twin' if multiplier == 2 else 'Single'} section fits "
                    f"{target_width_mm:.0f} mm support width with {remaining_gap_mm:.0f} mm gap."
                ),
            }
        )
    candidates.sort(key=_support_width_candidate_sort_key)
    return candidates


def _best_support_width_fit(item: dict, support_width_cm: float | None) -> dict | None:
    candidates = _support_width_fit_candidates(item, support_width_cm)
    return candidates[0] if candidates else None


def _support_width_miss_payload(item: dict, support_width_cm: float | None) -> dict | None:
    if support_width_cm is None or support_width_cm <= 0.0:
        return None
    profile = item.get("profile") or {}
    return {
        "fits": False,
        "support_width_cm": support_width_cm,
        "target_width_mm": support_width_cm * 10.0,
        "section_width_mm": profile.get("b"),
        "gap_limit_mm": SUPPORT_WIDTH_GAP_LIMIT_MM,
        "reason": "No single/twin support-width fit within the backend 0-30 mm gap rule.",
    }


def _support_width_candidate_sort_key(candidate: dict) -> tuple:
    family = candidate.get("family", "")
    return (
        candidate.get("remaining_gap_mm", math.inf),
        SUPPORT_WIDTH_FAMILY_ORDER.get(family, 99),
        candidate.get("weight_kg_m", math.inf),
        candidate.get("total_width_mm", math.inf),
        candidate.get("label", ""),
    )


def _support_width_item_sort_key(item: dict) -> tuple:
    fit = item.get("support_width_fit") or {}
    return (
        fit.get("remaining_gap_mm", math.inf),
        SUPPORT_WIDTH_FAMILY_ORDER.get(fit.get("family", ""), 99),
        fit.get("weight_kg_m", item.get("weight", math.inf)),
        item.get("governing", math.inf),
        item["profile"].get("n", ""),
    )


def _support_width_recommendation_payload(items: list[dict]) -> list[dict]:
    return [
        {
            "section": item.get("section"),
            "section_name": item.get("section_name"),
            "label": item.get("label"),
            "family": item.get("family"),
            "multiplier": item.get("multiplier"),
            "type": item.get("type"),
            "type_text": item.get("type_text"),
            "target_width_mm": item.get("target_width_mm"),
            "section_width_mm": item.get("section_width_mm"),
            "total_width_mm": item.get("total_width_mm"),
            "remaining_gap_mm": item.get("remaining_gap_mm"),
            "gap_limit_mm": item.get("gap_limit_mm"),
            "weight_kg_m": item.get("weight_kg_m"),
            "utilization": item.get("utilization"),
            "delta_mm": item.get("delta_mm"),
            "delta_allow_mm": item.get("delta_allow_mm"),
            "MEd_kNm": item.get("MEd_kNm"),
            "VEd_kN": item.get("VEd_kN"),
            "reasoning": item.get("reasoning"),
        }
        for item in items
    ]


def _support_width_recommendation_status(
    support_width_cm: float | None,
    recommendations: list[dict],
) -> dict:
    if support_width_cm is None or support_width_cm <= 0.0:
        return {
            "state": "empty",
            "message": "Enter supporting width (cm). Allowed wall/support gap = 0-30 mm.",
        }
    if recommendations:
        return {
            "state": "ok",
            "message": "Support-width recommendations are ranked by gap, family preference and weight.",
        }
    return {
        "state": "none",
        "message": "No width-fit passing section found. Allowed wall/support gap = 0-30 mm.",
    }


def _validate_recommendation_contract(value: object) -> tuple[list[dict], list[dict], list[dict]]:
    if not isinstance(value, tuple) or len(value) != 3:
        length = len(value) if hasattr(value, "__len__") else "unknown"
        raise ValueError(
            "Internal steel recommendation contract mismatch: expected "
            f"(recommendations, support_width_candidates, rejected_sections), got {type(value).__name__} length {length}."
        )
    recommendations, support_width_candidates, rejected_sections = value
    print(
        "[steel-beam] recommendation unpack targets:",
        {
            "recommendations": {"type": type(recommendations).__name__, "length": len(recommendations)},
            "support_width_candidates": {
                "type": type(support_width_candidates).__name__,
                "length": len(support_width_candidates),
            },
            "rejected_sections": {"type": type(rejected_sections).__name__, "length": len(rejected_sections)},
        },
    )
    if not all(isinstance(item, list) for item in value):
        raise ValueError("Internal steel recommendation contract mismatch: all recommendation outputs must be lists.")
    return recommendations, support_width_candidates, rejected_sections


def _validate_result_structure(detail: dict) -> list[str]:
    warnings = []
    checks = {
        "recommendations": list,
        "support_width_recommendations": list,
        "auto_load_breakdown": dict,
        "loads": dict,
        "plots": dict,
        "reactions": dict,
        "utilization_detail": dict,
    }
    for key, expected_type in checks.items():
        value = detail.get(key)
        print(
            "[steel-beam] response field check:",
            {
                "field": key,
                "type": type(value).__name__,
                "length": len(value) if hasattr(value, "__len__") else None,
            },
        )
        if not isinstance(value, expected_type):
            warnings.append(f"Backend response field '{key}' was not in the expected structure.")
    warnings.extend(validate_beam_plot_payload(detail.get("plots")))
    return warnings
