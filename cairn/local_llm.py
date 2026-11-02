"""Local model client (Muse Glimmer via Ollama / llama.cpp / vLLM, OpenAI-compatible chat API).

Privacy mode: the reasoning stays on the bench. Nothing here talks to a cloud endpoint unless you
point `base_url` at one. Same `complete(messages, tools)` contract as `WonderClient`, so
`WonderAgent` runs on it unchanged.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable

from .meta_api import MetaApiError

DEFAULT_LOCAL_URL = "http://localhost:11434/v1"  # Ollama
Transport = Callable[[str, dict], dict]


def to_chat_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {
        "name": t["name"], "description": t["description"],
        "parameters": {"type": "object", "properties": {k: {"type": v} for k, v in t["args"].items()},
                       "required": list(t["args"])}}} for t in tools]


class GlimmerClient:
    def __init__(self, base_url: str | None = None, model: str | None = None,
                 transport: Transport | None = None, timeout: float = 120.0):
        self.base_url = (base_url or os.environ.get("CAIRN_LOCAL_URL") or DEFAULT_LOCAL_URL).rstrip("/")
        self.model = model or os.environ.get("CAIRN_LOCAL_MODEL") or "glimmer"
        self._transport, self.timeout = transport, timeout
        self._history: list[dict] = []
        self._call_id: str | None = None

    def _post(self, path: str, body: dict) -> dict:
        if self._transport:
            return self._transport(path, body)
        req = urllib.request.Request(self.base_url + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.load(r)
        except OSError as e:
            raise MetaApiError(f"local model unreachable at {self.base_url}: {e}") from e

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        last = messages[-1]
        if last["role"] == "tool" and self._call_id:
            self._history.append({"role": "tool", "tool_call_id": self._call_id, "content": last["content"]})
        else:  # new conversation
            self._history = [m for m in messages if m["role"] in ("system", "user")]
        resp = self._post("/chat/completions", {"model": self.model, "messages": self._history,
                                                "tools": to_chat_tools(tools)})
        try:
            msg = resp["choices"][0]["message"]
        except (KeyError, IndexError):
            raise MetaApiError(f"unexpected local model reply: {str(resp)[:200]}") from None
        calls = msg.get("tool_calls") or []
        if calls:
            call = calls[0]
            self._call_id = call["id"]
            self._history.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
            raw = call["function"].get("arguments") or "{}"
            try:
                args = json.loads(raw) if isinstance(raw, str) else dict(raw)
            except ValueError:
                args = {}
            return {"tool": call["function"]["name"], "args": args}
        text = msg.get("content")
        if not text:
            raise MetaApiError("local model returned neither text nor a tool call")
        return {"text": text}
