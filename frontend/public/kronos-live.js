/* KRONOS live backend integration.
 *
 * Connects the existing KRONOS interface (index.html) to the KRONOS backend API.
 * - If the API is reachable, the interface's data arrays (CASES, PERS, EVT, GRAPH_NODES, GRAPH_EDGES)
 *   are filled from the backend and views lazily load person timelines / case evidence.
 * - If the API is NOT reachable (e.g. static Netlify/Vercel deploy), nothing changes: the original
 *   offline demonstration data and behaviour are used exactly as before.
 * Visual design is untouched: all markup produced here reuses the existing classes and inline styles.
 */
(function () {
  const API = localStorage.getItem("kr_api") || "/api";
  const st = { live: false, persons: new Set(), cases: new Set(), graphFocus: undefined, caseData: {}, personData: {}, health: null };
  const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const TY = { FIR: "FIR", CDR: "Comm", COMMUNICATION: "Comm", SOCIAL: "Comm", LOCATION: "Loc", FINANCIAL: "Fin", CROSS_CASE: "Cross" };
  const STATUS = { ACTIVE: "Active", UNDER_REVIEW: "Under review", CHARGE_SHEETED: "Closed", ARCHIVED: "Closed", CLOSED: "Closed" };
  const cap = s => s ? s[0] + s.slice(1).toLowerCase() : "Medium";
  const inr = n => "₹" + Number(n || 0).toLocaleString("en-IN", { maximumFractionDigits: 0 });

  async function j(path, opt = {}, timeout = 15000) {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), timeout);
    try {
      const r = await fetch(API + path, { ...opt, signal: ctl.signal, headers: { "content-type": "application/json", ...(opt.headers || {}) } });
      if (!r.ok) throw new Error(path + " → HTTP " + r.status);
      return await r.json();
    } finally { clearTimeout(t); }
  }

  /* ------------------------------------------------------------------ mapping to interface shapes */
  const ROLE_TXT = { PRINCIPAL_ACCUSED: "Principal accused (recorded)", ACCUSED: "Accused (recorded)", ASSOCIATE: "Associate",
    COMPLAINANT: "Complainant", VICTIM: "Victim", WITNESS: "Witness", MENTIONED: "Mentioned", RECORD_SUBJECT: "Records obtained" };
  function mapCase(c) {
    return { id: c.id, t: c.title, cat: c.offenceCategory, st: STATUS[c.status] || "Active", pr: cap(c.priority), ev: c.evidenceCount,
      act: (c.lastActivity || "").slice(0, 10), ppl: c.personIds, prim: c.primarySuspectIds, desc: c.description, _api: c };
  }
  function mapPerson(p) {
    const roles = {};
    (p.recordedRoles || []).forEach(r => { (roles[r.role] = roles[r.role] || []).push(r.caseId); });
    const order = ["PRINCIPAL_ACCUSED", "ACCUSED", "ASSOCIATE", "COMPLAINANT", "VICTIM", "WITNESS", "MENTIONED", "RECORD_SUBJECT"];
    const role = order.filter(r => roles[r]).map(r => `${ROLE_TXT[r]} • ${roles[r].join(", ")}`).join(" | ");
    return { id: p.id, n: p.name, role, first: p.firstSeen || "2025-01-01", last: p.lastSeen || "2025-01-01",
      ph: (p.contactNumbers || []).join(" • ") || "—", dev: (p.associatedDevices || []).join(" • ") || "—",
      ents: [...(p.bankAccounts || []), ...(p.knownLocations || []).slice(0, 3)], notes: p.notes + (p.alias ? ` Possible other identity: ${p.alias}.` : ""), _api: p };
  }
  function mapTimelineEvent(e, pid) {
    const derived = e.modality === "CROSS_CASE";
    return { id: derived ? e.id : e.evidenceId, evd: e.evidenceId, p: [pid, e.counterpartyId].filter(Boolean), d: e.timestamp.slice(0, 10),
      tm: e.timeStr, ty: TY[e.modality] || "Cross", k: (e.isAnomaly ? "⚠ " : "") + e.title, c: e.caseId, s: e.description,
      rel: cap(e.reliability), prov: "RECORD", src: e.sourceRecordId, mod: e.modality, anomaly: e.anomalyType, derived };
  }
  function mapEvidence(r) {
    const iso = r.iso || "";
    return { id: r.evidenceId, evd: r.evidenceId, p: r.relatedPersonIds || [], d: iso.slice(0, 10) || "2025-01-01", tm: iso.slice(11, 16) || "--:--",
      ty: TY[r.modality] || "Cross", k: (r.description || "").slice(0, 90), c: r.caseId, s: r.description, rel: cap(r.sourceReliability),
      prov: "RECORD", src: r.sourceRecordId, mod: r.modality, meta: r.metadata, loc: r.locationName };
  }
  function upsertEvents(list) {
    const byId = new Map(EVT.map((e, i) => [e.id, i]));
    list.forEach(e => {
      if (byId.has(e.id)) {
        const cur = EVT[byId.get(e.id)];
        cur.p = [...new Set([...(cur.p || []), ...(e.p || [])])];
        Object.keys(e).forEach(k => { if (cur[k] == null) cur[k] = e[k]; });
      } else { byId.set(e.id, EVT.length); EVT.push(e); }
    });
    EVT.sort((a, b) => (a.d + a.tm).localeCompare(b.d + b.tm));
  }

  /* ------------------------------------------------------------------ text → HTML with clickable citations */
  function fmt(text) {
    let h = esc(text).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    h = h.replace(/\b(EVD-[A-Z]+\d+)\b/g, '<button class="ev2" data-j="$1" onclick="openEv(\'$1\')">$1</button>');
    h = h.replace(/\b(CASE\d{3})\b/g, '<a class="kr-a" href="#case/$1">$1</a>').replace(/\b(P\d{5})\b/g, '<a class="kr-a" href="#p/$1">$1</a>');
    h = h.replace(/^\[RECORDED FACTS\]\s*/, '<div class="lab">RECORDED FACTS · local Llama 3.1 · evidence-grounded</div>')
         .replace(/^\[ANALYTICAL HYPOTHESIS — NOT FACT\]\s*/, '<div class="lab">DETECTIVE · ANALYTICAL HYPOTHESIS — NOT FACT</div>')
         .replace(/^\[(RECORDED FACTS|ANALYTICAL HYPOTHESIS)[^\]]*\]\s*/, '<div class="lab">$1 · deterministic (LLM unavailable)</div>');
    return h.replace(/\n/g, "<br>");
  }

  const lang = () => localStorage.getItem("kr_copilot_lang") || "en";
  const toHistory = arr => (arr || []).map(h => ({ role: (h.r === "u" || h.role === "user") ? "user" : "assistant",
    text: String(h.t ?? h.text ?? "").replace(/<details[\s\S]*?<\/details>/g, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim() }))
    .filter(h => h.text && h.text !== "…" && !/^(Mode switched|Retrieving evidence)/.test(h.text) && !/Mode switched\.$/.test(h.text)).slice(-8);
  const T = {
    diaryTab: { en: "5. Case Diary & Draft Report", hi: "5. केस डायरी और मसौदा रिपोर्ट", gu: "5. કેસ ડાયરી અને મુસદ્દો અહેવાલ", pa: "5. ਕੇਸ ਡਾਇਰੀ ਅਤੇ ਖਰੜਾ ਰਿਪੋਰਟ" },
    search: { en: "Search evidence in natural language — e.g. “cash deposits above 40,000 in March”, “calls at night”, “messages mentioning an account”",
              hi: "प्राकृतिक भाषा में साक्ष्य खोजें — जैसे “मार्च में 40,000 से अधिक नकद जमा”", gu: "કુદરતી ભાષામાં પુરાવા શોધો — દા.ત. “માર્ચમાં 40,000થી વધુ રોકડ જમા”",
              pa: "ਕੁਦਰਤੀ ਭਾਸ਼ਾ ਵਿੱਚ ਸਬੂਤ ਲੱਭੋ — ਜਿਵੇਂ “ਮਾਰਚ ਵਿੱਚ 40,000 ਤੋਂ ਵੱਧ ਨਕਦ ਜਮ੍ਹਾਂ”" },
  };
  const t = k => (T[k] || {})[lang()] || (T[k] || {}).en || k;

  async function ask(q, opt = {}) {
    const body = { query: q, mode: opt.mode === "D" || opt.mode === "DETECTIVE" ? "DETECTIVE" : "ASSISTANCE",
      caseId: opt.caseId || null, personId: opt.personId || null, modality: opt.modality || null,
      history: opt.history || [], lang: opt.lang || lang() };
    const r = await j("/assistant/query", { method: "POST", body: JSON.stringify(body) }, 240000);
    const m = r.meta || {};
    const reasoning = [
      ...(m.standaloneQuery ? [`Follow-up understood as: "${m.standaloneQuery}" (${m.conversationTurnsUsed} earlier turns used)`] : []),
      ...(m.queryLanguage && m.queryLanguage !== "en" ? [`Question language: ${m.queryLanguage} → translated to English for retrieval`] : []),
      `Scope: ${body.caseId || "all cases"}${body.personId ? " · person " + body.personId : ""}${body.modality ? " · filter " + body.modality : ""}`,
      `Intents detected: ${(m.intents || []).join(", ")}`,
      `Engines consulted: ${(m.sources || []).join(", ")}`,
      `${m.evidenceItems} of ${m.evidenceCandidates} ranked evidence items sent in ${m.batches} batch(es) to ${m.model || "deterministic fallback"}`,
      `Citations validated against supplied evidence: ${(r.referencedEvidenceIds || []).length} kept, ${(m.removedCitations || []).length} removed`,
    ];
    let html = fmt(r.text);
    if (r.textEnglish) html += `<details style="margin-top:6px;font-size:11px"><summary>English (verified original)</summary>${fmt(r.textEnglish)}</details>`;
    if (!/EVD-[A-Z]+\d+/.test(r.text) && (r.referencedEvidenceIds || []).length) {
      html += `<div class="mono" style="margin-top:6px;font-size:10px">Grounding records (not cited inline by the model): ${r.referencedEvidenceIds.slice(0, 6).map(i => `<button class="ev2" data-j="${i}" onclick="openEv('${i}')">${i}</button>`).join(" ")}</div>`;
    }
    return { html, reasoning, raw: r };
  }

  /* ------------------------------------------------------------------ loaders */
  async function loadPerson(pid) {
    try {
      const [tl, ids, feas, hist] = await Promise.all([j(`/persons/${pid}/timeline?limit=600`), j(`/persons/${pid}/identity-candidates`),
        j(`/persons/${pid}/feasibility`).catch(() => null), j(`/persons/${pid}/history`).catch(() => null)]);
      upsertEvents(tl.map(e => mapTimelineEvent(e, pid)));
      const P = PERS.find(p => p.id === pid);
      const mainCase = P && P._api ? (P._api.primarySuspectCases[0] || P._api.casesMentioned[0]) : null;
      st.personData[pid] = { identity: ids, feas, hist, nbe: mainCase ? await j(`/cases/${mainCase}/next-evidence`).catch(() => []) : [], mainCase };
    } catch (e) { console.warn("KRONOS: person load failed", e); }
    st.persons.add(pid);
  }
  async function loadCase(cid) {
    try {
      const [ev, summary, nbe, hyp, prio] = await Promise.all([j(`/cases/${cid}/evidence`), j(`/cases/${cid}/summary`),
        j(`/cases/${cid}/next-evidence`), j(`/cases/${cid}/hypotheses`), j(`/cases/${cid}/priority`)]);
      upsertEvents(ev.map(mapEvidence));
      st.caseData[cid] = { summary, nbe, hyp, prio, evCount: ev.length, diary: await j(`/cases/${cid}/diary`).catch(() => null) };
    } catch (e) { console.warn("KRONOS: case load failed", e); st.caseData[cid] = {}; }
    st.cases.add(cid);
  }
  async function fetchEvidence(id) {
    try { const r = await j(`/evidence/${encodeURIComponent(id)}`); upsertEvents([mapEvidence(r)]); return true; }
    catch (e) { toast("Evidence record " + id + " not found"); return false; }
  }
  async function loadGraph(focus) {
    const g = await j(`/graph/subgraph?focus=${encodeURIComponent(focus || "")}&depth=2&limit=80`);
    const COLOR = { PERSON: 0xB96D50, CASE: 0xC69A55, ORGANIZATION: 0xA86F45, LOCATION: 0xD79A4A, ACCOUNT: 0x7B8062, DEVICE: 0x8A7E72, EVIDENCE: 0x433A32 };
    const nodes = g.nodes.map(n => {
      const type = n.entityType === "COMPANY" ? "ORGANIZATION" : n.type;
      const P = PERS.find(p => p.id === n.id);
      const accused = P && P._api && P._api.primarySuspectCasesCount > 0;
      return { id: n.id, label: n.label, sublabel: n.sublabel || n.entityType, type, val: Math.max(7, Math.min(22, (n.val || 6) * 1.4)),
        color: type === "PERSON" ? (accused ? 0xB96D50 : 0x7B8062) : COLOR[type] || 0xA86F45, role: n.role };
    });
    const edges = g.edges.map(e => ({ source: e.source, target: e.target, label: `${e.label} (${e.weight}) · ${e.evidenceIds.slice(0, 2).join(", ")}`,
      modality: e.modality === "CROSS_CASE" ? "CROSS" : e.modality, weight: Math.min(5, 1 + Math.log2(1 + e.weight)), isAnomaly: e.isAnomaly }));
    GRAPH_NODES.splice(0, GRAPH_NODES.length, ...nodes);
    GRAPH_EDGES.splice(0, GRAPH_EDGES.length, ...edges);
    st.graphFocus = focus;
  }

  /* ------------------------------------------------------------------ shared UI fragments (existing styles) */
  const loading = msg => `<div style="max-width:1280px;margin:0 auto;padding:60px 20px;text-align:center"><div class="mono" style="font-size:12px;color:var(--terra)">${esc(msg)}</div></div>`;
  function recordBadge(e) {
    return `<div style="background:rgba(123,128,98,0.12);border:1px solid rgba(123,128,98,0.3);padding:10px 14px;border-radius:6px;margin:12px 0;font-size:12px">
      <div style="font-weight:700;color:var(--olive);text-transform:uppercase;letter-spacing:0.5px">KRONOS Evidence Record${e.derived ? " — derived marker" : ""}</div>
      <div style="margin-top:4px;color:var(--ink)"><b>Source record:</b> ${esc(e.src || "—")} · <b>Modality:</b> ${esc(e.mod || e.ty)}${e.anomaly ? ` · <b>Flag:</b> ${esc(e.anomaly)}` : ""}</div>
      <div style="margin-top:2px;font-size:11px;color:var(--ink)">Synthetic investigation data. Flags are investigative indicators requiring verification, not findings of guilt.</div>
      ${e.derived ? "" : `<div style="margin-top:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap"><button class="go" style="margin:0;padding:4px 10px;font-size:11px" onclick="KR.verify('${esc(e.evd || e.id)}', this)">Verify integrity (SHA-256 ledger)</button><button class="go" style="margin:0;padding:4px 10px;font-size:11px" onclick="KR.proof('${esc(e.evd || e.id)}', this)">Merkle proof (agency quorum)</button><button class="go" style="margin:0;padding:4px 10px;font-size:11px" onclick="KR.custody('${esc(e.evd || e.id)}', this)">Chain of custody</button></div><div class="mono kr-verify" style="font-size:10px;margin-top:6px;line-height:1.5"></div>`}
    </div>`;
  }
  async function proof(id, btn) {
    const out = btn.parentElement.parentElement.querySelector(".kr-verify");
    out.textContent = "building inclusion proof…";
    try {
      const r = await j(`/evidence/${encodeURIComponent(id)}/proof`);
      const sig = Object.entries(r.signatures || {}).map(([n, ok]) => `${n} ${ok ? "✓" : "✗"}`).join(" · ");
      out.innerHTML = `<b style="color:${r.result === "INCLUDED" ? "var(--olive)" : "var(--terra)"}">${esc(r.result)}</b> in ${esc(r.file)} batch of ${esc(r.batchRecords)} records · ${(r.path || []).length}-step Merkle path · anchored root ${esc((r.anchoredRoot || "").slice(0, 16))}… (block #${esc(r.anchorBlock)})<br>Agency signatures: ${esc(sig)} — quorum ${r.quorumMet ? "met" : "NOT met"}<br><span style="opacity:.75">${esc(r.note || "")}</span>`;
    } catch (e) { out.textContent = "proof unavailable"; }
  }
  async function custody(id, btn) {
    const out = btn.parentElement.parentElement.querySelector(".kr-verify");
    try {
      const h = await j(`/evidence/${encodeURIComponent(id)}/history`);
      out.innerHTML = `<b>Chain of custody (${h.length} ledger events)</b><br>` + h.slice(-12).map(b => `#${b.block} ${esc(b.ts.slice(0, 19).replace("T", " "))} · ${esc(b.eventType)} · ${esc(b.actor)}${b.metadata && b.metadata.result ? " · " + esc(b.metadata.result) : ""}`).join("<br>");
    } catch (e) { out.textContent = "custody history unavailable"; }
  }
  async function verify(id, btn) {
    const out = btn.parentElement.parentElement.querySelector(".kr-verify");
    out.textContent = "verifying…";
    try {
      const r = await j(`/evidence/${encodeURIComponent(id)}/verify`, { method: "POST" });
      out.innerHTML = `<b style="color:${r.result === "VERIFIED" ? "var(--olive)" : "var(--terra)"}">${esc(r.result)}</b> · block #${esc(r.ledgerBlock)} · ${esc((r.recomputedHash || "").slice(0, 16))}… <br><span style="opacity:.75">${esc(r.note || "")}</span>`;
    } catch (e) { out.textContent = "verification unavailable"; }
  }

  /* ------------------------------------------------------------------ profile augmentation */
  function afterProfile(el, pid) {
    const d = st.personData[pid] || {};
    const panel = [...el.querySelectorAll("div")].find(x => x.firstElementChild && /NEXT BEST EVIDENCE TO EXAMINE/.test(x.firstElementChild.textContent || "") && x.children.length >= 3);
    if (panel) {
      const own = (d.nbe || []).find(x => x.personId === pid);
      const r = own || (d.nbe || [])[0];
      const scope = own ? "" : (r && r.personId ? ` · CASE-LEVEL ITEM (concerns ${r.personId})` : " · CASE-LEVEL ITEM");
      panel.innerHTML = r ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px">
          <span style="font-size:10px;font-weight:700;color:var(--terra);text-transform:uppercase;letter-spacing:0.6px">NEXT BEST EVIDENCE TO EXAMINE</span>
          <span style="background:rgba(185,109,80,0.2);color:var(--terra);font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px">${esc(r.priority)} · VALUE ${esc(r.valueScore ?? "—")} · ${esc(r.status.replace(/_/g, " "))}${esc(scope)}</span></div>
        <div style="font-size:12px;font-weight:600;color:var(--ink)">${esc(r.evidenceType)}</div>
        <div style="font-size:11px;color:var(--ink);opacity:0.85;margin-top:2px">${esc(r.reason)} — <i>${esc(r.verificationAction)}</i></div>
        <div style="margin-top:8px"><button class="go" style="margin:0;padding:4px 10px;font-size:11px" onclick="window._kr_cur_tab='nbe';location.hash='case/${esc(d.mainCase)}'">Open Case Workspace (${esc(d.mainCase)}) →</button></div>`
        : `<div style="font-size:10px;font-weight:700;color:var(--terra);text-transform:uppercase;letter-spacing:0.6px">NEXT BEST EVIDENCE TO EXAMINE</div><div style="font-size:11px;margin-top:4px">No recommendations for this person in current records.</div>`;
      if (d.mainCase && !el.querySelector(".kh-dossier")) {
        const slot = document.createElement("div");
        slot.className = "kh-dossier";
        slot.innerHTML = `<div class="kh-muted" style="padding:10px 2px">Testing the line of inquiry against alternate hypotheses for ${esc(pid)}…</div>`;
        panel.after(slot);
        j(`/cases/${encodeURIComponent(d.mainCase)}/hypotheses?personId=${encodeURIComponent(pid)}`, {}, 180000)   // cold caches (e.g. right after a registration) can take a while
          .then(r => { const h = (r.hypotheses || [])[0]; slot.innerHTML = h ? `<div class="kh-dtitle">LINE OF INQUIRY vs ALTERNATE HYPOTHESES · ${esc(d.mainCase)}</div>` + hypCard(h, 0, true) : ""; })
          .catch(() => { slot.innerHTML = ""; });
      }
      const cands = (d.identity || []).filter(c => c.band !== "INSUFFICIENT_EVIDENCE" || c.contradicting.length).slice(0, 2);
      if (cands.length) {
        const box = document.createElement("div");
        box.style.cssText = "background:rgba(198,154,85,0.1);border:1px solid rgba(198,154,85,0.4);border-radius:8px;padding:12px 14px;margin-top:10px";
        box.innerHTML = cands.map(c => {
          const other = c.personA === pid ? c.personB : c.personA, oname = c.personA === pid ? c.nameB : c.nameA;
          return `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px"><span style="font-size:10px;font-weight:700;color:var(--gold);text-transform:uppercase;letter-spacing:0.6px">POSSIBLE SAME PERSON — REVIEW REQUIRED</span>
            <span style="background:rgba(198,154,85,0.25);color:var(--gold);font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px">${esc(c.band)} · ${esc(c.score)} · ${esc((c.basis || "identifier").toUpperCase())} · ${esc(c.status)}</span></div>
            <div style="font-size:12px;font-weight:600;color:var(--ink)"><a class="kr-a" href="#p/${esc(other)}">${esc(oname)} (${esc(other)})</a></div>
            <div style="font-size:11px;color:var(--ink);opacity:0.85;margin-top:2px">${c.reasons.slice(0, 4).map(esc).join(" · ")}</div>
            ${c.contradicting.length ? `<div style="font-size:11px;color:var(--terra);margin-top:2px">Contradicting: ${c.contradicting.slice(0, 2).map(x => esc(x.why)).join(" · ")}</div>` : ""}
            <div style="margin-top:6px;display:flex;gap:6px">${["CONFIRMED", "REJECTED", "DEFERRED"].map(dc => `<button class="go" style="margin:0;padding:3px 9px;font-size:10px" onclick="KR.review('${esc(c.candidateId)}','${dc}','${esc(pid)}')">${dc === "CONFIRMED" ? "Confirm" : dc === "REJECTED" ? "Reject" : "Defer"}</button>`).join("")}
            <span class="mono" style="font-size:10px;opacity:.7;align-self:center">never merged automatically</span></div>`;
        }).join('<hr style="border:0;border-top:1px solid rgba(198,154,85,0.3);margin:8px 0">');
        panel.after(box);
      }
      const extra = document.createElement("div");
      extra.style.cssText = "background:rgba(123,128,98,0.10);border:1px solid rgba(123,128,98,0.35);border-radius:8px;padding:12px 14px;margin-top:10px";
      const f = d.feas, h = d.hist;
      const recs = h ? [...h.priorRecords, ...h.priorRecordsViaPossibleIdentity] : [];
      extra.innerHTML = `${f ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px"><span style="font-size:10px;font-weight:700;color:var(--olive);text-transform:uppercase;letter-spacing:0.6px">TRAVEL FEASIBILITY (HAVERSINE)</span>
          <span style="background:rgba(123,128,98,0.2);color:var(--olive);font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px">${f.impossible + f.simultaneousDifferentPlaces ? "INCONSISTENCY FOUND" : f.requiresAirTravel ? "AIR TRAVEL ONLY" : "CONSISTENT"}</span></div>
        <div style="font-size:11px;color:var(--ink)">${f.pairsChecked} consecutive location pairs checked · ${f.plausible} plausible · ${f.requiresAirTravel} need air travel · ${f.impossible + f.simultaneousDifferentPlaces} impossible ${f.flags.slice(0, 3).map(x => evBtn(x.second.evidenceId)).join(" ")}</div>
        <div style="font-size:10px;opacity:.75;margin-top:2px">Accuracy-aware: distance minus both records' accuracy radii; thresholds ${f.thresholds.maxGroundKmh} km/h road, ${f.thresholds.maxAirKmh} km/h air.</div>` : ""}
        <div style="display:flex;justify-content:space-between;align-items:center;margin:10px 0 4px"><span style="font-size:10px;font-weight:700;color:var(--olive);text-transform:uppercase;letter-spacing:0.6px">CRIMINAL HISTORY LINKAGE — CONTEXT, NOT EVIDENCE</span>
          <span style="background:rgba(123,128,98,0.2);color:var(--olive);font-size:9px;font-weight:700;padding:2px 6px;border-radius:3px">${recs.length} LINKED RECORD${recs.length === 1 ? "" : "S"}</span></div>
        ${recs.slice(0, 3).map(l => `<div style="font-size:11px;color:var(--ink);margin:4px 0;padding-top:4px;border-top:1px dashed rgba(123,128,98,0.3)">
            <b>${esc(l.record.offence)}</b> (${esc(l.record.sections)}) · ${esc((l.record.date || "").slice(0, 4))} · <b>${esc((l.record.disposition || "").replace(/_/g, " "))}</b> ${evBtn(l.record.evidenceId)}
            <br><span style="opacity:.85">${esc(l.band)} link (${esc(l.score)}) · ${esc(l.status)}${l.viaPersonId ? ` · via possible identity <a class="kr-a" href="#p/${esc(l.viaPersonId)}">${esc(l.viaPersonId)}</a>` : ""} — ${l.reasons.slice(0, 2).map(esc).join(" · ")}</span>
            ${l.contradicting.length ? `<br><span style="color:var(--terra)">Contradicting: ${l.contradicting.slice(0, 2).map(esc).join(" · ")}</span>` : ""}
            ${l.viaPersonId ? "" : `<br>${["CONFIRMED", "REJECTED"].map(dc => `<button class="go" style="margin:3px 4px 0 0;padding:2px 8px;font-size:10px" onclick="KR.reviewHistory('${esc(l.linkId)}','${dc}','${esc(pid)}')">${dc === "CONFIRMED" ? "Confirm link" : "Reject link"}</button>`).join("")}`}</div>`).join("") || `<div style="font-size:11px">No prior record linked to this profile.</div>`}
        ${h && h.associatedCases.length ? `<div style="font-size:11px;margin-top:6px"><b>Network-associated cases:</b> ${h.associatedCases.slice(0, 6).map(a => `<a class="kr-a" href="#case/${esc(a.caseId)}" title="${esc(a.via.map(v => (v.personId || v.case) + ": " + v.basis.join(", ")).join(" | "))}">${esc(a.caseId)}</a>`).join(" · ")}</div>` : ""}
        <div style="font-size:10px;opacity:.75;margin-top:4px">Prior records never feed priority or hypothesis scores; acquittals mean no finding of guilt.</div>`;
      (el.querySelector(".dos .gbtn") || panel).before(extra);
    }
  }
  async function reviewHistory(linkId, decision, pid) {
    const note = prompt(`Reason for ${decision === "CONFIRMED" ? "confirming" : "rejecting"} this prior-record link (audited):`, "");
    if (note === null) return;
    try {
      await j(`/history/links/${encodeURIComponent(linkId)}/review`, { method: "POST", body: JSON.stringify({ decision, note, reviewer: "investigator" }) });
      toast(`Prior-record link ${decision.toLowerCase()} — audited`);
      st.persons.delete(pid); route();
    } catch (e) { toast("Review failed"); }
  }
  async function review(cid, decision, pid) {
    const note = prompt(`Reason for marking this identity match as ${decision} (recorded in audit trail):`, "") ;
    if (note === null) return;
    try {
      await j(`/identity/candidates/${cid}/review`, { method: "POST", body: JSON.stringify({ decision, note, reviewer: "investigator" }) });
      toast(`Identity match ${decision.toLowerCase()} — audited`);
      st.persons.delete(pid); route();
    } catch (e) { toast("Review failed"); }
  }

  /* ------------------------------------------------------------------ live case workspace (same layout) */
  const card = (title, color, body) => `<div style="background:var(--parchment);padding:16px;border-radius:6px;border-left:3px solid var(--${color})"><b style="font-size:14px;color:var(--${color})">${title}</b><br>${body}</div>`;
  const evBtn = id => `<button class="ev2" onclick="openEv('${esc(id)}')">${esc(id)}</button>`;
  const evBtns = ids => (ids || []).filter(i => /^EVD-/.test(i)).slice(0, 6).map(evBtn).join(" ");
  // Competing hypotheses: the line of inquiry (H) against the alternates (A1…A8, why the person may NOT have been involved)
  const FAV = { LINE_OF_INQUIRY: "Line of inquiry better supported", ALTERNATE: "Alternate better supported",
                OPEN: "Open — test the alternates", LINE_OF_INQUIRY_UNCONTESTED: "No alternate supported yet" };
  function hypCard(h, i, compact) {
    const sup = h.supporting || [], alts = h.alternateHypotheses || [], cmp = h.comparison || {}, fr = h.framing || {};
    const P = typeof PERS !== "undefined" ? PERS.find(p => p.id === h.personId) : null, nm = h.name || (P ? P.n : h.personId);
    const meter = (v, cls) => `<span class="kh-meter ${cls || ""}"><i style="width:${Math.round((v || 0) * 100)}%"></i></span>`;
    const c = h.confidence || {};
    return `<div class="kh${compact ? " compact" : ""}">
      <div class="kh-top"><span class="kh-badge">HYPOTHESIS ${String.fromCharCode(65 + i)} · ${esc((h.investigativePriority || "").toUpperCase())}</span>
        ${compact ? "" : `<a class="kr-a" href="#p/${esc(h.personId)}">${esc(nm)} dossier →</a>`}<span class="kh-review">Human review required</span></div>
      <p class="kh-note">${esc(fr.note || "Neither side is a finding; strengths are not probabilities.")}</p>
      <div class="kh-grid">
        <div class="kh-col kh-h">
          <div class="kh-tag">H · LINE OF INQUIRY</div>
          <h4>${esc(fr.lineOfInquiry || h.hypothesis)}</h4>
          <div class="kh-str">${meter(h.lineOfInquiryStrength)} <b>${(h.lineOfInquiryStrength ?? 0).toFixed(2)}</b></div>
          <div class="kh-sub">Evidence relied on</div>
          ${sup.map(x => `<div class="kh-ev"><span class="kh-src">${esc(x.source)}</span>${esc(x.text)} ${evBtns(x.evidenceIds)}
              ${(x.explainedBy || []).length ? `<div class="kh-exp">could be explained by ${x.explainedBy.map(c => `<b>${esc(c)}</b>`).join(", ")}</div>`
                : `<div class="kh-exp kh-diag">not explained by any alternate</div>`}</div>`).join("") || `<div class="kh-ev">No supporting evidence in the records.</div>`}
          ${(h.requiresClarification || []).length ? `<div class="kh-sub">Requires clarification (neither side)</div>${h.requiresClarification.map(x => `<div class="kh-ev kh-clar">${esc(x.text)} ${evBtns(x.evidenceIds)}</div>`).join("")}` : ""}
        </div>
        <div class="kh-col kh-a">
          <div class="kh-tag olive">ALTERNATE HYPOTHESES · why ${esc(nm)} may NOT have been involved</div>
          ${alts.map(al => `<div class="kh-alt">
              <div class="kh-alt-h"><span class="kh-code">${esc(al.code)}</span>${esc(al.title)}<span class="kh-lab ${esc(al.label.toLowerCase().replace(/\s+/g, "-"))}">${esc(al.label)}</span></div>
              <div class="kh-str">${meter(al.strength, "olive")} <b>${al.strength.toFixed(2)}</b>${al.addressesSupportingEvidence ? "" : ` <span class="kh-muted">· does not counter the evidence relied on</span>`}</div>
              <p class="kh-stmt">${esc(al.statement)}</p>
              ${al.evidence.map(x => `<div class="kh-ev2">• ${esc(x.text)} ${evBtns(x.evidenceIds)}</div>`).join("")}
              <div class="kh-test"><b>Test that would settle it:</b> ${esc(al.test)}</div></div>`).join("")
            || `<div class="kh-alt">No alternate explanation is supported by the records currently held. That does not confirm involvement — missing records could hold one.</div>`}
          ${(h.alternatesConsideredNotSupported || []).length ? `<div class="kh-cons">Also considered, no supporting record: ${h.alternatesConsideredNotSupported.map(x => `${esc(x.code)} ${esc(x.title.toLowerCase())}`).join(" · ")}</div>` : ""}
        </div>
      </div>
      <div class="kh-verdict"><span class="kh-fav ${esc(cmp.favours || "")}">${esc(FAV[cmp.favours] || "")}</span>${esc(cmp.verdict || "")}
        ${(cmp.settleWith || []).length ? `<div class="kh-settle"><b>What would settle it</b>${cmp.settleWith.map(t => `<div>• ${esc(t)}</div>`).join("")}</div>` : ""}
        <div class="kh-muted" style="margin-top:6px">Evidential balance ${c.evidentialBalance > 0 ? "+" : ""}${c.evidentialBalance ?? "—"} (${esc(c.assessment || "")}, completeness ${Math.round((c.completeness || 0) * 100)}%${(c.sourcesMissing || []).length ? `, missing: ${esc(c.sourcesMissing.join(", ").toLowerCase())}` : ""}) — not a probability of guilt.
        ${(h.contextPriorRecords || []).length ? ` Prior records (context only, not scored): ${h.contextPriorRecords.map(x => `${esc(x.text)} ${evBtns(x.evidenceIds)}`).join(" · ")}` : ""}</div>
      </div></div>`;
  }
  const tabBtn = (k, label, active) => `<button type="button" onclick="window.setCaseTab('${k}')" style="background:none;border:none;font-family:var(--serif);font-size:16px;font-weight:700;cursor:pointer;color:${active === k ? "var(--terra)" : "var(--ink)"};border-bottom:${active === k ? "3px solid var(--terra)" : "3px solid transparent"};padding:8px 14px;transition:all .2s ease">${label}</button>`;
  const pill = (k, label, cur, color) => `<button type="button" onclick="window.setCaseFilter('${k}')" style="margin:0;padding:6px 12px;font-size:11px;cursor:pointer;border-radius:99px;font-weight:${cur === k ? "700" : "400"};background:${cur === k ? `var(--${color})` : "#fff"};color:${cur === k ? "#fff" : "var(--ink)"};border:1px solid ${cur === k ? `var(--${color})` : "rgba(198,154,85,0.4)"}">${label}</button>`;

  function publicNotice(S) {
    const safeUrl = /^https:\/\/indian-high-court-judgments\.s3\.amazonaws\.com\//.test(S.url || "") ? S.url : "";
    return `<b>REAL PUBLIC RECORD:</b> FIR particulars and facts are taken from the ${esc(S.court || "High Court")} order in <b>${esc(S.caseNumber || "")}</b>
      dated ${esc(S.decisionDate || "")} (${esc(String(S.petitionType || "").replace(/_/g, " ").toLowerCase())}; outcome: ${esc(S.disposal || "not stated")}).
      <b>All natural persons are pseudonymised</b> ([Accused A1], [Complainant C1] …) and phone numbers, vehicle numbers and addresses are masked;
      these people are never matched against other records. Facts are <b>allegations as recorded in the order</b>, not findings. No call, location,
      financial or social-media records exist for this case. Source: ${safeUrl ? `<a class="kr-a" href="${esc(safeUrl)}" target="_blank" rel="noopener noreferrer">original order (PDF)</a>` : "original order"}
      · SHA-256 <span class="mono">${esc((S.sha256 || "").slice(0, 16))}…</span> (anchored on the evidence ledger) · ${esc(S.license || "")}.`;
  }

  function intakeNotice(S, C) {
    const hits = S.intakeHits || [];
    return `<b>REGISTERED THROUGH KRONOS INTAKE</b> by ${esc(S.registeredBy || "investigator")} (${esc(S.registeredVia || "form")}${S.informationType ? ", " + esc(S.informationType.toLowerCase()) : ""}).
      The FIR was hashed (SHA-256) and anchored on the evidence ledger, and processed by the same engines as every other record. Roles are <b>as recorded</b>;
      people were linked to existing records only where the investigator chose to.${S.delayReason ? ` Reason recorded for the reporting delay: <i>${esc(S.delayReason)}</i>.` : ""}
      ${(S.unknownAccused || []).length ? ` Unknown accused: ${S.unknownAccused.map(x => esc(x || "not described")).join("; ")}.` : ""}
      ${hits.length ? `<div style="margin-top:6px"><b>Intake intelligence — identifiers in this FIR already appear elsewhere:</b> ${hits.map(h => `${esc(h.kind.toLowerCase())} <span class="mono">${esc(h.value)}</span> → ${h.cases.map(c => `<a class="kr-a" href="#case/${esc(c.caseId)}">${esc(c.caseId)}</a> (${c.records})`).join(", ")}`).join(" · ")}</div>` : ""}
      <div style="margin-top:8px"><button class="go" style="margin:0;padding:4px 12px;font-size:11px;background:transparent;color:var(--terra)" onclick="KR.withdraw('${esc(C.id)}')">Withdraw this case…</button></div>`;
  }

  function liveCaseV(el, caseId, original) {
    const C = CASES.find(c => c.id === caseId) || CASES[0];
    const D = st.caseData[C.id] || {};
    const S = D.summary || {}, api = C._api || {};
    const caseEvents = EVT.filter(e => e.c === C.id && !e.derived);
    let activeTab = window._kr_cur_tab || "summary";
    let curEvFilter = window._kr_cur_flt || "ALL";
    let shown = 200;
    window.setCaseTab = t => { activeTab = t; window._kr_cur_tab = t; render(); };
    window.setCaseFilter = f => { curEvFilter = f; window._kr_cur_flt = f; shown = 200; render(); };
    window._kr_more = () => { shown += 300; render(); };
    let searchQ = window._kr_evq || "", searchRes = null;
    window._kr_search = async q => {
      searchQ = window._kr_evq = (q || "").trim();
      if (!searchQ) { searchRes = null; render(); return; }
      try { searchRes = await j(`/search/evidence?q=${encodeURIComponent(searchQ)}&caseId=${C.id}&limit=60`, {}, 60000); }
      catch (e) { toast("Search unavailable"); searchRes = null; }
      render();
    };
    const topAccused = (C.prim || [])[0] || (C.ppl || [])[0];
    const fs = S.financialSummary || {}, cs = S.communicationSummary || {}, ls = S.locationSummary || {};
    let scal = "";
    function scalability() {
      if (scal) return scal;
      const tmp = document.createElement("div");
      const keep = window._kr_cur_tab;
      window._kr_cur_tab = "scalability";
      try { original(tmp, "__offline_static__"); scal = tmp.firstElementChild ? tmp.firstElementChild.lastElementChild.outerHTML : ""; } catch (e) { scal = ""; }
      window._kr_cur_tab = keep;
      window.setCaseTab = t => { activeTab = t; window._kr_cur_tab = t; render(); };
      window.setCaseFilter = f => { curEvFilter = f; window._kr_cur_flt = f; shown = 200; render(); };
      return scal;
    }
    function platformPanel() {
      const P = st.platform;
      if (!P) { loadPlatform().then(render); return `<div class="mono" style="font-size:11px;color:var(--terra);margin-bottom:12px">Loading live federated-learning and ledger status…</div>`; }
      const F = P.fed || {}, L = P.ledger || {}, R = F.results || {};
      return `<div style="background:#fff;border:1px solid rgba(198,154,85,0.3);border-radius:8px;padding:24px;margin-bottom:20px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
          <div><h3 style="font-family:var(--serif);font-size:22px;color:var(--terra);margin:0">Live: Federated Learning Across State Units & Evidence Ledger</h3>
          <div class="mono" style="font-size:11px;opacity:0.8;margin-top:2px">RUNNING ON THIS DEPLOYMENT · SIMULATION OF ${Object.keys(F.agencies || {}).length} AGENCY NODES · NO RAW RECORDS SHARED</div></div>
          <button class="go" style="margin:0;padding:6px 14px;font-size:11px" onclick="KR.runFed(this)">Run federated training round set</button>
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:16px">
          <div style="background:var(--parchment);padding:16px;border-radius:6px;border-left:3px solid var(--terra);font-size:12px;line-height:1.6">
            <div class="mono" style="font-size:10px;font-weight:700;color:var(--terra)">FEDERATED MODEL (FEDAVG, HMAC-SIGNED UPDATES)</div>
            ${Object.entries(F.agencies || {}).map(([a, v]) => `${esc(a)}: ${v.trainingSamples} local records (stay local) · local-only AUC ${(R.localOnly || {})[a] ? R.localOnly[a].rocAuc : "—"}`).join("<br>")}
            <br><b>Global model ${esc((R.federatedGlobal || {}).modelVersion || "")}:</b> AUC ${(R.federatedGlobal || {}).rocAuc ?? "—"}, AP ${(R.federatedGlobal || {}).averagePrecision ?? "—"}
            <br>Centralised baseline: AUC ${(R.centralised || {}).rocAuc ?? "—"}, AP ${(R.centralised || {}).averagePrecision ?? "—"} · ${F.rounds || "—"} rounds · rejected updates: ${(F.rejectedUpdates || []).length}
            <br><span style="opacity:.8">${esc((F.risks || [])[0] || "")}</span>
          </div>
          <div style="background:var(--parchment);padding:16px;border-radius:6px;border-left:3px solid var(--olive);font-size:12px;line-height:1.6">
            <div class="mono" style="font-size:10px;font-weight:700;color:var(--olive)">EVIDENCE LEDGER (SHA-256 CHAIN + MERKLE ANCHORS, ${esc(L.quorum || "")} ED25519 QUORUM)</div>
            Chain: <b style="color:${(L.chain || {}).valid ? "var(--olive)" : "var(--terra)"}">${(L.chain || {}).valid ? "VALID" : "INVALID"}</b> · ${(L.chain || {}).blocks || 0} blocks
            <br>${(L.anchors || []).map(a => `${esc(a.file)}: ${a.records} records · root ${esc(a.merkleRoot.slice(0, 12))}… · ${a.validSignatures}/4 signatures${a.quorumMet ? " ✓" : " ✗"}`).join("<br>")}
            <br><span style="opacity:.8">${esc(L.mode || "")}. Verifies integrity since anchoring — not authenticity or lawful collection.</span>
          </div>
        </div></div>`;
    }
    function diaryPanel() {
      const Dy = D.diary;
      const L = lang();
      return `<div style="display:grid;grid-template-columns:1fr;gap:18px">
        <div style="background:#fff;border:1px solid rgba(198,154,85,0.3);border-radius:8px;padding:24px">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
            <div><h3 style="font-family:var(--serif);font-size:22px;color:var(--terra);margin:0">Automated Case Diary & Draft Case Report</h3>
            <div class="mono" style="font-size:11px;opacity:0.8;margin-top:2px">DRAFTS FOR THE INVESTIGATING OFFICER — GENERATED ONLY FROM RECORDED EVENTS AND KRONOS ACTIVITY</div></div>
            <div style="display:flex;gap:8px;flex-wrap:wrap">
              <a class="go" target="_blank" style="margin:0;padding:6px 14px;font-size:11px;text-decoration:none" href="${API}/cases/${C.id}/report.html?lang=${L}">Draft case report ↗</a>
              <a class="go" target="_blank" style="margin:0;padding:6px 14px;font-size:11px;text-decoration:none" href="${API}/cases/${C.id}/report.html?lang=${L}&llm=true">Report with local-LLM narrative ↗</a>
              <a class="go" target="_blank" style="margin:0;padding:6px 14px;font-size:11px;text-decoration:none" href="${API}/cases/${C.id}/diary.html?lang=${L}">Printable case diary ↗</a>
            </div>
          </div>
          ${L !== "en" ? `<div class="mono" style="font-size:10px;margin-top:8px;color:var(--olive)">Documents open in the selected language (${esc(L)}): fixed headings plus machine-translated narrative with identifiers protected; verified English is included.</div>` : ""}
          <div style="margin-top:14px;background:var(--parchment);padding:14px;border-radius:6px;border-left:3px solid var(--gold)">
            <b style="font-size:13px;color:var(--gold)">Add diary entry (field step, statement, observation)</b>
            <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:8px">
              <input id="kr-d-ts" type="datetime-local" style="padding:6px;border:1px solid rgba(198,154,85,0.5);border-radius:6px;font-size:12px">
              <input id="kr-d-place" placeholder="Place" style="padding:6px 10px;border:1px solid rgba(198,154,85,0.5);border-radius:6px;font-size:12px">
              <input id="kr-d-ev" placeholder="Evidence IDs (comma separated)" style="padding:6px 10px;border:1px solid rgba(198,154,85,0.5);border-radius:6px;font-size:12px;min-width:220px">
            </div>
            <textarea id="kr-d-text" rows="2" placeholder="What was done / ascertained (recorded in the evidence ledger)" style="width:100%;margin-top:8px;padding:8px 10px;border:1px solid rgba(198,154,85,0.5);border-radius:6px;font-size:12px;box-sizing:border-box"></textarea>
            <button class="go" style="margin:6px 0 0;padding:5px 14px;font-size:11px" onclick="window._kr_addDiary()">Add entry</button>
          </div>
          <div style="margin-top:16px;font-size:13px;line-height:1.55">
            ${Dy ? Dy.entries.map(e => `<div style="margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid rgba(198,154,85,0.25)">
              <div style="font-family:var(--serif);font-size:16px;font-weight:700;color:var(--ink)">Day ${e.day} — ${esc(e.date)}</div>
              ${e.sections.map(sct => `<div style="margin-top:4px"><span class="mono" style="font-size:10px;font-weight:700;color:var(--terra);text-transform:uppercase">${esc(sct.section)}</span>
                ${sct.items.map(it => `<div style="font-size:12px;margin-left:8px">${esc(it.time)} ${esc(it.text)} ${it.refs.filter(x => /^EVD-/.test(x)).map(evBtn).join(" ")}${it.refs.filter(x => !/^EVD-/.test(x)).map(x => `<span class="mono" style="font-size:10px;opacity:.7"> ${esc(x)}</span>`).join("")}</div>`).join("")}</div>`).join("")}
            </div>`).join("") : "Diary unavailable."}
            ${Dy ? `<div class="mono" style="font-size:10px;opacity:.75">${esc(Dy.note)}</div>` : ""}
          </div>
        </div></div>`;
    }
    window._kr_addDiary = async () => {
      const text = (document.getElementById("kr-d-text").value || "").trim();
      if (!text) { toast("Entry text is required"); return; }
      const ts = document.getElementById("kr-d-ts").value;
      const evIds = (document.getElementById("kr-d-ev").value || "").split(/[ ,]+/).filter(Boolean);
      try {
        await j(`/cases/${C.id}/diary/entries`, { method: "POST", body: JSON.stringify({ text, entryTs: ts || null,
          place: document.getElementById("kr-d-place").value || null, evidenceIds: evIds }) });
        D.diary = await j(`/cases/${C.id}/diary`); toast("Diary entry recorded (ledger)"); render();
      } catch (e) { toast("Could not add entry"); }
    };
    function render() {
      const evs = caseEvents.filter(e => curEvFilter === "ALL" || e.ty === curEvFilter);
      el.innerHTML = `
    <div class="kr-case" style="max-width:1280px;margin:0 auto;padding:16px 20px 80px">
      <div class="kr-actions" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:10px">
        <button class="go" style="margin:0;padding:7px 16px;font-size:12px;cursor:pointer" onclick="location.hash='#dash'">← Back to Investigations</button>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          ${topAccused ? `<button class="go" style="margin:0;padding:7px 16px;font-size:12px;cursor:pointer" onclick="location.hash='#p/${topAccused}'">Inspect ${esc((PERS.find(p => p.id === topAccused) || {}).n || topAccused)} Dossier →</button>` : ""}
          <button class="go" style="margin:0;padding:7px 16px;font-size:12px;cursor:pointer" onclick="location.hash='#graph/${C.id}'">View 3D Network Topology →</button>
          <a class="go" style="margin:0;padding:7px 16px;font-size:12px;cursor:pointer;text-decoration:none" href="${API}/cases/${C.id}/summary.txt" download="${C.id}_summary.txt">Export Summary (TXT) ↓</a>
        </div>
      </div>
      <div style="background:var(--parchment);border:1px solid rgba(198,154,85,0.4);border-radius:10px;padding:24px 28px;box-shadow:0 4px 16px rgba(48,37,31,0.04)">
        <div style="display:flex;gap:10px;align-items:center;margin-bottom:8px;flex-wrap:wrap">
          <span style="background:var(--terra);color:#fff;font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;letter-spacing:0.6px">${esc(C.id)}</span>
          <span style="background:rgba(185,109,80,0.15);color:var(--terra);font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;letter-spacing:0.6px">${esc(C.pr.toUpperCase())} PRIORITY</span>
          <span style="background:rgba(123,128,98,0.15);color:var(--olive);font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;letter-spacing:0.6px">${esc(C.st.toUpperCase())}</span>
          ${api.origin === "PUBLIC_RECORD" ? `<span style="background:var(--olive);color:#fff;font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;letter-spacing:0.6px">REAL CASE · PUBLIC RECORD</span>` : ""}
          ${api.origin === "INTAKE" ? `<span style="background:var(--esp);color:#fff;font-size:10px;font-weight:700;padding:3px 8px;border-radius:4px;letter-spacing:0.6px">REGISTERED IN KRONOS</span>` : ""}
          <span class="mono" style="font-size:11px;opacity:0.8;margin-left:auto">${esc([api.firNumber, (api.firNumber || "").includes(api.policeStation || "\u0000") ? (api.district || "") : [api.policeStation, api.district].filter(Boolean).join(", "), api.incidentDate ? "Incident " + api.incidentDate : ""].filter(Boolean).join(" · "))}</span>
        </div>
        <h1 style="font-family:var(--serif);font-size:32px;color:var(--ink);margin:0 0 10px;line-height:1.2">${esc(C.t)}</h1>
        <p style="margin:0;color:var(--ink);opacity:0.85;font-size:14px;line-height:1.6;max-width:980px">${fmt(S.conciseSummary || C.desc)}</p>
        <div style="margin-top:18px;background:rgba(198,154,85,0.1);border-left:4px solid var(--gold);padding:10px 14px;border-radius:0 6px 6px 0;font-size:12px;color:var(--ink)">
          ${api.origin === "PUBLIC_RECORD" ? publicNotice(api.source || {}) : api.origin === "INTAKE" ? intakeNotice(api.source || {}, C) : `<b>DATA PROVENANCE NOTICE:</b> Records are <b>synthetic investigation data</b> ingested from FIR, CDR, location, financial and social-media sources. Every statement cites evidence IDs; each record's SHA-256 hash is held on the KRONOS evidence ledger. Roles are <b>as recorded</b>; analytical flags and hypotheses require investigator verification and are <b>not findings of guilt</b>. Priority basis: ${esc(api.priorityBasis || "")}.`}
        </div>
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:14px;margin-top:20px;border-top:1px solid rgba(198,154,85,0.25);padding-top:16px">
          <div><div style="font-size:22px;font-weight:700;color:var(--terra);font-family:var(--serif)">${C.ev} Records</div><div class="mono" style="font-size:11px;opacity:0.8">Across 5 data sources</div></div>
          <div><div style="font-size:22px;font-weight:700;color:var(--olive);font-family:var(--serif)">${(fs.flagged || []).length} Flags</div><div class="mono" style="font-size:11px;opacity:0.8">Financial anomalies (indicators)</div></div>
          <div><div style="font-size:22px;font-weight:700;color:var(--gold);font-family:var(--serif)">${inr(api.totalFinancialVolume)}</div><div class="mono" style="font-size:11px;opacity:0.8">Recorded transaction volume</div></div>
          <div><div style="font-size:22px;font-weight:700;color:var(--ink);font-family:var(--serif)">${(S.people || []).length} People</div><div class="mono" style="font-size:11px;opacity:0.8">Recorded in this case</div></div>
          <div><div style="font-size:22px;font-weight:700;color:var(--ink);font-family:var(--serif)">${api.reportingDelayHours ?? "—"} h</div><div class="mono" style="font-size:11px;opacity:0.8">Reporting delay</div></div>
        </div>
      </div>
      <div class="kr-tabs" style="display:flex;gap:16px;margin:24px 0 16px;border-bottom:1px solid rgba(198,154,85,0.3);padding-bottom:0;flex-wrap:wrap">
        ${tabBtn("summary", "1. Investigation Summary & Chronology", activeTab)}${tabBtn("nbe", "2. Next Best Evidence & Hypotheses (AI Engine)", activeTab)}
        ${tabBtn("evidence", `3. Evidence Records & Provenance Ledger (${caseEvents.length})`, activeTab)}${tabBtn("scalability", "4. Enterprise Scalability & Anti-Corruption Audit", activeTab)}${tabBtn("diary", t("diaryTab"), activeTab)}
      </div>
      ${activeTab === "summary" ? `
      <div style="display:grid;grid-template-columns:1fr;gap:18px">
        <div style="background:#fff;border:1px solid rgba(198,154,85,0.3);border-radius:8px;padding:24px">
          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 16px">
            <h3 style="font-family:var(--serif);font-size:22px;color:var(--terra);margin:0">Case Overview & Multi-Source Investigative Synthesis</h3>
            <span class="mono" style="font-size:10px;opacity:.75">Summary ${S.stale ? "STALE — regenerate" : "current"} · data hash ${esc((S.dataHash || "").slice(0, 12))}</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(320px, 1fr));gap:20px;line-height:1.6;font-size:13px;color:var(--ink)">
            ${card("1. Narrative", "terra", fmt(S.llmNarrative || S.detailedNarrative || "") + `<div style="margin-top:8px"><button class="go" style="margin:0;padding:4px 10px;font-size:11px" onclick="KR.llmSummary('${C.id}', this)">${S.llmNarrative ? "Regenerate" : "Write"} narrative with local LLM</button></div>`)}
            ${card("2. People (recorded roles)", "terra", (S.people || []).map(p => `<a class="kr-a" href="#p/${p.personId}">${esc(p.name)} (${p.personId})</a> — ${esc(p.recordedRole.replace(/_/g, " ").toLowerCase())} <span class="mono" style="font-size:10px;opacity:.7">${esc(p.roleSource)}</span> ${evBtns(p.evidenceIds.slice(0, 1))}`).join("<br>"))}
            ${card("3. Financial activity", "gold", `${fs.transactions || 0} transactions, ${inr(fs.totalVolume)} total; ${(fs.flagged || []).length} flagged as indicators.<br>` +
              (fs.flagged || []).slice(0, 6).map(f => `${evBtn(f.evidenceId)} ${inr(f.amount)} · ${esc(f.methods.join("+"))}<br><span style="font-size:12px;opacity:.85">${esc(f.reasons[0])}${f.alternativeExplanation ? ` <i>(alt.: ${esc(f.alternativeExplanation)})</i>` : ""}</span>`).join("<br>"))}
            ${card("4. Communication", "gold", (cs.pairs || []).slice(0, 5).map(p => `${esc(p.names[0])} ↔ ${esc(p.names[1])}: <b>${p.total}</b> contacts${p.otherCases && p.otherCases.length ? ` · also in ${p.otherCases.slice(0, 3).join(", ")}` : ""}`).join("<br>") +
              (cs.aroundIncident ? `<br>Around incident: ${cs.aroundIncident.count} contacts (baseline ≈${cs.aroundIncident.expectedFromBaseline}), ${cs.aroundIncident.betweenNamedPersons} between named persons.` : "") +
              ((cs.importantMessages || []).length ? `<br><b>Messages referencing case identifiers:</b><br>` + cs.importantMessages.slice(0, 3).map(m => `${evBtn(m.evidenceId)} "${esc(m.text.slice(0, 90))}"`).join("<br>") : ""))}
            ${card("5. Location", "olive", (ls.nearIncident || []).slice(0, 5).map(x => `${x.personId}: ${x.distanceKm} km from incident, ${x.minutesFromIncident} min ${evBtn(x.evidenceId)}`).join("<br>") +
              ((ls.namedPersonsElsewhere || []).length ? `<br><b style="color:var(--terra)">Possibly exculpatory:</b><br>` + ls.namedPersonsElsewhere.slice(0, 3).map(x => `${x.personId} at ${esc(x.location)} (${x.distanceKm} km away) ${evBtn(x.evidenceId)}`).join("<br>") : "") || "No location records near the incident.")}
            ${card("6. Observations requiring verification", "olive", (S.suspiciousObservations || []).slice(0, 5).map(o => `${fmt(o.text)} ${evBtns(o.evidenceIds.slice(0, 2))}`).join("<br><br>") +
              (S.travelInconsistencies || []).map(t => `<br>Location inconsistency ${t.personId}: ${esc(t.verdict)} (${t.distanceKm} km / ${t.elapsedMinutes} min) ${evBtn(t.first)} ${evBtn(t.second)}`).join("") || "None.")}
            ${card("7. Missing information & uncertainties", "ink", (S.missingInformation || []).map(m => `• ${esc(m.personId || "")} ${esc(m.gap)}`).join("<br>") + "<br>" + (S.uncertainties || []).slice(0, 6).map(u => `• ${esc(u)}`).join("<br>"))}
            ${card("8. Chronology", "ink", (S.chronology || []).slice(0, 14).map(e => `<span class="mono" style="font-size:11px">${esc(e.timestamp)}</span> ${esc(e.event)} ${evBtns(e.evidenceIds.slice(0, 1))}`).join("<br>"))}
          </div>
        </div>
      </div>` : ""}
      ${activeTab === "nbe" ? `
      <div style="display:grid;grid-template-columns:1fr;gap:18px">
        <div style="background:#fff;border:1px solid rgba(198,154,85,0.3);border-radius:8px;padding:24px">
          <h3 style="font-family:var(--serif);font-size:22px;color:var(--terra);margin:0">KRONOS Detective • Analytical Hypotheses & Next Best Evidence</h3>
          <div class="mono" style="font-size:11px;opacity:0.8;margin-top:2px">ANALYTICAL HYPOTHESES — TESTED FROM BOTH SIDES — REQUIRE INVESTIGATOR VERIFICATION</div>
          <div style="display:grid;grid-template-columns:1fr;gap:16px;margin-top:16px">
            <div style="background:var(--parchment);border:1px solid rgba(198,154,85,0.4);border-radius:8px;padding:18px">
              <span style="background:rgba(198,154,85,0.25);color:var(--gold);font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px">INVESTIGATIVE PRIORITY (NOT A GUILT SCORE)</span>
              <div style="font-size:13px;line-height:1.6;margin-top:8px">${((D.prio || {}).ranking || []).slice(0, 6).map(r => `<a class="kr-a" href="#p/${r.personId}">${esc(r.name)} (${r.personId})</a> — recorded ${esc(r.recordedRole.replace(/_/g, " ").toLowerCase())} · <b>${esc(r.label)}</b> <span class="mono" style="font-size:10px">score ${r.priorityScore}</span><br><span style="font-size:11px;opacity:.8">${r.factors.filter(f => f.contribution).sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution)).slice(0, 3).map(f => `${esc(f.factor)} ${f.contribution > 0 ? "+" : ""}${f.contribution}: ${esc(f.explanation)}`).join(" · ")}</span>`).join("<br>")}</div>
            </div>
            ${((D.hyp || {}).hypotheses || []).map((h, i) => hypCard(h, i)).join("")}
            <div style="background:var(--parchment);border:1px solid rgba(123,128,98,0.3);border-radius:8px;padding:18px">
              <span style="background:rgba(123,128,98,0.2);color:var(--olive);font-size:10px;font-weight:700;padding:2px 8px;border-radius:4px">NEXT BEST EVIDENCE</span>
              <div style="font-size:13px;line-height:1.5;margin-top:8px">${(D.nbe || []).map(r => `<div style="margin:8px 0;padding-bottom:8px;border-bottom:1px solid rgba(198,154,85,0.25)">
                <b>${esc(r.evidenceType)}</b> <span class="mono" style="font-size:10px;color:var(--terra)">${esc(r.priority)} · value ${r.valueScore ?? "—"}</span>
                <select class="mono" style="font-size:10px;margin-left:6px" onchange="KR.setNbe('${C.id}','${r.id}',this.value)">${["AVAILABLE", "AVAILABLE_NOT_RETRIEVED", "TO_BE_OBTAINED", "CANNOT_VERIFY_CURRENTLY", "REQUESTED", "RECEIVED", "DISMISSED"].map(s => `<option ${s === r.status ? "selected" : ""}>${s}</option>`).join("")}</select><br>
                <span style="font-size:12px">${esc(r.reason)}. <i>Gap:</i> ${esc(r.evidenceGap)}. <i>Value:</i> ${esc(r.expectedInvestigativeValue)}.<br><b>Action:</b> ${esc(r.verificationAction)} ${evBtns(r.basisEvidenceIds)}
                ${r.scoreBreakdown ? `<br><span class="mono" style="font-size:10px;opacity:.8">score = 0.30×uncertainty ${r.scoreBreakdown.uncertaintyReduction} + 0.30×finding ${r.scoreBreakdown.findingStrength} + 0.20×subject priority ${r.scoreBreakdown.subjectPriority} + 0.20×obtainability ${r.scoreBreakdown.obtainability}${r.scoreBreakdown.exculpatoryBonus ? ` + exculpatory ${r.scoreBreakdown.exculpatoryBonus}` : ""}${r.scoreBreakdown.notes.length ? " · " + esc(r.scoreBreakdown.notes.join("; ")) : ""}</span>` : ""}</span></div>`).join("") || "No recommendations."}</div>
            </div>
          </div>
        </div>
      </div>` : ""}
      ${activeTab === "evidence" ? `
      <div style="background:#fff;border:1px solid rgba(198,154,85,0.3);border-radius:8px;padding:24px">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:12px">
          <div><h3 style="font-family:var(--serif);font-size:22px;color:var(--terra);margin:0">Case Evidence & Provenance Ledger</h3>
          <div class="mono" style="font-size:11px;opacity:0.8;margin-top:2px">Click any record to inspect the original source record and verify its SHA-256 integrity</div></div>
          <div style="flex-basis:100%;display:flex;gap:8px;align-items:center;margin:4px 0 2px">
            <input id="kr-evq" value="${esc(searchQ)}" placeholder="${esc(t("search"))}" style="flex:1;padding:8px 12px;border:1px solid rgba(198,154,85,0.5);border-radius:6px;font-size:12px;background:#fff;color:var(--ink)" onkeydown="if(event.key==='Enter')window._kr_search(this.value)">
            <button class="go" style="margin:0;padding:6px 14px;font-size:11px" onclick="window._kr_search(document.getElementById('kr-evq').value)">Search</button>
            ${searchRes ? `<button class="go" style="margin:0;padding:6px 14px;font-size:11px" onclick="window._kr_search('')">Clear</button>` : ""}
          </div>
          ${searchRes ? `<div class="mono" style="flex-basis:100%;font-size:11px;color:var(--olive)">Interpreted as: ${esc((searchRes.interpretation.explain || []).join(" · ") || "text similarity")}${(searchRes.interpretation.keywords || []).length ? " · keywords: " + esc(searchRes.interpretation.keywords.join(", ")) : ""} — ${searchRes.total} matching records (current case ranked first)</div>` : ""}
          <div style="display:flex;gap:8px;flex-wrap:wrap">${pill("ALL", "All", curEvFilter, "terra")}${pill("FIR", "FIR", curEvFilter, "terra")}${pill("Comm", "Calls & messages", curEvFilter, "terra")}${pill("Loc", "Location", curEvFilter, "olive")}${pill("Fin", "Financial", curEvFilter, "gold")}
          <button type="button" class="go" style="margin:0;padding:6px 12px;font-size:11px" onclick="KR.verifyChain(this)">Verify ledger chain</button></div>
        </div>
        <div style="display:grid;grid-template-columns:1fr;gap:10px">
          ${searchRes ? searchRes.results.map(r => `
            <div class="ev-row" style="background:var(--parchment);border:1px solid rgba(198,154,85,0.3);border-radius:6px;padding:12px 16px;cursor:pointer" onclick="openEv('${esc(r.evidenceId)}')">
              <div style="display:flex;gap:8px;align-items:center;margin-bottom:4px;flex-wrap:wrap">
                <span class="mono" style="font-weight:700;font-size:11px;color:var(--terra)">${esc(r.evidenceId)}</span>
                <span style="font-size:10px;padding:2px 6px;border-radius:3px;background:rgba(123,128,98,0.15);color:var(--olive);font-weight:700">${esc(r.modality)} · ${esc(r.caseId)}</span>
                <span class="mono" style="font-size:10px;opacity:0.7">${esc(r.timestamp)}</span></div>
              <div style="font-size:12px;color:var(--ink)">${esc(r.description || "")}</div>
              <div class="mono" style="font-size:10px;opacity:.75;margin-top:3px">why: ${esc(r.whyMatched.join(" · "))}</div>
            </div>`).join("") || "<div>No matching records.</div>" : ""}
          ${searchRes ? "" : evs.slice(0, shown).map(e => `
            <div class="ev-row" style="background:var(--parchment);border:1px solid rgba(198,154,85,0.3);border-radius:6px;padding:12px 16px;display:flex;justify-content:space-between;align-items:center;cursor:pointer;transition:transform .15s ease, box-shadow .15s ease" onclick="openEv('${e.id}')">
              <div style="max-width:80%">
                <div style="display:flex;gap:8px;align-items:center;margin-bottom:4px;flex-wrap:wrap">
                  <span class="mono" style="font-weight:700;font-size:11px;color:var(--terra)">${e.id}</span>
                  <span style="font-size:10px;padding:2px 6px;border-radius:3px;background:rgba(123,128,98,0.15);color:var(--olive);font-weight:700">${esc(e.mod || e.ty)} · ${esc(e.rel.toUpperCase())} RELIABILITY</span>
                  <span class="mono" style="font-size:10px;opacity:0.7">${fd(e.d)} · ${e.tm}</span>
                </div>
                <div style="font-size:12px;color:var(--ink);opacity:0.85;margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(e.s)}</div>
              </div>
              <button class="go" type="button" style="margin:0;padding:6px 14px;font-size:11px;cursor:pointer" onclick="openEv('${e.id}'); event.stopPropagation();">Inspect ↗</button>
            </div>`).join("")}
          ${!searchRes && evs.length > shown ? `<button class="go" style="margin:6px auto;padding:6px 14px;font-size:11px" onclick="window._kr_more()">Show more (${evs.length - shown} remaining)</button>` : ""}
        </div>
      </div>` : ""}
      ${activeTab === "scalability" ? platformPanel() + scalability() : ""}
      ${activeTab === "diary" ? diaryPanel() : ""}
    </div>`;
    }
    render();
    if (window._kr_pending_search && activeTab === "evidence") {
      const pq = window._kr_pending_search; window._kr_pending_search = null;
      window._kr_search(pq);
    }
  }

  async function loadPlatform() {
    const [fed, ledger] = await Promise.all([j("/federated/report").catch(() => ({})), j("/ledger/status", {}, 60000).catch(() => ({}))]);
    st.platform = { fed, ledger };
  }

  /* ------------------------------------------------------------------ install */
  function install() {
    const _profV = window.profV, _caseV = window.caseV, _graphV = window.graphV;
    window.profV = function (el, id) {
      const P = PERS.find(p => p.id === id) || PERS[0];
      if (!st.persons.has(P.id)) { el.innerHTML = loading(`Loading recorded activity for ${P.id} from KRONOS engines…`); loadPerson(P.id).then(route); return; }
      _profV(el, P.id);
      afterProfile(el, P.id);
    };
    window.caseV = function (el, id) {
      const C = CASES.find(c => c.id === id) || CASES[0];
      if (!st.cases.has(C.id)) { el.innerHTML = loading(`Loading ${C.id}: evidence, summary, hypotheses and next-best-evidence…`); loadCase(C.id).then(route); return; }
      liveCaseV(el, C.id, _caseV);
    };
    window.graphV = function (el, focus) {
      const f = focus || (PERS[0] && PERS[0].id);
      if (st.graphFocus !== f) { el.innerHTML = loading(`Building relationship subgraph around ${f}…`); loadGraph(f).then(route).catch(() => { st.graphFocus = f; route(); }); return; }
      _graphV(el, f);
    };
    // navigation shortcuts that pointed at the offline demo entities
    const topP = PERS[0] && PERS[0].id, topC = (CASES.slice().sort((a, b) => (b._api.flaggedFindings || 0) - (a._api.flaggedFindings || 0))[0] || {}).id;
    document.querySelectorAll('a[href*="P-JS01"]').forEach(a => a.setAttribute("href", `#p/${topP}`));
    document.querySelectorAll('a[href*="KRONOS-2024-001"]').forEach(a => a.setAttribute("href", `#case/${topC}`));
    const demo = document.querySelector("nav .demo");
    if (demo) demo.textContent = `LIVE BACKEND • ${CASES.length} CASES`;
  }

  /* ------------------------------------------------------------------ Copilot command router (online AND offline) */
  // Recognises navigation commands in English, Hindi, Gujarati and Punjabi and executes them reliably, reporting
  // each resolution step. Analytical questions are NOT treated as commands.
  const VERB = /\b(open|show|go to|goto|go|take me to|navigate( to)?|view|launch|display|load|switch to|bring up|jump to|explore|visit)\b|खोलो|खोलें|खोलिए|दिखाओ|दिखाएं|दिखाइए|जाओ|ले चलो|ખોલો|બતાવો|જાઓ|ਖੋਲ੍ਹੋ|ਦਿਖਾਓ|ਜਾਓ/i;
  const QUESTION = /^(what|which|who|whom|when|where|why|how|is|are|was|were|does|did|do|can|could|should|summari[sz]e|explain|compare|list|find|tell|give|क्या|कौन|कब|कहाँ|क्यों|कैसे|શું|કોણ|ક્યારે|ક્યાં|કેમ|ਕੀ|ਕੌਣ|ਕਦੋਂ|ਕਿੱਥੇ|ਕਿਉਂ)\b/i;
  const DEST = [
    ["back", /^(go )?back$|^पीछे|^પાછા|^ਪਿੱਛੇ/i, null, { en: "Back", hi: "पीछे", gu: "પાછા", pa: "ਪਿੱਛੇ" }],
    ["home", /\b(home( ?page)?|landing( page)?|start page|main page)\b|होम|मुख्य पृष्ठ|હોમ|ਹੋਮ/i, null, { en: "Home", hi: "होम", gu: "હોમ", pa: "ਹੋਮ" }],
    ["graph", /\b(graph|network|topology|relationship (map|graph)|3d)\b|ग्राफ|नेटवर्क|ગ્રાફ|નેટવર્ક|ਗ੍ਰਾਫ|ਨੈੱਟਵਰਕ/i, null, { en: "3D network graph", hi: "3D नेटवर्क ग्राफ", gu: "3D નેટવર્ક ગ્રાફ", pa: "3D ਨੈੱਟਵਰਕ ਗ੍ਰਾਫ" }],
    ["timeline", /\b(timeline|temporal|chronolog\w*|activity log)\b|टाइमलाइन|समयरेखा|ટાઇમલાઇન|ਟਾਈਮਲਾਈਨ/i, null, { en: "Timeline", hi: "टाइमलाइन", gu: "ટાઇમલાઇન", pa: "ਟਾਈਮਲਾਈਨ" }],
    ["dossier", /\b(dossier|profile|intelligence|suspect page)\b|डोजियर|डोज़ियर|प्रोफाइल|પ્રોફાઇલ|ડોઝિયર|ਪ੍ਰੋਫਾਈਲ/i, null, { en: "Dossier", hi: "डोजियर", gu: "ડોઝિયર", pa: "ਡੋਜ਼ੀਅਰ" }],
    ["diary", /\b(case diary|diary|draft report|case report|report)\b|डायरी|रिपोर्ट|ડાયરી|અહેવાલ|ਡਾਇਰੀ|ਰਿਪੋਰਟ/i, "diary", { en: "Case diary & draft report", hi: "केस डायरी और रिपोर्ट", gu: "કેસ ડાયરી અને અહેવાલ", pa: "ਕੇਸ ਡਾਇਰੀ ਅਤੇ ਰਿਪੋਰਟ" }],
    ["nbe", /\b(next best evidence|hypothes\w*|leads?|recommendations?)\b|परिकल्पना|सुझाव|પૂર્વધારણા|ਧਾਰਨਾ/i, "nbe", { en: "Next best evidence & hypotheses", hi: "अगले साक्ष्य और परिकल्पनाएँ", gu: "આગામી પુરાવા અને પૂર્વધારણાઓ", pa: "ਅਗਲੇ ਸਬੂਤ ਅਤੇ ਧਾਰਨਾਵਾਂ" }],
    ["scal", /\b(scalability|anti-?corruption|federated|blockchain|ledger status)\b|स्केलेबिलिटी|ભ્રષ્ટાચાર|ਫੈਡਰੇਟਿਡ/i, "scalability", { en: "Scalability, federated learning & ledger", hi: "स्केलेबिलिटी और लेजर", gu: "સ્કેલેબિલિટી અને લેજર", pa: "ਸਕੇਲੇਬਿਲਟੀ ਅਤੇ ਲੈਜਰ" }],
    ["evidence", /\b(evidence|records|exhibits|evidence log)\b|साक्ष्य|सबूत|પુરાવા|ਸਬੂਤ/i, "evidence", { en: "Evidence records", hi: "साक्ष्य रिकॉर्ड", gu: "પુરાવા રેકોર્ડ", pa: "ਸਬੂਤ ਰਿਕਾਰਡ" }],
    ["summary", /\b(summary|overview|case workspace|workspace)\b|सारांश|સારાંશ|ਸਾਰ/i, "summary", { en: "Case summary", hi: "केस सारांश", gu: "કેસ સારાંશ", pa: "ਕੇਸ ਸਾਰ" }],
    ["dash", /\b(investigations?|dashboard|case list|cases|all cases|persons of interest|people)\b|जांच|जाँच|डैशबोर्ड|सभी मामले|તપાસ|ડેશબોર્ડ|ਜਾਂਚ|ਡੈਸ਼ਬੋਰਡ/i, null, { en: "Investigations dashboard", hi: "जांच डैशबोर्ड", gu: "તપાસ ડેશબોર્ડ", pa: "ਜਾਂਚ ਡੈਸ਼ਬੋਰਡ" }],
    ["alerts", /\b(alerts?|notifications?)\b|अलर्ट|सूचनाएं|ચેતવણી|ਅਲਰਟ/i, null, { en: "Alerts", hi: "अलर्ट", gu: "ચેતવણીઓ", pa: "ਅਲਰਟ" }],
    ["settings", /\b(settings?|language)\b|सेटिंग|भाषा|સેટિંગ|ભાષા|ਸੈਟਿੰਗ|ਭਾਸ਼ਾ/i, null, { en: "Settings", hi: "सेटिंग", gu: "સેટિંગ", pa: "ਸੈਟਿੰਗ" }],
  ];
  const DONE = { en: "Opened", hi: "खोला गया", gu: "ખોલ્યું", pa: "ਖੋਲ੍ਹਿਆ" };
  const reEsc = x => x.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  function currentEntity() {
    const m = location.hash.match(/^#(p|case|graph)\/(.+)$/);
    return { person: m && m[1] === "p" ? decodeURIComponent(m[2]) : null, kase: m && m[1] === "case" ? decodeURIComponent(m[2]) : null };
  }
  function findCase(q) {
    const u = q.toUpperCase();
    const n = (u.match(/\bCASE\s*(?:NO\.?|NUMBER|#)?\s*(\d{1,3})\b/) || [])[1];      // "case 905", "case no. 12"
    return CASES.find(c => u.includes(c.id.toUpperCase())) || (n && CASES.find(c => c.id === "CASE" + n.padStart(3, "0"))) || null;
  }
  function findPerson(q) {
    const u = q.toUpperCase(), l = q.toLowerCase();
    const byId = PERS.find(p => new RegExp(`(^|[^A-Z0-9-])${reEsc(p.id.toUpperCase())}($|[^A-Z0-9-])`).test(u));
    if (byId) return { person: byId };
    // pseudonym labels ("Accused A1 · CASE905") must not match on case IDs or role words
    const toks = p => (p.n || "").toLowerCase().split(/\s+/).filter(t => t.length >= 3 && !/[()·]/.test(t) &&
      !/^case\d+$/.test(t) && !/^(accused|complainant|victim|witness|person|name|official|counsel)$/.test(t));
    const full = PERS.filter(p => toks(p).length && toks(p).every(t => new RegExp(`\\b${reEsc(t)}\\b`).test(l)));
    if (full.length === 1) return { person: full[0] };
    const part = full.length ? full : PERS.filter(p => toks(p).some(t => t.length >= 4 && new RegExp(`\\b${reEsc(t)}\\b`).test(l)));
    if (part.length === 1) return { person: part[0] };
    return part.length > 1 ? { ambiguous: part.slice(0, 5) } : {};
  }
  function parseCommand(text) {
    const q = (text || "").trim();
    if (!q) return null;
    const verb = VERB.test(q);
    const question = QUESTION.test(q) && !/^(open|go to|navigate)/i.test(q);
    const dest = DEST.find(d => d[1].test(q)) || null;
    const kase = findCase(q), per = findPerson(q);
    const words = q.split(/\s+/).length;
    const isCmd = !question && ((verb && (dest || kase || per.person || per.ambiguous)) ||
                                (!verb && words <= 3 && (dest || kase || per.person)));
    if (!isCmd) return null;
    let leftover = null;
    if (dest && dest[0] === "evidence") {
      leftover = q.replace(VERB, " ").replace(dest[1], " ").replace(/\b(of|for|about|on|with|the|in this case|this case)\b/gi, " ")
        .replace(kase ? new RegExp(reEsc(kase.id), "i") : /$^/, " ").replace(/\s+/g, " ").trim();
      if (leftover.split(" ").length < 2) leftover = null;
    }
    return { q, dest, kase, per, leftover };
  }
  function go(target, tab) {
    if (tab) window._kr_cur_tab = tab;
    const want = "#" + target.replace(/^#/, "");
    if (location.hash === want) { if (typeof route === "function") route(); } else location.hash = want;
    const panel = document.getElementById("copilot-panel");
    if (panel) panel.classList.remove("open");           // reveal the page the step opened
  }
  function runCommand(c, lng) {
    lng = lng || lang();
    const cur = currentEntity(), steps = [];
    const lab = d => (d[3][lng] || d[3].en);
    steps.push(`Command recognised: "${c.q}"` + (c.dest ? ` → ${c.dest[3].en}` : ""));
    if (c.per.ambiguous) {
      return { answerText: `Several people match — please be specific: ${c.per.ambiguous.map(p => `<b>${esc(p.n)}</b> (${esc(p.id)})`).join(", ")}.`,
               reasoning: [...steps, "Person reference is ambiguous — nothing opened"], action: null, executed: false };
    }
    let target, tab = null, label, extra = null;
    const key = c.dest ? c.dest[0] : (c.kase ? "case" : "person");
    const pickPerson = () => {
      if (c.per.person) { steps.push(`Person resolved from your text: ${c.per.person.n} (${c.per.person.id})`); return c.per.person.id; }
      if (cur.person) { steps.push(`Person taken from the open dossier: ${cur.person}`); return cur.person; }
      const k = cur.kase && CASES.find(x => x.id === cur.kase);
      const fromCase = k && ((k.prim || [])[0] || (k.ppl || [])[0]);
      if (fromCase) { steps.push(`Person taken from the open case ${k.id}: ${fromCase}`); return fromCase; }
      steps.push(`No person specified — opening the first listed person (${PERS[0].id})`); return PERS[0].id;
    };
    const pickCase = () => {
      if (c.kase) { steps.push(`Case resolved from your text: ${c.kase.id}`); return c.kase.id; }
      if (cur.kase) { steps.push(`Case taken from the open workspace: ${cur.kase}`); return cur.kase; }
      const pr = cur.person && CASES.find(x => (x.ppl || []).includes(cur.person));
      if (pr) { steps.push(`Case taken from the open dossier's first case: ${pr.id}`); return pr.id; }
      steps.push(`No case specified — opening the first listed case (${CASES[0].id})`); return CASES[0].id;
    };
    switch (key) {
      case "back": history.back(); steps.push("Went back to the previous page"); label = lab(c.dest);
        document.getElementById("copilot-panel")?.classList.remove("open"); break;
      case "home": target = "home"; label = lab(c.dest); break;
      case "dash": target = "dash"; label = lab(c.dest); break;
      case "graph": {
        const f = c.per.person ? c.per.person.id : c.kase ? c.kase.id : (cur.person || cur.kase);
        if (f) steps.push(`Graph focus: ${f}`);
        target = f ? `graph/${f}` : "graph"; label = lab(c.dest); break;
      }
      case "timeline": case "dossier": case "person": {
        const pid = pickPerson(); target = `p/${pid}`;
        const P = PERS.find(x => x.id === pid);
        label = `${key === "timeline" ? lab(DEST.find(d => d[0] === "timeline")) : lab(DEST.find(d => d[0] === "dossier"))} — ${P ? P.n : pid}`;
        if (key === "timeline") extra = () => setTimeout(() => { const t = document.querySelector(".tl"); if (t) t.scrollIntoView({ behavior: "smooth", block: "start" }); }, 600);
        break;
      }
      case "alerts": if (window.openNotifications) window.openNotifications(); steps.push("Alerts drawer opened"); label = lab(c.dest);
        document.getElementById("copilot-panel")?.classList.remove("open"); break;
      case "settings": if (window.openSettings) window.openSettings(); steps.push("Settings drawer opened"); label = lab(c.dest);
        document.getElementById("copilot-panel")?.classList.remove("open"); break;
      default: {   // case workspace (optionally a specific tab)
        const cid = pickCase(); target = `case/${cid}`;
        tab = c.dest ? c.dest[2] : "summary";
        if (tab === "diary" && !st.live) { tab = "summary"; steps.push("Case diary needs the live backend — opening the case summary instead"); }
        if (tab) steps.push(`Workspace tab: ${tab}`);
        if (c.leftover && st.live) { window._kr_pending_search = c.leftover; steps.push(`Evidence search queued: "${c.leftover}"`); }
        label = `${c.dest ? lab(c.dest) : "Case workspace"} — ${cid}`;
      }
    }
    if (target) { go(target, tab); steps.push(`Navigated to #${target}${tab ? ` (tab: ${tab})` : ""}`); if (extra) extra(); }
    if (typeof toast === "function") toast(`${DONE[lng] || DONE.en}: ${label}`);
    return { answerText: `<b>${esc(DONE[lng] || DONE.en)}:</b> ${esc(label)}.`, reasoning: steps,
             action: target ? { type: "NAV", target, tab, label } : null, executed: true };
  }
  window.KRcmd = { parse: parseCommand, run: runCommand, go };

  const CHIPS = {
    en: ["Register a new case", "Open investigations dashboard", "Open timeline", "Show 3D network graph", "Which people in this case warrant further investigation?",
         "Show evidence of cash deposits above 40,000", "Open case diary & draft report"],
    hi: ["नया केस दर्ज करें", "जांच डैशबोर्ड खोलो", "टाइमलाइन खोलो", "3D नेटवर्क ग्राफ दिखाओ", "इस मामले में किन लोगों की आगे जांच ज़रूरी है?",
         "40,000 से अधिक नकद जमा के साक्ष्य दिखाओ", "केस डायरी और रिपोर्ट खोलो"],
    gu: ["નવો કેસ નોંધો", "તપાસ ડેશબોર્ડ ખોલો", "ટાઇમલાઇન ખોલો", "3D નેટવર્ક ગ્રાફ બતાવો", "આ કેસમાં કયા લોકોની વધુ તપાસ જરૂરી છે?",
         "40,000થી વધુ રોકડ જમાના પુરાવા બતાવો", "કેસ ડાયરી અને અહેવાલ ખોલો"],
    pa: ["ਨਵਾਂ ਕੇਸ ਦਰਜ ਕਰੋ", "ਜਾਂਚ ਡੈਸ਼ਬੋਰਡ ਖੋਲ੍ਹੋ", "ਟਾਈਮਲਾਈਨ ਖੋਲ੍ਹੋ", "3D ਨੈੱਟਵਰਕ ਗ੍ਰਾਫ ਦਿਖਾਓ", "ਇਸ ਕੇਸ ਵਿੱਚ ਕਿਹੜੇ ਲੋਕਾਂ ਦੀ ਹੋਰ ਜਾਂਚ ਲੋੜੀਂਦੀ ਹੈ?",
         "40,000 ਤੋਂ ਵੱਧ ਨਕਦ ਜਮ੍ਹਾਂ ਦੇ ਸਬੂਤ ਦਿਖਾਓ", "ਕੇਸ ਡਾਇਰੀ ਅਤੇ ਰਿਪੋਰਟ ਖੋਲ੍ਹੋ"],
  };
  const chips = l => CHIPS[l] || CHIPS.en;
  const welcome = () => `<b>Welcome to KRONOS Copilot — connected to the live backend (${CASES.length} cases, ${PERS.length} persons).</b><br>` +
    "Ask questions about the evidence in English, हिंदी, ગુજરાતી or ਪੰਜਾਬੀ, or give commands such as <i>open investigations</i>, " +
    "<i>open timeline</i>, <i>open CASE005</i>, <i>show evidence of cash deposits above 40,000</i> or <i>open case diary</i>.";

  const style = document.createElement("style");
  style.textContent = "a.kr-a{color:var(--terra);text-decoration:none;font-weight:600}a.kr-a:hover{text-decoration:underline}body.kr-live .dos{overflow-y:auto}";
  document.head.appendChild(style);

  window.KR = {
    get live() { return st.live; }, st, ask, fetchEvidence, recordBadge, verify, review, proof, custody, reviewHistory, lang, toHistory,
    runFed: async btn => { btn.textContent = "Training across agency nodes…"; try { await j("/federated/run", { method: "POST", body: JSON.stringify({ rounds: 25 }) }, 120000); st.platform = null; toast("Federated rounds complete"); route(); } catch (e) { btn.textContent = "Federated run failed"; } },
    alerts: () => j("/alerts"),
    setNbe: (cid, rid, status) => j(`/cases/${cid}/next-evidence/${rid}`, { method: "PATCH", body: JSON.stringify({ status }) }).then(() => toast("Status saved")).catch(() => toast("Could not save status")),
    verifyChain: async btn => { btn.textContent = "verifying…"; try { const r = await j("/ledger/verify", {}, 60000); btn.textContent = r.valid ? `Ledger valid · ${r.blocks} blocks` : `INVALID blocks: ${r.invalidBlocks.join(",")}`; } catch (e) { btn.textContent = "unavailable"; } },
    llmSummary: async (cid, btn) => { btn.textContent = "Writing with local Llama 3.1 (≈30–60 s)…"; btn.disabled = true;
      try { const s = await j(`/cases/${cid}/summary?llm=true&regenerate=true`, {}, 240000); st.caseData[cid].summary = s; route(); } catch (e) { btn.textContent = "LLM unavailable"; } },
    chips, welcome,
    // after a case is registered or withdrawn: reload the case and person lists and drop cached views
    refresh: async () => {
      const [cs, ps] = await Promise.all([j("/cases", {}, 30000), j("/persons", {}, 30000)]);
      CASES.splice(0, CASES.length, ...cs.map(mapCase));
      PERS.splice(0, PERS.length, ...ps.map(mapPerson));
      st.cases.clear(); st.persons.clear(); st.caseData = {}; st.personData = {}; st.graphFocus = undefined;
      const demo = document.querySelector("nav .demo");
      if (demo) demo.textContent = `LIVE BACKEND • ${CASES.length} CASES`;
      if (window._krCopilotRefresh) window._krCopilotRefresh();
    },
    withdraw: async cid => {
      const why = prompt(`Withdraw ${cid}? This removes the case and the people created with it. The evidence ledger keeps the original blocks and records the withdrawal.\n\nReason:`);
      if (why === null) return;
      const r = await fetch(`${API}/cases/${encodeURIComponent(cid)}?reason=${encodeURIComponent(why)}`, { method: "DELETE" });
      if (!r.ok) { toast("Could not withdraw the case"); return; }
      await window.KR.refresh(); toast(`${cid} withdrawn — recorded on the ledger`); location.hash = "#dash";
    },
  };

  async function bootstrap() {
    st.health = await j("/health", {}, 8000);
    const [cs, ps] = await Promise.all([j("/cases", {}, 30000), j("/persons", {}, 30000)]);
    if (!cs.length) throw new Error("no cases in backend");
    CASES.splice(0, CASES.length, ...cs.map(mapCase));
    PERS.splice(0, PERS.length, ...ps.map(mapPerson));
    EVT.splice(0, EVT.length);
    st.live = true;
    document.body.classList.add("kr-live");
    install();
    if (window._krCopilotRefresh) window._krCopilotRefresh();
    console.info(`KRONOS live backend: ${cs.length} cases, ${ps.length} persons, LLM ${st.health.llm.available ? "available" : "unavailable"}`);
  }
  window.KR.ready = (async () => {
    for (let attempt = 0; attempt < 2; attempt++) {
      try { await bootstrap(); return; } catch (e) { await new Promise(r => setTimeout(r, 1500)); }
    }
    console.info("KRONOS backend not reachable — running offline demonstration data; retrying in the background.");
    setTimeout(() => { if (typeof toast === "function") toast("Live backend not reachable — showing offline demo data (retrying)"); }, 1200);
    let tries = 0;
    const retry = async () => {
      if (st.live || tries++ > 40) return;
      try {
        await bootstrap();
        if (typeof toast === "function") toast("Connected to the live KRONOS backend");
        if (typeof route === "function") route();
      } catch (e) { setTimeout(retry, 15000); }
    };
    setTimeout(retry, 15000);
  })();
})();
