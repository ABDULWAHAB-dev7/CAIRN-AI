# Record the demo in one sitting

The video is 25% of the score and the only artefact that can carry the other 75%. Record it even if perception is
still blocked: the honest tap-driven demo is stronger than no demo.

Two paths. Pick one before you set up, and do not mix them in the edit.

| Path | When | What the video claims |
|---|---|---|
| **A — SAM live** | `MODEL_API_KEY` works and `/health` shows no `perception_warning` | perception plus memory plus verification |
| **B — tap / replay** | Meta still answers `402 billing_not_configured` | memory plus verification; perception by tap, said on screen |

For path B, put this caption on the first frame: *"Recognition is off in this build (Meta billing). The memory, the safety stop and the passport are real."*

## Pre-flight (15 minutes)

- Laptop on the bench, lid open but powered off. Tray with numbered wells in frame. Even light, no window behind.
- Camera: phone on a mount looking down, or the laptop webcam. Fill the frame with bench + tray; leave the tray labels readable.
- Browser at `/bench`, 100% zoom, notifications off, one tab only. Hide the bookmarks bar.
- Screen recorder at 1080p, 30 fps, system audio on if you narrate live. Record the screen and the bench in the **same** take if you can; a single unbroken shot is more convincing than cuts.
- Do a 20-second test recording and watch it back before the real take. Check that the tray labels and the top strip are legible on a phone.

## The six shots

| # | Do this | Screen must show | Caption |
|---|---|---|---|
| 1 | Open `/bench`, press **Jobs → New job**, pick the device, type a job number, start. | `REMOVED 0 ACCOUNTED 0 MISSING 0`, `STATE sealed` | "AI can design a laptop. It can't take one apart." |
| 2 | Remove two or three screws, place them in wells. | counters move, tray wells fill, timeline grows | "Every part gets an identity, a location and a state." |
| 3 | Drop a screw off the bench and keep working. | within ~5 s: `MISSING 1` and the banner naming the part | "It noticed before I did." |
| 4 | Reach for the SSD with the battery still connected. | step card turns red, safety alert | "Stop. Disconnect the battery first. A safety rule, not a suggestion." |
| 5 | Aim a 3 mm screw at a 5 mm hole (or log the wrong part by tap). | correct well pulses once, alert names the part | "That hole takes a 5 mm. Tray 16." |
| 6 | Close the job, open the passport, scan the QR on a phone. | `VERIFIED`, counts reconcile, `RECORD INTACT` on the phone | "Anyone can check it wasn't edited." |

Between 5 and 6, cut to a clock and back: same screen, same counts, same next step. That is the "return from lunch"
beat, and it is the one a chatbot cannot fake.

## Rules

- Never show a terminal, a prompt or an API key.
- Never present the simulator replay as live footage. If you cut to **Jobs → Replay the scripted demo**, say "replay" in the caption.
- If a take fails, keep going; do not restage counts. A real miss that gets caught is better footage than a perfect run.
- If the live demo breaks, cut to the replay and say so. Do not fake a pass.

## Export

- 3:00 maximum, 1080p, captions burned in (judges watch muted), audio normalised to about -14 LUFS.
- Title: "Cairn — object permanence for physical repair".
- Upload unlisted to YouTube, put the link in the README top line and in the submission form.
- Cut a 30-second version from shots 3, 4 and 6 only. That is the clip for the thread and the viral pool.
- Keep the raw files. If a judge asks for the unedited take, you have it.
