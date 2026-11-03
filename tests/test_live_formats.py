"""The Meta clients, checked against REAL responses saved on 2026-11-02 (docs/proof/meta/), not hand-written fakes.

These do not call the network. They fail if the parser or the Wonder adapter drifts from what the live API returned.
Caveat: the SAM image was a bench-simulator render, so this proves the wire format, not detection quality on real parts.
"""
import json
from pathlib import Path

import pytest

from cairn.meta_api import MetaClient, WonderClient, parse_segmentation

PROOF = Path(__file__).resolve().parents[1] / "docs" / "proof" / "meta"
needs_proof = pytest.mark.skipif(not (PROOF / "sam-rectangle.output_text.txt").exists(), reason="proof artefacts absent")


@needs_proof
def test_sam_live_output_parses_into_boxes_inside_the_image():
    text = (PROOF / "sam-rectangle.output_text.txt").read_text(encoding="utf-8")
    boxes = parse_segmentation(text)
    assert len(boxes) == 6
    for frame, obj_id, (x1, y1, x2, y2), conf in boxes:
        assert frame == 0 and isinstance(obj_id, int)
        assert 0 <= x1 < x2 <= 960 and 0 <= y1 < y2 <= 600  # w=960, h=600 in the tokens: source pixels, no rescaling
        assert 0.0 < conf <= 1.0


@needs_proof
def test_sam_live_square_run_has_one_box_per_mask_and_unique_object_ids():
    text = (PROOF / "sam-square.output_text.txt").read_text(encoding="utf-8")
    boxes = parse_segmentation(text)
    assert len(boxes) == text.count("<|mask;") == 44
    assert len({oid for _, oid, _, _ in boxes}) == 44


@needs_proof
def test_wonder_adapter_reads_the_live_text_response_with_its_reasoning_item():
    live = json.loads((PROOF / "wonder.response.raw.txt").read_text(encoding="utf-8"))
    assert [i["type"] for i in live["output"]] == ["reasoning", "message"]
    assert WonderClient(MetaClient(transport=lambda *a: live))._parse(live) == {"text": "ok"}


@needs_proof
def test_wonder_adapter_reads_the_live_function_calls_and_the_loop_stays_legal():
    loop = json.loads((PROOF / "wonder-agent-loop.json").read_text(encoding="utf-8"))
    assert loop["outcome"] == {"ok": True, "reply_text": "Put on the ESD strap.", "source": "wonder"}
    assert [c["name"] for c in loop["tool_calls_made"]] == ["get_next_steps", "propose_step"]
    assert loop["graph_unchanged_by_model"] is True and loop["legal_steps_at_start"] == ["t01"]
    first, second = loop["transcript"]
    wc = WonderClient(MetaClient())
    assert wc._parse(first["response"]) == {"tool": "get_next_steps", "args": {}}
    assert wc._parse(second["response"]) == {"tool": "propose_step", "args": {"step_id": "t01"}}
    assert second["request"]["previous_response_id"] == first["response"]["id"]  # the documented tool-result handshake
    assert second["request"]["input"][0]["type"] == "function_call_output"
