'use strict';
/* The scenes, as code. Each scene has build(root, X) (make the DOM once) and draw(t, X) (set every style for local time t).
 * X.L[i] / X.D[i] are the start and length of narrated line i, so cues land on the words. */
const S = CAIRN.SCENES;
const { show, seq, type, draw, count, set, p, pulse, lerp, clamp } = E;
const H = (s, k) => s.q(k);

/* a small stack of three stones: the Cairn mark */
const STONES = (size, id) => `<svg width="${size}" height="${size}" viewBox="0 0 22 22" fill="none" stroke="#ab8ff1" stroke-width="1.1">
  <rect data-k="${id}1" x="2" y="15" width="18" height="5" rx="2.5" style="transform-box:fill-box"/>
  <rect data-k="${id}2" x="5" y="9" width="12" height="5" rx="2.5" style="transform-box:fill-box"/>
  <rect data-k="${id}3" x="8" y="3" width="6" height="5" rx="2.5" style="transform-box:fill-box"/></svg>`;
function stones(X, id, t, s) {  // three stones drop in one after another
  [1, 2, 3].forEach(i => {
    const el = X.q(id + i), st = s + (i - 1) * 0.28, a = p(t, st, 0.55, 'back');
    el.style.opacity = t >= st ? 1 : 0; el.style.transform = `translateY(${(1 - a) * -9}px)`;
  });
}
const shot = (name, x, y, w, extra = '') => `<div class="shot" data-k="${name}" style="left:${x}px;top:${y}px;width:${w}px;height:${Math.round(w * 9 / 16)}px;${extra}">
  <img src="assets/${name.replace(/^sh_/, '')}.png" style="width:${w}px"></div>`;
/* a ring around a part of a captured screenshot: box = [x, y, w, h] in the 1920x1080 capture */
const ring = (X, key, box, scale, x0, y0, cls = '') => `<div class="ring ${cls}" data-k="${key}" style="left:${x0 + box[0] * scale - 6}px;top:${y0 + box[1] * scale - 5}px;width:${box[2] * scale + 12}px;height:${box[3] * scale + 10}px"></div>`;

/* ------------------------------------------------------------------------------------------------ 1. hook */
S.hook = {
  build(root) {
    root.innerHTML = `
      <div class="abs center big" data-k="l0" style="top:390px">AI can design a <span class="kw">laptop</span>.</div>
      <div class="abs center mid" data-k="l1" style="top:390px;padding:0 240px;color:var(--pearl);line-height:1.2">It can write the code, plan the supply chain,<br>even draw the circuit board.</div>
      <div class="abs center big" data-k="l2" style="top:350px">But ask it to take one <span class="red">apart</span>,<br><span style="color:var(--pearl)">and it falls over.</span></div>
      <div class="abs center" data-k="logo" style="top:150px">
        ${STONES(190, 's')}
        <div class="big" style="font-size:200px;letter-spacing:-10px;margin-top:6px">Cairn</div>
        <div data-k="tagl" style="font-size:54px;color:var(--pearl);letter-spacing:-1px;margin-top:4px">Object permanence for physical repair.</div>
      </div>`;
  },
  draw(t, X) {
    const L = X.L, q = X.q;
    show(q('l0'), t, L[0], { dy: 40, d: 0.8, out: L[1] - 0.05 });
    show(q('l1'), t, L[1], { dy: 40, d: 0.8, out: L[2] - 0.05 });
    show(q('l2'), t, L[2], { dy: 40, d: 0.8, out: L[3] - 0.05 });
    show(q('logo'), t, L[3], { dy: 0, d: 0.3 });
    stones(X, 's', t, L[3]);
    show(q('tagl'), t, L[3] + 1.0, { dy: 24 });
  },
};

/* ------------------------------------------------------------------------------------------------ 2. problem */
S.problem = {
  build(root) {
    root.innerHTML = `
      <div class="abs center mid" data-k="head" style="top:120px">Recognition is <span class="kw">not</span> memory</div>
      <div class="card abs" data-k="cam" style="left:120px;top:250px;width:860px;height:520px;padding:0;overflow:hidden">
        <div class="mono" data-k="frame" style="position:absolute;left:22px;top:18px;font-size:26px;color:var(--pearl)">frame 41</div>
        <div class="mono" style="position:absolute;right:22px;top:18px;font-size:22px;color:var(--fog)">camera view</div>
        <div data-k="obj" style="position:absolute;left:0;top:210px;width:150px;height:150px">
          <svg width="150" height="150" viewBox="0 0 150 150"><circle cx="75" cy="75" r="40" fill="#25252d" stroke="#aeaac0" stroke-width="3"/>
            <path d="M52 75h46M75 52v46" stroke="#dad7de" stroke-width="6" stroke-linecap="round"/></svg>
          <div data-k="box" style="position:absolute;left:-6px;top:-6px;width:162px;height:162px;border:3px dashed var(--v);border-radius:8px"></div>
          <div class="mono" data-k="lab" style="position:absolute;left:-6px;top:-40px;font-size:24px;color:var(--v);white-space:nowrap">screw 0.82</div>
        </div>
        <div class="mono" data-k="qm" style="position:absolute;left:620px;top:200px;font-size:140px;color:var(--fog)">?</div>
      </div>
      <div class="card abs" data-k="rp1" style="left:1040px;top:250px;width:760px;height:520px">
        <h3>What recognition remembers</h3>
        <div class="mono" style="font-size:30px;line-height:2.1;margin-top:18px">
          <div data-k="r1">frame 41&nbsp;&nbsp;&nbsp;screw 0.82</div>
          <div data-k="r2" style="color:var(--fog)">frame 42&nbsp;&nbsp;&nbsp;(nothing)</div>
          <div data-k="r3" style="color:var(--fog)">frame 43&nbsp;&nbsp;&nbsp;(nothing)</div>
          <div data-k="r4" style="color:var(--red)">the screw no longer exists</div>
        </div>
      </div>
      <div class="card abs" data-k="rp2" style="left:1040px;top:250px;width:760px;height:520px;border-color:var(--v)">
        <h3 class="kw">What Cairn remembers</h3>
        <div class="mono" style="font-size:30px;line-height:1.75;margin-top:14px">
          <div>p_17 &middot; M2x4 battery screw</div>
          <div style="color:var(--pearl)">last seen 11:43:48, in a hand</div>
        </div>
        <div style="margin-top:20px"><span class="chip r" style="font-size:30px;padding:10px 22px">LOST</span> <span class="chip d" style="font-size:30px;padding:10px 22px">still on the books</span></div>
        <div data-k="still" class="kw" style="font-size:68px;font-weight:600;letter-spacing:-2px;margin-top:34px">It still exists.</div>
      </div>`;
  },
  draw(t, X) {
    const L = X.L, q = X.q;
    show(q('head'), t, L[0], { dy: 24 });
    show(q('cam'), t, L[0] + 0.25, { dy: 30 });
    show(q('rp1'), t, L[1], { dy: 30, out: L[3] - 0.05 });
    // the screw: sits in view, then slides out of the frame during line 2
    const m = p(t, L[2], 1.9, 'inout');
    const x = lerp(260, 1000, m);
    set(q('obj'), { left: x + 'px' });
    show(q('obj'), t, L[0] + 0.5, { dy: 0, d: 0.5 });
    q('obj').style.transform = '';
    const boxA = (1 - p(t, L[2] + 1.15, 0.3)) * p(t, L[1], 0.4);
    set(q('box'), { opacity: boxA }); set(q('lab'), { opacity: boxA });
    q('frame').textContent = 'frame ' + (41 + Math.floor(Math.max(0, t - L[2]) / 0.3));
    show(q('qm'), t, L[2] + 1.6, { dy: 0, sc: 0.7, d: 0.5, e: 'back' });
    show(q('r1'), t, L[1], { dy: 10 });
    show(q('r2'), t, L[2] + 1.1, { dy: 10 }); show(q('r3'), t, L[2] + 1.5, { dy: 10 }); show(q('r4'), t, L[2] + 2.3, { dy: 10 });
    show(q('rp2'), t, L[3], { dy: 30 });
    show(q('still'), t, L[3] + 1.8, { dy: 16, sc: 0.9, e: 'back' });
  },
};

/* ------------------------------------------------------------------------------------------------ 3. what */
S.what = {
  build(root) {
    // a deterministic QR-like glyph for the passport card
    let qr = '';
    for (let r = 0; r < 11; r++) for (let c = 0; c < 11; c++) {
      const finder = (r < 3 && c < 3) || (r < 3 && c > 7) || (r > 7 && c < 3);
      const on = finder ? !(r % 2 === 1 && c % 2 === 1 && ((r === 1 && c === 1) === false)) || (r === 1 && c === 1) : ((r * 7 + c * 13 + r * c) % 5) < 2;
      qr += `<i style="background:${on ? '#dad7de' : 'transparent'}"></i>`;
    }
    root.innerHTML = `
      <div class="abs center big" data-k="head" style="top:130px;font-size:92px">A memory layer for <span class="kw">physical repair</span></div>
      <div data-k="g1" class="abs" style="left:120px;top:330px;width:1680px">
        <div class="row" style="gap:36px;justify-content:center">
          <div class="card" data-k="c1" style="width:500px;height:230px"><h3 class="kw">Identity</h3><p>which part is which, even after it leaves the frame</p></div>
          <div class="card" data-k="c2" style="width:500px;height:230px"><h3 class="kw">Place</h3><p>on the device, in a hand, in a tray well, or nowhere we can see</p></div>
          <div class="card" data-k="c3" style="width:500px;height:230px"><h3 class="kw">State</h3><p>installed, in transit, removed, lost, reinstalled, retired</p></div>
        </div>
        <div style="margin:44px 40px 0;height:10px;border-radius:5px;background:rgba(174,170,192,.18);position:relative"><div data-k="tbar" style="position:absolute;left:0;top:0;height:10px;width:0;border-radius:5px;background:var(--v)"></div></div>
        <div class="sub" style="margin:18px 40px 0;text-align:center">the whole teardown, remembered</div>
      </div>
      <div data-k="g2" class="abs" style="left:120px;top:290px;width:1680px">
        <div class="row" style="gap:36px;justify-content:center">
          <div class="card" data-k="w1" style="width:500px;height:330px"><span class="chip f">1 &middot; first</span><h3 style="margin-top:18px">Independent repair shops</h3><p>where lost parts and skipped steps cost money every week</p></div>
          <div class="card" data-k="w2" style="width:500px;height:330px"><span class="chip">2 &middot; next</span><h3 style="margin-top:18px">Refurbishers and recyclers</h3><p>thousands of devices, each needing proof of what was done</p></div>
          <div class="card" data-k="w3" style="width:500px;height:330px"><span class="chip d">3 &middot; later</span><h3 style="margin-top:18px">Warranty and insurance</h3><p>a verified repair record instead of a dispute</p></div>
        </div>
      </div>
      <div data-k="pp" class="card abs" style="left:560px;top:290px;width:800px;height:440px;border-color:var(--v)">
        <div class="row" style="justify-content:space-between;align-items:flex-start">
          <div><div class="tag">Repair passport</div><div style="font-size:84px;font-weight:600;letter-spacing:-3px;margin-top:10px">VERIFIED</div>
            <div class="sub" style="margin-top:12px">23 / 23 fasteners<br>3 exceptions, all recorded<br>Ed25519-signed &middot; hash chain</div></div>
          <div style="display:grid;grid-template-columns:repeat(11,1fr);gap:2px;width:210px;height:210px;padding:10px;background:#17171c;border-radius:10px">${qr}</div>
        </div>
        <div class="credit" style="margin-top:22px">from the simulated demo job</div>
      </div>`;
  },
  draw(t, X) {
    const L = X.L, q = X.q;
    show(q('head'), t, L[0], { dy: 30, d: 0.8 });
    show(q('g1'), t, L[1] - 0.1, { dy: 0, d: 0.3, out: L[2] - 0.05 });
    [q('c1'), q('c2'), q('c3')].forEach((c, i) => show(c, t, L[1] + i * (X.D[1] / 3.2), { dy: 40, sc: 0.96 }));
    set(q('tbar'), { width: (100 * p(t, L[1] + 0.8, X.D[1] - 0.6, 'lin')) + '%' });
    show(q('g2'), t, L[2] - 0.1, { dy: 0, d: 0.3, out: L[3] - 0.05 });
    [q('w1'), q('w2'), q('w3')].forEach((c, i) => show(c, t, L[2] + 0.3 + i * (X.D[2] / 3.4), { dy: 40, sc: 0.96 }));
    show(q('pp'), t, L[3], { dy: 40, sc: 0.94 });
  },
};

/* ------------------------------------------------------------------------------------------------ 4. pipeline */
S.pipeline = {
  build(root) {
    const node = (k, x, y, w, h, b, s, cls = '') => `<div class="node ${cls}" data-k="${k}" style="left:${x}px;top:${y}px;width:${w}px;height:${h}px"><b>${b}</b><span>${s}</span></div>`;
    const arrow = (k, x, y, w) => `<div class="arrow" data-k="${k}" style="left:${x}px;top:${y}px;width:${w}px">&rarr;</div>`;
    root.innerHTML = `
      <div class="abs center mid" data-k="head" style="top:118px">Perception proposes. <span class="kw">The session decides.</span></div>
      ${node('n0', 120, 250, 280, 170, 'Camera', 'or a tap on the screen')}
      ${arrow('a0', 400, 305, 70)}
      ${node('n1', 470, 250, 280, 170, 'Perception', 'SAM 3.1 finds parts from a text prompt')}
      ${arrow('a1', 750, 305, 70)}
      ${node('n2', 820, 250, 280, 170, 'Session', 'identity, order, policy: what it means', 'k')}
      ${arrow('a2', 1100, 305, 70)}
      ${node('n3', 1170, 250, 280, 170, 'Event log', 'append-only, hash-chained', 'k')}
      ${arrow('a3', 1450, 305, 70)}
      ${node('n4', 1520, 250, 280, 170, 'Object graph', 'a view of the log')}
      <svg class="abs" style="left:0;top:0" width="1920" height="1080"><path data-k="elbow" pathLength="1" d="M1660 420 V470 H440 V520" fill="none" stroke="#ab8ff1" stroke-width="3"/></svg>
      ${node('n5', 230, 520, 420, 170, 'Safety kernel', '4 hard rules, outside the model', 'n')}
      ${arrow('a5', 650, 575, 100)}
      ${node('n6', 750, 520, 420, 170, 'Verification', '5 checks before a job can close')}
      ${arrow('a6', 1170, 575, 100)}
      ${node('n7', 1270, 520, 420, 170, 'Repair passport', 'signed, with a QR and a verify page', 'k')}
      <div class="abs" data-k="t1" style="left:470px;top:205px;width:280px;text-align:center"><span class="chip">proposes</span></div>
      <div class="abs" data-k="t2" style="left:820px;top:205px;width:280px;text-align:center"><span class="chip f">decides</span></div>
      <div class="abs" data-k="t3" style="left:1170px;top:205px;width:280px;text-align:center"><span class="chip">records</span></div>
      <div class="abs center" data-k="ban" style="top:760px"><span class="chip r" style="font-size:36px;padding:14px 30px">The model never writes.</span></div>`;
  },
  draw(t, X) {
    const L = X.L, q = X.q;
    show(q('head'), t, L[0], { dy: 24 });
    show(q('n0'), t, L[1], { dy: 30 }); show(q('a0'), t, L[1] + 0.5, { dy: 0, dx: -20 });
    show(q('n1'), t, L[1] + 0.9, { dy: 30 });
    show(q('n2'), t, L[2], { dy: 30 }); show(q('a1'), t, L[2] - 0.3, { dy: 0, dx: -20 });
    show(q('n3'), t, L[3], { dy: 30 }); show(q('a2'), t, L[3] - 0.3, { dy: 0, dx: -20 });
    show(q('n4'), t, L[3] + 1.6, { dy: 30 }); show(q('a3'), t, L[3] + 1.3, { dy: 0, dx: -20 });
    draw(q('elbow'), t, L[4], 1.2, 'inout');
    show(q('n5'), t, L[4] + 0.2, { dy: 30 }); show(q('a5'), t, L[4] + 1.2, { dy: 0, dx: -20 });
    show(q('n6'), t, L[4] + 1.5, { dy: 30 }); show(q('a6'), t, L[4] + 2.3, { dy: 0, dx: -20 });
    show(q('n7'), t, L[4] + 2.6, { dy: 30 });
    show(q('t1'), t, L[5], { dy: 12 }); show(q('t2'), t, L[5] + X.D[5] * 0.28, { dy: 12 }); show(q('t3'), t, L[5] + X.D[5] * 0.5, { dy: 12 });
    show(q('ban'), t, L[5] + X.D[5] * 0.72, { dy: 20, sc: 0.9, e: 'back' });
  },
};

/* ------------------------------------------------------------------------------------------------ 5. log */
S.log = {
  build(root, X) {
    const ch = X.data.chain; const EV = ch.events; const x0 = [120, 408, 696, 984, 1272, 1560];
    let html = `<div class="abs center mid" data-k="head" style="top:118px">An append-only, <span class="kw">hash-chained</span> log</div>`;
    EV.forEach((e, i) => {
      html += `<div class="node" data-k="b${i}" style="left:${x0[i]}px;top:230px;width:240px;height:262px;text-align:left;padding:14px 18px">
        <div class="mono" style="font-size:22px;color:var(--fog)">#${i + 1}</div>
        <div data-k="bt${i}" style="font-size:27px;line-height:1.2;margin:8px 0 14px;min-height:66px">${e}</div>
        <div class="mono" style="font-size:20px;color:var(--fog)">prev</div><div class="mono" data-k="bp${i}" style="font-size:24px">${ch.prev[i]}&hellip;</div>
        <div class="mono" style="font-size:20px;color:var(--fog);margin-top:8px">hash</div><div class="mono kw" data-k="bh${i}" style="font-size:24px">${ch.hash[i]}&hellip;</div>
      </div>`;
      if (i < 5) html += `<div class="abs mono" data-k="lk${i}" style="left:${x0[i] + 238}px;top:340px;width:52px;text-align:center;font-size:34px;color:var(--v)">&#8658;</div>`;
    });
    html += `
      <div class="abs" data-k="xmsg" style="left:120px;top:508px;width:1680px;text-align:center"><span class="chip r" style="font-size:30px;padding:10px 24px">change #4 and every link after it breaks</span></div>
      <div class="card abs" data-k="sql" style="left:120px;top:578px;width:640px;height:180px"><h3>SQLite</h3><p>updates and deletes are blocked at the database</p>
        <div style="margin-top:14px"><span class="chip r">UPDATE blocked</span> <span class="chip r">DELETE blocked</span></div></div>
      <div class="card abs" data-k="rp" style="left:820px;top:578px;width:980px;height:180px;border-color:var(--v)">
        <div class="row" style="gap:26px;justify-content:space-between">
          <div><div class="tag">restart the server</div><div class="mono" style="font-size:34px;margin-top:8px">graph = fold( log )</div></div>
          <div class="arrow" style="position:static;font-size:56px">&rarr;</div>
          <div><div style="font-size:34px;font-weight:600">ObjectGraph</div><div class="sub" style="font-size:28px">29 parts, state restored</div></div>
        </div></div>
      <div class="abs center" data-k="fin" style="top:782px"><span class="chip f" style="font-size:32px;padding:10px 26px">The memory is in the log, not in the model</span></div>
      <div class="credit abs" style="left:120px;top:850px">illustration: short hashes of a six-event chain, computed with SHA-256</div>`;
    root.innerHTML = html;
  },
  draw(t, X) {
    const L = X.L, q = X.q, ch = X.data.chain;
    show(q('head'), t, L[0], { dy: 24 });
    for (let i = 0; i < 6; i++) {
      show(q('b' + i), t, L[0] + 0.5 + i * 0.22, { dy: 30 });
      if (i < 5) show(q('lk' + i), t, L[0] + 0.7 + i * 0.22, { dy: 0, dx: -16 });
    }
    // tamper: event #4 is rewritten, so its hash changes and every later "prev" no longer matches
    const tamper = t >= L[1] + X.D[1] * 0.45;
    const k = p(t, L[1] + X.D[1] * 0.45, 0.5);
    q('bt3').textContent = tamper ? ch.tamperedText : ch.events[3];
    q('bh3').textContent = (tamper ? ch.tamperedHash : ch.hash[3]) + '…';
    for (let i = 3; i < 6; i++) {
      const bad = tamper && i >= 3;
      q('b' + i).style.borderColor = bad ? 'rgba(240,112,122,.85)' : '';
      if (i > 3) q('bp' + i).style.color = bad ? 'var(--red)' : '';
      if (i === 3) q('bh3').style.color = bad ? 'var(--red)' : '';
      if (i > 3) q('lk' + (i - 1)).style.color = bad ? 'var(--red)' : '';
    }
    q('lk3').style.color = tamper ? 'var(--red)' : '';
    show(q('xmsg'), t, L[1] + X.D[1] * 0.5, { dy: 12 });
    show(q('sql'), t, L[2], { dy: 30 });
    show(q('rp'), t, L[3], { dy: 30 });
    show(q('fin'), t, L[4], { dy: 20, sc: 0.92, e: 'back' });
  },
};

/* ------------------------------------------------------------------------------------------------ 6. graph */
S.graph = {
  build(root) {
    const st = (k, x, y, name, sub, cls = '') => `<div class="node ${cls}" data-k="${k}" style="left:${x}px;top:${y}px;width:250px;height:100px;padding:12px 10px"><b style="font-size:30px;margin-bottom:2px">${name}</b><span style="font-size:21px">${sub}</span></div>`;
    const lab = (k, x, y, txt, w = 220) => `<div class="abs" data-k="${k}" style="left:${x}px;top:${y}px;width:${w}px;font-size:22px;color:var(--pearl);text-align:center">${txt}</div>`;
    let wells = '';
    for (let i = 0; i < 24; i++) wells += `<div data-k="w${i}" style="width:74px;height:56px;border-radius:8px;border:1px solid var(--line);background:rgba(23,23,28,.6);font-size:18px;color:var(--fog);padding:4px 6px" class="mono">${String(i + 1).padStart(2, '0')}</div>`;
    root.innerHTML = `
      <div class="abs center mid" data-k="head" style="top:118px">Every part has an identity, a place and a <span class="kw">state</span></div>
      <svg class="abs" style="left:0;top:0" width="1920" height="1080">
        <defs><marker id="ah" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#ab8ff1"/></marker>
              <marker id="ahr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0 0L10 5L0 10z" fill="#f0707a"/></marker></defs>
        <path data-k="p1" pathLength="1" d="M370 320 H470" stroke="#ab8ff1" stroke-width="3" fill="none" marker-end="url(#ah)"/>
        <path data-k="p2" pathLength="1" d="M720 320 H820" stroke="#ab8ff1" stroke-width="3" fill="none" marker-end="url(#ah)"/>
        <path data-k="p3" pathLength="1" d="M595 370 V520" stroke="#f0707a" stroke-width="3" fill="none" marker-end="url(#ahr)"/>
        <path data-k="p4" pathLength="1" d="M945 370 V520" stroke="#ab8ff1" stroke-width="3" fill="none" marker-end="url(#ah)"/>
        <path data-k="p5" pathLength="1" d="M720 540 L840 372" stroke="#ab8ff1" stroke-width="3" stroke-dasharray="1" fill="none" marker-end="url(#ah)"/>
        <path data-k="p6" pathLength="1" d="M470 570 H370" stroke="#aeaac0" stroke-width="3" fill="none" marker-end="url(#ah)"/>
        <circle data-k="tok" r="9" fill="#ab8ff1" stroke="#fff" stroke-width="3" cx="134" cy="320"/>
      </svg>
      ${st('s0', 120, 270, 'INSTALLED', 'on the device')}
      ${st('s1', 470, 270, 'IN TRANSIT', 'in a hand')}
      ${st('s2', 820, 270, 'REMOVED', 'in a tray well')}
      ${st('s3', 120, 520, 'RETIRED', 'written off', '')}
      ${st('s4', 470, 520, 'LOST', 'unseen for 3 s', 'n')}
      ${st('s5', 820, 520, 'REINSTALLED', 'back on the device')}
      ${lab('l1', 360, 282, 'lifted', 120)}${lab('l2', 700, 282, 'placed', 140)}${lab('l3', 410, 432, 'unseen 3 s', 170).replace('text-align:center', 'text-align:right')}
      ${lab('l4', 950, 430, 'put back', 150)}${lab('l5', 800, 440, 'found', 110)}${lab('l6', 330, 590, 'retire', 140)}
      <div class="abs" data-k="trayh" style="left:1230px;top:232px"><span class="tag">Tray</span> <span class="sub" style="font-size:28px">24 numbered wells</span></div>
      <div class="abs" data-k="tray" style="left:1230px;top:280px;width:560px;display:grid;grid-template-columns:repeat(6,74px);gap:10px">${wells}</div>
      <div class="abs" data-k="tchip" style="left:1230px;top:570px"><span class="chip">29 parts</span> <span class="chip">23 fasteners</span> <span class="chip">12 kinds</span></div>
      <div class="card abs" data-k="timer" style="left:1230px;top:628px;width:560px;height:236px;border-color:rgba(240,112,122,.6)">
        <svg width="150" height="150" viewBox="0 0 150 150" style="position:absolute;left:24px;top:36px"><circle cx="75" cy="75" r="64" fill="none" stroke="rgba(174,170,192,.22)" stroke-width="12"/>
          <circle data-k="ring" cx="75" cy="75" r="64" fill="none" stroke="#f0707a" stroke-width="12" stroke-linecap="round" pathLength="1" transform="rotate(-90 75 75)"/></svg>
        <div class="mono num" data-k="tsec" style="position:absolute;left:24px;top:92px;width:150px;text-align:center;font-size:34px">0.0 s</div>
        <div style="position:absolute;left:204px;top:34px;width:330px"><span class="chip r" data-k="miss">MISSING 1</span>
          <div class="sub" style="font-size:26px;margin-top:12px">p_17, named, with the time it was last seen</div>
          <div data-k="sim" class="chip d" style="margin-top:12px;font-size:21px">simulated: slowest flag 2.75 s</div></div>
      </div>`;
  },
  draw(t, X) {
    const L = X.L, q = X.q, D = X.D;
    show(q('head'), t, L[0], { dy: 24 });
    ['s0', 's1', 's2', 's3', 's4', 's5'].forEach((k, i) => show(q(k), t, L[0] + 0.4 + i * 0.18, { dy: 24, sc: 0.95 }));
    ['p1', 'p2', 'p3', 'p4', 'p5', 'p6'].forEach((k, i) => draw(q(k), t, L[0] + 1.0 + i * 0.15, 0.6));
    ['l1', 'l2', 'l3', 'l4', 'l5', 'l6'].forEach((k, i) => show(q(k), t, L[0] + 1.4 + i * 0.15, { dy: 8 }));
    // the token walks installed -> in transit -> removed -> reinstalled during line 1
    const way = [[134, 320], [484, 320], [834, 320], [834, 570]]; const names = ['s0', 's1', 's2', 's5'];
    const seg = clamp((t - L[1]) / (D[1] - 0.4), 0, 0.9999) * 3; const i = Math.floor(seg), f = E.ease.inout(seg - i);
    const a = way[Math.min(i, 2)], b = way[Math.min(i + 1, 3)];
    const cx = t < L[1] ? way[0][0] : lerp(a[0], b[0], f), cy = t < L[1] ? way[0][1] : lerp(a[1], b[1], f);
    set(q('tok'), { }); q('tok').setAttribute('cx', cx); q('tok').setAttribute('cy', cy);
    names.forEach((n, j) => { const on = t >= L[1] && Math.round(seg) === j; q(n).style.borderColor = on ? 'var(--v)' : ''; q(n).style.background = on ? 'rgba(171,143,241,.18)' : ''; });
    // tray fills during line 2
    show(q('trayh'), t, L[2] - 0.2, { dy: 16 }); show(q('tray'), t, L[2] - 0.1, { dy: 16 }); show(q('tchip'), t, L[2] + 0.6, { dy: 16 });
    const filled = Math.floor(23 * p(t, L[2] + 0.2, D[2] - 0.6, 'lin'));
    for (let w = 0; w < 24; w++) { const on = w < filled; const el = q('w' + w); el.style.background = on ? 'rgba(171,143,241,.28)' : 'rgba(23,23,28,.6)'; el.style.borderColor = on ? 'var(--v)' : ''; el.style.color = on ? '#fff' : ''; }
    // the 3-second timer, then the measured number
    show(q('timer'), t, L[3], { dy: 24 });
    const k = p(t, L[3] + 0.4, 2.4, 'lin');
    set(q('ring'), { }); q('ring').style.strokeDasharray = 1; q('ring').style.strokeDashoffset = 1 - k;
    q('tsec').textContent = (3 * k).toFixed(1) + ' s';
    show(q('miss'), t, L[3] + 2.8, { dy: 0, sc: 0.7, e: 'back', d: 0.5 });
    q('s4').style.borderColor = t >= L[3] + 2.8 ? 'var(--red)' : ''; q('s4').style.background = t >= L[3] + 2.8 ? 'rgba(240,112,122,.2)' : '';
    show(q('sim'), t, L[4], { dy: 12 });
  },
};

/* ------------------------------------------------------------------------------------------------ 7. safety */
S.safety = {
  build(root) {
    const rule = (k, x, y, id, title, why) => `<div class="card" data-k="${k}" style="position:absolute;left:${x}px;top:${y}px;width:520px;height:200px;border-color:rgba(240,112,122,.5)">
      <div class="tag red" style="color:var(--red)">${id}</div><h3 style="margin-top:6px">${title}</h3><p>${why}</p></div>`;
    root.innerHTML = `
      <div class="abs center mid" data-k="head" style="top:118px">Four rules in code, <span class="kw">outside</span> the model</div>
      ${rule('r0', 120, 240, 'K1', 'ESD strap on', 'Static can silently kill a board.')}
      ${rule('r1', 670, 240, 'K2', 'Battery disconnected', 'A live battery can short a board.')}
      ${rule('r2', 120, 470, 'K3', 'Hazard halt', 'Smoke, heat or swelling: stop all work.')}
      ${rule('r3', 670, 470, 'K4', 'No prying near a battery', 'A punctured cell can ignite.')}
      <div class="abs" data-k="gate" style="left:1250px;top:240px;width:550px">
        <div class="node" style="position:static;height:96px;padding:16px"><b style="font-size:30px;margin:0">remove ssd_screw_01</b></div>
        <div class="arrow" style="position:static;transform:rotate(90deg);font-size:44px;margin:4px 0">&rarr;</div>
        <div class="node n" style="position:static;height:120px;padding:16px"><b style="font-size:34px">Safety kernel</b><span>checked before every removal</span></div>
        <div class="row" style="gap:20px;justify-content:center;margin-top:18px"><span class="chip">allowed</span><span class="chip r">blocked</span></div>
      </div>
      <div class="card abs" data-k="demo" style="left:1250px;top:240px;width:550px;height:480px;border-color:var(--red);background:rgba(240,112,122,.07)">
        <div class="mono" data-k="cmd" style="font-size:25px;color:var(--pearl);min-height:34px"></div>
        <div data-k="verd" style="margin-top:22px"><span class="chip r" style="font-size:34px;padding:10px 22px">BLOCKED &middot; K2_POWER_OFF</span></div>
        <div data-k="why" class="sub" style="margin-top:20px;font-size:29px;color:var(--ink)">Disconnect the battery before removing any internal component; a live battery can short a board.</div>
        <div data-k="rec" style="margin-top:22px"><span class="chip d">on the passport: safety_violation x001</span></div>
        <div data-k="red" class="sub" style="margin-top:14px;font-size:26px">The step card turns red.</div>
      </div>`;
  },
  draw(t, X) {
    const L = X.L, q = X.q, D = X.D;
    show(q('head'), t, L[0], { dy: 24 });
    ['r0', 'r1', 'r2', 'r3'].forEach((k, i) => show(q(k), t, L[1] + i * (D[1] / 4.4), { dy: 30, sc: 0.96 }));
    show(q('gate'), t, L[2], { dy: 24, out: L[3] - 0.05 });
    show(q('demo'), t, L[3], { dy: 24 });
    type(q('cmd'), 'guard( remove, ssd_screw_01 )', t, L[3] + 0.2, 34);
    show(q('verd'), t, L[3] + 1.4, { dy: 0, sc: 0.8, e: 'back', d: 0.45 });
    show(q('why'), t, L[3] + 2.0, { dy: 12 }); show(q('rec'), t, L[3] + 3.2, { dy: 12 }); show(q('red'), t, L[3] + 4.0, { dy: 12 });
    q('demo').style.borderColor = 'rgba(240,112,122,' + (0.5 + 0.5 * pulse(t, L[3] + 1.6, 0.5)) + ')';
  },
};

/* ------------------------------------------------------------------------------------------------ 8. demo */
/* camera.push: place a 1920x1080 capture in a box and move/zoom it between keyframes ({at, cx, cy, z, d}) */
function camera(layer, t, keys, boxW, boxH) {
  const s = boxW / 1920; let prev = { cx: 960, cy: 540, z: 1 }, cur = prev;
  for (const k of keys) { if (t < k.at) break; const f = p(t, k.at, k.d || 1.0, 'inout'); cur = { cx: lerp(prev.cx, k.cx, f), cy: lerp(prev.cy, k.cy, f), z: lerp(prev.z, k.z, f) }; prev = k; }
  layer.style.transform = `translate(${boxW / 2 - cur.cx * s * cur.z}px, ${boxH / 2 - cur.cy * s * cur.z}px) scale(${s * cur.z})`;
}
S.demo = {
  build(root, X) {
    const M = X.data.meta, BW = 1180, BH = 664, x0 = 120, y0 = 190;
    const rg = (name, sel, cls = '') => { const b = M[name].boxes[sel]; return `<div class="ring ${cls}" data-k="${name}|${sel}" style="left:${b[0] - 6}px;top:${b[1] - 5}px;width:${b[2] + 12}px;height:${b[3] + 10}px;border-width:5px"></div>`; };
    const panel = (k, name, rings) => `<div data-k="${k}" class="abs" style="left:0;top:0;width:1920px;height:1080px">
      <div class="shot" style="left:${x0}px;top:${y0}px;width:${BW}px;height:${BH}px"><div data-k="ly${k}" style="position:absolute;left:0;top:0;width:1920px;height:1080px;transform-origin:0 0">
        <img src="assets/${name}.png" style="width:1920px">${rings}</div></div></div>`;
    const W16 = '#wells > :nth-child(16)';
    root.innerHTML = `
      <div class="abs center mid" data-k="head" style="top:118px">The scripted demo, replayed in the <span class="kw">real app</span></div>
      ${panel('A', 'bench_drop', rg('bench_drop', '#st-miss', 'r') + rg('bench_drop', '#parts-out') + rg('bench_drop', '.ev.sel'))}
      ${panel('B', 'bench_wrong', rg('bench_wrong', W16, 'r') + rg('bench_wrong', '.ev.sel'))}
      ${panel('C', 'bench_lunch', rg('bench_lunch', '.ev.sel') + rg('bench_lunch', '#step'))}
      <div class="chip d abs" style="left:132px;top:${y0 + BH + 14}px;font-size:21px">simulated replay of the demo job &middot; a real screenshot of the app</div>
      <div class="card abs" data-k="tA" style="left:1340px;top:190px;width:460px;height:664px"><span class="tag">1 &middot; the drop</span>
        <div class="mono" style="font-size:25px;line-height:1.4;margin-top:16px;color:var(--ink)">p_17 M2x4 battery screw left the bench at 11:43 and did not arrive in a tray well.</div>
        <div style="margin-top:20px"><span class="chip r" style="font-size:30px">MISSING 1</span></div>
        <div class="sub" style="margin-top:20px;font-size:27px">The board names the part and the last time it was seen.</div></div>
      <div class="card abs" data-k="tB" style="left:1340px;top:190px;width:460px;height:664px"><span class="tag">2 &middot; the wrong screw</span>
        <div class="mono" style="font-size:25px;line-height:1.4;margin-top:16px;color:var(--ink)">That's a 3mm M2x3 SSD screw. That hole takes a 5mm. Tray 16.</div>
        <div style="margin-top:20px"><span class="chip">3 mm screw</span> <span class="chip r">5 mm hole</span></div>
        <div class="sub" style="margin-top:20px;font-size:27px">The right tray well is called out, and the attempt is on the record.</div></div>
      <div class="card abs" data-k="tC" style="left:1340px;top:190px;width:460px;height:664px"><span class="tag">3 &middot; the return</span>
        <div class="mono" style="font-size:25px;line-height:1.4;margin-top:16px;color:var(--ink)">30 minutes later. Found p_17 M2x4 battery screw, placed in tray 11.</div>
        <div style="margin-top:20px"><span class="chip">same next step</span> <span class="chip">same counts</span></div>
        <div class="sub" style="margin-top:20px;font-size:27px">The missing screw was never forgotten, and the job carries on exactly where it stopped.</div></div>`;
  },
  draw(t, X) {
    const L = X.L, D = X.D, q = X.q, BW = 1180, BH = 664;
    const ring = (name, sel) => q(name + '|' + sel);
    show(q('head'), t, L[0], { dy: 24 });
    show(q('A'), t, L[1], { dy: 0, d: 0.5, out: L[2] - 0.05 }); show(q('B'), t, L[2], { dy: 0, d: 0.5, out: L[3] - 0.05 }); show(q('C'), t, L[3], { dy: 0, d: 0.5 });
    ['A', 'B', 'C'].forEach(k => { q(k).style.transform = ''; });
    // 1 the drop: the counter and left panel, then the timeline entry
    const a1 = L[1] + 0.6, a2 = L[1] + D[1] * 0.55;
    camera(q('lyA'), t, [{ at: a1, cx: 240, cy: 190, z: 2.3 }, { at: a2, cx: 1500, cy: 880, z: 2.1 }, { at: L[2] - 0.9, cx: 960, cy: 540, z: 1, d: 0.8 }], BW, BH);
    show(ring('bench_drop', '#st-miss'), t, a1 + 0.9, { dy: 0, sc: 1.2, d: 0.4 }); show(ring('bench_drop', '#parts-out'), t, a1 + 1.5, { dy: 0, sc: 1.2, d: 0.4 });
    show(ring('bench_drop', '.ev.sel'), t, a2 + 0.9, { dy: 0, sc: 1.2, d: 0.4 });
    // 2 the wrong screw: tray well 16, then the timeline
    const b1 = L[2] + 0.6, b2 = L[2] + D[2] * 0.55;
    camera(q('lyB'), t, [{ at: b1, cx: 150, cy: 205, z: 3.0 }, { at: b2, cx: 1500, cy: 880, z: 2.1 }, { at: L[3] - 0.9, cx: 960, cy: 540, z: 1, d: 0.8 }], BW, BH);
    show(ring('bench_wrong', '#wells > :nth-child(16)'), t, b1 + 0.9, { dy: 0, sc: 1.4, d: 0.4 }); show(ring('bench_wrong', '.ev.sel'), t, b2 + 0.9, { dy: 0, sc: 1.2, d: 0.4 });
    // 3 the return: the log entry, then the unchanged next-step card
    const c1 = L[3] + 0.7, c2 = L[3] + D[3] * 0.5;
    camera(q('lyC'), t, [{ at: c1, cx: 1500, cy: 880, z: 2.1 }, { at: c2, cx: 670, cy: 890, z: 2.1 }], BW, BH);
    show(ring('bench_lunch', '.ev.sel'), t, c1 + 0.9, { dy: 0, sc: 1.2, d: 0.4 }); show(ring('bench_lunch', '#step'), t, c2 + 0.9, { dy: 0, sc: 1.2, d: 0.4 });
    show(q('tA'), t, L[1] + 0.2, { dy: 24, out: L[2] - 0.05 }); show(q('tB'), t, L[2] + 0.2, { dy: 24, out: L[3] - 0.05 }); show(q('tC'), t, L[3] + 0.2, { dy: 24 });
  },
};

/* ------------------------------------------------------------------------------------------------ 9. passport */
S.passport = {
  build(root, X) {
    const rows = [['Count', 'every removed fastener is reinstalled or retired'], ['Order', 'no step ran before its preconditions'], ['Safety', 'power off before component removal; no active hazard'],
      ['Closure', 'tray empty; no extra parts'], ['Function', 'boot test passed']];
    let r = ''; rows.forEach((x, i) => { r += `<div class="card" data-k="ck${i}" style="position:absolute;left:120px;top:${230 + i * 100}px;width:800px;height:84px;padding:12px 24px">
      <div class="row" style="justify-content:space-between"><div><b style="font-size:32px">${x[0]}</b><div style="font-size:23px;color:var(--pearl)">${x[1]}</div></div><span class="chip f" data-k="pass${i}">PASS</span></div></div>`; });
    const s1 = 0.78, ps = (name, x, y, w, h, ox, oy, sc, k) => `<div class="shot" data-k="${k}" style="left:${x}px;top:${y}px;width:${w}px;height:${h}px;background:#fff"><img src="assets/${name}.png" style="width:${1920 * sc}px;left:${-ox * sc}px;top:${-oy * sc}px"></div>`;
    root.innerHTML = `
      <div class="abs center mid" data-k="head" style="top:118px">Five checks, then a <span class="kw">signed passport</span></div>
      ${r}
      ${ps('passport', 1010, 220, 640, 600, 545, 20, s1, 'pp')}
      <div class="card abs" data-k="tam" style="left:1040px;top:610px;width:760px;height:230px;border-color:var(--red);background:rgba(13,13,18,.96)">
        <div class="mono" style="font-size:27px;color:var(--pearl)">counts.fasteners_accounted</div>
        <div class="mono" style="font-size:34px;margin-top:6px"><span style="color:var(--fog)">23</span> &rarr; <span class="red" data-k="v99">99</span></div>
        <div class="mono red" data-k="inv" style="font-size:27px;margin-top:16px;line-height:1.3">INVALID: signature does not match the passport body</div></div>
      ${ps('verify', 1000, 250, 760, 330, 270, 80, 0.78, 'ver')}
      <div class="abs" data-k="vchip" style="left:1000px;top:610px"><span class="chip f" style="font-size:30px">scan the QR &rarr; RECORD INTACT</span></div>`;
  },
  draw(t, X) {
    const L = X.L, q = X.q, D = X.D;
    show(q('head'), t, L[0], { dy: 24 });
    [0, 1, 2, 3, 4].forEach(i => {
      show(q('ck' + i), t, L[0] + 0.6 + i * 0.25, { dy: 24 });
      const on = t >= L[1] + 0.4 + i * (D[1] / 5.5);
      show(q('pass' + i), t, L[1] + 0.4 + i * (D[1] / 5.5), { dy: 0, sc: 0.6, e: 'back', d: 0.4 });
    });
    show(q('pp'), t, L[2], { dy: 30, sc: 0.97, out: L[4] - 0.05 });
    show(q('tam'), t, L[3] + 0.6, { dy: 24, out: L[4] - 0.05 });
    q('v99').style.opacity = 1; show(q('inv'), t, L[3] + 2.2, { dy: 8 });
    show(q('ver'), t, L[4], { dy: 30, sc: 0.97 }); show(q('vchip'), t, L[4] + 1.0, { dy: 12 });
  },
};

/* ------------------------------------------------------------------------------------------------ 10. open bench */
S.open = {
  build(root) {
    const chips = w => w.map(x => `<span class="chip" style="margin:0 8px 10px 0">${x}</span>`).join('');
    const chipsR = w => w.map(x => `<span class="chip r" style="margin:0 8px 10px 0">${x}</span>`).join('');
    root.innerHTML = `
      <div class="abs center mid" data-k="head" style="top:118px">Open bench: <span class="kw">any laptop</span>, no task list</div>
      <div class="shot" data-k="img" style="left:120px;top:210px;width:1000px;height:563px"><img src="assets/sam_overlay.jpg" style="width:1000px;height:563px"></div>
      <div class="chip abs" style="left:136px;top:226px;font-size:21px;background:rgba(8,8,10,.85)">REAL PHOTO &middot; SAM 3.1 live call</div>
      <div class="credit abs" style="left:120px;top:786px;width:1000px">"Laptop open servicing" by Solutionservice21, Wikimedia Commons, CC BY-SA 4.0 (creativecommons.org/licenses/by-sa/4.0). SAM's boxes added.</div>
      <div class="card abs" data-k="asks" style="left:1180px;top:210px;width:620px;height:300px"><div class="tag">SAM is asked for</div>
        <div style="margin-top:16px">${chips(['laptop', 'screw', 'fan', 'cable', 'circuit board'])}</div>
        <div class="sub" style="font-size:27px;margin-top:12px">Each thing found gets a slot (p_01, p_02 &hellip;) and is tracked from picture to picture.</div></div>
      <div class="card abs" data-k="nar" style="left:1180px;top:210px;width:620px;height:420px;border-color:var(--v)"><div class="tag">Example narration (format)</div>
        <div class="mono" data-k="n1" style="font-size:26px;line-height:1.35;margin-top:18px;min-height:72px"></div>
        <div class="mono" data-k="n2" style="font-size:26px;line-height:1.35;margin-top:12px;min-height:72px"></div>
        <div class="mono" data-k="n3" style="font-size:26px;line-height:1.35;margin-top:12px;min-height:72px"></div></div>
      <div class="card abs" data-k="fnd" style="left:1180px;top:210px;width:620px;height:520px"><div class="tag">Found on real photos</div>
        <div style="margin-top:14px">${chips(['laptop', 'screw', 'fan', 'cable', 'circuit board'])}</div>
        <div class="tag red" style="color:var(--red);margin-top:14px">Not found</div>
        <div style="margin-top:14px">${chipsR(['battery', 'hard drive', 'back cover', 'memory'])}</div>
        <div data-k="close" class="sub" style="margin-top:14px;font-size:30px;color:var(--ink)">Screws only show up when the camera is <b class="kw">close</b>.</div></div>`;
  },
  draw(t, X) {
    const L = X.L, q = X.q;
    show(q('head'), t, L[0], { dy: 24 });
    show(q('img'), t, L[0] + 0.3, { dy: 30 });
    show(q('asks'), t, L[1], { dy: 24, out: L[2] - 0.05 });
    show(q('nar'), t, L[2], { dy: 24, out: L[3] - 0.05 });
    type(q('n1'), 'I can see 31 screws, 1 fan on the laptop.', t, L[2] + 0.4, 30);
    type(q('n2'), 'Removed screw p_07. 30 screws still on the laptop.', t, L[2] + 2.0, 30);
    type(q('n3'), 'Screw p_07 is no longer on the laptop (not seen for 9 s).', t, L[2] + 3.6, 30);
    show(q('fnd'), t, L[3], { dy: 24 });
    const z = 1 + 0.22 * p(t, L[4], 3.0, 'inout');
    q('img').firstElementChild.style.transformOrigin = '30% 35%'; q('img').firstElementChild.style.transform = `scale(${z})`;
    show(q('close'), t, L[4], { dy: 12 });
  },
};

/* ------------------------------------------------------------------------------------------------ 11. models */
S.models = {
  build(root) {
    const card = (k, x, y, name, role, status, cls) => `<div class="card" data-k="${k}" style="position:absolute;left:${x}px;top:${y}px;width:800px;height:240px"><h3>${name}</h3>
      <p>${role}</p><div style="margin-top:16px"><span class="chip ${cls}" style="font-size:22px">${status}</span></div></div>`;
    root.innerHTML = `
      <div class="abs center mid" data-k="head" style="top:118px">Each model has one <span class="kw">narrow job</span></div>
      ${card('m0', 120, 240, 'SAM 3.1 &middot; the eyes', 'Turns pictures into detections: boxes, masks and labels from a text prompt. Nothing else.', 'live calls 2&ndash;3 Nov &middot; refused for billing since 3 Nov', 'r')}
      ${card('m1', 1000, 240, 'Muse Wonder &middot; the agent', 'Reads the graph and proposes the next step, but only a step the graph lists as legal. It has no tool that writes.', 'tool loop verified live on 2 Nov (simulated session)', '')}
      ${card('m2', 120, 520, 'Muse Glimmer &middot; the local option', 'Keeps bench video on the bench, with a privacy mode that refuses cloud components.', 'client and privacy mode tested on a fake &middot; no model run', 'd')}
      ${card('m3', 1000, 520, 'Voice', 'Push to talk and spoken alerts use the browser&rsquo;s own speech today.', 'Muse Voice not integrated', 'r')}`;
  },
  draw(t, X) {
    const L = X.L, q = X.q;
    show(q('head'), t, L[0], { dy: 24 });
    ['m0', 'm1', 'm2', 'm3'].forEach((k, i) => show(q(k), t, L[i + 1] + 0.1, { dy: 36, sc: 0.96 }));
  },
};

/* ------------------------------------------------------------------------------------------------ 12. honest */
S.honest = {
  build(root) {
    const li = a => a.map(x => `<div style="font-size:27px;line-height:1.3;margin:0 0 8px;color:var(--ink)">&bull; ${x}</div>`).join('');
    const box = (k, x, title, big, cap, items, cls) => `<div class="card" data-k="${k}" style="position:absolute;left:${x}px;top:200px;width:540px;height:490px;${cls}">
      <div class="tag" ${cls.includes('red') ? 'style="color:var(--red)"' : ''}>${title}</div>
      <div class="num" data-k="${k}n" style="font-size:120px;font-weight:600;letter-spacing:-5px;line-height:1.05;margin-top:6px">${big}</div>
      <div class="sub" style="font-size:28px;margin-bottom:18px">${cap}</div>${li(items)}</div>`;
    root.innerHTML = `
      <div class="abs center big" data-k="t0" style="top:410px;font-size:120px">Now the <span class="kw">honest</span> part.</div>
      ${box('bS', 690, 'Simulated', '10', 'simulated eval sessions', ['every teardown you saw', 'the evaluation table', 'timings such as the 2.75 s flag'], 'border-color:rgba(240,112,122,.6)')}
      ${box('bR', 120, 'Real and tested', '100+', 'automated tests, CI green', ['hash-chained log and object graph', 'safety kernel and five checks', 'signed passport and verify page', 'Docker image verified', 'proof ledger: every claim dated'], 'border-color:var(--v)')}
      ${box('bN', 1260, 'Not proven', '0', 'real teardowns filmed', ['perception on a real bench', 'Meta refuses SAM: 402 billing', 'SAM missed battery, drives, cover, memory'], 'border-color:var(--red);red')}
      <div class="abs center" data-k="fin" style="top:748px"><span class="chip f" style="font-size:36px;padding:14px 32px">We would rather show you the boundary than hide it.</span></div>`;
  },
  draw(t, X) {
    const L = X.L, q = X.q;
    show(q('t0'), t, L[0], { dy: 30, d: 0.8, out: L[1] - 0.05 });
    show(q('bS'), t, L[1] + 0.3, { dy: 36 }); count(q('bSn'), 0, 10, t, L[1] + 0.5, 1.0);
    show(q('bR'), t, L[2] + 0.2, { dy: 36 }); count(q('bRn'), 0, 100, t, L[2] + 0.4, 1.6, v => Math.round(v) + '+');
    show(q('bN'), t, L[3] + 0.2, { dy: 36 }); count(q('bNn'), 0, 0, t, L[3], 1);
    show(q('fin'), t, L[4], { dy: 20, sc: 0.92, e: 'back' });
  },
};

/* ------------------------------------------------------------------------------------------------ 13. close */
S.close = {
  build(root) {
    root.innerHTML = `
      <div class="abs center" data-k="logo" style="top:130px">${STONES(150, 'c')}</div>
      <div class="abs center mid" data-k="l0" style="top:340px;font-size:68px">Cairn gives AI a memory<br>for the physical world.</div>
      <div class="abs center big" data-k="l1" style="top:330px;font-size:92px;padding:0 160px;line-height:1.08">The first AI that can take something <span class="kw">apart</span>, and put it back together.</div>
      <div class="abs center" data-k="l2" style="top:700px">
        <div class="mono" style="font-size:38px">github.com/ABDULWAHAB-dev7/CAIRN-AI</div>
        <div class="mono" style="font-size:38px;margin-top:8px;color:var(--pearl)">cairn-ai-eta.vercel.app</div>
        <div class="credit" style="margin-top:22px;font-size:24px">Meta Global AI Developer Hackathon 2026 &middot; every claim is dated in docs/PROOF.md</div></div>`;
  },
  draw(t, X) {
    const L = X.L, q = X.q;
    show(q('logo'), t, L[0], { dy: 0, d: 0.3 }); stones(X, 'c', t, L[0] + 0.1);
    show(q('l0'), t, L[0] + 0.5, { dy: 26, out: L[1] - 0.05 });
    q('logo').style.top = (t >= L[1] ? 110 : 130) + 'px';
    show(q('l1'), t, L[1], { dy: 30, d: 0.9 });
    show(q('l2'), t, L[2], { dy: 24 });
  },
};
