# Brief: Resumes

Two flavors: ATS (Applicant Tracking System friendly) or Creative (visual design).

## ATS Resume (ReportLab)

Single-column, no colors, no tables, no images. Use clear section headers.

```python
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Use a clean serif/sans: Tinos (Times-compatible) or Carlito (Calibri-compatible)
import os
if os.path.exists("/usr/share/fonts/truetype/english/Tinos-Regular.ttf"):
    pdfmetrics.registerFont(TTFont("Tinos", "/usr/share/fonts/truetype/english/Tinos-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("Tinos-Bold", "/usr/share/fonts/truetype/english/Tinos-Bold.ttf"))
    BODY = "Tinos"; BOLD = "Tinos-Bold"
else:
    BODY = "Helvetica"; BOLD = "Helvetica-Bold"

styles = getSampleStyleSheet()
name_style = ParagraphStyle("name", fontName=BOLD, fontSize=22, leading=26, spaceAfter=4)
contact_style = ParagraphStyle("contact", fontName=BODY, fontSize=10, leading=12, textColor=colors.HexColor("#555555"))
h = ParagraphStyle("h", fontName=BOLD, fontSize=12, leading=14, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#222222"))
body_style = ParagraphStyle("body", fontName=BODY, fontSize=10, leading=13, spaceAfter=2)
bullet_style = ParagraphStyle("bullet", parent=body_style, leftIndent=14, bulletIndent=2)

doc = SimpleDocTemplate("resume.pdf", pagesize=LETTER,
    leftMargin=0.7*inch, rightMargin=0.7*inch, topMargin=0.6*inch, bottomMargin=0.6*inch)

story = [
    Paragraph("Jane Doe", name_style),
    Paragraph("jane@example.com · (555) 123-4567 · San Francisco, CA", contact_style),
    Spacer(1, 6),
    Paragraph("Experience", h),
    Paragraph("<b>Senior Engineer</b> — Acme Corp, 2023–Present", body_style),
    Paragraph("• Led migration to microservices, cutting latency 40%.", bullet_style),
    Paragraph("• Mentored 3 junior engineers.", bullet_style),
    # ... etc
]
doc.build(story)
```

## Creative Resume (Playwright)

For design-forward roles. Two-column, accent color, modern typography. See `briefs/creative.md` for the Playwright snapshot pattern — use A4 portrait, accent color matching the user's brand.

## Rules

1. **ATS resumes**: NEVER use tables for layout (parsers choke). Single column only.
2. **Font**: serif (Tinos/Times) or sans (Carlito/Calibri) — both ship in `/usr/share/fonts/truetype/english/`.
3. **Length**: 1 page for <10 yrs experience, 2 pages max otherwise.
4. **Bullet points**: start with action verbs (Led, Built, Shipped, Cut, Improved).
