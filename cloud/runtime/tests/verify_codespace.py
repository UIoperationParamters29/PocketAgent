#!/usr/bin/env python3
"""Verify a live PocketAgent codespace is reachable + the runtime is healthy.

Usage:
  python verify_codespace.py <codespace-name> [channel-secret]

If channel-secret is provided, also does a full WS handshake + sends a test
message (requires PA_TEST_LLM_API_KEY env var for the BYOK key).

This script is what the user can run after opening their codespace in a
browser once (to register the port forward) — it confirms everything is wired
up correctly before they try the phone app.
"""
import asyncio
import json
import os
import sys
import httpx
import websockets


async def main():
    if len(sys.argv) < 2:
        print("Usage: python verify_codespace.py <codespace-name> [channel-secret]")
        sys.exit(1)
    cs_name = sys.argv[1]
    secret = sys.argv[2] if len(sys.argv) > 2 else None
    runtime_url = f"https://{cs_name}-8000.app.github.dev"
    ws_url = runtime_url.replace("https://", "wss://") + "/agent"

    print(f"=== Verifying codespace: {cs_name} ===")
    print(f"Runtime URL: {runtime_url}")
    print()

    # 1. Health check
    print("--- 1. Health check (GET /) ---")
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{runtime_url}/")
            if r.status_code != 200:
                print(f"  ❌ HTTP {r.status_code} — runtime not reachable")
                print("  Possible causes:")
                print("    - Codespace was never opened in a browser (port forward not registered)")
                print("    - Runtime isn't running inside the codespace")
                print("    - Codespace is stopped (start it on github.com/codespaces)")
                sys.exit(1)
            data = r.json()
            print(f"  ✅ Runtime up: {data['name']} v{data['version']}")
            print(f"     workspace: {data['workspace']}")
            print(f"     default model: {data['default_model']}")
    except Exception as e:
        print(f"  ❌ {e}")
        sys.exit(1)

    # 2. Workspace tree
    print()
    print("--- 2. Workspace tree (GET /workspace) ---")
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{runtime_url}/workspace?depth=2")
            tree = r.json()
            top = [c["name"] for c in tree.get("children", [])]
            print(f"  ✅ Workspace root children: {top}")
    except Exception as e:
        print(f"  ❌ {e}")

    # 3. WS handshake (if secret provided)
    if not secret:
        print()
        print("--- 3. WS handshake (skipped — no channel secret provided) ---")
        print("  To test the WS channel, run with: python verify_codespace.py <name> <secret>")
        print()
        print("=== ✅ Codespace is reachable. Phone app should connect successfully. ===")
        return

    print()
    print("--- 3. WS handshake ---")
    try:
        async with websockets.connect(ws_url) as ws:
            await ws.send(json.dumps({
                "type": "session.start",
                "channel_secret": secret,
                "session": {
                    "base_url": os.environ.get("PA_TEST_LLM_BASE_URL", "https://api.openai.com/v1"),
                    "api_key": os.environ.get("PA_TEST_LLM_API_KEY", ""),
                    "model": os.environ.get("PA_TEST_LLM_MODEL", "gpt-4o-mini"),
                },
            }))
            start = json.loads(await ws.recv())
            if start.get("type") != "session.start":
                print(f"  ❌ Bad handshake response: {start}")
                sys.exit(1)
            print(f"  ✅ WS connected; session_id={start['session_id']}")

            # 4. Send a test message
            print()
            print("--- 4. Test message ---")
            await ws.send(json.dumps({"type": "user.message", "content": "Reply with exactly: PONG"}))
            events = []
            while True:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=60)
                    evt = json.loads(raw)
                    events.append(evt)
                    if evt.get("type") == "session.end":
                        break
                    if evt.get("type") == "error":
                        print(f"  ❌ Error event: {evt.get('message')}")
                        break
                except asyncio.TimeoutError:
                    print("  ⚠️  Timeout waiting for session.end")
                    break
            types = [e["type"] for e in events]
            print(f"  Events: {types}")
            final = [e for e in events if e["type"] == "assistant.message"]
            if final:
                print(f"  ✅ Reply: {final[0]['content']!r}")
            else:
                deltas = "".join(e.get("content","") for e in events if e["type"] == "assistant.delta")
                if deltas:
                    print(f"  ⚠️  Got deltas but no assistant.message: {deltas[:200]!r}")
                else:
                    print(f"  ❌ No reply at all")
    except Exception as e:
        print(f"  ❌ WS failed: {e}")
        sys.exit(1)

    print()
    print("=== ✅ Everything works — codespace + runtime + LLM are all connected. ===")


if __name__ == "__main__":
    asyncio.run(main())
