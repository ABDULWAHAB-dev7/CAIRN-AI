"""The bench, in pixels. One source of truth for the simulator, the SVG frame renderer,
the default calibration and the UI.

Overhead camera, 960x600 view: device on the left, a 6x4 tray of numbered wells (01-24) at the
top right, loose components below it.
"""
from __future__ import annotations

CANVAS = (960, 600)
DEVICE = (40.0, 120.0, 520.0, 540.0)
BENCH_AREA = (568.0, 360.0, 920.0, 560.0)
MARKER = (24.0, 24.0, 64.0, 64.0)  # printed calibration marker, top-left corner
WELL_COLS, WELL_ROWS, WELL_SIZE, WELL_PITCH = 6, 4, 56.0, 64.0
WELL_ORIGIN = (568.0, 64.0)
N_WELLS = WELL_COLS * WELL_ROWS  # 24


def well_rect(n: int) -> tuple[float, float, float, float]:
    if not 1 <= n <= N_WELLS:
        raise ValueError(f"well {n} out of range 1..{N_WELLS}")
    r, c = divmod(n - 1, WELL_COLS)
    x, y = WELL_ORIGIN[0] + c * WELL_PITCH, WELL_ORIGIN[1] + r * WELL_PITCH
    return (x, y, x + WELL_SIZE, y + WELL_SIZE)


def center(box) -> tuple[float, float]:
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def well_center(n: int) -> tuple[float, float]:
    return center(well_rect(n))


def all_wells() -> dict[int, tuple[float, float, float, float]]:
    return {n: well_rect(n) for n in range(1, N_WELLS + 1)}


def well_at(pt) -> int | None:
    for n, r in all_wells().items():
        if r[0] <= pt[0] <= r[2] and r[1] <= pt[1] <= r[3]:
            return n
    return None
