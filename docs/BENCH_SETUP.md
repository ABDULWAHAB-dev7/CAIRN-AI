# Bench setup and the Day 1 kill test

Everything here is the part that software cannot do for you. Do it before anything else: if SAM 3.1
cannot track the parts on your bench, change the bench, not the code.

## The bench

- Overhead camera on an articulating arm, looking straight down, 1080p, fixed focus and exposure.
- Black mat with a printed grid and a small calibration marker in the top-left corner of the view.
- A 6 x 4 tray with wells numbered 01 to 24, inside the view, top right. Wells 01-10 base screws, 11-14 battery
  screws, 15 SSD screw, 16-19 hinge screws, 20-22 fan screws, 23 Wi-Fi screw, 24 spare. (`cairn/geometry.py` is the
  source of truth; the simulator, the renderer and the default calibration all read it.)
- Bright, even light. Shadows kill tracking; motion blur is the other enemy.
- A laptop or tablet at the edge of the bench running the browser.

## Run it

```bash
docker compose up                       # http://localhost:8000
```

or without Docker: `pip install -e ".[server]" && cairn serve`.

1. Open http://localhost:8000 (a Chromium browser; `localhost` is allowed to use the camera).
2. **Jobs → New job**: pick the device, enter a job number and your name. Cairn snapshots the sealed device as the baseline.
3. Click **Camera**, allow access, then **Baseline** with the sealed device in view.
4. Set the server to perception mode (needs your Meta Model API key):

```bash
MODEL_API_KEY=... CAIRN_PERCEPTION=sam cairn serve
```

The browser sends a frame only when the scene changes (or every 4 s). The server draws quiet outlines
on the camera image; the camera feed itself is never re-encoded for the screen.

**Calibration.** The default calibration is the demo geometry. For your own tray, write a JSON file and set
`CAIRN_ZONES`: `{"trays": {}, "device": [x0,y0,x1,y1], "prompts": {"hinge screw": "hinge_screw"}}`. Wells are
taken from `cairn.geometry` unless you extend `ZoneMap`. Mount the camera so the tray lands on the geometry's
well rectangles, or edit the geometry.

**Cost.** SAM image requests are one prompt per part class per frame: 12 prompts at $2.50 per 1k images is about
$0.03 per frame. Change-gating keeps a 10-minute teardown to a few hundred frames. Video requests ($0.20 per 1k
frames) are the cheaper path once the kill test passes.

## No camera?

- **Replay**: Jobs → *Replay the scripted demo*. Every moment, including the frame, is on the timeline.
- **Manual input**: the drawer under the voice bar logs the ESD strap, battery disconnect/reconnect, boot test,
  and part moves by hand. Same safety kernel, same invariants, same passport.

## Day 1 kill test (do this first)

Question: can SAM 3.1 hold 6-8 part classes across a real 10-minute teardown?

1. Fix the camera, light and tray. Record one full teardown of the demo device as video.
2. Run it through `cairn serve` with `CAIRN_PERCEPTION=sam` by replaying the video into the camera (a virtual
   webcam such as OBS works), or send frames to `POST /sessions/{id}/image` directly.
3. Pass: at least 95% of the 23 fasteners reach a tray well with a stable identity; fewer than 5% ID switches.
4. Fail: change the device, the light or the tray before writing more code. The fallback is the Manual input
   drawer: the product becomes memory plus verification, not autonomous perception.

## Recording the evals

Ten teardowns, 2 lighting setups, 3 technicians. For each, save a session directory (`frames.jsonl`, `actions.json`,
`truth.json`, `meta.json`; see `cairn/evaluation.py`) with ground truth from a paper checklist marked by a second
person, then run `cairn eval --sessions path/to/recordings`. Commit `eval/metrics.json` and `eval/report.md`,
failures included.

## What is not verified here

No real camera, no live SAM or Wonder call, no Glimmer model, and no Docker build was run in the environment this
was written in (the Docker daemon was not available; `docker compose config` validates).

## Using a phone with no desktop in front of you (tunnel)

A phone browser only allows camera access over HTTPS, so a plain `http://<pc-ip>:8000` link will not work. Vercel cannot host
the live backend either (it needs a persistent database file and frames arriving every few seconds). The working route used
for the first phone test, from a PC that stays on:

```bash
# 1. public HTTPS address that forwards to the local server (uses the built-in ssh; use 127.0.0.1, not "localhost")
ssh -o ServerAliveInterval=30 -R 80:127.0.0.1:8820 nokey@localhost.run     # prints https://<random>.lhr.life

# 2. the server, with perception, a token and that address (for the passport QR)
MODEL_API_KEY=... CAIRN_PERCEPTION=sam CAIRN_API_TOKEN=<random token> CAIRN_PUBLIC_URL=https://<random>.lhr.life \
  cairn serve --host 127.0.0.1 --port 8820
```

On the phone: open the address + `/bench`, enter the token when asked, start a job, tap **Camera**, then **Baseline**.

Know before you rely on it:
- Anyone with the address **and** the token can use your SAM credits. Without the token every API route returns 401, but
  `/bench`, `/health` and `/v/<id>` are public by design. Use a fresh random token, and stop the tunnel when you are done.
- The address changes every time the tunnel restarts; the PC must stay on and awake.
- Camera frames pass through the tunnel provider. This is not the privacy mode.
- **One frame costs about 13 SAM requests** (one per part class), sent in parallel. Measured on 2026-11-03 with the 13 default
  prompts: **2.3 to 3.0 s per frame** once warm; the first frame after a server start took 23 s. Sent one after another it was
  27 s per frame. Roughly 3 s per check means a dropped part is flagged a few seconds after it leaves the frame, close to the
  blueprint's 5 s target but not measured on a real bench.
- The scripted task graph is the demo laptop (23 specific fasteners). A different machine will not match it, so for a real laptop
  start the job with **Any laptop (open bench)** instead (next section).
- If Meta answers `402 billing_not_configured`, every SAM call is refused until the billing problem on the Meta developer
  account is fixed (dev.meta.ai/billing). The page then says so in the camera panel, and `/health` shows it under
  `perception_warning`. Nothing in this repository can work around that.

## Open bench: any laptop (no task list)

Device **Any laptop (open bench)** does not need a known model. SAM looks for `laptop`, `screw`, `fan`, `cable` and
`circuit board` (plus `hand`), the app gives each thing it sees a slot, and then narrates by counting:

- after two pictures: "I can see 31 screws, 1 fan, 11 cables on the laptop. Start taking it apart and I will say what you remove."
- a screw seen in a hand or off the laptop: "Removed screw p_07. 30 screws still on the laptop."
- a screw that simply stops being there while the rest of the laptop is still in view for 9 s: "Screw p_07 is no longer on the
  laptop (not seen for 9 s)." (the close-up case, where nothing "leaves" the frame). If most parts vanish together the
  camera moved, and nothing is announced.
- a screw that comes back: "Screw p_07 is back on the laptop."

No ESD strap or power-off step is demanded in this mode, because the app has no task list for the machine.

**Measured on four public Wikimedia Commons photos of open laptops (2026-11-03; the photos are not committed):**
SAM reliably found laptop, screw (34 in one close-up), fan, cable and circuit board, and found nothing for battery, hard drive,
DVD drive, back cover or memory module. Screws are only found when the camera is close; in a wide shot they are too small.
A close-up fills the frame with the motherboard, so there is no "laptop" box and "on the laptop" then means the whole picture.
Re-encoding the same picture finds roughly 31 of 34 screws again, which is why a part must be missing for several seconds
before it is reported. Calls were typically 3 to 6 s per picture, with occasional 23 to 26 s outliers.

**Not verified:** a phone camera pointed at a real laptop being unscrewed. The end-to-end narration was exercised against the
real SAM API with still photos, and against scripted detections for removal.

