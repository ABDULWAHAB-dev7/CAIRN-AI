"""The explainer's script and its scene code must stay in step, and its honesty beats must stay in."""
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "explainer"
SCRIPT = json.loads((HERE / "script.json").read_text(encoding="utf-8"))
SCENES_JS = (HERE / "scenes.js").read_text(encoding="utf-8")


def test_every_scripted_scene_has_scene_code_and_the_reverse():
    ids = [s["id"] for s in SCRIPT["scenes"]]
    assert len(ids) == len(set(ids))
    coded = re.findall(r"^S\.(\w+) = \{", SCENES_JS, re.M)
    assert ids == coded, f"script and scenes.js disagree: {ids} vs {coded}"


def test_lines_are_short_enough_to_speak_and_the_cut_is_not_an_hour_long():
    words = 0
    for s in SCRIPT["scenes"]:
        assert s["lines"], s["id"]
        for line in s["lines"]:
            n = len(line.replace("**", "").split())
            assert 3 <= n <= 45, f"{s['id']}: {line!r} is {n} words"
            assert line.count("**") % 2 == 0, f"unbalanced ** in {line!r}"
            words += n
    assert words <= 1150, f"{words} words is more than about 6 minutes of narration at the default speaking rate"


def test_the_honest_beats_are_in_the_script():
    text = " ".join(l for s in SCRIPT["scenes"] for l in s["lines"]).lower()
    for must in ("simulated", "not proven", "billing", "no real bench test", "no local model has been run", "no battery"):
        assert must in text.replace("**", ""), must
    # no exact test count in the voice: it would be stale as soon as a test is added
    assert "more than a hundred automated tests" in text and not re.search(r"\d{3}", text)


def test_the_voice_script_and_the_build_agree_on_the_lines():
    build = (HERE / "build.py").read_text(encoding="utf-8")
    assert "--audio-dir" in build and "tts.ps1" in build
    assert (HERE / "tts.ps1").exists() and (HERE / "stage.html").exists() and (HERE / "engine.js").exists()
