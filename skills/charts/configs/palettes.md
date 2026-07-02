# Curated color palettes

## Categorical (max 8 series)

### z.ai (default)
```
#10A37F  #3B82F6  #F59E0B  #EF4444  #8B5CF6  #EC4899  #14B8A6  #F97316
```

### Tableau 10
```
#4E79A7  #F28E2B  #E15759  #76B7B2  #59A14F  #EDC948  #B07AA1  #FF9DA7
```

### Okabe-Ito (colorblind-safe)
```
#000000  #E69F00  #56B4E9  #009E73  #F0E442  #0072B2  #D55E00  #CC79A7
```

## Sequential

- Viridis (default for seaborn heatmaps): perceptually uniform, colorblind-safe
- YlGnBu: yellow → green → blue (good for intensity)
- Blues: single-hue (good for "confidence" scales)

## Diverging

- RdBu_r: red → white → blue (good for correlations, sentiment)
- coolwarm: similar, slightly more saturated

## When to use which

- ≤4 series, all positive: z.ai palette
- 5–8 series: Tableau 10
- Accessibility required: Okabe-Ito
- Heatmap intensity: YlGnBu
- Correlation matrix: RdBu_r with `vmin=-1, vmax=1, center=0`
