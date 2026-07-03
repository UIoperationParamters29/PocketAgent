---
name: web-search
metadata:
  author: PocketAgent
  version: "1.0"
description: "Search the web for real-time information beyond the model's knowledge cutoff. Returns structured results with URLs, snippets, and metadata. Use when the user needs current news, latest data, or facts you're unsure of."
license: MIT
---

# Web Search

## When to use

User asks for: current news, latest data, real-time prices, recently-released info, anything that might be newer than your training cutoff, or anything you're not 100% sure about.

## How to use

### Option A — z-ai-web-dev-sdk CLI (preferred)

```bash
npx z-ai-web-dev-sdk web-search \
  --query "latest OpenAI GPT-5 release date" \
  --num 5
```

Returns JSON:
```json
{
  "results": [
    {"title": "...", "url": "...", "snippet": "...", "published_at": "..."},
    ...
  ]
}
```

### Option B — Python via httpx

```python
import httpx, os, json

r = httpx.get(
    "https://api.z.ai/api/pallet/v1/web_search",
    headers={"Authorization": f"Bearer {os.environ['ZAI_API_KEY']}"},
    params={"query": "latest OpenAI GPT-5 release date", "num": 5},
    timeout=30,
)
results = r.json()
for item in results.get("results", []):
    print(f"- {item['title']}")
    print(f"  {item['url']}")
    print(f"  {item['snippet'][:200]}")
    print()
```

### Option C — DuckDuckGo HTML (no key required, fallback)

```python
import httpx
from bs4 import BeautifulSoup

r = httpx.get("https://html.duckduckgo.com/html/", params={"q": "query here"}, timeout=15)
soup = BeautifulSoup(r.text, "html.parser")
for result in soup.select(".result"):
    title = result.select_one(".result__title").get_text(strip=True)
    url = result.select_one(".result__url").get_text(strip=True)
    snippet = result.select_one(".result__snippet").get_text(strip=True)
    print(f"- {title}\n  {url}\n  {snippet}\n")
```

## Rules

1. **Always cite sources** in your final answer — include the URL.
2. **Cross-check** — don't trust a single source for factual claims; find 2+.
3. **Note the date** — search results have `published_at`; mention if info is stale.
4. **Don't fabricate** — if search returns nothing useful, say so. Never invent URLs.
5. **Be specific** — `"GPT-5 release date site:openai.com"` is better than `"GPT-5"`.

## Output

Return a concise summary with inline citations:
```
According to OpenAI's announcement [1], GPT-5 was released on...
Sources:
[1] https://openai.com/blog/gpt-5
[2] https://techcrunch.com/2026/...
```
