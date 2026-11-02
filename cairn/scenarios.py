"""A deterministic bench simulator and the scripted hero demo.

The simulator is synthetic: it stands in for SAM 3.1 + a camera so the memory, safety and
verification layers can be exercised and measured. It is NOT evidence about real perception;
that needs recorded bench footage (see README, "Day 1 kill test").
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from .device import Device, demo_laptop
from .events import EventLog
from .session import Alert, Detection, Frame, Session

T0 = 1_793_600_000.0  # 2026-11-02, an arbitrary bench morning


@dataclass
class Bench:
    session: Session
    seed: int = 0
    fps: float = 4.0
    p_dropout: float = 0.0  # chance a detection is missing in a given frame
    p_churn: float = 0.0  # chance the tracker issues a fresh track id for a part
    t: float = T0
    alerts: list[Alert] = field(default_factory=list)
    truth_log: list[dict] = field(default_factory=list)

    def __post_init__(self):
        self.rng = random.Random(self.seed)
        self.device = self.session.device
        self.truth = {pid: "device" for pid in self.device.parts}
        self.aim: dict[str, str | None] = {}
        self.gone: set[str] = set()
        self.track_n: dict[str, int] = {}
        self.extras: dict[str, tuple[str, str]] = {}
        self.frame_n = 0
        self.track_truth: dict[str, str] = {}  # track id -> true part id (for eval)
        self.index = {pid: i for i, pid in enumerate(sorted(self.device.parts))}
        self.xy = {pid: self._home(pid, "device") for pid in self.device.parts}

    def _home(self, pid: str, zone: str) -> tuple[float, float]:
        i = self.index[pid]
        if zone == "device":
            return (100.0 + (i % 6) * 55, 200.0 + (i // 6) * 55)
        if zone.startswith("tray_"):
            k = int(zone.split("_")[1])
            return (640.0 + (k % 3) * 90 + (i % 4) * 14, 90.0 + (k // 3) * 90 + (i % 3) * 14)
        return (420.0 + (i % 5) * 40, 520.0)

    # ---- frames -----------------------------------------------------------------------------
    def _hidden(self, pid: str) -> bool:
        cover_on = self.truth["base_cover"] == "device"
        return cover_on and pid != "base_cover" and self.device.parts[pid].cls != "base_screw"

    def _track(self, pid: str) -> str:
        n = self.track_n.setdefault(pid, 0)
        if self.p_churn and self.rng.random() < self.p_churn:
            n = self.track_n[pid] = n + 1
        tid = f"T:{pid}:{n}"
        self.track_truth[tid] = pid
        return tid

    def frame(self) -> list[Alert]:
        dets = []
        for pid in sorted(self.device.parts):
            if pid in self.gone or self._hidden(pid):
                continue
            if self.p_dropout and self.rng.random() < self.p_dropout:
                continue
            spec = self.device.parts[pid]
            x, y = self.xy[pid]
            jitter = (self.rng.uniform(-1.5, 1.5), self.rng.uniform(-1.5, 1.5))
            dets.append(Detection(self._track(pid), spec.cls, self.truth[pid], 0.95,
                                  self.aim.get(pid), (x + jitter[0], y + jitter[1])))
        for tid, (cls, zone) in self.extras.items():
            dets.append(Detection(tid, cls, zone, 0.9))
        self.frame_n += 1
        out = self.session.observe(Frame(f"frame_{self.frame_n:05d}", self.t, tuple(dets)))
        self.alerts += out
        self.t += 1.0 / self.fps
        return out

    def run(self, seconds: float) -> None:
        for _ in range(max(1, round(seconds * self.fps))):
            self.frame()

    # ---- what a technician does -------------------------------------------------------------
    def pick(self, pid: str, dwell: float = 1.0, aim: str | None = None) -> None:
        self.truth[pid], self.aim[pid] = "hand", aim
        x, y = self.xy[pid]
        self.xy[pid] = (x + 10, y - 25)  # lifted, still near where it came from
        self.run(dwell)

    def put(self, pid: str, zone: str, hole: str | None = None) -> None:
        self.truth[pid], self.aim[pid] = zone, hole
        self.xy[pid] = self._home(pid, zone)
        self.run(0.5)

    def remove(self, pid: str) -> None:
        spec = self.device.parts[pid]
        self.pick(pid)
        self.put(pid, spec.tray if spec.kind == "fastener" else "bench")

    def drop(self, pid: str) -> None:
        self.pick(pid)
        self.gone.add(pid)
        self.truth[pid] = "floor"
        self.truth_log.append({"kind": "drop", "part": pid, "t_left": self.t})
        self.run(0.5)

    def find(self, pid: str, zone: str) -> None:
        self.gone.discard(pid)
        self.track_n[pid] = self.track_n.get(pid, 0) + 1  # the tracker lost it; fresh track id
        self.put(pid, zone)

    def install(self, pid: str, hole: str | None = None, aim_first: str | None = None) -> None:
        self.pick(pid, aim=aim_first)
        self.put(pid, "device", hole)

    def say_step(self, step_id: str) -> None:
        self.alerts += self.session.complete_step(step_id, self.t)
        self.run(0.5)

    def add_extra(self, cls: str = "mystery_screw", zone: str = "bench") -> None:
        self.extras[f"T:extra:{len(self.extras)}"] = (cls, zone)
        self.truth_log.append({"kind": "extra_part", "t": self.t})

    # ---- composite moves --------------------------------------------------------------------
    def teardown_step(self, step_id: str) -> None:
        step = self.device.step(step_id)
        if not step.removes:
            self.say_step(step_id)
        for pid in step.removes:
            self.remove(pid)

    def reassemble_step(self, step) -> None:
        if not step.removes:
            self.say_step(f"r_{step.id}")
        for pid in reversed(step.removes):
            self.install(pid, self.device.parts[pid].hole)


def chaos_session(seed: int, faults: frozenset[str] = frozenset(), p_dropout=0.02, p_churn=0.01,
                  log: EventLog | None = None, boot_ok: bool = True) -> Bench:
    """One full teardown + reassembly, with optional injected faults. Returns the finished bench.

    faults: "drop" (a screw falls), "skip_battery" (reach for the SSD with power on),
            "wrong_screw" (a hinge screw aimed at the SSD hole), "extra_part".
    """
    dev = demo_laptop()
    s = Session(dev, log)
    b = Bench(s, seed=seed, p_dropout=p_dropout, p_churn=p_churn)
    s.register(b.t, technician="tech_a", bench="bench_02")
    b.run(2)
    for step_id in ("t01", "t02", "t03"):
        b.teardown_step(step_id)
    if "skip_battery" in faults:
        b.truth_log.append({"kind": "skip_battery", "t": b.t})
        b.pick("ssd_screw_01")
        b.put("ssd_screw_01", "device")  # Cairn objects; the technician backs off
    b.say_step("t04")
    dropped = None
    for step_id in ("t05", "t06", "t07", "t08", "t09"):
        step = dev.step(step_id)
        for pid in step.removes:
            if "drop" in faults and pid == "battery_screw_01" and dropped is None:
                b.drop(pid)
                dropped = pid
            else:
                b.remove(pid)
        if step_id == "t06" and dropped:
            b.run(6)  # long enough for Cairn to declare it missing
            b.find(dropped, dev.parts[dropped].tray)
    if "extra_part" in faults:
        b.add_extra()
    for step in dev.reverse_steps():
        if "wrong_screw" in faults and step.id == "t09":
            b.pick("ssd_screw_01", aim=dev.parts["hinge_screw_01"].hole)
            b.truth_log.append({"kind": "wrong_screw", "t": b.t})
            b.put("ssd_screw_01", dev.parts["ssd_screw_01"].tray)  # takes the hint and puts it back
        b.reassemble_step(step)
    b.extras.clear()  # the stray part is cleared before the final check
    s.record_boot_test(boot_ok, b.t)
    return b


def hero_demo(log: EventLog | None = None):
    """The three-minute story: a mistake, a memory, a proof. Yields (label, bench) checkpoints."""
    dev = demo_laptop()
    log = EventLog() if log is None else log
    s = Session(dev, log)
    b = Bench(s, seed=7)
    s.register(b.t, technician="tech_a", bench="bench_02")
    b.run(3)
    yield "intro", b
    for step_id in ("t01", "t02", "t03"):
        b.teardown_step(step_id)
    yield "cover_off", b
    # Hero moment: skip the battery step.
    b.pick("ssd_screw_01")
    yield "reached_for_ssd_with_power_on", b
    b.put("ssd_screw_01", "device")
    b.say_step("t04")
    b.teardown_step("t05")
    # Hero moment: drop a screw.
    for pid in dev.step("t06").removes:
        b.drop(pid) if pid == "battery_screw_01" else b.remove(pid)
    b.run(4)
    yield "dropped_a_screw", b
    # Hero moment: the return.
    b.t += 1800
    b.session = Session(dev, log)  # a fresh process: nothing but the event log survives lunch
    b.run(1)
    yield "returned_from_lunch", b
    b.find("battery_screw_01", "tray_2")
    for step_id in ("t07", "t08", "t09"):
        b.teardown_step(step_id)
    yield "teardown_done", b
    for step in dev.reverse_steps():
        if step.id == "t09":
            b.pick("ssd_screw_01", aim=dev.parts["hinge_screw_01"].hole)
            yield "wrong_screw", b
            b.put("ssd_screw_01", "tray_3")
        b.reassemble_step(step)
    yield "reassembled", b
    b.session.record_boot_test(True, b.t)
    yield "boot_test", b
