/* KRONOS premium layer — motion, 3D and micro-interactions on top of the existing interface.
   Everything is additive and degrades gracefully: no WebGL → no 3D layer; reduced motion → static; touch → no cursor halo. */
(() => {
  "use strict";
  const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const FINE = matchMedia("(hover: hover) and (pointer: fine)").matches;
  const $ = (s, r = document) => r.querySelector(s), $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const DIAL = `<svg viewBox="0 0 100 100" fill="none" stroke="#A86F45" aria-hidden="true"><circle cx="50" cy="50" r="46" stroke-width="3"/><circle cx="50" cy="50" r="38" stroke-width="1"/>${
    [...Array(12)].map((_, i) => `<line x1="50" y1="6" x2="50" y2="${i % 3 ? 11 : 15}" transform="rotate(${i * 30} 50 50)" stroke-width="1.5"/>`).join("")
  }<path d="M50 2v96M2 50h96" stroke-width="1.2"/><circle cx="50" cy="50" r="3" fill="#B96D50" stroke="none"/></svg>`;

  /* ------------------------------------------------------------ 1. preloader (first load only) */
  (function loader() {
    const L = document.getElementById("kp-loader");
    if (!L) return;
    if (RM) { L.remove(); return; }
    const bar = $(".kp-bar", L), num = $(".kp-num", L), t0 = performance.now();
    let p = 0, target = 0.3, done = false;
    addEventListener("load", () => { target = Math.max(target, 0.72); });
    const ready = window.KR && window.KR.ready ? window.KR.ready : Promise.resolve();
    Promise.race([ready, new Promise(r => setTimeout(r, 7000))]).then(() => setTimeout(() => { target = 1; done = true; }, 150));
    (function tick() {
      p += (target - p) * 0.07;
      if (done && target - p < 0.004) p = 1;
      bar.style.setProperty("--p", p.toFixed(3));
      num.textContent = String(Math.round(p * 100)).padStart(3, "0");
      if (done && p === 1 && performance.now() - t0 > 1200) {
        L.classList.add("out");
        setTimeout(() => L.remove(), 1100);
        return;
      }
      requestAnimationFrame(tick);
    })();
  })();

  /* ------------------------------------------------------------ 2. page curtain on navigation */
  const curtain = document.createElement("div");
  curtain.id = "kp-curtain";
  curtain.innerHTML = `<div class="kp-dial">${DIAL}</div>`;
  document.body.append(curtain);
  addEventListener("hashchange", () => {
    if (RM || !window.gsap || document.getElementById("kp-loader")) return;
    gsap.killTweensOf(curtain);
    gsap.fromTo(curtain, { clipPath: "inset(0% 0% 0% 0%)" },
      { clipPath: "inset(0% 0% 100% 0%)", duration: 0.8, ease: "power3.inOut", delay: 0.06 });
  });

  /* ------------------------------------------------------------ 3. cursor halo (keeps the native cursor) */
  if (FINE && !RM) {
    const c = document.createElement("div");
    c.id = "kp-cursor";
    document.body.append(c);
    let x = -100, y = -100, tx = -100, ty = -100;
    const HOT = "a,button,[role=button],select,input,textarea,.row,.metric,[onclick],[data-go],label,.ev2";
    addEventListener("pointermove", e => {
      tx = e.clientX; ty = e.clientY; c.classList.add("on");
      c.classList.toggle("hot", !!(e.target.closest && e.target.closest(HOT)));
    }, { passive: true });
    addEventListener("pointerdown", () => c.classList.add("down"));
    addEventListener("pointerup", () => c.classList.remove("down"));
    document.addEventListener("pointerleave", () => c.classList.remove("on"));
    (function loop() {
      x += (tx - x) * 0.22; y += (ty - y) * 0.22;
      c.style.transform = `translate3d(${x}px,${y}px,0)`;
      requestAnimationFrame(loop);
    })();
  }

  /* ------------------------------------------------------------ 4. magnetic buttons + sheen + tilt */
  const MAG = ".btn, .ib, .copilot-btn, nav .demo, .home-chat .btn-send, .go:not(.row .go)";
  let mag = null;
  const release = el => { if (el) el.style.translate = ""; };
  if (FINE && !RM) {
    addEventListener("pointermove", e => {
      const t = e.target.closest ? e.target : null;
      const el = t && t.closest(MAG);
      if (el !== mag) { release(mag); mag = el; }
      if (el) {
        const r = el.getBoundingClientRect();
        const dx = (e.clientX - (r.left + r.width / 2)) / r.width, dy = (e.clientY - (r.top + r.height / 2)) / r.height;
        el.style.translate = `${(dx * Math.min(12, r.width * 0.08)).toFixed(1)}px ${(dy * 6).toFixed(1)}px`;
      }
      const sh = t && t.closest(".kp-sheen");
      if (sh) { const r = sh.getBoundingClientRect(); sh.style.setProperty("--mx", `${e.clientX - r.left}px`); sh.style.setProperty("--my", `${e.clientY - r.top}px`); }
      const tl = t && t.closest(".kp-tilt");
      $$(".kp-tilt[data-tilting]").forEach(x => { if (x !== tl) { x.style.transform = ""; delete x.dataset.tilting; } });
      if (tl) {
        const r = tl.getBoundingClientRect();
        const rx = ((e.clientY - r.top) / r.height - 0.5) * -7, ry = ((e.clientX - r.left) / r.width - 0.5) * 9;
        tl.style.transform = `perspective(700px) rotateX(${rx.toFixed(2)}deg) rotateY(${ry.toFixed(2)}deg)`;
        tl.dataset.tilting = "1";
      }
    }, { passive: true });
  }

  /* ------------------------------------------------------------ 5. three.js hero: armillary rings + evidence orbit */
  function hero3D(stage) {
    if (!window.THREE || stage.querySelector(".kp-3d")) return;
    const T = window.THREE;
    const canvas = document.createElement("canvas");
    canvas.className = "kp-3d";
    canvas.setAttribute("aria-hidden", "true");
    stage.insertBefore(canvas, stage.querySelector(".hg") || stage.firstChild);
    let renderer;
    try { renderer = new T.WebGLRenderer({ canvas, alpha: true, antialias: true, powerPreference: "low-power" }); }
    catch (e) { canvas.remove(); return; }
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
    renderer.setClearColor(0x000000, 0);
    const scene = new T.Scene();
    const cam = new T.PerspectiveCamera(35, 16 / 9, 0.1, 100);
    cam.position.set(0, 0, 10);

    // soft round sprite
    const sc = document.createElement("canvas"); sc.width = sc.height = 64;
    const g = sc.getContext("2d"), grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grd.addColorStop(0, "rgba(255,255,255,1)"); grd.addColorStop(0.35, "rgba(255,255,255,.85)"); grd.addColorStop(1, "rgba(255,255,255,0)");
    g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
    const sprite = new T.CanvasTexture(sc);

    const orbit = new T.Group();
    orbit.rotation.set(1.2, 0, -0.09);       // tilted like the drawn orbits around the hourglass
    scene.add(orbit);
    const palette = [new T.Color(0xC69A55), new T.Color(0xB96D50), new T.Color(0xA86F45), new T.Color(0xE2C08A), new T.Color(0x8A6A48)];
    const N = 900, pos = new Float32Array(N * 3), col = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const a = Math.random() * Math.PI * 2, band = Math.random();
      const r = 2.35 + Math.pow(band, 1.6) * 2.1 + (Math.random() - 0.5) * 0.12;
      pos[i * 3] = Math.cos(a) * r; pos[i * 3 + 1] = (Math.random() - 0.5) * 0.18 * (1 + band); pos[i * 3 + 2] = Math.sin(a) * r;
      const c = palette[(Math.random() * palette.length) | 0]; col.set([c.r, c.g, c.b], i * 3);
    }
    const ringGeo = new T.BufferGeometry();
    ringGeo.setAttribute("position", new T.BufferAttribute(pos, 3));
    ringGeo.setAttribute("color", new T.BufferAttribute(col, 3));
    const ringPts = new T.Points(ringGeo, new T.PointsMaterial({ size: 0.075, map: sprite, vertexColors: true, transparent: true, opacity: 0.85, depthWrite: false }));
    orbit.add(ringPts);

    // armillary rings (thin gold tori)
    const ringMat = new T.MeshBasicMaterial({ color: 0xB98A4A, transparent: true, opacity: 0.5 });
    const rings = [[2.05, [1.2, 0, -0.09]], [2.95, [1.05, 0.55, 0.2]], [3.65, [1.32, -0.45, -0.25]]].map(([r, rot], i) => {
      const m = new T.Mesh(new T.TorusGeometry(r, i ? 0.0065 : 0.009, 6, 220), ringMat.clone());
      m.material.opacity = i ? 0.32 : 0.55;
      m.rotation.set(...rot); scene.add(m); return m;
    });
    // evidence beads travelling along the inner ring
    const beads = new T.Group(); rings[0].add(beads);
    for (let i = 0; i < 6; i++) {
      const b = new T.Mesh(new T.SphereGeometry(i % 3 ? 0.045 : 0.07, 16, 16), new T.MeshBasicMaterial({ color: i % 2 ? 0xB96D50 : 0xC69A55 }));
      b.userData.a = (i / 6) * Math.PI * 2; beads.add(b);
    }
    // floating dust
    const D = 220, dpos = new Float32Array(D * 3), dspd = new Float32Array(D);
    for (let i = 0; i < D; i++) { dpos.set([(Math.random() - 0.5) * 12, (Math.random() - 0.5) * 7, (Math.random() - 0.5) * 4], i * 3); dspd[i] = 0.002 + Math.random() * 0.006; }
    const dustGeo = new T.BufferGeometry(); dustGeo.setAttribute("position", new T.BufferAttribute(dpos, 3));
    const dust = new T.Points(dustGeo, new T.PointsMaterial({ size: 0.045, map: sprite, color: 0xC69A55, transparent: true, opacity: 0.55, depthWrite: false }));
    scene.add(dust);

    let mx = 0, my = 0, visible = true, raf = 0, last = performance.now();
    const onMove = e => { mx = e.clientX / innerWidth - 0.5; my = e.clientY / innerHeight - 0.5; };
    addEventListener("pointermove", onMove, { passive: true });
    const size = () => {
      const w = stage.clientWidth, h = stage.clientHeight;
      if (!w || !h) return;
      renderer.setSize(w, h, false); cam.aspect = w / h; cam.updateProjectionMatrix();
    };
    size();
    const ro = new ResizeObserver(size); ro.observe(stage);
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; }, { threshold: 0.01 }); io.observe(canvas);
    const dispose = () => {
      cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); removeEventListener("pointermove", onMove);
      scene.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); });
      sprite.dispose(); renderer.dispose();
    };
    function frame(now) {
      if (!document.body.contains(canvas)) { dispose(); return; }
      raf = requestAnimationFrame(frame);
      if (!visible || document.hidden) return;
      const dt = Math.min(50, now - last); last = now;
      const k = dt / 16.7;
      orbit.rotation.y += 0.0016 * k;
      rings[0].rotation.z += 0.0011 * k; rings[1].rotation.z -= 0.0007 * k; rings[2].rotation.z += 0.0005 * k;
      beads.children.forEach((b, i) => { b.userData.a += 0.004 * k * (1 + i * 0.07); b.position.set(Math.cos(b.userData.a) * 2.05, Math.sin(b.userData.a) * 2.05, 0); });
      for (let i = 0; i < D; i++) { dpos[i * 3 + 1] += dspd[i] * k; if (dpos[i * 3 + 1] > 3.6) dpos[i * 3 + 1] = -3.6; }
      dustGeo.attributes.position.needsUpdate = true;
      cam.position.x += (mx * 1.1 - cam.position.x) * 0.04;
      cam.position.y += (-my * 0.7 - cam.position.y) * 0.04;
      cam.lookAt(0, 0, 0);
      renderer.render(scene, cam);
    }
    if (RM) { renderer.render(scene, cam); } else { raf = requestAnimationFrame(frame); }
    setTimeout(() => canvas.classList.add("on"), 500);
  }

  /* ------------------------------------------------------------ 6. per-render enhancements */
  const ease = t => 1 - Math.pow(1 - t, 3);
  function countUp(b) {
    if (!b || RM) return;
    const m = (b.textContent || "").match(/^\s*([\d,]+)(.*)$/);
    if (!m) return;
    const n = +m[1].replace(/,/g, ""), rest = m[2];
    if (!n || n < 4) return;
    const t0 = performance.now(), dur = 1100 + Math.min(900, Math.log10(n) * 220);
    (function step(now) {
      const p = Math.min(1, (now - t0) / dur);
      b.textContent = Math.round(n * ease(p)).toLocaleString("en-IN") + rest;
      if (p < 1) requestAnimationFrame(step);
    })(t0);
  }
  // PERS is a top-level binding of the main script (not a window property); read it by name
  function topPerson() { try { return (typeof PERS !== "undefined" && PERS[0] && PERS[0].id) || null; } catch (e) { return null; } }
  function enhance() {
    $$(".tag:not([data-t])").forEach(t => { t.dataset.t = (t.textContent || "").trim().toLowerCase().split(/\s+/)[0] || "x"; });
    $$(".metric:not([data-kp])").forEach(m => { m.dataset.kp = "1"; m.classList.add("kp-sheen", "kp-tilt"); countUp($("b", m)); });
    $$(".pane:not([data-kp])").forEach(p => { p.dataset.kp = "1"; p.classList.add("kp-sheen"); });
    // hero: demo-only targets → live destinations
    if (window.KR && window.KR.live) {
      const tp = topPerson();
      $$('[data-go="p/P-0427"]').forEach(b => { b.dataset.go = /NETWORK/i.test(b.textContent) ? "graph" : (tp ? `p/${tp}` : "dash"); });
    }
    const stage = $(".view.hero .stage");
    if (stage && !stage.querySelector(".kp-3d")) hero3D(stage);
    $$(".story .blk:not([data-kp])").forEach(b => { b.dataset.kp = "1"; $$(".two>div,.three>div", b).forEach(d => d.classList.add("kp-sheen")); });
  }
  let queued = false;
  const app = document.getElementById("app");
  new MutationObserver(() => { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; enhance(); }); } })
    .observe(app || document.body, { childList: true, subtree: true });
  enhance();

  /* ------------------------------------------------------------ 7. home chat expanded → hero buttons step aside */
  setInterval(() => {
    const c = document.getElementById("hchat");
    const open = !!c && document.body.dataset.v === "home" && (c.classList.contains("has-msgs") || c.classList.contains("sug-open"))
      && !c.classList.contains("hchat-hidden");
    document.body.classList.toggle("kp-hchat-open", open);
  }, 200);

  /* ------------------------------------------------------------ 8. nav: show the active section clearly on load */
  addEventListener("hashchange", () => { const tp = document.querySelector(".view"); if (tp) tp.scrollTop = 0; });
})();
