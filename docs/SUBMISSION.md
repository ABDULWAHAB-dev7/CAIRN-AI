# Submission kit

Status of every item the end state asks for, then the drafts. Nothing marked TODO has been done; these need a
physical bench, a camera, API access, or your voice.

**Framing decision (2026-11-02, updated after the live calls):** the SAM 3.1 and Muse Wonder calls now succeed
(`docs/PROOF.md` rows 11-12b), but SAM has only seen a simulator render. Perception on real parts is **unproven** until
the kill test passes on a real bench. Until then the demo is presented as **memory and verification, with perception by
tap**, and the eval table says "perception: not proven". If the kill test passes, say so with the real numbers from
`eval/real/`; if it fails, keep this framing.

| Item | Status |
|---|---|
| Working repo, `docker compose up`, replay mode without a camera | built; Docker build untested here |
| Single-view bench screen, tray map, timeline with frames, voice bar, close job | built, tested in a browser on the simulator |
| Passport PDF + JSON with QR, evidence frames, hash chain, status line | built, tested |
| Eval table, ten sessions | harness built; sessions are **synthetic**. TODO: record ten real teardowns |
| Open bench: narrate any laptop (count, removed, no longer on the laptop) | built, tested; **not run on a real unscrewing**. SAM found laptop, screws, fan, cable, board on real photos and **not** battery, drives, cover or memory |
| Meta API access | **blocked 2026-11-03: `402 billing_not_configured`** until the billing problem is fixed at dev.meta.ai/billing |
| Day 1 kill test (SAM 3.1 on a real bench) | **TODO**, see `docs/BENCH_SETUP.md` |
| 3-minute video | **TODO**: shot list below |
| 30-second clip, thread | **TODO**: drafts below |
| Local Glimmer deployment note | `docs/GLIMMER.md`; no model run yet |
| Backup footage, second device | **TODO** |

## One paragraph

Cairn gives AI object permanence for physical repair. Today's models recognise a screw but forget it the moment it
leaves the frame, so they cannot guide a real teardown. Cairn tracks every part with identity, keeps a persistent
object graph, catches missing, wrong and out-of-order parts, enforces a safety kernel the model cannot override, and
closes the job with a signed repair passport that anyone can verify. In the demo a technician drops a screw, reaches
for the SSD with the battery connected, grabs the wrong screw, walks away for lunch and comes back to exactly the
same state. It targets the 62M-tonne e-waste problem and the repair skills gap.

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

## Submission checklist

- [ ] 3-minute captioned video, playable muted, three hero moments each readable in under 10 seconds
- [ ] One-paragraph pitch (above)
- [ ] Architecture diagram: `docs/ARCHITECTURE.md`
- [ ] Eval table from **real** recordings, with at least one honest failure (`eval/report.md` is synthetic)
- [ ] Sample passport PDF + JSON from a real job (`cairn demo` makes a simulated one)
- [ ] Glimmer deployment note with measured latency (`docs/GLIMMER.md`)
- [ ] 30-second clip and thread
- [ ] Backup footage, a second device, a second tray
- [ ] Every figure checked against its primary source; every claimed model has a visible role in the video
