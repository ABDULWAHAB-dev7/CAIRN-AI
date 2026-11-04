'use strict';
/* A tiny scene-code animation engine.
 *
 * Every visual is a pure function of time: renderAt(T) sets styles for the instant T and nothing else, so any frame can be
 * rendered on its own (and in parallel). Scenes are code (scenes.js); narration lines give each scene its cue times.
 * Python (build.py) calls CAIRN.init(timeline, data) once, then CAIRN.renderAt(T) for every frame and screenshots the page.
 */
const E = (() => {
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, k) => a + (b - a) * k;
  const ease = {
    lin: k => k,
    out: k => 1 - Math.pow(1 - k, 3),
    expo: k => (k >= 1 ? 1 : 1 - Math.pow(2, -10 * k)),
    back: k => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(k - 1, 3) + c1 * Math.pow(k - 1, 2); },
    inout: k => (k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2),
  };
  // progress 0..1 of an animation that starts at s and lasts d
  const p = (t, s, d = 0.6, e = 'out') => ease[e](clamp((t - s) / d));

  /* appear at s (optionally leave at `out`): opacity + a small move + scale */
  function show(el, t, s, o = {}) {
    if (!el) return;
    const { d = 0.6, dx = 0, dy = 26, sc = 1, e = 'out', out = Infinity, od = 0.35, to = 1 } = o;
    const k = p(t, s, d, e), ko = out === Infinity ? 0 : p(t, out, od, 'out');
    const a = k * (1 - ko);
    el.style.opacity = a * to;
    el.style.visibility = a <= 0.001 ? 'hidden' : 'visible';
    el.style.transform = `translate(${(1 - k) * dx}px, ${(1 - k) * dy}px) scale(${lerp(sc, 1, k)})`;
  }
  /* several elements, one visible per time slot: starts[i] .. starts[i+1] */
  function seq(els, t, starts, o = {}) {
    els.forEach((el, i) => show(el, t, starts[i], { ...o, out: i < els.length - 1 ? starts[i + 1] - 0.05 : Infinity }));
  }
  /* typing: reveals text at cps characters per second, with a caret while typing */
  function type(el, text, t, s, cps = 38) {
    if (!el) return;
    const n = Math.max(0, Math.min(text.length, Math.floor((t - s) * cps)));
    el.textContent = text.slice(0, n) + (t >= s && n < text.length ? '▌' : '');
    el.style.visibility = t >= s ? 'visible' : 'hidden';
  }
  /* SVG stroke drawing (the path needs pathLength="1") */
  function draw(el, t, s, d = 0.8, e = 'out') {
    if (!el) return;
    el.style.strokeDasharray = 1; el.style.strokeDashoffset = 1 - p(t, s, d, e);
    el.style.opacity = t >= s ? 1 : 0;
  }
  function count(el, a, b, t, s, d = 1.2, fmt = v => Math.round(v)) {
    if (!el) return;
    el.textContent = fmt(lerp(a, b, p(t, s, d, 'out')));
  }
  function set(el, props) { if (el) Object.assign(el.style, props); }
  /* pulse 0..1..0 around time c */
  const pulse = (t, c, w = 0.5) => Math.max(0, 1 - Math.abs(t - c) / w);
  return { clamp, lerp, ease, p, show, seq, type, draw, count, set, pulse };
})();

const CAIRN = (() => {
  let TL = null, DATA = null, stage = null, nodes = {}, capEl = null, chipEl = null, barEl = null, bgEl = null;
  const SCENES = window.SCENES = {};

  const strip = s => s.replace(/\*\*/g, '');
  const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const kw = s => esc(s).replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');

  /* caption chunks for one narrated line: <= 9 words, timed by character share */
  function chunks(line, start, dur) {
    const words = line.split(/\s+/); const out = []; let cur = [];
    const flush = () => { if (cur.length) { out.push(cur.join(' ')); cur = []; } };
    for (const w of words) {
      cur.push(w);
      const plain = strip(cur.join(' '));
      if (cur.length >= 9 || (/[.,;:!?]$/.test(w) && cur.length >= 4)) flush();
      else if (plain.length > 62) flush();
    }
    flush();
    const total = out.reduce((n, c) => n + strip(c).length, 0) || 1;
    let at = start;
    return out.map(c => { const d = dur * strip(c).length / total; const r = { s: at, e: at + d, html: kw(c) }; at += d; return r; });
  }

  function init(timeline, data) {
    TL = timeline; DATA = data;
    stage = document.getElementById('stage');
    capEl = document.getElementById('cap'); chipEl = document.getElementById('chip'); barEl = document.getElementById('bar'); bgEl = document.getElementById('bg');
    let chap = 0;
    for (const sc of TL.scenes) {
      const root = document.createElement('section');
      root.className = 'scene'; root.id = 's_' + sc.id; stage.appendChild(root);
      sc.root = root; sc.chapterNo = sc.chapter ? ++chap : 0;
      sc.caps = [];
      sc.lines.forEach((ln, i) => sc.caps.push(...chunks(ln, sc.L[i], sc.D[i])));
      const def = SCENES[sc.id];
      if (!def) throw new Error('no scene code for ' + sc.id);
      sc.X = { id: sc.id, L: sc.L, D: sc.D, dur: sc.dur, data: DATA, root, q: k => root.querySelector(`[data-k="${k}"]`), qa: k => [...root.querySelectorAll(`[data-k="${k}"]`)] };
      def.build(root, sc.X);
    }
    const imgs = [...document.images];
    return Promise.all([document.fonts.ready, ...imgs.map(i => (i.complete ? Promise.resolve() : new Promise(r => { i.onload = i.onerror = r; })))]).then(() => true);
  }

  function renderAt(T) {
    const sc = TL.scenes.find(s => T >= s.start && T < s.start + s.dur) || TL.scenes[TL.scenes.length - 1];
    const t = T - sc.start;
    for (const s of TL.scenes) s.root.style.display = s === sc ? 'block' : 'none';
    sc.root.style.opacity = Math.min(E.p(t, 0, 0.45), 1 - E.p(t, sc.dur - 0.4, 0.4));
    SCENES[sc.id].draw(t, sc.X);
    // chapter chip, progress bar, slow drifting glow, caption
    chipEl.textContent = sc.chapter ? `${String(sc.chapterNo).padStart(2, '0')}  ·  ${sc.chapter}` : '';
    chipEl.style.opacity = sc.chapter ? Math.min(E.p(t, 0.3, 0.5), 1 - E.p(t, sc.dur - 0.4, 0.4)) : 0;
    barEl.style.width = (100 * T / TL.total) + '%';
    bgEl.style.transform = `translate(${Math.sin(T * 0.11) * 90}px, ${Math.cos(T * 0.08) * 40}px) scale(${1 + 0.04 * Math.sin(T * 0.05)})`;
    const c = sc.caps.find(c => t >= c.s && t < c.e + 0.04);
    if (c) { capEl.innerHTML = c.html; capEl.style.opacity = Math.min(1, E.p(t, c.s, 0.18)); capEl.style.display = 'block'; }
    else capEl.style.display = 'none';
    return sc.id;
  }

  return { init, renderAt, SCENES };
})();
window.CAIRN = CAIRN;
