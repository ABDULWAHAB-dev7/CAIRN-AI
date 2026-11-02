import base64
import hashlib
import io

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("PIL")
from fastapi.testclient import TestClient  # noqa: E402

from cairn import geometry as geo  # noqa: E402
from cairn import passport  # noqa: E402
from cairn.device import demo_laptop  # noqa: E402
from cairn.events import EventLog  # noqa: E402
from cairn.frames import FrameStore, render_png  # noqa: E402
from cairn.perception import RawTrack, Sam31Perception, ZoneMap  # noqa: E402
from cairn.scenarios import hero_demo  # noqa: E402
from cairn.server import create_app  # noqa: E402
from cairn.session import Session  # noqa: E402
from cairn.timeline import build_timeline  # noqa: E402


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path, api_token=""))


def png_size(data: bytes):
    from PIL import Image

    return Image.open(io.BytesIO(data)).size


# ---- geometry, wells, codes ----------------------------------------------------------------------
def test_tray_has_24_wells_and_23_fasteners_fill_them_in_class_order():
    d = demo_laptop()
    assert len(geo.all_wells()) == 24
    assert sorted(w for ws in d.wells.values() for w in ws) == list(range(1, 24))
    assert d.wells["tray_4"] == (16, 17, 18, 19) and d.code("hinge_screw_01").startswith("p_")
    assert geo.well_at(geo.well_center(7)) == 7 and geo.well_at((0, 0)) is None


def test_zone_map_default_maps_wells_to_class_trays_and_reports_the_well():
    d = demo_laptop()
    zm = ZoneMap.default(d)
    box = tuple(geo.well_rect(17))
    assert zm.zone_for(box, []) == "tray_4" and zm.well_for(box) == 17
    assert zm.zone_for((60, 150, 80, 170), []) == "device"

    class Fake:
        def track(self, image, prompts):
            return [RawTrack("a", "hinge screw", box, 0.9)]

    det = Sam31Perception(Fake(), zm, {"hinge screw": "hinge_screw"}).frame("f", 0, b"").detections[0]
    assert (det.zone, det.well, det.box) == ("tray_4", 17, box)


# ---- top strip, wells, alerts ----------------------------------------------------------------------
def test_hero_demo_top_strip_and_missing_alert_wording():
    log = EventLog()
    seen = {}
    for label, b in hero_demo(log):
        if label == "dropped_a_screw":
            seen["top"] = b.session.top_strip()
            seen["alerts"] = [a for a in b.alerts if a.kind == "missing_part"]
    assert seen["top"]["missing"] == 1 and seen["top"]["removed"] >= 15
    msg = seen["alerts"][0].message
    assert "left the bench at" in msg and "did not arrive in a tray well" in msg and "p_" in msg
    assert b.session.top_strip() == {"removed": 29, "missing": 0, "accounted": 29, "state": "reassembling"}


def test_wrong_screw_alert_pulses_the_correct_well():
    wrong = None
    for label, b in hero_demo(EventLog()):
        if label == "wrong_screw":
            wrong = [a for a in b.alerts if a.kind == "wrong_fastener"][0]
    assert wrong.well in demo_laptop().wells["tray_4"]  # the 5mm hinge screws live in wells 16-19


def test_wells_list_has_24_entries_and_marks_filled(tmp_path):
    for label, b in hero_demo(EventLog()):
        if label == "teardown_done":
            wells = b.session.wells()
    assert len(wells) == 24 and sum(w["filled"] for w in wells) == 23 and wells[23]["tray"] is None


# ---- timeline ------------------------------------------------------------------------------------------
def test_timeline_names_events_and_links_frames(tmp_path):
    log, store = EventLog(), FrameStore(tmp_path, "t")
    for _, b in hero_demo(log, sink=store.append):
        pass
    tl = build_timeline(b.session.device, log.events())
    kinds = {e["kind"] for e in tl}
    assert {"baseline", "removed", "placed", "returned", "exception", "resolved", "lost", "step"} <= kinds
    assert any("Disconnect the battery" in e["text"] for e in tl if e["kind"] == "exception")
    assert all(store.row(e["frame"]) for e in tl if e["frame"] and e["frame"].startswith("frame_"))
    assert [e["seq"] for e in tl] == sorted(e["seq"] for e in tl)


# ---- server: job, baseline, frames, state at event -----------------------------------------------------
def test_job_number_and_baseline_snapshot(client):
    r = client.post("/sessions", json={"technician": "t", "job_number": "J-77"}).json()
    assert r["job_number"] == "J-77" and r["snapshot"]["job_number"] == "J-77"
    ev = client.get(f"/sessions/{r['id']}/events").json()["events"]
    base = [e for e in ev if e["type"] == "baseline"][0]
    assert base["payload"]["fasteners"] == 23 and base["payload"]["parts"] == 29
    assert len(r["snapshot"]["wells"]) == 24


def test_baseline_image_is_stored_and_served(client):
    sid = client.post("/sessions", json={"technician": "t"}).json()["id"]
    jpg = io.BytesIO()
    from PIL import Image

    Image.new("RGB", (64, 40), "gray").save(jpg, "JPEG")
    assert client.post(f"/sessions/{sid}/baseline", content=b"").status_code == 422
    assert client.post(f"/sessions/{sid}/baseline", content=jpg.getvalue()).json() == {"frame_id": "baseline"}
    raw = client.get(f"/sessions/{sid}/frames/baseline.png", params={"raw": "true"})
    assert raw.headers["content-type"] == "image/jpeg"
    assert png_size(client.get(f"/sessions/{sid}/frames/baseline.png").content) == geo.CANVAS


def test_empty_session_still_renders_a_bench_and_unknown_frame_404s(client):
    sid = client.post("/sessions", json={"technician": "t"}).json()["id"]
    assert png_size(client.get(f"/sessions/{sid}/frames/latest.png").content) == geo.CANVAS
    assert client.get(f"/sessions/{sid}/frames/nope.png").status_code == 404
    assert client.get(f"/sessions/{sid}/frames/latest.png", params={"well": 99}).status_code == 422


def test_state_at_event_rewinds_the_whole_screen(client):
    did = client.post("/demo").json()["id"]
    tl = client.get(f"/sessions/{did}/timeline").json()["entries"]
    lost = next(e for e in tl if e["kind"] == "lost")
    at = client.get(f"/sessions/{did}/at/{lost['seq']}").json()
    assert at["snapshot"]["top"]["missing"] == 1 and at["snapshot"]["top"]["state"] == "components out"
    first = client.get(f"/sessions/{did}/at/1").json()
    assert first["snapshot"]["top"]["removed"] == 0
    assert client.get(f"/sessions/{did}/at/99999").status_code == 404
    png = client.get(f"/sessions/{did}/frames/{at['frame_id']}.png")
    assert png.status_code == 200 and png_size(png.content) == geo.CANVAS


def test_live_snapshot_keeps_recent_alerts_for_the_banner(client):
    sid = client.post("/sessions", json={"technician": "t"}).json()["id"]
    client.post(f"/sessions/{sid}/taps", json={"part_id": "base_screw_01", "zone": "hand"})
    s = client.get(f"/sessions/{sid}").json()
    assert s["recent_alerts"][0]["kind"] == "safety_violation"
    assert any(x["type"] == "safety_violation" for x in s["snapshot"]["exceptions"])


def test_tap_with_well_records_where_the_part_sits(client):
    sid = client.post("/sessions", json={"technician": "t"}).json()["id"]
    client.post(f"/sessions/{sid}/steps", json={"step_id": "t01"})
    client.post(f"/sessions/{sid}/taps", json={"part_id": "base_screw_03", "zone": "tray_1", "well": 3})
    w = client.get(f"/sessions/{sid}").json()["snapshot"]["wells"][2]
    assert w["filled"] and w["part"] == demo_laptop().code("base_screw_03")
    assert client.post(f"/sessions/{sid}/taps", json={"part_id": "ssd", "zone": "hand", "well": 99}).status_code == 422


# ---- close job and the passport ----------------------------------------------------------------------------
def test_close_blocked_then_closed_with_exceptions_needs_a_note(client):
    sid = client.post("/sessions", json={"technician": "t", "job_number": "J-9"}).json()["id"]
    client.post(f"/sessions/{sid}/steps", json={"step_id": "t01"})
    client.post(f"/sessions/{sid}/taps", json={"part_id": "base_screw_01", "zone": "tray_1"})
    r = client.post(f"/sessions/{sid}/close")
    assert r.status_code == 409 and any("count" in x for x in r.json()["detail"]["reasons"])
    no_note = client.post(f"/sessions/{sid}/close", json={"accept_exceptions": True})
    assert no_note.status_code == 409 and "written note" in no_note.json()["detail"]["reasons"][0]
    p = client.post(f"/sessions/{sid}/close", json={"accept_exceptions": True, "note": "customer collected it as-is"}).json()
    assert p["body"]["status"] == "CLOSED WITH EXCEPTIONS" and p["body"]["job_number"] == "J-9"
    assert p["body"]["close"]["note"] == "customer collected it as-is" and p["body"]["close"]["failing"]
    assert client.get(f"/sessions/{sid}").json()["closed"] == "with_exceptions"
    assert client.post(f"/sessions/{sid}/close").json() == p  # idempotent
    assert "CLOSED WITH EXCEPTIONS" in client.get(f"/sessions/{sid}/passport.html").text


def test_verified_passport_has_evidence_qr_counts_and_safety_checks(client):
    did = client.post("/demo").json()["id"]
    p = client.post(f"/sessions/{did}/close").json()
    b = p["body"]
    assert b["status"] == "VERIFIED" and b["job_number"] == "J-1042"
    assert 4 <= len(b["evidence"]) <= 6 and set(p["attachments"]) == {e["frame_id"] for e in b["evidence"]}
    c = b["counts"]
    assert c["parts_removed"] == c["parts_reinstalled"] + c["parts_retired"] and c["parts_outstanding"] == 0
    assert b["safety_checks"]["esd_strap_logged"] and b["safety_checks"]["power_disconnected_logged"]
    assert b["functional_test"]["passed"] is True and b["verify_url"].endswith(f"/v/{did}")
    assert "verification QR" in client.get(f"/sessions/{did}/passport.html").text
    assert client.get(f"/sessions/{did}/passport.pdf").content.startswith(b"%PDF")
    for e in b["evidence"]:  # each image really is the one that was signed
        assert hashlib.sha256(base64.b64decode(p["attachments"][e["frame_id"]])).hexdigest() == e["sha256"]


def test_swapping_an_evidence_image_breaks_verification(client):
    did = client.post("/demo").json()["id"]
    p = client.post(f"/sessions/{did}/close").json()
    assert passport.verify(p)[0]
    fid = p["body"]["evidence"][0]["frame_id"]
    p["attachments"][fid] = base64.b64encode(b"not the same picture").decode()
    ok, problems = passport.verify(p)
    assert not ok and "altered" in problems[0]
    assert client.post("/verify", json=p).json()["valid"] is False


def test_public_verify_page_needs_no_token_and_flags_tampering(tmp_path):
    app = create_app(tmp_path, api_token="tok")
    c = TestClient(app)
    h = {"Authorization": "Bearer tok"}
    did = c.post("/demo", headers=h).json()["id"]
    assert c.get(f"/v/{did}").status_code == 404
    c.post(f"/sessions/{did}/close", headers=h)
    page = c.get(f"/v/{did}")  # no auth header: this is what the QR opens
    assert page.status_code == 200 and "RECORD INTACT" in page.text and "VERIFIED" in page.text
    assert c.get(f"/sessions/{did}/passport", headers={}).status_code == 401  # the full record still needs the token


def test_landing_bench_and_design_assets_are_served(client):
    home = client.get("/")
    assert home.status_code == 200 and "Object permanence for physical work" in home.text and 'href="/bench' in home.text
    assert "Not yet" in home.text and "SAM 3.1 on a real camera" in home.text  # the page says what is not done
    bench = client.get("/bench")
    assert bench.status_code == 200 and "Cairn Bench" in bench.text and "REMOVED" in bench.text and "Close job" in bench.text
    css = client.get("/ui/tokens.css")
    assert css.status_code == 200 and "--color-void:#08080a" in css.text and "--color-lavender-beam:#ab8ff1" in css.text
    assert client.get("/ui/fonts/inter-tight-latin.woff2").content[:4] == b"wOF2"


def test_pages_use_only_the_design_palette():
    import re
    from pathlib import Path

    ui = Path(__file__).resolve().parents[1] / "cairn" / "ui"
    allowed = {"#08080a", "#0d0d12", "#17171c", "#25252d", "#31313a", "#62626f", "#8b8e9c", "#aeaac0", "#dad7de",
               "#ab8ff1", "#8960f0", "#8e6ce4", "#f0707a", "#fff"}
    for name in ("index.html", "bench.html", "tokens.css"):
        found = {c.lower() for c in re.findall(r"#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", (ui / name).read_text(encoding="utf-8"))}
        assert found <= allowed, f"{name} uses off-palette colours: {sorted(found - allowed)}"


# ---- rendering ----------------------------------------------------------------------------------------------
def test_render_highlights_a_well_and_draws_over_a_camera_image(tmp_path):
    from PIL import Image

    s = Session(demo_laptop())
    plain = render_png(None, s, highlight_well=4)
    assert plain != render_png(None, s)
    cam = io.BytesIO()
    Image.new("RGB", (320, 200), (200, 30, 30)).save(cam, "JPEG")
    out = Image.open(io.BytesIO(render_png(None, s, background=cam.getvalue()))).convert("RGB")
    assert out.size == geo.CANVAS and out.getpixel((300, 300))[0] > 150  # camera pixels, not the dark mat
