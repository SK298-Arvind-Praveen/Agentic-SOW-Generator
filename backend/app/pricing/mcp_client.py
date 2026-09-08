"""Small synchronous MCP stdio client for the vendored AWS calculator."""

from __future__ import annotations

import json
import queue
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, Optional


class PricingCalculatorError(RuntimeError):
    pass


class CalculatorMcpClient:
    def __init__(self, bundle: Path, node_binary: str = "node", timeout: int = 90):
        self.bundle = Path(bundle)
        self.node_binary = node_binary
        self.timeout = timeout
        self.process: Optional[subprocess.Popen] = None
        self.messages: queue.Queue = queue.Queue()
        self.request_id = 0

    def __enter__(self):
        if not self.bundle.exists():
            raise PricingCalculatorError(f"AWS calculator bundle not found: {self.bundle}")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            [self.node_binary, str(self.bundle)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=creationflags,
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        self._request("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "shellkode-sow-generator", "version": "1.0"},
        })
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        return self

    def __exit__(self, *_args):
        if self.process:
            try:
                if self.process.stdin:
                    self.process.stdin.close()
                self.process.wait(timeout=2)
            except Exception:
                self.process.terminate()
            finally:
                self.process = None

    def _read_stdout(self) -> None:
        assert self.process and self.process.stdout
        for line in self.process.stdout:
            try:
                self.messages.put(json.loads(line))
            except json.JSONDecodeError:
                continue

    def _read_stderr(self) -> None:
        assert self.process and self.process.stderr
        for line in self.process.stderr:
            line = line.strip()
            if line:
                print(f"[PRICING][CALCULATOR] {line}", flush=True)

    def _send(self, message: Dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise PricingCalculatorError("AWS calculator process is not running")
        self.process.stdin.write(json.dumps(message, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def _request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        self.request_id += 1
        request_id = self.request_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            try:
                message = self.messages.get(timeout=self.timeout)
            except queue.Empty as exc:
                raise PricingCalculatorError(f"AWS calculator timed out during {method}") from exc
            if message.get("id") != request_id:
                continue
            if message.get("error"):
                raise PricingCalculatorError(str(message["error"]))
            return message.get("result") or {}

    def call(self, tool: str, arguments: Optional[Dict[str, Any]] = None) -> Any:
        result = self._request("tools/call", {"name": tool, "arguments": arguments or {}})
        content = result.get("content") or []
        text = "\n".join(
            str(item.get("text") or "") for item in content if isinstance(item, dict)
        ).strip()
        if result.get("isError"):
            raise PricingCalculatorError(text or f"AWS calculator tool {tool} failed")
        try:
            return json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return text
