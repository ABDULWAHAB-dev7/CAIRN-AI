# Cairn explained

A 5:36 animated explainer of the whole project: the problem, how Cairn works end to end, each part of the
machinery, what it is for, and what is real and what is not. Built from code, not edited in a timeline.

| File | Length | What |
|---|---|---|
| [`video/cairn-explained.mp4`](video/cairn-explained.mp4) | 5:36 | 1080p, captions burned in, voiceover |
| [`video/cairn-demo.mp4`](video/cairn-demo.mp4) | 2:31 | the shorter captioned replay ([`VIDEO.md`](VIDEO.md)), under the hackathon's three-minute cap |

If the submission form caps the video at three minutes, submit `cairn-demo.mp4` and use this one as the long explanation.

## How it was made

The method follows a creator video about making motion graphics with Claude: write the script, make the voiceover, let
Claude write the animation as code, render it frame by frame, join it with ffmpeg. The engine here is written from scratch
for this repo. Nothing was downloaded. Details, and how to swap in an ElevenLabs or your own voice, are in
[`../explainer/README.md`](../explainer/README.md).

- `explainer/script.json`: the narration, one sentence per line, key words marked.
- `explainer/scenes.js`: 13 scenes as code. Every visual is a function of time, with cues locked to the start of each sentence.
- `explainer/build.py`: voiceover, timeline, about 10,105 frames rendered by 12 headless browsers, ffmpeg.
- The real-app shots come from `explainer/capture_assets.py`: screenshots of the running app replaying the simulated demo.

## What it shows

| Time | Chapter | Narration |
|---|---|---|
| 0:00 | Opening | AI can design a laptop. It can write the code, plan the supply chain, even draw the circuit board. But ask it to take one apart, and it falls over. This is Cairn. Object permanence, for physical repair. |
| 0:14 | The problem | Today's vision models have object recognition. They can see a screw, draw a box around it, and give it a name. But the moment the screw leaves the frame, it is gone from their world. A person knows the screw still exists. That is object permanence, and the models do not have it. |
| 0:32 | What Cairn is | Cairn is a memory layer for physical repair. It watches a repair bench, gives every part an identity, a place and a state, and remembers the whole teardown. The plan starts with independent repair shops, then refurbishers and recyclers, then warranty and insurance. What comes out is not a chat reply. It is a signed repair passport. |
| 0:52 | How it works | Here is how it works, end to end. A camera, or a tap on the screen, feeds a perception model. In the design that is SAM 3.1, which finds and tracks parts from a text prompt. Perception only proposes. A session layer decides what it means: which part is which, whether a step is legal, whether anything is wrong. Every decision is written to an append-only log. The object graph is just a view of that log. A safety kernel and five verification checks stand between the work and the final passport. The rule through all of it: the model proposes, the session decides, the log records. The model never writes. |
| 1:28 | The memory | The memory is a hash-chained log. Each event carries the hash of the one before it, so changing anything in the past breaks every link after it. The log lives in SQLite, with updates and deletes blocked at the database. The object graph is rebuilt by replaying the log. Restart the server, and the state comes back exactly. That is what makes the return from lunch work. The memory is in the log, not in the model. |
| 1:53 | The object graph | Every part is a node with an identity, a place, and a state. Installed. In transit, while it is in a hand. Removed, once it reaches a tray well. Reinstalled. Retired. Or lost. The demo laptop has twenty-nine parts, twenty-three of them fasteners, and a tray of twenty-four numbered wells. If a part is in transit and nobody has seen it for three seconds, it becomes missing, with the part named and the time it was last seen. In the simulated sessions, the longest it took to flag a dropped screw was two point seven five seconds. |
| 2:25 | The safety kernel | Four safety rules sit in code, outside the model. ESD strap on before touching internals. Battery disconnected before removing any internal part. Stop all work if smoke, heat or swelling is reported. And never pry near a connected battery. They are checked before every removal. A language model can explain a rule, but it cannot switch one off. In the demo, a hand reaches for an SSD screw with the battery still connected. The step card turns red, and the violation goes on the passport. |
| 2:53 | The demo, replayed | Here is the scripted demo, replayed in the real app. First, a screw is dropped. It never reaches a tray, so the board shows missing one, and names the part. Then the wrong screw. A three millimetre screw is about to go into a five millimetre hole, so the right tray well is called out. Then a thirty minute break. When the technician returns, the screen, the counts and the next step are still there, and the missing screw is found and logged. |
| 3:18 | Verification and the passport | Closing a job is not a button press. Five checks have to pass. Count: every removed fastener is reinstalled or retired. Order. Safety. Closure: the tray is empty and there are no extra parts. And function: the boot test passed. If they pass, Cairn signs a repair passport. Counts that reconcile, every exception and how it was resolved, evidence frames pinned by hash, and a QR code. The signature covers the head of the event chain, so editing the passport, or the log behind it, breaks verification. Anyone can scan the code and see whether the record is intact. |
| 3:52 | Open bench: any laptop | A scripted task list only fits one laptop, so there is also an open bench mode for any machine. SAM looks for the laptop, screws, fans, cables and circuit boards. Cairn gives each one a slot and tracks it from picture to picture. It counts what it sees, announces what comes off, and says when a screw is no longer on the laptop. On real photos of open laptops, SAM found dozens of screws, a fan, cables and the board. It found no battery, no drive, no back cover and no memory. And screws only show up when the camera is close. |
| 4:24 | Which model does what | Each model has one narrow job. SAM 3.1 turns pictures into detections. It is the eyes, and only the eyes. Muse Wonder is the agent. It can read the graph and propose the next step, but only a step the graph lists as legal. It has no tool that writes. Muse Glimmer is the local option, so bench video can stay on the bench. The client is written and tested against a fake. No local model has been run. Voice today is the browser's own speech. Muse Voice is not integrated. |
| 4:53 | What is real, what is not | Now the honest part. Every teardown you have seen is simulated, and so are the numbers in the evaluation table. What is real is the machinery: the log, the graph, the safety kernel, the checks, the signed passport and the verify page. More than a hundred automated tests cover it, the Docker image is verified, and a proof ledger dates every claim. What is not proven is perception during a real teardown. Meta has refused our SAM calls since the third of November over a billing problem, so there was no real bench test. We would rather show you the boundary than hide it. |
| 5:25 | Closing | Cairn gives AI a memory for the physical world. The first AI that can take something apart, and put it back together. The code, the proof ledger and the live replay are linked below. |

## What it is not

- It is not footage of a real teardown. Every part of the bench shown is the simulated demo, and the video says so.
- The voice is a synthetic Windows voice, chosen because it needs no account. It is clear but plain; replace it with
  `--audio-dir` if you have a better one.
- It does not show perception working on a real bench, because that was never run. It shows what SAM did find on a real
  photo and what it did not, and that Meta has refused the calls since 3 November.

## Credits

- The open-bench shot uses "Laptop open servicing" by Solutionservice21, Wikimedia Commons, licensed CC BY-SA 4.0
  (https://creativecommons.org/licenses/by-sa/4.0). SAM's boxes were drawn on it, and the credit is on screen. The image
  is not in this repository, only the video frames that show it.
- Inter Tight (SIL Open Font License) is the typeface.
