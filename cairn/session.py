"""A repair session: turns observations into append-only events and policy decisions.

Perception (SAM 3.1, or a human tap) supplies detections. This module owns identity, memory,
the safety kernel, ordering checks and exceptions. The model never writes to the graph.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass

from . import invariants, safety
from .device import Device
from .events import Event, EventLog
from .graph import AT_REST, ObjectGraph, PartNode, PartState

_CONFLICT = "<conflict>"
LOST_GRACE_S = 3.0  # in-transit part unseen this long => missing (target <= 5 s)


@dataclass(frozen=True)
class Detection:
    track_id: str
    cls: str
    zone: str  # "device" | "hand" | "tray_N" | "bench"
    confidence: float = 1.0
    hole: str | None = None  # hole the part is being aimed at / sits in, when known
    xy: tuple[float, float] | None = None  # box centre; breaks re-ID ties (dropout vs new track)
    box: tuple[float, float, float, float] | None = None  # outline for the overlay
    well: int | None = None  # tray well the part sits in, when zone is a tray


@dataclass(frozen=True)
class Frame:
    frame_id: str
    ts: float
    detections: tuple[Detection, ...]


@dataclass(frozen=True)
class Alert:
    kind: str
    message: str
    severity: str = "info"  # info | warn | critical
    part_id: str | None = None
    rule: str | None = None
    ts: float = 0.0
    well: int | None = None  # well the overlay should pulse


def _mm(x: float | None) -> str:
    return f"{x:g}mm" if x is not None else "?"


class Session:
    def __init__(self, device: Device, log: EventLog | None = None, lost_grace_s: float = LOST_GRACE_S):
        self.device = device
        self.log = EventLog() if log is None else log
        self.graph = ObjectGraph(device)
        self.lost_grace_s = lost_grace_s
        self.track_map: dict[str, str] = {}
        self.part_track: dict[str, str] = {}
        self.last_seen: dict[str, float] = {}
        self.last_xy: dict[str, tuple[float, float]] = {}
        self.last_box: dict[str, tuple[float, float, float, float]] = {}
        self.head = self.log.head()
        self.frame_sink = None  # optional callable(Frame): the server keeps frames for the timeline
        self.extra_tracks: set[str] = set()
        self._warned: set[tuple] = set()
        for e in self.log.events():  # memory survives a lunch break: rebuild from the log
            self._fold(e)

    # ---- event plumbing ---------------------------------------------------------------------
    @classmethod
    def replica(cls, device: Device, events: list[Event]) -> "Session":
        """A read-only Session folded from some events (state at an earlier moment). Never append to it."""
        s = cls(device, EventLog())
        for e in events:
            s._fold(e)
        return s

    def _fold(self, e: Event) -> None:
        self.head = e.hash
        self.graph.apply(e)
        if e.type in ("part_zone", "track_bound") and e.payload.get("track_id"):
            self.track_map[e.payload["track_id"]] = e.payload["part_id"]
            self.part_track[e.payload["part_id"]] = e.payload["track_id"]
        if e.type == "part_zone":
            self.last_seen[e.payload["part_id"]] = e.ts
        if e.type == "exception_raised" and e.payload.get("track_id"):
            self.extra_tracks.add(e.payload["track_id"])

    def _emit(self, ts: float, type_: str, payload: dict) -> Event:
        ev = self.log.append(ts, type_, payload)
        self._fold(ev)
        return ev

    def register(self, ts: float, technician: str, bench: str, **extra) -> None:
        self._emit(ts, "device_registered",
                   {"device_id": self.device.id, "device_label": self.device.label,
                    "technician": technician, "bench": bench, **extra})
        self.baseline(ts)

    def baseline(self, ts: float, frame_id: str | None = None) -> None:
        """Snapshot of the sealed device: the inventory every later claim is measured against."""
        expected: dict[str, int] = {}
        for p in self.device.parts.values():
            expected[p.cls] = expected.get(p.cls, 0) + 1
        self._emit(ts, "baseline", {"expected": expected, "parts": len(self.device.parts),
                                    "fasteners": len(self.device.fasteners()), "frame": frame_id})

    def _raise(self, ts, type_, severity, detail, part_id=None, step_id=None, evidence=(),
               track_id=None) -> str | None:
        # Violations are deduped per step (a skipped step is one mistake, not eleven screws).
        key_part = None if type_ in ("safety_violation", "order_violation") and step_id else part_id
        for x in self.graph.open_exceptions():
            xp = None if x.type in ("safety_violation", "order_violation") and x.step_id else x.part_id
            if x.type == type_ and xp == key_part and x.step_id == step_id:
                return None  # already open: do not spam
        xid = f"x{len(self.graph.exceptions) + 1:03d}"
        payload = {"id": xid, "type": type_, "severity": severity, "detail": detail,
                   "part_id": part_id, "step_id": step_id, "evidence": list(evidence)}
        if track_id:
            payload["track_id"] = track_id
        self._emit(ts, "exception_raised", payload)
        return xid

    def _auto_resolve(self, ts, part_id, types, note) -> None:
        for x in self.graph.open_exceptions():
            if x.part_id == part_id and x.type in types:
                self._emit(ts, "exception_resolved", {"id": x.id, "by": "system", "note": note})

    def _resolve_step(self, ts, step_id, types, note) -> None:
        for x in self.graph.open_exceptions():
            if x.step_id == step_id and x.type in types:
                self._emit(ts, "exception_resolved", {"id": x.id, "by": "system", "note": note})

    # ---- perception in ----------------------------------------------------------------------
    def observe(self, frame: Frame) -> list[Alert]:
        alerts: list[Alert] = []
        if self.frame_sink:
            self.frame_sink(frame)
        tracks_now = {d.track_id for d in frame.detections}
        claimed: set[str] = set()
        for det in frame.detections:
            pid = self._bind(det, tracks_now, claimed, frame)
            if pid == _CONFLICT:
                continue  # two tracks claim one part this frame: perception noise, not a new object
            if pid is None:
                alerts += self._extra_part(det, frame)
                continue
            claimed.add(pid)
            self.last_seen[pid] = frame.ts
            if det.xy:
                self.last_xy[pid] = det.xy
            if det.box:
                self.last_box[pid] = det.box
            self._zone_update(self.graph.parts[pid], det.zone, det.hole, frame.ts,
                              frame.frame_id, det.confidence, det.track_id, alerts, well=det.well)
        alerts += self.tick(frame.ts)
        return alerts

    def observe_manual(self, part_id: str, zone: str, ts: float, hole: str | None = None,
                       well: int | None = None) -> list[Alert]:
        """Human-confirmed memory: the fallback when perception fails. Same policy, tap as input."""
        alerts: list[Alert] = []
        self.last_seen[part_id] = ts
        self._zone_update(self.graph.parts[part_id], zone, hole, ts, f"tap@{ts:g}", 1.0, None, alerts, well=well)
        alerts += self.tick(ts)
        return alerts

    def _bind(self, det: Detection, tracks_now: set[str], claimed: set[str], frame: Frame) -> str | None:
        pid = self.track_map.get(det.track_id)
        if pid:
            return pid if pid not in claimed else _CONFLICT
        cands = [s.id for s in self.device.parts_of(det.cls)
                 if s.id not in claimed and self.part_track.get(s.id) not in tracks_now]

        def rank(p: str):
            n = self.graph.parts[p]
            lost = 0 if n.state == PartState.LOST else 1
            zone = 0 if n.zone == det.zone else 1
            xy = self.last_xy.get(p)
            dist = math.dist(det.xy, xy) if det.xy and xy else 0.0
            return (lost, zone, round(dist, 1), 0 if p not in self.part_track else 1, p)

        if not cands:
            return None
        pid = min(cands, key=rank)
        self._emit(frame.ts, "track_bound", {"track_id": det.track_id, "part_id": pid,
                                             "rebind": pid in self.part_track, "frame": frame.frame_id})
        return pid

    def _extra_part(self, det: Detection, frame: Frame) -> list[Alert]:
        if det.track_id in self.extra_tracks:
            return []
        xid = self._raise(frame.ts, "extra_part", "medium",
                          f"Unexpected {det.cls} (track {det.track_id}) is not part of this device.",
                          evidence=[frame.frame_id], track_id=det.track_id)
        self.extra_tracks.add(det.track_id)
        return [Alert("extra_part", f"I see a {det.cls} that does not belong to this device.",
                      "warn", ts=frame.ts)] if xid else []

    # ---- the policy core --------------------------------------------------------------------
    def _zone_update(self, node: PartNode, zone: str, hole, ts, frame_id, conf, track_id,
                     alerts: list[Alert], well: int | None = None) -> None:
        spec, pid, state, prior_zone = node.spec, node.spec.id, node.state, node.zone
        if state == PartState.RETIRED:
            return
        if zone == "hand" and hole:
            self._check_hole(node, hole, ts, frame_id, alerts, install=False)
        if zone == node.zone and state != PartState.LOST:
            return
        payload = {"part_id": pid, "zone": zone, "confidence": conf, "frame": frame_id}
        if track_id:
            payload["track_id"] = track_id
        if well:
            payload["well"] = well
        step_id = self.device.step_of_part.get(pid)
        step = self.device.step(step_id) if step_id else None

        if zone == "device":
            h = hole or self._free_hole(spec.cls)
            payload["hole"] = h
            late = [d for d in self.device.dependents.get(step_id, ())
                    if self.graph.reverse_needs_work(self.device.step(d))] if step_id else []
            self._emit(ts, "part_zone", payload)
            if late:
                self._raise(ts, "order_violation", "high",
                            f"{spec.label} reinstalled before '{self.device.step(late[0]).action}' was undone.",
                            part_id=pid, step_id=step_id, evidence=[frame_id])
                alerts.append(Alert("order_violation", f"Wrong order: {self.device.step(late[0]).action.lower()} first.",
                                    "warn", pid, ts=ts))
            if not (hole and self._check_hole(node, hole, ts, frame_id, alerts, install=True)):
                self._auto_resolve(ts, pid, ("wrong_fastener",), "seated correctly")
            if state == PartState.IN_TRANSIT and prior_zone == "hand" and step_id:
                self._resolve_step(ts, step_id, ("safety_violation", "order_violation"),
                                   "action reversed before the part left the bench")
            self._step_alert(step, ts, alerts, reverse=True)
        elif state in (PartState.INSTALLED, PartState.REINSTALLED):
            alerts += self._removal(node, step, ts, frame_id)
            self._emit(ts, "part_zone", payload)
            self._step_alert(step, ts, alerts, reverse=False)
        else:
            self._emit(ts, "part_zone", payload)
            if zone.startswith("tray_"):
                self._auto_resolve(ts, pid, ("wrong_fastener",), "returned to its tray before installing")
            if state == PartState.LOST:
                self._auto_resolve(ts, pid, ("missing_part",), "found again")
                alerts.append(Alert("found", f"Found the {spec.label}.", "info", pid, ts=ts))
            if zone.startswith("tray_") and spec.kind == "fastener" and zone != spec.tray:
                alerts.append(Alert("wrong_tray", f"That {spec.label} goes in {spec.tray.replace('_', ' ')}.",
                                    "info", pid, ts=ts, well=self._free_well(spec.cls)))

    def _removal(self, node: PartNode, step, ts, frame_id) -> list[Alert]:
        pid, spec = node.spec.id, node.spec
        verdict = safety.check(self.graph, safety.Action("remove", pid))
        if not verdict.allowed:
            self._raise(ts, "safety_violation", "critical", f"{pid}: {verdict.reason}",
                        part_id=pid, step_id=step.id if step else None, evidence=[frame_id])
            return [Alert("safety_violation", f"Stop. {verdict.reason}", "critical", pid, verdict.rule, ts)]
        if step is None or self.graph.reassembling():
            return []
        if not self.graph.preconditions_met(step):
            missing = next(self.device.step(r) for r in step.requires
                           if not self.graph.teardown_done(self.device.step(r)))
            self._raise(ts, "order_violation", "high",
                        f"{spec.label} removed before '{missing.action}'.", part_id=pid,
                        step_id=step.id, evidence=[frame_id])
            return [Alert("order_violation", f"Wrong order. {missing.action} first.", "warn", pid, ts=ts)]
        if spec.kind == "component":
            held = [f.id for f in self.device.fasteners()
                    if f.fastens == pid and self.graph.parts[f.id].state in (PartState.INSTALLED, PartState.REINSTALLED)]
            if held:
                self._raise(ts, "order_violation", "high",
                            f"{spec.label} lifted with {len(held)} fastener(s) still in.", part_id=pid,
                            step_id=step.id, evidence=[frame_id])
                return [Alert("order_violation", f"The {spec.label} is still screwed in.", "warn", pid, ts=ts)]
        return []

    def _check_hole(self, node: PartNode, hole: str, ts, frame_id, alerts, install: bool) -> bool:
        target = self.device.holes.get(hole)
        spec = node.spec
        if target is None or target.cls == spec.cls:
            return False
        well = self._free_well(target.cls)
        msg = (f"That's a {_mm(spec.size_mm)} {spec.label}. That hole takes a {_mm(target.size_mm)}. "
               f"Tray {well:02d}.")
        if install:
            self._raise(ts, "wrong_fastener", "medium", msg, part_id=spec.id, evidence=[frame_id])
            alerts.append(Alert("wrong_fastener", msg, "warn", spec.id, ts=ts, well=well))
        elif (spec.id, hole) not in self._warned:
            self._warned.add((spec.id, hole))
            self._raise(ts, "wrong_fastener", "medium", msg, part_id=spec.id, evidence=[frame_id])
            alerts.append(Alert("wrong_fastener", msg, "warn", spec.id, ts=ts, well=well))
        return True

    def _free_well(self, cls: str) -> int | None:
        """The first empty tray well for a screw class: the one the overlay pulses."""
        wells = self.device.wells.get(self.device.tray_for(cls), ())
        used = {n.well for n in self.graph.parts.values() if n.state == PartState.REMOVED and n.well}
        return next((w for w in wells if w not in used), wells[0] if wells else None)

    def _free_hole(self, cls: str) -> str | None:
        used = {n.hole for n in self.graph.parts.values() if n.state == PartState.REINSTALLED}
        return next((p.hole for p in self.device.parts_of(cls) if p.hole not in used), None)

    def _step_alert(self, step, ts, alerts, reverse: bool) -> None:
        if step is None:
            return
        parts = [self.graph.parts[p] for p in step.removes]
        if reverse and all(p.state in AT_REST for p in parts):
            alerts.append(Alert("step_verified", f"Verified: {self.graph._describe(step, True)['action']}", ts=ts))
        elif not reverse and all(p.removed_once for p in parts):
            alerts.append(Alert("step_done", f"Done: {step.action}", ts=ts))

    # ---- time -------------------------------------------------------------------------------
    def tick(self, ts: float) -> list[Alert]:
        """Event-driven timers: a part that leaves the frame mid-transit is declared missing."""
        alerts = []
        for pid, n in self.graph.parts.items():
            if n.state != PartState.IN_TRANSIT:
                continue
            seen = self.last_seen.get(pid, n.last_change_ts)
            if ts - seen < self.lost_grace_s:
                continue
            self._emit(ts, "part_lost", {"part_id": pid, "last_seen": seen, "latency_s": round(ts - seen, 3)})
            when = time.strftime("%H:%M", time.localtime(seen))
            msg = (f"{n.spec.label.capitalize()} {self.device.code(pid)} left the bench at {when} "
                   f"and did not arrive in a tray well.")
            self._raise(ts, "missing_part", "high", msg, part_id=pid, evidence=n.evidence[-1:])
            alerts.append(Alert("missing_part", msg, "warn", pid, ts=ts, well=n.spec.well))
        return alerts

    # ---- human / explicit inputs --------------------------------------------------------------
    def complete_step(self, step_id: str, ts: float, source: str = "voice") -> list[Alert]:
        """Action steps SAM cannot see (ESD strap, battery disconnect). Spoken or tapped."""
        reverse = step_id.startswith("r_")
        spec = self.device.step(step_id[2:] if reverse else step_id)
        if step_id in self.graph.completed_steps:
            return []
        alerts: list[Alert] = []
        if reverse:
            effect = "power_on" if spec.effect == "power_off" else None
        else:
            effect = spec.effect
            if not self.graph.preconditions_met(spec):
                self._raise(ts, "order_violation", "high",
                            f"'{spec.action}' recorded before its prerequisites.", step_id=spec.id)
                alerts.append(Alert("order_violation", f"Wrong order for: {spec.action}.", "warn", ts=ts))
        self._emit(ts, "step_completed", {"step_id": step_id, "effect": effect, "source": source})
        alerts.append(Alert("step_done", f"Logged: {self.graph._describe(spec, reverse)['action']}.", ts=ts))
        return alerts

    def report_hazard(self, kind: str, ts: float) -> list[Alert]:
        self._emit(ts, "hazard", {"kind": kind})
        self._raise(ts, "hazard", "critical", f"{kind} reported.")
        return [Alert("hazard", f"Stop all work. {safety.explain('K3_HAZARD_HALT')}", "critical",
                      rule="K3_HAZARD_HALT", ts=ts)]

    def clear_hazard(self, ts: float, note: str) -> None:
        self._emit(ts, "hazard_cleared", {"note": note})
        for x in self.graph.open_exceptions():
            if x.type == "hazard":
                self._emit(ts, "exception_resolved", {"id": x.id, "by": "technician", "note": note})

    def resolve_exception(self, xid: str, ts: float, note: str, by: str = "technician") -> None:
        """The technician wins. The disagreement stays in the log and on the passport."""
        self._emit(ts, "exception_resolved", {"id": xid, "by": by, "note": note})

    def retire_part(self, part_id: str, ts: float, reason: str) -> None:
        self._emit(ts, "part_retired", {"part_id": part_id, "reason": reason})
        self._auto_resolve(ts, part_id, ("missing_part",), f"retired: {reason}")

    def record_boot_test(self, passed: bool, ts: float) -> None:
        self._emit(ts, "boot_test", {"passed": passed})

    def guard(self, action: safety.Action) -> safety.Verdict:
        """Pre-check a proposed action (voice: 'can I pull the SSD?')."""
        return safety.check(self.graph, action)

    # ---- summaries --------------------------------------------------------------------------
    def can_close(self) -> tuple[bool, list[str]]:
        return invariants.can_close(self.graph)

    def recap(self) -> dict:
        g = self.graph
        removed = [p for p, n in g.parts.items() if n.state in (PartState.REMOVED, PartState.IN_TRANSIT, PartState.LOST)]
        return {
            "phase": g.phase().value,
            "parts_out": len(removed),
            "unaccounted_fasteners": g.unaccounted_fasteners(),
            "missing": g.missing_parts(),
            "battery_connected": not g.power_off,
            "open_exceptions": [x.id for x in g.open_exceptions()],
            "next": g.next_step(),
        }

    def top_strip(self) -> dict:
        """The four numbers on the overlay: REMOVED, ACCOUNTED, MISSING, STATE."""
        g = self.graph
        out = [n for n in g.parts.values() if n.removed_once]
        missing = [n for n in out if n.state == PartState.LOST]
        transit = [n for n in out if n.state == PartState.IN_TRANSIT]
        return {"removed": len(out), "missing": len(missing),
                "accounted": len(out) - len(missing) - len(transit),
                "state": g.phase().value.lower().replace("_", " ")}

    def wells(self) -> list[dict]:
        """The 24 tray wells: which class each is for, and whether a removed part sits in it."""
        g = self.graph
        by_well = {n.well: pid for pid, n in g.parts.items() if n.state == PartState.REMOVED and n.well}
        out = []
        for tray, wells in sorted(self.device.wells.items()):
            for w in wells:
                pid = by_well.get(w)
                out.append({"n": w, "tray": tray, "cls": self.device.trays[tray], "filled": pid is not None,
                            "part": self.device.code(pid) if pid else None})
        used = {x["n"] for x in out}
        out += [{"n": n, "tray": None, "cls": None, "filled": False, "part": None}
                for n in range(1, 25) if n not in used]
        return sorted(out, key=lambda x: x["n"])

    def snapshot(self) -> dict:
        g = self.graph
        parts = {pid: g.part_json(pid) for pid in g.parts}
        for pid, pj in parts.items():
            pj["box"] = self.last_box.get(pid)
        return {
            **self.recap(),
            "job_number": g.registration.get("job_number"),
            "top": self.top_strip(),
            "wells": self.wells(),
            "closed": "verified" if g.verified else "with_exceptions" if g.closed_with_exceptions is not None else None,
            "counts": g.counts(),
            "parts": parts,
            "exceptions": [vars(x) for x in g.exceptions.values()],
            "invariants": [vars(i) for i in invariants.evaluate(g)],
            "head": self.head,
            "events": self.graph.seq,
        }
