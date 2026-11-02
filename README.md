# Cairn

**Object permanence for physical work.** Cairn watches a repair bench, gives every part a persistent identity, remembers the teardown across time, catches missing, wrong or out-of-order parts, and ends with a signed, independently verifiable repair passport.

The full plan is in [`docs/Cairn-Project-Blueprint.pdf`](docs/Cairn-Project-Blueprint.pdf). This repo is the build.

## Run it

```bash
docker compose up                  # http://localhost:8000  (Docker build not yet tested; see docs/BENCH_SETUP.md)
# or
pip install -e ".[server,dev]"
cairn serve                        # http://localhost:8000
```

Open it, choose **Jobs → Replay the scripted demo**, and click any timeline entry. No camera needed.

```bash
python -m pytest                   # 68 tests
cairn demo                         # scripted hero demo -> out/passport.{json,html,pdf}, repair.db
cairn verify out/passport.json --db out/repair.db
cairn eval                         # records 10 simulated sessions, replays and scores them -> eval/report.md
```

## Hosted replay

`python scripts/export_static.py` builds `site/`, a read-only static copy of the bench screen replaying the simulated demo
(real rendered frames, real state at every event, the signed passport). It is what is deployed at
https://cairn-ai-eta.vercel.app. The live backend is not on Vercel: it needs a persistent disk and a long-lived
event stream, so run it with Docker or on a host that offers both.

## Design

The front end follows the "aurora behind smoked glass" reference: a near-black void, pearl type, one violet signal, depth from surface value rather than shadow, 3px buttons and inputs, 10px cards, light-on-dark primary buttons. Tokens live in `cairn/ui/tokens.css` (the display face is self-hosted Inter Tight, a substitute for Overused Grotesk). `/` is the landing page, `/bench` the working screen. The rendered camera frames use the same palette. One deliberate deviation from the reference: critical safety states and missing parts use a single muted red, because colour is the fastest signal on a safety stop. A test (`test_pages_use_only_the_design_palette`) keeps both pages inside the palette.

## The bench screen

One view, not a chat window (`cairn/ui/bench.html`, served at `/`):

- **Centre:** the live bench feed with thin outlines and tiny labels, e.g. `p_04 · hinge screw · tray 04`. Camera mode overlays them on the video; server mode draws the bench.
- **Top strip:** `REMOVED · ACCOUNTED · MISSING · STATE`.
- **Left:** the 24-well tray map. The correct well pulses once when a part is misplaced.
- **Bottom left:** the next-step card, one instruction and one reason. It turns red on a safety violation.
- **Bottom right:** the timeline. Click any event to see that moment's frame and the whole screen as it was.
- **Voice bar:** push to talk (hold the button or Space) or an open mic, in a Chromium browser. Spoken alerts. A manual-input drawer covers everything the camera cannot see (ESD strap, battery disconnect, boot test) and works with no camera at all.
- **Close job:** runs the invariants and either blocks the close, produces the passport, or, if the technician writes down what they are accepting, stamps it `CLOSED WITH EXCEPTIONS`.

## Backend

Interactive docs at `/docs`. Sessions persist as one SQLite file each and reload on restart.

| Route | Purpose |
|---|---|
| `POST /sessions` (device, job number, technician), `GET /sessions[/{id}]` | start a job (snapshots the sealed device), list, snapshot |
| `POST /sessions/{id}/frames` · `/image` · `/taps` · `/baseline` | perception in: detections, a camera image (needs SAM), a human tap, the baseline picture |
| `POST /sessions/{id}/steps` · `/hazard` · `/boot-test` · `/exceptions/{x}/resolve` · `/parts/{p}/retire` | spoken or tapped actions and technician decisions |
| `POST /sessions/{id}/ask` · `/guard`, `GET /queries/{name}` | agent answers, safety pre-checks, the product queries |
| `GET /sessions/{id}/timeline` · `/at/{seq}` · `/frames/{id}.png` · `/events` · `/stream` | what the screen shows; state at any event; frames; audit log; live events |
| `POST /sessions/{id}/close`, `GET .../passport[.html\|.pdf]`, `POST /verify`, `GET /v/{id}` | close job; fetch the passport; stateless verify; the public page the QR opens |

Environment: `CAIRN_DATA_DIR`, `CAIRN_API_TOKEN` (Bearer auth on everything except `/health`, `/v/{id}` and the page),
`CAIRN_AGENT=deterministic|wonder|glimmer`, `CAIRN_PERCEPTION=none|sam` (+ `CAIRN_ZONES`), `MODEL_API_KEY`,
`CAIRN_LOCAL_URL`/`CAIRN_LOCAL_MODEL`, `CAIRN_PUBLIC_URL`, and `CAIRN_PRIVACY=local`, which refuses to start with any
component that would send bench images or prompts to a cloud API. If an LLM agent errors, answers fall back to the graph agent.

## The passport

One A4 page (PDF) plus the JSON behind it: status line (`VERIFIED` or `CLOSED WITH EXCEPTIONS`), device, job number,
technician, bench, start and end, parts removed / reinstalled / retired with counts that reconcile, every exception
with how it was resolved, four to six evidence frames (each SHA-256-pinned inside the signed body), safety checks,
the functional test, a QR code to the public verify page, and the hash chain over the event log. Ed25519-signed;
`cairn verify` and `POST /verify` check the signature, the evidence images and the chain.

## Status against the end state

| Piece | State |
|---|---|
| Event log, object graph, task graph, safety kernel, invariants, signed passport (PDF + JSON + QR) | built, tested |
| Identity tracking through dropout and new track ids; restart from the log alone | built, tested on simulated detections |
| Bench screen, tray map, timeline with frames, state at any event, close job, manual fallback | built; checked in a browser against the simulator |
| HTTP backend, auth, persistence, privacy mode, Glimmer client, Meta API clients | built, tested against fakes; **no live API call has been made** |
| Eval harness on recorded-session files | built; the shipped sessions are **synthetic** |
| Docker compose | written, `docker compose config` passes; **image build not run** |
| SAM 3.1 on a real bench (Day 1 kill test) | **not done**: needs a camera and a bench |
| Camera mode in the browser | written, **never run against a real camera** |
| Voice | browser speech recognition and synthesis; Muse Voice Transcribe **not integrated** |
| Local perception (video never leaves the bench) | **not built**: SAM is a cloud API, see `docs/GLIMMER.md` |
| 3-minute video, ten real recorded teardowns, real Glimmer run, backup footage | **not done**: see `docs/SUBMISSION.md` |

## What is not proven yet

- **Perception.** Nobody has run SAM 3.1 on a real bench here. The simulator (`cairn/scenarios.py`) produces the detections SAM would, with injected dropout and track-id churn. It says nothing about real perception.
- **The eval numbers are simulated.** `eval/report.md` demonstrates the harness and the safety and memory layers, not the product.
- **Live API calls.** `cairn/meta_api.py` follows https://dev.meta.ai/docs but has only run against fake transports.
- **The "no robot, no cloud box" claim** holds for everything except perception.
- **Passport trust.** The signature proves the record was not altered, not who signed it; tying a key to a real shop needs a key registry.

## Layout

```
cairn/events.py     hash-chained event log         cairn/safety.py     safety kernel
cairn/device.py     task graph, 24 wells, codes    cairn/invariants.py verification invariants
cairn/graph.py      object graph (projection)      cairn/passport.py   sign / verify / PDF / HTML / QR
cairn/session.py    reconciler + policy            cairn/agent.py      graph agent, Wonder loop
cairn/geometry.py   the bench in pixels            cairn/frames.py     frame store + renderer
cairn/timeline.py   human-readable event list      cairn/server.py     HTTP backend
cairn/ui/bench.html the single-view screen         cairn/meta_api.py   Wonder + SAM 3.1 clients
cairn/scenarios.py  bench simulator, hero demo     cairn/local_llm.py  Glimmer / local model client
cairn/evaluation.py record, replay, score          docs/               setup, Glimmer note, submission kit
```

Design rule: the model never writes to the graph. Perception proposes detections, the session decides, the log records, and the passport only issues when every invariant holds.
