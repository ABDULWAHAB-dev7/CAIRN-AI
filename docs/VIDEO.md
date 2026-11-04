# The demo video

Two files, built by `scripts/make_demo_video.py` from the running app:

| File | Length | What |
|---|---|---|
| [`video/cairn-demo.mp4`](video/cairn-demo.mp4) | 2:31 | the full cut, 1080p, captions burned in, no audio |
| [`video/cairn-30s.mp4`](video/cairn-30s.mp4) | 0:26 | the short cut for the clip and thread: the drop, the safety stop, the verify page |

## What it is, and is not

It is a **captioned replay of the simulated demo** in the real bench screen, passport page and verify page. The counts, the
safety stop, the close-job result and the signed passport come from the running code, not from edited footage. Every bench
shot is labelled "SIMULATED REPLAY · recognition is off in this build", and the first frame and the "what is real, and what is not" card near
the end say what is simulated and what is not.

It is **not** footage of a real teardown, and it is not narrated. Perception is off (`CAIRN_PERCEPTION=none`), so no Meta
call is made while filming. The one real-perception shot is a photo with SAM 3.1's boxes from the live call on 2026-11-03.
A live recording on a real bench, as in [`DEMO-RUNBOOK.md`](DEMO-RUNBOOK.md), is still stronger; this exists so that a true
video is available if that recording is not possible.

## Shots

| Time | On screen | Caption |
|---|---|---|
| 0:00 | title card with the disclosure | (card text) |
| 0:09 | the real bench screen, replaying the simulated demo (event #2) | AI can design a laptop. It can't take one apart. |
| 0:15 | the real bench screen, replaying the simulated demo (event #2) | It can recognise a screw. It forgets the screw the moment it leaves the frame. |
| 0:22 | a real photo with SAM 3.1's boxes | What SAM 3.1 saw on a real open laptop photo: dozens of screws. It found no battery, drive or cover. |
| 0:32 | the real bench screen, replaying the simulated demo (event #24) | Cairn gives every part an identity, a location and a state. |
| 0:39 | the real bench screen, replaying the simulated demo (event #69) | The drop: a screw leaves the bench and never reaches a tray. |
| 0:45 | the real bench screen, replaying the simulated demo (event #69) | MISSING 1, with the part named. It noticed before I did. |
| 0:51 | the real bench screen, replaying the simulated demo (event #55) | The danger: a hand reaches for an SSD screw while the battery is still connected. |
| 0:57 | the real bench screen, replaying the simulated demo (event #55) | Stop. Disconnect the battery first. A safety rule the model cannot override. |
| 1:04 | the real bench screen, replaying the simulated demo (event #100) | The wrong screw: a 3 mm screw about to go into a 5 mm hole. |
| 1:10 | the real bench screen, replaying the simulated demo (event #100) | That hole takes a 5 mm. Tray 16. |
| 1:15 | the real bench screen, replaying the simulated demo (event #73) | Then a 30-minute break, with one screw still missing. |
| 1:20 | the real bench screen, replaying the simulated demo (event #76) | Back from lunch: same next step. The missing screw was never forgotten; it is found and placed in tray 11. |
| 1:28 | the real bench screen, replaying the simulated demo (event #156) | Reassembly: every screw back where it came from, each step checked. |
| 1:34 | the real close-job dialog | Close the job: VERIFIED. 23 of 23 fasteners. Three exceptions recorded, none hidden. |
| 1:42 | a real page of the app | A signed repair passport: counts that reconcile, evidence frames, a hash chain over the log. |
| 1:49 | a real page of the app | Anyone can check it. Change one number and the signature fails. |
| 1:56 | architecture card | (card text) |
| 2:06 | what is real and what is not | (card text) |
| 2:23 | end card | (card text) |

## Credit

The SAM shot uses "Laptop open servicing" by Solutionservice21, Wikimedia Commons, licensed CC BY-SA 4.0
(https://creativecommons.org/licenses/by-sa/4.0). SAM's boxes were drawn on it; the credit is on screen. That image is not
in this repository, only the video frames that show it.

## Rebuild

```bash
pip install playwright pillow && playwright install chromium     # and ffmpeg on PATH
python scripts/make_demo_video.py --out out/video                 # all shots except the SAM photo
python scripts/make_demo_video.py --out out/video --sam-overlay path/to/overlay.jpg --sam-credit "credit line"
```

`tests/test_video_plan.py` keeps the plan under three minutes and keeps the disclosure on the first frame and every bench frame.
