---
name: pdf
metadata:
  author: PocketAgent
  version: "1.0"
description: "Professional PDF toolkit. Four production lines: (1) Report — structured docs via ReportLab; (2) Creative — visual design via JSON Blueprint → Playwright snapshot; (3) Academic — LaTeX/Tectonic for math-heavy papers; (4) Process — extract/merge/split/fill existing PDFs."
license: MIT
---

# PDF — Document Production Workbench

## When to use

User asks for any PDF deliverable: report, proposal, white paper, contract, resume, poster, infographic, academic paper, form-fill, merge/split.

## How to use

### Step 1 — Triage the request

| User wants | Route to |
|---|---|
| Multi-page report / proposal / white paper / contract / analysis | `briefs/report.md` (ReportLab) |
| Poster / infographic / invitation / dashboard / single-page visual | `briefs/creative.md` (Playwright) |
| Academic paper / thesis / math-heavy document | `briefs/academic.md` (LaTeX/Tectonic) |
| Extract / merge / split / fill form / convert existing PDF | `briefs/process.md` (pypdf/pdfplumber) |
| Resume | `briefs/resume.md` (ATS or creative) |

### Step 2 — Pre-routing checks (run BEFORE matching brief)

1. **Emoji check** — if user content has decorative emoji (📊🎯🔥), force Creative pipeline (ReportLab renders emoji as □).
2. **CJK check** — Chinese/Japanese/Korean needs NotoSerifSC body / Noto Sans SC headings. Probe: `ls /usr/share/fonts/truetype/chinese/`.
3. **Size check** — non-standard page sizes (not A4/Letter/A3) → Creative (Playwright handles any dimension).
4. **Character safety** — replace rare Unicode with plain equivalents to avoid encoding corruption.

### Step 3 — Load the brief

```
Skill(mode='read', name='pdf', file='briefs/report.md')      # for reports
Skill(mode='read', name='pdf', file='briefs/creative.md')    # for posters
Skill(mode='read', name='pdf', file='briefs/academic.md')    # for papers
Skill(mode='read', name='pdf', file='briefs/process.md')     # for processing
Skill(mode='read', name='pdf', file='briefs/resume.md')      # for resumes
```

### Step 4 — Follow the brief

Each brief contains:
- the exact code template
- font registration rules
- the page-break rule (only between cover and TOC, or cover and body)
- the character-safety rule (no Unicode escapes; use ReportLab tags)

## Output

- Save all PDFs to `download/` with descriptive names.
- Use `report_*.pdf`, `poster_*.pdf`, `paper_*.pdf` prefixes.

## Character safety (CRITICAL)

All text in PDFs must come from:
- CJK characters rendered by registered Chinese fonts (NotoSerifSC body / Noto Sans SC headings)
- Mathematical operators used as literal characters (e.g., `+ − × ÷ ± ≤ √ ∑ ≅ ∫ π ∠`)
- ASCII letters and digits

**FORBIDDEN** — never emit these as Unicode escapes in code:
- Superscript/subscript digits (`\u00b2`, `\u2082`) — use `<super>` / `<sub>` tags in `Paragraph()`
- Math operators as escapes (`\u2245`, `\u2212`) — use the literal character
- Emoji (`\u2728`, `\u2705`) — Creative pipeline only

| Need | Correct |
|---|---|
| Superscript | `Paragraph('10<super>2</super>', style)` |
| Subscript | `Paragraph('H<sub>2</sub>O', style)` |
| Bold | `Paragraph('<b>Title</b>', style)` |
| Math op | `Paragraph('AB ⊥ AC, ∠A = 90°', style)` |
| Sci notation | `Paragraph('1.2 × 10<super>8</super> kg/m<super>3</super>', style)` |

## Page-break rule

Page breaks are ONLY allowed:
- Between cover page and TOC (if TOC exists)
- Between cover page and main content (if no TOC)
- Between TOC and main content

All content after the TOC flows continuously WITHOUT page breaks. Do NOT insert manual page breaks mid-content.

## Files

- `briefs/report.md` — ReportLab structured docs
- `briefs/creative.md` — Playwright JSON Blueprint → snapshot
- `briefs/academic.md` — LaTeX/Tectonic
- `briefs/process.md` — pypdf/pdfplumber
- `briefs/resume.md` — ATS / creative resumes
- `configs/fonts.md` — font registration recipes
