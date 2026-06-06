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
    section = results.get("section") or {}
    material = results.get("material") or {}
    rows = [
        ("Project name", "Not specified"),
        ("Member name", "Not specified"),
        ("Date/time", created_at.strftime("%Y-%m-%d %H:%M")),
        ("Member type", "Timber beam"),
        ("Material grade", format_text(material.get("grade"))),
        ("Selected section", format_text(section.get("name"))),
        ("Report source", "Backend FastAPI timber beam calculation result"),
    ]
    return section_heading("1. Project Information", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def geometry_section(request_data: dict[str, Any], results: dict[str, Any], styles: dict) -> list:
    section = results.get("section") or {}
    rows = [
        ("Span", format_number(get_path(request_data, "geometry.span_m"), 3, " m")),
        ("Deflection limit", "L/" + format_number(get_path(request_data, "geometry.deflection_limit_ratio"), 0)),
        ("Width", format_number(section.get("width_mm"), 0, " mm")),
        ("Depth", format_number(section.get("depth_mm"), 0, " mm")),
        ("Area", format_number(section.get("area_mm2"), 0, " mm²")),
        ("Section modulus W", format_number(section.get("W_mm3"), 0, " mm³")),
        ("Second moment Iy", format_number(section.get("Iy_mm4"), 0, " mm⁴")),
    ]
    return section_heading("2. Geometry & Section", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def material_section(results: dict[str, Any], styles: dict) -> list:
    m = results.get("material") or {}
    r = results.get("resistance") or {}
    rows = [
        ("Grade", format_text(m.get("grade"))),
        ("Type", format_text(m.get("type"))),
        ("fm,k", format_number(m.get("fm_k"), 1, " N/mm²")),
        ("fv,k", format_number(m.get("fv_k"), 1, " N/mm²")),
        ("E mean", format_number(m.get("E_mean"), 0, " N/mm²")),
        ("Density", format_number(m.get("density"), 0, " kg/m³")),
        ("gamma_M", format_number(m.get("gamma_M"), 2)),
        ("kmod", format_number(m.get("kmod"), 2)),
        ("fm,d", format_number(r.get("fm_d"), 2, " N/mm²")),
        ("fv,d", format_number(r.get("fv_d"), 2, " N/mm²")),
    ]
    return section_heading("3. Material (EN 1995-1-1)", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def loads_section(request_data: dict[str, Any], results: dict[str, Any], styles: dict) -> list:
    rows = [
        ("Load mode", format_text(get_path(request_data, "loads.mode"))),
        ("Direct UDL", format_number(get_path(request_data, "loads.direct_w_kN_m"), 3, " kN/m")),
        ("Include self-weight", "Yes" if get_path(request_data, "loads.include_self_weight") else "No"),
        ("MEd", format_number(results.get("MEd_kNm"), 3, " kNm")),
        ("VEd", format_number(results.get("VEd_kN"), 3, " kN")),
    ]
    return section_heading("4. Loads & Effects", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def checks_section(results: dict[str, Any], styles: dict) -> list:
    util = results.get("utilization_detail") or {}
    res = results.get("resistance") or {}
    deflection = results.get("deflection") or {}

    def verdict(value: Any) -> str:
        try:
            return "PASS" if float(value) <= 1.0 else "FAIL"
        except (TypeError, ValueError):
            return "-"

    rows = [
        ["Check", "Demand", "Resistance / Limit", "Utilization", "Result"],
        [
            "Bending (6.1.6)",
            format_number(results.get("MEd_kNm"), 3, " kNm"),
            format_number(res.get("MRd_kNm"), 3, " kNm"),
            format_number(util.get("bending"), 3),
            verdict(util.get("bending")),
        ],
        [
            "Shear (6.1.7)",
            format_number(results.get("VEd_kN"), 3, " kN"),
            format_number(res.get("VRd_kN"), 3, " kN"),
            format_number(util.get("shear"), 3),
            verdict(util.get("shear")),
        ],
        [
            "Deflection (7.2)",
            format_number(deflection.get("delta_max_mm"), 2, " mm"),
            format_number(deflection.get("delta_allow_mm"), 2, " mm"),
            format_number(util.get("deflection"), 3),
            verdict(util.get("deflection")),
        ],
    ]
    table = Table(rows, colWidths=[42 * mm, 40 * mm, 44 * mm, 24 * mm, 20 * mm], hAlign="LEFT", repeatRows=1)
    table.setStyle(list_table_style())
    content = section_heading("5. Design Checks", styles) + [table, Spacer(1, 3 * mm)]
    overall = "PASS" if format_text(results.get("status_kind")) != "bad" else "FAIL"
    content.append(Paragraph(f"Governing utilization: {format_number(results.get('utilization'), 3)} — Overall: {overall} ({format_text(results.get('status'))})", styles["normal"]))
    content.append(Spacer(1, 4 * mm))
    return content


def recommendations_section(results: dict[str, Any], styles: dict) -> list:
    recommendations = results.get("recommendations") or []
    content = section_heading("6. Section Recommendations", styles)
    if not recommendations:
        content.extend([Paragraph("No passing timber section found in the library for these loads.", styles["normal"]), Spacer(1, 4 * mm)])
        return content
    rows = [["Section", "Width (mm)", "Depth (mm)", "Utilization"]]
    for item in recommendations[:12]:
        rows.append(
            [
                format_text(item.get("section")),
                format_number(item.get("width_mm"), 0),
                format_number(item.get("depth_mm"), 0),
                format_number(item.get("utilization"), 3),
            ]
        )
    table = Table(rows, colWidths=[40 * mm, 35 * mm, 35 * mm, 35 * mm], hAlign="LEFT", repeatRows=1)
    table.setStyle(list_table_style())
    content.extend([table, Spacer(1, 4 * mm)])
    return content


def warnings_section(response: dict[str, Any], results: dict[str, Any], styles: dict) -> list:
    warnings: list[str] = []
    for item in (response.get("warnings") or []) + (results.get("warnings") or []):
        if item not in warnings:
            warnings.append(item)
    for item in get_path(results, "status_detail.failures", []) or []:
        message = f"Failure: {item}"
        if message not in warnings:
            warnings.append(message)
    content = section_heading("7. Warnings", styles)
    if not warnings:
        content.append(Paragraph("No backend warnings returned for this calculation.", styles["normal"]))
    else:
        rows = [["Warning / note"]] + [[format_text(item)] for item in warnings]
        table = Table(rows, colWidths=[170 * mm], hAlign="LEFT", repeatRows=1)
        table.setStyle(list_table_style())
        content.append(table)
    return content
