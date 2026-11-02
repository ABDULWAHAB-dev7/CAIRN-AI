"""HTTP backend: sessions, perception ingest, the agent, the live event stream and the passport.

Run: `cairn serve`   (needs `pip install -e ".[server]"`)

Config (environment):
  CAIRN_DATA_DIR      where sessions, keys and passports live            (default ./data)
  CAIRN_API_TOKEN     if set, every route except /health needs `Authorization: Bearer <token>`
  CAIRN_AGENT         deterministic | wonder | glimmer                  (default deterministic)
  CAIRN_PERCEPTION    none | sam                                        (default none)
  CAIRN_ZONES         JSON file: {"trays": {"tray_1": [x0,y0,x1,y1]}, "device": [..], "prompts": {"hinge screw": "hinge_screw"}}
  CAIRN_PRIVACY       local => customer images never leave the bench: sam perception and the cloud agent are refused
"""
from __future__ import annotations

import asyncio
import base64
import dataclasses
import hmac
import html
import json
import os
import re
import threading
import time
import uuid
from collections import deque
from pathlib import Path

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, passport, safety
from .agent import Agent, DeterministicAgent, SafeAgent, WonderAgent
from .device import DEVICES, get_device
from .events import Event, EventLog
from .frames import FrameStore, render_png
from .timeline import build_timeline
from .perception import Sam31Perception, ZoneMap
from .scenarios import hero_demo
from .session import Detection, Frame, Session

ID_RE = re.compile(r"^[0-9a-f]{12}$")
ZONE_RE = r"^(device|hand|bench|tray_\d+)$"


# ---- request models ------------------------------------------------------------------------------
class NewSession(BaseModel):
    technician: str = Field(min_length=1, max_length=80)
    bench: str = Field(default="bench_01", min_length=1, max_length=80)
    device: str = "demo_laptop"
    job_number: str | None = Field(default=None, max_length=40)


class DetectionIn(BaseModel):
    track_id: str
    cls: str
    zone: str = Field(pattern=ZONE_RE)
    confidence: float = Field(default=1.0, ge=0, le=1)
    hole: str | None = None
    xy: tuple[float, float] | None = None


class FrameIn(BaseModel):
    frame_id: str
    ts: float | None = None
    detections: list[DetectionIn]


class TapIn(BaseModel):
    part_id: str
    zone: str = Field(pattern=ZONE_RE)
    hole: str | None = None
    well: int | None = Field(default=None, ge=1, le=24)
    ts: float | None = None


class StepIn(BaseModel):
    step_id: str
    ts: float | None = None


class HazardIn(BaseModel):
    kind: str = Field(pattern="^(smoke|heat|swelling)$")
    ts: float | None = None


class NoteIn(BaseModel):
    note: str = Field(min_length=1, max_length=500)
    ts: float | None = None


class RetireIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)
    ts: float | None = None


class BootIn(BaseModel):
    passed: bool
    ts: float | None = None


class AskIn(BaseModel):
    utterance: str = Field(min_length=1, max_length=1000)


class GuardIn(BaseModel):
    kind: str = Field(pattern="^(remove|pry)$")
    part_id: str | None = None
    near: str | None = None


class PassportIn(BaseModel):
    technician: str | None = None
    ts: float | None = None
    accept_exceptions: bool = False
    note: str | None = Field(default=None, max_length=1000)


# ---- runtime -------------------------------------------------------------------------------------
class Runtime:
    def __init__(self, sid: str, session: Session, frames: FrameStore):
        self.id, self.session, self.frames, self.lock = sid, session, frames, threading.Lock()
        self.alerts: deque = deque(maxlen=60)
        session.frame_sink = frames.append

    def meta(self) -> dict:
        g = self.session.graph
        return {"id": self.id, "device": g.device.id, "technician": g.registration.get("technician"),
                "bench": g.registration.get("bench"), "job_number": g.registration.get("job_number"),
                "phase": g.phase().value, "events": g.seq, "verified": g.verified,
                "closed": "verified" if g.verified else "with_exceptions"
                if g.closed_with_exceptions is not None else None}

    def push(self, alerts) -> None:
        for a in alerts:
            if a.kind not in ("step_done", "step_verified"):
                self.alerts.append(dataclasses.asdict(a))


class Hub:
    def __init__(self, data_dir: Path):
        self.dir = data_dir
        for sub in ("sessions", "passports", "keys", "frames"):
            (self.dir / sub).mkdir(parents=True, exist_ok=True)
        self.items: dict[str, Runtime] = {}
        self._lock = threading.Lock()
        for f in sorted((self.dir / "sessions").glob("*.db")):
            if ID_RE.match(f.stem):
                self._load(f)

    def _load(self, f: Path) -> None:
        log = EventLog(str(f))
        first = next(iter(log.events()), None)
        if first is None or first.type != "device_registered":
            return
        self.items[f.stem] = Runtime(f.stem, Session(get_device(first.payload["device_id"]), log),
                                     FrameStore(self.dir / "frames", f.stem))

    def create(self, technician: str, bench: str, device: str, log_id: str | None = None) -> Runtime:
        sid = log_id or uuid.uuid4().hex[:12]
        rt = Runtime(sid, Session(get_device(device), EventLog(str(self.dir / "sessions" / f"{sid}.db"))),
                     FrameStore(self.dir / "frames", sid))
        with self._lock:
            self.items[sid] = rt
        return rt

    def get(self, sid: str) -> Runtime:
        rt = self.items.get(sid) if ID_RE.match(sid) else None
        if rt is None:
            raise HTTPException(404, "no such session")
        return rt

    def signer(self, bench: str) -> passport.Signer:
        safe = re.sub(r"[^A-Za-z0-9_-]", "_", bench)[:60] or "bench"
        return passport.Signer.load_or_create(self.dir / "keys" / f"{safe}.pem")

    def passport_path(self, sid: str) -> Path:
        return self.dir / "passports" / f"{sid}.json"


def _now(rt: Runtime, ts: float | None) -> float:
    """Server clock unless the caller supplies one; never earlier than the last event."""
    return max(ts if ts is not None else time.time(), rt.session.graph.last_ts)


def _alerts(alerts) -> list[dict]:
    return [dataclasses.asdict(a) for a in alerts]


def _out(rt: Runtime, alerts) -> dict:
    rt.push(alerts)
    return {"alerts": _alerts(alerts), "recap": rt.session.recap(), "top": rt.session.top_strip()}


def make_agent(kind: str, privacy_local: bool) -> Agent:
    if kind == "wonder":
        if privacy_local:
            raise RuntimeError("CAIRN_PRIVACY=local forbids the cloud Wonder agent; use glimmer")
        from .meta_api import MetaClient, WonderClient
        return SafeAgent(WonderAgent(WonderClient(MetaClient())))
    if kind == "glimmer":
        from .local_llm import GlimmerClient
        return SafeAgent(WonderAgent(GlimmerClient()))
    if kind != "deterministic":
        raise RuntimeError(f"unknown CAIRN_AGENT {kind!r}")
    return DeterministicAgent()


def make_perception(kind: str, privacy_local: bool, zones_file: str | None):
    if kind == "none":
        return None
    if kind != "sam":
        raise RuntimeError(f"unknown CAIRN_PERCEPTION {kind!r}")
    if privacy_local:
        raise RuntimeError("CAIRN_PRIVACY=local forbids sending bench images to the cloud SAM API")
    from .meta_api import MetaClient, Sam31Backend
    if zones_file:
        cfg = json.loads(Path(zones_file).read_text(encoding="utf-8"))
        zones = ZoneMap({k: tuple(v) for k, v in cfg["trays"].items()}, tuple(cfg["device"]))
        prompts = cfg["prompts"]
    else:  # the demo bench geometry (cairn.geometry) and one prompt per part class
        dev = get_device("demo_laptop")
        zones = ZoneMap.default(dev)
        prompts = {c.replace("_", " "): c for c in dev.classes()}
    return Sam31Perception(Sam31Backend(MetaClient()), zones, prompts)


def create_app(data_dir: str | Path | None = None, agent: Agent | None = None, perception=None,
               api_token: str | None = None) -> FastAPI:
    env = os.environ.get
    privacy_local = env("CAIRN_PRIVACY", "") == "local"
    hub = Hub(Path(data_dir or env("CAIRN_DATA_DIR", "data")))
    if agent is None:
        agent = make_agent(env("CAIRN_AGENT", "deterministic"), privacy_local)
    if perception is None:
        perception = make_perception(env("CAIRN_PERCEPTION", "none"), privacy_local, env("CAIRN_ZONES"))
    token = api_token if api_token is not None else env("CAIRN_API_TOKEN")

    def auth(request: Request):
        if token and not hmac.compare_digest(request.headers.get("authorization", ""), f"Bearer {token}"):
            raise HTTPException(401, "missing or invalid bearer token")

    app = FastAPI(title="Cairn", version=__version__)
    secured = [Depends(auth)]

    @app.get("/health")
    def health():
        return {"ok": True, "version": __version__, "agent": type(agent).__name__,
                "perception": type(perception).__name__ if perception else None,
                "privacy": "local" if privacy_local else "cloud-allowed", "auth": bool(token),
                "sessions": len(hub.items)}

    @app.get("/devices", dependencies=secured)
    def devices():
        return {"devices": sorted(DEVICES)}

    # ---- sessions -----------------------------------------------------------------------------
    @app.post("/sessions", status_code=201, dependencies=secured)
    def create_session(body: NewSession):
        try:
            rt = hub.create(body.technician, body.bench, body.device)
        except KeyError as e:
            raise HTTPException(422, str(e).strip("'\""))
        extra = {"job_number": body.job_number} if body.job_number else {}
        rt.session.register(time.time(), body.technician, body.bench, **extra)
        return {**rt.meta(), "snapshot": rt.session.snapshot()}

    @app.post("/demo", status_code=201, dependencies=secured)
    def run_demo():
        """Create a session and drive the scripted hero demo into it (dev, demos, UI testing)."""
        sid = uuid.uuid4().hex[:12]
        log = EventLog(str(hub.dir / "sessions" / f"{sid}.db"))
        store = FrameStore(hub.dir / "frames", sid)
        bench = None
        for _, bench in hero_demo(log, sink=store.append, job="J-1042"):
            pass
        rt = Runtime(sid, bench.session, store)
        hub.items[sid] = rt
        return {**rt.meta(), "snapshot": rt.session.snapshot()}

    @app.get("/sessions", dependencies=secured)
    def list_sessions():
        return {"sessions": [rt.meta() for rt in hub.items.values()]}

    @app.get("/sessions/{sid}", dependencies=secured)
    def get_session(sid: str):
        rt = hub.get(sid)
        with rt.lock:
            return {**rt.meta(), "snapshot": rt.session.snapshot(), "recent_alerts": list(rt.alerts)}

    @app.get("/sessions/{sid}/events", dependencies=secured)
    def get_events(sid: str, after: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=5000)):
        rt = hub.get(sid)
        with rt.lock:
            evs = [e for e in rt.session.log.events() if e.seq > after][:limit]
            ok, bad = rt.session.log.verify()
        return {"chain_ok": ok, "bad_seq": bad, "head": rt.session.log.head(),
                "events": [dataclasses.asdict(e) for e in evs]}

    @app.get("/sessions/{sid}/stream", dependencies=secured)
    async def stream(sid: str, request: Request, after: int = Query(0, ge=0), follow: bool = True):
        rt = hub.get(sid)

        async def gen():
            seq = after
            while True:
                with rt.lock:
                    new = [e for e in rt.session.log.events() if e.seq > seq]
                for e in new:
                    seq = e.seq
                    yield f"id: {e.seq}\nevent: {e.type}\ndata: {json.dumps(dataclasses.asdict(e))}\n\n"
                if not follow or await request.is_disconnected():
                    return
                await asyncio.sleep(0.4)

        return StreamingResponse(gen(), media_type="text/event-stream")

    # ---- observations in ----------------------------------------------------------------------
    def _check_parts(rt: Runtime, *ids):
        for i in ids:
            if i is not None and i not in rt.session.graph.parts:
                raise HTTPException(404, f"unknown part {i!r}")

    @app.post("/sessions/{sid}/frames", dependencies=secured)
    def post_frame(sid: str, body: FrameIn):
        rt = hub.get(sid)
        with rt.lock:
            ts = _now(rt, body.ts)
            f = Frame(body.frame_id, ts, tuple(Detection(d.track_id, d.cls, d.zone, d.confidence, d.hole, d.xy)
                                               for d in body.detections))
            alerts = rt.session.observe(f)
            return _out(rt, alerts)

    @app.post("/sessions/{sid}/image", dependencies=secured)
    async def post_image(sid: str, request: Request, frame_id: str | None = None, ts: float | None = None):
        if perception is None:
            raise HTTPException(503, "no perception backend configured (CAIRN_PERCEPTION)")
        rt = hub.get(sid)
        image = await request.body()
        if not image:
            raise HTTPException(422, "empty image body")
        when = _now(rt, ts)
        fid = frame_id or f"img_{int(when * 1000)}"
        try:
            frame = await asyncio.to_thread(perception.frame, fid, when, image)
        except Exception as e:
            raise HTTPException(502, f"perception failed: {type(e).__name__}: {e}")
        with rt.lock:
            rt.frames.save_image(frame.frame_id, image)
            alerts = rt.session.observe(frame)
            return {**_out(rt, alerts), "detections": len(frame.detections), "frame_id": frame.frame_id}

    @app.post("/sessions/{sid}/taps", dependencies=secured)
    def post_tap(sid: str, body: TapIn):
        rt = hub.get(sid)
        _check_parts(rt, body.part_id)
        with rt.lock:
            alerts = rt.session.observe_manual(body.part_id, body.zone, _now(rt, body.ts), body.hole, body.well)
            return _out(rt, alerts)

    @app.post("/sessions/{sid}/steps", dependencies=secured)
    def post_step(sid: str, body: StepIn):
        rt = hub.get(sid)
        base = body.step_id[2:] if body.step_id.startswith("r_") else body.step_id
        try:
            spec = rt.session.device.step(base)
        except KeyError:
            raise HTTPException(404, f"unknown step {body.step_id!r}")
        if spec.removes or (body.step_id.startswith("r_") and not spec.reverse_action):
            raise HTTPException(422, "only action steps (ESD, battery) are logged by voice or tap")
        with rt.lock:
            alerts = rt.session.complete_step(body.step_id, _now(rt, body.ts), "api")
            return _out(rt, alerts)

    @app.post("/sessions/{sid}/hazard", dependencies=secured)
    def post_hazard(sid: str, body: HazardIn):
        rt = hub.get(sid)
        with rt.lock:
            alerts = rt.session.report_hazard(body.kind, _now(rt, body.ts))
            return _out(rt, alerts)

    @app.delete("/sessions/{sid}/hazard", dependencies=secured)
    def clear_hazard(sid: str, body: NoteIn):
        rt = hub.get(sid)
        with rt.lock:
            if not rt.session.graph.hazard:
                raise HTTPException(409, "no active hazard")
            rt.session.clear_hazard(_now(rt, body.ts), body.note)
            return {"recap": rt.session.recap()}

    @app.post("/sessions/{sid}/exceptions/{xid}/resolve", dependencies=secured)
    def resolve(sid: str, xid: str, body: NoteIn):
        rt = hub.get(sid)
        with rt.lock:
            x = rt.session.graph.exceptions.get(xid)
            if x is None:
                raise HTTPException(404, "no such exception")
            if x.resolved:
                raise HTTPException(409, "already resolved")
            rt.session.resolve_exception(xid, _now(rt, body.ts), body.note)
            return {"recap": rt.session.recap()}

    @app.post("/sessions/{sid}/parts/{pid}/retire", dependencies=secured)
    def retire(sid: str, pid: str, body: RetireIn):
        rt = hub.get(sid)
        _check_parts(rt, pid)
        with rt.lock:
            rt.session.retire_part(pid, _now(rt, body.ts), body.reason)
            return {"recap": rt.session.recap()}

    @app.post("/sessions/{sid}/boot-test", dependencies=secured)
    def boot(sid: str, body: BootIn):
        rt = hub.get(sid)
        with rt.lock:
            rt.session.record_boot_test(body.passed, _now(rt, body.ts))
            return {"can_close": rt.session.can_close()[0], "recap": rt.session.recap()}

    # ---- reasoning ----------------------------------------------------------------------------
    @app.post("/sessions/{sid}/ask", dependencies=secured)
    def ask(sid: str, body: AskIn):
        rt = hub.get(sid)
        with rt.lock:
            r = agent.respond(rt.session, body.utterance)
        return {"text": r.text, "source": r.source}

    @app.get("/sessions/{sid}/queries/{name}", dependencies=secured)
    def queries(sid: str, name: str):
        rt = hub.get(sid)
        with rt.lock:
            g = rt.session.graph
            if name == "missing_parts":
                return {"missing_parts": g.missing_parts()}
            if name == "next_step":
                return {"next_step": g.next_step(), "valid": g.valid_next_steps()}
            if name == "can_close":
                ok, reasons = rt.session.can_close()
                return {"can_close": ok, "reasons": reasons}
        raise HTTPException(404, "queries: missing_parts | next_step | can_close")

    @app.post("/sessions/{sid}/guard", dependencies=secured)
    def guard(sid: str, body: GuardIn):
        rt = hub.get(sid)
        _check_parts(rt, body.part_id)
        with rt.lock:
            v = rt.session.guard(safety.Action(body.kind, body.part_id, body.near))
        return dataclasses.asdict(v)

    # ---- passport -----------------------------------------------------------------------------
    def _frame_png(rt: Runtime, fid: str) -> bytes | None:
        row, img = rt.frames.row(fid), rt.frames.image(fid)
        if row is None and img is None:
            return None
        return render_png(row, rt.session, background=img)

    def _close(rt: Runtime, request: Request, body: PassportIn) -> dict:
        path = hub.passport_path(rt.id)
        with rt.lock:
            if path.exists():  # idempotent: a signed passport is never re-signed
                return json.loads(path.read_text(encoding="utf-8"))
            g = rt.session.graph
            tech = body.technician or g.registration.get("technician") or "unknown"
            base = (os.environ.get("CAIRN_PUBLIC_URL") or str(request.base_url)).rstrip("/")
            try:
                p = passport.issue(rt.session, tech, hub.signer(g.registration.get("bench", "bench")),
                                   _now(rt, body.ts), accept_exceptions=body.accept_exceptions, note=body.note,
                                   frame_png=lambda fid: _frame_png(rt, fid), verify_url=f"{base}/v/{rt.id}")
            except passport.PassportRefused as e:
                raise HTTPException(409, {"error": "close blocked: invariants not satisfied", "reasons": e.reasons})
            path.write_text(passport.dumps(p), encoding="utf-8")
            return p

    @app.post("/sessions/{sid}/passport", dependencies=secured)
    def issue_passport(sid: str, request: Request, body: PassportIn = Body(default_factory=PassportIn)):
        return _close(hub.get(sid), request, body)

    @app.post("/sessions/{sid}/close", dependencies=secured)
    def close_job(sid: str, request: Request, body: PassportIn = Body(default_factory=PassportIn)):
        """Close the job: VERIFIED, blocked (409 with reasons), or CLOSED WITH EXCEPTIONS if accepted."""
        return _close(hub.get(sid), request, body)

    def _stored(sid: str) -> dict:
        hub.get(sid)
        path = hub.passport_path(sid)
        if not path.exists():
            raise HTTPException(404, "no passport issued for this session")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/sessions/{sid}/passport", dependencies=secured)
    def get_passport(sid: str):
        return _stored(sid)

    @app.get("/sessions/{sid}/passport.html", dependencies=secured, response_class=HTMLResponse)
    def passport_html(sid: str):
        return passport.to_html(_stored(sid))

    @app.get("/sessions/{sid}/passport.pdf", dependencies=secured)
    def passport_pdf(sid: str):
        p = _stored(sid)
        out = hub.dir / "passports" / f"{sid}.pdf"
        try:
            passport.to_pdf(p, out)
        except ImportError:
            raise HTTPException(501, "PDF export needs Pillow: pip install cairn[pdf]")
        return Response(out.read_bytes(), media_type="application/pdf")

    @app.post("/verify", dependencies=secured)
    def verify(body: dict = Body(...)):
        """Stateless: check a passport's signature and, if events are supplied, the hash chain."""
        if "body" not in body or "signature" not in body:
            raise HTTPException(422, "expected {body, signature}")
        from .events import Event
        try:
            events = [Event(**e) for e in body["events"]] if body.get("events") is not None else None
            ok, problems = passport.verify({"body": body["body"], "signature": body["signature"],
                                       "attachments": body.get("attachments") or {}}, events)
        except (KeyError, TypeError, ValueError, IndexError) as e:
            raise HTTPException(422, f"malformed passport or events: {type(e).__name__}")
        return {"valid": ok, "problems": problems}

    # ---- the single-view bench screen ---------------------------------------------------------
    @app.post("/sessions/{sid}/baseline", dependencies=secured)
    async def post_baseline(sid: str, request: Request):
        """Attach a camera frame of the sealed device as the job's baseline."""
        rt = hub.get(sid)
        image = await request.body()
        if not image:
            raise HTTPException(422, "empty image body")
        with rt.lock:
            rt.frames.save_image("baseline", image)
            rt.session.baseline(_now(rt, None), "baseline")
        return {"frame_id": "baseline"}

    @app.get("/sessions/{sid}/timeline", dependencies=secured)
    def timeline(sid: str):
        rt = hub.get(sid)
        with rt.lock:
            return {"entries": build_timeline(rt.session.device, rt.session.log.events())}

    @app.get("/sessions/{sid}/at/{seq}", dependencies=secured)
    def state_at(sid: str, seq: int):
        """Everything the screen shows, as it was right after event `seq` (click a timeline entry)."""
        rt = hub.get(sid)
        with rt.lock:
            events = rt.session.log.events()
            if not 0 <= seq <= len(events):
                raise HTTPException(404, "no such event")
            part = events[:seq]
            snap = Session.replica(rt.session.device, part).snapshot()
            ts = part[-1].ts if part else 0.0
            row = rt.frames.at_or_before(ts)
            ev = events[seq - 1] if seq else None
            fid = (ev.payload.get("frame") if ev else None) or (row["frame_id"] if row else None)
            return {"seq": seq, "ts": ts, "snapshot": snap, "frame_id": fid}

    @app.get("/sessions/{sid}/frames/{name}", dependencies=secured)
    def frame_image(sid: str, name: str, well: int | None = Query(None, ge=1, le=24), raw: bool = False):
        """`latest.png` or `<frame_id>.png`: the camera image with quiet outlines, or the drawn bench."""
        rt = hub.get(sid)
        fid = name[:-4] if name.endswith(".png") else name
        with rt.lock:
            row = rt.frames.latest() if fid == "latest" else rt.frames.row(fid)
            img = rt.frames.image(row["frame_id"] if row else fid)
            if row is None and img is None and fid != "latest":
                raise HTTPException(404, "no such frame")
            if raw and img:
                return Response(img, media_type="image/jpeg")
            png = render_png(row, rt.session, highlight_well=well, background=img)
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})

    @app.get("/v/{sid}", response_class=HTMLResponse)
    def public_verify(sid: str):
        """Target of the passport QR code. Public by design: shows only the verdict and summary."""
        rt = hub.get(sid)
        path = hub.passport_path(sid)
        if not path.exists():
            raise HTTPException(404, "this job has no passport yet")
        p = json.loads(path.read_text(encoding="utf-8"))
        ok, problems = passport.verify(p, rt.session.log.events())
        b, esc = p["body"], html.escape
        verdict = "RECORD INTACT" if ok else "RECORD DOES NOT VERIFY"
        color = "#0f766e" if ok else "#b91c1c"
        note = esc("; ".join(problems)) if problems else "Signature and hash chain checked against the event log."
        return (
            "<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Cairn passport check</title>"
            "<body style='font:16px system-ui;max-width:560px;margin:2rem auto;padding:0 1rem'>"
            f"<h1 style='color:{color}'>{verdict}</h1>"
            f"<p><b>{esc(b['status'])}</b> &middot; job {esc(str(b.get('job_number') or '-'))}"
            f" &middot; {esc(b['device']['label'])}</p>"
            f"<p>{b['counts']['fasteners_accounted']}/{b['counts']['fasteners_total']} fasteners, "
            f"{b['counts']['extra_parts']} extra parts, {len(b['exceptions'])} exceptions recorded.</p>"
            f"<p style='color:#64748b;font-size:13px'>{note}<br>"
            f"Chain head {esc(b['event_chain']['head'][:24])}&hellip;</p>")

    ui_dir = Path(__file__).parent / "ui"

    @app.get("/", include_in_schema=False)
    def landing():
        return FileResponse(ui_dir / "index.html")

    @app.get("/bench", include_in_schema=False)
    def bench_ui():
        return FileResponse(ui_dir / "bench.html")

    app.mount("/ui", StaticFiles(directory=ui_dir), name="ui")  # tokens.css and the self-hosted font

    return app
