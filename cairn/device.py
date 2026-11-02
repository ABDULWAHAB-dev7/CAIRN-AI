"""Curated task graph for a device. The LLM chooses among these steps; it never invents them."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class PartSpec:
    id: str
    cls: str
    label: str
    kind: str  # "fastener" | "component"
    tray: str
    size_mm: float | None = None
    hole: str | None = None  # fasteners: the hole this fastener came from
    fastens: str | None = None  # fasteners: component it holds
    requires_power_off: bool = True


@dataclass(frozen=True)
class StepSpec:
    id: str
    action: str
    why: str
    removes: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    effect: str | None = None  # "esd_on" | "power_off"
    reverse_action: str | None = None  # None => not reversed during reassembly


@dataclass
class Device:
    id: str
    label: str
    parts: dict[str, PartSpec]
    steps: tuple[StepSpec, ...]
    trays: dict[str, str] = field(default_factory=dict)  # tray slot -> part class

    def __post_init__(self):
        self._step_by_id = {s.id: s for s in self.steps}
        self.holes: dict[str, PartSpec] = {p.hole: p for p in self.parts.values() if p.hole}
        self.step_of_part = {pid: s.id for s in self.steps for pid in s.removes}
        self.dependents: dict[str, list[str]] = {s.id: [] for s in self.steps}
        for s in self.steps:
            for r in s.requires:
                self.dependents[r].append(s.id)

    def step(self, step_id: str) -> StepSpec:
        return self._step_by_id[step_id]

    def classes(self) -> list[str]:
        return sorted({p.cls for p in self.parts.values()})

    def parts_of(self, cls: str) -> list[PartSpec]:
        return sorted((p for p in self.parts.values() if p.cls == cls), key=lambda p: p.id)

    def fasteners(self) -> list[PartSpec]:
        return [p for p in self.parts.values() if p.kind == "fastener"]

    def tray_for(self, cls: str) -> str:
        return next(p.tray for p in self.parts.values() if p.cls == cls)

    def reverse_steps(self) -> list[StepSpec]:
        return [s for s in reversed(self.steps) if s.reverse_action or s.removes]


def demo_laptop() -> Device:
    """A 23-fastener demo laptop: 6 fastener classes, 6 components."""
    parts: dict[str, PartSpec] = {}

    def components(*items):
        for pid, label, power in items:
            parts[pid] = PartSpec(pid, pid, label, "component", "bench", requires_power_off=power)

    def screws(cls, label, n, size, tray, fastens, power=True):
        for i in range(1, n + 1):
            pid = f"{cls}_{i:02d}"
            parts[pid] = PartSpec(
                pid, cls, label, "fastener", tray, size, f"{fastens}.{cls}.{i:02d}", fastens, power
            )

    components(
        ("base_cover", "base cover", False),
        ("battery", "battery", True),
        ("ssd", "SSD", True),
        ("fan", "cooling fan", True),
        ("wifi_card", "Wi-Fi card", True),
        ("hinge_bracket", "hinge bracket", True),
    )
    screws("base_screw", "M2x6 base screw", 10, 6, "tray_1", "base_cover", power=False)
    screws("battery_screw", "M2x4 battery screw", 4, 4, "tray_2", "battery")
    screws("ssd_screw", "M2x3 SSD screw", 1, 3, "tray_3", "ssd")
    screws("hinge_screw", "M2.5x5 hinge screw", 4, 5, "tray_4", "hinge_bracket")
    screws("fan_screw", "M2x4 fan screw", 3, 4, "tray_5", "fan")
    screws("wifi_screw", "M2x3 Wi-Fi screw", 1, 3, "tray_6", "wifi_card")

    def ids(cls):
        return tuple(sorted(p for p in parts if p.rsplit("_", 1)[0] == cls))

    steps = (
        StepSpec("t01", "Put on the ESD strap", "Static discharge can kill a board you cannot see.",
                 effect="esd_on"),
        StepSpec("t02", "Remove the 10 base screws", "The base cover is held by ten fasteners.",
                 removes=ids("base_screw"), requires=("t01",)),
        StepSpec("t03", "Lift off the base cover", "Nothing inside is reachable until the cover is off.",
                 removes=("base_cover",), requires=("t02",)),
        StepSpec("t04", "Disconnect the battery", "A live battery can short a board; this must come first.",
                 requires=("t03",), effect="power_off", reverse_action="Reconnect the battery"),
        StepSpec("t05", "Remove the SSD", "The SSD sits above the battery connector.",
                 removes=ids("ssd_screw") + ("ssd",), requires=("t04",)),
        StepSpec("t06", "Remove the battery", "The battery covers the hinge screws.",
                 removes=ids("battery_screw") + ("battery",), requires=("t04",)),
        StepSpec("t07", "Remove the cooling fan", "The fan is held by three screws and a ribbon.",
                 removes=ids("fan_screw") + ("fan",), requires=("t04",)),
        StepSpec("t08", "Remove the Wi-Fi card", "The antenna leads must come off with it.",
                 removes=ids("wifi_screw") + ("wifi_card",), requires=("t04",)),
        StepSpec("t09", "Remove the hinge bracket", "Reachable only once the battery is out.",
                 removes=ids("hinge_screw") + ("hinge_bracket",), requires=("t06",)),
    )
    trays = {p.tray: p.cls for p in parts.values() if p.kind == "fastener"}
    return Device("demo_laptop", "Demo laptop (23 fasteners)", parts, steps, trays)


DEVICES = {"demo_laptop": demo_laptop}


def get_device(device_id: str) -> Device:
    try:
        return DEVICES[device_id]()
    except KeyError:
        raise KeyError(f"unknown device {device_id!r}; known: {sorted(DEVICES)}") from None
