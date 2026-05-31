from __future__ import annotations


REQUIRED_BEAM_PLOT_SERIES = ("x", "shear", "moment", "deflection")


def validate_beam_plot_payload(plots: object) -> list[str]:
    """Validate the response contract used by frontend steel-beam diagrams."""
    warnings: list[str] = []
    if not isinstance(plots, dict):
        return ["Backend response field 'plots' was not in the expected structure."]

    lengths: dict[str, int] = {}
    for key in REQUIRED_BEAM_PLOT_SERIES:
        value = plots.get(key)
        if not isinstance(value, list):
            warnings.append(f"Backend plot field '{key}' was not a list.")
            continue
        lengths[key] = len(value)

    if lengths:
        unique_lengths = set(lengths.values())
        if len(unique_lengths) != 1:
            warnings.append("Backend plot arrays have mismatched lengths.")
        elif next(iter(unique_lengths)) < 2:
            warnings.append("Backend plot arrays do not contain enough stations.")

    if not isinstance(plots.get("meta"), dict):
        warnings.append("Backend plot metadata was not in the expected structure.")
    if not isinstance(plots.get("markers"), dict):
        warnings.append("Backend plot markers were not in the expected structure.")
    return warnings

