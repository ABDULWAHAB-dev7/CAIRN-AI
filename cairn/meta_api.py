"""Clients for the Meta Model API (https://dev.meta.ai/docs): Muse Wonder and SAM 3.1.

Written from the public docs: base URL https://api.meta.ai/v1, `Authorization: Bearer`,
POST /responses, flat function tools, `function_call` / `function_call_output` items, and the
SAM special-token text stream. The transport is injectable so everything is tested offline;
the live calls themselves have NOT been exercised in this repo.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

from .perception import Box, RawTrack

DEFAULT_BASE_URL = "https://api.meta.ai/v1"
Transport = Callable[[str, dict, bool], object]


class MetaApiError(RuntimeError):
    pass


def _env_key() -> str:
    key = os.environ.get("MODEL_API_KEY") or os.environ.get("META_API_KEY")
    if not key:
        raise MetaApiError("Set MODEL_API_KEY (the name Meta's docs use) or META_API_KEY.")
    return key


class MetaClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 transport: Transport | None = None, timeout: float = 60.0):
        self.base_url = (base_url or os.environ.get("META_API_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self._key = api_key
        self._transport = transport
        self.timeout = timeout

    def responses(self, body: dict) -> dict:
        return self._send("/responses", {**body, "stream": False}, False)

    def stream_text(self, body: dict) -> str:
        """POST /responses with stream=true; return the concatenated output_text deltas."""
        return self._send("/responses", {**body, "stream": True}, True)

    def _send(self, path: str, body: dict, stream: bool):
        if self._transport:
            return self._transport(path, body, stream)
        req = urllib.request.Request(
            self.base_url + path, data=json.dumps(body).encode(), method="POST",
            headers={"Authorization": f"Bearer {self._key or _env_key()}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if not stream:
                    return json.load(resp)
                return _collect_deltas(line.decode("utf-8", "replace") for line in resp)
        except urllib.error.HTTPError as e:
            raise MetaApiError(f"{e.code} from Meta Model API: {e.read()[:300]!r}") from e


def _collect_deltas(lines) -> str:
    out = []
    for line in lines:
        line = line.strip()
        if not line.startswith("data:") or line == "data: [DONE]":
            continue
        try:
            ev = json.loads(line[5:])
        except ValueError:
            continue
        if ev.get("type") == "response.output_text.delta":
            out.append(ev.get("delta", ""))
    return "".join(out)


# ---- Muse Wonder ---------------------------------------------------------------------------------

def to_function_tools(tools: list[dict]) -> list[dict]:
    """cairn.agent.WONDER_TOOLS -> Responses API flat function tools."""
    return [{
        "type": "function", "name": t["name"], "description": t["description"],
        "parameters": {"type": "object", "properties": {k: {"type": v} for k, v in t["args"].items()},
                       "required": list(t["args"]), "additionalProperties": False},
    } for t in tools]


class WonderClient:
    """Adapts the Responses API to the `complete(messages, tools)` contract `WonderAgent` expects.

    Stateful per conversation: tool results go back with `previous_response_id`, as the docs describe.
    """

    def __init__(self, client: MetaClient, model: str = "muse-wonder-1.0"):
        self.client, self.model = client, model
        self._prev: str | None = None
        self._call_id: str | None = None

    def complete(self, messages: list[dict], tools: list[dict]) -> dict:
        last = messages[-1]
        if last["role"] == "tool" and self._prev and self._call_id:
            body = {"model": self.model, "previous_response_id": self._prev,
                    "input": [{"type": "function_call_output", "call_id": self._call_id, "output": last["content"]}]}
        else:
            system = next((m["content"] for m in messages if m["role"] == "system"), None)
            user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
            body = {"model": self.model, "input": user}
            if system:
                body["instructions"] = system
        body["tools"] = to_function_tools(tools)
        return self._parse(self.client.responses(body))

    def _parse(self, resp: dict) -> dict:
        self._prev = resp.get("id")
        text = []
        for item in resp.get("output", []):
            if item.get("type") == "function_call":
                self._call_id = item["call_id"]
                try:
                    args = json.loads(item.get("arguments") or "{}")
                except ValueError:
                    args = {}
                return {"tool": item["name"], "args": args}
            if item.get("type") == "message":
                text += [c.get("text", "") for c in item.get("content", []) if c.get("type") == "output_text"]
        if not text:
            raise MetaApiError(f"Wonder returned no text or tool call: {str(resp)[:200]}")
        return {"text": "".join(text)}


# ---- SAM 3.1 -------------------------------------------------------------------------------------

_FRAME = re.compile(r"<(\d+)f>")
_MASK = re.compile(r"<\|mask;.*?\|>", re.S)
_BOX = re.compile(r"(\d+)<\|box;([^|]*)\|>")


def parse_segmentation(text: str) -> list[tuple[int, int, Box, float]]:
    """Parse SAM's token stream into (frame, object_id, box, confidence). Masks are skipped."""
    out = []
    text = _MASK.sub("", text)
    parts = _FRAME.split(text)  # ['', frame, body, frame, body, ...]
    for i in range(1, len(parts), 2):
        frame = int(parts[i])
        for oid, fields in _BOX.findall(parts[i + 1]):
            kv = dict(p.split("=", 1) for p in fields.split(";") if "=" in p)
            box = (float(kv["x1"]), float(kv["y1"]), float(kv["x2"]), float(kv["y2"]))
            out.append((frame, int(oid), box, float(kv.get("c", 1.0))))
    return out


class Sam31Backend:
    """`SamBackend` over the Meta Model API. One request per concept prompt, per image.

    Image requests are stateless, so object ids restart each call; Cairn's reconciler does the
    re-identification (position + class + state). Video requests would give stable ids across
    frames and are the next step once the kill test passes.
    """

    def __init__(self, client: MetaClient, model: str = "sam-3.1", mime: str = "image/jpeg", max_parallel: int = 16):
        self.client, self.model, self.mime, self.max_parallel = client, model, mime, max_parallel

    def _one(self, data_url: str, prompt: str) -> list[RawTrack]:
        body = {
            "model": self.model,
            "metadata": {"include_confidence": "true"},
            "input": [{"type": "message", "role": "user", "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": data_url}]}],
        }
        return [RawTrack(f"{prompt}:{oid}", prompt, box, conf)
                for _, oid, box, conf in parse_segmentation(self.client.stream_text(body))]

    def track(self, image: bytes, prompts: list[str]) -> list[RawTrack]:
        """One request per concept, sent in parallel: measured serially, 13 prompts took ~27 s per frame."""
        data_url = f"data:{self.mime};base64,{base64.b64encode(image).decode()}"
        if not prompts:
            return []
        with ThreadPoolExecutor(max_workers=min(len(prompts), self.max_parallel)) as pool:
            results = list(pool.map(lambda p: self._one(data_url, p), prompts))  # keeps prompt order; raises on failure
        return [t for r in results for t in r]
