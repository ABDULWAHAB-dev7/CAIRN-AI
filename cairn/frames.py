"""Frame store and renderer: what the timeline shows when you click an event.

Frames are kept as JSON detections (plus the camera JPEG when there is one). A frame without a
camera image, such as in replay mode or the simulator, is drawn from its detections on the bench
geometry, so every event still has a matching picture.
"""
from __future__ import annotations

import bisect
import dataclasses
import io
import json
from pathlib import Path

from . import geometry as geo

ZONE_COLORS = {"device": "#aeaac0", "hand": "#dad7de", "bench": "#8b8e9c"}  # pearl / chalk / fog
TRAY_COLOR = "#ab8ff1"  # lavender beam
LOST_COLOR = "#f0707a"  # critical: the one non-violet colour


class FrameStore:
    def __init__(self, root: Path, sid: str):
        self.path = root / f"{sid}.jsonl"
        self.img_dir = root / sid
        self.rows: dict[str, dict] = {}
        self.order: list[str] = []
        self._ts: list[float] = []
        root.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._index(json.loads(line))

    def _index(self, row: dict) -> None:
        fid = row["frame_id"]
        if fid not in self.rows:
            self.order.append(fid)
            self._ts.append(row["ts"])
        self.rows[fid] = row

    def append(self, frame) -> None:
        row = {"frame_id": frame.frame_id, "ts": frame.ts,
               "detections": [dataclasses.asdict(d) for d in frame.detections]}
        if frame.frame_id in self.rows:
            return
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, separators=(",", ":")) + "\n")
        self._index(row)

    def save_image(self, frame_id: str, data: bytes) -> None:
        self.img_dir.mkdir(parents=True, exist_ok=True)
        (self.img_dir / f"{_safe(frame_id)}.jpg").write_bytes(data)

    def image(self, frame_id: str) -> bytes | None:
        p = self.img_dir / f"{_safe(frame_id)}.jpg"
        return p.read_bytes() if p.exists() else None

    def row(self, frame_id: str) -> dict | None:
        return self.rows.get(frame_id)

    def latest(self) -> dict | None:
        return self.rows[self.order[-1]] if self.order else None

    def at_or_before(self, ts: float) -> dict | None:
        i = bisect.bisect_right(self._ts, ts) - 1
        return self.rows[self.order[i]] if i >= 0 else None


def _safe(frame_id: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in frame_id)[:80]


def _font(size: int):
    from PIL import ImageFont

    for name in ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


def part_label(session, track_id: str, det: dict) -> tuple[str, str]:
    """('p_04 · hinge screw · tray 04', colour) for one detection, from the graph's identity."""
    g = session.graph
    pid = session.track_map.get(track_id)
    zone = det["zone"]
    if pid:
        n = g.parts[pid]
        where = f"tray {det['well']:02d}" if zone.startswith("tray_") and det.get("well") else zone.replace("_", " ")
        text = f"{g.device.code(pid)} · {n.spec.cls.replace('_', ' ')} · {where}"
        lost = n.state.value == "lost"
    else:
        text, lost = f"? · {det['cls'].replace('_', ' ')} · {zone}", False
    color = LOST_COLOR if lost else TRAY_COLOR if zone.startswith("tray_") else ZONE_COLORS.get(zone, "#94a3b8")
    return text, color


def render_png(row: dict | None, session, size=(960, 600), highlight_well: int | None = None,
               caption: str | None = None, background: bytes | None = None) -> bytes:
    """Draw the bench for one frame: mat, grid, marker, 24 wells, device footprint, quiet outlines."""
    from PIL import Image, ImageDraw

    w, h = geo.CANVAS
    if background:  # a real camera frame: draw only the quiet outlines on top of it
        img = Image.open(io.BytesIO(background)).convert("RGB").resize((w, h))
    else:
        img = Image.new("RGB", (w, h), "#08080a")
    d = ImageDraw.Draw(img)
    if not background:
        for x in range(0, w, 40):
            d.line([(x, 0), (x, h)], fill="#0d0d12")
        for y in range(0, h, 40):
            d.line([(0, y), (w, y)], fill="#0d0d12")
        d.rectangle(geo.MARKER, outline="#dad7de", width=2)
        d.rectangle([geo.MARKER[0] + 8, geo.MARKER[1] + 8, geo.MARKER[2] - 20, geo.MARKER[3] - 20], fill="#dad7de")
    d.rectangle(geo.DEVICE, outline="#25252d", width=1)
    small, tiny = _font(11), _font(10)
    filled = set()
    if row:
        for det in row["detections"]:
            if det.get("well") and det["zone"].startswith("tray_"):
                filled.add(det["well"])
    for n, r in geo.all_wells().items():
        hl = n == highlight_well
        d.rectangle(r, outline="#ab8ff1" if hl else "#25252d", width=3 if hl else 1,
                    fill="#17171c" if n in filled and not background else None)
        d.text((r[0] + 3, r[1] + 2), f"{n:02d}", fill="#62626f", font=tiny)
    if row:
        for det in row["detections"]:
            box = det.get("box")
            if not box:
                continue
            text, color = part_label(session, det["track_id"], det)
            d.rectangle(box, outline=color, width=1)
            full = (box[2] - box[0]) > 20 or det["zone"] == "hand" or color == LOST_COLOR
            d.text((box[0], max(0, box[1] - 13)), text if full else text.split(" · ")[0],
                   fill=color, font=small if full else tiny)  # full label for big/in-hand; code for resting screws
    if caption:
        d.rectangle([0, h - 26, w, h], fill="#0d0d12")
        d.text((10, h - 20), caption, fill="#aeaac0", font=small)
    if size != (w, h):
        img = img.resize(size)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()
