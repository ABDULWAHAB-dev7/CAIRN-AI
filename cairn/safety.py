"""Hard-coded safety kernel. Rules are module constants; no API disables them.

The agent may call `explain(rule_id)`. It cannot allow, skip or edit a rule.
"""
from __future__ import annotations

from dataclasses import dataclass

from .graph import ObjectGraph


@dataclass(frozen=True)
class Action:
    kind: str  # "remove" | "pry"
    part_id: str | None = None
    near: str | None = None


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    rule: str | None = None
    reason: str | None = None


_ALLOW = Verdict(True)

_EXPLAIN = {
    "K1_ESD": "Put the ESD strap on before touching internals; static can silently kill a board.",
    "K2_POWER_OFF": "Disconnect the battery before removing any internal component; a live battery can short a board.",
    "K3_HAZARD_HALT": "Smoke, heat or swelling was reported. Stop all work and clear the hazard before continuing.",
    "K4_NO_PRY_NEAR_BATTERY": "Never pry near a connected battery; a punctured cell can ignite.",
}


def _k3(g: ObjectGraph, a: Action) -> Verdict:
    if g.hazard:
        return Verdict(False, "K3_HAZARD_HALT", f"{g.hazard} reported. {_EXPLAIN['K3_HAZARD_HALT']}")
    return _ALLOW


def _k1(g: ObjectGraph, a: Action) -> Verdict:
    if a.kind == "remove" and not g.esd_on:
        return Verdict(False, "K1_ESD", _EXPLAIN["K1_ESD"])
    return _ALLOW


def _k2(g: ObjectGraph, a: Action) -> Verdict:
    if a.kind == "remove" and a.part_id and not g.power_off:
        if g.device.parts[a.part_id].requires_power_off:
            return Verdict(False, "K2_POWER_OFF", _EXPLAIN["K2_POWER_OFF"])
    return _ALLOW


def _k4(g: ObjectGraph, a: Action) -> Verdict:
    if a.kind == "pry" and a.near == "battery" and not g.power_off:
        return Verdict(False, "K4_NO_PRY_NEAR_BATTERY", _EXPLAIN["K4_NO_PRY_NEAR_BATTERY"])
    return _ALLOW


_RULES = (_k3, _k1, _k2, _k4)  # evaluated in order; first denial wins


def check(graph: ObjectGraph, action: Action) -> Verdict:
    for rule in _RULES:
        v = rule(graph, action)
        if not v.allowed:
            return v
    return _ALLOW


def explain(rule_id: str) -> str:
    return _EXPLAIN.get(rule_id, "Unknown rule.")
