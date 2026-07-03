"""Get Claude Fable 5's review of the PocketAgent runtime — streaming version."""
import httpx, json, sys
from pathlib import Path

BASE_URL = "https://api.gateway.orgn.com/v1"
API_KEY = "sk-ollm-g1IDxLLVhFbO-mZLJfLIURm2sFThisIaWioS7hcxfopaVzZjx1SQRoMPUuvlY"
MODEL = "vercel_claude_fable_5"

def get_review(files: dict[str, str], focus: str) -> str:
    files_block = "\n\n".join(f"--- {name} ---\n{content[:6000]}" for name, content in files.items())

    system = f"""You are Claude Fable 5, a senior code reviewer. Review PocketAgent — a phone app that replicates z.ai agentic mode using Termux as the agent's Linux computer on the phone.

Architecture: APK (thin UI) ←HTTP ws://127.0.0.1:8080→ Termux (runs full agent: LLM calls + tools + workspace)

FOCUS: {focus}

For each issue:
1. Severity: 🔴 critical / 🟡 important / 🟢 nice-to-have
2. File + function
3. What's wrong
4. Exact fix

End with: VERDICT: SHIP IT  or  VERDICT: FIX FIRST"""

    user_msg = f"Review these files:\n\n{files_block}\n\nGive me a structured review."

    content = ""
    with httpx.Client(timeout=300) as c:
        with c.stream("POST", f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user_msg}], "stream": True, "max_tokens": 4000, "temperature": 0.3}) as r:
            if r.status_code != 200:
                return f"[ERROR {r.status_code}] {r.read().decode()[:300]}"
            for line in r.iter_lines():
                if not line or not line.startswith("data: "): continue
                data = line[6:]
                if data == "[DONE]": break
                try:
                    chunk = json.loads(data)
                    if chunk.get("choices"):
                        delta = chunk["choices"][0].get("delta", {})
                        if delta.get("content"):
                            content += delta["content"]
                            print(delta["content"], end="", flush=True)
                except: pass
    return content

if __name__ == "__main__":
    focus = sys.argv[1] if len(sys.argv) > 1 else "bugs, Termux compatibility, security, z.ai parity"
    files = {}
    for fp in ["runtime-pkg/pocketagent/server.py", "runtime-pkg/pocketagent/cli.py", "phone/src/screens/ChatScreen.tsx", "phone/src/screens/OnboardingScreen.tsx"]:
        p = Path(fp)
        if p.exists():
            files[fp] = p.read_text(errors="replace")
    print(f"=== Claude Fable 5 reviewing: {focus} ===")
    print(f"Files: {list(files.keys())}")
    print()
    review = get_review(files, focus)
    Path("/tmp/claude_review.md").write_text(review)
    print(f"\n\n[Saved to /tmp/claude_review.md]")
