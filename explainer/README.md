# Cairn explainer: a video made from code

The video is not edited in a timeline. Every shape, movement and caption is code in `scenes.js`; a headless browser
renders each frame from that code; ffmpeg joins the frames to a voiceover. It follows the same method as the
creator video that inspired it (scene code, rendered frame by frame, voiceover from a script), but the engine here is
written from scratch for this repo, so nothing was downloaded.

| Step in the method | Here |
|---|---|
| Download the engine | not needed: `engine.js` (about 120 lines of animation helpers), `scenes.js`, `stage.html`, `build.py` |
| Install what it needs | Python, Chromium (via Playwright), ffmpeg. No bun, no uv. |
| Script and voiceover | `script.json` is the script. `tts.ps1` makes one clip per sentence with the voices built into Windows. `--audio-dir` takes ElevenLabs or your own clips instead |
| Animate | `scenes.js`: one function per scene, every visual a function of time `t`, cues locked to the start of each sentence |
| Render | `build.py`: about 10,000 frames across 12 browsers, then ffmpeg (H.264 + AAC, loudness-normalised) |

## Run it

```bash
pip install playwright pillow numpy && playwright install chromium     # ffmpeg must be on PATH
python explainer/capture_assets.py --out out/explainer/assets           # clean screenshots of the real app (perception off, no Meta call)
python explainer/build.py --out out/explainer                           # voiceover + frames + video
```

Quick looks while editing: `--at 25,94.5,138` renders stills at those seconds, `--stills 14` renders 14 evenly spaced ones.
Other voice: `--list-voices`, then `--voice Ravi`. Faster or slower: `--rate 1.1`.

The SAM shot needs a photo that is not in the repo (see `docs/EXPLAINER.md`, Credits). Put a picture with SAM's boxes at
`out/explainer/assets/sam_overlay.jpg`, or the scene shows an empty frame there.

## Using ElevenLabs or your own voice

Export one file per narrated sentence into a folder, named `<scene>_<n>.mp3` (or `.wav`) with `n` counting from 0, for
example `hook_0.mp3`, `hook_1.mp3`, `problem_0.mp3`. The lines and their order are in `script.json`. Then:

```bash
python explainer/build.py --out out/explainer --audio-dir path/to/clips
```

Scene lengths, cues and captions are recomputed from your clips, so the animation stays in step with the new voice. The
ElevenLabs MCP can produce the clips, but that needs your own ElevenLabs account and key; nothing here creates one.

## How a scene is written

```js
S.safety = {
  build(root) { root.innerHTML = `...`; },            // make the DOM once
  draw(t, X) {                                          // set every style for local time t
    show(X.q('r0'), t, X.L[1], { dy: 30 });             // appear when sentence 1 starts
    type(X.q('cmd'), 'guard( remove, ssd_screw_01 )', t, X.L[3] + 0.2);
  },
};
```

`X.L[i]` and `X.D[i]` are the start and length of narrated sentence `i`. Because `draw` is a pure function of `t`, any frame
can be rendered alone, which is what lets 12 browsers share the work.

## What this does not do

- It does not export an editable After Effects file (the creator's pro tip). That needs a separate exporter.
- The default Windows voice is a plain synthetic voice. Swap it for a better one with `--audio-dir`.
- The real-app shots are screenshots of the simulated demo replay, labelled as such on screen.
