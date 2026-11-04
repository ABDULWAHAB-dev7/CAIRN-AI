"""The demo video's plan: it must stay under three minutes, every shot says what it shows, and the disclosure is on screen."""
import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("playwright")
pytest.importorskip("PIL")

_spec = importlib.util.spec_from_file_location("make_demo_video", Path(__file__).resolve().parents[1] / "scripts" / "make_demo_video.py")
video = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(video)


def test_cut_fits_three_minutes_and_the_clip_fits_thirty_seconds():
    assert sum(s["secs"] for s in video.SHOTS) <= 180
    assert sum(s["clip"] for s in video.SHOTS if s.get("clip")) <= 30


def test_shots_are_unique_and_captioned_unless_they_are_cards():
    ids = [s["id"] for s in video.SHOTS]
    assert len(ids) == len(set(ids))
    for s in video.SHOTS:
        assert s["kind"] in ("card", "bench", "modal", "page", "image")
        assert s["caption"] or s["kind"] == "card", s["id"]
        assert len(s["caption"]) <= 120, f"{s['id']}: caption too long to read in {s['secs']} s"
        assert s["secs"] >= 4


def test_disclosure_is_on_the_first_frame_and_on_every_bench_frame():
    assert "simulated" in video.CARDS["title"].lower() and "Meta billing" in video.CARDS["title"]
    assert "SIMULATED REPLAY" in video.REPLAY
    assert "Not proven" in video.CARDS["truth"] and "Simulated" in video.CARDS["truth"]
    # a bench or modal shot that sets its own label would drop the disclosure
    assert all("label" not in s for s in video.SHOTS if s["kind"] in ("bench", "modal"))
