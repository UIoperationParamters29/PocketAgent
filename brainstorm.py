"""Brainstorm session: me (z.ai GLM) + Claude Fable 5, discussing how to ship
PocketAgent as a phone APK with an AI 'mini-computer' that has full Linux +
network access — avoiding the persistent Android permission failures the user
hit in past attempts, and matching z.ai agentic mode as closely as possible.

Format: I ask a question, Claude responds, I respond, etc. Multi-turn.
"""
import httpx, json, sys

BASE_URL = "https://api.gateway.orgn.com/v1"
API_KEY = "sk-ollm-g1IDxLLVhFbO-mZLJfLIURm2sFThisIaWioS7hcxfopaVzZjx1SQRoMPUuvlY"
CLAUDE = "vercel_claude_fable_5"
GLM = "near_glm_5"  # me

def call_llm(model, messages, max_tokens=2000):
    with httpx.Client(timeout=120) as c:
        r = c.post(f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.7})
    if r.status_code != 200:
        return f"[ERROR {r.status_code}] {r.text[:200]}"
    return r.json()["choices"][0]["message"]["content"]

# The setup
CONTEXT = """We're building PocketAgent — a phone app that replicates z.ai agentic mode on the user's phone, using their own LLM API keys. The agent needs its own 'mini-computer' with full Linux + network access so it can run bash commands, install packages, write files, call APIs — exactly like z.ai agentic mode.

CONSTRAINTS:
- Must ship as an APK the user can sideload
- NO credit card anywhere (user has been blocked by Render, Koyeb, Fly.io, Oracle, Modal)
- The user's LLM endpoint is api.gateway.orgn.com (a custom gateway, not standard OpenAI)
- User has tried 'local storage dedication' on Android in the past — persistent failures due to Android permissions (storage, network, background execution limits)
- The agent needs to feel like z.ai agentic mode: full Linux, persistent workspace, can do anything

WHAT WE'VE TRIED + WHY IT FAILED:
1. GitHub Codespaces — port-forward URL requires opening codespace in browser first
2. Daytona — free $200 credit, no CC, BUT blocks api.gateway.orgn.com (IP allowlist)
3. Render — requires CC verification
4. Modal — only $1/month free now
5. Past Android local-storage attempts — permission failures

WHAT WORKS (proven):
- The agent logic + LLM + tools all work perfectly together (we tested with you — you built a full sales dashboard with charts in 12 iterations)
- The phone has working internet to api.gateway.orgn.com
- HF Spaces: free, no CC, 2 vCPU/16GB, 48hr sandbox, public URL immediately, allows outbound HTTPS

THE USER'S LATEST IDEA: They're open to dedicating space ON THE PHONE itself to give the AI a 'mini-computer' with full access. They tried this in the past but hit persistent Android permission failures. They want to know if there's a creative way to make this work without the permission hell.

Please brainstorm with me. Be creative. Consider:
- Termux (Android terminal emulator) as the agent's computer
- Proot/chroot on Android (rootless Linux env)
- UserLAnd / Andronix (Linux-on-Android apps)
- A hybrid: phone runs the agent loop, cloud runs the tools
- Architectural flips (phone calls LLM, cloud executes tools)
- Anything else creative

The goal: the most z.ai-agentic-mode-like experience, that won't break in persistent failures. What's the BEST path?"""

conversation = [
    {"role": "system", "content": "You are Claude Fable 5, a senior AI engineer brainstorming with another AI engineer (z.ai GLM) about how to ship a phone-based AI agent app. Be creative, specific, and honest about trade-offs. Don't just list options — engage with the other AI's ideas, build on them, push back when needed. This is a real conversation, not a Q&A."},
    {"role": "user", "content": CONTEXT + "\n\n---\n\nLet's brainstorm. I'll start: my current best idea is the 'architectural flip' — phone runs the agent loop + calls the LLM directly, cloud (HF Spaces) is just a dumb tool executor. But the user is now asking about running the whole thing ON the phone. What's your honest take on Termux/proot/UserLAnd as the agent's computer? Is it viable, or will Android permission hell kill it again?"},
]

print("=" * 70)
print("🧠 BRAINSTORM SESSION: z.ai GLM × Claude Fable 5")
print("=" * 70)
print()
print("📝 Topic: How to ship PocketAgent as a phone APK with a full Linux")
print("   'mini-computer' for the AI — avoiding Android permission failures")
print()

# Round 1: Claude responds to the setup
print("─" * 70)
print("CLAUDE FABLE 5:")
print("─" * 70)
claude_reply = call_llm(CLAUDE, conversation)
print(claude_reply)
conversation.append({"role": "assistant", "content": claude_reply})

# Round 2: GLM (me) responds
print()
print("─" * 70)
print("z.ai GLM (me):")
print("─" * 70)
conversation.append({"role": "user", "content": "Respond to Claude's analysis. Be honest — where do you agree, where do you push back? What's the most pragmatic path? Remember the user has been burned by permission failures before, so reliability matters more than elegance."})
glm_reply = call_llm(GLM, conversation)
print(glm_reply)
conversation.append({"role": "assistant", "content": glm_reply})

# Round 3: Claude responds
print()
print("─" * 70)
print("CLAUDE FABLE 5:")
print("─" * 70)
conversation.append({"role": "user", "content": "Respond to GLM's take. If you two are converging on an answer, articulate it clearly. If not, push back. What's the actual recommendation we'd give the user?"})
claude_reply2 = call_llm(CLAUDE, conversation)
print(claude_reply2)
conversation.append({"role": "assistant", "content": claude_reply2})

# Round 4: GLM synthesizes
print()
print("─" * 70)
print("z.ai GLM (me) — synthesis:")
print("─" * 70)
conversation.append({"role": "user", "content": "Synthesize the conversation into a final recommendation for the user. Be specific about the architecture, the steps, and why it won't break. The user is frustrated and needs a path that WILL work."})
final = call_llm(GLM, conversation)
print(final)
