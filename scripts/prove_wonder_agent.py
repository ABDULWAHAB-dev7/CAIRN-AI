"""Live check of the Muse Wonder tool-calling loop (the path WonderAgent uses), against a fresh simulated session.

Needs MODEL_API_KEY (else META_API_KEY). Saves the full request/response transcript, with the key never written, to
docs/proof/meta/wonder-agent-loop.json. Usage (repo root):  python scripts/prove_wonder_agent.py .
"""
import datetime
import json
import sys
from pathlib import Path

repo = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
sys.path.insert(0, str(repo))

from cairn.agent import WonderAgent  # noqa: E402
from cairn.device import demo_laptop  # noqa: E402
from cairn.meta_api import MetaClient, WonderClient  # noqa: E402
from cairn.session import Session  # noqa: E402

transcript = []


class LoggingClient(MetaClient):
    def responses(self, body):
        t = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            resp = super().responses(body)
            transcript.append({"at_utc": t, "request": body, "response": resp})
            return resp
        except Exception as e:  # keep failures in the record
            transcript.append({"at_utc": t, "request": body, "error": f"{type(e).__name__}: {e}"})
            raise


session = Session(demo_laptop())  # sealed device: the only legal first step is "Put on the ESD strap"
events_before = len(session.log)
agent = WonderAgent(WonderClient(LoggingClient()))
outcome = {}
try:
    reply = agent.respond(session, "What should I do next?")
    outcome = {"ok": True, "reply_text": reply.text, "source": reply.source}
except Exception as e:
    outcome = {"ok": False, "error": f"{type(e).__name__}: {e}"}

legal = [s["id"] for s in session.graph.valid_next_steps()]
tool_calls = [it for t in transcript for it in (t.get("response") or {}).get("output", []) if it.get("type") == "function_call"]
result = {
    "outcome": outcome, "legal_steps_at_start": legal, "rounds": len(transcript),
    "tool_calls_made": [{"name": c.get("name"), "arguments": c.get("arguments"), "call_id": c.get("call_id")} for c in tool_calls],
    "events_before": events_before, "events_after": len(session.log),
    "graph_unchanged_by_model": len(session.log) == events_before,  # the model has no tool that writes
    "transcript": transcript,
}
out = repo / "docs" / "proof" / "meta"
out.mkdir(parents=True, exist_ok=True)
(out / "wonder-agent-loop.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps({k: v for k, v in result.items() if k != "transcript"}, indent=2))
