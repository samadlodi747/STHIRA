from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape, portrait
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from reports.formatting.pdf_styles import default_margins, engineering_styles

# Utilizations at/above this are treated as off-scale (e.g. the column engine's 999.0
# sentinel for degenerate/grossly-overstressed members). They are shown as ">10.00"
# and excluded from the average so summary statistics stay meaningful. Underlying
# stored values are never changed — this is presentation only.
_OFF_SCALE_UTIL = 10.0


@dataclass(frozen=True)
class GeneratedReport:
    filename: str
    content: bytes
    media_type: str = "application/pdf"


# Saved member entries use these mode labels (set by the frontend schedule).
_BEAM_LABEL = "Steel Beam"
_COLUMN_LABEL = "Steel Column"
_TIMBER_LABEL = "Timber Beam"


class _NumberedCanvas(pdfcanvas.Canvas):
    """Canvas that defers page rendering so a 'Page X / Y' total can be stamped.

    Standard ReportLab recipe: buffer each page's state, then on save() replay them
    once the total page count is known.
    """

    def __init__(self, *args, header_lines=None, margins=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states: list[dict] = []
        self._header_lines = header_lines or {}
        self._margins = margins or (16 * mm, 15 * mm, 16 * mm, 14 * mm)

    def showPage(self) -> None:  # noqa: N802 (ReportLab API name)
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._draw_page_furniture(total)
            super().showPage()
        super().save()

    def _draw_page_furniture(self, total_pages: int) -> None:
        left, right, top, bottom = self._margins
        width, height = self._pagesize
        self.saveState()

        # Top header band.
        self.setFont("Helvetica-Bold", 13)
        self.setFillColor(colors.HexColor("#111827"))
        self.drawString(left, height - top + 4 * mm, "MEMBER SCHEDULE")

        self.setFont("Helvetica", 8.5)
        self.setFillColor(colors.HexColor("#374151"))
        project = self._header_lines.get("project") or "Not specified"
        date_text = self._header_lines.get("date") or ""
        self.drawString(left, height - top - 1 * mm, f"Project Name: {project}")
        self.drawRightString(width - right, height - top - 1 * mm, f"Date: {date_text}")

        # Header rule.
        self.setStrokeColor(colors.HexColor("#9ca3af"))
        self.setLineWidth(0.5)
        self.line(left, height - top - 3 * mm, width - right, height - top - 3 * mm)

        # Footer with page numbering. self._pageNumber is restored from the saved
        # per-page state, so it is the correct number for the page being replayed.
        self.setFont("Helvetica", 7)
        self.setFillColor(colors.HexColor("#6b7280"))
        self.drawRightString(width - right, bottom * 0.55, f"Page {self._pageNumber} / {total_pages}")
        self.restoreState()


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text or text in {"-", "–", "—"}:
        return None
    number = []
    seen_dot = False
    for ch in text:
        if ch.isdigit():
            number.append(ch)
        elif ch == "." and not seen_dot:
            number.append(ch)
            seen_dot = True
        elif ch in "+-" and not number:
            number.append(ch)
        else:
            break
    try:
        return float("".join(number))
    except ValueError:
        return None


def _text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def _is_passing(member: dict) -> bool | None:
    # Pass/fail is taken from the saved engineering STATUS, which is authoritative and
    # already accounts for serviceability (deflection) as well as strength. The stored
    # controlValue is the strength-only control utilization (deflection is excluded by
    # the engine), so it must NOT be used as the primary pass/fail signal — a member can
    # fail on deflection while controlValue <= 1.0 (e.g. 0.000).
    kind = str(member.get("statusKind") or "").strip().lower()
    if kind in ("bad", "fail", "failed", "error"):
        return False
    if kind in ("ok", "warn", "warning"):
        return True

    status = str(member.get("statusText") or "").strip().lower()
    if status and status != "ready":
        fail_markers = ("exceed", "fail", "not implemented", "class 4", "invalid")
        if any(marker in status for marker in fail_markers):
            return False
        return True

    # Last-resort fallback only when no saved status is available.
    util = _to_float(member.get("controlValue"))
    if util is not None:
        return util <= 1.0
    return None


def _status_label(member: dict) -> str:
    passing = _is_passing(member)
    if passing is True:
        return "PASS"
    if passing is False:
        return "FAIL"
    return "-"


def _format_util_display(value: Any) -> str:
    """Engineering-friendly utilization text. Off-scale/sentinel values (e.g. 999.0)
    become '> 10.00'; finite values keep their numeric form. Stored value is unchanged."""
    util = _to_float(value)
    if util is None:
        return _text(value)
    if util > _OFF_SCALE_UTIL:
        return "> 10.00"
    return f"{util:.3f}"


def _deflection_pair(value: Any) -> tuple[float | None, float | None]:
    """Parse a saved deflection display string like '155571.57 (allow 9.80)' into
    (delta_max, allowable). Returns (None, None) when it cannot be parsed."""
    text = str(value or "")
    dmax = _to_float(text.split("(")[0]) if text else None
    allow = None
    if "allow" in text.lower():
        after = text.lower().split("allow", 1)[1]
        allow = _to_float(after)
    return dmax, allow


def _deflection_ratio(member: dict) -> float | None:
    dmax, allow = _deflection_pair(member.get("deflectionValue"))
    if dmax is None or allow is None or allow <= 0.0:
        return None
    return dmax / allow


def _is_grossly_invalid(member: dict) -> bool:
    """A failed beam whose governing demand is off-scale (e.g. deflection thousands of
    times over the limit). Its reaction-derived bearing detailing (slof length and
    reinforcement) is not a meaningful engineering output and is reported as 'N/A'.
    Passing and marginally-failing beams are never affected."""
    if _is_passing(member) is not False:
        return False
    demand = max(
        _to_float(member.get("controlValue")) or 0.0,
        _deflection_ratio(member) or 0.0,
    )
    return demand > _OFF_SCALE_UTIL


def _deflection_cell(value: Any, style: ParagraphStyle) -> Paragraph:
    """Render δmax on two lines ('value' / '(allow A)') to relieve table width pressure."""
    dmax, allow = _deflection_pair(value)
    if dmax is None:
        return Paragraph(_text(value), style)
    dmax_text = f"{dmax:,.2f}"
    if allow is None:
        return Paragraph(dmax_text, style)
    return Paragraph(f"{dmax_text}<br/>(allow {allow:.2f})", style)


def _banner_table(
    title: str,
    header: list[str],
    rows: list[list[str]],
    col_widths: list[float],
    *,
    portrait_mode: bool,
    status_col: int | None = None,
) -> Table:
    # Headers are always wrapped Paragraphs so multi-word labels (e.g. "Right Slof L (cm)")
    # render on their own lines instead of colliding/merging with neighbours. Portrait uses
    # a smaller font for the extra columns.
    header_font = 6.2 if portrait_mode else 7.2
    body_font_size = 6.2 if portrait_mode else 7.2
    header_style = ParagraphStyle(
        "MsHeaderCell",
        fontName="Helvetica-Bold",
        fontSize=header_font,
        leading=header_font + 1.6,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#111827"),
    )
    header_cells = [Paragraph(text, header_style) for text in header]

    data = [[title] + [""] * (len(header) - 1), header_cells] + rows
    table = Table(data, colWidths=col_widths, repeatRows=2, hAlign="LEFT")
    style = [
        # Banner row (section title) — repeats on every continuation page.
        ("SPAN", (0, 0), (-1, 0)),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("TOPPADDING", (0, 0), (-1, 0), 4),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
        # Column header row.
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#e5e7eb")),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
        # Body.
        ("FONTNAME", (0, 2), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), body_font_size),
        ("LEADING", (0, 1), (-1, -1), body_font_size + 1.8),
        ("GRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4 if not portrait_mode else 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4 if not portrait_mode else 3),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("ROWBACKGROUNDS", (0, 2), (-1, -1), [colors.white, colors.HexColor("#f9fafb")]),
    ]
    # Colour the PASS/FAIL status cells for instant readability.
    if status_col is not None:
        for row_index, row in enumerate(rows):
            cell = str(row[status_col]).strip().upper()
            if cell == "PASS":
                style.append(("TEXTCOLOR", (status_col, 2 + row_index), (status_col, 2 + row_index), colors.HexColor("#047857")))
            elif cell == "FAIL":
                style.append(("TEXTCOLOR", (status_col, 2 + row_index), (status_col, 2 + row_index), colors.HexColor("#b91c1c")))
        style.append(("FONTNAME", (status_col, 2), (status_col, -1), "Helvetica-Bold"))
    table.setStyle(TableStyle(style))
    return table


def _scaled_widths(fractions: list[float], available: float) -> list[float]:
    total = sum(fractions)
    return [available * (f / total) for f in fractions]


def generate_member_schedule_pdf_report(
    *,
    request_data: dict[str, Any],
    created_at: datetime | None = None,
) -> GeneratedReport:
    created = created_at or datetime.now()
    project_name = _text(request_data.get("project_name"), "Not specified")
    orientation = str(request_data.get("orientation") or "landscape").strip().lower()
    members = request_data.get("members") or []

    beams = [m for m in members if str(m.get("modeLabel")) == _BEAM_LABEL]
    columns = [m for m in members if str(m.get("modeLabel")) == _COLUMN_LABEL]
    timber = [m for m in members if str(m.get("modeLabel")) == _TIMBER_LABEL]

    page_size = landscape(A4) if orientation == "landscape" else portrait(A4)
    left, right, top, bottom = default_margins()
    # Extra top margin to clear the page header band drawn by the numbered canvas.
    top_margin = top + 8 * mm

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=page_size,
        leftMargin=left,
        rightMargin=right,
        topMargin=top_margin,
        bottomMargin=bottom,
        title="Member Schedule",
        author="Structural Engineering Calculator",
    )
    styles = engineering_styles()
    available = page_size[0] - left - right
    portrait_mode = orientation != "landscape"
    cell_font = 6.2 if portrait_mode else 7.2
    value_style = ParagraphStyle(
        "MsValueCell",
        fontName="Helvetica",
        fontSize=cell_font,
        leading=cell_font + 1.6,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1f2937"),
    )
    story: list = []

    # Beam schedule. Explicit (proportional) widths give wide fields to multi-word headers
    # and the multiline δmax cell so nothing collides; narrow fields to short numerics.
    beam_header = [
        "Member", "Length (m)", "Selected Section", "δmax (mm)", "Control Util. (max)",
        "Left Slof W (cm)", "Left Slof L (cm)", "Right Slof W (cm)", "Right Slof L (cm)",
        "Mid Reinf. (cm²)", "End Reinf. (cm²)", "Status",
    ]
    beam_fractions = [2.0, 1.1, 2.2, 2.1, 1.7, 1.15, 1.45, 1.15, 1.45, 1.5, 1.5, 1.25]
    if beams:
        beam_rows = [
            [
                _text(m.get("name")),
                _text(m.get("length")),
                _text(m.get("section")),
                _deflection_cell(m.get("deflectionValue"), value_style),
                _format_util_display(m.get("controlValue")),
                _text(m.get("leftSlofWidth")),
                "N/A" if _is_grossly_invalid(m) else _text(m.get("leftSlofLength")),
                _text(m.get("rightSlofWidth")),
                "N/A" if _is_grossly_invalid(m) else _text(m.get("rightSlofLength")),
                "N/A" if _is_grossly_invalid(m) else _text(m.get("reinforcementMid")),
                "N/A" if _is_grossly_invalid(m) else _text(m.get("reinforcementHead")),
                _status_label(m),
            ]
            for m in beams
        ]
        story.append(_banner_table("BEAM SCHEDULE", beam_header, beam_rows, _scaled_widths(beam_fractions, available), portrait_mode=portrait_mode, status_col=11))
    else:
        story.append(Paragraph("BEAM SCHEDULE", styles["section"]))
        story.append(Paragraph("No saved beams in the member schedule.", styles["normal"]))
    story.append(Spacer(1, 6 * mm))

    # Column schedule. Governing axis is included when captured in the saved member data.
    column_header = ["Member", "Length (m)", "Selected Section", "Control Util. (max)", "Gov. Axis", "Status"]
    column_fractions = [1.9, 1.0, 2.3, 1.4, 1.0, 1.1]
    if columns:
        column_rows = [
            [
                _text(m.get("name")),
                _text(m.get("length")),
                _text(m.get("section")),
                _format_util_display(m.get("controlValue")),
                _text(m.get("governingAxis")),
                _status_label(m),
            ]
            for m in columns
        ]
        story.append(_banner_table("COLUMN SCHEDULE", column_header, column_rows, _scaled_widths(column_fractions, available), portrait_mode=portrait_mode, status_col=5))
    else:
        story.append(Paragraph("COLUMN SCHEDULE", styles["section"]))
        story.append(Paragraph("No saved columns in the member schedule.", styles["normal"]))
    story.append(Spacer(1, 6 * mm))

    # Timber beam schedule.
    if timber:
        timber_header = ["Member", "Material", "Selected Section", "Span (m)", "δmax (mm)", "Control Util. (max)", "Status"]
        timber_fractions = [1.7, 1.2, 1.8, 1.0, 2.0, 1.6, 1.1]
        timber_rows = [
            [
                _text(m.get("name")),
                _text(m.get("material")),
                _text(m.get("section")),
                _text(m.get("length")),
                _deflection_cell(m.get("deflectionValue"), value_style),
                _format_util_display(m.get("controlValue")),
                _status_label(m),
            ]
            for m in timber
        ]
        story.append(_banner_table("TIMBER BEAM SCHEDULE", timber_header, timber_rows, _scaled_widths(timber_fractions, available), portrait_mode=portrait_mode, status_col=6))
        story.append(Spacer(1, 6 * mm))

    # Project summary (beams + timber beams + columns).
    summary_members = beams + timber + columns
    utils = [u for u in (_to_float(m.get("controlValue")) for m in summary_members) if u is not None]
    # Off-scale sentinels (e.g. 999.0) are excluded from the average so it reflects real
    # engineering utilizations rather than being skewed by degenerate failures.
    on_scale = [u for u in utils if u <= _OFF_SCALE_UTIL]
    pass_flags = [_is_passing(m) for m in summary_members]
    passing = sum(1 for f in pass_flags if f is True)
    failing = sum(1 for f in pass_flags if f is False)
    max_util = max(utils) if utils else None
    avg_util = (sum(on_scale) / len(on_scale)) if on_scale else None

    summary_rows = [
        ["Total Beams", str(len(beams))],
        ["Total Timber Beams", str(len(timber))],
        ["Total Columns", str(len(columns))],
        ["Total Members", str(len(summary_members))],
        ["Maximum Utilization", _format_util_display(max_util) if max_util is not None else "-"],
        ["Average Utilization", f"{avg_util:.3f}" if avg_util is not None else "-"],
        ["Passing Members", str(passing)],
        ["Failing Members", str(failing)],
    ]
    summary_table = Table([["SUMMARY", ""]] + summary_rows, colWidths=_scaled_widths([1.0, 1.0], min(available, 150 * mm)), hAlign="LEFT")
    summary_table.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (-1, 0)),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 2 * mm))
    story.append(
        Paragraph(
            "Utilizations above 10.0 are shown as “&gt; 10.00”. Average Utilization excludes these "
            "off-scale members so the figure reflects realistic engineering utilizations; counts and "
            "Maximum Utilization include all members. For grossly failed beams the reaction-derived "
            "slof length and reinforcement are reported as “N/A”, as they are not meaningful detailing "
            "outputs for an invalid design.",
            styles["small"],
        )
    )

    header_lines = {"project": project_name, "date": created.strftime("%Y-%m-%d %H:%M")}
    margins = (left, right, top_margin, bottom)

    def make_canvas(*args, **kwargs):
        return _NumberedCanvas(*args, header_lines=header_lines, margins=margins, **kwargs)

    doc.build(story, canvasmaker=make_canvas)
    content = buffer.getvalue()
    if not content.startswith(b"%PDF"):
        raise RuntimeError("Generated member schedule report is not a valid PDF stream.")

    return GeneratedReport(filename="Member_Schedule.pdf", content=content)
