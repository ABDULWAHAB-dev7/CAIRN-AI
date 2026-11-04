"""Capture clean screenshots of the real app for the explainer, plus the boxes of the parts a scene may circle.

Starts the app with perception off (no Meta call), replays the simulated demo, reviews a few events, closes the job, and
saves PNGs and `meta.json` (name -> {size, boxes: {selector: [x, y, w, h]}}) into the assets folder.

    python explainer/capture_assets.py --out out/explainer/assets
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
W, H = 1920, 1080
SELECTORS = ["#top", "#st-miss", "#st-removed", "#st-acc", "#left", "#parts-out", "#feedwrap", "#step", "#tl", "#wells", ".ev.sel", "#wells > :nth-child(16)"]
BENCH_EVENTS = {"bench_start": 2, "bench_identity": 24, "bench_danger": 55, "bench_drop": 69, "bench_lunch": 76,
                "bench_wrong": 100, "bench_reassembly": 156}


def wait_health(base: str) -> None:
    end = time.time() + 40
    while time.time() < end:
        try:
            urllib.request.urlopen(base + "/health", timeout=2)
            return
        except Exception:
            time.sleep(0.5)
    raise SystemExit("server did not start")


def boxes(page) -> dict:
    return page.evaluate("""(sels) => { const out = {}; for (const s of sels) { const e = document.querySelector(s);
        if (e) { const r = (s === '#st-miss' ? e.parentElement : e).getBoundingClientRect(); out[s] = [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; } } return out; }""",
                         SELECTORS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/explainer/assets")
    ap.add_argument("--port", type=int, default=8852)
    args = ap.parse_args()
    out = (ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    base = f"http://127.0.0.1:{args.port}"
    env = {k: v for k, v in os.environ.items() if k not in ("MODEL_API_KEY", "META_API_KEY")}
    env.update(CAIRN_PERCEPTION="none", CAIRN_API_TOKEN="", CAIRN_DATA_DIR=tempfile.mkdtemp(prefix="cairn-explainer-"), PYTHONPATH=str(ROOT))
    srv = subprocess.Popen([sys.executable, "-m", "cairn.cli", "serve", "--host", "127.0.0.1", "--port", str(args.port)],
                           cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    meta: dict = {}
    try:
        wait_health(base)
        with sync_playwright() as p:
            b = p.chromium.launch()
            ctx = b.new_context(viewport={"width": W, "height": H}, device_scale_factor=2)  # 2x so zoomed shots stay sharp
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
            for name, seq in BENCH_EVENTS.items():
                pg.evaluate("s => openReview(s)", seq)
                pg.wait_for_function("(() => { const f = document.getElementById('feed'); return f && f.complete && f.naturalWidth > 0; })()", timeout=20000)
                pg.wait_for_timeout(900)
                pg.evaluate("() => { const e = document.querySelector('.ev.sel'); if (e) e.scrollIntoView({block: 'center'}); }")
                pg.wait_for_timeout(250)
                pg.screenshot(path=str(out / f"{name}.png"))
                meta[name] = {"size": [W, H], "boxes": boxes(pg), "event": seq}
            pg.evaluate("() => { const b = [...document.querySelectorAll('button')].find(x => /Back to live/.test(x.textContent)); if (b) b.click(); }")
            pg.wait_for_timeout(1200)
            pg.click("#btn-close")
            pg.wait_for_selector("text=JOB CLOSED", timeout=30000)
            pg.wait_for_timeout(700)
            pg.screenshot(path=str(out / "bench_closed.png"))
            meta["bench_closed"] = {"size": [W, H], "boxes": {}}
            pg.evaluate("hide()")
            page2 = ctx.new_page()
            for name, path, zoom in [("passport", f"/sessions/{sid}/passport.html", 1.0), ("verify", f"/v/{sid}", 2.2)]:
                page2.goto(base + path, wait_until="networkidle")
                if zoom != 1.0:
                    page2.evaluate("z => { document.body.style.zoom = z; }", zoom)
                page2.wait_for_timeout(800)
                page2.screenshot(path=str(out / f"{name}.png"))
                meta[name] = {"size": [W, H], "boxes": {}}
            b.close()
    finally:
        srv.terminate()
    (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({"assets": sorted(meta), "out": str(out)}))


if __name__ == "__main__":
    main()
