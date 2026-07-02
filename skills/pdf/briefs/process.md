# Brief: Process existing PDFs

Use for: extract text, merge, split, fill forms, convert.

## Extract text

```python
import pdfplumber
with pdfplumber.open("input.pdf") as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        print(text)
```

## Merge multiple PDFs

```python
from pypdf import PdfWriter
writer = PdfWriter()
for path in ["a.pdf", "b.pdf", "c.pdf"]:
    writer.append(path)
with open("merged.pdf", "wb") as f:
    writer.write(f)
```

## Split a PDF

```python
from pypdf import PdfReader, PdfWriter
reader = PdfReader("input.pdf")
for i, page in enumerate(reader.pages):
    writer = PdfWriter()
    writer.add_page(page)
    with open(f"page_{i+1}.pdf", "wb") as f:
        writer.write(f)
```

## Fill a form

```python
from pypdf import PdfReader, PdfWriter
reader = PdfReader("form_template.pdf")
writer = PdfWriter()
writer.append(reader)
writer.update_page_form_field_values(writer.pages[0], {"name": "Alice", "date": "2026-07-03"})
with open("filled.pdf", "wb") as f:
    writer.write(f)
```

## PDF → images

```python
import pdf2image
images = pdf2image.convert_from_path("input.pdf", dpi=200)
for i, img in enumerate(images):
    img.save(f"page_{i+1}.png")
```
