"""Human-readable timeline: every event the technician cares about, newest at the bottom."""
from __future__ import annotations

from .device import Device
from .events import Event
from .graph import ObjectGraph, PartState

AT_REST = (PartState.INSTALLED, PartState.REINSTALLED)


def build_timeline(device: Device, events: list[Event]) -> list[dict]:
    """Fold the log once, naming each change by what it meant: removed, placed, returned, exception."""
    g = ObjectGraph(device)
    out: list[dict] = []

    def add(e, kind, text, frame=None, severity="info"):
        out.append({"seq": e.seq, "ts": e.ts, "kind": kind, "text": text, "frame": frame, "severity": severity})

    for e in events:
        p = e.payload
        t = e.type
        if t == "part_zone":
            n = g.parts[p["part_id"]]
            spec, code = n.spec, device.code(p["part_id"])
            before, zone, name = n.state, p["zone"], f"{code} {spec.label}"
            if zone.startswith("tray_"):
                where = f"tray {p['well']:02d}" if p.get("well") else zone.replace("_", " ")
                if before in AT_REST:
                    add(e, "removed", f"Removed {name}, placed in {where}", p.get("frame"))
                elif before == PartState.LOST:
                    add(e, "returned", f"Found {name}, placed in {where}", p.get("frame"))
                else:
                    add(e, "placed", f"Placed {name} in {where}", p.get("frame"))
            elif zone in ("hand", "bench") and before in AT_REST:
                add(e, "removed", f"Removed {name}", p.get("frame"))
            elif zone == "out_of_view" and before in AT_REST:  # open bench: it stopped being there, no picture of the moment
                add(e, "removed", f"{name.capitalize()} no longer on the laptop (not seen for several seconds)")
            elif zone == "device" and before not in AT_REST:
                add(e, "returned", f"Reinstalled {name}", p.get("frame"))
        elif t == "part_lost":
            n = g.parts[p["part_id"]]
            add(e, "lost", f"{device.code(p['part_id'])} {n.spec.label} left the bench", None, "warn")
        elif t == "exception_raised":
            add(e, "exception", p["detail"], (p.get("evidence") or [None])[0],
                "critical" if p["severity"] == "critical" else "warn")
        elif t == "exception_resolved":
            add(e, "resolved", f"Resolved {p['id']} ({p.get('by', 'system')}): {p.get('note') or ''}".strip())
        elif t == "step_completed":
            sid = p["step_id"]
            base = device.step(sid[2:] if sid.startswith("r_") else sid)
            label = base.reverse_action if sid.startswith("r_") else base.action
            add(e, "step", f"Logged: {label}")
        elif t == "baseline":
            add(e, "baseline", "Job started on an open bench: the camera finds the parts as it goes" if device.open_bench else
                f"Baseline snapshot of the sealed device ({p['parts']} parts, {p['fasteners']} fasteners)", p.get("frame"))
        elif t == "boot_test":
            add(e, "step", "Boot test " + ("passed" if p["passed"] else "FAILED"), None,
                "info" if p["passed"] else "warn")
        elif t == "part_retired":
            add(e, "resolved", f"Retired {device.code(p['part_id'])}: {p['reason']}")
        elif t in ("hazard", "hazard_cleared"):
            add(e, "exception" if t == "hazard" else "resolved",
                f"Hazard reported: {p['kind']}" if t == "hazard" else f"Hazard cleared: {p.get('note')}",
                None, "critical" if t == "hazard" else "info")
        elif t == "passport_issued":
            add(e, "close", f"Job closed: {p.get('status', 'signed')}")
        g.apply(e)
    return out
