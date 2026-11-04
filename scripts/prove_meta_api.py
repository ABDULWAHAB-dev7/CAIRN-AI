"""One live Muse Wonder call and one live SAM 3.1 call. Saves redacted request, raw response, status and time
under docs/proof/meta/. The key (MODEL_API_KEY, else META_API_KEY) is read from the environment and never printed
or written. The SAM input is a rendered frame from the bench SIMULATOR, not a real bench: a successful call proves
the wiring and the parser, not perception.

Usage (repo root):  python scripts/prove_meta_api.py . [sam-prompt]      (default prompt: "screw")
Each SAM prompt is saved as its own artefact set (sam-<prompt>.*) so failed attempts are kept, not overwritten.
"""
import base64
import datetime
import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

repo = Path(sys.argv[1])
out = repo / "docs" / "proof" / "meta"
out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(repo))

name = next((n for n in ("MODEL_API_KEY", "META_API_KEY") if os.environ.get(n)), None)
if not name:
    sys.exit("no key in MODEL_API_KEY or META_API_KEY")
KEY = os.environ[name]
BASE = "https://api.meta.ai/v1"


def post(path, body, stream=False, timeout=60):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    started = datetime.datetime.now(datetime.timezone.utc)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return started, r.status, dict(r.headers), raw
    except urllib.error.HTTPError as e:
        return started, e.code, dict(e.headers), e.read().decode("utf-8", "replace")
    except OSError as e:
        return started, 0, {}, f"network error: {e}"


def redact_headers(h):
    return {k: ("[redacted]" if k.lower() in ("set-cookie", "authorization") else v) for k, v in h.items()}


def save(tag, request_body, started, status, headers, raw, extra=None):
    meta = {
        "called_at_utc": started.isoformat(), "env_var_used": name, "endpoint": BASE + "/responses",
        "http_status": status, "request_authorization": "Bearer [redacted]", "request_body": request_body,
        "response_headers": redact_headers(headers), **(extra or {}),
    }
    (out / f"{tag}.request-and-status.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    (out / f"{tag}.response.raw.txt").write_text(raw, encoding="utf-8")
    return meta


results = {}

# ---- Muse Wonder: one short prompt ------------------------------------------------------------
body = {"model": "muse-wonder-1.0", "input": "Reply with exactly one word: ok", "stream": False}
t, st, hd, raw = post("/responses", body)
save("wonder", body, t, st, hd, raw)
results["wonder"] = st
print("wonder http", st, "|", raw[:160].replace("\n", " "))

# ---- SAM 3.1: one still image (a rendered simulator frame: NOT a real bench) -------------------
from PIL import Image  # noqa: E402

from cairn.frames import render_png  # noqa: E402
from cairn.scenarios import hero_demo  # noqa: E402

frame_row, sess = None, None
for label, b in hero_demo():
    if label == "cover_off":
        sess = b.session
        frame_row = {"detections": []}
        # find the latest frame's detections from the bench truth: re-render via the simulator's own frame
        from cairn.session import Detection  # noqa
        dets = []
        for pid, spec in sess.device.parts.items():
            if pid in b.gone or b._hidden(pid):
                continue
            x, y = b.xy[pid]
            r = 8 if spec.kind == "fastener" else 26
            dets.append({"track_id": pid, "cls": spec.cls, "zone": b.truth[pid], "box": [x - r, y - r, x + r, y + r],
                         "well": spec.well if b.truth[pid] == spec.tray else None})
        frame_row = {"detections": dets}
        break
png = render_png(frame_row, sess)
img = Image.open(io.BytesIO(png)).convert("RGB")
buf = io.BytesIO()
img.save(buf, "JPEG", quality=88)
jpg = buf.getvalue()
(out / "sam_input.jpg").write_bytes(jpg)
assert len(jpg) < 2_000_000
prompt = sys.argv[2] if len(sys.argv) > 2 else "screw"
slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower()).strip("-")
data_url = "data:image/jpeg;base64," + base64.b64encode(jpg).decode()
body = {"model": "sam-3.1", "metadata": {"include_confidence": "true"}, "stream": True,
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": prompt}, {"type": "input_image", "image_url": data_url}]}]}
t, st, hd, raw = post("/responses", body, stream=True)
redacted = json.loads(json.dumps(body))
redacted["input"][0]["content"][1]["image_url"] = (
    f"data:image/jpeg;base64,[{len(jpg)} bytes, sha256 {hashlib.sha256(jpg).hexdigest()[:16]}..., see sam_input.jpg]")
save(f"sam-{slug}", redacted, t, st, hd, raw, {"image": {"file": "sam_input.jpg", "bytes": len(jpg),
     "sha256": hashlib.sha256(jpg).hexdigest(),
     "what_it_is": "a rendered frame from the bench SIMULATOR, not a photograph of a real bench"}})
results["sam"] = st
print("sam http", st, "| raw bytes", len(raw))

# ---- parse deltas and draw an overlay ----------------------------------------------------------
deltas = []
for line in raw.splitlines():
    line = line.strip()
    if line.startswith("data:") and line != "data: [DONE]":
        try:
            ev = json.loads(line[5:])
        except ValueError:
            continue
        if ev.get("type") == "response.output_text.delta":
            deltas.append(ev.get("delta", ""))
text = "".join(deltas)
(out / f"sam-{slug}.output_text.txt").write_text(text, encoding="utf-8")
from cairn.meta_api import parse_segmentation  # noqa: E402

try:
    boxes = parse_segmentation(text)
except Exception as e:  # a parser failure is itself a finding
    boxes = []
    print("PARSER ERROR:", type(e).__name__, e)
print("sam boxes parsed:", len(boxes))
overlay = img.copy()
from PIL import ImageDraw  # noqa: E402

d = ImageDraw.Draw(overlay)
for frame, oid, box, conf in boxes:
    d.rectangle(box, outline="#ab8ff1", width=2)
    d.text((box[0], max(0, box[1] - 12)), f"id{oid} {conf:.2f}", fill="#dad7de")
overlay.save(out / f"sam-{slug}.overlay.png")
(out / f"summary-{slug}.json").write_text(json.dumps({
    "wonder_http": results["wonder"], "sam_http": results["sam"], "sam_boxes_parsed": len(boxes),
    "sam_prompt": prompt, "image_is_simulator_render": True}, indent=2), encoding="utf-8")
print("saved to", out)
