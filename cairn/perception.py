"""Perception adapters: turn camera output into Frames. The graph never sees pixels.

The SAM 3.1 backend itself is not bundled: it needs Meta Model API access and a real bench.
`SamBackend` is the seam. `ZoneMap` (pixels -> bench zones) is real and tested.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from .session import Detection, Frame

Box = tuple[float, float, float, float]  # x0, y0, x1, y1 in pixels


@dataclass(frozen=True)
class RawTrack:
    track_id: str
    label: str  # the text prompt that matched, e.g. "hinge screw"
    box: Box
    score: float


class SamBackend(Protocol):
    def track(self, image: bytes, prompts: list[str]) -> list[RawTrack]:
        """Text-prompted detection + identity-preserving tracking (SAM 3.1)."""


def _center(b: Box) -> tuple[float, float]:
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def _inside(pt, rect: Box) -> bool:
    return rect[0] <= pt[0] <= rect[2] and rect[1] <= pt[1] <= rect[3]


@dataclass
class ZoneMap:
    """Calibrated once per bench: tray wells and the device footprint, in image pixels."""

    trays: dict[str, Box]
    device: Box
    hand_label: str = "hand"
    wells: dict[int, Box] = field(default_factory=dict)  # numbered tray wells (01-24)
    well_zone: dict[int, str] = field(default_factory=dict)  # well number -> tray zone name

    @classmethod
    def default(cls, device) -> "ZoneMap":
        """Calibration from the shared bench geometry (cairn.geometry), for the demo bench."""
        from . import geometry as geo

        zone = {w: t for t, ws in device.wells.items() for w in ws}
        return cls(trays={}, device=geo.DEVICE, wells=geo.all_wells(), well_zone=zone)

    def well_for(self, box: Box) -> int | None:
        c = _center(box)
        return next((n for n, r in self.wells.items() if _inside(c, r)), None)

    def zone_for(self, box: Box, hands: list[Box]) -> str:
        c = _center(box)
        if any(_inside(c, h) for h in hands):
            return "hand"
        n = self.well_for(box)
        if n is not None:
            return self.well_zone.get(n, f"tray_{n}")
        for name, rect in self.trays.items():
            if _inside(c, rect):
                return name
        return "device" if _inside(c, self.device) else "bench"


DEVICE_CLASS = "@device"  # a prompt mapped to this finds the device itself (its box becomes the "on the device" region)


def _iou(a: Box, b: Box) -> float:
    iw, ih = max(0.0, min(a[2], b[2]) - max(a[0], b[0])), max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = iw * ih
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class SimpleTracker:
    """Stable ids across pictures. SAM image requests number their objects afresh on every call, so object 3 in one
    frame is unrelated to object 3 in the next; without this, identity would be scrambled every frame.

    Matching is per class: first by box overlap, then by nearness to a track that was not matched this frame (a part
    nudged a little, or back after a short occlusion). Tracks that go unseen are kept for `max_age_s` so a returning
    part keeps its id."""

    def __init__(self, max_age_s: float = 12.0, iou_min: float = 0.25, reid_dist: float = 1.6):
        self.max_age_s, self.iou_min, self.reid_dist = max_age_s, iou_min, reid_dist
        self.tracks: dict[str, dict] = {}
        self._n = 0

    def _camera_shift(self, items: list[tuple[str, Box]]) -> tuple[float, float]:
        """A hand-held phone moves between pictures, shifting every part by about the same amount. Estimate that shift
        (median offset to the nearest known part of the same kind) so tiny screws still match after a 10 px wobble."""
        offs: list[tuple[float, float]] = []
        for cls, box in items:
            c, best = _center(box), None
            for t in self.tracks.values():
                if t["cls"] == cls:
                    tc = _center(t["box"])
                    d = math.dist(c, tc)
                    if d <= 40 and (best is None or d < best[0]):
                        best = (d, (c[0] - tc[0], c[1] - tc[1]))
            if best:
                offs.append(best[1])
        if len(offs) < 5:
            return 0.0, 0.0
        xs, ys = sorted(o[0] for o in offs), sorted(o[1] for o in offs)
        return xs[len(xs) // 2], ys[len(ys) // 2]

    def update(self, items: list[tuple[str, Box]], ts: float) -> list[str]:
        self.tracks = {k: t for k, t in self.tracks.items() if ts - t["ts"] <= self.max_age_s}
        dx, dy = self._camera_shift(items)
        for t in self.tracks.values():  # compare like with like: where each known part would be after the wobble
            b = t["box"]
            t["cmp"] = (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)
        ids: list[str | None] = [None] * len(items)
        used: set[str] = set()
        by_cls: dict[str, list[int]] = {}
        for i, (cls, _) in enumerate(items):
            by_cls.setdefault(cls, []).append(i)
        for cls, idxs in by_cls.items():
            cands = [k for k, t in self.tracks.items() if t["cls"] == cls]
            pairs = sorted(((_iou(items[i][1], self.tracks[k]["cmp"]), i, k) for i in idxs for k in cands), reverse=True)
            for score, i, k in pairs:
                if score < self.iou_min:
                    break
                if ids[i] is None and k not in used:
                    ids[i], _ = k, used.add(k)
        for i, (cls, box) in enumerate(items):
            if ids[i] is not None:
                continue
            size, c, best = max(box[2] - box[0], box[3] - box[1]), _center(box), None
            for k, t in self.tracks.items():
                if t["cls"] != cls or k in used:
                    continue
                tb = t["cmp"]
                d = math.dist(c, _center(tb))
                if d <= self.reid_dist * max(size, tb[2] - tb[0], tb[3] - tb[1], 12.0) and (best is None or d < best[0]):
                    best = (d, k)
            if best:
                ids[i], _ = best[1], used.add(best[1])
        for i, (cls, box) in enumerate(items):
            if ids[i] is None:
                self._n += 1
                ids[i] = f"{cls}#{self._n}"
            self.tracks[ids[i]] = {"cls": cls, "box": box, "ts": ts}
        return ids  # type: ignore[return-value]


def _union(boxes: list[Box]) -> Box:
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _grow(b: Box, frac: float) -> Box:
    mx, my = (b[2] - b[0]) * frac, (b[3] - b[1]) * frac
    return (b[0] - mx, b[1] - my, b[2] + mx, b[3] + my)


class Sam31Perception:
    label = "SAM 3.1"

    def __init__(self, backend: SamBackend, zones: ZoneMap, prompt_to_class: dict[str, str], tracker: SimpleTracker | None = None):
        self.backend, self.zones, self.prompt_to_class, self.tracker = backend, zones, prompt_to_class, tracker
        self.device_box: Box | None = None  # last laptop region found (open bench); kept when a frame loses it

    def frame(self, frame_id: str, ts: float, image: bytes) -> Frame:
        prompts = list(self.prompt_to_class) + [self.zones.hand_label]
        raw = self.backend.track(image, prompts)
        hands = [r.box for r in raw if r.label == self.zones.hand_label]
        laptops = [r.box for r in raw if self.prompt_to_class.get(r.label) == DEVICE_CLASS]
        if laptops:  # the device moves, so "on the device" is wherever the laptop is in THIS picture
            self.device_box = _grow(_union(laptops), 0.04)
            self.zones.device = self.device_box
        parts = [r for r in raw if r.label in self.prompt_to_class and self.prompt_to_class[r.label] != DEVICE_CLASS]
        ids = (self.tracker.update([(self.prompt_to_class[r.label], r.box) for r in parts], ts)
               if self.tracker else [r.track_id for r in parts])
        dets = tuple(
            Detection(tid, self.prompt_to_class[r.label], self.zones.zone_for(r.box, hands), r.score,
                      xy=_center(r.box), box=r.box, well=self.zones.well_for(r.box))
            for tid, r in zip(ids, parts)
        )
        return Frame(frame_id, ts, dets)


def load_frames(path: str | Path) -> list[Frame]:
    """Replay mode: frames recorded as JSON, so the demo runs without a camera."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Frame(r["frame_id"], r["ts"], tuple(Detection(**d) for d in r["detections"])) for r in rows]


def dump_frames(frames: list[Frame], path: str | Path) -> None:
    rows = [{"frame_id": f.frame_id, "ts": f.ts, "detections": [vars(d) for d in f.detections]} for f in frames]
    Path(path).write_text(json.dumps(rows), encoding="utf-8")
