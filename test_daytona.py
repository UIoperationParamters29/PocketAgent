"""Test Daytona sandbox: can it reach LLM APIs?"""
import os
os.environ["DAYTONA_API_KEY"] = "dtn_5489f0d141b5cd1675b6114467aeecb4623495cf5dc7c8ebe13e36221ba4b046"
os.environ["DAYTONA_SERVER_URL"] = "https://app.daytona.io/api"
os.environ["DAYTONA_TARGET"] = "us"

from daytona import Daytona, CreateSandboxFromSnapshotParams
import time

print("=== Connecting to Daytona ===")
daytona = Daytona()
print("[ok] Connected")

# Use the existing sandbox we created
SB_ID = "b5256600-063b-4469-a5ed-0d78edcd93b7"
print(f"\n=== Getting sandbox {SB_ID} ===")
try:
    sb = daytona.get(SB_ID)
    print(f"[ok] Got sandbox: {sb.id}, state={sb.state}")
except Exception as e:
    print(f"get failed: {e}, creating new one...")
    sb = daytona.create(CreateSandboxFromSnapshotParams())
    print(f"[ok] Created: {sb.id}, state={sb.state}")

# Wait for it to be ready
print("\n=== Waiting for sandbox to be ready ===")
for i in range(10):
    time.sleep(2)
    sb = daytona.get(sb.id)
    print(f"  [{i}] state={sb.state}")
    if sb.state == "started":
        break

print("\n=== CRITICAL TEST: LLM API egress from inside the sandbox ===")
tests = [
    ("OpenAI", "curl -sS -o /dev/null -w '%{http_code}' --max-time 10 https://api.openai.com/v1/models"),
    ("Anthropic", "curl -sS -o /dev/null -w '%{http_code}' --max-time 10 https://api.anthropic.com/v1/"),
    ("Your endpoint", "curl -sS -o /dev/null -w '%{http_code}' --max-time 10 https://api.gateway.orgn.com/v1/models -H 'Authorization: Bearer sk-ollm-g1IDxLLVhFbO-mZLJfLIURm2sFThisIaWioS7hcxfopaVzZjx1SQRoMPUuvlY'"),
    ("Google", "curl -sS -o /dev/null -w '%{http_code}' --max-time 10 https://www.google.com"),
]

for name, cmd in tests:
    print(f"\n--- {name} ---")
    try:
        result = sb.process.exec(cmd, timeout=15)
        print(f"  exit_code: {result.exit_code}")
        print(f"  stdout: {result.result[:200]}")
        if result.exit_code != 0:
            print(f"  stderr: {getattr(result, 'stderr', '')[:200]}")
    except Exception as e:
        print(f"  ERROR: {e}")

print("\n=== Test 2: pip install fastapi (can we install packages?) ===")
try:
    result = sb.process.exec("pip install fastapi uvicorn 2>&1 | tail -3", timeout=60)
    print(f"  exit_code: {result.exit_code}")
    print(f"  output: {result.result[:300]}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== Test 3: Get preview URL for port 8000 ===")
try:
    info = sb.get_preview_link(8000)
    print(f"  Preview URL: {info}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== Test 4: Start a quick HTTP server + fetch its preview URL ===")
try:
    # Start a simple Python HTTP server on port 8000 in background
    sb.process.exec("python3 -c \"import http.server,socketserver; h=http.server.BaseHTTPRequestHandler; h.do_GET=lambda s:(s.send_response(200),s.send_header('content-type','application/json'),s.end_headers(),s.wfile.write(b'{\\\"ok\\\":true}')); socketserver.TCPServer(('0.0.0.0',8000),h).serve_forever()\" &", timeout=2)
    time.sleep(2)
    # Get preview URL
    info = sb.get_preview_link(8000)
    print(f"  Preview URL info: {info}")
except Exception as e:
    print(f"  ERROR: {e}")

print("\n=== DONE ===")
print(f"Sandbox ID (save this): {sb.id}")
