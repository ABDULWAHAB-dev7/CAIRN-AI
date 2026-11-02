"""Eval harness: the metrics from blueprint section 13, measured on recorded sessions.

A recorded session is a directory:
    frames.jsonl   every frame's detections, as the perception layer produced them
    actions.json   what perception cannot see: spoken or tapped steps, the boot test
    truth.json     ground truth: injected or hand-labelled faults, and (optional) track -> part labels
    meta.json      device, technician, bench, start time

`cairn eval` records the built-in simulated sessions and then scores them by replaying the files
through a fresh Session, which is exactly how a real recording is scored. Replace the directory
with clips from a real bench and the table is evidence about the product. As shipped, it is not:
the sessions are SYNTHETIC and say nothing about SAM 3.1 on a real camera.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .device import get_device
from .events import EventLog
from .frames import FrameStore
from .scenarios import chaos_session
from .session import Detection, Frame, Session

QUIET = dict(p_dropout=0.02, p_churn=0.01)
STRESS = dict(p_dropout=0.12, p_churn=0.06)  # a bad-lighting profile: much worse than the targets assume

FAULT_PLAN = [  # (seed, faults, noise, note). Four clean runs measure false alarms.
    (1, frozenset(), QUIET, "clean"), (2, frozenset(), QUIET, "clean"),
    (3, frozenset(), QUIET, "clean"), (4, frozenset(), QUIET, "clean"),
    (5, frozenset({"drop"}), QUIET, "dropped screw"),
    (6, frozenset({"skip_battery"}), QUIET, "skipped battery step"),
    (7, frozenset({"wrong_screw"}), QUIET, "wrong screw"),
    (8, frozenset({"extra_part"}), QUIET, "stray part"),
    (9, frozenset({"drop", "skip_battery", "wrong_screw"}), QUIET, "three faults"),
    (10, frozenset({"drop", "skip_battery", "wrong_screw", "extra_part"}), STRESS, "all faults, bad lighting"),
]

TARGETS = {
    "part_detection_recall": (">=", 0.95),
    "id_switch_rate": ("<=", 0.05),
    "missing_part_latency_s_max": ("<=", 5.0),
    "scripted_fault_catch_rate": (">=", 1.0),
    "false_alarm_rate_clean_runs": ("<=", 0.10),
}


# ---- recording ---------------------------------------------------------------------------------
def record_session(root: Path, seed: int, faults, noise: dict, note: str = "") -> Path:
    """Run one simulated session and write it out in the recorded-session format."""
    d = root / f"run_{seed:02d}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    store = FrameStore(d, "frames")
    b = chaos_session(seed, faults, sink=store.append, **noise)
    events = b.session.log.events()
    reg = next(e for e in events if e.type == "device_registered")
    actions = [{"ts": e.ts, "kind": "step", "step_id": e.payload["step_id"], "source": e.payload.get("source", "voice")} for e in events if e.type == "step_completed"]
    actions += [{"ts": e.ts, "kind": "boot_test", "passed": e.payload["passed"]} for e in events if e.type == "boot_test"]
    (d / "actions.json").write_text(json.dumps(actions), encoding="utf-8")
    (d / "truth.json").write_text(json.dumps({
        "faults": b.truth_log, "track_truth": b.track_truth, "synthetic": True, "seed": seed,
        "noise": noise, "note": note}), encoding="utf-8")
    (d / "meta.json").write_text(json.dumps({
        "device": reg.payload["device_id"], "technician": reg.payload["technician"],
        "bench": reg.payload["bench"], "start_ts": reg.ts, "head": b.session.log.head()}), encoding="utf-8")
    return d


# ---- replay + scoring ----------------------------------------------------------------------------
def replay(d: Path) -> Session:
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    s = Session(get_device(meta["device"]), EventLog())
    s.register(meta["start_ts"], meta["technician"], meta["bench"])
    items = []
    for line in (d / "frames.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        items.append((r["ts"], 1, Frame(r["frame_id"], r["ts"], tuple(
            Detection(**{**x, "xy": tuple(x["xy"]) if x.get("xy") else None,
                         "box": tuple(x["box"]) if x.get("box") else None}) for x in r["detections"]))))
    for a in json.loads((d / "actions.json").read_text(encoding="utf-8")):
        items.append((a["ts"], 0, a))  # at equal times the spoken step lands before the frame
    alerts = []
    for _, _, it in sorted(items, key=lambda x: (x[0], x[1])):
        if isinstance(it, Frame):
            alerts += s.observe(it)
        elif it["kind"] == "step":
            alerts += s.complete_step(it["step_id"], it["ts"], it.get("source", "voice"))
        else:
            s.record_boot_test(it["passed"], it["ts"])
    s.replayed_alerts = alerts
    return s


def score(d: Path) -> dict:
    s, g = replay(d), None
    g = s.graph
    truth = json.loads((d / "truth.json").read_text(encoding="utf-8"))
    track_truth, faults_log = truth.get("track_truth", {}), truth["faults"]
    seen = set(track_truth.values())
    bound = set(s.track_map.values())
    label, wrong, bindings = {}, 0, 0
    for e in s.log.events():  # an ID switch: a physical part labelled P is later labelled Q
        if e.type == "track_bound":
            bindings += 1
            t = track_truth.get(e.payload["track_id"])
            if label.setdefault(t, e.payload["part_id"]) != e.payload["part_id"]:
                wrong += 1
    exc = list(g.exceptions.values())
    caught, latencies = {}, []
    for f in faults_log:
        if f["kind"] == "drop":
            hit = [x for x in exc if x.type == "missing_part" and x.part_id == f["part"]]
            caught["drop"] = bool(hit)
            if hit:
                latencies.append(round(hit[0].ts - f["t_left"], 2))
        elif f["kind"] == "skip_battery":
            caught["skip_battery"] = any(x.type == "safety_violation" for x in exc)
        elif f["kind"] == "wrong_screw":
            caught["wrong_screw"] = any(a.kind == "wrong_fastener" for a in s.replayed_alerts)
        elif f["kind"] == "extra_part":
            caught["extra_part"] = any(x.type == "extra_part" for x in exc)
    kinds = {f["kind"] for f in faults_log}
    expected = ({"missing_part"} if "drop" in kinds else set()) | ({"safety_violation"} if "skip_battery" in kinds else set()) \
        | ({"extra_part"} if "extra_part" in kinds else set()) | ({"wrong_fastener"} if "wrong_screw" in kinds else set())
    types = [x.type for x in exc]
    ok, reasons = s.can_close()
    return {
        "run": truth["seed"], "note": truth.get("note", ""), "faults": sorted(kinds), "noise": truth.get("noise"),
        "parts_visible": len(seen), "parts_tracked": len(seen & bound), "tracks": bindings, "id_switches": wrong,
        "caught": caught, "missing_latency_s": latencies, "exceptions": types,
        "spurious": sorted(set(types) - expected), "can_close": ok, "close_blockers": reasons,
        "blocked_by_design": (not ok) and {x.type for x in exc if not x.resolved} <= expected,
        "events": len(s.log), "chain_ok": s.log.verify()[0],
        "reproduces_recording": s.log.head() == json.loads((d / "meta.json").read_text(encoding="utf-8"))["head"],
    }


def run_eval(plan=FAULT_PLAN, out: str | Path | None = None, sessions_dir: str | Path | None = None) -> dict:
    """Record the simulated plan (or score an existing directory of recordings) and report."""
    root = Path(sessions_dir) if sessions_dir else Path(out).parent / "sessions" if out else Path("eval/sessions")
    if plan is not None and not (sessions_dir and any(Path(sessions_dir).glob("run_*"))):
        for seed, faults, noise, note in plan:
            record_session(root, seed, faults, noise, note)
    rows = [score(d) for d in sorted(root.glob("run_*"))]
    clean = [r for r in rows if not r["faults"]]
    lat = [x for r in rows for x in r["missing_latency_s"]]
    caught = [v for r in rows for v in r["caught"].values()]
    tracks = sum(r["tracks"] for r in rows)
    metrics = {
        "part_detection_recall": round(sum(r["parts_tracked"] for r in rows) / sum(r["parts_visible"] for r in rows), 4),
        "id_switch_rate": round(sum(r["id_switches"] for r in rows) / tracks, 4) if tracks else None,
        "missing_part_latency_s_max": max(lat) if lat else None,
        "scripted_fault_catch_rate": round(sum(caught) / len(caught), 4) if caught else None,
        "false_alarm_rate_clean_runs": round(sum(1 for r in clean if r["exceptions"]) / len(clean), 4) if clean else None,
        "chains_verified": all(r["chain_ok"] for r in rows),
        "replay_reproduces_recording": all(r["reproduces_recording"] for r in rows),
        "task_completion_vs_baseline": "not measured (needs human technicians)",
    }
    report = {"synthetic": True, "runs": rows, "metrics": metrics,
              "targets": {k: f"{op} {v}" for k, (op, v) in TARGETS.items()},
              "pass": {k: _passes(metrics[k], *TARGETS[k]) for k in TARGETS}}
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(json.dumps(report, indent=2), encoding="utf-8")
        (Path(out).parent / "report.md").write_text(format_markdown(report), encoding="utf-8")
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


def format_markdown(report: dict) -> str:
    m = report["metrics"]
    out = ["# Eval report", "",
           "> **Synthetic.** These sessions come from the bench simulator, not a camera. They test the memory, "
           "safety and verification layers under injected dropout and tracker churn. Replace `eval/sessions/` "
           "with recorded clips (see `cairn/evaluation.py`) for evidence about real perception.", "",
           "| Metric | Value | Target | Result |", "|---|---|---|---|"]
    for k, t in report["targets"].items():
        out.append(f"| {k} | {m[k]} | {t} | {'PASS' if report['pass'][k] else '**FAIL**'} |")
    out += ["", f"Every event chain verified: {m['chains_verified']}. Replaying the recording reproduces the original "
            f"event log byte for byte: {m['replay_reproduces_recording']}.", "",
            "| Run | Setup | Parts | Tracked | ID switches | Caught | Missing-part latency | Spurious | Closes clean |",
            "|---|---|---|---|---|---|---|---|---|"]
    for r in report["runs"]:
        caught = ", ".join(f"{k}:{'yes' if v else 'NO'}" for k, v in r["caught"].items()) or "n/a"
        lat = ", ".join(f"{x}s" for x in r["missing_latency_s"]) or "-"
        out.append(f"| {r['run']:02d} | {r['note']} | {r['parts_visible']} | {r['parts_tracked']} | {r['id_switches']} | "
                   f"{caught} | {lat} | {', '.join(r['spurious']) or '-'} | {'yes' if r['can_close'] else 'no'} |")
    out += ["", "## Imperfections, honestly", ""]
    unexpected = [r for r in report["runs"] if not r["can_close"] and not r["blocked_by_design"]]
    spurious = [r for r in report["runs"] if r["spurious"]]
    missed = [(r, k) for r in report["runs"] for k, v in r["caught"].items() if not v]
    switched = [r for r in report["runs"] if r["id_switches"]]
    for r in unexpected:
        out.append(f"- **Run {r['run']:02d} ({r['note']}) could not close clean:** {'; '.join(r['close_blockers'])}.")
    for r in spurious:
        out.append(f"- **Run {r['run']:02d}:** false alarm(s) {', '.join(r['spurious'])}.")
    for r, k in missed:
        out.append(f"- **Run {r['run']:02d}:** missed the injected fault `{k}`.")
    for r in switched:
        out.append(f"- **Run {r['run']:02d} ({r['note']}):** {r['id_switches']} identity switches between interchangeable "
                   f"screws after the tracker issued new ids; every part still reconciled and the job "
                   f"{'closed clean' if r['can_close'] else 'stopped at the close gate'}.")
    held = [r for r in report["runs"] if r["blocked_by_design"]]
    if held:
        runs = ", ".join("%02d" % r["run"] for r in held)
        out.append(f"- Runs {runs} stop at the close gate by design: a stray part is an open "
                   "exception until the technician resolves it with a note. They then close, or close with exceptions.")
    if not (unexpected or spurious or missed):
        out.append("- No missed faults and no false alarms in this set. Real footage will be harsher; treat this as a floor on "
                   "the harness, not a result.")
    return "\n".join(out) + "\n"
