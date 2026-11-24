/* KRONOS — the header WORKSPACE menu and the NEW CASE link.
   WORKSPACE: the case you are working on (with its tabs), what you opened recently, shortcuts, and the backend status.
   The active case follows you: the open case, else the open person's first case, else the last case you opened. */
(() => {
  "use strict";
  const btn = document.getElementById("kr-ws"), badge = document.getElementById("kr-ws-c");
  if (!btn) return;
  const KEY = "kr_ws_recent_v1", MAX = 6;
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const cases = () => { try { return typeof CASES !== "undefined" ? CASES : []; } catch (e) { return []; } };
  const pers = () => { try { return typeof PERS !== "undefined" ? PERS : []; } catch (e) { return []; } };
  const live = () => !!(window.KR && window.KR.live);
  const load = () => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch (e) { return []; } };
  const store = list => { try { localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX))); } catch (e) { /* private mode */ } };

  // ---- remember where the investigator has been
  function parse(hash) {
    const [v, a] = (hash || "").replace(/^#/, "").split("/");
    const id = a ? decodeURIComponent(a) : "";
    if (v === "case" && id) return { k: "case", id };
    if (v === "p" && id) return { k: "p", id };
    if (v === "graph" && id) return { k: "graph", id };
    if (v === "temporal" && id) return { k: "temporal", id };
    return null;
  }
  function remember() {
    const e = parse(location.hash);
    if (!e) return;
    const list = load().filter(x => !(x.k === e.k && x.id === e.id));
    list.unshift({ ...e, t: Date.now() });
    store(list);
    if (e.k === "case") { try { localStorage.setItem("kr_ws_case", e.id); } catch (err) { /* ignore */ } }
  }
  function activeCase() {
    const cs = cases(), e = parse(location.hash);
    const has = id => cs.find(c => c.id === id);
    if (e && e.k === "case" && has(e.id)) return has(e.id);
    if (e && (e.k === "p" || e.k === "temporal" || e.k === "graph")) {
      const c = cs.find(x => (x.prim || []).includes(e.id)) || cs.find(x => (x.ppl || []).includes(e.id)) || has(e.id);
      if (c) return c;
    }
    let last = null; try { last = localStorage.getItem("kr_ws_case"); } catch (err) { /* ignore */ }
    return (last && has(last)) || cs.slice().sort((a, b) => ((b._api || {}).flaggedFindings || 0) - ((a._api || {}).flaggedFindings || 0))[0] || null;
  }
  const ago = t => { const s = (Date.now() - t) / 1000; return s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : `${Math.floor(s / 86400)} d ago`; };
  function label(x) {
    const P = pers().find(p => p.id === x.id), C = cases().find(c => c.id === x.id);
    if (x.k === "case") return { href: `#case/${x.id}`, what: "Case workspace", name: C ? C.t : x.id };
    if (x.k === "p") return { href: `#p/${x.id}`, what: "Dossier", name: P ? P.n : x.id };
    if (x.k === "graph") return { href: `#graph/${x.id}`, what: "Network graph", name: P ? P.n : C ? C.t : x.id };
    return { href: `#temporal/${x.id}`, what: "Temporal engine", name: P ? P.n : x.id };
  }

  // ---- the header button: shows the active case
  function paint() {
    const C = activeCase();
    badge.textContent = C ? C.id : "";
    btn.classList.toggle("live", live());
    btn.title = C ? `Workspace — active case ${C.id}${C.t ? `: ${C.t}` : ""}` : "Workspace";
    if (panel.classList.contains("open")) build();
  }

  // ---- the panel
  const panel = document.createElement("div");
  panel.className = "kr-wsp"; panel.id = "kr-wsp"; panel.setAttribute("role", "dialog"); panel.setAttribute("aria-label", "Workspace");
  document.body.append(panel);
  const TABS = [["summary", "Summary"], ["nbe", "Hypotheses"], ["evidence", "Evidence"], ["diary", "Diary"]];
  function build() {
    const C = activeCase(), L = live();
    const recent = load().filter(x => x.k !== "case" || !C || x.id !== C.id).slice(0, 5);
    const people = C ? (C.prim && C.prim.length ? C.prim : C.ppl || []).slice(0, 4).map(id => pers().find(p => p.id === id) || { id, n: id }) : [];
    const h = live() && window.KR.st && window.KR.st.health;
    const llm = h && h.llm && h.llm.available;
    panel.innerHTML = `
      <div class="kr-wsp-h"><span>YOUR WORKSPACE</span><button type="button" class="kr-wsp-x" aria-label="Close">×</button></div>
      ${C ? `<div class="kr-wsp-case">
        <div class="kr-wsp-k">ACTIVE CASE</div>
        <a class="kr-wsp-title" href="#case/${esc(C.id)}"><b>${esc(C.id)}</b> ${esc(C.t || "")}</a>
        <div class="kr-wsp-meta">${[C.cat, C.st, C.pr && `${C.pr} priority`, C.ev != null && `${C.ev} records`].filter(Boolean).map(esc).join(" · ")}</div>
        <div class="kr-wsp-tabs">${TABS.filter(([k]) => L || k !== "diary").map(([k, t]) => `<button type="button" data-tab="${k}">${t}</button>`).join("")}</div>
        ${people.length ? `<div class="kr-wsp-ppl">${people.map(p => `<a href="#p/${esc(p.id)}" title="Open dossier"><b>${esc(p.n)}</b> ${esc(p.id)}</a>`).join("")}</div>` : ""}
        <button type="button" class="kr-wsp-go" data-tab="summary">Open case workspace →</button>
      </div>` : ""}
      <div class="kr-wsp-k">RECENTLY OPENED</div>
      ${recent.length ? `<ul class="kr-wsp-rec">${recent.map(x => { const l = label(x); return `<li><a href="${esc(l.href)}"><span><b>${esc(l.name)}</b> <i>${esc(l.what)}${x.id !== l.name ? ` · ${esc(x.id)}` : ""}</i></span><em>${ago(x.t)}</em></a></li>`; }).join("")}</ul>`
        : `<p class="kr-wsp-empty">Cases, dossiers and graphs you open will appear here.</p>`}
      <div class="kr-wsp-k">SHORTCUTS</div>
      <div class="kr-wsp-sc">
        <button type="button" data-act="new">+ New case</button>
        <a href="#dash">All cases</a>
        <a href="#temporal${C && C.prim && C.prim[0] ? `/${esc(C.prim[0])}` : ""}">Temporal engine</a>
        <a href="#graph${C && C.prim && C.prim[0] ? `/${esc(C.prim[0])}` : ""}">Network graph</a>
      </div>
      <div class="kr-wsp-f${L ? " on" : ""}">${window.KRstatic ? `Online prototype · read-only snapshot (${esc(window.KRstatic.built || "")}) · ${cases().length} cases · ${pers().length} persons · AI in the full install` : L ? `Live backend · ${cases().length} cases · ${pers().length} persons · local AI ${llm ? "ready" : "offline"}`
        : "Offline demonstration data · the live backend is not connected"}</div>`;
    panel.querySelector(".kr-wsp-x").onclick = () => open(false);
    panel.querySelectorAll("[data-tab]").forEach(b => b.onclick = () => {
      open(false);
      if (window.KRcmd) window.KRcmd.go(`case/${C.id}`, b.dataset.tab);
      else { window._kr_cur_tab = b.dataset.tab; location.hash = `#case/${C.id}`; }
    });
    const nb = panel.querySelector("[data-act=new]");
    if (nb) nb.onclick = () => { open(false); newCase(); };
  }
  function place() {
    const r = btn.getBoundingClientRect();
    panel.style.top = `${Math.round(r.bottom + 10)}px`;
    let right = Math.max(10, Math.round(innerWidth - r.right));
    if (innerWidth - right - panel.offsetWidth < 10) right = Math.max(10, innerWidth - panel.offsetWidth - 10);   // keep it on screen
    panel.style.right = `${right}px`;
  }
  function open(on) {
    if (on) { build(); place(); }
    panel.classList.toggle("open", on);
    btn.setAttribute("aria-expanded", String(on));
    if (on) { const f = panel.querySelector(".kr-wsp-title, a, button:not(.kr-wsp-x)"); f && f.focus({ preventScroll: true }); }
  }
  btn.addEventListener("click", e => { e.stopPropagation(); open(!panel.classList.contains("open")); });
  panel.addEventListener("click", e => { e.stopPropagation(); if (e.target.closest("a")) open(false); });
  document.addEventListener("click", () => { if (panel.classList.contains("open")) open(false); });
  addEventListener("keydown", e => { if (e.key === "Escape" && panel.classList.contains("open")) { open(false); btn.focus(); } });
  addEventListener("resize", () => { if (panel.classList.contains("open")) place(); });

  // ---- NEW CASE (header link and the phone menu): open the intake form over the current page
  function newCase() { (function o(n) { if (window.KRintake) window.KRintake.open(1); else if (n < 40) setTimeout(() => o(n + 1), 150); })(0); }
  document.addEventListener("click", e => {
    const a = e.target.closest && e.target.closest('a[href="#new"]');
    if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault(); newCase();
  });

  addEventListener("hashchange", () => { remember(); paint(); });
  addEventListener("kr:data", paint);
  if (window.KR && window.KR.ready) window.KR.ready.finally(paint);
  remember(); paint();
})();
