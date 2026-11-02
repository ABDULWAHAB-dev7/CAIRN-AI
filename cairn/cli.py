"""cairn demo | eval | verify"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import passport
from .agent import DeterministicAgent
from .events import EventLog
from .evaluation import format_table, run_eval
from .scenarios import hero_demo

NARRATION = {
    "intro": "The bench is set. Cairn is watching.",
    "cover_off": "ESD strap on, ten screws out, base cover off.",
    "reached_for_ssd_with_power_on": "Hand goes for the SSD. The battery is still connected.",
    "dropped_a_screw": "A battery screw falls and never reaches its tray.",
    "returned_from_lunch": "Thirty minutes later, a brand-new process opens the same event log.",
    "teardown_done": "Teardown finished; the dropped screw has been found.",
    "wrong_screw": "A 3mm screw is aimed at a 5mm hinge hole.",
    "reassembled": "Every step verified, every part back.",
    "boot_test": "Boot test passed.",
}


def cmd_demo(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    db = out / "repair.db"
    if db.exists():
        db.unlink()
    log = EventLog(str(db))
    agent, seen, bench = DeterministicAgent(), 0, None
    for label, bench in hero_demo(log):
        print(f"\n== {NARRATION.get(label, label)}")
        for a in bench.alerts[seen:]:
            if a.kind not in ("step_done", "step_verified"):
                print(f"   [{a.severity}] {a.message}")
        seen = len(bench.alerts)
        question = {"returned_from_lunch": "I'm back, status?", "dropped_a_screw": "I dropped a screw",
                    "teardown_done": "what's next?", "boot_test": "Am I done?"}.get(label)
        if question:
            print(f"   you: {question}\n   cairn: {agent.respond(bench.session, question).text}")
    s = bench.session
    signer = passport.Signer.load_or_create(out / "keys" / "bench_02.pem")
    p = passport.issue(s, "tech_a", signer, bench.t + 5)
    (out / "passport.json").write_text(passport.dumps(p), encoding="utf-8")
    (out / "passport.html").write_text(passport.to_html(p), encoding="utf-8")
    try:
        passport.to_pdf(p, out / "passport.pdf")
    except ImportError:
        print("(install cairn[pdf] for passport.pdf)")
    ok, problems = passport.verify(p, s.log.events())
    c = p["body"]["counts"]
    print(f"\nPassport: {c['fasteners_accounted']}/{c['fasteners_total']} fasteners, "
          f"{c['extra_parts']} extra parts, chain {'verified' if ok else problems}")
    print(f"Wrote passport.json, .html, .pdf and repair.db to {out}")
    return 0 if ok else 1


def cmd_eval(args) -> int:
    report = run_eval(out=args.out)
    print(format_table(report))
    return 0 if all(report["pass"].values()) else 1


def cmd_verify(args) -> int:
    p = json.loads(Path(args.passport).read_text(encoding="utf-8"))
    events = EventLog(args.db).events() if args.db else None
    ok, problems = passport.verify(p, events)
    print("VALID" if ok else "INVALID: " + "; ".join(problems))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cairn")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("demo", help="run the scripted hero demo and issue a passport")
    d.add_argument("--out", default="out")
    d.set_defaults(fn=cmd_demo)
    e = sub.add_parser("eval", help="run the simulated eval harness")
    e.add_argument("--out", default="eval/metrics.json")
    e.set_defaults(fn=cmd_eval)
    v = sub.add_parser("verify", help="verify a passport (and its event log)")
    v.add_argument("passport")
    v.add_argument("--db")
    v.set_defaults(fn=cmd_verify)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
