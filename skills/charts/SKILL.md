---
name: charts
metadata:
  author: PocketAgent
  version: "1.0"
description: "Professional chart and diagram creation. Covers data charts (bar/line/pie/scatter/heatmap) and structural diagrams (flowchart/mind map/org chart/architecture/ER). Auto-routes by scene: matplotlib/seaborn for data, Mermaid/Playwright+CSS for structural."
license: MIT
---

# Charts — Professional Chart & Diagram Creation

## When to use

Use this skill whenever the user asks to:
- create / draw / plot / generate / visualize a chart, graph, diagram, or dashboard
- make something "more polished" or "publication-ready" as a visual
- transform document content into a chart/diagram

**FORBIDDEN**: do NOT use matplotlib/seaborn for mind maps, tree diagrams, org charts, flowcharts, or any structural diagram — those MUST use Playwright+CSS or Mermaid.

## How to use

### Step 1 — Classify the request

| User wants | Route to | Tool |
|---|---|---|
| Bar / line / pie / scatter / heatmap / boxplot / histogram / area / radar / candlestick / waterfall / regression | `briefs/data_chart.md` | matplotlib or seaborn |
| Flowchart / mind map / tree / org chart / architecture / network / ER / sequence / Gantt / swimlane | `briefs/structural_diagram.md` | Mermaid (simple) or Playwright+CSS (polished) |
| Multi-chart dashboard / KPI panel | `briefs/dashboard.md` | matplotlib grids or D3.js |
| Just a quick sketch | inline Mermaid code block | none |

### Step 2 — Load the matching brief

```
Skill(mode='read', name='charts', file='briefs/data_chart.md')        # for data charts
Skill(mode='read', name='charts', file='briefs/structural_diagram.md') # for structural
Skill(mode='read', name='charts', file='briefs/dashboard.md')         # for dashboards
```

### Step 3 — Follow the brief

Each brief contains:
- the exact Python/JS code template to use
- the color palette and typography rules
- the anti-overlap and layout-hygiene rules
- how to save the output (always to `download/`)

## Anti-overlap rules (MANDATORY)

1. **Layout engine**: every matplotlib figure MUST pass `constrained_layout=True` to `plt.subplots()` or `plt.figure()`. NEVER also call `plt.tight_layout()` or `subplots_adjust()` — they conflict.
2. **Legends**: prefer `bbox_to_anchor` to place legends OUTSIDE the plot area, not `loc='best'` (which lands on data).
3. **Truncation**: never truncate labels silently — rotate or wrap them.
4. **Fonts**: for Chinese text, use `Noto Sans SC` (with DejaVu Sans fallback). Probe first: `ls /usr/share/fonts/truetype/chinese/`.

## Output

- Save all images to `download/` as PNG (300 DPI for data, 2x for structural).
- Use descriptive filenames: `sales_q3_bar.png`, not `chart1.png`.
- After saving, tell the user the absolute path.

## Files in this skill

- `briefs/data_chart.md` — bar/line/pie/scatter/heatmap/boxplot templates (matplotlib/seaborn)
- `briefs/structural_diagram.md` — flowchart/mind map/org/architecture/ER (Mermaid + Playwright+CSS)
- `briefs/dashboard.md` — multi-chart dashboards
- `configs/palettes.md` — curated color palettes (categorical, sequential, diverging)
- `scripts/` — reusable plotting helpers
- `references/` — anti-overlap patterns, font fallback chains
