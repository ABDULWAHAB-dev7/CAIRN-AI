# Submission kit

Status of every item the end state asks for, then the drafts. Nothing marked TODO has been done; these need a
physical bench, a camera, API access, or your voice.

**Framing decision (2026-11-02, last checked 2026-11-04):** the SAM 3.1 and Muse Wonder calls now succeed
(`docs/PROOF.md` rows 11-12b), but SAM has only seen a simulator render. Perception on real parts is **unproven** until
the kill test passes on a real bench. Until then the demo is presented as **memory and verification, with perception by
tap**, and the eval table says "perception: not proven". If the kill test passes, say so with the real numbers from
`eval/real/`; if it fails, keep this framing.

| Item | Status |
|---|---|
| Working repo, `docker compose up`, replay mode without a camera | **verified 2026-11-04**: image builds, Compose is healthy, `/demo` and the passport PDF work inside the container (see `docs/proof/docker/docker-verify.txt`) |
| Single-view bench screen, tray map, timeline with frames, voice bar, close job | built, tested in a browser on the simulator |
| Passport PDF + JSON with QR, evidence frames, hash chain, status line | built, tested |
| Eval table, ten sessions | harness built; sessions are **synthetic**. TODO: record ten real teardowns |
| Open bench: narrate any laptop (count, removed, no longer on the laptop) | built, tested; **not run on a real unscrewing**. SAM found laptop, screws, fan, cable, board on real photos and **not** battery, drives, cover or memory |
| Meta API access | **blocked 2026-11-03: `402 billing_not_configured`** until the billing problem is fixed at dev.meta.ai/billing |
| Day 1 kill test (SAM 3.1 on a real bench) | **TODO**, see `docs/BENCH_SETUP.md` |
| 3-minute video | **built, 2:31**: a captioned replay of the **simulated** demo (`docs/video/cairn-demo.mp4`, how: `docs/VIDEO.md`). Not real-bench footage and not narrated; a live recording per `docs/DEMO-RUNBOOK.md` would still be stronger |
| 30-second clip, thread | clip built (`docs/video/cairn-30s.mp4`, 26 s); thread: drafts below, **yours to post** |
| Local Glimmer deployment note | `docs/GLIMMER.md`; no model run yet |
| Backup footage, second device | **TODO** |

## One paragraph

Cairn gives AI object permanence for physical repair. Today's models recognise a screw but forget it the moment it
leaves the frame, so they cannot guide a real teardown. Cairn tracks every part with identity, keeps a persistent
object graph, catches missing, wrong and out-of-order parts, enforces a safety kernel the model cannot override, and
closes the job with a signed repair passport that anyone can verify. In the demo a technician drops a screw, reaches
for the SSD with the battery connected, grabs the wrong screw, walks away for lunch and comes back to exactly the
same state. It targets the 62M-tonne e-waste problem and the repair skills gap.

## What is simulated

Put this where judges see it, in these words or close to them:

> Everything in this repo that looks like a bench session — the frames, the screenshots, the ten eval runs, the
> hero demo — comes from a bench simulator (`cairn/scenarios.py`). It exercises the memory, safety and verification
> layers; it says nothing about real perception. The Meta API clients made successful live calls on 2026-11-02
> (SAM 3.1 and Muse Wonder, transcripts in `docs/PROOF.md`), and SAM found laptop, screws, fan, cable and circuit
> board on real photos of open laptops on 2026-11-03, but not battery, drives, back cover or memory. On
> 2026-11-03 Meta began refusing SAM calls with `402 billing_not_configured`, so perception is not available in this
> build. The demo is memory and verification, with perception by tap; the safety kernel, the invariants, the signed
> passport and the verification page are real and tested.

Do not say "Cairn tracks every part on your bench" without the second half of that paragraph.

## 3-minute video: shot list (record five takes, keep the cleanest)

| Time | Show | Say |
|---|---|---|
| 0:00 | Overhead: laptop, tray, camera. Screen: empty job, REMOVED 0. | "AI can design a laptop. It can't take one apart. Here's why." |
| 0:15 | Split screen: a screw gets an outline, leaves the frame, the outline disappears. | "It has object recognition, not object permanence." |
| 0:30 | New job screen: device, job number. Teardown starts; tray map fills. | "Cairn gives every part an identity, a location and a state." |
| 1:00 | **The drop.** MISSING 1 within about five seconds, banner: "...left the bench at ... and did not arrive in a tray well." | "It noticed before I did." |
| 1:15 | **The danger.** Hand reaches for the SSD, battery connected. Step card turns red. | "Stop. Disconnect the battery first. A safety rule, not a suggestion." |
| 1:30 | **The wrong screw.** A 3 mm screw toward a 5 mm hole; the right well pulses once. | "That hole takes a 5 mm. Tray 16." |
| 1:45 | **The return.** Cut to a clock. Same screen, same counts, same next step. Click an old timeline entry: the frame appears. | "I left for lunch. Cairn didn't." |
| 2:05 | Reassembly turns green; tray empties; MISSING 0. | "Every step verified." |
| 2:20 | Close job. Passport PDF: VERIFIED, counts reconcile, evidence frames, QR. | "23 of 23 fasteners. Signed." |
| 2:40 | Scan the QR on a phone: RECORD INTACT. Flash the architecture. | "Anyone can check it wasn't edited." |
| 2:55 | Logo, tagline. | "The first AI that can take something apart and put it back together." |

Caption every line; judges watch muted. Do not show prompts, API calls or a terminal. If the live demo breaks, cut to
the replay (Jobs, *Replay the scripted demo*) or the backup clip. Do not fake results: stage the bench, not the
counts.

## 30-second clip

"AI can design a phone. It can't take one apart. It has object recognition, but not object permanence: it forgets a
part the moment it leaves the frame. Cairn tracks every part, remembers the teardown, and proves the reassembly.
Drop a screw. Skip the battery step. Walk away. Cairn remembers."

## Thread draft

1. AI can design a laptop but can't take one apart. The missing sense is memory. (clip)
2. Models recognise a screw. They don't know it still exists once it leaves the frame.
3. Cairn watches a repair bench, gives every part an identity, and keeps a persistent, auditable object graph.
4. A hard-coded safety kernel the model can explain but not override: no internal part comes out with the battery live.
5. The output is a signed repair passport: counts that reconcile, evidence frames, a QR and a hash chain over the log.
6. 62M tonnes of e-waste a year; right-to-repair is growing, repair capability isn't. Repo and demo: (link)

## Submission checklist (state at 2026-11-04)

| Item | State |
|---|---|
| One-paragraph pitch | **done** (above) |
| Architecture diagram | **done**: `docs/ARCHITECTURE.md` |
| Working repo, one command, replay without a camera | **done and verified** |
| Signed passport PDF + JSON with QR and hash chain | **done** (from a simulated job; labelled) |
| Proof ledger with dates and artefacts | **done**: `docs/PROOF.md`, 25 rows |
| MIT licence | **done**: `LICENSE` |
| 3-minute captioned video | **built** as a replay of the simulated demo (`docs/video/cairn-demo.mp4`, 2:31); **yours to upload**. A live take per `docs/DEMO-RUNBOOK.md` would replace it |
| Eval table from **real** recordings | **yours**: `eval/report.md` is synthetic and says so |
| Sample passport from a **real** job | **yours**; `cairn demo` only makes a simulated one |
| 30-second clip and thread | clip **built** (`docs/video/cairn-30s.mp4`); thread drafts above; **yours to post** |
| Glimmer note with measured latency | note exists; **no model was run** |
| Backup footage, second device, second tray | **yours** |
| Every figure checked against its primary source | **yours**; the appendix numbers are secondary |
| Every claimed model has a visible role in the video | **yours**; SAM is currently blocked by billing |

If you run out of time, ship the first six rows and be explicit about the rest. A small, true submission beats a
large, unverifiable one.
