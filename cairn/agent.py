"""Reasoning layer. Language is the model's job; truth is the graph's.

DeterministicAgent answers from graph queries alone (works offline, and is the replay-mode voice).
WonderAgent lets an LLM choose among tools and *valid* steps. It can explain a safety rule but
has no tool that changes the graph or the kernel.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol

from . import safety
from .graph import PartState
from .session import Session


@dataclass(frozen=True)
class Reply:
    text: str
    source: str = "graph"


class Agent(Protocol):
    def respond(self, session: Session, utterance: str) -> Reply: ...


def _join(items: list[str]) -> str:
    return ", ".join(items[:-1]) + f" and {items[-1]}" if len(items) > 1 else (items[0] if items else "")


class DeterministicAgent:
    def respond(self, s: Session, utterance: str) -> Reply:
        u = utterance.lower()
        g = s.graph
        if re.search(r"\b(dropped|lost|fell)\b", u):
            return Reply(self._dropped(s))
        if re.search(r"\b(missing|unaccounted|where)\b", u):
            return Reply(self._missing(s))
        if re.search(r"\b(done|finished|close|passport)\b", u):
            ok, reasons = s.can_close()
            return Reply("Yes. Run the passport." if ok else "Not yet: " + "; ".join(reasons) + ".")
        if re.search(r"\bwhy\b", u):
            nxt = g.next_step()
            return Reply(nxt["why"] if nxt else "There is nothing left to explain.")
        if re.search(r"\b(next|what now|what do i do)\b", u):
            return Reply(self._next(s))
        if re.search(r"\b(back|recap|where was i|status)\b", u):
            return Reply(self._recap(s))
        return Reply("Ask me what's next, what's missing, whether you're done, or why.")

    def _next(self, s: Session) -> str:
        steps = s.graph.valid_next_steps()
        if not steps:
            return "Nothing left to do. Run the boot test and issue the passport."
        text = steps[0]["action"] + "."
        if not s.graph.reassembling() and not s.graph.power_off and steps[0]["id"] != "t04":
            text += " The battery is still connected."
        open_x = s.graph.open_exceptions()
        if open_x:
            text += f" {len(open_x)} open exception{'s' if len(open_x) != 1 else ''}."
        return text

    def _missing(self, s: Session) -> str:
        g = s.graph
        lost = g.missing_parts()
        loose = g.unaccounted_fasteners()
        if lost:
            return f"Missing: {_join([g.parts[p].spec.label + ' (' + p + ')' for p in lost])}."
        if loose:
            return f"Nothing lost. {len(loose)} fasteners are out of the device and not yet reinstalled."
        return "Nothing is missing."

    def _dropped(self, s: Session) -> str:
        g = s.graph
        gone = g.missing_parts() or [p for p, n in g.parts.items() if n.state == PartState.IN_TRANSIT]
        if not gone:
            return "I have not lost sight of any part. Tell me which one."
        n = g.parts[gone[0]]
        tray = n.spec.tray
        held = sum(1 for m in g.parts.values() if m.spec.cls == n.spec.cls and m.zone == tray and m.state == PartState.REMOVED)
        return f"That's the {n.spec.label}. {tray.replace('_', ' ').capitalize()} has {held}. Check the floor mat."

    def _recap(self, s: Session) -> str:
        r = s.recap()
        bits = [f"{r['parts_out']} parts are out"]
        if r["unaccounted_fasteners"]:
            bits.append(f"{len(r['unaccounted_fasteners'])} fasteners unaccounted for")
        if r["battery_connected"]:
            bits.append("the battery is still connected")
        return "Welcome back. " + _join(bits).capitalize() + ". " + (r["next"]["action"] + "." if r["next"] else "")


# ---- LLM agent (Muse Wonder) ---------------------------------------------------------------------

WONDER_TOOLS = [
    {"name": "get_next_steps", "description": "List every step that is currently legal.", "args": {}},
    {"name": "missing_parts", "description": "Parts the graph considers lost.", "args": {}},
    {"name": "part_status", "description": "State, location and evidence for one part.", "args": {"part_id": "string"}},
    {"name": "can_close", "description": "Whether every verification invariant holds.", "args": {}},
    {"name": "explain_rule", "description": "Why a safety rule exists.", "args": {"rule_id": "string"}},
    {"name": "propose_step", "description": "Tell the technician the next step. Must be a legal step id.", "args": {"step_id": "string"}},
]

SYSTEM_PROMPT = (
    "You are Cairn, a repair copilot. You never touch the device; the technician acts. "
    "Answer only from tool results. Never invent a step: propose_step accepts only ids returned by "
    "get_next_steps. You cannot change or disable safety rules; you can only explain them."
)


class WonderAgent:
    """Tool-use loop over a model client.

    `client.complete(messages, tools)` must return {"tool": name, "args": {...}} or {"text": "..."}.
    Bind it to the Meta Model API (muse-wonder-1.0) in your deployment; see docs/ARCHITECTURE.md.
    """

    def __init__(self, client, max_rounds: int = 6):
        self.client, self.max_rounds = client, max_rounds

    def respond(self, s: Session, utterance: str) -> Reply:
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": utterance}]
        for _ in range(self.max_rounds):
            out = self.client.complete(messages, WONDER_TOOLS)
            if "text" in out:
                return Reply(out["text"], "wonder")
            result = self._call(s, out["tool"], out.get("args", {}))
            messages.append({"role": "tool", "name": out["tool"], "content": json.dumps(result)})
            if out["tool"] == "propose_step" and result.get("ok"):
                return Reply(result["action"] + ".", "wonder")
        return Reply(DeterministicAgent().respond(s, utterance).text, "fallback")

    def _call(self, s: Session, tool: str, args: dict) -> dict:
        g = s.graph
        if tool == "get_next_steps":
            return {"steps": g.valid_next_steps()}
        if tool == "missing_parts":
            return {"missing": g.missing_parts()}
        if tool == "part_status":
            pid = args.get("part_id")
            return g.part_json(pid) if pid in g.parts else {"error": f"unknown part {pid}"}
        if tool == "can_close":
            ok, reasons = s.can_close()
            return {"can_close": ok, "reasons": reasons}
        if tool == "explain_rule":
            return {"explanation": safety.explain(str(args.get("rule_id")))}
        if tool == "propose_step":
            legal = {x["id"]: x for x in g.valid_next_steps()}
            step = legal.get(args.get("step_id"))
            if not step:
                return {"ok": False, "error": "not a legal step now", "legal": list(legal)}
            return {"ok": True, **step}
        return {"error": f"unknown tool {tool}"}


class SafeAgent:
    """Use an LLM agent, but never let an outage stop the bench: fall back to the graph agent."""

    def __init__(self, primary: Agent, fallback: Agent | None = None):
        self.primary, self.fallback = primary, fallback or DeterministicAgent()

    def respond(self, s: Session, utterance: str) -> Reply:
        try:
            return self.primary.respond(s, utterance)
        except Exception as e:  # network, auth, malformed model output
            r = self.fallback.respond(s, utterance)
            return Reply(r.text, f"fallback ({type(e).__name__})")
