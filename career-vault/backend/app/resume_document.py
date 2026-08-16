"""DOCX rendering for a Career Vault master resume.

This renderer intentionally uses only approved, already-generated draft content. It does
not make model calls and never reads data belonging to another user.
"""

from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ACCENT = RGBColor(33, 101, 69)
INK = RGBColor(24, 34, 31)
MUTED = RGBColor(81, 96, 88)


def _set_cell_shading(cell: Any, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


def _set_run_font(run: Any, size: float, bold: bool = False, color: RGBColor = INK) -> None:
    run.font.name = "Aptos"
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Aptos")
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = color


def _add_section_heading(document: Document, text: str) -> None:
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.space_before = Pt(10)
    paragraph.paragraph_format.space_after = Pt(4)
    paragraph.paragraph_format.keep_with_next = True
    run = paragraph.add_run(text.upper())
    _set_run_font(run, 9, bold=True, color=ACCENT)


def _add_bullets(document: Document, items: list[str]) -> None:
    for item in items:
        if not isinstance(item, str) or not item.strip():
            continue
        paragraph = document.add_paragraph(style="List Bullet")
        paragraph.paragraph_format.space_after = Pt(1)
        paragraph.paragraph_format.line_spacing = 1.05
        run = paragraph.add_run(item.strip())
        _set_run_font(run, 9.5)


def _clean_list(values: Any) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()] if isinstance(values, list) else []


def render_master_resume(path: Path, display_name: str, resume: dict[str, Any]) -> None:
    """Create a compact, ATS-readable DOCX with a resume contact header override."""
    path.parent.mkdir(parents=True, exist_ok=True)
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(0.55)
    section.bottom_margin = Inches(0.55)
    section.left_margin = Inches(0.65)
    section.right_margin = Inches(0.65)

    styles = document.styles
    styles["Normal"].font.name = "Aptos"
    styles["Normal"]._element.rPr.rFonts.set(qn("w:eastAsia"), "Aptos")
    styles["Normal"].font.size = Pt(9.5)
    styles["Normal"].font.color.rgb = INK

    # Named resume-contact-header override: the identity is prominent, while the body
    # stays entirely text-based and easy for ATS systems to read.
    name = document.add_paragraph()
    name.alignment = WD_ALIGN_PARAGRAPH.CENTER
    name.paragraph_format.space_after = Pt(2)
    run = name.add_run(display_name.upper())
    _set_run_font(run, 20, bold=True, color=ACCENT)
    headline = str(resume.get("headline") or "Professional Profile").strip()
    if headline:
        line = document.add_paragraph()
        line.alignment = WD_ALIGN_PARAGRAPH.CENTER
        line.paragraph_format.space_after = Pt(10)
        run = line.add_run(headline)
        _set_run_font(run, 10.5, color=MUTED)

    summary = str(resume.get("professional_summary") or "").strip()
    if summary:
        _add_section_heading(document, "Professional Summary")
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(4)
        paragraph.paragraph_format.line_spacing = 1.08
        run = paragraph.add_run(summary)
        _set_run_font(run, 9.5)

    skills = _clean_list(resume.get("skills"))
    if skills:
        _add_section_heading(document, "Core Skills")
        table = document.add_table(rows=1, cols=1)
        table.autofit = True
        cell = table.cell(0, 0)
        _set_cell_shading(cell, "F0F6F1")
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_after = Pt(2)
        paragraph.paragraph_format.space_before = Pt(2)
        run = paragraph.add_run("  •  ".join(skills))
        _set_run_font(run, 9.3, color=MUTED)

    experience = resume.get("experience")
    if isinstance(experience, list) and experience:
        _add_section_heading(document, "Professional Experience")
        for entry in experience:
            if not isinstance(entry, dict):
                continue
            role = str(entry.get("role") or "Professional experience").strip()
            company = str(entry.get("company") or "").strip()
            dates = str(entry.get("dates") or "").strip()
            title = document.add_paragraph()
            title.paragraph_format.space_before = Pt(4)
            title.paragraph_format.space_after = Pt(1)
            title.paragraph_format.keep_with_next = True
            run = title.add_run(role)
            _set_run_font(run, 10, bold=True)
            if company:
                run = title.add_run(f" | {company}")
                _set_run_font(run, 10, color=MUTED)
            if dates:
                run = title.add_run(f"  {dates}")
                _set_run_font(run, 9, color=MUTED)
            _add_bullets(document, _clean_list(entry.get("highlights")))

    for section_key, heading in (("certifications", "Certifications"), ("education", "Education"), ("additional_highlights", "Additional Highlights")):
        values = _clean_list(resume.get(section_key))
        if values:
            _add_section_heading(document, heading)
            _add_bullets(document, values)

    document.save(path)
