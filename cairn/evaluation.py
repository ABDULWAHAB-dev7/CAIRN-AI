"""Eval harness: the metrics from blueprint section 13, measured on simulated bench sessions.

SYNTHETIC. These numbers show the memory/safety/verification layers behave under dropout and
tracker churn. They say nothing about SAM 3.1 on a real bench; swap in recorded clips for that.
"""
from __future__ import annotations

import json
from pathlib import Path

from .scenarios import chaos_session

FAULT_PLAN = [  # (seed, faults). Four clean runs measure false alarms.
    (1, frozenset()), (2, frozenset()), (3, frozenset()), (4, frozenset()),
    (5, frozenset({"drop"})), (6, frozenset({"skip_battery"})), (7, frozenset({"wrong_screw"})),
    (8, frozenset({"extra_part"})), (9, frozenset({"drop", "skip_battery", "wrong_screw"})),
    (10, frozenset({"drop", "skip_battery", "wrong_screw", "extra_part"})),
]

TARGETS = {
    "part_detection_recall": (">=", 0.95),
    "id_switch_rate": ("<=", 0.05),
    "missing_part_latency_s_max": ("<=", 5.0),
    "scripted_fault_catch_rate": (">=", 1.0),
    "false_alarm_rate_clean_runs": ("<=", 0.10),
}


def _ever_exceptions(b, *types):
    return [x for x in b.session.graph.exceptions.values() if x.type in types]


def run_session(seed: int, faults: frozenset[str], **noise) -> dict:
    b = chaos_session(seed, faults, **noise)
    s, g = b.session, b.session.graph
    seen = set(b.track_truth.values())
    bound = set(s.track_map.values())
    # An ID switch: a physical part that was labelled P is later labelled Q. The first label of
    # interchangeable screws is arbitrary, so it is not scored.
    label, wrong, bindings = {}, 0, 0
    for e in s.log.events():
        if e.type == "track_bound":
            bindings += 1
            truth = b.track_truth.get(e.payload["track_id"])
            if label.setdefault(truth, e.payload["part_id"]) != e.payload["part_id"]:
                wrong += 1
    row = {
        "run": seed, "faults": sorted(faults), "parts": len(g.parts),
        "parts_tracked": len(seen & bound), "parts_visible": len(seen),
        "tracks": bindings, "id_switches": wrong,
        "exceptions": [x.type for x in g.exceptions.values()],
        "events": len(s.log), "chain_ok": s.log.verify()[0],
    }
    # Did Cairn catch each injected fault, and how fast?
    caught, latencies = {}, []
    for f in b.truth_log:
        if f["kind"] == "drop":
            hit = [x for x in _ever_exceptions(b, "missing_part") if x.part_id == f["part"]]
            caught["drop"] = bool(hit)
            if hit:
                latencies.append(round(hit[0].ts - f["t_left"], 2))
        elif f["kind"] == "skip_battery":
            caught["skip_battery"] = bool(_ever_exceptions(b, "safety_violation"))
        elif f["kind"] == "wrong_screw":
            caught["wrong_screw"] = any(a.kind == "wrong_fastener" for a in b.alerts)
        elif f["kind"] == "extra_part":
            caught["extra_part"] = bool(_ever_exceptions(b, "extra_part"))
    row["caught"], row["missing_latency_s"] = caught, latencies
    expected = {"missing_part"} if "drop" in faults else set()
    expected |= {"safety_violation"} if "skip_battery" in faults else set()
    expected |= {"extra_part"} if "extra_part" in faults else set()
    row["spurious"] = sorted(set(row["exceptions"]) - expected)
    ok, reasons = s.can_close()
    row["can_close"] = ok
    return row


def run_eval(plan=FAULT_PLAN, out: str | Path | None = None, **noise) -> dict:
    rows = [run_session(seed, faults, **noise) for seed, faults in plan]
    tracked = sum(r["parts_tracked"] for r in rows)
    visible = sum(r["parts_visible"] for r in rows)
    switches, tracks = sum(r["id_switches"] for r in rows), sum(r["tracks"] for r in rows)
    caught = [v for r in rows for v in r["caught"].values()]
    clean = [r for r in rows if not r["faults"]]
    lat = [x for r in rows for x in r["missing_latency_s"]]
    metrics = {
        "part_detection_recall": round(tracked / visible, 4),
        "id_switch_rate": round(switches / tracks, 4),
        "missing_part_latency_s_max": max(lat) if lat else None,
        "scripted_fault_catch_rate": round(sum(caught) / len(caught), 4) if caught else None,
        "false_alarm_rate_clean_runs": round(sum(1 for r in clean if r["exceptions"]) / len(clean), 4),
        "chains_verified": all(r["chain_ok"] for r in rows),
        "task_completion_vs_baseline": "not measured (needs human technicians)",
    }
    report = {"synthetic": True, "runs": rows, "metrics": metrics,
              "targets": {k: f"{op} {v}" for k, (op, v) in TARGETS.items()},
              "pass": {k: _passes(metrics[k], *TARGETS[k]) for k in TARGETS}}
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def _passes(value, op, target) -> bool:
    return value is not None and (value >= target if op == ">=" else value <= target)


def format_table(report: dict) -> str:
    lines = [f"{'METRIC':34} {'VALUE':>10} {'TARGET':>10}  RESULT"]
    for k, t in report["targets"].items():
        v = report["metrics"][k]
        lines.append(f"{k:34} {str(v):>10} {t:>10}  {'PASS' if report['pass'][k] else 'FAIL'}")
    lines.append("(synthetic sessions; not evidence about real perception)")
    return "\n".join(lines)
