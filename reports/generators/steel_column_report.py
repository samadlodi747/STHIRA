from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from reports.formatting.pdf_styles import default_margins, engineering_styles
from reports.templates.steel_column_sections import (
    buckling_section,
    geometry_section,
    loads_section,
    project_information,
    recommendations_section,
    stability_summary_section,
    utilization_section,
    warnings_section,
)
from reports.utils.values import report_filename


@dataclass(frozen=True)
class GeneratedReport:
    filename: str
    content: bytes
    media_type: str = "application/pdf"


def generate_steel_column_pdf_report(
    *,
    request_data: dict[str, Any],
    calculation_response: dict[str, Any],
    created_at: datetime | None = None,
) -> GeneratedReport:
    created = created_at or datetime.now()
    results = calculation_response.get("results") or {}
    if not results:
        raise ValueError("Steel column report cannot be generated without calculation results.")

    print("[steel-column-report] stability summary:", results.get("stability_summary"))
    print("[steel-column-report] PDF generation stage: build document")
    buffer = BytesIO()
    left, right, top, bottom = default_margins()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title="Steel Column Calculation Report",
        author="Structural Engineering Calculator",
    )
    styles = engineering_styles()

    story = [
        Paragraph("Steel Column Calculation Report", styles["title"]),
        Paragraph("Backend-generated engineering calculation sheet. Values are taken from the FastAPI steel column engine.", styles["subtitle"]),
        Spacer(1, 2),
    ]
    story.extend(project_information(request_data, results, created, styles))
    story.extend(geometry_section(request_data, results, styles))
    story.extend(loads_section(request_data, results, styles))
    story.extend(stability_summary_section(results, styles))
    story.extend(buckling_section(results, styles))
    story.extend(utilization_section(results, styles))
    story.extend(recommendations_section(results, styles))
    story.extend(warnings_section(calculation_response, results, styles))

    def footer(canvas, document) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColorRGB(0.42, 0.45, 0.50)
        canvas.drawRightString(
            document.pagesize[0] - right,
            bottom * 0.55,
            f"Generated {created:%Y-%m-%d %H:%M} | Page {document.page}",
        )
        canvas.restoreState()

    print("[steel-column-report] PDF generation stage: render")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    content = buffer.getvalue()
    if not content.startswith(b"%PDF"):
        raise RuntimeError("Generated steel column report is not a valid PDF stream.")

    filename = report_filename("steel_column_report", created)
    print("[steel-column-report] PDF generation stage: complete", {"filename": filename, "bytes": len(content)})
    return GeneratedReport(filename=filename, content=content)
