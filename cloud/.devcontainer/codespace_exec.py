#!/usr/bin/env python3
"""Run a command inside a GitHub Codespace via the gh cs ssh --stdio proxy.

This is the only reliable way to exec into a codespace from a sandbox
that doesn't have direct SSH network access. The gh CLI handles the
auth + transport; we just pipe a command + capture output.

Usage: python3 codespace_exec.py <codespace-name> <command>
"""
import asyncio
import os
import sys
from pathlib import Path

GH_BIN = str(Path.home() / ".local/bin/gh")
SSH_BIN = "/tmp/ssh-extracted/usr/bin/ssh"


async def run_in_codespace(codespace: str, command: str, timeout: float = 60.0) -> tuple[int, str]:
    """Returns (exit_code, output)."""
    # Use ssh with gh as the ProxyCommand. This is the same config that
    # `gh cs ssh --config` generates.
    proxy_cmd = f"{GH_BIN} cs ssh -c {codespace} --stdio"
    ssh_cmd = [
        SSH_BIN,
        "-i", str(Path.home() / ".ssh" / "codespaces.auto"),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", f"ConnectTimeout={int(timeout)}",
        "-o", f"ProxyCommand={proxy_cmd}",
        "codespace@invalid",  # hostname is ignored (proxy uses codespace name)
        command,
    ]

    gh_dir = str(Path.home() / ".local" / "bin")
    cur_path = os.environ.get("PATH", "")
    proc = await asyncio.create_subprocess_exec(
        *ssh_cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PATH": f"{gh_dir}:{cur_path}"},
    )

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        output = stdout.decode(errors="replace")
        if stderr:
            err = stderr.decode(errors="replace")
            if "Warning" not in err and "Pseudo-terminal" not in err:
                output += "\n[stderr]\n" + err
        return proc.returncode or 0, output
    except asyncio.TimeoutError:
        proc.kill()
        return 124, "(timeout)"


async def main():
    if len(sys.argv) < 3:
        print("Usage: codespace_exec.py <codespace-name> <command>")
        sys.exit(2)
    codespace = sys.argv[1]
    command = sys.argv[2]
    code, output = await run_in_codespace(codespace, command)
    print(output, end="")
    sys.exit(code)


if __name__ == "__main__":
    asyncio.run(main())
