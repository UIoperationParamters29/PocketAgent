"""Summon Claude Opus 4.8 as master reviewer/improver for PocketAgent.

Gives it:
  - Full project context (architecture, goals, what we've tried)
  - All 8 tools (Bash, Read, Write, Edit, Glob, Grep, LS, TodoWrite)
  - The PocketAgent repo as its workspace
  - A mandate: polish UI/UX, fix bugs, improve functionality

We just monitor + stream what it does, then verify + ship.
"""
import httpx, json, subprocess, os, sys, time
from pathlib import Path
from typing import Any

BASE_URL = "https://api.gateway.orgn.com/v1"
API_KEY = "sk-ollm-FO2QJqW6ioPI-wBAiuesqgHD0jDjh4eBttpvxoZemGeltpcozkaLcCrk89Hqu"
MODEL = "vercel_claude_opus_4_8"  # less costly than Fable 5
WORKSPACE = Path("/home/z/my-project/pocketagent")

TOOLS = [
    {"type":"function","function":{"name":"Bash","description":"Execute a bash command in the PocketAgent repo. Full Linux. You can run tests, check types, install deps, git, anything.","parameters":{"type":"object","properties":{"command":{"type":"string"},"timeout":{"type":"integer","default":120}},"required":["command"]}}},
    {"type":"function","function":{"name":"Read","description":"Read a file from the PocketAgent repo.","parameters":{"type":"object","properties":{"file_path":{"type":"string"},"offset":{"type":"integer","default":0},"limit":{"type":"integer","default":2000}},"required":["file_path"]}}},
    {"type":"function","function":{"name":"Write","description":"Create or overwrite a file in the PocketAgent repo. Use this to fix bugs or improve code.","parameters":{"type":"object","properties":{"file_path":{"type":"string"},"content":{"type":"string"}},"required":["file_path","content"]}}},
    {"type":"function","function":{"name":"Edit","description":"Exact string replacement in an existing file. Use this for surgical fixes.","parameters":{"type":"object","properties":{"file_path":{"type":"string"},"old_str":{"type":"string"},"new_str":{"type":"string"},"replace_all":{"type":"boolean","default":False}},"required":["file_path","old_str","new_str"]}}},
    {"type":"function","function":{"name":"Glob","description":"Find files by name pattern.","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string","default":"."}},"required":["pattern"]}}},
    {"type":"function","function":{"name":"Grep","description":"Search file contents.","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string","default":"."},"ignore_case":{"type":"boolean","default":False}},"required":["pattern"]}}},
    {"type":"function","function":{"name":"LS","description":"List directory contents.","parameters":{"type":"object","properties":{"path":{"type":"string"}},"required":["path"]}}},
    {"type":"function","function":{"name":"TodoWrite","description":"Update your todo list.","parameters":{"type":"object","properties":{"todos":{"type":"array","items":{"type":"object","properties":{"id":{"type":"string"},"content":{"type":"string"},"status":{"type":"string","enum":["pending","in_progress","completed"]},"priority":{"type":"string","enum":["high","medium","low"]}},"required":["id","content","status","priority"]}}},"required":["todos"]}}},
]

def resolve(p):
    path = Path(p)
    if not path.is_absolute(): path = WORKSPACE / path
    return path.resolve()

def exec_tool(name, args):
    try:
        if name == "Bash":
            r = subprocess.run(args["command"], shell=True, cwd=WORKSPACE, capture_output=True, text=True, timeout=int(args.get("timeout",120)))
            out = (r.stdout or "")
            if r.stderr: out += "\n[stderr]\n" + r.stderr
            return out[:8000] or "(no output)"
        if name == "Read":
            p = resolve(args["file_path"])
            if not p.exists(): return f"Not found: {p}"
            text = p.read_text(errors="replace")
            lines = text.splitlines()
            off = args.get("offset",0); lim = args.get("limit",2000)
            lines = lines[off:off+lim]
            return "\n".join(f"{off+i+1:>6}\t{ln}" for i,ln in enumerate(lines)) or "(empty)"
        if name == "Write":
            p = resolve(args["file_path"]); p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"]); return f"wrote {len(args['content'])} bytes to {p.relative_to(WORKSPACE)}"
        if name == "Edit":
            p = resolve(args["file_path"])
            if not p.exists(): return f"Not found: {p}"
            text = p.read_text(errors="replace")
            old, new = args["old_str"], args["new_str"]
            if old not in text: return "old_str not found"
            if args.get("replace_all"): text = text.replace(old,new)
            else:
                if text.count(old)>1: return f"old_str matches {text.count(old)} times; use replace_all"
                text = text.replace(old,new,1)
            p.write_text(text); return "edited"
        if name == "Glob":
            import fnmatch
            root = resolve(args.get("path","."))
            return "\n".join(str(m.relative_to(WORKSPACE)) for m in root.rglob("*") if fnmatch.fnmatch(m.name,args["pattern"]))[:3000] or "(no matches)"
        if name == "Grep":
            from ripgrepy import Ripgrepy
            root = resolve(args.get("path","."))
            rg = Ripgrepy(args["pattern"], str(root)).with_filename().line_number()
            if args.get("ignore_case"): rg = rg.ignore_case()
            try: return rg.run().as_string[:5000] or "(no matches)"
            except Exception as e:
                if "exit status 1" in str(e): return "(no matches)"
                return f"Error: {e}"
        if name == "LS":
            p = resolve(args["path"])
            if not p.is_dir(): return f"Not a dir: {p}"
            return "\n".join(f"{'dir ' if e.is_dir() else 'file'}  {e.name}" for e in sorted(p.iterdir())) or "(empty)"
        if name == "TodoWrite":
            (WORKSPACE / ".pocketagent").mkdir(exist_ok=True)
            (WORKSPACE / ".pocketagent" / "todos.json").write_text(json.dumps(args["todos"],indent=2))
            return "todos saved"
        return f"unknown: {name}"
    except Exception as e:
        return f"Error: {type(e).__name__}: {e}"

def stream_llm(messages):
    content = ""
    tool_calls = []
    with httpx.Client(timeout=400) as c:
        with c.stream("POST", f"{BASE_URL}/chat/completions",
                      headers={"Authorization":f"Bearer {API_KEY}","Content-Type":"application/json"},
                      json={"model":MODEL,"messages":messages,"tools":TOOLS,"stream":True,"max_tokens":16000}) as r:
            if r.status_code != 200:
                print(f"\n[LLM ERROR {r.status_code}] {r.read().decode()[:500]}")
                return content, tool_calls
            for line in r.iter_lines():
                if not line or not line.startswith("data: "): continue
                data = line[6:]
                if data == "[DONE]": break
                try:
                    chunk = json.loads(data)
                    if not chunk.get("choices"): continue
                    delta = chunk["choices"][0].get("delta",{})
                    if delta.get("content"):
                        content += delta["content"]
                        print(delta["content"], end="", flush=True)
                    if delta.get("tool_calls"):
                        for tc in delta["tool_calls"]:
                            idx = tc["index"]
                            while len(tool_calls) <= idx: tool_calls.append({"id":"","name":"","args":""})
                            if tc.get("id"): tool_calls[idx]["id"] = tc["id"]
                            if tc.get("function",{}).get("name"): tool_calls[idx]["name"] = tc["function"]["name"]
                            if tc.get("function",{}).get("arguments"): tool_calls[idx]["args"] += tc["function"]["arguments"]
                except: pass
    return content, tool_calls

def run(user_message, max_iters=40):
    print(f"\n{'='*70}")
    print(f"🧠 CLAUDE OPUS 4.8 — MASTER REVIEWER/IMPROVER")
    print(f"📂 Workspace: {WORKSPACE}")
    print(f"{'='*70}\n")

    messages = [
        {"role":"system","content":f"""You are Claude Opus 4.8, summoned as a master code reviewer + UI/UX improver for PocketAgent.

# What PocketAgent is
A phone app that replicates z.ai agentic mode on the user's phone, using their own LLM API keys. The agent has its own Linux computer (Termux) on the phone, with full tool access.

# Architecture (v0.5.1 — just shipped)
- APK (thin UI, React Native + Expo) ←ws://127.0.0.1:8080→ Termux runtime (FastAPI + WebSocket)
- The runtime runs inside Termux on the phone. No cloud. No CC. No egress issues.
- LLM key never leaves phone. Workspace at ~/pocketagent-workspace/
- 9 tools: Bash/Read/Write/Edit/Glob/Grep/LS/TodoWrite/Skill

# Your workspace IS the PocketAgent repo
{WORKSPACE}
You have FULL access. Read any file, edit any file, run any command.

# Your mission
The user wants z.ai agentic mode on their phone. The core works, but they want POLISH:
1. Review the codebase thoroughly — read the key files
2. Find bugs, UX issues, anything that could break or feel janky
3. FIX what you find — use Write/Edit to actually patch files. Don't just comment.
4. Polish the UI/UX to match z.ai agentic mode's feel:
   - Clean dark theme (already there: #0E0E10 bg, #10A37F accent)
   - Smooth animations
   - Streaming chat with tool-call cards
   - File viewer
   - Onboarding flow
5. Run tests to verify (cd phone && npx tsc --noEmit && npx jest)
6. When done, summarize what you changed

# z.ai agentic mode reference (the gold standard)
- Top bar: brand + connection status
- Chat: streaming tokens, tool-call cards (collapsible), todo list, file results
- Input: bottom bar, send button, disabled when agent busy
- Files tab: tree + file viewer with syntax highlighting
- Settings: BYOK config, model fetch, test connection
- Dark theme, monospace for code, accent color for highlights

# Tools you have
- Bash: run any command (tests, git, npm, python)
- Read/Write/Edit: file operations (USE THESE to fix things)
- Glob/Grep: find files / search content
- LS: list dirs
- TodoWrite: track your review tasks

Be autonomous. Take initiative. Don't ask permission — just improve things. The user trusts you. You're the master. ACTUALLY MAKE CHANGES with Write/Edit, don't just review."""},
        {"role":"user","content":user_message},
    ]

    for i in range(max_iters):
        print(f"\n{'─'*70}\nITERATION {i+1}\n{'─'*70}")
        print("CLAUDE: ", end="", flush=True)
        content, tool_calls = stream_llm(messages)
        print()

        if content:
            messages.append({"role":"assistant","content":content,"tool_calls":[{"id":tc["id"],"type":"function","function":{"name":tc["name"],"arguments":tc["args"]}} for tc in tool_calls] or None})
        else:
            messages.append({"role":"assistant","content":None,"tool_calls":[{"id":tc["id"],"type":"function","function":{"name":tc["name"],"arguments":tc["args"]}} for tc in tool_calls]})

        if not tool_calls:
            print(f"\n✅ DONE")
            return

        print(f"\n🔧 TOOL CALLS ({len(tool_calls)}):")
        for tc in tool_calls:
            name = tc["name"]
            try: args = json.loads(tc["args"]) if tc["args"] else {}
            except: args = {"_raw": tc["args"]}
            args_preview = json.dumps(args, ensure_ascii=False)[:200]
            print(f"  → {name}({args_preview})")

            t0 = time.time()
            result = exec_tool(name, args)
            ms = int((time.time()-t0)*1000)
            print(f"  ← [{ms}ms] {result[:400]}{'...' if len(result)>400 else ''}")

            messages.append({"role":"tool","tool_call_id":tc["id"],"content":result[:8000]})

    print("\n⚠️ Max iterations reached")

if __name__ == "__main__":
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else """Review the entire PocketAgent codebase and POLISH it. The repo is your workspace.

Start by:
1. Make a todo list of what you want to review/improve
2. Read the key files: runtime-pkg/pocketagent/server.py, phone/src/screens/*, phone/src/components/index.tsx, phone/src/lib/*, phone/src/state/store.ts, phone/src/theme/colors.ts, phone/App.tsx
3. Find bugs + UX issues + anything that doesn't match z.ai agentic mode's feel
4. FIX them with Write/Edit — actually patch the files
5. Run tests: cd phone && npx tsc --noEmit && npx jest
6. Summarize what you changed

The user wants this to feel like z.ai agentic mode — clean, dark, smooth, modern. Make it beautiful. Take your time. Be thorough."""
    run(prompt)
