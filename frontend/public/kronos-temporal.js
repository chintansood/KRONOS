/* KRONOS Temporal Engine on the home page — pick a person and replay their recorded activity in time:
   time river (every record by type), travel feasibility (Haversine), the day's routine and the event under the playhead.
   Uses the live API: /temporal/highlights, /persons/{id}/timeline, /persons/{id}/feasibility, /persons/{id}/routine. */
(() => {
  "use strict";
  const API = "/api";
  const RM = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const j = (p, ms = 45000) => {
    if (window.KRstatic) return window.KRstatic.get(p);   // online prototype
    const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms);
    return fetch(API + p, { signal: ctl.signal }).then(r => { clearTimeout(t); if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  };
  const LANES = [
    { label: "Location", color: "#7B8062", mods: ["LOCATION"] },
    { label: "Calls", color: "#5B7DA8", mods: ["CDR"] },
    { label: "Messages", color: "#C58B7A", mods: ["COMMUNICATION", "SOCIAL"] },
    { label: "Money", color: "#C69A55", mods: ["FINANCIAL"] },
    { label: "Case records", color: "#30251F", mods: ["FIR", "CROSS_CASE"] },
  ];
  const laneOf = m => { const i = LANES.findIndex(l => l.mods.includes(m)); return i < 0 ? LANES.length - 1 : i; };
  const W = 1000, PADL = 104, PADR = 18, TOP = 46, LH = 34, H = TOP + LANES.length * LH + 34;
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const tsOf = s => Date.parse(String(s).replace(" ", "T"));
  const fmtDT = t => { const d = new Date(t); return `${String(d.getDate()).padStart(2, "0")} ${MON[d.getMonth()]} ${d.getFullYear()} · ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`; };
  const iso = t => { const d = new Date(t); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
  const persons = () => { try { return typeof PERS !== "undefined" ? PERS : []; } catch (e) { return []; } };
  const VERDICT = { IMPOSSIBLE: "Impossible", REQUIRES_AIR_TRAVEL: "Needs air travel", SIMULTANEOUS: "Two places at once" };

  function sectionHTML() {
    return `<div class="blk kt-blk">
      <small class="no">04 TEMPORAL ENGINE</small>
      <h2>Reconstruct <em>when</em>, <em>where</em> and <em>with whom</em>.</h2>
      <p class="lead">Pick anyone in the records. KRONOS lines up every call, message, transfer and location fix in time,
        checks whether each move between places was physically possible, and replays the sequence.</p>
      <div class="kt-panel">
        <div class="kt-bar">
          <label class="kt-search"><span>Person</span><input id="kt-q" list="kt-list" placeholder="Name or ID, e.g. P00049" autocomplete="off"><datalist id="kt-list"></datalist></label>
          <div class="kt-chips" id="kt-chips"><span class="kt-muted">Loading suggestions…</span></div>
        </div>
        <div class="kt-head" id="kt-head"></div>
        <div class="kt-river-wrap">
          <svg class="kt-river" id="kt-river" viewBox="0 0 ${W} ${H}" tabindex="0" role="img" aria-label="Time river of recorded activity"></svg>
          <div class="kt-tip" id="kt-tip" hidden></div>
        </div>
        <div class="kt-ctl">
          <button class="kt-play" id="kt-play" type="button">▶ Replay timeline</button>
          <button class="kt-ib" id="kt-prev" type="button" title="Previous record" aria-label="Previous record">⏮</button>
          <button class="kt-ib" id="kt-next" type="button" title="Next record" aria-label="Next record">⏭</button>
          <select id="kt-speed" aria-label="Replay speed"><option value="1">1×</option><option value="2">2×</option><option value="4">4×</option></select>
          <select id="kt-zoom" aria-label="Zoom"><option value="0">Whole span</option><option value="30">30 days</option><option value="7">7 days</option><option value="1">1 day</option></select>
          <span class="kt-legend">${LANES.map(l => `<i style="--c:${l.color}"></i>${l.label}`).join("")}<i class="kt-a"></i>Anomaly</span>
        </div>
        <div class="kt-grid">
          <div class="kt-card kt-now" id="kt-now"></div>
          <div class="kt-card kt-feas" id="kt-feas"></div>
          <div class="kt-card kt-day" id="kt-day"></div>
        </div>
        <div class="kt-actions">
          <button class="btn p" id="kt-dossier" type="button">Open full dossier →</button>
          <button class="btn" id="kt-ask" type="button">Ask KRONOS about this timeline</button>
        </div>
        <p class="kt-note">Times and places are as recorded by the source systems. A flag is a lead to verify (shared phone, wrong attribution,
          location error or a flight), never a finding.</p>
      </div></div>`;
  }

  function init(sec, want) {
    const $ = s => sec.querySelector(s);
    const S = { pid: null, ev: [], times: [], feas: null, t0: 0, t1: 1, sel: -1, raf: 0, playT: null, day: null, flags: [], full: [0, 1], dayTimer: 0 };
    const X = t => PADL + (t - S.t0) / (S.t1 - S.t0) * (W - PADL - PADR);
    const Y = lane => TOP + lane * LH + LH / 2;
    const live = window.KR && window.KR.live, page = !!sec.closest(".kt-page");
    if (!live) {
      $(".kt-panel").innerHTML = `<p class="kt-muted" style="padding:28px">The temporal engine needs the KRONOS backend (it is offline right now). Open any person dossier to see the offline demo timeline.</p>`;
      return;
    }
    // person picker
    $("#kt-list").innerHTML = persons().slice(0, 400).map(p => `<option value="${esc(p.id)} · ${esc(p.n)}">`).join("");
    const pick = v => {
      const s = String(v || "").trim(); if (!s) return;
      const id = (s.match(/\bP\d{5}\b/i) || [])[0];
      const P = id ? persons().find(p => p.id === id.toUpperCase()) : persons().find(p => (p.n || "").toLowerCase().includes(s.toLowerCase()));
      if (P) load(P.id); else toastMsg(`No person matches "${s}"`);
    };
    $("#kt-q").addEventListener("change", e => pick(e.target.value));
    $("#kt-q").addEventListener("keydown", e => { if (e.key === "Enter") pick(e.target.value); });
    j("/temporal/highlights?limit=6").then(h => {
      const chips = [...h.travel.map(x => ({ id: x.personId, n: x.name, tag: x.impossible ? `⚠ ${x.impossible} impossible` : `${x.air} need flight`, hot: !!x.impossible })),
                     ...h.active.slice(0, 3).map(x => ({ id: x.personId, n: x.name, tag: `${x.records} records` }))];
      $("#kt-chips").innerHTML = `<span class="kt-muted">Suggested:</span>` + chips.map(c =>
        `<button type="button" class="kt-chip${c.hot ? " hot" : ""}" data-p="${esc(c.id)}"><b>${esc(c.n)}</b> ${esc(c.id)} <em>${esc(c.tag)}</em></button>`).join("");
      $("#kt-chips").querySelectorAll("[data-p]").forEach(b => b.onclick = () => load(b.dataset.p));
      load(want || (h.travel[0] || h.active[0] || {}).personId || (persons()[0] || {}).id);
    }).catch(() => { $("#kt-chips").innerHTML = ""; if (want || persons()[0]) load(want || persons()[0].id); });

    function toastMsg(m) { if (typeof toast === "function") toast(m); }

    async function load(pid) {
      if (!pid) return;
      stop();
      S.pid = pid; S.sel = -1;
      if (page && location.hash !== `#temporal/${pid}`) history.replaceState(null, "", `#temporal/${pid}`);   // the page URL names the person shown
      sec.querySelectorAll(".kt-chip").forEach(b => b.classList.toggle("on", b.dataset.p === pid));
      const P = persons().find(p => p.id === pid);
      $("#kt-q").value = P ? `${P.id} · ${P.n}` : pid;
      $("#kt-head").innerHTML = `<span class="kt-muted">Loading ${esc(pid)}'s recorded activity…</span>`;
      $("#kt-river").innerHTML = ""; $("#kt-now").innerHTML = ""; $("#kt-feas").innerHTML = ""; $("#kt-day").innerHTML = "";
      try {
        const [tl, fe] = await Promise.all([j(`/persons/${pid}/timeline`), j(`/persons/${pid}/feasibility`)]);
        if (S.pid !== pid) return;
        S.ev = (Array.isArray(tl) ? tl : tl.events || []).filter(e => e.timestamp).map(e => ({ ...e, t: tsOf(e.timestamp), lane: laneOf(e.modality) }))
          .filter(e => !isNaN(e.t)).sort((a, b) => a.t - b.t);
        S.times = S.ev.map(e => e.t);
        S.feas = fe; S.flags = fe.flags || [];
      } catch (e) {
        $("#kt-head").innerHTML = `<span class="kt-muted">Could not load ${esc(pid)} (${esc(e.message)}).</span>`; return;
      }
      if (!S.ev.length) { $("#kt-head").innerHTML = `<span class="kt-muted">${esc(pid)} has no time-stamped records.</span>`; return; }
      const span = S.times[S.times.length - 1] - S.times[0] || 3600e3;
      S.full = [S.times[0] - span * 0.015, S.times[S.times.length - 1] + span * 0.015];
      [S.t0, S.t1] = S.full;
      head(P); feas();
      const firstFlag0 = S.flags[0] ? S.ev.findIndex(e => e.evidenceId === S.flags[0].first.evidenceId) : -1;
      win(S.ev[firstFlag0 >= 0 ? firstFlag0 : S.ev.length - 1].t); river();
      select(firstFlag0 >= 0 ? firstFlag0 : S.ev.length - 1);
      if (!RM && window.gsap) gsap.from(sec.querySelectorAll(".kt-dot"), { attr: { r: 0 }, duration: 0.6, stagger: { amount: 0.8 }, ease: "back.out(2)" });
    }

    function head(P) {
      const n = {}; S.ev.forEach(e => { const l = LANES[e.lane].label; n[l] = (n[l] || 0) + 1; });
      const anom = S.ev.filter(e => e.isAnomaly).length, cases = [...new Set(S.ev.map(e => e.caseId).filter(Boolean))];
      $("#kt-head").innerHTML = `<div><b class="kt-name">${esc(P ? P.n : S.pid)}</b> <span class="mono">${esc(S.pid)}</span>
        <span class="kt-muted">· ${S.ev.length} records · ${fmtDT(S.times[0]).slice(0, 11)} → ${fmtDT(S.times[S.times.length - 1]).slice(0, 11)}
        · ${cases.length} case${cases.length === 1 ? "" : "s"}${anom ? ` · <span class="kt-warn">${anom} flagged</span>` : ""}</span></div>
        <div class="kt-counts">${Object.entries(n).map(([k, v]) => `<span>${esc(k)} <b>${v}</b></span>`).join("")}</div>`;
    }

    function river() {
      const svg = $("#kt-river");
      let g = "";
      LANES.forEach((l, i) => {
        g += `<text x="${PADL - 12}" y="${Y(i) + 4}" text-anchor="end" class="kt-lane">${l.label}</text>
              <line x1="${PADL}" x2="${W - PADR}" y1="${Y(i)}" y2="${Y(i)}" class="kt-rail"/>`;
      });
      // month / day ticks
      const d0 = new Date(S.t0), d1 = new Date(S.t1), days = (S.t1 - S.t0) / 864e5;
      const step = days > 120 ? "m" : days > 20 ? "w" : "d";
      const c = new Date(d0.getFullYear(), d0.getMonth(), step === "m" ? 1 : d0.getDate());
      while (c <= d1) {
        if (c >= d0) { const x = X(c.getTime()); g += `<line x1="${x}" x2="${x}" y1="${TOP - 6}" y2="${H - 28}" class="kt-tick"/><text x="${x + 3}" y="${H - 14}" class="kt-tlab">${String(c.getDate()).padStart(2, "0")} ${MON[c.getMonth()]}</text>`; }
        step === "m" ? c.setMonth(c.getMonth() + 1) : c.setDate(c.getDate() + (step === "w" ? 7 : 1));
      }
      // travel-feasibility arcs between the two records of each flag
      S.flags.forEach((f, k) => {
        const a = tsOf(f.first.timestamp), b = tsOf(f.second.timestamp);
        if (isNaN(a) || isNaN(b)) return;
        const x1 = X(a), x2 = Math.max(X(b), x1 + 6), y = Y(0), h = 26 + Math.min(30, (x2 - x1) * 0.4);
        g += `<path d="M${x1} ${y} Q ${(x1 + x2) / 2} ${y - h} ${x2} ${y}" class="kt-arc ${f.verdict === "IMPOSSIBLE" ? "bad" : ""}" data-f="${k}"/>`;
      });
      // flag pins: visible even when the two records are minutes apart on a months-long axis
      let lastPin = -99;
      S.flags.forEach((f, k) => {
        const a = tsOf(f.first.timestamp); if (isNaN(a) || a < S.t0 || a > S.t1) return;
        const x = X(a), bad = f.verdict === "IMPOSSIBLE";
        g += `<g class="kt-pin ${bad ? "bad" : ""}" data-f="${k}"><line x1="${x}" x2="${x}" y1="${TOP - 26}" y2="${Y(0) - 6}"/>
              <path d="M${x} ${TOP - 30} l5 6 l-5 6 l-5 -6z"/>${x - lastPin > 70 ? `<text x="${x + 8}" y="${TOP - 19}">${bad ? "⚠ " : "✈ "}${Math.round(f.impliedSpeedKmh)} km/h</text>` : ""}</g>`;
        lastPin = x;
      });
      S.ev.forEach((e, i) => {
        if (e.t < S.t0 || e.t > S.t1) return;
        const L = LANES[e.lane];
        g += `<circle class="kt-dot${e.isAnomaly ? " kt-anom" : ""}" data-i="${i}" cx="${X(e.t).toFixed(1)}" cy="${Y(e.lane)}" r="${e.isAnomaly ? 5.2 : 3.6}" fill="${L.color}"/>`;
      });
      g += `<g id="kt-ph" class="kt-ph"><line y1="${TOP - 10}" y2="${H - 30}"/><circle r="5" cy="${TOP - 10}"/></g>`;
      svg.innerHTML = g;
      const tip = $("#kt-tip");
      const near = clientX => {
        const r = svg.getBoundingClientRect(), x = (clientX - r.left) / r.width * W;
        const t = S.t0 + (x - PADL) / (W - PADL - PADR) * (S.t1 - S.t0);
        let lo = 0, hi = S.times.length - 1;
        while (lo < hi) { const m = (lo + hi) >> 1; S.times[m] < t ? lo = m + 1 : hi = m; }
        return lo > 0 && Math.abs(S.times[lo - 1] - t) < Math.abs(S.times[lo] - t) ? lo - 1 : lo;
      };
      let drag = false;
      svg.onpointermove = e => {
        const i = near(e.clientX), ev = S.ev[i]; if (!ev) return;
        if (drag) { stop(); select(i); }
        const r = svg.getBoundingClientRect();
        tip.hidden = false;
        tip.style.left = `${Math.min(r.width - 230, Math.max(0, (X(ev.t) / W) * r.width - 110))}px`;
        tip.style.top = `${(Y(ev.lane) / H) * r.height - 62}px`;
        tip.innerHTML = `<b>${esc(fmtDT(ev.t))}</b><br>${esc(ev.title)}`;
      };
      svg.onpointerleave = () => { tip.hidden = true; drag = false; };
      svg.onpointerdown = e => { drag = true; stop(); select(near(e.clientX)); svg.setPointerCapture && svg.setPointerCapture(e.pointerId); };
      svg.onpointerup = () => { drag = false; };
      svg.onkeydown = e => {
        if (e.key === "ArrowRight") { e.preventDefault(); stop(); select(Math.min(S.ev.length - 1, S.sel + 1)); }
        if (e.key === "ArrowLeft") { e.preventDefault(); stop(); select(Math.max(0, S.sel - 1)); }
      };
      svg.querySelectorAll(".kt-arc,.kt-pin").forEach(a => a.addEventListener("click", ev => { ev.stopPropagation(); focusFlag(+a.dataset.f); }));
    }

    function feas() {
      const f = S.feas || {};
      const list = S.flags.slice(0, 4).map((x, k) => `<button type="button" class="kt-flag ${x.verdict === "IMPOSSIBLE" ? "bad" : ""}" data-f="${k}">
          <span class="kt-v">${esc(VERDICT[x.verdict] || x.verdict)}</span>
          <span>${esc(x.first.location)} <em>${esc(String(x.first.timestamp).slice(5, 16))}</em> → ${esc(x.second.location)} <em>${esc(String(x.second.timestamp).slice(5, 16))}</em></span>
          <span class="mono">${esc(x.distanceKm)} km in ${esc(x.elapsedMinutes)} min = ${esc(x.impliedSpeedKmh)} km/h</span></button>`).join("");
      $("#kt-feas").innerHTML = `<h4>Travel feasibility <span class="kt-muted">Haversine, accuracy-aware</span></h4>
        <div class="kt-stats"><span><b>${f.pairsChecked ?? 0}</b> moves checked</span><span><b>${f.plausible ?? 0}</b> plausible</span>
        <span class="${f.requiresAirTravel ? "warn" : ""}"><b>${f.requiresAirTravel ?? 0}</b> need a flight</span>
        <span class="${f.impossible ? "bad" : ""}"><b>${f.impossible ?? 0}</b> impossible</span>
        ${f.simultaneousDifferentPlaces ? `<span class="bad"><b>${f.simultaneousDifferentPlaces}</b> two places at once</span>` : ""}</div>
        ${list || `<p class="kt-ok">Every recorded move is physically possible within ${esc((f.thresholds || {}).maxGroundKmh || 150)} km/h by road.</p>`}`;
      $("#kt-feas").querySelectorAll("[data-f]").forEach(b => b.onclick = () => focusFlag(+b.dataset.f));
    }

    function focusFlag(k) {
      const f = S.flags[k]; if (!f) return;
      stop();
      const i = S.ev.findIndex(e => e.evidenceId === f.first.evidenceId);
      if ($("#kt-zoom").value === "0") { $("#kt-zoom").value = "1"; }      // zoom in so the journey is visible as an arc
      if (i >= 0) { win(S.ev[i].t, true); river(); select(i); }
      sec.querySelectorAll(".kt-arc").forEach(a => a.classList.toggle("on", +a.dataset.f === k));
    }

    // zoom window around a time (whole span when zoom = 0)
    function win(t, force) {
      const z = +($("#kt-zoom") ? $("#kt-zoom").value : 0);
      if (!z) { const changed = S.t0 !== S.full[0] || S.t1 !== S.full[1]; [S.t0, S.t1] = S.full; return changed; }
      if (!force && t >= S.t0 && t <= S.t1 && S.t1 - S.t0 <= z * 864e5 * 1.01) return false;
      const w = z * 864e5;
      S.t0 = Math.max(S.full[0], t - w * 0.3); S.t1 = S.t0 + w;
      if (S.t1 > S.full[1]) { S.t1 = S.full[1]; S.t0 = Math.max(S.full[0], S.t1 - w); }
      return true;
    }
    function select(i, fromPlay) {
      const e = S.ev[i]; if (!e) return;
      if (win(fromPlay && S.playT ? S.playT : e.t)) river();
      S.sel = i;
      const svg = $("#kt-river");
      svg.querySelectorAll(".kt-dot.sel").forEach(d => d.classList.remove("sel"));
      const dot = svg.querySelector(`.kt-dot[data-i="${i}"]`); if (dot) dot.classList.add("sel");
      if (fromPlay) svg.querySelectorAll(".kt-dot").forEach(d => d.classList.toggle("lit", +d.dataset.i <= i));
      const ph = svg.querySelector("#kt-ph"); if (ph) ph.setAttribute("transform", `translate(${X(fromPlay && S.playT ? S.playT : e.t)},0)`);
      const L = LANES[e.lane];
      $("#kt-now").innerHTML = `<h4>At the playhead <span class="kt-muted">${i + 1} / ${S.ev.length}</span></h4>
        <div class="kt-when">${esc(fmtDT(e.t))}</div>
        <div class="kt-what"><i style="--c:${L.color}"></i>${esc(L.label)}${e.isAnomaly ? ` <span class="kt-warn">⚠ ${esc(String(e.anomalyType || "flagged").replace(/_/g, " ").toLowerCase())}</span>` : ""}</div>
        <p class="kt-title">${esc(e.title)}</p><p class="kt-desc">${esc(e.description || "")}</p>
        <div class="kt-meta">${e.locationName ? `<span>📍 ${esc(e.locationName)}</span>` : ""}${e.caseId ? `<a href="#case/${esc(e.caseId)}">${esc(e.caseId)}</a>` : ""}
        ${e.evidenceId ? `<button type="button" class="kt-ev" data-ev="${esc(e.evidenceId)}">${esc(e.evidenceId)}</button>` : ""}</div>`;
      const evb = $("#kt-now .kt-ev"); if (evb) evb.onclick = () => window.openEv && window.openEv(evb.dataset.ev);
      const d = iso(e.t);
      clearTimeout(S.dayTimer);
      if (d !== S.day) S.dayTimer = setTimeout(() => day(d), fromPlay ? 650 : 0);
    }

    async function day(d) {
      S.day = d;
      $("#kt-day").innerHTML = `<h4>Day routine <span class="kt-muted">${esc(d)}</span></h4><span class="kt-muted">Loading…</span>`;
      let r; try { r = await j(`/persons/${S.pid}/routine?date=${d}`); } catch (e) { $("#kt-day").innerHTML = `<h4>Day routine</h4><span class="kt-muted">Unavailable.</span>`; return; }
      if (S.day !== d) return;
      const dates = r.availableDates || [], k = dates.indexOf(d);
      const gaps = (r.gaps || []).slice(0, 2).map(g => `<li class="gap">No records ${esc(g.from || g.start || "")}–${esc(g.to || g.end || "")}${g.hours ? ` (${esc(g.hours)} h)` : ""}</li>`).join("");
      $("#kt-day").innerHTML = `<h4>Day routine
          <span class="kt-daynav"><button type="button" data-d="${esc(dates[k - 1] || "")}" ${k > 0 ? "" : "disabled"} aria-label="Previous day">‹</button>
          ${esc(new Date(d + "T00:00").toDateString().slice(0, 10))}
          <button type="button" data-d="${esc(dates[k + 1] || "")}" ${k >= 0 && k < dates.length - 1 ? "" : "disabled"} aria-label="Next day">›</button></span></h4>
        <ul>${(r.entries || []).slice(0, 9).map(x => /^no records/i.test(x.text || "") || !x.evidenceId
          ? `<li class="gap"><b>${esc(x.time)}</b>${esc(x.text || "No records")}</li>`
          : `<li data-ev="${esc(x.evidenceId || "")}"><b>${esc(x.time)}</b><i style="--c:${LANES[laneOf(x.kind)].color}"></i>${esc(x.location || x.text || "")}</li>`).join("")}${(r.entries || []).some(x => /^no records/i.test(x.text || "")) ? "" : gaps}</ul>
        ${(r.entries || []).length > 9 ? `<span class="kt-muted">+${r.entries.length - 9} more that day</span>` : ""}`;
      $("#kt-day").querySelectorAll("[data-d]").forEach(b => b.onclick = () => {
        if (!b.dataset.d) return; stop();
        const i = S.ev.findIndex(e => iso(e.t) === b.dataset.d); if (i >= 0) select(i); else day(b.dataset.d);
      });
      $("#kt-day").querySelectorAll("li[data-ev]").forEach(li => li.onclick = () => { const i = S.ev.findIndex(e => e.evidenceId === li.dataset.ev); if (i >= 0) { stop(); select(i); } });
    }

    // replay: the playhead sweeps through time; the card shows the latest record it has passed
    function play() {
      if (S.raf) return stop();
      if (!S.ev.length) return;
      $("#kt-play").textContent = "❚❚ Pause";
      $("#kt-play").classList.add("on");
      let i = S.sel >= S.ev.length - 1 ? 0 : Math.max(0, S.sel);
      S.playT = S.ev[i].t;
      let last = performance.now();
      const total = 22000;           // whole record span in ~22 s at 1×
      const step = now => {
        const sp = +$("#kt-speed").value || 1;
        S.playT += (now - last) * (S.t1 - S.t0) / total * sp; last = now;
        while (i < S.ev.length - 1 && S.ev[i + 1].t <= S.playT) i++;
        select(i, true);
        if (S.playT >= S.times[S.times.length - 1]) { stop(); select(S.ev.length - 1, true); return; }
        S.raf = requestAnimationFrame(step);
      };
      S.raf = requestAnimationFrame(step);
    }
    function stop() {
      if (S.raf) cancelAnimationFrame(S.raf);
      S.raf = 0; S.playT = null;
      const b = $("#kt-play"); if (b) { b.textContent = "▶ Replay timeline"; b.classList.remove("on"); }
      sec.querySelectorAll(".kt-dot.lit").forEach(d => d.classList.remove("lit"));
    }
    $("#kt-play").onclick = play;
    $("#kt-zoom").onchange = () => { stop(); const e = S.ev[S.sel]; win(e ? e.t : S.full[0], true); river(); if (S.sel >= 0) select(S.sel); };
    $("#kt-prev").onclick = () => { stop(); select(Math.max(0, S.sel - 1)); };
    $("#kt-next").onclick = () => { stop(); select(Math.min(S.ev.length - 1, S.sel + 1)); };
    $("#kt-dossier").onclick = () => { if (S.pid) location.hash = `#p/${S.pid}`; };
    $("#kt-ask").onclick = () => {
      if (!S.pid) return;
      const q = `Are there any location inconsistencies or unusual patterns in ${S.pid}'s timeline?`;
      const btn = document.getElementById("copilot-btn"), panel = document.getElementById("copilot-panel");
      if (panel && !panel.classList.contains("open") && btn) btn.click();
      setTimeout(() => { const inp = document.getElementById("c-input"); if (inp) { inp.value = q; document.getElementById("c-send-btn").click(); } }, 350);
    };
    // stop playback when the home view goes away
    const obs = new MutationObserver(() => { if (!document.body.contains(sec)) { stop(); obs.disconnect(); } });
    obs.observe(document.getElementById("app") || document.body, { childList: true, subtree: true });
  }

  // the TEMPORAL ENGINE page in the header (#temporal, or #temporal/P00049 for one person): the same engine, on its own page
  window.temporalV = function (el, pid) {
    el.classList.add("kt-page");
    const sec = document.createElement("section");
    sec.id = "kt"; sec.className = "story kt"; sec.setAttribute("aria-label", "Temporal engine");
    sec.innerHTML = sectionHTML().replace('<small class="no">04 TEMPORAL ENGINE</small>', '<small class="no">TEMPORAL ENGINE</small>');
    el.append(sec);
    const want = pid ? decodeURIComponent(pid).toUpperCase() : null;
    (window.KR && window.KR.ready ? window.KR.ready : Promise.resolve()).finally(() => { if (sec.isConnected) init(sec, want); });
  };

  function scan() {
    const v = document.querySelector(".view.hero");
    if (v && v.querySelector(".story") && !v.querySelector("#kt")) {
      const sec = document.createElement("section");
      sec.id = "kt"; sec.className = "story kt"; sec.setAttribute("aria-label", "Temporal engine");
      sec.innerHTML = sectionHTML();
      v.querySelector(".story").after(sec);
      const start = () => (window.KR && window.KR.ready ? window.KR.ready : Promise.resolve()).finally(() => init(sec));
      // load only when the section comes near the viewport (keeps the hero fast)
      const io = new IntersectionObserver(([e]) => { if (e.isIntersecting) { io.disconnect(); start(); } }, { root: v, rootMargin: "600px 0px" });
      io.observe(sec);
    }
  }
  new MutationObserver(scan).observe(document.getElementById("app") || document.body, { childList: true, subtree: true });
  scan();
  if (/^#temporal/.test(location.hash) && typeof route === "function" && !document.querySelector(".kt-page")) route();
})();
