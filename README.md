# Cairn

**Object permanence for physical work.** Cairn watches a repair bench, gives every part a persistent identity, remembers the teardown across time, catches missing, wrong or out-of-order parts, and ends with a signed, independently verifiable repair passport.

The full plan is in [`docs/Cairn-Project-Blueprint.pdf`](docs/Cairn-Project-Blueprint.pdf). This repo is the build.

```bash
pip install -e ".[dev]"
python -m pytest          # 23 tests
cairn demo                # scripted hero demo -> out/passport.json, passport.html, repair.db
cairn verify out/passport.json --db out/repair.db
cairn eval                # blueprint section 13 metrics on simulated sessions
```

## Status against the blueprint

| Blueprint piece | State |
|---|---|
| Append-only, hash-chained event log (SQLite, UPDATE/DELETE blocked) | built, tested |
| Object graph, task graph, repair state machine, the three product queries | built, tested |
| Safety kernel (ESD, power-off, hazard halt, no pry near battery); the agent can only explain it | built, tested |
| Verification invariants (count, order, safety, closure, function) and passport gate | built, tested |
| Passport: Ed25519-signed JSON + printable HTML, verifiable against the event log | built, tested |
| Identity/re-ID reconciler (track churn, dropout, lost-part recovery), restart from log alone | built, tested |
| Human-confirmed tap fallback (same policy as perception) | built |
| Agent: deterministic graph agent, plus Muse Wonder tool loop that can only propose legal steps | built; Wonder needs a client |
| Perception: `ZoneMap` (pixels to tray/device/hand), `Sam31Perception` adapter, frame replay | built; SAM backend not bundled |
| Eval harness (recall, ID switches, missing-part latency, fault catch, false alarms) | built, **synthetic data only** |
| Voice (Muse Voice), Glimmer local watcher, Muse Image passport art | not started |
| Next.js overlay / tray map / timeline UI | not started |
| Passport as PDF (HTML today) | not started |

## What is not proven yet

- **Day 1 kill test.** Nobody has run SAM 3.1 on a real bench. The simulator in `cairn/scenarios.py` produces the detections SAM would, with injected dropout and track-id churn, so the memory and safety layers can be tested. It says nothing about real perception.
- **The eval numbers are simulated.** `cairn eval` prints a table, but until it is fed recorded clips it demonstrates the harness, not the product.
- **Wonder and SAM clients.** `WonderAgent` takes any client with `complete(messages, tools)`; `Sam31Perception` takes any `SamBackend`. Wire both to the Meta Model API with your key.
- **Passport trust.** The signature proves the record was not altered. Tying a key to a real shop needs a key registry.

## Layout

```
cairn/events.py      hash-chained event log          cairn/safety.py      safety kernel
cairn/device.py      curated task graph (23 screws)  cairn/invariants.py  verification invariants
cairn/graph.py       object graph (event projection) cairn/passport.py    sign / verify / render
cairn/session.py     reconciler + policy             cairn/agent.py       graph agent + Wonder loop
cairn/perception.py  zones, SAM adapter, replay      cairn/scenarios.py   bench simulator, hero demo
cairn/evaluation.py  metrics                         tests/               23 tests
```

Design rule: the model never writes to the graph. Perception proposes detections, the session decides, the log records, and the passport only issues when every invariant holds.
