ACTIONS = ("live", "wind", "snow")


def variable_action_factors(
    lead_action: str,
    gamma_Q: float,
    psi0: dict[str, float],
) -> dict[str, float]:
    factors = {"G": 0.0, "live": 0.0, "wind": 0.0, "snow": 0.0}
    for action in ACTIONS:
        factors[action] = gamma_Q * (1.0 if action == lead_action else psi0.get(action, 0.0))
    return factors
