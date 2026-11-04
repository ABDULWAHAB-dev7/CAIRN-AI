"""Build the demo video from the real app.

What it films: screenshots of the real bench screen, passport page and verify page while the app replays the SIMULATED
scripted demo (`cairn/scenarios.py`), with captions in a bar under the picture, plus title, architecture and "what is
real" cards. Nothing is staged: the counts, the safety stop and the signed passport come from the running code. Every
bench shot is labelled "SIMULATED REPLAY". Perception is off (CAIRN_PERCEPTION=none), so no Meta call is made.

Needs: playwright (+ chromium), Pillow and ffmpeg on PATH.
    python scripts/make_demo_video.py --out out/video [--sam-overlay path/to/overlay.jpg --sam-credit "..."]
Writes cairn-demo.mp4 (the full cut) and cairn-30s.mp4, plus the stills and captions.json.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
W, H = 1920, 1080
BH = 170  # caption bar height; the app gets the rest
CH = H - BH

# ---------------------------------------------------------------------------------------------------------------
# The cut. kind: card | bench (review a past event of the replay) | modal | page | image.   clip = seconds in the 30 s cut.
# ---------------------------------------------------------------------------------------------------------------
REPLAY = "SIMULATED REPLAY  ·  recognition is off in this build"
SHOTS = [
    dict(id="title", kind="card", secs=9, clip=None, caption="", card="title"),
    dict(id="hook1", kind="bench", seq=2, secs=6, clip=4,
         caption="AI can design a laptop. It can't take one apart."),
    dict(id="hook2", kind="bench", seq=2, secs=7, clip=None,
         caption="It can recognise a screw. It forgets the screw the moment it leaves the frame."),
    dict(id="sam", kind="image", secs=10, clip=None, label="REAL PHOTO  ·  live SAM 3.1 call, 3 Nov 2026",
         caption="What SAM 3.1 saw on a real open laptop photo: dozens of screws. It found no battery, drive or cover."),
    dict(id="identity", kind="bench", seq=24, secs=7, clip=None, hl=["#left"],
         caption="Cairn gives every part an identity, a location and a state."),
    dict(id="drop1", kind="bench", seq=69, secs=6, clip=None, hl=[".ev.sel"],
         caption="The drop: a screw leaves the bench and never reaches a tray."),
    dict(id="drop2", kind="bench", seq=69, secs=6, clip=5, hl=["#st-miss", "#parts-out"],
         caption="MISSING 1, with the part named. It noticed before I did."),
    dict(id="danger1", kind="bench", seq=55, secs=6, clip=None, hl=[".ev.sel"],
         caption="The danger: a hand reaches for an SSD screw while the battery is still connected."),
    dict(id="danger2", kind="bench", seq=55, secs=7, clip=6, hl=["#step"],
         caption="Stop. Disconnect the battery first. A safety rule the model cannot override."),
    dict(id="wrong1", kind="bench", seq=100, secs=6, clip=None, hl=[".ev.sel"],
         caption="The wrong screw: a 3 mm screw about to go into a 5 mm hole."),
    dict(id="wrong2", kind="bench", seq=100, secs=5, clip=None, hl=[".ev.sel"],
         caption="That hole takes a 5 mm. Tray 16."),
    dict(id="lunch1", kind="bench", seq=73, secs=5, clip=None, hl=["#st-miss", "#parts-out"],
         caption="Then a 30-minute break, with one screw still missing."),
    dict(id="lunch2", kind="bench", seq=76, secs=8, clip=None, hl=[".ev.sel"],
         caption="Back from lunch: same next step. The missing screw was never forgotten; it is found and placed in tray 11."),
    dict(id="reassembly", kind="bench", seq=156, secs=6, clip=None,
         caption="Reassembly: every screw back where it came from, each step checked."),
    dict(id="close", kind="modal", secs=8, clip=None,
         caption="Close the job: VERIFIED. 23 of 23 fasteners. Three exceptions recorded, none hidden."),
    dict(id="passport", kind="page", path="/sessions/{sid}/passport.html", secs=7, clip=None, label="THE SIMULATED DEMO JOB'S PASSPORT",
         caption="A signed repair passport: counts that reconcile, evidence frames, a hash chain over the log."),
    dict(id="verify", kind="page", path="/v/{sid}", secs=7, clip=6, label="THE PUBLIC VERIFY PAGE  ·  the QR code opens this", zoom=2.4,
         caption="Anyone can check it. Change one number and the signature fails."),
    dict(id="arch", kind="card", secs=10, clip=None, caption="", card="arch"),
    dict(id="truth", kind="card", secs=17, clip=None, caption="", card="truth"),
    dict(id="end", kind="card", secs=8, clip=5, caption="", card="end"),
]

HL_JS = """
(() => {
  const ensure = () => { if (!document.getElementById('vstyle')) { const st = document.createElement('style'); st.id = 'vstyle';
    st.textContent = '.vhl{outline:4px solid #ab8ff1!important;outline-offset:6px;border-radius:10px;position:relative;z-index:50}';
    document.documentElement.appendChild(st); } };
  window.__hl = sels => { ensure(); document.querySelectorAll('.vhl').forEach(e => e.classList.remove('vhl'));
    (sels || []).forEach(s => { try { const e = document.querySelector(s); if (e) { (s === '#st-miss' ? e.parentElement : e).classList.add('vhl'); } } catch (x) {} }); };
})();
"""

BASE_CSS = """<link rel="stylesheet" href="%(base)s/ui/tokens.css"><style>
html,body{margin:0;height:100%%;background:#08080a;color:#dad7de;font-family:"Inter Tight",system-ui,sans-serif}
.bar{position:absolute;left:0;top:0;width:1920px;height:170px;box-sizing:border-box;background:#0d0d12;border-top:3px solid #ab8ff1;
  padding:16px 70px 0;display:flex;flex-direction:column;justify-content:center}
.bar .lab{font:600 18px/1 "Inter Tight",system-ui,sans-serif;letter-spacing:1.4px;color:#ab8ff1;margin-bottom:10px;text-transform:uppercase}
.bar .cap{font:500 41px/1.2 "Inter Tight",system-ui,sans-serif;letter-spacing:-.4px;color:#fff;max-width:1780px}
</style>"""

CARD_BASE = """<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="%(base)s/ui/tokens.css"><style>
html,body{margin:0;height:100%%;background:#08080a;color:#dad7de;font-family:"Inter Tight",system-ui,sans-serif}
body{display:flex;align-items:center;justify-content:center;
 background:radial-gradient(ellipse 80%% 55%% at 50%% 118%%,rgba(142,108,228,.42),transparent 70%%),#08080a}
.wrap{width:1560px}h1{font-size:150px;font-weight:400;letter-spacing:-6px;margin:0;line-height:1}
h2{font-size:64px;font-weight:400;letter-spacing:-2px;margin:0 0 30px}
p{font-size:34px;line-height:1.35;margin:0 0 18px;color:#aeaac0}.big{font-size:48px;color:#dad7de;letter-spacing:-1px}
.pill{display:inline-block;font-size:22px;padding:8px 16px;border:1px solid rgba(171,143,241,.6);border-radius:999px;color:#dad7de;margin-bottom:30px;letter-spacing:.5px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:26px}.box{border:1px solid rgba(174,170,192,.25);border-radius:12px;padding:24px 30px;background:rgba(23,23,28,.7)}
.box h3{margin:0 0 12px;font-size:28px;font-weight:600;letter-spacing:0;color:#ab8ff1}.box p,.box li{font-size:26px;line-height:1.32;color:#dad7de;margin:0 0 6px}
ul{margin:0;padding-left:26px}.warn h3{color:#f0707a}small{font-size:22px;color:#8b8e9c}
.flow{display:flex;align-items:stretch;gap:0;margin:20px 0 34px}.step{flex:1;border:1px solid rgba(174,170,192,.3);border-radius:10px;padding:20px 16px;background:rgba(23,23,28,.8);text-align:center}
.step b{display:block;font-size:30px;margin-bottom:6px}.step span{font-size:21px;color:#aeaac0}.arrow{align-self:center;font-size:34px;color:#ab8ff1;padding:0 8px}
.step.k{border-color:#ab8ff1}.step.n{border-color:#f0707a}
</style></head><body><div class="wrap">%(body)s</div></body></html>"""

CARDS = {
    "title": """<div class="pill">REPLAY OF A SIMULATED TEARDOWN</div><h1>Cairn</h1>
<p class="big" style="margin-top:18px">Object permanence for physical repair.</p>
<p style="margin-top:56px;font-size:30px">This video replays a simulated teardown in the real app. Recognition is off in this build
(Meta billing). <span style="color:#dad7de">The memory, the safety stop and the passport are real.</span></p>""",
    "arch": """<h2>The model proposes. The session decides.</h2>
<div class="flow"><div class="step"><b>Camera</b><span>or a tap</span></div><div class="arrow">→</div>
<div class="step"><b>Perception</b><span>SAM 3.1 proposes detections</span></div><div class="arrow">→</div>
<div class="step k"><b>Session</b><span>decides: policy, identity</span></div><div class="arrow">→</div>
<div class="step k"><b>Event log</b><span>append-only, hash chain</span></div><div class="arrow">→</div>
<div class="step"><b>Object graph</b><span>every part: id, place, state</span></div></div>
<div class="flow"><div class="step n"><b>Safety kernel</b><span>4 hard rules, no model override</span></div><div class="arrow">→</div>
<div class="step"><b>Verification</b><span>5 checks before close</span></div><div class="arrow">→</div>
<div class="step k"><b>Repair passport</b><span>Ed25519-signed, QR, verify page</span></div></div>
<p>The model never writes to the graph. Muse Wonder can only ask questions and propose a legal step; the log records what happened.</p>""",
    "truth": """<h2>What is real, and what is not</h2><div class="grid">
<div class="box"><h3>Real and tested</h3><ul><li>Hash-chained event log; tampering is detected</li><li>Object graph, safety kernel, five verification checks</li>
<li>Signed passport and public verify page</li><li>113 automated tests, Docker image verified</li></ul></div>
<div class="box"><h3>Live Meta calls, 2–3 Nov 2026</h3><ul><li>SAM 3.1 and Muse Wonder calls succeeded</li>
<li>SAM found laptop, screws, fan, cables and board on real photos; it found no battery, drive, cover or memory</li></ul></div>
<div class="box warn"><h3>Simulated</h3><ul><li>Every teardown in this video</li><li>The eval table: ten simulated sessions</li></ul></div>
<div class="box warn"><h3>Not proven</h3><ul><li>Perception during a real teardown</li><li>Meta has refused SAM calls since 3 Nov (billing)</li></ul></div></div>
<p style="margin-top:26px"><small>Everything is dated and linked in docs/PROOF.md.</small></p>""",
    "end": """<h2 style="font-size:84px;letter-spacing:-3px">The first AI that can take something apart and put it back together.</h2>
<p class="big" style="margin-top:50px">Cairn</p><p>github.com/ABDULWAHAB-dev7/CAIRN-AI<br>cairn-ai-eta.vercel.app</p>""",
}


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def wait_health(base: str, timeout: float = 40) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen(base + "/health", timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit("server did not start")


def compose(top_png: bytes, bar_png: bytes, out: Path) -> None:
    img = Image.new("RGB", (W, H), (8, 8, 10))
    img.paste(Image.open(io.BytesIO(top_png)).convert("RGB").crop((0, 0, W, CH)), (0, 0))
    img.paste(Image.open(io.BytesIO(bar_png)).convert("RGB"), (0, CH))
    img.save(out)


def capture(args, base: str, stills: Path) -> dict:
    """One PNG per shot. Returns the session id used."""
    sam_img = None
    if args.sam_overlay and Path(args.sam_overlay).exists():
        sam_img = base64.b64encode(Path(args.sam_overlay).read_bytes()).decode()
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": W, "height": CH}, device_scale_factor=1)
        ctx.add_init_script(HL_JS)
        # a second page that renders the caption bar and the cards at full size
        art = b.new_context(viewport={"width": W, "height": H}, device_scale_factor=1).new_page()

        def bar(shot) -> bytes:
            label = shot.get("label", REPLAY)
            art.set_content("<!doctype html><html><head><meta charset='utf-8'>" + BASE_CSS % {"base": base} + "</head><body>"
                            f"<div class='bar'><div class='lab'>{esc(label)}</div><div class='cap'>{esc(shot['caption'])}</div></div></body></html>",
                            wait_until="networkidle")
            art.wait_for_timeout(250)
            return art.screenshot(clip={"x": 0, "y": 0, "width": W, "height": BH})

        pg = ctx.new_page()
        pg.goto(base + "/bench", wait_until="networkidle")
        pg.wait_for_timeout(800)
        if not pg.is_visible("#j-dev"):
            pg.click("#btn-new")
        pg.click("text=Replay the scripted demo")
        pg.wait_for_selector("text=Demo job ready", timeout=90000)
        pg.evaluate("hide()")
        pg.wait_for_timeout(600)
        sid = pg.evaluate("sid")

        def settle():
            pg.wait_for_function("(() => { const f = document.getElementById('feed'); return f && f.complete && f.naturalWidth > 0; })()", timeout=20000)
            pg.wait_for_timeout(900)

        for shot in [s for s in SHOTS if s["kind"] == "bench"]:
            pg.evaluate("s => openReview(s)", shot["seq"])
            settle()
            pg.evaluate("h => __hl(h)", shot.get("hl", []))
            pg.evaluate("() => { const e = document.querySelector('.ev.sel'); if (e) e.scrollIntoView({block: 'center'}); }")
            pg.wait_for_timeout(250)
            compose(pg.screenshot(), bar(shot), stills / f"{shot['id']}.png")
        # live again, then close the job in the real UI
        pg.evaluate("() => { const b = [...document.querySelectorAll('button')].find(x => /Back to live/.test(x.textContent)); if (b) b.click(); }")
        pg.wait_for_timeout(1200)
        pg.evaluate("__hl([])")
        pg.click("#btn-close")
        pg.wait_for_selector("text=JOB CLOSED", timeout=30000)
        pg.wait_for_timeout(700)
        shot = next(s for s in SHOTS if s["kind"] == "modal")
        compose(pg.screenshot(), bar(shot), stills / f"{shot['id']}.png")
        pg.evaluate("hide()")

        pages = ctx.new_page()
        for shot in [s for s in SHOTS if s["kind"] == "page"]:
            pages.goto(base + shot["path"].format(sid=sid), wait_until="networkidle")
            if shot.get("zoom"):
                pages.evaluate("z => { document.body.style.zoom = z; }", shot["zoom"])
            pages.wait_for_timeout(900)
            compose(pages.screenshot(), bar(shot), stills / f"{shot['id']}.png")

        for shot in [s for s in SHOTS if s["kind"] == "card"]:
            art.set_content(CARD_BASE % {"base": base, "body": CARDS[shot["card"]]}, wait_until="networkidle")
            art.wait_for_timeout(500)
            art.screenshot(path=str(stills / f"{shot['id']}.png"))

        for shot in [s for s in SHOTS if s["kind"] == "image"]:
            if sam_img is None:
                continue
            art.set_viewport_size({"width": W, "height": CH})
            art.set_content("<!doctype html><html><head><meta charset='utf-8'>" + BASE_CSS % {"base": base} + "</head><body>"
                            f"<div style='position:relative;width:{W}px;height:{CH}px;background:#000'>"
                            f"<img src='data:image/jpeg;base64,{sam_img}' style='width:{W}px;height:{CH}px;object-fit:contain'>"
                            f"<div style='position:absolute;right:24px;bottom:14px;font:400 17px/1.3 \"Inter Tight\",sans-serif;color:#aeaac0;"
                            f"background:rgba(8,8,10,.78);padding:4px 10px;border-radius:4px;max-width:1100px;text-align:right'>{esc(args.sam_credit)}</div></div>"
                            "</body></html>", wait_until="networkidle")
            art.wait_for_timeout(500)
            top = art.screenshot()
            art.set_viewport_size({"width": W, "height": H})
            compose(top, bar(shot), stills / f"{shot['id']}.png")
        b.close()
    return {"sid": sid}


def build(shots: list[dict], stills: Path, out: Path, key: str) -> float:
    """Concat the stills with ffmpeg. key = 'secs' (full cut) or 'clip' (30 s cut)."""
    rows = [(s, s["secs"] if key == "secs" else s["clip"]) for s in shots
            if (stills / f"{s['id']}.png").exists() and (key == "secs" or s.get("clip"))]
    total = float(sum(d for _, d in rows))
    lst = out.with_suffix(".txt")
    lines = ["ffconcat version 1.0"]
    for s, d in rows:
        lines += [f"file '{(stills / (s['id'] + '.png')).as_posix()}'", f"duration {d}"]
    lines.append(f"file '{(stills / (rows[-1][0]['id'] + '.png')).as_posix()}'")
    lst.write_text("\n".join(lines), encoding="utf-8")
    vf = f"fps=30,scale={W}:{H},format=yuv420p,fade=t=in:st=0:d=0.6,fade=t=out:st={total - 0.8:.2f}:d=0.8"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-vf", vf, "-t", f"{total:.2f}",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-c:a", "aac", "-b:a", "96k",
                    "-movflags", "+faststart", str(out)], check=True)
    return total


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/video")
    ap.add_argument("--port", type=int, default=8851)
    ap.add_argument("--sam-overlay", default="", help="a picture with SAM's boxes drawn on a real laptop photo (not in the repo)")
    ap.add_argument("--sam-credit", default="")
    args = ap.parse_args()
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH")
    out = (ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    stills = out / "stills"
    stills.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{args.port}"
    env = {k: v for k, v in os.environ.items() if k not in ("MODEL_API_KEY", "META_API_KEY")}
    env.update(CAIRN_PERCEPTION="none", CAIRN_API_TOKEN="", CAIRN_DATA_DIR=tempfile.mkdtemp(prefix="cairn-video-"), PYTHONPATH=str(ROOT))
    srv = subprocess.Popen([sys.executable, "-m", "cairn.cli", "serve", "--host", "127.0.0.1", "--port", str(args.port)],
                           cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait_health(base)
        info = capture(args, base, stills)
    finally:
        srv.terminate()
    full = build(SHOTS, stills, out / "cairn-demo.mp4", "secs")
    clip = build(SHOTS, stills, out / "cairn-30s.mp4", "clip")
    (out / "captions.json").write_text(json.dumps([{k: v for k, v in s.items() if k in ("id", "caption", "secs")} for s in SHOTS],
                                                  indent=2), encoding="utf-8")
    print(json.dumps({"session": info["sid"], "full_seconds": full, "clip_seconds": clip, "out": str(out)}))


if __name__ == "__main__":
    main()
