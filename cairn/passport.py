"""The repair passport: a signed record anyone can verify without trusting the technician.

Ed25519 over canonical JSON, anchored to the head of the hash-chained event log. The signed body
carries a SHA-256 for each evidence frame, so the images bundled beside it cannot be swapped.
The embedded public key proves integrity, not identity; a shop key registry is the roadmap item
that ties a key to a real shop.
"""
from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import time
from pathlib import Path
from typing import Callable

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import invariants
from .events import GENESIS, Event, canonical, verify_events
from .graph import ObjectGraph, PartState
from .session import Session

SCHEMA = "cairn.passport/2"
VERIFIED = "VERIFIED"
WITH_EXCEPTIONS = "CLOSED WITH EXCEPTIONS"
MAX_EVIDENCE = 6


class PassportRefused(Exception):
    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


class Signer:
    def __init__(self, key: Ed25519PrivateKey):
        self._key = key

    @classmethod
    def generate(cls) -> "Signer":
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def load_or_create(cls, path: str | Path) -> "Signer":
        path = Path(path)
        if path.exists():
            return cls(serialization.load_pem_private_key(path.read_bytes(), password=None))
        s = cls.generate()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(s._key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        return s

    @property
    def public_hex(self) -> str:
        return self._key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()

    def sign(self, data: bytes) -> str:
        return self._key.sign(data).hex()


def fmt_ts(ts: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts)) if ts else "-"


def _exception_rows(g: ObjectGraph) -> list[dict]:
    return [{
        "id": x.id, "type": x.type, "severity": x.severity, "detail": x.detail, "ts": x.ts,
        "part_id": x.part_id, "evidence": x.evidence, "resolved": x.resolved,
        "resolved_by": x.resolved_by, "note": x.note,
    } for x in g.exceptions.values()]


def select_evidence(s: Session) -> list[dict]:
    """Four to six frames of the critical moments: baseline, each exception, the final state."""
    g, picks, seen = s.graph, [], set()

    def add(frame_id, ts, caption):
        if frame_id and frame_id not in seen and len(picks) < MAX_EVIDENCE:
            seen.add(frame_id)
            picks.append({"frame_id": frame_id, "ts": ts, "caption": caption})

    events = s.log.events()
    base = next((e for e in events if e.type == "baseline" and e.payload.get("frame")), None)
    if base:
        add(base.payload["frame"], base.ts, "Baseline: sealed device")
    for x in sorted(g.exceptions.values(), key=lambda x: x.ts):
        if x.evidence and len(picks) < MAX_EVIDENCE - 1:
            add(x.evidence[0], x.ts, f"{x.type.replace('_', ' ')}: {x.detail}")
    zones = [e for e in events if e.type == "part_zone" and e.payload.get("frame")]
    if zones and len(picks) < 4:  # quiet job: add the opening and mid-job frames so the record has context
        for frac, caption in ((0.0, "First part moved"), (0.5, "Mid-job")):
            e = zones[int(frac * (len(zones) - 1))]
            add(e.payload["frame"], e.ts, caption)
    if zones:
        add(zones[-1].payload["frame"], zones[-1].ts, "Final state")
    return sorted(picks, key=lambda p: p["ts"])


def build_body(s: Session, technician: str, issued_ts: float, signer: Signer, status: str,
               evidence: list[dict], verify_url: str | None = None, close_note: str | None = None,
               failing: list[str] | None = None) -> dict:
    g = s.graph
    nodes = g.parts.values()
    removed = sum(1 for n in nodes if n.removed_once)
    reinstalled = sum(1 for n in nodes if n.state == PartState.REINSTALLED)
    retired = sum(1 for n in nodes if n.state == PartState.RETIRED)
    c = g.counts()
    timeline = [{"ts": e.ts, "type": e.type, **{k: v for k, v in e.payload.items()
                 if k in ("step_id", "kind", "passed", "part_id")}}
                for e in s.log.events()
                if e.type in ("step_completed", "hazard", "hazard_cleared", "boot_test", "part_lost",
                              "part_retired")]
    rows = _exception_rows(g)
    return {
        "schema": SCHEMA,
        "status": status,
        "device": {"id": g.device.id, "label": g.device.label},
        "job_number": g.registration.get("job_number"),
        "technician": technician,
        "bench": g.registration.get("bench"),
        "started_ts": g.started_ts,
        "ended_ts": issued_ts,
        "counts": {**c, "extra_parts": sum(1 for x in g.exceptions.values() if x.type == "extra_part"),
                   "parts_removed": removed, "parts_reinstalled": reinstalled, "parts_retired": retired,
                   "parts_outstanding": removed - reinstalled - retired},
        "safety_checks": {
            "esd_strap_logged": "t01" in g.completed_steps,
            "power_disconnected_logged": "t04" in g.completed_steps,
            "safety_violations": sum(1 for x in g.exceptions.values() if x.type == "safety_violation"),
            "swelling_heat_smoke_events": sum(1 for e in s.log.events() if e.type == "hazard"),
        },
        "functional_test": {"passed": g.boot_test},
        "invariants": [vars(i) for i in invariants.evaluate(g)],
        "exceptions": rows,
        "overrides": [x["id"] for x in rows if x["resolved_by"] == "technician"],
        "close": {"note": close_note, "failing": failing or []} if status == WITH_EXCEPTIONS else None,
        "timeline": timeline,
        "evidence": evidence,
        "event_chain": {"genesis": GENESIS, "length": len(s.log), "head": s.log.head()},
        "verify_url": verify_url,
        "signer": {"alg": "ed25519", "public_key": signer.public_hex},
    }


def issue(s: Session, technician: str, signer: Signer, issued_ts: float, *,
          accept_exceptions: bool = False, note: str | None = None,
          frame_png: Callable[[str], bytes | None] | None = None, verify_url: str | None = None) -> dict:
    """Close the job. VERIFIED only if every invariant holds. Otherwise the close is blocked,
    unless the technician accepts the exceptions in writing, which stamps CLOSED WITH EXCEPTIONS.
    """
    ok, reasons = invariants.can_close(s.graph)
    if not ok:
        if not accept_exceptions:
            raise PassportRefused(reasons)
        if not (note and note.strip()):
            raise PassportRefused(["closing with exceptions needs a written note", *reasons])
    status = VERIFIED if ok else WITH_EXCEPTIONS
    picks = select_evidence(s)
    attachments: dict[str, str] = {}
    evidence = []
    for p in picks:
        png = frame_png(p["frame_id"]) if frame_png else None
        if png:
            attachments[p["frame_id"]] = base64.b64encode(png).decode()
            evidence.append({**p, "sha256": hashlib.sha256(png).hexdigest()})
    body = build_body(s, technician, issued_ts, signer, status, evidence, verify_url,
                      note.strip() if note else None, None if ok else reasons)
    passport = {"body": body, "signature": signer.sign(canonical(body).encode()), "attachments": attachments}
    s._emit(issued_ts, "passport_issued", {"signature": passport["signature"], "status": status})
    if ok:
        s._emit(issued_ts, "verified", {})
    else:
        s._emit(issued_ts, "closed_with_exceptions", {"note": note.strip(), "failing": reasons})
    return passport


def verify(passport: dict, events: list[Event] | None = None) -> tuple[bool, list[str]]:
    """Check the signature, the evidence images, and (if supplied) the event hash chain."""
    problems = []
    body = passport["body"]
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(body["signer"]["public_key"]))
        pub.verify(bytes.fromhex(passport["signature"]), canonical(body).encode())
    except Exception:
        problems.append("signature does not match the passport body")
    for e in body.get("evidence", []) if isinstance(body, dict) else []:
        b64 = passport.get("attachments", {}).get(e["frame_id"])
        if b64 is not None and hashlib.sha256(base64.b64decode(b64)).hexdigest() != e["sha256"]:
            problems.append(f"evidence frame {e['frame_id']} was altered")
    if events is not None:
        ok, bad = verify_events(events)
        if not ok:
            problems.append(f"event chain broken at seq {bad}")
        chain = body["event_chain"]
        if len(events) < chain["length"] or events[chain["length"] - 1].hash != chain["head"]:
            problems.append("event log does not reach the head the passport was signed against")
    return (not problems, problems)


def qr_png(text: str) -> bytes | None:
    try:
        import segno
    except ImportError:
        return None
    buf = io.BytesIO()
    segno.make(text, error="m").save(buf, kind="png", scale=5, border=2)
    return buf.getvalue()


def qr_payload(passport: dict) -> str:
    b = passport["body"]
    return b.get("verify_url") or f"cairn:verify:{b['event_chain']['head']}"


def _status_color(status: str) -> str:
    return "#0f766e" if status == VERIFIED else "#b45309"


def to_html(passport: dict) -> str:
    b, esc = passport["body"], html.escape
    c, sc = b["counts"], b["safety_checks"]
    yes = lambda v: "yes" if v else "no"  # noqa: E731
    inv = "".join(
        f"<tr><td>{esc(i['name'])}</td><td class={'ok' if i['ok'] else 'bad'}>{'PASS' if i['ok'] else 'FAIL'}</td>"
        f"<td>{esc(i['detail'])}</td></tr>" for i in b["invariants"])
    exc = "".join(
        f"<tr><td>{esc(x['id'])}</td><td>{esc(x['type'])}</td><td>{esc(x['detail'])}</td>"
        f"<td>{esc(str(x['resolved_by'] or 'OPEN'))}{(': ' + esc(x['note'])) if x['note'] else ''}</td></tr>"
        for x in b["exceptions"]) or "<tr><td colspan=4>None</td></tr>"
    imgs = "".join(
        f"<figure><img src='data:image/png;base64,{passport['attachments'][e['frame_id']]}' alt=''>"
        f"<figcaption>{esc(fmt_ts(e['ts']))}<br>{esc(e['caption'][:110])}</figcaption></figure>"
        for e in b.get("evidence", []) if e["frame_id"] in passport.get("attachments", {}))
    qr = qr_png(qr_payload(passport))
    qr_html = f"<img class=qr src='data:image/png;base64,{base64.b64encode(qr).decode()}' alt='verification QR'>" if qr else ""
    close = (f"<p class=bad><b>Closed over open problems.</b> Technician note: {esc(b['close']['note'])}</p>"
             if b.get("close") else "")
    return f"""<!doctype html><meta charset=utf-8><title>Repair passport {esc(str(b.get('job_number') or ''))}</title>
<style>body{{font:14px system-ui;max-width:820px;margin:2rem auto;color:#0b1220;padding:0 1rem}}
.status{{font-size:1.8rem;font-weight:800;color:{_status_color(b['status'])};letter-spacing:.04em}}
table{{border-collapse:collapse;width:100%;margin:.5rem 0 1rem}}td{{border-bottom:1px solid #e2e8f0;padding:.3rem .5rem;vertical-align:top}}
.ok{{color:#0f766e;font-weight:700}}.bad{{color:#b91c1c;font-weight:700}}code{{font-size:11px;word-break:break-all}}
.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}figure{{margin:0}}figure img{{width:100%;border:1px solid #cbd5e1}}
figcaption{{font-size:11px;color:#475569}}.qr{{width:140px;float:right}}h3{{margin:1rem 0 .2rem}}</style>
{qr_html}<div class=status>{esc(b['status'])}</div>
<p>{esc(b['device']['label'])} &middot; job <b>{esc(str(b.get('job_number') or '-'))}</b> &middot; technician {esc(b['technician'])} &middot; bench {esc(str(b['bench']))}<br>
{esc(fmt_ts(b['started_ts']))} &rarr; {esc(fmt_ts(b['ended_ts']))}</p>{close}
<p><b>{c['parts_removed']}</b> removed &middot; <b>{c['parts_reinstalled']}</b> reinstalled &middot; <b>{c['parts_retired']}</b> retired
&middot; {c['fasteners_accounted']}/{c['fasteners_total']} fasteners &middot; {c['extra_parts']} extra parts
&middot; outstanding {c['parts_outstanding']}</p>
<h3>Checks</h3><table>{inv}</table>
<p>ESD strap logged: {yes(sc['esd_strap_logged'])} &middot; power disconnected logged: {yes(sc['power_disconnected_logged'])}
&middot; safety violations: {sc['safety_violations']} &middot; swelling/heat/smoke events: {sc['swelling_heat_smoke_events']}
&middot; functional test: {'passed' if b['functional_test']['passed'] else 'not passed'}</p>
<h3>Exceptions</h3><table>{exc}</table><h3>Evidence</h3><div class=grid>{imgs}</div>
<h3>Verification</h3><p>Events: {b['event_chain']['length']}<br>Chain head (SHA-256) <code>{b['event_chain']['head']}</code><br>
Signature (Ed25519) <code>{passport['signature']}</code><br>Public key <code>{b['signer']['public_key']}</code></p>"""


def to_pdf(passport: dict, path: str | Path, preview_png: str | Path | None = None) -> None:
    """One A4 page: status, job, counts, checks, exceptions, evidence frames, QR and hash chain."""
    from PIL import Image, ImageDraw, ImageFont

    def font(size, bold=False):
        names = ("arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else ("arial.ttf", "DejaVuSans.ttf")
        for name in names:
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                pass
        return ImageFont.load_default(size)

    b, c, sc = passport["body"], passport["body"]["counts"], passport["body"]["safety_checks"]
    W, H, M = 1240, 1754, 70
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    y = M

    def line(text, size=24, fill="#0b1220", gap=8, x=M, bold=False):
        nonlocal y
        d.text((x, y), text, font=font(size, bold), fill=fill)
        y += size + gap

    d.text((M, y), "REPAIR PASSPORT", font=font(22, True), fill="#64748b")
    y += 34
    line(b["status"], 62, _status_color(b["status"]), 14, bold=True)
    line(f"{b['device']['label']}   |   job {b.get('job_number') or '-'}   |   technician {b['technician']}   |   bench {b['bench']}", 25, gap=6)
    line(f"{fmt_ts(b['started_ts'])}  to  {fmt_ts(b['ended_ts'])}", 22, "#64748b", 22)
    line(f"{c['parts_removed']} removed   {c['parts_reinstalled']} reinstalled   {c['parts_retired']} retired   "
         f"outstanding {c['parts_outstanding']}   |   {c['fasteners_accounted']}/{c['fasteners_total']} fasteners   {c['extra_parts']} extra", 26, "#0f766e", 18, bold=True)
    for i in b["invariants"]:
        line(f"{i['name'].upper():9} {'PASS' if i['ok'] else 'FAIL'}   {i['detail'][:82]}", 21,
             "#0b1220" if i["ok"] else "#b91c1c", 4)
    y += 6
    yn = lambda v: "yes" if v else "NO"  # noqa: E731
    line(f"ESD strap logged: {yn(sc['esd_strap_logged'])}    power disconnected logged: {yn(sc['power_disconnected_logged'])}    "
         f"safety violations: {sc['safety_violations']}    swelling/heat/smoke: {sc['swelling_heat_smoke_events']}", 20, "#334155", 4)
    line(f"Functional test: {'PASSED' if b['functional_test']['passed'] else 'NOT PASSED'}", 22, "#0b1220", 18, bold=True)
    if b.get("close"):
        line(f"Closed over open problems. Technician note: {b['close']['note'][:90]}", 20, "#b45309", 10)
    line("Exceptions", 26, "#0b1220", 6, bold=True)
    exc = b["exceptions"]
    for x in exc[:5] or [{"id": "-", "type": "none", "detail": "", "resolved_by": None, "note": None}]:
        res = f"{x['resolved_by']}: {x['note']}" if x["resolved_by"] else ("OPEN" if x["detail"] else "")
        line(f"{x['id']} {x['type'].replace('_', ' ')}: {x['detail']}"[:100], 19, "#334155", 2)
        if res:
            line(f"-> {res}"[:100], 17, "#64748b", 5, x=M + 40)
    if len(exc) > 5:
        line(f"+ {len(exc) - 5} more in the JSON record", 17, "#64748b", 6)
    y += 10
    line("Evidence", 26, "#0b1220", 8, bold=True)
    tw, th, gap = 352, 220, 20
    shown = [e for e in b.get("evidence", []) if e["frame_id"] in passport.get("attachments", {})]
    for k, e in enumerate(shown[:6]):
        col, row = k % 3, k // 3
        x0, y0 = M + col * (tw + gap), y + row * (th + 62)
        thumb = Image.open(io.BytesIO(base64.b64decode(passport["attachments"][e["frame_id"]]))).convert("RGB")
        img.paste(thumb.resize((tw, th)), (x0, y0))
        d.rectangle([x0, y0, x0 + tw, y0 + th], outline="#cbd5e1")
        d.text((x0, y0 + th + 4), fmt_ts(e["ts"]), font=font(15), fill="#0b1220")
        d.text((x0, y0 + th + 22), e["caption"][:46], font=font(15), fill="#475569")
        d.text((x0, y0 + th + 38), e["caption"][46:92], font=font(15), fill="#475569")
    y += (th + 62) * (1 + (len(shown[:6]) - 1) // 3) if shown else 0
    y = max(y, H - 330)
    d.line([(M, y), (W - M, y)], fill="#e2e8f0", width=2)
    y += 20
    qr = qr_png(qr_payload(passport))
    if qr:
        img.paste(Image.open(io.BytesIO(qr)).convert("RGB").resize((220, 220)), (M, y))
    x = M + 250
    d.text((x, y), "Scan to verify. Hash chain over the event log:", font=font(19, True), fill="#0b1220")
    d.text((x, y + 30), f"{b['event_chain']['length']} events   head (SHA-256)", font=font(16), fill="#64748b")
    d.text((x, y + 52), b["event_chain"]["head"], font=font(15), fill="#334155")
    d.text((x, y + 86), "Signature (Ed25519)", font=font(16), fill="#64748b")
    d.text((x, y + 108), passport["signature"][:64], font=font(15), fill="#334155")
    d.text((x, y + 128), passport["signature"][64:], font=font(15), fill="#334155")
    d.text((x, y + 162), "Public key", font=font(16), fill="#64748b")
    d.text((x, y + 184), b["signer"]["public_key"], font=font(15), fill="#334155")
    img.save(path, "PDF", resolution=150)
    if preview_png:
        img.save(preview_png, "PNG")


def dumps(passport: dict) -> str:
    return json.dumps(passport, indent=2, ensure_ascii=False)
