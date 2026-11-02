import copy
import sqlite3

import pytest

from cairn import invariants, passport, safety
from cairn.agent import DeterministicAgent, WonderAgent
from cairn.device import demo_laptop
from cairn.events import Event, EventLog, verify_events
from cairn.graph import PartState, Phase
from cairn.perception import RawTrack, Sam31Perception, ZoneMap
from cairn.scenarios import Bench, chaos_session, hero_demo
from cairn.session import Session


def fresh():
    dev = demo_laptop()
    s = Session(dev)
    b = Bench(s, seed=1)
    s.register(b.t, "tech", "bench")
    b.run(2)
    return s, b


# ---- event log ----------------------------------------------------------------------------------
def test_log_is_hash_chained_and_append_only():
    log = EventLog()
    for i in range(5):
        log.append(float(i), "x", {"i": i})
    assert log.verify() == (True, None)
    with pytest.raises(sqlite3.DatabaseError):
        log._db.execute("update events set payload='{}' where seq=2")
    with pytest.raises(sqlite3.DatabaseError):
        log._db.execute("delete from events where seq=2")


def test_tampered_event_is_detected():
    log = EventLog()
    for i in range(4):
        log.append(float(i), "x", {"i": i})
    evs = log.events()
    forged = Event(evs[1].seq, evs[1].ts, evs[1].type, {"i": 99}, evs[1].prev_hash, evs[1].hash)
    assert verify_events([evs[0], forged, *evs[2:]]) == (False, 2)


# ---- device & graph -----------------------------------------------------------------------------
def test_device_has_23_fasteners_and_valid_task_graph():
    d = demo_laptop()
    assert len(d.fasteners()) == 23
    assert len(set(d.step_of_part)) == len(d.parts)  # every part is removed by exactly one step
    assert {"base_screw", "battery_screw", "ssd_screw", "hinge_screw", "fan_screw", "wifi_screw"} <= set(d.classes())


def test_next_step_follows_task_graph():
    s, b = fresh()
    assert s.graph.next_step()["id"] == "t01"
    b.say_step("t01")
    assert s.graph.next_step()["id"] == "t02"


def test_phase_progression():
    s, b = fresh()
    assert s.graph.phase() == Phase.SEALED
    b.say_step("t01")
    b.remove("base_screw_01")
    assert s.graph.phase() == Phase.OPENED


# ---- safety kernel ------------------------------------------------------------------------------
def test_removal_without_esd_or_power_off_is_blocked_and_recorded():
    s, b = fresh()
    b.remove("base_screw_01")  # no ESD strap
    assert any(x.type == "safety_violation" for x in s.graph.exceptions.values())
    assert any(a.rule == "K1_ESD" for a in b.alerts)


def test_skipping_battery_step_raises_k2():
    s, b = fresh()
    for t in ("t01", "t02", "t03"):
        b.teardown_step(t)
    b.remove("ssd_screw_01")
    assert any(a.rule == "K2_POWER_OFF" for a in b.alerts)
    assert not s.guard(safety.Action("remove", "ssd")).allowed


def test_pry_near_connected_battery_denied_until_power_off():
    s, b = fresh()
    assert not s.guard(safety.Action("pry", near="battery")).allowed
    b.say_step("t04")  # out of order, but records power_off
    assert s.guard(safety.Action("pry", near="battery")).allowed


def test_hazard_halts_everything_until_technician_clears():
    s, b = fresh()
    b.say_step("t01")
    s.report_hazard("swelling", b.t)
    assert s.graph.phase() == Phase.EXCEPTION
    assert not s.guard(safety.Action("remove", "base_screw_01")).allowed
    assert safety.check(s.graph, safety.Action("remove", "base_screw_01")).rule == "K3_HAZARD_HALT"
    s.clear_hazard(b.t, "battery cooled, swelling was a shadow")
    assert s.guard(safety.Action("remove", "base_screw_01")).allowed


def test_agent_has_no_way_to_change_the_kernel():
    assert not hasattr(safety, "disable") and not hasattr(safety, "allow")
    assert isinstance(safety._RULES, tuple)


# ---- memory -------------------------------------------------------------------------------------
def test_dropped_screw_becomes_missing_with_low_latency():
    s, b = fresh()
    for t in ("t01", "t02", "t03"):
        b.teardown_step(t)
    b.say_step("t04")
    b.drop("ssd_screw_01")
    b.run(5)
    assert s.graph.missing_parts() == ["ssd_screw_01"]
    x = next(x for x in s.graph.exceptions.values() if x.type == "missing_part")
    assert x.ts - b.truth_log[0]["t_left"] <= 5.0


def test_state_survives_restart_from_the_log_alone():
    s, b = fresh()
    for t in ("t01", "t02", "t03"):
        b.teardown_step(t)
    b.say_step("t04")
    b.drop("ssd_screw_01")
    b.run(5)
    s2 = Session(s.device, s.log)
    assert s2.graph.missing_parts() == ["ssd_screw_01"]
    assert s2.graph.power_off and s2.graph.esd_on
    assert s2.recap()["parts_out"] == s.recap()["parts_out"]
    assert s2.track_map == s.track_map


def test_found_screw_is_reidentified_after_tracker_loses_it():
    s, b = fresh()
    for t in ("t01", "t02", "t03"):
        b.teardown_step(t)
    b.say_step("t04")
    b.drop("ssd_screw_01")
    b.run(5)
    b.find("ssd_screw_01", "tray_3")
    assert s.graph.parts["ssd_screw_01"].state == PartState.REMOVED
    assert not s.graph.open_exceptions()


def test_unknown_object_is_an_extra_part():
    s, b = fresh()
    b.add_extra()
    b.run(1)
    assert any(x.type == "extra_part" for x in s.graph.exceptions.values())


def test_wrong_fastener_is_caught_at_install_and_resolves_when_corrected():
    s, b = fresh()
    b.say_step("t01")
    b.remove("base_screw_01")
    b.install("base_screw_01", hole=s.device.parts["hinge_screw_01"].hole)
    assert any(x.type == "wrong_fastener" for x in s.graph.open_exceptions())
    b.remove("base_screw_01")
    b.install("base_screw_01", hole=s.device.parts["base_screw_01"].hole)
    assert not [x for x in s.graph.open_exceptions() if x.type == "wrong_fastener"]


def test_manual_tap_fallback_uses_the_same_policy():
    s, _ = fresh()
    alerts = s.observe_manual("base_screw_01", "tray_1", 1.0)  # no ESD strap
    assert any(a.kind == "safety_violation" for a in alerts)


# ---- invariants & passport ----------------------------------------------------------------------
def test_passport_refused_while_invariants_fail():
    b = chaos_session(1, frozenset({"drop"}), p_dropout=0, p_churn=0, boot_ok=False)
    ok, reasons = invariants.can_close(b.session.graph)
    assert not ok and any(r.startswith("function") for r in reasons)
    with pytest.raises(passport.PassportRefused):
        passport.issue(b.session, "tech", passport.Signer.generate(), b.t)


def test_hero_demo_ends_in_a_verifiable_passport():
    log = EventLog()
    b = None
    for _, b in hero_demo(log):
        pass
    signer = passport.Signer.generate()
    p = passport.issue(b.session, "tech_a", signer, b.t + 1)
    assert p["body"]["counts"]["fasteners_accounted"] == 23
    assert p["body"]["counts"]["extra_parts"] == 0
    assert passport.verify(p, log.events()) == (True, [])


def test_forged_passport_and_truncated_log_fail_verification():
    log = EventLog()
    for _, b in hero_demo(log):
        pass
    p = passport.issue(b.session, "tech_a", passport.Signer.generate(), b.t + 1)
    forged = copy.deepcopy(p)
    forged["body"]["counts"]["fasteners_accounted"] = 24
    assert not passport.verify(forged)[0]
    assert not passport.verify(p, log.events()[:-30])[0]


def test_technician_override_is_recorded_on_the_passport():
    b = chaos_session(2, frozenset({"skip_battery"}), p_dropout=0, p_churn=0)
    s = b.session
    for x in list(s.graph.open_exceptions()):
        s.resolve_exception(x.id, b.t, "I confirm the battery was never live")
    p = passport.issue(s, "tech", passport.Signer.generate(), b.t)
    assert all(e["note"] for e in p["body"]["exceptions"] if e["resolved_by"] == "technician")


# ---- agents -------------------------------------------------------------------------------------
def test_deterministic_agent_answers_from_the_graph():
    s, b = fresh()
    a = DeterministicAgent()
    assert "ESD" in a.respond(s, "what's next?").text
    assert a.respond(s, "am I done?").text.startswith("Not yet")


class ScriptedClient:
    def __init__(self, calls):
        self.calls = list(calls)

    def complete(self, messages, tools):
        return self.calls.pop(0)


def test_wonder_agent_cannot_propose_an_illegal_step():
    s, _ = fresh()
    client = ScriptedClient([
        {"tool": "propose_step", "args": {"step_id": "t05"}},  # SSD removal: not legal yet
        {"tool": "get_next_steps", "args": {}},
        {"tool": "propose_step", "args": {"step_id": "t01"}},
    ])
    reply = WonderAgent(client).respond(s, "what next?")
    assert reply.text == "Put on the ESD strap."


# ---- perception ---------------------------------------------------------------------------------
class FakeSam:
    def track(self, image, prompts):
        return [
            RawTrack("a", "hinge screw", (95, 95, 105, 105), 0.9),
            RawTrack("b", "hinge screw", (10, 10, 20, 20), 0.9),
            RawTrack("c", "hinge screw", (300, 300, 310, 310), 0.9),
            RawTrack("h", "hand", (290, 290, 330, 330), 0.9),
        ]


def test_zone_map_assigns_hand_tray_device_and_bench():
    zones = ZoneMap(trays={"tray_4": (0, 0, 50, 50)}, device=(80, 80, 200, 200))
    p = Sam31Perception(FakeSam(), zones, {"hinge screw": "hinge_screw"})
    f = p.frame("f1", 0.0, b"")
    assert {d.track_id: d.zone for d in f.detections} == {"a": "device", "b": "tray_4", "c": "hand"}
