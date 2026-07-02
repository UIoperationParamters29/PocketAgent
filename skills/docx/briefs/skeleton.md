---
name: docx
metadata:
  author: PocketAgent
  version: "1.0"
description: "Create, edit, and analyze Word (.docx) documents. Supports tracked changes, comments, formatting preservation, and text extraction. Use when the user wants a .docx as the final deliverable."
license: MIT
---

# Word (.docx) Document Production

## When to use

User asks for: a report, article, proposal, manuscript, requirements doc, PRD, blog post, or any text deliverable that should be editable in Word.

## How to use

The full skeleton + rules are in this `SKILL.md` (no separate brief needed for the common case).

### Step 1 — Read the skeleton below and follow it exactly.

### Step 2 — Save to `download/` with a descriptive name.

## Skeleton

```python
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

doc = Document()
section = doc.sections[0]
section.top_margin = Cm(2.5); section.bottom_margin = Cm(2.5)
section.left_margin = Cm(2.5); section.right_margin = Cm(2.5)

styles = doc.styles
normal = styles["Normal"]
normal.font.name = "Calibri"
normal.font.size = Pt(11)
normal.paragraph_format.line_spacing = 1.15
normal.paragraph_format.space_after = Pt(6)

# Cover
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run("Document Title")
run.bold = True; run.font.size = Pt(28)
doc.add_paragraph()
doc.add_page_break()   # ONLY page break: cover → body

# Body
doc.add_heading("1. Introduction", level=1)
doc.add_paragraph("Body text here...")

doc.save("/home/z/my-project/download/document.docx")
```

## CRITICAL rules

1. **Page breaks**: ONLY between cover and TOC/body. NEVER mid-content.
2. **Lists**: one item per paragraph (`style="List Bullet"`). NEVER multiple items in one paragraph.
3. **List alignment**: left-align (NOT justify — justify breaks list items).
4. **Headings**: use `doc.add_heading(text, level=N)`.
5. **Tables**: always set `style=` (e.g., "Light Grid Accent 1").
6. **Content depth**: each paragraph ≥ 3-5 sentences, each section ≥ 150-200 words.
7. **No artificial endings**: never add "End of Document" markers.

## Reading existing .docx

```python
doc = Document("input.docx")
for para in doc.paragraphs:
    print(para.text)
for table in doc.tables:
    for row in table.rows:
        print([cell.text for cell in row.cells])
```
