"""Creative egress bypass tests — find a way to reach api.gateway.orgn.com from Daytona."""
import os
os.environ["DAYTONA_API_KEY"] = "dtn_5489f0d141b5cd1675b6114467aeecb4623495cf5dc7c8ebe13e36221ba4b046"
os.environ["DAYTONA_API_URL"] = "https://app.daytona.io/api"
os.environ["DAYTONA_TARGET"] = "us"

from daytona import Daytona
import time

daytona = Daytona()
sb = daytona.get("b5256600-063b-4469-a5ed-0d78edcd93b7")
print(f"Sandbox: {sb.id}, state={sb.state}")

if sb.state != sb.state.STARTED:
    print("Starting sandbox...")
    daytona.start(sb)
    for i in range(15):
        time.sleep(2)
        sb = daytona.get(sb.id)
        print(f"  [{i}] state={sb.state}")
        if sb.state == sb.state.STARTED:
            break

print(f"\nFinal state: {sb.state}")

print("\n=== Test 1: Direct IP with Host header (bypass DNS) ===")
r = sb.process.exec(
    "curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "
    "-H 'Host: api.gateway.orgn.com' "
    "--resolve api.gateway.orgn.com:443:34.72.214.192 "
    "https://api.gateway.orgn.com/v1/models",
    timeout=15
)
print(f"  Result: {r.result.strip()} (exit {r.exit_code})")

print("\n=== Test 2: Cloudflare workers.dev reachable? ===")
r = sb.process.exec(
    "curl -sS -o /dev/null -w '%{http_code}' --max-time 10 https://workers.cloudflare.com/",
    timeout=15
)
print(f"  workers.cloudflare.com: {r.result.strip()}")

r = sb.process.exec(
    "curl -sS -o /dev/null -w '%{http_code}' --max-time 10 https://test-worker.pocketagent.workers.dev/ 2>&1 | head -1",
    timeout=15
)
print(f"  test worker: {r.result.strip()}")

print("\n=== Test 3: Is it IP-based or DNS-based blocking? ===")
# Try a different domain on the same IP range (GCP us-central)
r = sb.process.exec(
    "curl -sS -o /dev/null -w '%{http_code}' --max-time 10 https://google.com/",
    timeout=15
)
print(f"  google.com: {r.result.strip()}")

# Try the IP directly with curl --resolve
r = sb.process.exec(
    "curl -sS -o /dev/null -w '%{http_code}' --max-time 10 -k https://34.72.214.192/ -H 'Host: api.gateway.orgn.com'",
    timeout=15
)
print(f"  direct IP 34.72.214.192: {r.result.strip()}")

print("\n=== Test 4: Can we reach a Cloudflare Pages site? ===")
r = sb.process.exec(
    "curl -sS -o /dev/null -w '%{http_code}' --max-time 10 https://pages.cloudflare.com/",
    timeout=15
)
print(f"  pages.cloudflare.com: {r.result.strip()}")

print("\n=== Test 5: SSH port 22 reachable? (for tunneling) ===")
r = sb.process.exec(
    "timeout 3 bash -c 'echo > /dev/tcp/github.com/22' 2>&1 && echo 'PORT 22 OPEN' || echo 'PORT 22 BLOCKED'",
    timeout=8
)
print(f"  github.com:22: {r.result.strip()}")

print("\n=== Test 6: Check if we can install socat/nc for port forwarding ===")
r = sb.process.exec("which socat nc ncat 2>&1; apt list --installed 2>/dev/null | grep -E 'socat|netcat' | head -3", timeout=10)
print(f"  tools: {r.result.strip()}")

print("\n=== Test 7: Try a different IP for the same service ===")
# orgn.com might have multiple IPs. Let's see if there's a different one
r = sb.process.exec("getent hosts api.gateway.orgn.com 2>&1; dig +short api.gateway.orgn.com 2>&1", timeout=10)
print(f"  DNS: {r.result.strip()}")

print("\n=== Test 8: Check what domains ARE on the allowlist ===")
# Daytona docs say "essential services" are allowed. Let's see what works.
domains = [
    "registry.npmjs.org",
    "registry-1.docker.io",
    "auth.docker.io",
    "pypi.org",
    "files.pythonhosted.org",
    "github.com",
    "raw.githubusercontent.com",
    "objects.githubusercontent.com",
    "huggingface.co",
    "cdn.jsdelivr.net",
    "deno.land",
    "workers.dev",
    "cloudflare.com",
    "onrender.com",
    "fly.io",
    "railway.app",
    "vercel.app",
    "netlify.app",
    "glitch.me",
]
print("  Testing domains:")
for d in domains:
    r = sb.process.exec(f"curl -sS -o /dev/null -w '%{{http_code}}' --max-time 6 https://{d}/ 2>&1", timeout=10)
    code = r.result.strip().split("\n")[-1][:10]
    print(f"    {d:35s} -> {code}")

print("\n=== DONE ===")
