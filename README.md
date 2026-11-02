# Cairn

**Object permanence for physical work.** Cairn watches a repair bench, gives every part a persistent identity, remembers the teardown across time, catches missing, wrong or out-of-order parts, and ends with a signed, independently verifiable repair passport.

The full plan is in [`docs/Cairn-Project-Blueprint.pdf`](docs/Cairn-Project-Blueprint.pdf). This repo is the build.

```bash
pip install -e ".[dev]"
python -m pytest          # 48 tests
cairn demo                # scripted hero demo -> out/passport.json, passport.html, repair.db
cairn verify out/passport.json --db out/repair.db
cairn eval                # blueprint section 13 metrics on simulated sessions
```

## Backend

```bash
pip install -e ".[server,pdf]"
cairn serve --port 8000        # interactive docs at /docs
```

| Route | Purpose |
|---|---|
| `POST /sessions`, `GET /sessions`, `GET /sessions/{id}` | create / list / snapshot (parts, invariants, exceptions, next step) |
| `POST /sessions/{id}/frames` · `/image` · `/taps` | perception in: detections, a raw camera image (needs SAM), or a human tap |
| `POST /sessions/{id}/steps` · `/hazard` · `/boot-test` · `/exceptions/{x}/resolve` · `/parts/{p}/retire` | spoken or tapped actions and technician decisions |
| `POST /sessions/{id}/ask` · `/guard`, `GET /queries/{name}` | agent answers, safety pre-checks, the three product queries |
| `GET /sessions/{id}/events` · `/stream` | audit log with chain check; live server-sent events |
| `POST /sessions/{id}/passport`, `GET .../passport[.html\|.pdf]`, `POST /verify` | gated, idempotent signing; stateless verification |
| `POST /demo` | run the scripted hero demo into a new session |

Sessions persist as one SQLite file each and reload on restart. Configuration is by environment:
`CAIRN_DATA_DIR`, `CAIRN_API_TOKEN` (Bearer auth on everything but `/health`),
`CAIRN_AGENT=deterministic|wonder|glimmer`, `CAIRN_PERCEPTION=none|sam` + `CAIRN_ZONES`,
`CAIRN_LOCAL_URL`/`CAIRN_LOCAL_MODEL` for Glimmer, and `CAIRN_PRIVACY=local`, which refuses to start
with any component that would send bench video or prompts to a cloud API. If an LLM agent errors,
answers fall back to the graph agent instead of failing.

## Status against the blueprint

| Blueprint piece | State |
|---|---|
| Append-only, hash-chained event log (SQLite, UPDATE/DELETE blocked) | built, tested |
| Object graph, task graph, repair state machine, the three product queries | built, tested |
| Safety kernel (ESD, power-off, hazard halt, no pry near battery); the agent can only explain it | built, tested |
| Verification invariants (count, order, safety, closure, function) and passport gate | built, tested |
| Passport: Ed25519-signed JSON + HTML + PDF, verifiable against the event log | built, tested |
| Identity/re-ID reconciler (track churn, dropout, lost-part recovery), restart from log alone | built, tested |
| Human-confirmed tap fallback (same policy as perception) | built |
| Agent: deterministic graph agent, plus Muse Wonder tool loop that can only propose legal steps | built, tested |
| Meta Model API clients (`cairn/meta_api.py`): Wonder via Responses API function calls, SAM 3.1 via token-stream parser | built from the public docs, tested offline; **live calls not yet run** |
| Perception: `ZoneMap` (pixels to tray/device/hand), `Sam31Perception` adapter, frame replay | built, tested |
| Eval harness (recall, ID switches, missing-part latency, fault catch, false alarms) | built, **synthetic data only** |
| HTTP backend (`cairn serve`): sessions, ingest, agent, SSE, passport, auth, persistence | built, tested; smoke-tested over real HTTP |
| Glimmer local agent (OpenAI-compatible chat API, privacy mode) | built, tested against a fake; no Glimmer model run yet |
| Voice (Muse Voice), Muse Image passport art | not started |
| Replay UI (`web/`, deployed on Vercel): timeline, part map, passport | built; static replay of the simulated demo |
| Live camera overlay (canvas, Next.js) | not started |
| Passport PDF export (needs `pip install -e ".[pdf]"`) | built, tested |

## What is not proven yet

- **Day 1 kill test.** Nobody has run SAM 3.1 on a real bench. The simulator in `cairn/scenarios.py` produces the detections SAM would, with injected dropout and track-id churn, so the memory and safety layers can be tested. It says nothing about real perception.
- **The eval numbers are simulated.** `cairn eval` prints a table, but until it is fed recorded clips it demonstrates the harness, not the product.
- **Live API calls.** `cairn/meta_api.py` follows https://dev.meta.ai/docs (base `https://api.meta.ai/v1`, Bearer auth, key in `MODEL_API_KEY` or `META_API_KEY`) but has only run against fake transports. Image requests give per-call object ids; stable video ids come after the kill test.
- **Passport trust.** The signature proves the record was not altered. Tying a key to a real shop needs a key registry.

## Layout

```
cairn/events.py      hash-chained event log          cairn/safety.py      safety kernel
cairn/device.py      curated task graph (23 screws)  cairn/invariants.py  verification invariants
cairn/graph.py       object graph (event projection) cairn/passport.py    sign / verify / render
cairn/session.py     reconciler + policy             cairn/agent.py       graph agent + Wonder loop
cairn/perception.py  zones, SAM adapter, replay      cairn/scenarios.py   bench simulator, hero demo
cairn/evaluation.py  metrics                         tests/               48 tests
```

Design rule: the model never writes to the graph. Perception proposes detections, the session decides, the log records, and the passport only issues when every invariant holds.
