"""Build the Cairn explainer: scene code -> frames (headless Chromium) -> video (ffmpeg) with a voiceover.

    python explainer/capture_assets.py --out out/explainer/assets        # once: clean screenshots of the real app
    python explainer/build.py --out out/explainer                        # voiceover + render + encode
    python explainer/build.py --out out/explainer --stills 14            # quick look: 14 stills, no video
    python explainer/build.py --out out/explainer --voice Mark           # another Windows voice (--list-voices)
    python explainer/build.py --out out/explainer --audio-dir my_audio   # your own clips: my_audio/<scene>_<n>.mp3|wav

Voiceover: one clip per narrated sentence, made with the voices built into Windows (explainer/tts.ps1), so cues in the
animation land on the exact start of each sentence. To use ElevenLabs or your own voice, export one file per sentence into
a folder and pass --audio-dir; nothing else changes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import threading
import wave
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
FPS, W, H = 30, 1920, 1080
LEAD, GAP, TAIL = 0.7, 0.35, 1.1  # seconds: before the first line, between lines, after the last line
SR = 48000


# --------------------------------------------------------------------------------------------------- voiceover
def plain(s: str) -> str:
    return s.replace("**", "")


def list_voices() -> None:
    subprocess.run(["powershell.exe", "-NoProfile", "-File", str(HERE / "tts.ps1"), "-List"], check=True)


def make_audio(script: dict, work: Path, voice: str, rate: float, audio_dir: Path | None) -> dict[tuple[str, int], Path]:
    """One 48 kHz mono wav per narrated line. Returns {(scene, line): path}."""
    work.mkdir(parents=True, exist_ok=True)
    out: dict[tuple[str, int], Path] = {}
    jobs = []
    for sc in script["scenes"]:
        for i, line in enumerate(sc["lines"]):
            if audio_dir:
                src = next((p for ext in ("wav", "mp3", "m4a") if (p := audio_dir / f"{sc['id']}_{i}.{ext}").exists()), None)
                if src is None:
                    raise SystemExit(f"--audio-dir is missing {sc['id']}_{i}.(wav|mp3|m4a)")
                wav = work / f"{sc['id']}_{i}.custom.wav"
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ar", str(SR), "-ac", "1", str(wav)], check=True)
                out[(sc["id"], i)] = wav
                continue
            key = hashlib.sha1(f"{voice}|{rate}|{plain(line)}".encode()).hexdigest()[:12]
            raw = work / f"{key}.raw.wav"
            wav = work / f"{key}.wav"
            out[(sc["id"], i)] = wav
            if not wav.exists():
                jobs.append({"text": plain(line), "out": str(raw), "wav": str(wav)})
    if jobs:
        jf = work / "tts_jobs.json"
        jf.write_text(json.dumps([{"text": j["text"], "out": j["out"]} for j in jobs]), encoding="utf-8")
        r = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(HERE / "tts.ps1"), "-Jobs", str(jf), "-Voice", voice, "-Rate", str(rate)],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(f"text to speech failed: {r.stderr.strip()[:400]}")
        for j in jobs:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", j["out"], "-ar", str(SR), "-ac", "1", j["wav"]], check=True)
    return out


def duration(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def make_timeline(script: dict, audio: dict) -> dict:
    t, scenes = 0.0, []
    for sc in script["scenes"]:
        L, D, at = [], [], LEAD
        for i, _ in enumerate(sc["lines"]):
            d = duration(audio[(sc["id"], i)])
            L.append(round(at, 3)); D.append(round(d, 3)); at += d + GAP
        dur = at - GAP + TAIL + sc.get("tail", 0)
        scenes.append({"id": sc["id"], "chapter": sc["chapter"], "lines": sc["lines"], "start": round(t, 3), "dur": round(dur, 3), "L": L, "D": D})
        t += dur
    return {"total": round(t, 3), "fps": FPS, "scenes": scenes}


def mix_narration(timeline: dict, audio: dict, out: Path) -> None:
    buf = np.zeros(int((timeline["total"] + 1) * SR), dtype=np.float32)
    for sc in timeline["scenes"]:
        for i, L in enumerate(sc["L"]):
            with wave.open(str(audio[(sc["id"], i)])) as w:
                x = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
            a = int((sc["start"] + L) * SR)
            buf[a:a + len(x)] += x
    pcm = (np.clip(buf, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(pcm.tobytes())


# --------------------------------------------------------------------------------------------------- data for the scenes
def chain_data() -> dict:
    """A real six-event SHA-256 chain, shortened, for the 'hash-chained log' illustration."""
    events = ["device registered", "baseline photo, 29 parts", "ESD strap logged", "p_07 removed", "p_17 lost", "p_17 found"]
    fulls, prev = [], "genesis"
    for e in events:
        prev = hashlib.sha256(f"{prev}|{e}".encode()).hexdigest()
        fulls.append(prev)
    tampered_text = "p_07 untouched"  # event #4 rewritten: its hash changes, so #5's stored "prev" no longer matches
    tampered = hashlib.sha256(f"{fulls[2]}|{tampered_text}".encode()).hexdigest()[:8]
    return {"events": events, "prev": ["00000000"] + [h[:8] for h in fulls[:-1]], "hash": [h[:8] for h in fulls],
            "tamperedText": tampered_text, "tamperedHash": tampered}


# --------------------------------------------------------------------------------------------------- rendering
class Handler(SimpleHTTPRequestHandler):
    assets: Path = Path(".")

    def translate_path(self, path: str) -> str:
        path = path.split("?", 1)[0]
        if path.startswith("/assets/"):
            return str(self.assets / path[len("/assets/"):])
        return str(HERE / path.lstrip("/"))

    def log_message(self, *a):  # quiet
        pass


def serve(assets: Path) -> tuple[ThreadingHTTPServer, int]:
    Handler.assets = assets
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def render_chunk(port: int, timeline: dict, data: dict, frames: list[int], outdir: str, fmt: str) -> int:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_context(viewport={"width": W, "height": H}, device_scale_factor=1).new_page()
        for attempt in range(4):  # under load the page script can be slow to arrive: wait for it, reload if it never does
            pg.goto(f"http://127.0.0.1:{port}/stage.html", wait_until="load")
            try:
                pg.wait_for_function("typeof CAIRN !== 'undefined' && !!window.SCENES && !!SCENES.close", timeout=15000)
                break
            except Exception:
                if attempt == 3:
                    raise
        pg.evaluate("([tl, d]) => CAIRN.init(tl, d)", [timeline, data])
        for i in frames:
            pg.evaluate("T => CAIRN.renderAt(T)", i / FPS)
            if fmt == "png":
                pg.screenshot(path=f"{outdir}/f_{i:05d}.png")
            else:
                pg.screenshot(path=f"{outdir}/f_{i:05d}.jpg", type="jpeg", quality=93)
        b.close()
    return len(frames)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/explainer")
    ap.add_argument("--voice", default="Mark")
    ap.add_argument("--list-voices", action="store_true")
    ap.add_argument("--rate", type=float, default=1.25, help="speaking rate of the Windows voice (1.0 = normal)")
    ap.add_argument("--audio-dir", default="")
    ap.add_argument("--stills", type=int, default=0, help="render N evenly spaced stills for a quick look, no video")
    ap.add_argument("--at", default="", help="comma-separated seconds to render as stills")
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--name", default="cairn-explained")
    ap.add_argument("--crf", type=int, default=22, help="H.264 quality: lower is bigger and sharper")
    ap.add_argument("--clean", action="store_true", help="discard frames already rendered and start again")
    args = ap.parse_args()
    if args.list_voices:
        return list_voices()
    out = (ROOT / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    assets = out / "assets"
    if not (assets / "meta.json").exists():
        raise SystemExit(f"run explainer/capture_assets.py --out {args.out}/assets first")
    work = out / "work"
    script = json.loads((HERE / "script.json").read_text(encoding="utf-8"))
    audio = make_audio(script, work / "audio", args.voice, args.rate, Path(args.audio_dir) if args.audio_dir else None)
    timeline = make_timeline(script, audio)
    data = {"meta": json.loads((assets / "meta.json").read_text(encoding="utf-8")), "chain": chain_data()}
    (work / "timeline.json").write_text(json.dumps(timeline, indent=1), encoding="utf-8")
    srv, port = serve(assets)
    total_frames = int(math.ceil(timeline["total"] * FPS))
    print(f"narration lines: {sum(len(s['lines']) for s in script['scenes'])}, length {timeline['total']:.1f}s, {total_frames} frames", flush=True)

    if args.stills or args.at:
        times = [float(x) for x in args.at.split(",") if x] if args.at else [timeline["total"] * (k + 0.5) / args.stills for k in range(args.stills)]
        d = out / "stills"; d.mkdir(parents=True, exist_ok=True)
        frames = [min(total_frames - 1, int(t * FPS)) for t in times]
        render_chunk(port, timeline, data, frames, str(d), "png")
        print(json.dumps({"stills": [f"f_{i:05d}.png" for i in frames], "dir": str(d)}))
        return

    fdir = work / "frames"
    sig = hashlib.sha1(b"".join((HERE / f).read_bytes() for f in ("engine.js", "scenes.js", "stage.css", "stage.html")) +
                       (work / "timeline.json").read_bytes() + (assets / "meta.json").read_bytes()).hexdigest()
    if fdir.exists() and (fdir / ".sig").exists() and (fdir / ".sig").read_text() == sig and not args.clean:
        pass  # same scenes, timing and assets as the frames already on disk: resume
    else:
        if fdir.exists():
            shutil.rmtree(fdir)
        fdir.mkdir(parents=True)
        (fdir / ".sig").write_text(sig)
    n = max(1, args.workers)
    for attempt in range(3):
        missing = [i for i in range(total_frames) if not (fdir / f"f_{i:05d}.jpg").exists()]
        if not missing:
            break
        step = math.ceil(len(missing) / n)
        chunks = [missing[a:a + step] for a in range(0, len(missing), step)]
        print(f"rendering {len(missing)} frames (pass {attempt + 1})", flush=True)
        with ProcessPoolExecutor(max_workers=n) as ex:
            futures = [ex.submit(render_chunk, port, timeline, data, c, str(fdir), "jpg") for c in chunks]
            for f in futures:
                try:
                    f.result()
                except Exception as e:  # a worker died: the next pass renders what is still missing
                    print("worker failed:", str(e).splitlines()[0][:160], flush=True)
    missing = [i for i in range(total_frames) if not (fdir / f"f_{i:05d}.jpg").exists()]
    if missing:
        raise SystemExit(f"{len(missing)} frames could not be rendered (first: {missing[0]})")
    print(f"all {total_frames} frames rendered", flush=True)

    narr = work / "narration.wav"
    mix_narration(timeline, audio, narr)
    mp4 = out / f"{args.name}.mp4"
    af = "highpass=f=80,acompressor=threshold=-20dB:ratio=3:attack=5:release=120,loudnorm=I=-16:TP=-1.5:LRA=9"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(fdir / "f_%05d.jpg"), "-i", str(narr),
                    "-c:v", "libx264", "-preset", "slow", "-crf", str(args.crf), "-tune", "animation", "-pix_fmt", "yuv420p", "-af", af, "-ar", "48000", "-c:a", "aac", "-b:a", "160k",
                    "-shortest", "-movflags", "+faststart", str(mp4)], check=True)
    print(json.dumps({"video": str(mp4), "seconds": timeline["total"], "frames": total_frames}))
    srv.shutdown()


if __name__ == "__main__":
    main()
