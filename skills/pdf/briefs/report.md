# Brief: Report PDFs (ReportLab)

Use for: reports, proposals, white papers, contracts, analysis documents.

## Skeleton

```python
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---- Register CJK fonts (probe first!) ----
import os
CJK_DIR = "/usr/share/fonts/truetype/chinese"
if os.path.exists(CJK_DIR):
    pdfmetrics.registerFont(TTFont("NotoSansSC", f"{CJK_DIR}/NotoSansSC-Regular.ttf"))
    pdfmetrics.registerFont(TTFont("NotoSansSC-Bold", f"{CJK_DIR}/NotoSansSC-Bold.ttf"))
    pdfmetrics.registerFont(TTFont("NotoSerifSC", "/usr/share/fonts/truetype/noto-serif-sc/NotoSerifSC-Regular.ttf"))
    BODY_FONT = "NotoSerifSC"
    HEADING_FONT = "NotoSansSC-Bold"
else:
    BODY_FONT = "Helvetica"
    HEADING_FONT = "Helvetica-Bold"

# ---- Styles ----
styles = getSampleStyleSheet()
body = ParagraphStyle("body", parent=styles["BodyText"], fontName=BODY_FONT,
                     fontSize=11, leading=16, spaceAfter=8, alignment=4)  # 4=justify
h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontName=HEADING_FONT,
                    fontSize=20, leading=26, spaceBefore=20, spaceAfter=12, textColor=colors.HexColor("#0E0E10"))
h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName=HEADING_FONT,
                    fontSize=14, leading=18, spaceBefore=14, spaceAfter=6, textColor=colors.HexColor("#18181B"))

# ---- Build the doc ----
doc = SimpleDocTemplate(
    "/home/z/my-project/download/report.pdf",
    pagesize=A4,
    leftMargin=2*cm, rightMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm,
)

story = []
# Cover
story.append(Paragraph("Report Title", h1))
story.append(Spacer(1, 6*mm))
story.append(Paragraph("Subtitle or author", body))
story.append(PageBreak())   # ONLY page break: cover → body
# Body (NO more page breaks)
story.append(Paragraph("1. Introduction", h2))
story.append(Paragraph("Body text here...", body))
# ... continue ...
doc.build(story)
print("saved: /home/z/my-project/download/report.pdf")
```

## CRITICAL rules

1. **Page breaks**: only between cover and body. After that, NEVER insert `PageBreak()` mid-content.
2. **Justification**: use `alignment=4` (justify) for body, but use `alignment=0` (left) for lists — justify breaks list items badly.
3. **Math/superscripts**: use `<super>`/`<sub>` tags inside `Paragraph()`, NEVER Unicode escapes.
4. **Line breaks**: do NOT break a sentence across lines. Start a new `Paragraph()` only at logical paragraph boundaries.
5. **Bullet lists**: one item per `Paragraph()`, each with `leftIndent=12` and a bullet char.
6. **Tables**: use `Table` with `TableStyle` for borders/grids. Set `colWidths` to avoid overflow.
7. **No emoji**: ReportLab renders emoji as □. Force Creative pipeline if user has emoji.
8. **No artificial endings**: never add "------End of Report------" or similar.

## Multi-section report recipe

```python
sections = [
    ("Executive Summary", "..."),
    ("Background", "..."),
    ("Analysis", "..."),
    ("Recommendations", "..."),
]
for title, content in sections:
    story.append(Paragraph(title, h2))
    story.append(Paragraph(content, body))
```

## Content depth (MANDATORY)

- Each paragraph ≥ 3-5 sentences.
- Each section ≥ 150-200 words.
- Never a heading followed by only 1-2 lines.
- Enrich with examples, context, implications.
