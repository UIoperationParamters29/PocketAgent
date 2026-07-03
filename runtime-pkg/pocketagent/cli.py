"""CLI entry points for pocketagent-runtime.

Usage in Termux:
  pocketagent-start   # start the agent server (foreground, with wake-lock)
  pocketagent-stop    # stop a running server
  pocketagent-status  # check if server is running
"""
import os
import sys
import subprocess
import time
import signal
from pathlib import Path

PID_FILE = Path.home() / ".pocketagent" / "runtime.pid"
LOG_FILE = Path.home() / ".pocketagent" / "runtime.log"
PORT = 8080


def _ensure_dirs():
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)


def _is_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, 0)  # signal 0 = check if alive
        return True
    except (ProcessLookupError, ValueError, PermissionError):
        return False


def start():
    """Start the PocketAgent runtime server in the background."""
    _ensure_dirs()
    if _is_running():
        print(f"✅ PocketAgent is already running on port {PORT}")
        print(f"   Logs: {LOG_FILE}")
        return

    # Try to acquire a Termux wake-lock (prevents Android from killing us)
    try:
        subprocess.run(["termux-wake-lock"], check=False, timeout=5)
        print("✅ Acquired Termux wake-lock")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("⚠️  termux-wake-lock not available (install Termux:API app if you want background survival)")

    # Start uvicorn in the background
    print(f"🚀 Starting PocketAgent runtime on port {PORT}...")
    log_fd = open(LOG_FILE, "a")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "pocketagent.server:app",
         "--host", "127.0.0.1", "--port", str(PORT)],
        stdout=log_fd, stderr=subprocess.STDOUT,
        # Detach from this shell so we survive
        start_new_session=True,
    )
    PID_FILE.write_text(str(proc.pid))

    # Wait for it to come up
    for i in range(15):
        time.sleep(1)
        if _is_running() and _health_check():
            print(f"✅ PocketAgent is running on http://127.0.0.1:{PORT}")
            print(f"   PID: {proc.pid}")
            print(f"   Logs: {LOG_FILE}")
            print(f"   Workspace: {Path.home() / 'pocketagent-workspace'}")
            print(f"\n   Open the PocketAgent app on your phone to connect.")
            return
        if proc.poll() is not None:
            # Process died
            print(f"❌ Server failed to start. Logs:")
            print(LOG_FILE.read_text()[-2000:])
            return

    print(f"⏳ Still starting... check logs: {LOG_FILE}")


def stop():
    """Stop the running PocketAgent runtime."""
    _ensure_dirs()
    if not _is_running():
        print("PocketAgent is not running.")
        PID_FILE.unlink(missing_ok=True)
        return

    try:
        pid = int(PID_FILE.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        time.sleep(1)
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        print(f"✅ Stopped PocketAgent (PID {pid})")
    except Exception as e:
        print(f"❌ Failed to stop: {e}")
    finally:
        PID_FILE.unlink(missing_ok=True)
        # Release wake-lock
        try:
            subprocess.run(["termux-wake-unlock"], check=False, timeout=5)
        except Exception:
            pass


def status():
    """Check if PocketAgent is running."""
    if _is_running():
        pid = PID_FILE.read_text().strip()
        healthy = _health_check()
        print(f"✅ PocketAgent is running (PID {pid})")
        print(f"   Health: {'healthy' if healthy else 'unhealthy'}")
        print(f"   URL: http://127.0.0.1:{PORT}")
        print(f"   Logs: {LOG_FILE}")
    else:
        print("❌ PocketAgent is not running. Run: pocketagent-start")


def _health_check() -> bool:
    """Quick HTTP health check."""
    try:
        import httpx
        r = httpx.get(f"http://127.0.0.1:{PORT}/", timeout=2)
        return r.status_code == 200
    except Exception:
        return False


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "start"
    if cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "status":
        status()
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: pocketagent {start|stop|status}")
        sys.exit(1)
