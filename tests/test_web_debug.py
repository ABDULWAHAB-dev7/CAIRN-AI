"""Regression tests for bugs found while debugging the web screens."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cairn.server import MAX_IMAGE_BYTES, create_app  # noqa: E402

UI = Path(__file__).resolve().parents[1] / "cairn" / "ui"


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path, api_token=""))


def new(client):
    return client.post("/sessions", json={"technician": "t"}).json()["id"]


# ---- the speech parser: questions must never change the safety record ----------------------------
def _run_parser(phrases):
    html = (UI / "bench.html").read_text(encoding="utf-8")
    start = html.index("const QUESTION")
    end = html.index("async function say(")
    code = html[start:end] + f"\nconsole.log(JSON.stringify({json.dumps(phrases)}.map(p => recordFromSpeech(p))));"
    out = subprocess.run(["node", "-e", code], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_speech_questions_never_log_steps_but_statements_do():
    questions = ["Do I need an ESD strap for this?", "is the battery disconnected yet?", "Is the battery out",
                 "what's next?", "should I disconnect the battery", "did the boot test pass?",
                 "can I pull the SSD now", "is it smoking?", "why is the battery still connected"]
    statements = {
        "ESD strap is on": ["steps", {"step_id": "t01"}],
        "I'm wearing the ESD strap": ["steps", {"step_id": "t01"}],
        "battery disconnected": ["steps", {"step_id": "t04"}],
        "the battery is unplugged": ["steps", {"step_id": "t04"}],
        "battery reconnected": ["steps", {"step_id": "r_t04"}],
        "boot test passed": ["boot-test", {"passed": True}],
        "the battery is swelling": ["hazard", {"kind": "swelling"}],
        "I see smoke": ["hazard", {"kind": "smoke"}],
    }
    assert _run_parser(questions) == [None] * len(questions)
    assert _run_parser(list(statements)) == list(statements.values())
    assert _run_parser(["thanks", "hello there", ""]) == [None, None, None]


# ---- server ---------------------------------------------------------------------------------------
def test_session_view_names_the_latest_frame_so_the_page_can_skip_unchanged_pictures(client):
    from cairn.session import Detection, Frame  # noqa: F401

    sid = new(client)
    assert client.get(f"/sessions/{sid}").json()["latest_frame"] is None
    det = {"track_id": "a", "cls": "base_screw", "zone": "device"}
    client.post(f"/sessions/{sid}/frames", json={"frame_id": "f1", "detections": [det]})
    client.post(f"/sessions/{sid}/frames", json={"frame_id": "f2", "detections": [det]})
    assert client.get(f"/sessions/{sid}").json()["latest_frame"] == "f2"


def test_identical_frame_requests_return_identical_images_and_graph_changes_invalidate(client):
    sid = new(client)
    client.post(f"/sessions/{sid}/steps", json={"step_id": "t01"})
    det = {"track_id": "a", "cls": "base_screw", "zone": "device", "box": [1, 1, 9, 9]}
    client.post(f"/sessions/{sid}/frames", json={"frame_id": "f1", "detections": [det]})
    a = client.get(f"/sessions/{sid}/frames/latest.png").content
    assert client.get(f"/sessions/{sid}/frames/latest.png").content == a
    client.post(f"/sessions/{sid}/taps", json={"part_id": "base_screw_01", "zone": "hand"})  # graph moved on
    assert client.get(f"/sessions/{sid}/frames/latest.png").status_code == 200


def test_oversized_uploads_are_refused(client):
    sid = new(client)
    big = b"x" * (MAX_IMAGE_BYTES + 1)
    assert client.post(f"/sessions/{sid}/baseline", content=big).status_code == 413
    assert client.post(f"/sessions/{sid}/baseline", content=b"small").status_code == 200


def test_frame_payload_limits(client):
    sid = new(client)
    det = {"track_id": "a", "cls": "base_screw", "zone": "device"}
    assert client.post(f"/sessions/{sid}/frames", json={"frame_id": "f", "detections": [det] * 301}).status_code == 422
    assert client.post(f"/sessions/{sid}/frames", json={"frame_id": "x" * 81, "detections": [det]}).status_code == 422
    assert client.post(f"/sessions/{sid}/frames", json={"frame_id": "f", "detections": [{**det, "track_id": "t" * 81}]}).status_code == 422


# ---- pages ----------------------------------------------------------------------------------------
def test_bench_page_has_no_prompt_and_labels_every_form_control():
    html = (UI / "bench.html").read_text(encoding="utf-8")
    script = html[html.index("<script>"):]
    assert not re.search(r"(?<![\w.])prompt\(", script) and "alert(" not in script  # unavailable in embedded browsers
    for field in re.findall(r'<input id="(j-\w+|ptok|say)"', html) + ["j-dev", "cnote", "ptxt"]:
        assert f'for="{field}"' in html or f'id="{field}" aria-label' in html or field == "say", f"{field} has no label"
    assert 'role="dialog"' in html and 'aria-modal="true"' in html and 'role="alert"' in html
    assert "tabIndex = 0" in html  # timeline entries are reachable from the keyboard


def test_text_colours_meet_contrast_on_the_dark_surfaces():
    """Ash (#62626f) is 3.0-3.3:1 on the dark surfaces: fine for borders, too faint for text."""
    for name in ("index.html", "bench.html"):
        text = (UI / name).read_text(encoding="utf-8")
        assert not re.search(r"(?<!border-)(?<!background-)color:var\(--color-ash\)", text), f"{name} sets text in ash"
    assert "::placeholder" in (UI / "tokens.css").read_text(encoding="utf-8")
    assert "placeholder,textarea::placeholder{color:var(--color-fog)}" in (UI / "tokens.css").read_text(encoding="utf-8")


def test_landing_has_landmarks_and_one_h1():
    html = (UI / "index.html").read_text(encoding="utf-8")
    assert html.count("<h1") == 1 and "<main" in html and 'aria-label="Main"' in html and 'lang="en"' in html


def test_static_export_serves_bench_from_any_path_and_is_read_only(tmp_path):
    pytest.importorskip("PIL")
    import sys

    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "site"
    run = subprocess.run([sys.executable, str(root / "scripts" / "export_static.py"), "--out", str(out)],
                         capture_output=True, text=True, cwd=root, timeout=120,
                         env={**__import__("os").environ, "PYTHONPATH": str(root)})
    assert run.returncode == 0, run.stderr
    for rel in ("index.html", "bench.html", "bench/index.html", "v.html", "vercel.json", "ui/tokens.css",
                "ui/fonts/inter-tight-latin.woff2", "data/timeline.json", "data/passport.pdf", "data/frames/latest.png"):
        assert (out / rel).exists(), rel
    page = (out / "bench" / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"""['"`]data/""", page), "relative data paths break when served from /bench/"
    assert "/data/meta.json" in page and "read-only replay" in page.lower() and "role', 'note'" in page
    session = json.loads((out / "data" / "session.json").read_text(encoding="utf-8"))
    assert session["latest_frame"] and session["closed"] == "verified"
    assert (out / "data" / "at" / "0.json").exists()


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_camera_asks_for_the_rear_camera_first_and_falls_back_sensibly():
    """Phones open the FRONT camera unless asked for the rear one; a laptop has only one camera."""
    html = (UI / "bench.html").read_text(encoding="utf-8")
    assert 'id="btn-flip"' in html and "flipCam" in html
    start, end = html.index("let facing"), html.index("async function toggleCam")
    harness = """
const log = []; let mode = 'ok';
const navigator = {mediaDevices: {getUserMedia: async (c) => {
  const want = c.video.facingMode && c.video.facingMode.ideal; log.push(want || 'any');
  if (mode === 'denied') throw Object.assign(new Error('denied'), {name: 'NotAllowedError'});
  if (mode === 'laptop' && want) throw Object.assign(new Error('x'), {name: 'OverconstrainedError'});
  return {getVideoTracks: () => [{getSettings: () => ({facingMode: want})}]};
}}};
(async () => {
  const res = {};
  await openStream(); res.phone = log.splice(0);
  facing = 'user'; await openStream(); res.flipped = log.splice(0);
  mode = 'laptop'; facing = 'environment'; await openStream(); res.laptop = log.splice(0);
  mode = 'denied'; try { await openStream(); } catch (e) { res.denied = [log.splice(0).length, e.name]; }
  console.log(JSON.stringify(res));
})();
"""
    out = subprocess.run(["node", "-e", html[start:end] + harness], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == {"phone": ["environment"], "flipped": ["user"],
                                      "laptop": ["environment", "any"], "denied": [1, "NotAllowedError"]}


def test_image_response_says_what_the_model_saw_so_the_page_can_show_it(tmp_path):
    from cairn.session import Detection, Frame

    class Fake:
        prompt_to_class = {"battery": "battery", "fan": "fan"}

        def frame(self, fid, ts, image):
            return Frame(fid, ts, (Detection("a", "battery", "device", 0.8412, box=(10.04, 20, 110, 90)),
                                   Detection("b", "fan", "bench", 0.5)))

    c = TestClient(create_app(tmp_path, perception=Fake(), api_token=""))
    sid = c.post("/sessions", json={"technician": "t"}).json()["id"]
    r = c.post(f"/sessions/{sid}/image", content=b"jpeg").json()
    assert r["detections"] == 2 and r["prompts"] == ["battery", "fan"] and isinstance(r["ms"], int)
    assert r["seen"][0] == {"cls": "battery", "zone": "device", "conf": 0.84, "box": [10.0, 20, 110, 90]}
    assert r["seen"][1]["box"] is None  # a detection without a box is still reported, not dropped


def test_camera_page_always_says_whether_anything_is_being_checked():
    html = (UI / "bench.html").read_text(encoding="utf-8")
    assert 'id="camstat"' in html and 'role="status"' in html
    for state in ("Camera on, but nothing is being checked", "Frames are only analysed inside a job",
                  "none of this device's parts recognised", "The SAM call failed", "Paused: reviewing a past moment",
                  "Dashed outlines show them"):
        assert state in html, state
    assert "if (!sid) { notify('Start a job so I can analyse" in html and "catch (e) { /* offline" not in html  # no silent skip


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_capture_keeps_the_cameras_aspect_ratio():
    """A portrait phone frame used to be stretched into 960x600 before SAM saw it."""
    html = (UI / "bench.html").read_text(encoding="utf-8")
    start, end = html.index("function captureSize()"), html.index("function frameBlob(")
    code = html[start:end] + """
const sizes = [[1280, 720], [720, 1280], [1920, 1080], [640, 480], [1080, 1080]];
const out = sizes.map(([w, h]) => { global.$ = () => ({videoWidth: w, videoHeight: h}); return captureSize(); });
console.log(JSON.stringify(out));"""
    out = subprocess.run(["node", "-e", code.replace("const v = $('cam')", "const v = $('cam')")], capture_output=True, text=True, timeout=20)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    assert got == [[960, 540], [540, 960], [960, 540], [960, 720], [960, 960]]
    for (w, h), (cw, ch) in zip([[1280, 720], [720, 1280], [1920, 1080], [640, 480], [1080, 1080]], got):
        assert abs(w / h - cw / ch) < 0.01
