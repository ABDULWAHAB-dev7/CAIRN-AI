"""Verification invariants. All five must hold before a passport can be issued."""
from __future__ import annotations

from dataclasses import dataclass

from .graph import ObjectGraph, PartState


@dataclass(frozen=True)
class Invariant:
    name: str
    ok: bool
    detail: str


def _open(g: ObjectGraph, *types: str):
    return [x for x in g.open_exceptions() if x.type in types]


def evaluate(g: ObjectGraph) -> list[Invariant]:
    f_bad = g.unaccounted_fasteners()
    count = Invariant(
        "count", not f_bad,
        "every removed fastener is reinstalled or retired" if not f_bad
        else f"{len(f_bad)} fastener{'s' if len(f_bad) != 1 else ''} unaccounted: {', '.join(f_bad)}",
    )
    order_bad = _open(g, "order_violation", "wrong_fastener")
    order = Invariant(
        "order", not order_bad,
        "no step ran before its preconditions" if not order_bad
        else f"{len(order_bad)} unresolved ordering problem(s)",
    )
    safe_bad = _open(g, "safety_violation", "hazard")
    safe_ok = not safe_bad and g.hazard is None
    safety = Invariant(
        "safety", safe_ok,
        "power off before component removal; no active hazard" if safe_ok
        else "unresolved safety exception",
    )
    loose = [pid for pid, n in g.parts.items()
             if n.state in (PartState.REMOVED, PartState.IN_TRANSIT, PartState.LOST)]
    extra = _open(g, "extra_part")
    closure = Invariant(
        "closure", not loose and not extra,
        "tray empty; no extra parts" if not loose and not extra
        else f"{len(loose)} part(s) not reinstalled, {len(extra)} extra part(s)",
    )
    if g.boot_test is True:
        function = Invariant("function", True, "boot test passed")
    else:
        function = Invariant(
            "function", False, "boot test not run" if g.boot_test is None else "boot test failed"
        )
    return [count, order, safety, closure, function]


def can_close(g: ObjectGraph) -> tuple[bool, list[str]]:
    reasons = [f"{i.name}: {i.detail}" for i in evaluate(g) if not i.ok]
    return (not reasons, reasons)
