#!/usr/bin/env python3
"""Persistent local REA MCP session for sequential, auditable research queries.

Reads JSON requests from stdin: {"method":"tools/call","params":{...}}.
Writes full responses to an exclusive evidence directory and prints only paths.
Send {"close":true} to close the active binary and the server cleanly.
"""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading


def main():
    root = Path(__file__).resolve().parent.parent
    out = Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env.setdefault("GHIDRA_INSTALL_DIR", str(root / ".tools/ghidra"))
    env.setdefault("JAVA_HOME", "/Library/Java/JavaVirtualMachines/jdk-21.jdk/Contents/Home")
    env.setdefault("GHIDRA_HEADLESS_MAXMEM", "8G")
    env.setdefault("REA_GHIDRA_STARTUP_TIMEOUT_MS", "1200000")
    response_timeout = max(1500, int(env["REA_GHIDRA_STARTUP_TIMEOUT_MS"]) / 1000 + 120)
    responses = queue.Queue()
    with (out / "server.stderr").open("w") as stderr:
        server = subprocess.Popen(
            ["node", str(root / ".tools/rea/node_modules/rea-agents/scripts/rea.mjs"), "mcp"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=stderr,
            text=True, bufsize=1, env=env, cwd=root,
        )
        def reader():
            for line in server.stdout:
                try:
                    responses.put(json.loads(line))
                except json.JSONDecodeError:
                    responses.put({"non_json_stdout": line})
            responses.put({"server_closed": True})
        threading.Thread(target=reader, daemon=True).start()
        seq = 0
        def exchange(method, params=None):
            nonlocal seq
            seq += 1
            request = {"jsonrpc": "2.0", "id": seq, "method": method, "params": params or {}}
            request_path = out / f"{seq:04d}-request.json"
            request_path.write_text(json.dumps(request, indent=2) + "\n")
            server.stdin.write(json.dumps(request) + "\n")
            server.stdin.flush()
            while True:
                response = responses.get(timeout=response_timeout)
                if response.get("id") == seq:
                    path = out / f"{seq:04d}-response.json"
                    path.write_text(json.dumps(response, indent=2) + "\n")
                    print(json.dumps({"id": seq, "method": method, "response_path": str(path),
                                      "error": response.get("error"),
                                      "isError": response.get("result", {}).get("isError")}), flush=True)
                    return response
                with (out / "notifications.jsonl").open("a") as f:
                    f.write(json.dumps(response) + "\n")
                if response.get("server_closed"):
                    raise RuntimeError("REA server closed before responding")
        try:
            exchange("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                     "clientInfo": {"name": "rebase-research", "version": "1"}})
            server.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
            server.stdin.flush()
            exchange("tools/list")
            for line in sys.stdin:
                command = json.loads(line)
                if command.get("close"):
                    exchange("tools/call", {"name": "close_binary", "arguments": {}})
                    break
                result = exchange(command["method"], command.get("params"))
                if result.get("error") or result.get("result", {}).get("isError"):
                    # Do not re-import a failed large target for queued requests.
                    # The failed response remains evidence; retry in a fresh session.
                    exchange("tools/call", {"name": "close_binary", "arguments": {}})
                    break
        finally:
            server.stdin.close()
            try:
                server.wait(timeout=15)
            except subprocess.TimeoutExpired:
                server.terminate()
                try:
                    server.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    main()
