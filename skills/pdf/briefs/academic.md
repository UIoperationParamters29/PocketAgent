# Brief: Academic PDFs (LaTeX / Tectonic)

Use for: papers, theses, math-heavy documents, anything with citations/bibliography.

## Skeleton

```latex
\\documentclass[11pt]{article}
\\usepackage[utf8]{inputenc}
\\usepackage{amsmath, amssymb, amsthm}
\\usepackage{graphicx}
\\usepackage{hyperref}
\\usepackage[margin=1in]{geometry}
\\usepackage{ctex}   % for Chinese; remove if English-only

\\title{Paper Title}
\\author{Author Name}
\\date{\\today}

\\begin{document}
\\maketitle

\\begin{abstract}
Abstract text here...
\\end{abstract}

\\section{Introduction}
Body text. Math: $E = mc^2$. Display math:
\\begin{equation}
  \\int_0^\\infty e^{-x^2} \\, dx = \\frac{\\sqrt{\\pi}}{2}
\\end{equation}

\\section{Related Work}
...

\\bibliographystyle{plain}
\\bibliography{refs}

\\end{document}
```

## Compile

```bash
tectonic paper.tex
# produces paper.pdf
```

`tectonic` is preferred over `pdflatex` because it auto-downloads packages and handles CJK cleanly. If unavailable, fall back to `pdflatex --shell-escape paper.tex` (run twice for refs).

## Rules

1. **Math**: use `$...$` for inline, `\\begin{equation}...\\end{equation}` for display. NEVER use Unicode math symbols in source — LaTeX has macros for everything.
2. **CJK**: `\usepackage{ctex}` handles Chinese. For Japanese, use `pxjahcar`; for Korean, `kotex`.
3. **Bibliography**: BibTeX `.bib` file + `\bibliographystyle{plain}` + `\bibliography{refs}`. Run `bibtex` then `latex` twice.
4. **Tables**: use `tabular` environment; for complex tables use `booktabs`.
5. **Figures**: `\includegraphics[width=\linewidth]{fig.png}` inside `figure` env with `\caption` and `\label`.
