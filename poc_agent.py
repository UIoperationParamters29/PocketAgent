"""Proof of concept: run the agent loop using the user's LLM key + this workspace's tools.

This proves the concept works BEFORE we deploy anywhere. The agent:
1. Calls the user's LLM at api.gateway.orgn.com
2. Parses tool calls
3. Executes tools (Bash, Read, Write, etc.) in THIS workspace
4. Returns results to the LLM
5. Streams the response

If this works, we know the agent logic + LLM + tools all work together.
Then we just deploy this exact script to a free public host for the phone app.
"""
import httpx
import json
import subprocess
import os
from pathlib import Path

BASE_URL = "https://api.gateway.orgn.com/v1"
API_KEY = "sk-ollm-g1IDxLLVhFbO-mZLJfLIURm2sFThisIaWioS7hcxfopaVzZjx1SQRoMPUuvlY"
MODEL = "near_glm_5"

WORKSPACE = Path("/home/z/my-project/poc-workspace")
WORKSPACE.mkdir(parents=True, exist_ok=True)

# --- Tool definitions (same as our cloud runtime) ---
TOOLS = [
    {"type": "function", "function": {
        "name": "Bash",
        "description": "Execute a bash command in the workspace.",
        "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]},
    }},
    {"type": "function", "function": {
        "name": "Read",
        "description": "Read a file from the workspace.",
        "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}}, "required": ["file_path"]},
    }},
    {"type": "function", "function": {
        "name": "Write",
        "description": "Create or overwrite a file in the workspace.",
        "parameters": {"type": "object", "properties": {"file_path": {"type": "string"}, "content": {"type": "string"}}, "required": ["file_path", "content"]},
    }},
    {"type": "function", "function": {
        "name": "LS",
        "description": "List files in a directory.",
        "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    }},
]

def execute_tool(name, args):
    """Execute a tool in this workspace."""
    try:
        if name == "Bash":
            r = subprocess.run(args["command"], shell=True, cwd=WORKSPACE, capture_output=True, text=True, timeout=30)
            return r.stdout + (r.stderr and f"\n[stderr]\n{r.stderr}" or "")
        elif name == "Read":
            p = WORKSPACE / args["file_path"]
            return p.read_text() if p.exists() else f"File not found: {p}"
        elif name == "Write":
            p = WORKSPACE / args["file_path"]
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(args["content"])
            return f"Wrote {len(args['content'])} bytes to {p}"
        elif name == "LS":
            p = WORKSPACE / args["path"]
            return "\n".join(f"{f.name:30s} {'dir' if f.is_dir() else f'{f.stat().st_size}b'}" for f in sorted(p.iterdir())) if p.is_dir() else "Not a dir"
        return f"Unknown tool: {name}"
    except Exception as e:
        return f"Error: {e}"

def run_agent(user_message, max_iters=10):
    """Run the agent loop: user message → LLM → tools → ... → final answer."""
    messages = [
        {"role": "system", "content": f"You are PocketAgent, a personal AI agent running inside your own Linux computer. Your workspace is {WORKSPACE}. You have tools: Bash, Read, Write, LS. Use them to complete tasks. Be direct and efficient."},
        {"role": "user", "content": user_message},
    ]

    for i in range(max_iters):
        print(f"\n{'='*60}")
        print(f"ITERATION {i+1}")
        print(f"{'='*60}")

        # Call the LLM
        print("Calling LLM...")
        with httpx.Client(timeout=120) as client:
            r = client.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"},
                json={"model": MODEL, "messages": messages, "tools": TOOLS, "max_tokens": 2000},
            )
        
        if r.status_code != 200:
            print(f"LLM error: {r.status_code} {r.text[:300]}")
            return
        
        data = r.json()
        choice = data["choices"][0]
        msg = choice["message"]
        
        # Add assistant message
        messages.append(msg)
        
        # If there's content, print it
        if msg.get("content"):
            print(f"\nAGENT: {msg['content'][:500]}")
        
        # If there are tool calls, execute them
        tool_calls = msg.get("tool_calls", [])
        if not tool_calls:
            print(f"\n✅ DONE (no more tool calls)")
            return msg.get("content", "")
        
        print(f"\nTOOL CALLS ({len(tool_calls)}):")
        for tc in tool_calls:
            fn = tc["function"]
            name = fn["name"]
            args = json.loads(fn["arguments"])
            print(f"  → {name}({json.dumps(args)[:100]})")
            
            result = execute_tool(name, args)
            print(f"  ← {result[:200]}")
            
            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": result[:5000],
            })
    
    print("\n⚠️ Max iterations reached")

# --- Run a real test ---
print("=" * 60)
print("POCKETAGENT PROOF OF CONCEPT")
print(f"LLM: {BASE_URL} / {MODEL}")
print(f"Workspace: {WORKSPACE}")
print("=" * 60)

run_agent("""I'm testing you. Please do these 3 things:
1. List what's in your workspace using LS
2. Create a file called hello.txt with the content 'PocketAgent works!'
3. Read it back and confirm the content""")

print("\n" + "=" * 60)
print("VERIFICATION: Files in workspace:")
for f in WORKSPACE.iterdir():
    print(f"  {f.name} ({f.stat().st_size} bytes)")
    if f.is_file() and f.suffix == ".txt":
        print(f"    content: {f.read_text()!r}")
print("=" * 60)
