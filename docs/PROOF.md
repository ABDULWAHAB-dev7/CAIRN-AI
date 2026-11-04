# Proof ledger

Every claim the README makes, what backs it, and when it was run. Dates are UTC. If a row says **not exercised**, the
claim is *not* supported and nobody should repeat it as if it were.

**Read this first.** All sessions, frames, screenshots and eval numbers in this repo come from a bench **simulator**.
No real bench or real teardown has been run. The Meta API clients **made successful live calls on 2026-11-02**
(rows 11 to 12b). On 2026-11-03 SAM was also tried on four public photos of open laptops (row 21), and later that day
Meta started refusing every SAM call for billing (row 22). **Perception on a real teardown is still unproven** (row 17). The first attempt, with an invalid key, was rejected with HTTP 401 and is kept in git history
(commit `522dd46`, `docs/proof/meta/` as it was then).

| # | Claim | Status | Artefact | Run |
|---|---|---|---|---|
| 1 | 113 tests pass on a clone of `main`; CI is green | verified | [`fresh-clone/pytest.txt`](proof/fresh-clone/pytest.txt), re-run 2026-11-04; GitHub Actions `test` on merge commit `42f8152` | 2026-11-04 |
| 2 | Event log is hash-chained and append-only; tampering is detected | verified (unit tests) | `tests/test_core.py::test_log_is_hash_chained_and_append_only`, `::test_tampered_event_is_detected` | 2026-11-02 |
| 3 | Object graph, safety kernel (4 rules), five verification checks | verified on simulated detections | `tests/test_core.py` (safety, memory, invariants sections) | 2026-11-02 |
| 4 | The signed passport verifies against the event log; an edited copy is rejected | verified | [`fresh-clone/demo-verify-tamper.txt`](proof/fresh-clone/demo-verify-tamper.txt), [`fresh-clone/sample-passport.json`](proof/fresh-clone/sample-passport.json) (**simulated** session) | 2026-11-02 |
| 5 | HTTP backend: sessions, auth, persistence, frames, close job, passport routes, SSE | verified with an in-process test client | `tests/test_server.py`, `tests/test_bench.py`, `tests/test_web_debug.py`. A live-HTTP smoke test (15 checks) was also run by hand; **its transcript was not saved** | 2026-11-02 |
| 6 | Bench screen: tray map, step card, timeline with frames, state at any event | verified against the simulator | [`img/bench-drop.png`](img/bench-drop.png), [`img/passport-closed.png`](img/passport-closed.png) (screenshots of the **simulated** demo), `tests/test_bench.py` | 2026-11-02 |
| 7 | Close job: blocked, `VERIFIED`, or `CLOSED WITH EXCEPTIONS` with a written note | verified | `tests/test_bench.py::test_close_blocked_then_closed_with_exceptions_needs_a_note`, `::test_verified_passport_has_evidence_qr_counts_and_safety_checks` | 2026-11-02 |
| 8 | Eval table: recall, ID switches, missing-part latency, fault catch, false alarms | **synthetic only** | [`../eval/report.md`](../eval/report.md), [`../eval/metrics.json`](../eval/metrics.json) from `cairn eval` on 10 simulated sessions | 2026-11-02 |
| 9 | Replaying a recorded session reproduces the original event log exactly | verified (simulated recordings) | `tests/test_eval.py::test_recording_replays_to_the_identical_event_log` | 2026-11-02 |
| 10 | Hosted replay at https://cairn-ai-eta.vercel.app | verified at the time of the log | [`fresh-clone/live-site.txt`](proof/fresh-clone/live-site.txt). It is a read-only replay of the **simulated** demo. See *Incidents* | 2026-11-02 |
| 11 | **SAM 3.1 client: live call succeeds and the parser reads the live format** | **verified on a simulator render only.** HTTP 200 streaming. Prompt `square` → 44 boxes (one per mask, unique object ids, confidences 0.62 to 0.86), prompt `rectangle` → 6 boxes (confidences 0.53 to 0.55). The overlay shows the boxes landing on the squares in the picture. Prompt `screw` → 0 detections (the render contains no screws) | [`proof/meta/sam-square.request-and-status.json`](proof/meta/sam-square.request-and-status.json), [`.response.raw.txt`](proof/meta/sam-square.response.raw.txt), [`.overlay.png`](proof/meta/sam-square.overlay.png); same for [`rectangle`](proof/meta/sam-rectangle.overlay.png) and [`screw`](proof/meta/sam-screw.request-and-status.json); input [`sam_input.jpg`](proof/meta/sam_input.jpg) is a **simulator render, not a real bench**. Format locked by `tests/test_live_formats.py` | 2026-11-02 |
| 12 | **Muse Wonder client: live plain-text call** | verified. HTTP 200, `status: completed`, a `reasoning` item then a `message` item with text `ok` | [`proof/meta/wonder.request-and-status.json`](proof/meta/wonder.request-and-status.json), [`wonder.response.raw.txt`](proof/meta/wonder.response.raw.txt) | 2026-11-02 |
| 12b | **Muse Wonder tool-calling loop, as the agent uses it** | verified against a **simulated** session. The model called `get_next_steps`, then `propose_step("t01")` (the one legal step) and the reply was "Put on the ESD strap." The tool result went back via `function_call_output` + `previous_response_id`. The session log was 0 events before and after: the model wrote nothing | [`proof/meta/wonder-agent-loop.json`](proof/meta/wonder-agent-loop.json) (full request/response transcript), `scripts/prove_wonder_agent.py`, `tests/test_live_formats.py` | 2026-11-02 |
| 13 | Browser camera capture sends frames to the server | **partly.** On 2026-11-03 the page sent frames from a scripted browser video stream to the server and showed the narration (scripted detections, not SAM). The owner opened a real phone camera once, but no job was started so nothing was analysed (fixed in PR #11). **No confirmed run with a real phone camera on a real laptop** | none saved | 2026-11-03 |
| 14 | Docker image builds and runs | **verified.** `docker build` succeeds, `docker compose up` reports healthy on `/health`, `POST /demo` returns 201 with 163 events, and `cairn demo` renders the passport PDF inside the container (so the fonts are present) | [`proof/docker/docker-verify.txt`](proof/docker/docker-verify.txt) | 2026-11-04 |
| 15 | Glimmer (local model) client | tested against a fake chat endpoint only; **no model was run** | `tests/test_server.py::test_glimmer_tool_loop_over_chat_completions` | 2026-11-02 |
| 16 | `CAIRN_PRIVACY=local` refuses cloud components | verified (unit test) | `tests/test_server.py::test_privacy_local_refuses_cloud_components` | 2026-11-02 |
| 17 | SAM 3.1 tracks parts on a real bench (Day 1 kill test) | **not done** (needs a camera and a bench). Row 21 is partial evidence only, and it found no battery, drive, cover or memory, which the demo's hero moments need | none | n/a |
| 18 | Eval on recorded real teardowns | **not done** | none | n/a |
| 19 | 3-minute demo video | **not done** | none | n/a |
| 20 | Muse Voice, Muse Image, video that never leaves the bench | **not built** | none | n/a |
| 21 | **SAM 3.1 on real laptop photos** (open-bench classes) | **observed, not archived.** Four public Wikimedia Commons photos of open laptops. Reliably found: laptop, screw (34 in one close-up), fan, cable, circuit board. Found nothing for battery, hard drive, DVD drive, back cover, memory module. Screws only when the camera is close. Re-encoding the same picture re-finds about 31 of 34 screws. End to end with the open-bench session on one photo: "I can see 34 screws, 1 fan, 11 cables, 1 circuit board on the laptop". The photos and overlays are third-party images and are **not committed**, so a reader cannot re-check this from the repo. This is **not** the Day 1 kill test (no teardown, no recall measured against ground truth) | none in the repo | 2026-11-03 |
| 22 | **Meta API refuses SAM calls: `402 billing_not_configured`** | **current blocker.** "Billing verification failed. Billing Issue." for the team behind the key. Reproduced with a 64 px image, so it is not specific to a photo. Cannot be fixed in this repo; needs the billing problem resolved at dev.meta.ai/billing. The camera panel and `/health` (`perception_warning`) now say so | `tests/test_open_bench.py::test_a_billing_refusal_from_meta_is_explained_and_shown_on_health` | 2026-11-03 |
| 23 | **Open bench: narration for any laptop** (count, announce, removed, no longer on the laptop, back) | verified with scripted detections that renumber and shuffle objects on every call (like the real API) and with a browser run of the page; real SAM only on still photos (row 21). **A real removal was not filmed**: painting screws out of a photo did not remove them from SAM's view | `tests/test_open_bench.py` (23 tests) | 2026-11-03 |
| 24 | 113 tests pass on `main`; CI green | verified | GitHub Actions `test` on merge commit `42f8152` (PR #12); `python -m pytest` locally, 2026-11-04 | 2026-11-04 |
| 26 | A 2:31 captioned demo video and a 26 s clip exist | built from the running app replaying the **simulated** demo; labelled as such on every bench frame and in the closing card. Not real-bench footage, not narrated. One shot shows a CC BY-SA photo with SAM's boxes from the live call on 2026-11-03 | [`video/cairn-demo.mp4`](video/cairn-demo.mp4), [`video/cairn-30s.mp4`](video/cairn-30s.mp4), `scripts/make_demo_video.py`, [`VIDEO.md`](VIDEO.md), `tests/test_video_plan.py` | 2026-11-04 |
| 27 | A 5:36 narrated explainer video exists | built from code (`explainer/`): scenes as JavaScript, every frame rendered by headless Chromium, ffmpeg, a synthetic Windows voice. It explains the whole project and says which parts are simulated or unproven. Not real-bench footage. One shot shows a CC BY-SA photo with SAM's boxes, credited on screen. The voice is synthetic and was checked only for presence and level, not by ear | [`video/cairn-explained.mp4`](video/cairn-explained.mp4), [`EXPLAINER.md`](EXPLAINER.md), `explainer/`, `tests/test_explainer_plan.py` | 2026-11-04 |
| 25 | The repo is MIT-licensed and the pages load with no console errors | verified | [`LICENSE`](../LICENSE); headless Chromium on `/`, `/bench` and `/docs` returned zero console messages, 2026-11-04 (the `/favicon.ico` 404 is gone) | 2026-11-04 |

## What the live calls do and do not show

**They show:** the endpoint, the Bearer scheme, the request bodies for text, image and tool calls, SAM's streamed
token format (`<0f>id<|box;x1;y1;x2;y2;w;h;c|><|mask;...|>`, coordinates in source pixels), and Wonder's response items
(including a `reasoning` item the adapter must skip) all match what `cairn/meta_api.py` expects. No code change was
needed. Reproduce with a valid key in `MODEL_API_KEY`: `python scripts/prove_meta_api.py . square` and
`python scripts/prove_wonder_agent.py .`. The key is never written to any artefact (checked by search).

**They do not show:** that SAM 3.1 can find screws, hands or any real part. The image was a dark mat with drawn squares,
so "square" is an easy concept and "screw" correctly found nothing. SAM image requests are also stateless, so object
ids restart on every call; identity across frames still relies on Cairn's own tracker, which has only been tested on
simulated detections. Latency and cost per frame on a real bench are unmeasured. None of this replaces the kill test.

## Incidents

- **2026-11-02: the hosted site returned 404 for about 10 minutes.** The Vercel project is linked to this GitHub repo,
  so each merge to `main` auto-deployed the repo root (which has no `index.html`) as production and took over the
  alias. The static site was redeployed from the CLI and returned 200 again. **Fix:** a root `vercel.json` makes Git-triggered
  builds generate the static site (`scripts/export_static.py`) instead of deploying the empty repo root. It was verified on a
  Git-triggered **preview** build (`/`, `/bench`, `/v`, `/v.html`, `/data/passport.pdf` all 200) before this change was
  merged; the production result after merge is recorded in the sprint report.
- **`/favicon.ico` returns 404** (one console error per page load). Cosmetic; not fixed.
