"""Perception adapters: turn camera output into Frames. The graph never sees pixels.

The SAM 3.1 backend itself is not bundled: it needs Meta Model API access and a real bench.
`SamBackend` is the seam. `ZoneMap` (pixels -> bench zones) is real and tested.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
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

    def zone_for(self, box: Box, hands: list[Box]) -> str:
        c = _center(box)
        if any(_inside(c, h) for h in hands):
            return "hand"
        for name, rect in self.trays.items():
            if _inside(c, rect):
                return name
        return "device" if _inside(c, self.device) else "bench"


class Sam31Perception:
    def __init__(self, backend: SamBackend, zones: ZoneMap, prompt_to_class: dict[str, str]):
        self.backend, self.zones, self.prompt_to_class = backend, zones, prompt_to_class

    def frame(self, frame_id: str, ts: float, image: bytes) -> Frame:
        prompts = list(self.prompt_to_class) + [self.zones.hand_label]
        raw = self.backend.track(image, prompts)
        hands = [r.box for r in raw if r.label == self.zones.hand_label]
        dets = tuple(
            Detection(r.track_id, self.prompt_to_class[r.label], self.zones.zone_for(r.box, hands), r.score)
            for r in raw if r.label in self.prompt_to_class
        )
        return Frame(frame_id, ts, dets)


def load_frames(path: str | Path) -> list[Frame]:
    """Replay mode: frames recorded as JSON, so the demo runs without a camera."""
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    return [Frame(r["frame_id"], r["ts"], tuple(Detection(**d) for d in r["detections"])) for r in rows]


def dump_frames(frames: list[Frame], path: str | Path) -> None:
    rows = [{"frame_id": f.frame_id, "ts": f.ts, "detections": [vars(d) for d in f.detections]} for f in frames]
    Path(path).write_text(json.dumps(rows), encoding="utf-8")
