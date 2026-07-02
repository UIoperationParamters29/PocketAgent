# Brief: Creative PDFs (Playwright + CSS)

Use for: posters, infographics, single-page visual designs, branded dashboards, invitations, certificates.

## Approach

The LLM acts as Art Director: output a JSON spatial blueprint describing boxes, then compile to a pixel-perfect PDF via Playwright snapshot.

## Step 1 — Author the HTML+CSS

Write a single HTML file with embedded CSS. Use:
- `flexbox` / `grid` for layout
- Custom fonts via `@font-face` or Google Fonts (Noto Sans SC for CJK)
- `background`, `border-radius`, `box-shadow` freely
- A fixed `viewport` matching the target page size

## Step 2 — Snapshot via Playwright

```python
import asyncio
from playwright.async_api import async_playwright

HTML = """
<!doctype html><html><head><style>
  @page { size: A4 landscape; margin: 0; }
  body { margin: 0; font-family: 'Inter', 'Noto Sans SC', sans-serif; }
  .poster { width: 297mm; height: 210mm; background: linear-gradient(135deg, #0E0E10, #18181B);
            color: #FAFAFA; padding: 32mm; box-sizing: border-box;
            display: flex; flex-direction: column; justify-content: space-between; }
  h1 { font-size: 56pt; margin: 0; font-weight: 800; line-height: 1.1; }
  .accent { color: #10A37F; }
  .meta { font-size: 14pt; color: #A1A1AA; }
</style></head><body>
  <div class="poster">
    <div>
      <h1>Welcome to <span class="accent">PocketAgent</span></h1>
      <p class="meta">Your AI, with its own computer, on your phone.</p>
    </div>
    <div class="meta">2026 · v0.1</div>
  </div>
</body></html>
"""

async def render():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(HTML, wait_until="networkidle")
        await page.pdf(
            path="/home/z/my-project/download/poster.pdf",
            format="A4", landscape=True, print_background=True,
            margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
        )
        await browser.close()

asyncio.run(render())
```

## Rules

1. **`@page { margin: 0; }`** — content fills the page edge-to-edge.
2. **`print_background=True`** — without this, gradients and bg colors vanish.
3. **`wait_until="networkidle"`** — wait for fonts to load.
4. **Custom fonts**: use Google Fonts (`<link>`) or `@font-face`. Always include `font-display: swap`.
5. **CJK**: include `'Noto Sans SC', 'Noto Serif SC'` in font-family stacks.
6. **Emoji**: ALLOWED here (unlike ReportLab). Render via system emoji font.
7. **Fixed dimensions**: use `mm` units matching the target page size for predictable layout.
