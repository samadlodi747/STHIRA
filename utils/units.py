GRAVITY_M_S2 = 9.81


def steel_self_weight_kN_m(weight_kg_m: float) -> float:
    """Convert profile mass per metre to characteristic line load."""
    return (weight_kg_m or 0.0) * GRAVITY_M_S2 / 1000.0


def cm2_to_mm2(value_cm2: float) -> float:
    return value_cm2 * 100.0


def cm3_to_mm3(value_cm3: float) -> float:
    return value_cm3 * 1000.0


def cm4_to_mm4(value_cm4: float) -> float:
    return value_cm4 * 10000.0
