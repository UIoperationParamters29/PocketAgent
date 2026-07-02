# Brief: Data Charts (matplotlib / seaborn)

Use for: bar, line, pie, scatter, heatmap, boxplot, histogram, area, radar, candlestick, waterfall, regression, distribution.

## Template

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt

# Register CJK + Latin fallback fonts (probe first!)
for p in [
    "/usr/share/fonts/truetype/chinese/NotoSansSC-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]:
    try: fm.fontManager.addfont(p)
    except Exception: pass

plt.rcParams["font.sans-serif"] = ["Noto Sans SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

# ---- Build the figure ----
fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
# ... plot ...
ax.set_title("...")
ax.set_xlabel("...")
ax.set_ylabel("...")

# Legend OUTSIDE the plot area
ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", borderaxespad=0)

fig.savefig("/home/z/my-project/download/my_chart.png", dpi=300)
plt.close(fig)
print("saved: /home/z/my-project/download/my_chart.png")
```

## CRITICAL RULES

1. **`constrained_layout=True`** — pass to `plt.subplots()` or `plt.figure()`. NEVER also call `plt.tight_layout()`, `subplots_adjust()`, or pass `bbox_inches='tight'` to `savefig`. These conflict and silently break margins.
2. **`matplotlib.use("Agg")`** at the top — headless backend, no display.
3. **Font registration** — register `Noto Sans SC` (CJK) + `DejaVu Sans` (Latin/symbol fallback). matplotlib 3.9+ does per-glyph fallback when `font.sans-serif` lists multiple.
4. **DPI**: 300 for print/screen, 150 for previews.
5. **Savefig**: do NOT pass `bbox_inches='tight'` — conflicts with `constrained_layout`.

## Common chart recipes

### Bar chart

```python
fig, ax = plt.subplots(figsize=(10, 6), constrained_layout=True)
cats = ["A", "B", "C", "D"]
vals = [23, 45, 12, 67]
ax.bar(cats, vals, color="#10A37F", edgecolor="none")
ax.set_ylabel("Count")
ax.set_title("Category distribution")
fig.savefig("download/bar.png", dpi=300)
```

### Line chart with multiple series

```python
fig, ax = plt.subplots(figsize=(12, 6), constrained_layout=True)
for name, series in data.items():
    ax.plot(series.index, series.values, label=name, linewidth=2)
ax.set_xlabel("Date")
ax.set_ylabel("Value")
ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left", borderaxespad=0)
fig.savefig("download/line.png", dpi=300)
```

### Heatmap (seaborn)

```python
import seaborn as sns
fig, ax = plt.subplots(figsize=(10, 8), constrained_layout=True)
sns.heatmap(matrix, annot=True, fmt=".1f", cmap="YlGnBu", ax=ax,
            cbar_kws={"label": "Intensity"})
fig.savefig("download/heatmap.png", dpi=300)
```

### Scatter with regression

```python
import seaborn as sns
fig, ax = plt.subplots(figsize=(8, 8), constrained_layout=True)
sns.regplot(data=df, x="x", y="y", ax=ax, scatter_kws={"alpha": 0.5},
            line_kws={"color": "red"})
fig.savefig("download/scatter.png", dpi=300)
```

## Palette quick-picks

- Categorical (z.ai style): `["#10A37F", "#3B82F6", "#F59E0B", "#EF4444", "#8B5CF6", "#EC4899"]`
- Sequential: `"viridis"` or `"YlGnBu"`
- Diverging: `"RdBu_r"` or `"coolwarm"`
