"""PocketAgent LIVE — full z.ai-parity tool surface, powered by vercel_claude_fable_5.

The agent gets my entire workspace + all 8 tools. We just monitor + stream.
"""
import httpx, json, subprocess, os, sys, time
from pathlib import Path
from typing import Any

BASE_URL = "https://api.gateway.orgn.com/v1"
API_KEY = "sk-ollm-g1IDxLLVhFbO-mZLJfLIURm2sFThisIaWioS7hcxfopaVzZjx1SQRoMPUuvlY"
MODEL = "vercel_claude_fable_5"
WORKSPACE = Path("/home/z/my-project/agent-workspace")
WORKSPACE.mkdir(parents=True, exist_ok=True)

# --- The full z.ai-parity tool surface ---
TOOLS = [
    {"type":"function","function":{"name":"Bash","description":"Execute a bash command in your workspace. Full Linux. You can install packages (apt/pip/npm), run scripts, git, anything.","parameters":{"type":"object","properties":{"command":{"type":"string"},"timeout":{"type":"integer","default":120}},"required":["command"]}}},
    {"type":"function","function":{"name":"Read","description":"Read a text file from your workspace. Returns cat -n style output.","parameters":{"type":"object","properties":{"file_path":{"type":"string"},"offset":{"type":"integer","default":0},"limit":{"type":"integer","default":2000}},"required":["file_path"]}}},
    {"type":"function","function":{"name":"Write","description":"Create or overwrite a file in your workspace. Directories created as needed.","parameters":{"type":"object","properties":{"file_path":{"type":"string"},"content":{"type":"string"}},"required":["file_path","content"]}}},
    {"type":"function","function":{"name":"Edit","description":"Exact string replacement in an existing file.","parameters":{"type":"object","properties":{"file_path":{"type":"string"},"old_str":{"type":"string"},"new_str":{"type":"string"},"replace_all":{"type":"boolean","default":False}},"required":["file_path","old_str","new_str"]}}},
    {"type":"function","function":{"name":"Glob","description":"Find files by name pattern.","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string","default":"."}},"required":["pattern"]}}},
    {"type":"function","function":{"name":"Grep","description":"Search file contents using ripgrep.","parameters":{"type":"object","properties":{"pattern":{"type":"string"},"path":{"type":"string","default":"."},"ignore_case":{"type":"boolean","default":False}},"required":["pattern"]}}},
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
            out = (r.stdout or "") + (r.stderr and "\n[stderr]\n"+r.stderr or "")
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
    """Stream the LLM response, collecting content + tool_calls."""
    content = ""
    tool_calls = []
    with httpx.Client(timeout=300) as c:
        with c.stream("POST", f"{BASE_URL}/chat/completions",
                      headers={"Authorization":f"Bearer {API_KEY}","Content-Type":"application/json"},
                      json={"model":MODEL,"messages":messages,"tools":TOOLS,"stream":True,"max_tokens":8000}) as r:
            if r.status_code != 200:
                print(f"\n[LLM ERROR {r.status_code}] {r.read().decode()[:300]}")
                return content, tool_calls
            for line in r.iter_lines():
                if not line or not line.startswith("data: "): continue
                data = line[6:]
                if data == "[DONE]": break
                try:
                    chunk = json.loads(data)
                    if not chunk.get("choices"): continue
                    delta = chunk["choices"][0].get("delta",{})
                    # Content stream
                    if delta.get("content"):
                        content += delta["content"]
                        print(delta["content"], end="", flush=True)
                    # Tool calls (streamed incrementally)
                    if delta.get("tool_calls"):
                        for tc in delta["tool_calls"]:
                            idx = tc["index"]
                            while len(tool_calls) <= idx: tool_calls.append({"id":"","name":"","args":""})
                            if tc.get("id"): tool_calls[idx]["id"] = tc["id"]
                            if tc.get("function",{}).get("name"): tool_calls[idx]["name"] = tc["function"]["name"]
                            if tc.get("function",{}).get("arguments"): tool_calls[idx]["args"] += tc["function"]["arguments"]
                except: pass
    return content, tool_calls

def run(user_message, max_iters=15):
    print(f"\n{'='*70}")
    print(f"🤖 POCKETAGENT LIVE — {MODEL}")
    print(f"📂 Workspace: {WORKSPACE}")
    print(f"{'='*70}\n")
    
    messages = [
        {"role":"system","content":f"""You are PocketAgent — a personal AI agent running inside your own Linux computer.

# What you are
- You live in a real Linux workspace at {WORKSPACE}
- Layout: download/ (deliverables), scripts/ (your scripts), upload/ (user files), skills/ (SKILL.md packages)
- You have FULL Linux — apt, pip, npm, git, anything.

# Tools
- Bash: run any command (full Linux)
- Read/Write/Edit: file operations
- Glob/Grep: find files / search content
- LS: list dirs
- TodoWrite: track your tasks

# How you work
- ALWAYS make a todo list first for multi-step tasks
- Persist scripts to scripts/ before running
- Save deliverables to download/
- Be autonomous — install tools if you need them
- Stream your thinking as you work
- Match the user's language
- When done, give a brief summary

You are powerful. Take initiative. The user is watching on their phone."""},
        {"role":"user","content":user_message},
    ]
    
    for i in range(max_iters):
        print(f"\n{'─'*70}\nITERATION {i+1}\n{'─'*70}")
        print("AGENT: ", end="", flush=True)
        content, tool_calls = stream_llm(messages)
        print()  # newline after streaming
        
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
            args_preview = json.dumps(args, ensure_ascii=False)[:150]
            print(f"  → {name}({args_preview})")
            
            t0 = time.time()
            result = exec_tool(name, args)
            ms = int((time.time()-t0)*1000)
            print(f"  ← [{ms}ms] {result[:300]}{'...' if len(result)>300 else ''}")
            
            messages.append({"role":"tool","tool_call_id":tc["id"],"content":result[:8000]})
    
    print("\n⚠️ Max iterations reached")

if __name__ == "__main__":
    # Take the user's prompt from argv, or use a default
    prompt = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else """I'm testing you. Do these 3 things:
1. Use LS to see what's in your workspace
2. Create a Python script at scripts/hello.py that prints 'PocketAgent lives!' + the current date
3. Run it with Bash and tell me the output"""
    run(prompt)
