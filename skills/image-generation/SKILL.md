---
name: image-generation
metadata:
  author: PocketAgent
  version: "1.0"
description: "Generate images from text descriptions using AI. Supports multiple sizes; returns OSS-hosted direct URLs. Use when the user wants to create images, artwork, design assets, or any visual from a text prompt."
license: MIT
---

# Image Generation

## When to use

User asks to: create an image, generate a picture, make artwork, design an asset, draw something from a text description.

## How to use

### Option A — z-ai-web-dev-sdk CLI (preferred; available in the codespace)

```bash
# Install once
npm install z-ai-web-dev-sdk

# Generate
npx z-ai-web-dev-sdk image-generation \
  --prompt "A serene mountain lake at sunset, photorealistic" \
  --size 1024x1024 \
  --output /home/z/my-project/download/image.png
```

### Option B — Python via HTTP

If the SDK isn't available, the agent can shell out to a hosted API. Replace `<KEY>` with the user's key (NEVER log it).

```python
import base64, httpx, os

r = httpx.post(
    "https://api.z.ai/api/pallet/v1/images/generations",
    headers={"Authorization": f"Bearer {os.environ['ZAI_API_KEY']}"},
    json={
        "model": "cogview-3-plus",
        "prompt": "A serene mountain lake at sunset, photorealistic",
        "size": "1024x1024",
    },
    timeout=120,
)
data = r.json()
# Save the image (data URL or OSS URL depending on API)
if "data" in data and data["data"]:
    item = data["data"][0]
    if item.get("url"):
        img_bytes = httpx.get(item["url"]).content
    elif item.get("b64_json"):
        img_bytes = base64.b64decode(item["b64_json"])
    with open("/home/z/my-project/download/image.png", "wb") as f:
        f.write(img_bytes)
    print("saved: /home/z/my-project/download/image.png")
```

## Sizes

Common supported sizes:
- `1024x1024` (square, default)
- `1024x1792` (portrait)
- `1792x1024` (landscape)
- `768x768` (smaller, faster)

## Prompt tips

- Be specific about style: "photorealistic", "oil painting", "watercolor", "3D render", "flat design vector"
- Specify composition: "wide-angle", "close-up", "top-down", "isometric"
- Include lighting: "golden hour", "studio lighting", "soft natural light"
- Negative prompts (if API supports): "no text, no watermark"

## Output

- Save to `download/` as PNG.
- Use descriptive filenames: `mountain_lake_sunset.png`, not `image1.png`.
- After saving, return the absolute path so the user can find it on their phone (the Files screen will list it).
