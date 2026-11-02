"""Replay the hero demo's event log into web/data.json (one snapshot per meaningful event)."""
import json
from pathlib import Path

from cairn import invariants, passport
from cairn.events import EventLog
from cairn.graph import ObjectGraph
from cairn.scenarios import hero_demo

log = EventLog()
for _, b in hero_demo(log):
    pass
dev = b.session.device
signer = passport.Signer.generate()
p = passport.issue(b.session, "tech_a", signer, b.t + 5)
events = log.events()
order = sorted(dev.parts)
g = ObjectGraph(dev)
t0 = events[0].ts
frames = []
for e in events:
    g.apply(e)
    msg = None
    pl = e.payload
    if e.type == "exception_raised":
        msg = [pl["severity"], pl["detail"]]
    elif e.type == "exception_resolved":
        msg = ["info", f"Resolved {pl['id']}: {pl.get('note')}"]
    elif e.type == "step_completed":
        msg = ["info", f"Logged: {pl['step_id']}"]
    elif e.type == "part_lost":
        msg = ["warn", f"{pl['part_id']} left the frame and never reached a tray"]
    elif e.type == "boot_test":
        msg = ["info", "Boot test passed"]
    elif e.type == "passport_issued":
        msg = ["info", "Passport signed"]
    if e.type in ("track_bound",) or (e.type == "part_zone" and msg is None and frames and frames[-1]["i"] == e.seq - 1 and False):
        continue
    nxt = g.next_step()
    frames.append({
        "i": e.seq, "t": round(e.ts - t0, 1), "msg": msg, "phase": g.phase().value,
        "power_off": g.power_off, "next": nxt["action"] if nxt else None,
        "acc": g.counts()["fasteners_accounted"],
        "s": [g.parts[x].state.value for x in order],
        "z": [g.parts[x].zone for x in order],
        "open": len(g.open_exceptions()),
    })
out = {"synthetic": True, "parts": [{"id": x, "label": dev.parts[x].label, "kind": dev.parts[x].kind} for x in order],
       "frames": frames, "invariants": [vars(i) for i in invariants.evaluate(g)],
       "passport": {"counts": p["body"]["counts"], "head": p["body"]["event_chain"]["head"],
                    "signature": p["signature"], "public_key": p["body"]["signer"]["public_key"],
                    "exceptions": p["body"]["exceptions"]}}
Path("web/data.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
print(len(frames), "frames")
