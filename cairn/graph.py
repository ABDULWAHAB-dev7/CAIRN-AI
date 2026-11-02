"""The object graph: a pure projection of the event log. Events are appended, never overwritten."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .device import Device, PartSpec, StepSpec
from .events import Event


class PartState(str, Enum):
    INSTALLED = "installed"
    IN_TRANSIT = "in_transit"
    REMOVED = "removed"
    LOST = "lost"
    REINSTALLED = "reinstalled"
    RETIRED = "retired"


class Phase(str, Enum):
    SEALED = "SEALED"
    OPENED = "OPENED"
    POWER_OFF = "POWER_OFF"
    COMPONENTS_OUT = "COMPONENTS_OUT"
    REASSEMBLING = "REASSEMBLING"
    VERIFIED = "VERIFIED"
    EXCEPTION = "EXCEPTION"


AT_REST = (PartState.INSTALLED, PartState.REINSTALLED, PartState.RETIRED)


@dataclass
class PartNode:
    spec: PartSpec
    state: PartState = PartState.INSTALLED
    zone: str = "device"
    hole: str | None = None
    confidence: float = 1.0
    track_id: str | None = None
    removed_once: bool = False
    well: int | None = None
    evidence: list[str] = field(default_factory=list)
    last_change_ts: float = 0.0


@dataclass
class ExceptionNode:
    id: str
    type: str
    severity: str
    detail: str
    ts: float
    part_id: str | None = None
    step_id: str | None = None
    evidence: list[str] = field(default_factory=list)
    resolved: bool = False
    resolved_by: str | None = None
    note: str | None = None


class ObjectGraph:
    def __init__(self, device: Device):
        self.device = device
        self.parts: dict[str, PartNode] = {pid: PartNode(spec) for pid, spec in device.parts.items()}
        self.exceptions: dict[str, ExceptionNode] = {}
        self.completed_steps: dict[str, float] = {}  # action steps, by timestamp
        self.reinstall_log: list[str] = []
        self.esd_on = False
        self.power_off = False
        self.hazard: str | None = None
        self.boot_test: bool | None = None
        self.verified = False
        self.closed_with_exceptions: str | None = None  # technician's note when closed over open exceptions
        self.registration: dict = {}
        self.started_ts: float | None = None
        self.last_ts: float = 0.0
        self.seq = 0

    # ---- projection -------------------------------------------------------------------------
    def apply(self, e: Event) -> None:
        p = e.payload
        self.seq = e.seq
        self.last_ts = e.ts
        if self.started_ts is None:
            self.started_ts = e.ts
        t = e.type
        if t == "device_registered":
            self.registration = dict(p)
        elif t == "part_zone":
            n = self.parts[p["part_id"]]
            zone = p["zone"]
            was_at_rest = n.state in (PartState.INSTALLED, PartState.REINSTALLED)
            n.zone, n.confidence, n.last_change_ts = zone, p.get("confidence", 1.0), e.ts
            n.track_id = p.get("track_id", n.track_id)
            n.well = p.get("well") if zone.startswith("tray_") else None
            if p.get("frame"):
                n.evidence.append(p["frame"])
            if zone == "device":
                if n.state != PartState.INSTALLED:
                    n.state, n.hole = PartState.REINSTALLED, p.get("hole")
                    self.reinstall_log.append(n.spec.id)
            elif zone == "hand":
                n.state = PartState.IN_TRANSIT
            else:
                n.state = PartState.REMOVED
            if was_at_rest and zone != "device":
                n.removed_once = True
        elif t == "part_lost":
            self.parts[p["part_id"]].state = PartState.LOST
            self.parts[p["part_id"]].last_change_ts = e.ts
        elif t == "part_retired":
            self.parts[p["part_id"]].state = PartState.RETIRED
            self.parts[p["part_id"]].last_change_ts = e.ts
        elif t == "step_completed":
            self.completed_steps[p["step_id"]] = e.ts
            effect = p.get("effect")
            if effect == "esd_on":
                self.esd_on = True
            elif effect == "power_off":
                self.power_off = True
            elif effect == "power_on":
                self.power_off = False
        elif t == "exception_raised":
            self.exceptions[p["id"]] = ExceptionNode(
                p["id"], p["type"], p["severity"], p["detail"], e.ts, p.get("part_id"),
                p.get("step_id"), list(p.get("evidence", [])),
            )
        elif t == "exception_resolved":
            x = self.exceptions[p["id"]]
            x.resolved, x.resolved_by, x.note = True, p.get("by", "system"), p.get("note")
        elif t == "hazard":
            self.hazard = p["kind"]
        elif t == "hazard_cleared":
            self.hazard = None
        elif t == "boot_test":
            self.boot_test = bool(p["passed"])
        elif t == "verified":
            self.verified = True
        elif t == "closed_with_exceptions":
            self.closed_with_exceptions = p.get("note", "")

    # ---- step status ------------------------------------------------------------------------
    def teardown_done(self, step: StepSpec) -> bool:
        if step.removes:
            return all(self.parts[pid].removed_once for pid in step.removes)
        return step.id in self.completed_steps

    def reverse_needs_work(self, step: StepSpec) -> bool:
        if step.removes:
            return any(self.parts[pid].state not in AT_REST for pid in step.removes)
        return step.id in self.completed_steps and f"r_{step.id}" not in self.completed_steps

    def preconditions_met(self, step: StepSpec) -> bool:
        return all(self.teardown_done(self.device.step(r)) for r in step.requires)

    def reassembling(self) -> bool:
        return all(self.teardown_done(s) for s in self.device.steps)

    # ---- queries (the three that run the product) ---------------------------------------------
    def missing_parts(self) -> list[str]:
        return sorted(pid for pid, n in self.parts.items() if n.state == PartState.LOST)

    def unaccounted_fasteners(self) -> list[str]:
        return sorted(
            pid for pid, n in self.parts.items()
            if n.spec.kind == "fastener"
            and n.state in (PartState.REMOVED, PartState.IN_TRANSIT, PartState.LOST)
        )

    def valid_next_steps(self) -> list[dict]:
        """Every step the technician may legally take now. The agent chooses among these."""
        out = []
        if self.reassembling():
            for s in self.device.reverse_steps():
                if self.reverse_needs_work(s):
                    out.append(self._describe(s, reverse=True))
                    break
        else:
            for s in self.device.steps:
                if not self.teardown_done(s) and self.preconditions_met(s):
                    out.append(self._describe(s))
        return out

    def next_step(self) -> dict | None:
        steps = self.valid_next_steps()
        return steps[0] if steps else None

    def _describe(self, s: StepSpec, reverse: bool = False) -> dict:
        if reverse:
            action = s.reverse_action or s.action.replace("Remove", "Reinstall", 1)
        else:
            action = s.action
        return {"id": f"r_{s.id}" if reverse else s.id, "action": action, "why": s.why,
                "reverse": reverse}

    def open_exceptions(self) -> list[ExceptionNode]:
        return [x for x in self.exceptions.values() if not x.resolved]

    def phase(self) -> Phase:
        if self.verified:
            return Phase.VERIFIED
        if self.hazard:
            return Phase.EXCEPTION
        nodes = self.parts.values()
        if any(n.state == PartState.REINSTALLED for n in nodes):
            return Phase.REASSEMBLING
        if any(n.removed_once and n.spec.kind == "component" and n.spec.requires_power_off
               for n in nodes):
            return Phase.COMPONENTS_OUT
        if self.power_off:
            return Phase.POWER_OFF
        if any(n.removed_once for n in nodes):
            return Phase.OPENED
        return Phase.SEALED

    # ---- serialisation ----------------------------------------------------------------------
    def part_json(self, pid: str) -> dict:
        n, s = self.parts[pid], self.parts[pid].spec
        edges = []
        if s.fastens:
            edges.append({"type": "fastens", "to": s.fastens})
        step = self.device.step_of_part.get(pid)
        if step:
            for r in self.device.step(step).requires:
                edges.append({"type": "requires", "to": r})
        return {
            "part_id": pid, "class": s.kind, "label": s.label, "state": n.state.value,
            "location": n.zone, "well": n.well, "code": self.device.code(pid), "confidence": n.confidence, "evidence": n.evidence[-3:],
            "edges": edges,
        }

    def counts(self) -> dict:
        f = [n for n in self.parts.values() if n.spec.kind == "fastener"]
        return {
            "fasteners_total": len(f),
            "fasteners_accounted": sum(1 for n in f if n.state in AT_REST),
            "retired": sum(1 for n in f if n.state == PartState.RETIRED),
        }
