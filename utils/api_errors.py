from __future__ import annotations

from typing import Any


def api_response(
    *,
    success: bool,
    results: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
    errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "success": success,
        "results": results or {},
        "warnings": warnings or [],
        "errors": errors or [],
    }


def friendly_validation_errors(raw_errors: list[dict[str, Any]]) -> list[str]:
    messages: list[str] = []
    for error in raw_errors:
        messages.append(_friendly_validation_error(error))
    return _dedupe(messages)


def friendly_engineering_error(message: str) -> str:
    lower = message.lower()
    if "unknown steel profile" in lower:
        return "Selected steel section is not available in the backend profile library."
    if "point load position" in lower:
        return "Point load position must lie within the beam span."
    if "incomplete geometry" in lower or "section properties" in lower:
        if "column" in lower:
            return "Selected section has incomplete geometry or section properties for steel column design."
        return "Selected section has incomplete geometry or section properties for steel beam design."
    if "profile_name" in lower:
        return "Select a valid steel section."
    return message or "Steel beam calculation could not be completed."


def friendly_http_error(detail: Any, status_code: int) -> str:
    if status_code == 404:
        return "Requested API endpoint was not found."
    if isinstance(detail, str) and detail.strip():
        if status_code == 501:
            return detail.strip()
        return _hide_framework_detail(detail.strip(), status_code)
    if status_code >= 500:
        return "The calculation service encountered a backend error."
    return "The API request could not be completed."


def _friendly_validation_error(error: dict[str, Any]) -> str:
    loc = [str(part) for part in error.get("loc", []) if str(part) != "body"]
    normalized = ".".join(part for part in loc if not part.isdigit())
    message_type = str(error.get("type", ""))

    if normalized == "profile_name":
        return "Select a valid steel section."
    if normalized == "geometry.span_m":
        return "Span must be greater than zero."
    if normalized == "geometry.length_m":
        return "Column length must be greater than zero."
    if normalized in {"geometry.buckling_length_y_m", "geometry.buckling_length_z_m"}:
        return "Column buckling lengths must be greater than zero."
    if normalized == "geometry.ltb_length_m":
        return "Column LTB length cannot be negative."
    if normalized == "geometry.deflection_limit_ratio":
        return "Deflection limit ratio must be greater than zero."
    if normalized == "material.fy_MPa":
        return "Steel yield strength must be greater than 0 MPa."
    if normalized == "material.E_GPa":
        return "Young's modulus must be greater than 0 GPa."
    if normalized in {"material.gamma_M0", "design.ltb.gamma_M1"}:
        return "Partial material factors must be greater than zero."
    if normalized == "design.gamma_M1":
        return "Partial material factors must be greater than zero."
    if normalized in {"loads.direct_w_kN_m", "loads.line_loads.w_kN_m", "loads.point_loads.P_kN"}:
        return "Load values cannot be negative."
    if normalized in {
        "loads.permanent.N_kN",
        "loads.snow.N_kN",
        "loads.wind.N_kN",
        "loads.variable.N_kN",
        "loads.permanent.py_kN_m",
        "loads.snow.py_kN_m",
        "loads.wind.py_kN_m",
        "loads.variable.py_kN_m",
        "loads.permanent.pz_kN_m",
        "loads.snow.pz_kN_m",
        "loads.wind.pz_kN_m",
        "loads.variable.pz_kN_m",
        "loads.permanent.Py_kN",
        "loads.snow.Py_kN",
        "loads.wind.Py_kN",
        "loads.variable.Py_kN",
        "loads.permanent.Pz_kN",
        "loads.snow.Pz_kN",
        "loads.wind.Pz_kN",
        "loads.variable.Pz_kN",
    }:
        return "Column load values cannot be negative."
    if normalized == "loads.point_loads.a_m":
        return "Point load position cannot be negative."
    if normalized in {"loads.gamma_G", "loads.gamma_Q"}:
        return "Load factors cannot be negative."
    if normalized in {"loads.psi0", "loads.psi1", "loads.psi2"}:
        return "Combination factors cannot be negative."
    if normalized in {
        "loads.automatic.floor_rows.span_m",
        "loads.automatic.floor_rows.dead_kN_m2",
        "loads.automatic.floor_rows.additional_dead_kN_m2",
        "loads.automatic.wall_rows.thickness_cm",
        "loads.automatic.wall_rows.density_kN_m3",
        "loads.automatic.wall_rows.height_m",
        "loads.automatic.wall_rows.percent",
    }:
        return "Automatic load take-down dimensions and loads cannot be negative."
    if normalized == "design.support_width_cm":
        return "Support width must be greater than zero when provided."
    if normalized == "design.left_support_width_cm":
        return "Left support width must be greater than zero when provided."
    if normalized == "design.right_support_width_cm":
        return "Right support width must be greater than zero when provided."
    if normalized == "design.shear_area_override_cm2":
        return "Shear area override cannot be negative."
    if normalized == "design.ltb.unrestrained_length_m":
        return "Unbraced length cannot be negative."
    if normalized == "design.ltb.C1":
        return "LTB moment factor C1 must be greater than zero."
    if normalized in {"design.ltb.alpha_LT", "design.ltb.lambda_LT0", "design.ltb.beta_LT"}:
        return "LTB factors cannot be negative."
    if normalized == "design.ltb.poisson_ratio":
        return "Poisson ratio must be at least zero and less than 0.5."
    if "literal_error" in message_type or "enum" in message_type:
        return "Invalid steel design option selected."
    if "missing" in message_type:
        return "A required steel design input is missing."
    if "finite_number" in message_type or "float_parsing" in message_type or "int_parsing" in message_type:
        return "All numeric steel inputs must be finite numbers."
    return "One or more steel inputs are invalid."


def _hide_framework_detail(detail: str, status_code: int) -> str:
    lower = detail.lower()
    if lower.startswith("body.") or "input should" in lower or "field required" in lower:
        return "One or more API inputs are invalid."
    if "traceback" in lower or "stack trace" in lower or 'file "' in lower:
        return "The calculation service encountered a backend error."
    if status_code >= 500:
        return "The calculation service encountered a backend error."
    return detail


def _dedupe(messages: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for message in messages:
        if message in seen:
            continue
        seen.add(message)
        out.append(message)
    return out
