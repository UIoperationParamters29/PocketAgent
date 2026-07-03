# Brief: Word (.docx) Documents

Use for: reports, articles, proposals, manuscripts — when the user wants an editable Word file.

## Skeleton

```python
from docx import Document
from docx.shared import Pt, Cm, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.style import WD_STYLE_TYPE

doc = Document()

# ---- Page setup ----
section = doc.sections[0]
section.top_margin = Cm(2.5)
section.bottom_margin = Cm(2.5)
section.left_margin = Cm(2.5)
section.right_margin = Cm(2.5)

# ---- Styles ----
styles = doc.styles
normal = styles["Normal"]
normal.font.name = "Calibri"
normal.font.size = Pt(11)
normal.paragraph_format.line_spacing = 1.15
normal.paragraph_format.space_after = Pt(6)

# ---- Cover ----
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run("Document Title")
run.bold = True
run.font.size = Pt(28)
run.font.color.rgb = RGBColor(0x0E, 0x0E, 0x10)
doc.add_paragraph()  # spacer

# Page break: ONLY between cover and body (per page-break rule)
doc.add_page_break()

# ---- Body ----
doc.add_heading("1. Introduction", level=1)
doc.add_paragraph("Body text here...")

doc.add_heading("2. Background", level=1)
doc.add_paragraph("More body text...")

# Bullet list
doc.add_paragraph("First item", style="List Bullet")
doc.add_paragraph("Second item", style="List Bullet")

# Table
table = doc.add_table(rows=3, cols=2, style="Light Grid Accent 1")
table.cell(0, 0).text = "Name"
table.cell(0, 1).text = "Value"

doc.save("/home/z/my-project/download/document.docx")
print("saved: /home/z/my-project/download/document.docx")
```

## Rules

1. **Page breaks**: ONLY between cover and TOC/body. No mid-content breaks.
2. **Lists**: one item per paragraph, use `style="List Bullet"` or `"List Number"`. NEVER put multiple items in one paragraph.
3. **Alignment**: use left-align for lists (justify breaks them). Justify is fine for body paragraphs.
4. **Headings**: use `doc.add_heading(text, level=N)` — preserves accessibility.
5. **Tables**: always set a `style=` (e.g., "Light Grid Accent 1") or they render borderless.
6. **Fonts**: Calibri (default), or set `run.font.name = "..."` for custom.
7. **Content depth**: each paragraph ≥ 3-5 sentences, each section ≥ 150-200 words. No shallow sections.
8. **No artificial endings**: never add "End of Document" or similar markers.

## Tracked changes

```python
from docx.oxml.ns import qn
# Add `<w:ins>` wrapper around a run to mark as insertion
# (advanced — see python-docx docs)
```

## Reading existing .docx

```python
doc = Document("input.docx")
for para in doc.paragraphs:
    print(para.text)
for table in doc.tables:
    for row in table.rows:
        print([cell.text for cell in row.cells])
```
