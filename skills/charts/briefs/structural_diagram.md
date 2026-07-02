# Brief: Structural Diagrams (Mermaid + Playwright+CSS)

Use for: flowchart, mind map, tree, org chart, architecture, network, ER, sequence, Gantt, swimlane.

## FORBIDDEN

Do NOT use matplotlib/seaborn for ANY structural diagram. They produce wrong output. Use Mermaid (simple) or Playwright+CSS (polished).

## Route by complexity

| Need | Tool |
|---|---|
| Quick sketch, text-only output acceptable | Mermaid code block (no rendering) |
| Need a PNG/SVG image, simple structure | Mermaid + Playwright snapshot |
| Polished, branded, complex layout | Playwright + hand-written CSS + HTML |

## Template 1 — Mermaid + Playwright snapshot

```python
import asyncio
from playwright.async_api import async_playwright

MERMAID_CODE = """
flowchart LR
    A[User] --> B[Phone APK]
    B -->|WSS| C[Codespace]
    C --> D[Agent Runtime]
    D --> E[LLM Provider]
"""

async def render():
    html = f"""
    <!doctype html><html><head>
    <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
    <style>body {{ margin: 0; padding: 24px; background: #fff; }}
    .mermaid {{ font-family: 'Inter', sans-serif; }}</style>
    </head><body>
    <div class="mermaid">{MERMAID_CODE}</div>
    <script>mermaid.initialize({{startOnLoad: true, theme: 'neutral'}});</script>
    </body></html>
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 800})
        await page.set_content(html)
        await page.wait_for_selector(".mermaid svg", timeout=10_000)
        await page.screenshot(path="/home/z/my-project/download/diagram.png", full_page=True)
        await browser.close()

asyncio.run(render())
```

## Template 2 — Hand-built CSS layout (for org charts, architecture diagrams)

```python
import asyncio
from playwright.async_api import async_playwright

HTML = """
<!doctype html><html><head><style>
  body { margin: 0; padding: 40px; background: #0E0E10; font-family: 'Inter', sans-serif; color: #FAFAFA; }
  .row { display: flex; gap: 24px; justify-content: center; margin-bottom: 24px; }
  .box { background: #18181B; border: 1px solid #27272A; border-radius: 10px;
         padding: 16px 24px; min-width: 140px; text-align: center; }
  .box.accent { border-color: #10A37F; }
  .box h3 { margin: 0 0 4px 0; font-size: 14px; font-weight: 600; }
  .box p { margin: 0; font-size: 12px; color: #A1A1AA; }
  .arrow { text-align: center; color: #71717A; font-size: 24px; line-height: 1; margin: -8px 0; }
</style></head><body>
  <div class="row">
    <div class="box accent"><h3>Phone</h3><p>Expo APK</p></div>
  </div>
  <div class="arrow">↓</div>
  <div class="row">
    <div class="box"><h3>Codespace</h3><p>GitHub</p></div>
    <div class="box"><h3>Runtime</h3><p>FastAPI</p></div>
  </div>
</body></html>
"""

async def render():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(HTML)
        await page.screenshot(path="/home/z/my-project/download/arch.png", full_page=True)
        await browser.close()

asyncio.run(render())
```

## Rules

1. **Background**: white for print, dark `#0E0E10` for branded.
2. **Font**: Inter for UI, JetBrains Mono for code labels.
3. **Snapshot**: always `full_page=True` so the diagram isn't cropped.
4. **Wait**: for Mermaid, always `wait_for_selector(".mermaid svg")` before snapshotting.
5. **Output**: save to `download/` as PNG (2x device pixel ratio for retina).

## When to skip rendering

If the user just wants the diagram source (e.g., "give me the Mermaid for X"), output the code block in your message — don't snapshot. Only render when they explicitly want a PNG/SVG file.
