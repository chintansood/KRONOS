/* KRONOS — 2D network graph, used when the browser cannot create a WebGL context (no GPU, virtual machine, remote
   desktop, or WebGL disabled by policy). Same nodes, links, colours, filters, search and inspector card as the 3D view. */
(() => {
  "use strict";
  const EDGE = { FIR: "#C0504A", FINANCIAL: "#B96D50", COMMUNICATION: "#4A7FB5", LOCATION: "#7B8062", CROSS: "#8A63B0" };
  const hex = c => typeof c === "number" ? "#" + c.toString(16).padStart(6, "0") : (c || "#C69A55");
  const esc = s => String(s ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

  window.graph2D = function (el, container, card, focusId) {
    const NODES = typeof GRAPH_NODES !== "undefined" ? GRAPH_NODES : [], EDGES = typeof GRAPH_EDGES !== "undefined" ? GRAPH_EDGES : [];
    const badge = el.querySelector(".graph-title .mono"); if (badge) badge.textContent = "2D VIEW · WEBGL UNAVAILABLE";
    const hud = el.querySelector(".graph-hud"); if (hud) hud.textContent = "DRAG TO PAN • SCROLL TO ZOOM • CLICK NODE TO INSPECT";
    const orbit = el.querySelector("#g-orbit"); if (orbit) orbit.style.display = "none";
    const cv = document.createElement("canvas"); cv.className = "g2d"; cv.style.cssText = "display:block;width:100%;height:100%;cursor:grab";
    container.prepend(cv);
    const ctx = cv.getContext("2d");
    let W = 0, H = 0, dpr = 1;
    const size = () => { dpr = Math.min(devicePixelRatio || 1, 2); W = container.clientWidth || innerWidth; H = container.clientHeight || innerHeight - 120;
      cv.width = W * dpr; cv.height = H * dpr; cv.style.height = H + "px"; };
    size();
    // deterministic start (same rings as the 3D layout), then a short force simulation
    const P = {}, n = NODES.length || 1;
    NODES.forEach((nd, i) => {
      const r = nd.type === "CASE" ? 120 : nd.type === "PERSON" ? 68 : 160, a = (i / n) * Math.PI * 2;
      P[nd.id] = { x: Math.cos(a) * r + Math.sin(i * 1.5) * 14, y: Math.sin(a) * r, vx: 0, vy: 0, nd, r: nd.val ? Math.max(4, nd.val * 0.85) : 6 };
    });
    const links = EDGES.filter(e => P[e.source] && P[e.target]);
    const ids = Object.keys(P);
    for (let it = 0; it < 260; it++) {
      const k = 1 - it / 260;
      for (let i = 0; i < ids.length; i++) for (let j = i + 1; j < ids.length; j++) {
        const a = P[ids[i]], b = P[ids[j]]; let dx = a.x - b.x, dy = a.y - b.y; const d2 = dx * dx + dy * dy + 0.01, f = 900 / d2;
        dx *= f; dy *= f; a.vx += dx; a.vy += dy; b.vx -= dx; b.vy -= dy;
      }
      links.forEach(e => { const a = P[e.source], b = P[e.target]; const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1, f = (d - 70) * 0.02;
        a.vx += dx / d * f; a.vy += dy / d * f; b.vx -= dx / d * f; b.vy -= dy / d * f; });
      ids.forEach(id => { const p = P[id]; p.vx -= p.x * 0.004; p.vy -= p.y * 0.004; p.x += Math.max(-12, Math.min(12, p.vx)) * k; p.y += Math.max(-12, Math.min(12, p.vy)) * k; p.vx *= 0.5; p.vy *= 0.5; });
    }
    // fit to view
    const xs = ids.map(id => P[id].x), ys = ids.map(id => P[id].y);
    const bw = Math.max(1, Math.max(...xs) - Math.min(...xs)), bh = Math.max(1, Math.max(...ys) - Math.min(...ys));
    const view = { s: Math.min(W / (bw + 120), H / (bh + 120)), x: 0, y: 0 };
    const cx0 = (Math.max(...xs) + Math.min(...xs)) / 2, cy0 = (Math.max(...ys) + Math.min(...ys)) / 2;
    const home = { ...view };
    let filter = "ALL", sel = null, query = "";
    const toScreen = p => [(p.x - cx0) * view.s + W / 2 + view.x, (p.y - cy0) * view.s + H / 2 + view.y];
    const visible = nd => filter === "ALL" || nd.type === filter;
    function connected(id) { const s = new Set([id]); links.forEach(e => { if (e.source === id || e.target === id) { s.add(e.source); s.add(e.target); } }); return s; }
    function draw() {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.fillStyle = "#F5EFEB"; ctx.fillRect(0, 0, W, H);
      const near = sel ? connected(sel.id) : null;
      const hit = nd => !query || (nd.label + nd.id + (nd.sublabel || "")).toLowerCase().includes(query);
      links.forEach(e => {
        const a = P[e.source], b = P[e.target]; if (!visible(a.nd) || !visible(b.nd)) return;
        const on = near ? (e.source === sel.id || e.target === sel.id) : true;
        const [x1, y1] = toScreen(a), [x2, y2] = toScreen(b);
        ctx.strokeStyle = EDGE[e.modality] || "#C69A55"; ctx.globalAlpha = on ? (e.isAnomaly ? 0.85 : 0.45) : 0.07; ctx.lineWidth = Math.max(0.6, (e.weight || 1) * 0.8);
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.quadraticCurveTo((x1 + x2) / 2, (y1 + y2) / 2 - 10, x2, y2); ctx.stroke();
      });
      ctx.globalAlpha = 1;
      ids.forEach(id => {
        const p = P[id]; if (!visible(p.nd)) return;
        const [x, y] = toScreen(p), r = Math.max(3, p.r * Math.min(1.6, view.s * 0.9));
        ctx.globalAlpha = (near && !near.has(id)) || !hit(p.nd) ? 0.2 : 1;
        ctx.fillStyle = hex(p.nd.color); ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
        if (sel && sel.id === id) { ctx.strokeStyle = "#30251F"; ctx.lineWidth = 2; ctx.stroke(); }
        if (p.nd.type === "PERSON" || p.nd.type === "CASE" || (sel && sel.id === id)) {
          ctx.fillStyle = "#30251F"; ctx.font = `${sel && sel.id === id ? 600 : 500} 11px Inter, system-ui, sans-serif`; ctx.textAlign = "center";
          ctx.fillText(String(p.nd.label).slice(0, 26), x, y - r - 4);
        }
      });
      ctx.globalAlpha = 1;
    }
    function select(nd) {
      sel = nd; draw();
      if (!nd) { card.style.display = "none"; return; }
      const live = window.KR && KR.live;
      card.style.display = "block";
      card.innerHTML = `<button onclick="document.getElementById('g-card').style.display='none'" style="float:right;border:none;background:none;cursor:pointer;font-size:16px">✕</button>
        <span class="badge mono" style="background:#B96D50;color:#fff">${esc(nd.type)}</span><h3>${esc(nd.label)}</h3>
        <div class="mono" style="opacity:.8;margin-bottom:8px">${esc(nd.sublabel || "")}</div>
        <p style="font-size:12px;margin:6px 0">${nd.type === "PERSON" ? (live ? "Recorded entity in the investigation network. Connections are recorded links, not evidence of involvement." : "Recorded entity.") : "Linked entity."}</p>
        <div style="margin-top:12px;display:flex;gap:6px">${nd.type === "PERSON" ? `<button class="go" style="margin:0;padding:6px 12px;font-size:11px" onclick="location.hash='#p/${esc(nd.id)}'">Open Person Dossier →</button>` : ""}
        ${nd.type === "CASE" ? `<button class="go" style="margin:0;padding:6px 12px;font-size:11px" onclick="location.hash='#case/${esc(nd.id)}'">Open Case Workspace →</button>` : ""}
        <button onclick="document.getElementById('g-card').style.display='none'" style="border:1px solid var(--cop);background:none;padding:6px 12px;border-radius:8px;font-size:11px">Dismiss</button></div>`;
    }
    function nodeAt(mx, my) {
      let best = null, bd = 1e9;
      ids.forEach(id => { const p = P[id]; if (!visible(p.nd)) return; const [x, y] = toScreen(p), d = Math.hypot(mx - x, my - y);
        if (d < Math.max(10, p.r * view.s + 4) && d < bd) { bd = d; best = p.nd; } });
      return best;
    }
    let drag = null, moved = false;
    const down = e => { const t = e.touches ? e.touches[0] : e; drag = { x: t.clientX, y: t.clientY, vx: view.x, vy: view.y }; moved = false; cv.style.cursor = "grabbing"; };
    const move = e => { if (!drag) return; const t = e.touches ? e.touches[0] : e; const dx = t.clientX - drag.x, dy = t.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) moved = true; view.x = drag.vx + dx; view.y = drag.vy + dy; draw(); };
    const up = e => { cv.style.cursor = "grab"; if (drag && !moved) { const r = cv.getBoundingClientRect(), t = e.changedTouches ? e.changedTouches[0] : e; select(nodeAt(t.clientX - r.left, t.clientY - r.top)); } drag = null; };
    const wheel = e => { e.preventDefault(); const r = cv.getBoundingClientRect(), mx = e.clientX - r.left - W / 2 - view.x, my = e.clientY - r.top - H / 2 - view.y;
      const f = Math.exp(-e.deltaY * 0.0015), s2 = Math.max(home.s * 0.4, Math.min(home.s * 6, view.s * f)), k = s2 / view.s;
      view.x -= mx * (k - 1); view.y -= my * (k - 1); view.s = s2; draw(); };
    cv.addEventListener("mousedown", down); cv.addEventListener("touchstart", down, { passive: true });
    addEventListener("mousemove", move); addEventListener("touchmove", move, { passive: true });
    addEventListener("mouseup", up); addEventListener("touchend", up);
    cv.addEventListener("wheel", wheel, { passive: false });
    const onResize = () => { size(); draw(); }; addEventListener("resize", onResize);
    el.querySelectorAll(".graph-controls button[data-f]").forEach(b => b.onclick = () => {
      el.querySelectorAll(".graph-controls button[data-f]").forEach(x => x.classList.remove("on")); b.classList.add("on"); filter = b.dataset.f; draw(); });
    const search = el.querySelector("#g-search");
    if (search) search.oninput = e => { query = e.target.value.toLowerCase().trim(); const m = query && NODES.find(nd => (nd.label + nd.id + (nd.sublabel || "")).toLowerCase().includes(query)); if (m) select(m); else draw(); };
    const reset = el.querySelector("#g-reset");
    if (reset) reset.onclick = () => { Object.assign(view, home); filter = "ALL"; query = ""; if (search) search.value = "";
      el.querySelectorAll(".graph-controls button[data-f]").forEach(x => x.classList.toggle("on", x.dataset.f === "ALL")); select(null); };
    draw();
    if (focusId && P[focusId]) setTimeout(() => select(P[focusId].nd), 150);
    window.cleanup = () => { removeEventListener("mousemove", move); removeEventListener("touchmove", move); removeEventListener("mouseup", up);
      removeEventListener("touchend", up); removeEventListener("resize", onResize); };
  };
})();
