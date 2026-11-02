import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from cairn.agent import WONDER_TOOLS, SafeAgent, WonderAgent  # noqa: E402
from cairn.local_llm import GlimmerClient  # noqa: E402
from cairn.server import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(tmp_path, api_token=""))


def new(client, **kw):
    r = client.post("/sessions", json={"technician": "tech_a", "bench": "bench_02", **kw})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_health_and_device_list(client):
    h = client.get("/health").json()
    assert h["ok"] and h["auth"] is False and h["privacy"] == "cloud-allowed"
    assert client.get("/devices").json() == {"devices": ["demo_laptop"]}


def test_create_session_validates_input(client):
    assert client.post("/sessions", json={"technician": ""}).status_code == 422
    assert client.post("/sessions", json={"technician": "t", "device": "toaster"}).status_code == 422
    assert client.get("/sessions/nonexistent0").status_code == 404
    assert client.get("/sessions/..%2f..%2fetc").status_code == 404


def test_safety_violation_flows_through_taps_and_guard(client):
    sid = new(client)
    r = client.post(f"/sessions/{sid}/taps", json={"part_id": "base_screw_01", "zone": "tray_1"}).json()
    assert r["alerts"][0]["kind"] == "safety_violation" and r["alerts"][0]["rule"] == "K1_ESD"
    g = client.post(f"/sessions/{sid}/guard", json={"kind": "remove", "part_id": "ssd"}).json()
    assert g["allowed"] is False
    assert client.post(f"/sessions/{sid}/taps", json={"part_id": "nope", "zone": "hand"}).status_code == 404
    assert client.post(f"/sessions/{sid}/taps", json={"part_id": "ssd", "zone": "mars"}).status_code == 422


def test_frames_endpoint_binds_tracks_and_updates_memory(client):
    sid = new(client)
    client.post(f"/sessions/{sid}/steps", json={"step_id": "t01"})

    def det(z):
        return {"frame_id": "f", "detections": [{"track_id": "a", "cls": "base_screw", "zone": z, "xy": [1, 2]}]}

    client.post(f"/sessions/{sid}/frames", json=det("device"))
    client.post(f"/sessions/{sid}/frames", json=det("hand"))
    r = client.post(f"/sessions/{sid}/frames", json=det("tray_1")).json()
    assert r["recap"]["parts_out"] == 1
    snap = client.get(f"/sessions/{sid}").json()["snapshot"]
    assert snap["parts"]["base_screw_01"]["state"] == "removed"


def test_steps_endpoint_only_accepts_action_steps(client):
    sid = new(client)
    assert client.post(f"/sessions/{sid}/steps", json={"step_id": "t02"}).status_code == 422
    assert client.post(f"/sessions/{sid}/steps", json={"step_id": "zz"}).status_code == 404
    assert client.post(f"/sessions/{sid}/steps", json={"step_id": "t01"}).status_code == 200


def test_ask_uses_the_graph(client):
    sid = new(client)
    r = client.post(f"/sessions/{sid}/ask", json={"utterance": "what's next?"}).json()
    assert "ESD" in r["text"] and r["source"] == "graph"
    assert client.get(f"/sessions/{sid}/queries/next_step").json()["next_step"]["id"] == "t01"
    assert client.get(f"/sessions/{sid}/queries/bogus").status_code == 404


def test_hazard_halts_and_clear_requires_active_hazard(client):
    sid = new(client)
    assert client.request("DELETE", f"/sessions/{sid}/hazard", json={"note": "x"}).status_code == 409
    client.post(f"/sessions/{sid}/hazard", json={"kind": "swelling"})
    assert client.get(f"/sessions/{sid}").json()["snapshot"]["phase"] == "EXCEPTION"
    client.request("DELETE", f"/sessions/{sid}/hazard", json={"note": "cooled"})
    assert client.get(f"/sessions/{sid}").json()["snapshot"]["phase"] != "EXCEPTION"


def test_passport_refused_then_issued_after_demo_and_verifies(client):
    sid = new(client)
    r = client.post(f"/sessions/{sid}/passport")
    assert r.status_code == 409 and r.json()["detail"]["reasons"]

    did = client.post("/demo").json()["id"]
    p = client.post(f"/sessions/{did}/passport").json()
    assert p["body"]["counts"]["fasteners_accounted"] == 23
    assert client.post(f"/sessions/{did}/passport").json() == p  # idempotent
    assert client.get(f"/sessions/{did}/passport").json() == p
    assert "Repair passport" in client.get(f"/sessions/{did}/passport.html").text

    ev = client.get(f"/sessions/{did}/events", params={"limit": 5000}).json()
    assert ev["chain_ok"]
    assert client.post("/verify", json={**p, "events": ev["events"]}).json() == {"valid": True, "problems": []}
    forged = json.loads(json.dumps(p))
    forged["body"]["counts"]["fasteners_accounted"] = 99
    assert client.post("/verify", json=forged).json()["valid"] is False
    assert client.post("/verify", json={"body": {}, "signature": "00"}).json()["valid"] is False
    assert client.post("/verify", json={"nope": 1}).status_code == 422


def test_passport_pdf(client):
    pytest.importorskip("PIL")
    did = client.post("/demo").json()["id"]
    assert client.get(f"/sessions/{did}/passport.pdf").status_code == 404
    client.post(f"/sessions/{did}/passport")
    r = client.get(f"/sessions/{did}/passport.pdf")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")


def test_event_stream_backlog_and_resume(client):
    sid = new(client)
    client.post(f"/sessions/{sid}/steps", json={"step_id": "t01"})
    text = client.get(f"/sessions/{sid}/stream", params={"follow": "false"}).text
    assert "event: device_registered" in text and "event: step_completed" in text
    last = max(int(x.split(": ")[1]) for x in text.splitlines() if x.startswith("id: "))
    assert client.get(f"/sessions/{sid}/stream", params={"follow": "false", "after": last}).text == ""


def test_sessions_survive_a_restart(tmp_path):
    a = TestClient(create_app(tmp_path, api_token=""))
    sid = new(a)
    a.post(f"/sessions/{sid}/steps", json={"step_id": "t01"})
    b = TestClient(create_app(tmp_path, api_token=""))
    s = b.get(f"/sessions/{sid}").json()
    assert s["technician"] == "tech_a" and s["snapshot"]["next"]["id"] == "t02"
    assert [x["id"] for x in b.get("/sessions").json()["sessions"]] == [sid]


def test_api_token_is_enforced(tmp_path):
    c = TestClient(create_app(tmp_path, api_token="s3cret"))
    assert c.get("/health").status_code == 200
    assert c.get("/sessions").status_code == 401
    assert c.get("/sessions", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert c.get("/sessions", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_image_endpoint_needs_perception_and_uses_it(tmp_path):
    c = TestClient(create_app(tmp_path, api_token=""))
    sid = new(c)
    assert c.post(f"/sessions/{sid}/image", content=b"x").status_code == 503

    from cairn.session import Detection, Frame

    class Fake:
        def frame(self, fid, ts, image):
            return Frame(fid, ts, (Detection("a", "base_screw", "device"),))

    c2 = TestClient(create_app(tmp_path / "2", perception=Fake(), api_token=""))
    sid2 = new(c2)
    r = c2.post(f"/sessions/{sid2}/image", content=b"jpegbytes").json()
    assert r["detections"] == 1
    assert c2.post(f"/sessions/{sid2}/image", content=b"").status_code == 422


def test_perception_failure_is_a_502_not_a_crash(tmp_path):
    class Boom:
        def frame(self, *a):
            raise RuntimeError("camera on fire")

    c = TestClient(create_app(tmp_path, perception=Boom(), api_token=""))
    sid = new(c)
    assert c.post(f"/sessions/{sid}/image", content=b"x").status_code == 502


def test_privacy_local_refuses_cloud_components(tmp_path, monkeypatch):
    monkeypatch.setenv("CAIRN_PRIVACY", "local")
    monkeypatch.setenv("CAIRN_AGENT", "wonder")
    with pytest.raises(RuntimeError, match="forbids"):
        create_app(tmp_path)
    monkeypatch.setenv("CAIRN_AGENT", "deterministic")
    monkeypatch.setenv("CAIRN_PERCEPTION", "sam")
    with pytest.raises(RuntimeError, match="forbids"):
        create_app(tmp_path)
    monkeypatch.setenv("CAIRN_PERCEPTION", "none")
    assert TestClient(create_app(tmp_path)).get("/health").json()["privacy"] == "local"


def test_safe_agent_falls_back_when_the_llm_is_down(tmp_path):
    class Down:
        def respond(self, s, u):
            raise ConnectionError("offline")

    c = TestClient(create_app(tmp_path, agent=SafeAgent(Down()), api_token=""))
    sid = new(c)
    r = c.post(f"/sessions/{sid}/ask", json={"utterance": "what's next"}).json()
    assert "ESD" in r["text"] and r["source"].startswith("fallback")


# ---- Glimmer (local model) -----------------------------------------------------------------------
def test_glimmer_tool_loop_over_chat_completions():
    sent = []
    script = [
        {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "get_next_steps", "arguments": "{}"}}]}}]},
        {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "c2", "type": "function",
             "function": {"name": "propose_step", "arguments": "{\"step_id\": \"t01\"}"}}]}}]},
    ]

    def transport(path, body):
        sent.append((path, json.loads(json.dumps(body))))
        return script.pop(0)

    from cairn.device import demo_laptop
    from cairn.session import Session

    reply = WonderAgent(GlimmerClient(transport=transport)).respond(Session(demo_laptop()), "next?")
    assert reply.text == "Put on the ESD strap."
    assert sent[0][0] == "/chat/completions" and sent[0][1]["tools"][0]["type"] == "function"
    second = sent[1][1]["messages"]
    assert second[-1]["role"] == "tool" and second[-1]["tool_call_id"] == "c1"
    assert second[-2]["role"] == "assistant" and second[-2]["tool_calls"][0]["id"] == "c1"


def test_glimmer_unreachable_raises_clear_error():
    from cairn.meta_api import MetaApiError

    with pytest.raises(MetaApiError, match="unreachable"):
        GlimmerClient(base_url="http://127.0.0.1:9/v1", timeout=1).complete(
            [{"role": "user", "content": "hi"}], WONDER_TOOLS)
