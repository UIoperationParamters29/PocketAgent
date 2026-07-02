# Brief: Dashboards (multi-chart compositions)

Use for: KPI panels, multi-chart reports, interactive-looking visual summaries.

## Approach

1. Use `matplotlib` with `GridSpec` for static PNG dashboards.
2. Use ECharts/D3.js + Playwright snapshot for interactive-looking polished dashboards.

## Template — matplotlib GridSpec

```python
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

fig = plt.figure(figsize=(16, 9), constrained_layout=True)
gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.3, wspace=0.3)

ax_kpi1 = fig.add_subplot(gs[0, 0])
ax_kpi2 = fig.add_subplot(gs[0, 1])
ax_kpi3 = fig.add_subplot(gs[0, 2])
ax_chart1 = fig.add_subplot(gs[1, :2])
ax_chart2 = fig.add_subplot(gs[1, 2])

# KPI cards (text-only axes)
for ax, label, value in [(ax_kpi1, "Revenue", "$1.2M"), (ax_kpi2, "Users", "12,450"), (ax_kpi3, "Churn", "2.3%")]:
    ax.axis("off")
    ax.text(0.5, 0.7, label, ha="center", fontsize=11, color="#71717A", transform=ax.transAxes)
    ax.text(0.5, 0.3, value, ha="center", fontsize=24, fontweight="bold", color="#10A37F", transform=ax.transAxes)

# ... fill ax_chart1 and ax_chart2 with real charts ...

fig.savefig("/home/z/my-project/download/dashboard.png", dpi=200)
```

## Template — ECharts + Playwright (polished)

For interactive-looking dashboards, write an HTML file with ECharts then snapshot it. See `scripts/render_echarts.py` for a reusable helper.
