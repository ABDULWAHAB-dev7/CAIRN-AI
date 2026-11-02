"""Build a read-only static site of the bench screen replaying the simulated hero demo.

    python scripts/export_static.py [--out site] [--url https://example.vercel.app]

The page is the real cairn/ui/bench.html; a small shim answers its API calls from files written
here, so every click on the timeline shows the real rendered frame and the real state at that event.
Nothing is live: no camera, no model, no server. Deploy the output folder to any static host.
"""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from cairn import passport
from cairn.events import EventLog
from cairn.frames import FrameStore, render_png
from cairn.scenarios import hero_demo
from cairn.session import Session
from cairn.timeline import build_timeline

SHIM = r"""
<script>
/* Static replay shim: answers the app's API calls from ./data. Read-only. */
(() => {
  const real = window.fetch.bind(window);
  const json = (o, status = 200) => new Response(JSON.stringify(o), {status, headers: {'Content-Type': 'application/json'}});
  const file = (p) => real(p);
  let META = null, SESSION = null;
  const ready = Promise.all([real('data/meta.json').then(r => r.json()), real('data/session.json').then(r => r.json())])
    .then(([m, s]) => { META = m; SESSION = s; });
  window.fetch = async (url, opts = {}) => {
    await ready;
    const p = new URL(url, location.href).pathname, method = (opts.method || 'GET').toUpperCase();
    let m;
    if (p === '/sessions' && method === 'GET') return json({sessions: [META]});
    if (p === '/devices') return json({devices: ['demo_laptop']});
    if (p === '/demo' || (p === '/sessions' && method === 'POST')) return json({...META, snapshot: SESSION.snapshot});
    if (/^\/sessions\/[^/]+$/.test(p)) return json(SESSION);
    if (/\/timeline$/.test(p)) return file('data/timeline.json');
    if ((m = p.match(/\/at\/(\d+)$/))) { const r = await file(`data/at/${m[1]}.json`); return r.ok ? r : json({detail: 'no such event'}, 404); }
    if ((m = p.match(/\/frames\/([^/]+)\.png$/))) { const r = await file(`data/frames/${decodeURIComponent(m[1])}.png`); return r.ok ? r : json({detail: 'frame not in this replay'}, 404); }
    if (/\/close$/.test(p)) return file('data/passport.json');
    if (/\/passport\.pdf$/.test(p)) return file('data/passport.pdf');
    if (/\/passport\.html$/.test(p)) return file('data/passport.html');
    if (/\/passport$/.test(p)) return file('data/passport.json');
    if (/\/ask$/.test(p)) return json({text: 'This replay is read-only. Run the full app to talk to Cairn.', source: 'replay'});
    if (method !== 'GET') return json({detail: 'This is a read-only replay of a simulated session.'}, 409);
    return real(url, opts);
  };
  addEventListener('DOMContentLoaded', () => {
    const r = document.createElement('div');
    r.style.cssText = 'position:fixed;left:50%;transform:translateX(-50%);bottom:6px;z-index:20;background:#3a2a08;border:1px solid #fbbf24;color:#fde68a;padding:4px 12px;border-radius:6px;font:12px system-ui';
    r.textContent = 'Read-only replay of a SIMULATED session. No camera, no model. Not evidence about real perception.';
    document.body.appendChild(r);
  });
})();
</script>
"""

VERIFY_PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Cairn passport check</title><body style='font:16px system-ui;max-width:560px;margin:2rem auto;padding:0 1rem'>
<h1 style='color:#0f766e'>RECORD INTACT</h1>
<p><b>{status}</b> &middot; job {job} &middot; {device}</p>
<p>{acc}/{tot} fasteners, {extra} extra parts, {nexc} exceptions recorded.</p>
<p style='color:#64748b;font-size:13px'>Signature and hash chain were checked when this demo site was built, against a simulated session.
This page is static and does not re-verify. To verify independently, download the passport JSON and run
<code>cairn verify passport.json</code>.<br>Chain head {head}&hellip;</p>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site")
    ap.add_argument("--url", default="https://cairn-ai-eta.vercel.app")
    a = ap.parse_args()
    out = Path(a.out)
    shutil.rmtree(out, ignore_errors=True)
    (out / "data" / "at").mkdir(parents=True)
    (out / "data" / "frames").mkdir()

    with tempfile.TemporaryDirectory() as tmp:
        log, store = EventLog(), FrameStore(Path(tmp), "demo")
        bench = None
        for _, bench in hero_demo(log, sink=store.append, job="J-1042"):
            pass
        s, dev, events = bench.session, bench.session.device, log.events()

        def png(fid):
            row = store.row(fid)
            return render_png(row, s) if row else None

        timeline = build_timeline(dev, events)
        wanted = {0: None}
        for e in timeline:
            wanted[e["seq"]] = e
        frames_written = set()

        def write_frame(fid):
            if fid and fid not in frames_written and (data := png(fid)):
                (out / "data" / "frames" / f"{fid}.png").write_bytes(data)
                frames_written.add(fid)

        for seq in wanted:
            part = events[:seq]
            snap = Session.replica(dev, part).snapshot()
            ts = part[-1].ts if part else 0.0
            row = store.at_or_before(ts)
            ev = events[seq - 1] if seq else None
            fid = (ev.payload.get("frame") if ev else None) or (row["frame_id"] if row else None)
            write_frame(fid)
            (out / "data" / "at" / f"{seq}.json").write_text(
                json.dumps({"seq": seq, "ts": ts, "snapshot": snap, "frame_id": fid}), encoding="utf-8")
        for e in timeline:
            write_frame(e["frame"])
        (out / "data" / "frames" / "latest.png").write_bytes(png(store.latest()["frame_id"]))

        # the passport, issued before the final snapshot so the screen shows a closed job
        signer = passport.Signer.generate()
        p = passport.issue(s, "tech_a", signer, bench.t + 5, frame_png=png, verify_url=f"{a.url}/v.html")
        ok, problems = passport.verify(p, log.events())
        assert ok, problems
        events = log.events()
        timeline = build_timeline(dev, events)
        (out / "data" / "passport.json").write_text(passport.dumps(p), encoding="utf-8")
        (out / "data" / "passport.html").write_text(passport.to_html(p), encoding="utf-8")
        passport.to_pdf(p, out / "data" / "passport.pdf")
        for e in timeline:
            if e["seq"] not in wanted:  # the close event(s) added by issuing
                part = events[: e["seq"]]
                row = store.at_or_before(part[-1].ts)
                (out / "data" / "at" / f"{e['seq']}.json").write_text(json.dumps({
                    "seq": e["seq"], "ts": part[-1].ts, "snapshot": Session.replica(dev, part).snapshot(),
                    "frame_id": row["frame_id"] if row else None}), encoding="utf-8")
                if row:
                    write_frame(row["frame_id"])
        (out / "data" / "timeline.json").write_text(json.dumps({"entries": timeline}), encoding="utf-8")
        snap = s.snapshot()
        meta = {"id": "demo", "device": dev.id, "technician": "tech_a", "bench": "bench_02", "job_number": "J-1042",
                "phase": snap["phase"], "events": snap["events"], "verified": True, "closed": "verified"}
        (out / "data" / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
        (out / "data" / "session.json").write_text(json.dumps({**meta, "snapshot": snap, "recent_alerts": []}), encoding="utf-8")
        b = p["body"]
        (out / "v.html").write_text(VERIFY_PAGE.format(
            status=b["status"], job=b["job_number"], device=b["device"]["label"],
            acc=b["counts"]["fasteners_accounted"], tot=b["counts"]["fasteners_total"],
            extra=b["counts"]["extra_parts"], nexc=len(b["exceptions"]), head=b["event_chain"]["head"][:24]), encoding="utf-8")

    page = (Path(__file__).resolve().parents[1] / "cairn" / "ui" / "bench.html").read_text(encoding="utf-8")
    page = page.replace("<script>\nconst $ =", SHIM + "<script>\nconst $ =", 1)
    assert SHIM in page, "bench.html layout changed: shim not injected"
    page = page.replace("(async () => { if (sid) {", "(async () => { sid = 'demo'; localStorage.setItem('cairn.sid', 'demo'); if (sid) {", 1)
    (out / "index.html").write_text(page, encoding="utf-8")
    size = sum(f.stat().st_size for f in out.rglob("*") if f.is_file())
    print(f"{len(list((out / 'data' / 'at').iterdir()))} states, {len(frames_written) + 1} frames, {size / 1e6:.1f} MB -> {out}")


if __name__ == "__main__":
    main()
