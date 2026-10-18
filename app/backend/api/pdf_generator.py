"""One-page expert handoff PDF generator using ReportLab (guide section 6 & 11 task 19)."""
from __future__ import annotations

import io
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def generate_expert_handoff_pdf(
    investigation_id: int,
    farm_name: str,
    field_name: str,
    crop: str | None,
    symptom_date: str,
    window_days: int,
    report: dict[str, Any],
) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleStyle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#1b4d3e"),
        spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "MetaStyle",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#4a5568"),
    )
    heading_style = ParagraphStyle(
        "HStyle",
        parent=styles["Heading2"],
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#2d3748"),
        spaceBefore=6,
        spaceAfter=3,
        keepWithNext=True,
    )
    body_style = ParagraphStyle(
        "BodyStyle",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#1a202c"),
        spaceAfter=2,
    )
    disclaimer_style = ParagraphStyle(
        "DisclaimerStyle",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#c53030"),
        alignment=1,  # Center
    )

    story = []

    # Header
    story.append(Paragraph("<b>FasalNama — Farm Record Investigation (Expert Handoff)</b>", title_style))
    story.append(
        Paragraph(
            f"<b>Farm:</b> {farm_name} | <b>Field:</b> {field_name} ({crop or 'Crop N/A'}) | "
            f"<b>Symptom Date:</b> {symptom_date} | <b>Window:</b> {window_days} days | "
            f"<b>Investigation Ref:</b> INV-{investigation_id:03d}",
            meta_style,
        )
    )
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#cbd5e0"), spaceAfter=6))

    sections = report.get("sections", {})

    # 1. What the records show
    records = sections.get("records_show", [])
    if records:
        story.append(Paragraph("<b>1. What the Records Show (Chronological Facts)</b>", heading_style))
        for item in records[:8]:
            text = item.get("text", "")
            ids = ", ".join(item.get("event_ids", []))
            ref = f" <i>[{ids}]</i>" if ids else ""
            story.append(Paragraph(f"• {text}{ref}", body_style))

    # 2. What may be worth investigating
    investigate = sections.get("worth_investigating", [])
    if investigate:
        story.append(Paragraph("<b>2. What May Be Worth Investigating (Hypotheses)</b>", heading_style))
        for item in investigate[:5]:
            text = item.get("text", "")
            story.append(Paragraph(f"• {text}", body_style))

    # 3. Questions to ask next
    questions = sections.get("questions_next", [])
    if questions:
        story.append(Paragraph("<b>3. Prepared Questions for Agronomist / Expert</b>", heading_style))
        for item in questions[:5]:
            text = item.get("text", "")
            story.append(Paragraph(f"? {text}", body_style))

    # 4. Missing records
    missing = sections.get("missing_records", [])
    if missing:
        story.append(Paragraph("<b>4. Missing Records & Unknowns</b>", heading_style))
        for item in missing[:5]:
            text = item.get("text", "")
            story.append(Paragraph(f"⚠ {text}", body_style))

    # 5. Photo observations
    photos = sections.get("photo_observations", [])
    if photos:
        story.append(Paragraph("<b>5. Field Photo Observations (Unconfirmed)</b>", heading_style))
        for item in photos[:4]:
            text = item.get("text", "")
            pids = ", ".join(item.get("photo_ids", []))
            ref = f" <i>[{pids}]</i>" if pids else ""
            story.append(Paragraph(f"📷 {text}{ref}", body_style))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=6))

    # Non-negotiable Disclaimer
    disclaimer = report.get("disclaimer", "This is an evidence summary built from records, not a diagnosis.")
    story.append(Paragraph(f"<b>CRITICAL NOTE:</b> {disclaimer} Never substitute this summary for an agronomist's visit.", disclaimer_style))

    doc.build(story)
    return buf.getvalue()
