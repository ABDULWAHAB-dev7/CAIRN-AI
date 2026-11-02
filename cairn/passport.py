"""The repair passport: a signed record anyone can verify without trusting the technician.

Ed25519 over canonical JSON, anchored to the head of the hash-chained event log.
Note: the embedded public key proves integrity, not identity. A shop key registry (roadmap)
is what ties a key to a real shop.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import invariants
from .events import GENESIS, Event, canonical, verify_events
from .graph import ObjectGraph
from .session import Session

SCHEMA = "cairn.passport/1"


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


def _exception_rows(g: ObjectGraph) -> list[dict]:
    return [{
        "id": x.id, "type": x.type, "severity": x.severity, "detail": x.detail, "ts": x.ts,
        "part_id": x.part_id, "evidence": x.evidence, "resolved": x.resolved,
        "resolved_by": x.resolved_by, "note": x.note,
    } for x in g.exceptions.values()]


def build_body(s: Session, technician: str, issued_ts: float, signer: Signer) -> dict:
    g = s.graph
    ok, reasons = invariants.can_close(g)
    if not ok:
        raise PassportRefused(reasons)
    evidence = sorted({f for n in g.parts.values() for f in n.evidence} |
                      {f for x in g.exceptions.values() for f in x.evidence})
    c = g.counts()
    timeline = [{"ts": e.ts, "type": e.type, **{k: v for k, v in e.payload.items() if k in
                 ("step_id", "kind", "passed", "part_id")}}
                for e in s.log.events() if e.type in ("step_completed", "hazard", "hazard_cleared", "boot_test", "part_lost", "part_retired")]
    return {
        "schema": SCHEMA,
        "device": {"id": g.device.id, "label": g.device.label},
        "technician": technician,
        "bench": g.registration.get("bench"),
        "started_ts": g.started_ts,
        "issued_ts": issued_ts,
        "counts": {**c, "extra_parts": sum(1 for x in g.exceptions.values() if x.type == "extra_part")},
        "invariants": [vars(i) for i in invariants.evaluate(g)],
        "exceptions": _exception_rows(g),
        "overrides": [x["id"] for x in _exception_rows(g) if x["resolved_by"] == "technician"],
        "timeline": timeline,
        "evidence": evidence,
        "event_chain": {"genesis": GENESIS, "length": len(s.log), "head": s.log.head()},
        "signer": {"alg": "ed25519", "public_key": signer.public_hex},
    }


def issue(s: Session, technician: str, signer: Signer, issued_ts: float) -> dict:
    """Gate: refuses unless every invariant holds. The passport is not a debug log."""
    body = build_body(s, technician, issued_ts, signer)
    passport = {"body": body, "signature": signer.sign(canonical(body).encode())}
    s._emit(issued_ts, "passport_issued", {"signature": passport["signature"]})
    s._emit(issued_ts, "verified", {})
    return passport


def verify(passport: dict, events: list[Event] | None = None) -> tuple[bool, list[str]]:
    """Check the signature and, if the event log is supplied, replay the hash chain against it."""
    problems = []
    body = passport["body"]
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(body["signer"]["public_key"]))
        pub.verify(bytes.fromhex(passport["signature"]), canonical(body).encode())
    except Exception:
        problems.append("signature does not match the passport body")
    if events is not None:
        ok, bad = verify_events(events)
        if not ok:
            problems.append(f"event chain broken at seq {bad}")
        chain = body["event_chain"]
        if len(events) < chain["length"] or events[chain["length"] - 1].hash != chain["head"]:
            problems.append("event log does not reach the head the passport was signed against")
    return (not problems, problems)


def to_html(passport: dict) -> str:
    b, esc = passport["body"], html.escape
    rows = "".join(
        f"<tr><td>{esc(i['name'])}</td><td class={'ok' if i['ok'] else 'bad'}>{'PASS' if i['ok'] else 'FAIL'}</td>"
        f"<td>{esc(i['detail'])}</td></tr>" for i in b["invariants"])
    exc = "".join(
        f"<tr><td>{esc(x['id'])}</td><td>{esc(x['type'])}</td><td>{esc(x['detail'])}</td>"
        f"<td>{esc(str(x['resolved_by'] or 'open'))}{(': ' + esc(x['note'])) if x['note'] else ''}</td></tr>"
        for x in b["exceptions"]) or "<tr><td colspan=4>None</td></tr>"
    c = b["counts"]
    return f"""<!doctype html><meta charset=utf-8><title>Repair passport</title>
<style>body{{font:14px system-ui;max-width:760px;margin:2rem auto;color:#0b1220}}
h1{{margin:0}}.big{{font-size:2rem;font-weight:700;color:#0f766e}}table{{border-collapse:collapse;width:100%;margin:1rem 0}}
td{{border-bottom:1px solid #e2e8f0;padding:.35rem .5rem;vertical-align:top}}.ok{{color:#0f766e}}.bad{{color:#b91c1c}}
code{{font-size:11px;word-break:break-all}}</style>
<h1>Repair passport</h1><p>{esc(b['device']['label'])} &middot; technician {esc(b['technician'])} &middot; bench {esc(str(b['bench']))}</p>
<p class=big>{c['fasteners_accounted']} / {c['fasteners_total']} fasteners &middot; {c['extra_parts']} extra parts</p>
<table>{rows}</table><h3>Exceptions</h3><table>{exc}</table>
<p>Evidence frames: {len(b['evidence'])} &middot; events: {b['event_chain']['length']}</p>
<p>Chain head<br><code>{b['event_chain']['head']}</code></p>
<p>Signature (ed25519)<br><code>{passport['signature']}</code><br>Public key<br><code>{b['signer']['public_key']}</code></p>"""


def dumps(passport: dict) -> str:
    return json.dumps(passport, indent=2, ensure_ascii=False)
