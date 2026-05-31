from dataclasses import dataclass
import math

from utils.units import cm2_to_mm2, cm3_to_mm3


@dataclass(frozen=True)
class SectionClass:
    eps: float
    flange_class: int | None
    web_class: int | None
    overall: int | None
    c_over_t: float | None
    d_over_t: float | None


@dataclass(frozen=True)
class SectionProps:
    I_cm4: float
    Wel_cm3: float
    Wpl_cm3: float
    Wuse_cm3: float
    Wuse_kind: str
    Avz_cm2: float
    It_cm4: float
    Iw_value: float
    weight_kg_m: float


def _class_from_limit(value: float | None, limit_1: float, limit_2: float, limit_3: float) -> int | None:
    if value is None or value < 0:
        return None
    if value <= limit_1:
        return 1
    if value <= limit_2:
        return 2
    if value <= limit_3:
        return 3
    return 4


def compute_bending_class(profile: dict, fy_MPa: float) -> SectionClass:
    eps = math.sqrt(235.0 / fy_MPa)
    tw = float(profile.get("tw", 0.0) or 0.0)
    tf = float(profile.get("tf", 0.0) or 0.0)
    radius = float(profile.get("r", 0.0) or 0.0)
    width = float(profile.get("b", 0.0) or 0.0)
    depth_clear = float(profile.get("d", 0.0) or 0.0)
    inner_height = float(profile.get("hi", 0.0) or 0.0)

    if not (tw > 0.0 and tf > 0.0 and width > 0.0):
        return SectionClass(eps, None, None, None, None, None)

    flange_outstand = max(0.0, (width - tw) / 2.0 - radius)
    web_clear = depth_clear if depth_clear > 0.0 else max(0.0, inner_height - 2.0 * radius)
    c_over_t = flange_outstand / tf
    d_over_t = web_clear / tw

    flange_class = _class_from_limit(c_over_t, 9.0 * eps, 10.0 * eps, 14.0 * eps)
    web_class = _class_from_limit(d_over_t, 72.0 * eps, 83.0 * eps, 124.0 * eps)
    overall = max(flange_class or 4, web_class or 4)
    return SectionClass(eps, flange_class, web_class, overall, c_over_t, d_over_t)


def get_section_props(axis: str, profile: dict, section_class: SectionClass) -> SectionProps:
    I_cm4 = float(profile.get("Iy" if axis == "major" else "Iz", 0.0) or 0.0)
    Wel_cm3 = float(profile.get("Wy" if axis == "major" else "Wz", 0.0) or 0.0)
    Wpl_cm3 = float(profile.get("Wpl_y" if axis == "major" else "Wpl_z", 0.0) or 0.0)

    Wuse_cm3 = Wel_cm3
    Wuse_kind = "Wel"
    if section_class.overall is not None and section_class.overall <= 2 and Wpl_cm3 > 0.0:
        Wuse_cm3 = Wpl_cm3
        Wuse_kind = "Wpl"

    return SectionProps(
        I_cm4=I_cm4,
        Wel_cm3=Wel_cm3,
        Wpl_cm3=Wpl_cm3,
        Wuse_cm3=Wuse_cm3,
        Wuse_kind=Wuse_kind,
        Avz_cm2=float(profile.get("Avz", 0.0) or 0.0),
        It_cm4=float(profile.get("It", 0.0) or 0.0),
        Iw_value=float(profile.get("Iw", 0.0) or 0.0),
        weight_kg_m=float(profile.get("g", 0.0) or 0.0),
    )


def area_cm2(profile: dict) -> float:
    for key in ("A", "a", "Ag"):
        value = float(profile.get(key, 0.0) or 0.0)
        if value > 0.0:
            return value
    weight = float(profile.get("g", 0.0) or 0.0)
    return weight / 0.785 if weight > 0.0 else 0.0


def axial_resistance_kN(area_cm2_value: float, fy_MPa: float, gamma_M0: float) -> float:
    area_mm2 = cm2_to_mm2(area_cm2_value)
    return area_mm2 * fy_MPa / gamma_M0 / 1000.0 if area_mm2 > 0.0 else 0.0


def shear_resistance_kN(shear_area_cm2: float, fy_MPa: float, gamma_M0: float) -> float:
    area_mm2 = cm2_to_mm2(shear_area_cm2)
    return area_mm2 * fy_MPa / (math.sqrt(3.0) * gamma_M0) / 1000.0 if area_mm2 > 0.0 else 0.0


def bending_resistance_kNm(W_cm3: float, fy_MPa: float, gamma_M0: float) -> float:
    return cm3_to_mm3(W_cm3) * fy_MPa / gamma_M0 / 1_000_000.0 if W_cm3 > 0.0 else 0.0


def high_shear_reduced_bending_kNm(MRd_kNm: float, VEd_kN: float, VRd_kN: float) -> tuple[float, float]:
    if VRd_kN <= 0.0 or VEd_kN <= 0.5 * VRd_kN:
        return MRd_kNm, 0.0
    rho = (2.0 * VEd_kN / VRd_kN - 1.0) ** 2
    return MRd_kNm * max(0.0, 1.0 - rho), rho


def ltb_check(
    profile: dict,
    section_props: SectionProps,
    MEd_kNm: float,
    fy_MPa: float,
    E_N_mm2: float,
    unrestrained_length_m: float,
    C1: float,
    alpha_LT: float,
    gamma_M1: float,
    lambda_LT0: float,
    beta_LT: float,
    poisson_ratio: float,
) -> dict | None:
    Iz_mm4 = float(profile.get("Iz", 0.0) or 0.0) * 10000.0
    It_mm4 = float(profile.get("It", 0.0) or 0.0) * 10000.0
    # The legacy profile library stores Iw in the same scaled value used by the original app.
    Iw_mm6 = float(profile.get("Iw", 0.0) or 0.0) * 1000.0
    W_mm3 = cm3_to_mm3(section_props.Wuse_cm3)

    if not (
        unrestrained_length_m > 0.0
        and C1 > 0.0
        and gamma_M1 > 0.0
        and Iz_mm4 > 0.0
        and It_mm4 > 0.0
        and Iw_mm6 > 0.0
        and W_mm3 > 0.0
    ):
        return None

    G_N_mm2 = E_N_mm2 / (2.0 * (1.0 + poisson_ratio))
    Lb_mm = unrestrained_length_m * 1000.0
    term = Iw_mm6 / Iz_mm4 + (Lb_mm**2 * G_N_mm2 * It_mm4) / (math.pi**2 * E_N_mm2 * Iz_mm4)
    Mcr_Nmm = C1 * (math.pi**2 * E_N_mm2 * Iz_mm4 / Lb_mm**2) * math.sqrt(max(0.0, term))
    if Mcr_Nmm <= 0.0:
        return None

    lambda_LT = math.sqrt((W_mm3 * fy_MPa) / Mcr_Nmm)
    chi_LT = 1.0
    if lambda_LT > lambda_LT0:
        phi_LT = 0.5 * (1.0 + alpha_LT * (lambda_LT - lambda_LT0) + beta_LT * lambda_LT**2)
        discriminant = max(0.0, phi_LT**2 - beta_LT * lambda_LT**2)
        chi_LT = min(1.0, 1.0 / (phi_LT + math.sqrt(discriminant)))

    MbRd_kNm = chi_LT * W_mm3 * fy_MPa / gamma_M1 / 1_000_000.0
    return {
        "Mcr_kNm": Mcr_Nmm / 1_000_000.0,
        "chi_LT": chi_LT,
        "MbRd_kNm": MbRd_kNm,
        "utilization": MEd_kNm / MbRd_kNm if MbRd_kNm > 0.0 else math.inf,
    }
