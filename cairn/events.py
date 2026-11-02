"""Append-only, hash-chained event log. The single source of truth for a repair."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass

GENESIS = "0" * 64


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(prev_hash: str, ts: float, type_: str, payload: dict) -> str:
    return hashlib.sha256((prev_hash + canonical([ts, type_, payload])).encode()).hexdigest()


@dataclass(frozen=True)
class Event:
    seq: int
    ts: float
    type: str
    payload: dict
    prev_hash: str
    hash: str


class EventLog:
    """SQLite-backed log. UPDATE and DELETE are rejected by triggers, so history is replayable."""

    def __init__(self, path: str = ":memory:"):
        self._db = sqlite3.connect(path)
        self._db.executescript(
            """
            create table if not exists events(
              seq integer primary key, ts real not null, type text not null,
              payload text not null, prev_hash text not null, hash text not null);
            create trigger if not exists events_no_update before update on events
              begin select raise(abort, 'event log is append-only'); end;
            create trigger if not exists events_no_delete before delete on events
              begin select raise(abort, 'event log is append-only'); end;
            """
        )
        self._db.commit()

    def head(self) -> str:
        row = self._db.execute("select hash from events order by seq desc limit 1").fetchone()
        return row[0] if row else GENESIS

    def append(self, ts: float, type_: str, payload: dict) -> Event:
        prev = self.head()
        h = compute_hash(prev, ts, type_, payload)
        cur = self._db.execute(
            "insert into events(ts, type, payload, prev_hash, hash) values (?,?,?,?,?)",
            (ts, type_, canonical(payload), prev, h),
        )
        self._db.commit()
        return Event(cur.lastrowid, ts, type_, payload, prev, h)

    def events(self) -> list[Event]:
        rows = self._db.execute(
            "select seq, ts, type, payload, prev_hash, hash from events order by seq"
        ).fetchall()
        return [Event(s, ts, t, json.loads(p), ph, h) for s, ts, t, p, ph, h in rows]

    def __len__(self) -> int:
        return self._db.execute("select count(*) from events").fetchone()[0]

    def verify(self) -> tuple[bool, int | None]:
        return verify_events(self.events())


def verify_events(events: list[Event]) -> tuple[bool, int | None]:
    """Recompute the chain. Returns (ok, first_bad_seq)."""
    prev = GENESIS
    for e in events:
        if e.prev_hash != prev or compute_hash(prev, e.ts, e.type, e.payload) != e.hash:
            return False, e.seq
        prev = e.hash
    return True, None
