from __future__ import annotations

from datetime import datetime
from typing import Any

from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table

from reports.formatting.pdf_styles import data_table_style, list_table_style
from reports.utils.values import format_number, format_text, get_path


def section_heading(title: str, styles: dict) -> list:
    return [Paragraph(title, styles["section"])]


def key_value_table(rows: list[tuple[str, str]]) -> Table:
    table = Table(rows, colWidths=[58 * mm, 112 * mm], hAlign="LEFT")
    table.setStyle(data_table_style())
    return table


def project_information(request_data: dict[str, Any], results: dict[str, Any], created_at: datetime, styles: dict) -> list:
    section = results.get("section", {})
    rows = [
        ("Project name", "Not specified"),
        ("Engineer name", "Not specified"),
        ("Date/time", created_at.strftime("%Y-%m-%d %H:%M")),
        ("Beam mode", format_text(get_path(request_data, "loads.mode"))),
        ("Selected section", format_text(section.get("name"))),
        ("Report source", "Backend FastAPI steel beam calculation result"),
    ]
    return section_heading("1. Project Information", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def geometry_section(request_data: dict[str, Any], results: dict[str, Any], styles: dict) -> list:
    automatic = get_path(request_data, "loads.automatic", {}) or {}
    floor_rows = automatic.get("floor_rows") or []
    slab_types = sorted({format_text(row.get("slab_type")) for row in floor_rows if isinstance(row, dict)})
    left_width = get_path(request_data, "design.left_support_width_cm")
    if left_width is None:
        left_width = get_path(request_data, "design.support_width_cm")
    right_width = get_path(request_data, "design.right_support_width_cm")
    if right_width is None:
        right_width = get_path(request_data, "design.support_width_cm")
    bearing_left = results.get("support_bearing_left") or results.get("support_bearing") or {}
    bearing_right = results.get("support_bearing_right") or results.get("support_bearing") or {}
    rows = [
        ("Span", format_number(get_path(request_data, "geometry.span_m"), 3, " m")),
        ("Bending axis", format_text(get_path(request_data, "geometry.axis"))),
        ("Deflection limit", "L/" + format_number(get_path(request_data, "geometry.deflection_limit_ratio"), 0)),
        ("Left support width", format_number(left_width, 1, " cm")),
        ("Right support width", format_number(right_width, 1, " cm")),
        ("Left slof (width / length)", f"{format_number(bearing_left.get('width_cm'), 1, ' cm')} / {format_number(bearing_left.get('length_cm'), 2, ' cm')}"),
        ("Right slof (width / length)", f"{format_number(bearing_right.get('width_cm'), 1, ' cm')} / {format_number(bearing_right.get('length_cm'), 2, ' cm')}"),
        ("Beam spacing", "Not specified"),
        ("Slab type", ", ".join(slab_types) if slab_types else "Not specified"),
    ]
    return section_heading("2. Geometry", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def loads_section(request_data: dict[str, Any], results: dict[str, Any], styles: dict) -> list:
    breakdown = results.get("auto_load_breakdown") or {}
    rows = [
        ("Load mode", format_text(get_path(request_data, "loads.mode"))),
        ("Direct UDL", format_number(get_path(request_data, "loads.direct_w_kN_m"), 3, " kN/m")),
        ("ULS line load", format_number(get_path(results, "loads.w_ULS_kN_m"), 4, " kN/m")),
        ("SLS line load", format_number(get_path(results, "loads.w_SLS_kN_m"), 4, " kN/m")),
        ("Auto dead line load Gk", format_number(breakdown.get("auto_dead_load_kN_m"), 3, " kN/m")),
        ("Auto live line load Qk", format_number(breakdown.get("auto_live_load_kN_m"), 3, " kN/m")),
        ("Floor contribution", format_number(breakdown.get("floor_contribution_kN_m"), 3, " kN/m")),
        ("Wall contribution", format_number(breakdown.get("wall_contribution_kN_m"), 3, " kN/m")),
    ]
    return section_heading("3. Loads", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def design_results_section(results: dict[str, Any], styles: dict) -> list:
    reactions = results.get("reactions") or {}
    deflection = results.get("deflection") or {}
    rows = [
        ("MEd", format_number(results.get("MEd"), 3, " kNm")),
        ("VEd", format_number(results.get("VEd"), 3, " kN")),
        ("Reaction RA", format_number(reactions.get("left_kN"), 3, " kN")),
        ("Reaction RB", format_number(reactions.get("right_kN"), 3, " kN")),
        ("Deflection", format_number(deflection.get("delta_max_mm") or results.get("delta"), 2, " mm")),
        ("Deflection limit", format_number(deflection.get("delta_allow_mm"), 2, " mm")),
        ("Utilization", format_number(results.get("utilization"), 3)),
        ("Status", format_text(results.get("status"))),
        ("Governing combination", format_text(results.get("governing_combination"))),
    ]
    return section_heading("4. Design Results", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def recommendations_section(results: dict[str, Any], styles: dict) -> list:
    recommendations = results.get("recommendations") or []
    content = section_heading("5. Recommendations", styles)
    if not recommendations:
        content.extend([Paragraph("No passing section recommendations returned by the backend.", styles["normal"]), Spacer(1, 4 * mm)])
        return content

    rows = [["Section", "Family", "Weight", "Util.", "Delta", "Reason"]]
    for item in recommendations[:12]:
        fit = item.get("support_width_fit") or {}
        reason = fit.get("reasoning") or format_text(item.get("governing"))
        rows.append(
            [
                format_text(item.get("section")),
                format_text(item.get("family")),
                format_number(item.get("weight_kg_m"), 1, " kg/m"),
                format_number(item.get("utilization"), 3),
                f"{format_number(item.get('delta_mm'), 2)} / {format_number(item.get('delta_allow_mm'), 2)} mm",
                reason,
            ]
        )
    table = Table(rows, colWidths=[25 * mm, 18 * mm, 23 * mm, 18 * mm, 30 * mm, 56 * mm], hAlign="LEFT", repeatRows=1)
    table.setStyle(list_table_style())
    content.extend([table, Spacer(1, 4 * mm)])
    return content


def warnings_section(response: dict[str, Any], results: dict[str, Any], styles: dict) -> list:
    warnings = []
    for item in response.get("warnings") or []:
        if item not in warnings:
            warnings.append(item)
    for item in results.get("warnings") or []:
        if item not in warnings:
            warnings.append(item)
    failures = get_path(results, "status_detail.failures", []) or []
    for item in failures:
        message = f"Failure: {item}"
        if message not in warnings:
            warnings.append(message)

    content = section_heading("6. Warnings", styles)
    if not warnings:
        content.append(Paragraph("No backend warnings returned for this calculation.", styles["normal"]))
    else:
        rows = [["Warning / note"]] + [[format_text(item)] for item in warnings]
        table = Table(rows, colWidths=[170 * mm], hAlign="LEFT", repeatRows=1)
        table.setStyle(list_table_style())
        content.append(table)
    return content
