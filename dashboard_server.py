"""Serve the dashboard and run its case experiments on a local fork.

The HTTP API is intentionally loopback-only by default. It invokes the same
``dashboard_proof.py`` entry point, which uses the existing fork runner, and
never broadcasts to Tempo mainnet.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent
RUN_LOCK = threading.Lock()
CASE_IDS = {"small", "gap", "illiquid"}


def rpc_call(url: str, method: str, params: list, timeout: float = 2.0):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                          "params": params}).encode()
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = json.loads(response.read())
    if "error" in body:
        raise RuntimeError(body["error"].get("message", "RPC returned an error"))
    return body["result"]


def safe_rpc_label(url: str) -> str:
    parsed = urlsplit(url)
    return f"{parsed.hostname or 'local fork'}:{parsed.port or 80}"


class DashboardHandler(SimpleHTTPRequestHandler):
    server_version = "TempoDashboard/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    @property
    def fork_rpc(self) -> str:
        return self.server.fork_rpc  # type: ignore[attr-defined]

    def json_response(self, status: HTTPStatus, payload: dict) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except (BrokenPipeError, ConnectionAbortedError):
            pass

    def fork_status(self) -> dict:
        try:
            chain_id = int(rpc_call(self.fork_rpc, "eth_chainId", []), 16)
            block_number = int(rpc_call(self.fork_rpc, "eth_blockNumber", []), 16)
            ready = chain_id == 4217 and block_number == 41_183_156
            return {"ready": ready, "chainId": chain_id,
                    "blockNumber": block_number,
                    "endpoint": safe_rpc_label(self.fork_rpc),
                    "message": ("Local fork is ready" if ready else
                                "Use a fresh Tempo fork at block 41,183,156")}
        except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
            return {"ready": False, "endpoint": safe_rpc_label(self.fork_rpc),
                    "message": "Local fork is not reachable",
                    "detail": str(exc)[:180]}

    def do_GET(self) -> None:  # noqa: N802 - standard-library handler API
        path = urlsplit(self.path).path
        if path == "/":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/dashboard/#solution")
            self.end_headers()
            return
        if path == "/api/status":
            self.json_response(HTTPStatus.OK, self.fork_status())
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802 - standard-library handler API
        if urlsplit(self.path).path != "/api/run-universal-router":
            self.json_response(HTTPStatus.NOT_FOUND, {"ok": False,
                                                       "error": "Unknown endpoint"})
            return
        if not RUN_LOCK.acquire(blocking=False):
            self.json_response(HTTPStatus.CONFLICT, {"ok": False,
                                                      "error": "A proof is already running"})
            return
        started = time.perf_counter()
        try:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 256:
                    raise ValueError("Request body must contain a case ID")
                request = json.loads(self.rfile.read(length))
                case_id = request.get("caseId") if isinstance(request, dict) else None
                if not isinstance(case_id, str) or case_id not in CASE_IDS:
                    raise ValueError("Unknown test case")
            except (ValueError, json.JSONDecodeError) as exc:
                self.json_response(HTTPStatus.BAD_REQUEST,
                                   {"ok": False, "error": str(exc)})
                return
            status = self.fork_status()
            if not status["ready"]:
                self.json_response(HTTPStatus.SERVICE_UNAVAILABLE,
                                   {"ok": False, "error": status["message"],
                                    "fork": status})
                return
            command = [sys.executable, str(ROOT / "dashboard_proof.py"),
                       "--rpc", self.fork_rpc, "--case", case_id]
            try:
                safety_snapshot = rpc_call(self.fork_rpc, "evm_snapshot", [])
            except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
                self.json_response(HTTPStatus.SERVICE_UNAVAILABLE,
                                   {"ok": False,
                                    "error": f"Could not isolate the local fork: {exc}"})
                return
            completed = None
            run_error = None
            try:
                try:
                    completed = subprocess.run(
                        command, cwd=ROOT, capture_output=True, text=True,
                        encoding="utf-8", timeout=90, check=False)
                except (subprocess.TimeoutExpired, OSError) as exc:
                    run_error = exc
            finally:
                try:
                    restored = rpc_call(self.fork_rpc, "evm_revert", [safety_snapshot],
                                        timeout=10.0)
                except (OSError, ValueError, RuntimeError, urllib.error.URLError):
                    restored = False
            if restored is not True:
                self.json_response(HTTPStatus.INTERNAL_SERVER_ERROR,
                                   {"ok": False,
                                    "error": "Local fork safety snapshot could not be restored; restart Anvil"})
                return
            if run_error is not None:
                self.json_response(HTTPStatus.GATEWAY_TIMEOUT,
                                   {"ok": False,
                                    "error": "The local-fork proof stopped or timed out; its fork state was restored"})
                return
            try:
                record = json.loads(completed.stdout)
            except json.JSONDecodeError:
                self.json_response(HTTPStatus.INTERNAL_SERVER_ERROR,
                                   {"ok": False,
                                    "error": (completed.stderr.strip() or
                                              "The demo returned no JSON")[:500]})
                return
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            if completed.returncode != 0:
                self.json_response(HTTPStatus.INTERNAL_SERVER_ERROR,
                                   {"ok": False, "error":
                                    (completed.stderr.strip() or "Experiment failed")[:500]})
                return
            self.json_response(HTTPStatus.OK,
                               {"ok": True, "elapsedMs": elapsed_ms, "record": record})
        finally:
            RUN_LOCK.release()

    def log_message(self, message: str, *args) -> None:
        print(f"dashboard: {message % args}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--rpc", default=os.getenv("TEMPO_FORK_RPC",
                                                    "http://127.0.0.1:8549"))
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    server.fork_rpc = args.rpc  # type: ignore[attr-defined]
    print(f"Dashboard: http://{args.host}:{args.port}/dashboard/#solution")
    print(f"Fork RPC: {safe_rpc_label(args.rpc)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
