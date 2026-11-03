"""Open-bench mode: any laptop, parts discovered by the camera, and the app says what you take off.

The fake backend behaves like the real SAM image API: it finds the laptop, and it renumbers its objects on EVERY call
(`screw:0` in one frame is not `screw:0` in the next), in a different order each time.
"""
import random

import pytest

from cairn.device import get_device
from cairn.events import EventLog
from cairn.meta_api import RawTrack
from cairn.perception import DEVICE_CLASS, Sam31Perception, SimpleTracker, ZoneMap
from cairn.session import Session

LAPTOP = (100.0, 100.0, 700.0, 500.0)
SCREW_SPOTS = [(150, 150), (250, 150), (350, 150), (450, 150), (550, 150)]  # all on the laptop
OFF = (850, 300)  # well outside the laptop


def box(c, r=8):
    return (c[0] - r, c[1] - r, c[0] + r, c[1] + r)


class FakeSam:
    """Scripted scene: .screws = centres on screen, .hand = a box or None, .laptop = box or None."""

    def __init__(self):
        self.screws, self.hand, self.laptop, self.calls = list(SCREW_SPOTS), None, LAPTOP, 0
        self.rng = random.Random(3)

    def track(self, image, prompts):
        self.calls += 1
        out = []
        if self.laptop:
            out.append(RawTrack("laptop:0", "laptop", self.laptop, 0.9))
        order = list(self.screws)
        self.rng.shuffle(order)  # the real API numbers objects afresh, in no useful order
        out += [RawTrack(f"screw:{i}", "screw", box(c), 0.8) for i, c in enumerate(order)]
        if self.hand:
            out.append(RawTrack("hand:0", "hand", self.hand, 0.7))
        return out


class Bench:
    def __init__(self):
        self.sam = FakeSam()
        zones = ZoneMap(trays={}, device=(0.0, 0.0, 1e9, 1e9))
        self.perception = Sam31Perception(self.sam, zones, {"laptop": DEVICE_CLASS, "screw": "screw"}, SimpleTracker())
        self.session = Session(get_device("open_laptop"), EventLog())
        self.session.register(0.0, "tech", "bench")
        self.t, self.alerts = 1000.0, []

    def frame(self, n=1):
        out = []
        for _ in range(n):
            f = self.perception.frame(f"f{int(self.t)}", self.t, b"jpeg")
            out += self.session.observe(f)
            self.t += 3.0
        self.alerts += out
        return out

    def said(self):
        return [a.message for a in self.alerts if a.severity == "info" and a.kind != "step_done"]


def test_it_announces_what_it_sees_once_parts_are_stable_and_nothing_else_happens_while_still():
    b = Bench()
    assert b.frame() == []  # one picture can be a false positive: wait for a second
    second = b.frame()
    assert [a.kind for a in second] == ["seen"] and "5 screws" in second[0].message
    assert b.frame(4) == []  # ids are renumbered every call, yet nothing is "removed": identity is stable
    top = b.session.top_strip()
    assert top["removed"] == 0 and top["missing"] == 0
    assert len(b.session.graph.discovered) == 5


def test_unscrewing_is_announced_with_a_running_count():
    b = Bench()
    b.frame(2)
    b.sam.screws.remove(SCREW_SPOTS[2])  # a screw leaves the laptop...
    b.sam.hand = box((350, 150), 40)
    b.sam.screws.append((355, 155))  # ...held in the hand, still over the laptop
    b.frame()
    b.sam.hand = None
    b.sam.screws.remove((355, 155))
    b.sam.screws.append(OFF)  # ...and put down on the table
    b.frame()
    msgs = b.said()
    assert any(m.startswith("Removed screw") and "4 screws still on the laptop" in m for m in msgs), msgs
    assert b.session.tally()["screw"] == {"label": "screw", "on_device": 4, "in_hand": 0, "off_device": 1,
                                          "not_visible": 0, "lost": 0}
    assert b.session.top_strip()["removed"] == 1 and b.session.top_strip()["accounted"] == 1
    assert len(b.session.graph.discovered) == 5  # the moved screw kept its identity; no sixth slot was claimed


def test_several_screws_count_down_and_one_is_dropped_and_flagged_missing():
    b = Bench()
    b.frame(2)
    for spot in SCREW_SPOTS[:3]:
        b.sam.screws.remove(spot)
        b.sam.screws.append(OFF)
        OFF_next = (OFF[0] + 40, OFF[1])
        globals()["OFF"] = OFF_next
        b.frame()
    removed = [m for m in b.said() if m.startswith("Removed screw")]
    assert [m.split(". ")[1] for m in removed] == ["4 screws still on the laptop.", "3 screws still on the laptop.",
                                                    "2 screws still on the laptop."]
    # a screw goes into the hand and then vanishes (dropped): flagged after the grace period, not before
    gone = SCREW_SPOTS[3]
    b.sam.screws.remove(gone)
    b.sam.hand = box(gone, 40)
    b.sam.screws.append((gone[0] + 5, gone[1] + 5))
    b.frame()
    b.sam.screws.remove((gone[0] + 5, gone[1] + 5))
    b.sam.hand = None
    b.frame()  # 3 s later: one missed frame is not a loss (SAM blinks on tiny parts in a hand)
    assert not b.session.graph.missing_parts()
    b.frame()  # 6 s: still inside the 7 s grace
    assert not b.session.graph.missing_parts()
    b.frame()  # 9 s: gone for good
    assert len(b.session.graph.missing_parts()) == 1
    assert any(a.kind == "missing_part" for a in b.alerts)
    assert b.session.top_strip()["missing"] == 1


def test_a_screw_put_back_is_announced_and_counts_up():
    b = Bench()
    b.frame(2)
    b.sam.screws.remove(SCREW_SPOTS[0])
    b.sam.screws.append(OFF)
    b.frame()
    b.sam.screws.remove(OFF)
    b.sam.screws.append(SCREW_SPOTS[0])
    b.frame()
    assert any(m.endswith("5 screws on the laptop.") and "back on the laptop" in m for m in b.said()), b.said()
    assert b.session.top_strip()["state"] != "sealed" and b.session.tally()["screw"]["on_device"] == 5


def test_the_laptop_region_follows_the_laptop():
    b = Bench()
    b.frame()
    assert b.perception.device_box and b.perception.device_box[0] < LAPTOP[0]  # grown a little for margin
    b.sam.laptop = None  # laptop not found in this picture: keep the last region instead of calling everything removed
    before = b.perception.device_box
    b.frame()
    assert b.perception.device_box == before and b.session.top_strip()["removed"] == 0


def test_no_esd_strap_is_demanded_on_the_open_bench():
    b = Bench()
    b.frame(2)
    b.sam.screws.remove(SCREW_SPOTS[1])
    b.sam.screws.append(OFF)
    b.frame()
    assert not b.session.graph.exceptions  # the demo laptop would have stopped you; any other laptop must not
    assert get_device("demo_laptop").require_esd is True and get_device("open_laptop").require_esd is False


def test_open_bench_counts_only_what_the_camera_found():
    b = Bench()
    b.frame(2)
    c = b.session.graph.counts()
    assert c["fasteners_total"] == 5 and c["fasteners_accounted"] == 5  # not the 60 slots in the pool
    snap = b.session.snapshot()
    assert snap["open_bench"] is True and len(snap["parts"]) == 5 and snap["tally"]["screw"]["on_device"] == 5


# ---- the tracker on its own --------------------------------------------------------------------------------------------
def test_tracker_keeps_ids_across_shuffled_detections_and_after_a_short_occlusion():
    t = SimpleTracker(max_age_s=12)
    a = [("screw", box((100, 100))), ("screw", box((200, 100))), ("cable", box((300, 300), 30))]
    ids1 = t.update(a, 0.0)
    ids2 = t.update([a[2], a[0], a[1]], 3.0)  # same scene, listed in another order
    assert ids2 == [ids1[2], ids1[0], ids1[1]]
    t.update([a[0], a[2]], 6.0)  # screw 2 hidden for a while
    t.update([a[0], a[2]], 9.0)
    ids3 = t.update(a, 12.0)  # and it is back, within max_age
    assert ids3 == ids1


def test_tracker_forgets_old_tracks_and_never_mixes_kinds():
    t = SimpleTracker(max_age_s=5)
    first = t.update([("screw", box((100, 100)))], 0.0)
    again = t.update([("screw", box((100, 100)))], 30.0)  # far too late: a new part
    assert again != first
    other = t.update([("fan", box((100, 100)))], 31.0)  # same place, different kind
    assert other[0].startswith("fan#")


def test_tracker_follows_a_part_that_moved_a_little():
    t = SimpleTracker()
    a = t.update([("screw", box((100, 100)))], 0.0)
    b = t.update([("screw", box((112, 104)))], 3.0)
    assert a == b


@pytest.mark.parametrize("n", [0, 1])
def test_tracker_handles_empty_and_single_frames(n):
    assert SimpleTracker().update([("screw", box((5, 5)))][:n], 0.0) == (["screw#1"] if n else [])


# ---- the close-up case: the laptop fills the picture, so a removed screw simply stops being there ----------------------
def test_a_screw_that_vanishes_from_a_still_visible_board_is_reported_after_a_few_seconds():
    b = Bench()
    b.frame(3)
    b.sam.screws.remove(SCREW_SPOTS[1])  # unscrewed and taken out of the picture
    for _ in range(2):  # 3 s and 6 s later: could be a blink, say nothing
        b.frame()
    assert not [m for m in b.said() if "no longer" in m]
    b.frame(2)  # 9 s, 12 s: it is gone
    gone = [m for m in b.said() if "no longer on the laptop" in m]
    assert len(gone) == 1 and "4 screws still on the laptop" in gone[0], b.said()
    t = b.session.tally()["screw"]
    assert t["on_device"] == 4 and t["not_visible"] == 1
    assert b.session.top_strip()["removed"] == 1
    assert b.session.top_strip()["accounted"] == 0  # gone from view is not "accounted for": nobody knows where it is
    assert b.session.top_strip()["missing"] == 0  # and it is not an alarm either


def test_the_timeline_records_what_came_off_and_does_not_pretend_there_was_a_sealed_baseline():
    from cairn.timeline import build_timeline

    b = Bench()
    b.frame(3)
    b.sam.screws.remove(SCREW_SPOTS[1])
    b.frame(4)
    text = [e["text"] for e in build_timeline(b.session.device, b.session.log.events())]
    assert any("no longer on the laptop" in t for t in text), text
    sealed = [t for t in text if "sealed device" in t]
    assert not sealed, sealed


def test_a_vanished_screw_that_comes_back_is_announced_as_back():
    b = Bench()
    b.frame(3)
    b.sam.screws.remove(SCREW_SPOTS[1])
    b.frame(4)  # long enough to be reported gone
    b.sam.screws.append(SCREW_SPOTS[1])
    b.frame()
    assert any("back on the laptop" in m and m.endswith("5 screws on the laptop.") for m in b.said()), b.said()
    assert b.session.tally()["screw"]["on_device"] == 5


def test_if_most_parts_vanish_at_once_the_camera_moved_and_nothing_is_called_removed():
    b = Bench()
    b.frame(3)
    keep = b.sam.screws[0]
    b.sam.screws = [keep]  # the phone swung away: 4 of 5 screws gone from the picture at the same moment
    b.frame(5)
    assert not [m for m in b.said() if "no longer" in m or m.startswith("Removed")]
    assert b.session.top_strip()["removed"] == 0
    b.sam.screws = list(SCREW_SPOTS)  # and back
    b.frame(2)
    assert b.session.top_strip()["removed"] == 0 and b.session.tally()["screw"]["on_device"] == 5


def test_a_one_off_false_positive_is_never_counted_or_announced():
    b = Bench()
    b.frame(3)
    b.sam.screws.append((600, 300))  # noise: appears in a single picture
    b.frame()
    b.sam.screws.remove((600, 300))
    b.frame(5)
    assert b.session.tally()["screw"]["on_device"] == 5  # the phantom is not part of the count
    assert not [m for m in b.said() if "no longer" in m or m.startswith("Removed")]


def test_hand_held_camera_shake_does_not_look_like_unscrewing():
    b = Bench()
    b.frame(3)
    for dx, dy in [(14, 9), (-10, 12), (6, -15), (0, 0)]:  # the whole picture wobbles
        b.sam.screws = [(x + dx, y + dy) for x, y in SCREW_SPOTS]
        b.sam.laptop = (LAPTOP[0] + dx, LAPTOP[1] + dy, LAPTOP[2] + dx, LAPTOP[3] + dy)
        b.frame()
    assert b.session.top_strip()["removed"] == 0 and len(b.session.graph.discovered) == 5
    assert not [m for m in b.said() if m.startswith("Removed") or "no longer" in m]


def test_tracker_compensates_a_shift_that_would_defeat_overlap_matching_on_tiny_boxes():
    t = SimpleTracker()
    grid = [("screw", box((100 + 40 * i, 100 + 30 * j), 6)) for i in range(4) for j in range(3)]
    ids = t.update(grid, 0.0)
    shifted = [(c, (b[0] + 16, b[1] + 11, b[2] + 16, b[3] + 11)) for c, b in grid]  # 16 px wobble on 12 px boxes
    assert t.update(shifted, 3.0) == ids


# ---- the server and the page ---------------------------------------------------------------------
def test_image_endpoint_reports_the_tally_and_laptop_region_for_the_page(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from cairn.server import create_app
    from cairn.session import Detection, Frame

    class Fake:
        prompt_to_class = {"laptop": DEVICE_CLASS, "screw": "screw"}
        device_box = LAPTOP

        def frame(self, fid, ts, image):
            return Frame(fid, ts, tuple(Detection(f"s{i}", "screw", "device", 0.8, xy=c, box=box(c)) for i, c in enumerate(SCREW_SPOTS)))

    c = TestClient(create_app(tmp_path, perception=Fake(), api_token=""))
    sid = c.post("/sessions", json={"technician": "t", "device": "open_laptop"}).json()["id"]
    first = c.post(f"/sessions/{sid}/image", content=b"jpeg").json()
    assert first["tally"] == {} and not [a for a in first["alerts"] if a["kind"] == "seen"]  # one picture proves nothing
    second = c.post(f"/sessions/{sid}/image", content=b"jpeg").json()
    assert second["tally"]["screw"]["on_device"] == 5 and second["device_box"] == list(LAPTOP)
    assert second["prompts"] == ["screw"]  # the laptop is not a part, so it is not listed as one
    assert [a["message"] for a in second["alerts"] if a["kind"] == "seen"] == [
        "I can see 5 screws on the laptop. Start taking it apart and I will say what you remove."]
    snap = c.get(f"/sessions/{sid}").json()["snapshot"]
    assert snap["open_bench"] is True and snap["tally"]["screw"]["on_device"] == 5 and len(snap["parts"]) == 5


def test_open_laptop_is_the_first_device_offered():
    pytest.importorskip("fastapi")
    from cairn.device import DEVICES

    assert list(DEVICES)[0] == "open_laptop"


UI = __import__("pathlib").Path(__file__).resolve().parents[1] / "cairn" / "ui"


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node not installed")
def test_page_turns_the_tally_into_plain_rows():
    import json
    import subprocess

    html = (UI / "bench.html").read_text(encoding="utf-8")
    code = html[html.index("function plural("):html.index("function handleAlerts(")] + """
const t = {screw: {label: 'screw', on_device: 31, in_hand: 1, off_device: 0, not_visible: 2, lost: 0},
           fan: {label: 'fan', on_device: 1, in_hand: 0, off_device: 0, not_visible: 0, lost: 0}};
console.log(JSON.stringify([tallyRows(t), tallyRows(null), plural('screw', 1), plural('screw', 0)]));"""
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    rows, empty, one, none = json.loads(out.stdout)
    assert rows[0]["title"] == "Screws" and rows[0]["on"] == 31 and rows[0]["total"] == 34
    assert rows[0]["text"] == "31 on the laptop, 1 in a hand, 2 no longer on it"
    assert rows[1]["title"] == "Fans" and rows[1]["text"] == "1 on the laptop"
    assert empty == [] and one == "1 screw" and none == "0 screws"


def test_page_offers_the_open_bench_and_says_what_it_cannot_do():
    html = (UI / "bench.html").read_text(encoding="utf-8")
    for text in ("Any laptop (open bench)", "I cannot yet recognise batteries, drives, memory or the back cover",
                 "Take it apart. I am watching.", "cam.deviceBox", "SAYS.has(a.kind)", "On the laptop: "):
        assert text in html, text


def test_a_billing_refusal_from_meta_is_explained_and_shown_on_health(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from cairn.meta_api import MetaApiError
    from cairn.server import PerceptionPool, _perception_error, create_app

    refusal = MetaApiError('402 from Meta Model API: b\'{"error":{"code":"billing_not_configured","message":"Billing Issue"}}\'')
    msg = _perception_error(refusal)
    assert "billing problem" in msg and "dev.meta.ai/billing" in msg and "b'" not in msg
    assert "rejected the API key" in _perception_error(MetaApiError("401 from Meta Model API: b'no'"))
    assert _perception_error(RuntimeError("boom")) == "perception failed: RuntimeError: boom"

    class Refusing:
        def track(self, image, prompts):
            raise refusal

    pool = PerceptionPool(lambda: Refusing())
    c = TestClient(create_app(tmp_path, perception=pool, api_token=""))
    assert c.get("/health").json()["perception_warning"] is None
    sid = c.post("/sessions", json={"technician": "t", "device": "open_laptop"}).json()["id"]
    r = c.post(f"/sessions/{sid}/image", content=b"jpeg")
    assert r.status_code == 502 and "billing problem" in r.json()["detail"]
    assert "billing problem" in c.get("/health").json()["perception_warning"]
