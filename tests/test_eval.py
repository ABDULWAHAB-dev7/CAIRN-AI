import json

from cairn.evaluation import QUIET, record_session, run_eval, score


def test_recording_replays_to_the_identical_event_log(tmp_path):
    d = record_session(tmp_path, 5, frozenset({"drop", "skip_battery"}), QUIET, "two faults")
    assert {p.name for p in d.iterdir()} >= {"frames.jsonl", "actions.json", "truth.json", "meta.json"}
    r = score(d)
    assert r["reproduces_recording"] and r["chain_ok"]
    assert r["caught"] == {"skip_battery": True, "drop": True} and r["missing_latency_s"][0] <= 5


def test_run_eval_scores_an_existing_directory_of_recordings(tmp_path):
    record_session(tmp_path, 1, frozenset(), QUIET, "clean")
    record_session(tmp_path, 8, frozenset({"extra_part"}), QUIET, "stray")
    report = run_eval(plan=None, out=tmp_path / "m" / "metrics.json", sessions_dir=tmp_path)
    assert len(report["runs"]) == 2 and report["metrics"]["replay_reproduces_recording"]
    stray = next(r for r in report["runs"] if r["run"] == 8)
    assert stray["blocked_by_design"] and not stray["can_close"]
    assert json.loads((tmp_path / "m" / "metrics.json").read_text())["synthetic"] is True
    assert "Imperfections" in (tmp_path / "m" / "report.md").read_text(encoding="utf-8")
