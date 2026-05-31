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
    rows = [
        ("Project name", "Not specified"),
        ("Engineer name", "Not specified"),
        ("Date/time", created_at.strftime("%Y-%m-%d %H:%M")),
        ("Column mode", "Steel column"),
        ("Selected section", format_text(section.get("name"))),
        ("Report source", "Backend FastAPI steel column calculation result"),
    ]
    return section_heading("1. Project Information", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def geometry_section(request_data: dict[str, Any], results: dict[str, Any], styles: dict) -> list:
    rows = [
        ("Length", format_number(get_path(request_data, "geometry.length_m"), 3, " m")),
        ("Buckling length y", format_number(get_path(request_data, "geometry.buckling_length_y_m"), 3, " m")),
        ("Buckling length z", format_number(get_path(request_data, "geometry.buckling_length_z_m"), 3, " m")),
        ("LTB / kip length", format_number(get_path(request_data, "geometry.ltb_length_m"), 3, " m")),
        ("Deflection limit", "L/" + format_number(get_path(request_data, "geometry.deflection_limit_ratio"), 0)),
        ("Finish type", format_text(get_path(request_data, "design.finish_type"))),
        ("Load position", format_text(get_path(request_data, "design.load_position"))),
    ]
    return section_heading("2. Geometry", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def loads_section(request_data: dict[str, Any], results: dict[str, Any], styles: dict) -> list:
    rows = [
        ("Permanent N", format_number(get_path(request_data, "loads.permanent.N_kN"), 3, " kN")),
        ("Snow N", format_number(get_path(request_data, "loads.snow.N_kN"), 3, " kN")),
        ("Wind N", format_number(get_path(request_data, "loads.wind.N_kN"), 3, " kN")),
        ("Variable N", format_number(get_path(request_data, "loads.variable.N_kN"), 3, " kN")),
        ("Include self-weight", "Yes" if get_path(request_data, "loads.include_self_weight") else "No"),
    ]
    return section_heading("3. Loads", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def stability_summary_section(results: dict[str, Any], styles: dict) -> list:
    stability = results.get("stability_summary") or {}
    classification = stability.get("section_classification") or {}
    rows = [
        ("Section classification", format_text(classification.get("assumed_class"))),
        ("Classification basis", format_text(classification.get("basis"))),
        ("Buckling curve y / z", f"{format_text(stability.get('buckling_curve_y'))} / {format_text(stability.get('buckling_curve_z'))}"),
        ("Imperfection factor alpha y / z", f"{format_number(stability.get('imperfection_factor_alpha_y'), 3)} / {format_number(stability.get('imperfection_factor_alpha_z'), 3)}"),
        ("lambda-bar y / z", f"{format_number(stability.get('lambda_bar_y'), 3)} / {format_number(stability.get('lambda_bar_z'), 3)}"),
        ("chi y / z", f"{format_number(stability.get('chi_y'), 3)} / {format_number(stability.get('chi_z'), 3)}"),
        ("Nb,Rd,y / Nb,Rd,z", f"{format_number(stability.get('NbRdy_kN'), 2, ' kN')} / {format_number(stability.get('NbRdz_kN'), 2, ' kN')}"),
        ("Governing check", format_text(stability.get("governing_check"))),
        ("Governing axis", format_text(stability.get("governing_axis"))),
        (
            "Governing resistance",
            f"{format_text(stability.get('governing_resistance_label'))} = {format_number(stability.get('governing_resistance_kN'), 2, ' kN')}",
        ),
        ("Governing utilization", format_number(stability.get("governing_utilization"), 3)),
        ("Pass / Fail", format_text(stability.get("pass_fail"))),
        ("Failure reason", format_text(stability.get("governing_failure_reason"))),
        ("Reason", format_text(stability.get("reason"))),
    ]
    return section_heading("4. Eurocode Stability Summary", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def buckling_section(results: dict[str, Any], styles: dict) -> list:
    buckling = results.get("buckling") or {}
    stability = results.get("stability_summary") or {}
    rows = [
        ("Effective buckling length y", format_number(stability.get("effective_buckling_length_y_m"), 3, " m")),
        ("Effective buckling length z", format_number(stability.get("effective_buckling_length_z_m"), 3, " m")),
        ("Ncr,y", format_number(buckling.get("Ncr_y_kN"), 2, " kN")),
        ("Ncr,z", format_number(buckling.get("Ncr_z_kN"), 2, " kN")),
        ("lambda-bar y", format_number(buckling.get("lambda_bar_y"), 3)),
        ("lambda-bar z", format_number(buckling.get("lambda_bar_z"), 3)),
        ("Buckling curve y", format_text(buckling.get("buckling_curve_y"))),
        ("Buckling curve z", format_text(buckling.get("buckling_curve_z"))),
        ("chi y", format_number(buckling.get("chi_y"), 3)),
        ("chi z", format_number(buckling.get("chi_z"), 3)),
        ("chi LT", format_number(buckling.get("chi_lt"), 3)),
        ("Geometric slenderness y", format_number(buckling.get("slender_y"), 1)),
        ("Geometric slenderness z", format_number(buckling.get("slender_z"), 1)),
        ("Mcr", format_number(buckling.get("Mcr_kNm"), 2, " kNm")),
    ]
    return section_heading("5. Buckling Verification", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def utilization_section(results: dict[str, Any], styles: dict) -> list:
    effects = results.get("effects") or {}
    resistance = results.get("resistance") or {}
    util = results.get("utilization_detail") or {}
    deflection = results.get("deflection") or {}
    rows = [
        ("NEd", format_number(effects.get("NEd_kN"), 3, " kN")),
        ("Nc,Rd", format_number(resistance.get("NcRd_kN"), 2, " kN")),
        ("My,Ed", format_number(effects.get("MyEd_kNm"), 3, " kNm")),
        ("Mz,Ed", format_number(effects.get("MzEd_kNm"), 3, " kNm")),
        ("Vz,Ed", format_number(effects.get("VzEd_kN"), 3, " kN")),
        ("Compression utilization", format_number(util.get("compression"), 3)),
        ("Stability y/z", f"{format_number(util.get('stability_y'), 3)} / {format_number(util.get('stability_z'), 3)}"),
        ("Governing check", format_text(results.get("governing_check_description") or results.get("governing_check"))),
        ("Governing utilization", format_number(results.get("utilization"), 3)),
        ("Deflection y/z", f"{format_number(deflection.get('uy_mm'), 2)} / {format_number(deflection.get('uz_mm'), 2)} mm"),
        ("Deflection limit", format_number(deflection.get("allow_mm"), 2, " mm")),
        ("Status", format_text(results.get("status"))),
        ("Failure reason", format_text(results.get("governing_failure_reason"))),
        ("Governing combination", format_text(results.get("governing_combination"))),
    ]
    return section_heading("6. Utilization Summary", styles) + [key_value_table(rows), Spacer(1, 4 * mm)]


def recommendations_section(results: dict[str, Any], styles: dict) -> list:
    recommendations = results.get("recommendations") or []
    content = section_heading("7. Recommendations", styles)
    if not recommendations:
        content.extend([Paragraph("No passing column recommendations returned by the backend.", styles["normal"]), Spacer(1, 4 * mm)])
        return content

    rows = [["Section", "Family", "Weight", "Util.", "Governing", "Axis", "chi y/z"]]
    for item in recommendations[:12]:
        rows.append(
            [
                format_text(item.get("section")),
                format_text(item.get("family")),
                format_number(item.get("weight_kg_m"), 1, " kg/m"),
                format_number(item.get("utilization"), 3),
                format_text(item.get("governing")),
                format_text(item.get("governing_axis")),
                f"{format_number(item.get('chi_y'), 3)} / {format_number(item.get('chi_z'), 3)}",
            ]
        )
    table = Table(rows, colWidths=[25 * mm, 18 * mm, 23 * mm, 18 * mm, 36 * mm, 16 * mm, 34 * mm], hAlign="LEFT", repeatRows=1)
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
    for item in get_path(results, "status_detail.failures", []) or []:
        message = f"Failure: {item}"
        if message not in warnings:
            warnings.append(message)

    content = section_heading("8. Warnings", styles)
    if not warnings:
        content.append(Paragraph("No backend warnings returned for this calculation.", styles["normal"]))
    else:
        rows = [["Warning / note"]] + [[format_text(item)] for item in warnings]
        table = Table(rows, colWidths=[170 * mm], hAlign="LEFT", repeatRows=1)
        table.setStyle(list_table_style())
        content.append(table)
    return content
