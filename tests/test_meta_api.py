import json

from cairn.agent import WONDER_TOOLS, WonderAgent
from cairn.meta_api import MetaClient, Sam31Backend, WonderClient, parse_segmentation, to_function_tools
from cairn.session import Session
from cairn.device import demo_laptop

SAMPLE = (
    "<0f>0<|box;x1=211;y1=228;x2=270;y2=254;w=320;h=334;c=0.97|>"
    "<|mask;x=0;y=0;c=0.9;data=27,60,~!!!!M!0c[0o91w?q1|pIH4pPRVp2B3'7|>"
    ",2<|box;x1=155;y1=228;x2=202;y2=254;w=320;h=334;c=0.5|><|mask;x=0;y=0;data=2,2,~abc|>"
)


def test_parse_segmentation_reads_boxes_and_skips_masks():
    got = parse_segmentation(SAMPLE)
    assert got == [(0, 0, (211.0, 228.0, 270.0, 254.0), 0.97), (0, 2, (155.0, 228.0, 202.0, 254.0), 0.5)]


def test_parse_segmentation_handles_video_frames_and_missing_confidence():
    text = "<0f>0<|box;x1=1;y1=2;x2=3;y2=4;w=9;h=9|><|mask;x=0;y=0;data=1,1,~a|>\n<3f>0<|box;x1=5;y1=6;x2=7;y2=8;w=9;h=9|><|mask;x=0;y=0;data=1,1,~a|>"
    assert [(f, o, c) for f, o, _, c in parse_segmentation(text)] == [(0, 0, 1.0), (3, 0, 1.0)]


def test_tools_become_flat_function_tools():
    t = to_function_tools(WONDER_TOOLS)[2]
    assert t["type"] == "function" and t["name"] == "part_status"
    assert t["parameters"]["required"] == ["part_id"] and t["parameters"]["additionalProperties"] is False


def test_sam_backend_sends_one_request_per_prompt_with_image_and_confidence():
    sent = []

    def transport(path, body, stream):
        sent.append((path, body, stream))
        return SAMPLE

    tracks = Sam31Backend(MetaClient(transport=transport)).track(b"\xff\xd8img", ["hinge screw", "hand"])
    assert [s[0] for s in sent] == ["/responses", "/responses"] and all(s[2] for s in sent)
    parts = sent[0][1]["input"][0]["content"]
    assert parts[0] == {"type": "input_text", "text": "hinge screw"}
    assert parts[1]["image_url"].startswith("data:image/jpeg;base64,")
    assert sent[0][1]["metadata"] == {"include_confidence": "true"} and sent[0][1]["model"] == "sam-3.1"
    assert len(tracks) == 4 and tracks[0].track_id == "hinge screw:0" and tracks[0].score == 0.97


def test_wonder_round_trip_uses_previous_response_id_and_call_id():
    sent = []
    script = [
        {"id": "resp_1", "output": [{"type": "function_call", "name": "get_next_steps", "arguments": "{}", "call_id": "call_9"}]},
        {"id": "resp_2", "output": [{"type": "function_call", "name": "propose_step", "arguments": json.dumps({"step_id": "t01"}), "call_id": "call_10"}]},
    ]

    def transport(path, body, stream):
        sent.append(body)
        return script.pop(0)

    s = Session(demo_laptop())
    reply = WonderAgent(WonderClient(MetaClient(transport=transport))).respond(s, "what next?")
    assert reply.text == "Put on the ESD strap." and reply.source == "wonder"
    assert sent[0]["model"] == "muse-wonder-1.0" and "instructions" in sent[0] and sent[0]["input"] == "what next?"
    assert sent[1]["previous_response_id"] == "resp_1"
    assert sent[1]["input"][0]["type"] == "function_call_output" and sent[1]["input"][0]["call_id"] == "call_9"


def test_wonder_text_answer_is_returned():
    def transport(path, body, stream):
        return {"id": "r", "output": [{"type": "message", "content": [{"type": "output_text", "text": "Hello."}]}]}

    assert WonderClient(MetaClient(transport=transport)).complete(
        [{"role": "system", "content": "s"}, {"role": "user", "content": "hi"}], WONDER_TOOLS) == {"text": "Hello."}
