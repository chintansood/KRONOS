/* KRONOS — new-case intake.
   One draft, three ways in: a guided form (10 steps), the same questions as a conversation in the Copilot and in the home
   chat ("add a new case"), and a home-page section / dashboard button. Registration goes through POST /api/cases, which runs
   the FIR loader, SHA-256 hashing, the evidence ledger, recorded roles, NER, identity candidates, summary and index. */
(() => {
  "use strict";
  const API = "/api", LS = "kr_intake_v1";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const pad = n => String(n).padStart(2, "0");
  async function api(path, opt = {}, ms = 120000) {
    const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), ms);
    try {
      const r = await fetch(API + path, { ...opt, signal: ctl.signal, headers: { "content-type": "application/json" } });
      let data = null; try { data = await r.json(); } catch (e) { /* empty */ }
      return { ok: r.ok, status: r.status, data };
    } finally { clearTimeout(t); }
  }
  const live = () => !!(window.KR && window.KR.live);

  /* ------------------------------------------------------------------ draft + options */
  const nowLocal = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`; };
  const emptyDraft = () => ({ registration: { informationType: "Written complaint", registeredAt: nowLocal(), firNumber: "" },
    offence: { priority: "MEDIUM" }, occurrence: {}, complainant: { relation: "S/o", isVictim: true }, accused: [], others: [],
    property: {}, narrative: "", officer: { rank: "Sub-Inspector" } });
  let S;
  try { S = JSON.parse(localStorage.getItem(LS)) || null; } catch (e) { S = null; }
  if (!S || !S.draft) S = { draft: emptyDraft(), qi: 0, active: false, stack: [], review: null };
  const save = () => { try { localStorage.setItem(LS, JSON.stringify(S)); } catch (e) { /* quota */ } };
  let OPT = null;
  const options = () => OPT || (OPT = api("/intake/options", {}, 30000).then(r => { if (!r.ok) throw new Error("options"); return r.data; })
    .catch(e => { OPT = null; throw e; }));
  const get = (o, path) => path.split(".").reduce((a, k) => (a == null ? a : a[k]), o);
  const set = (o, path, v) => { const ks = path.split("."); let a = o; ks.slice(0, -1).forEach(k => { if (a[k] == null) a[k] = /^\d+$/.test(k) ? {} : {}; a = a[k]; }); a[ks[ks.length - 1]] = v; };

  /* ------------------------------------------------------------------ parsing */
  function parseDT(t) {
    t = String(t || "").trim().toLowerCase().replace(/\s+hrs?$/, "");
    if (!t) return null;
    const now = new Date();
    if (/^now$|^right now$|^just now$/.test(t)) return nowLocal();
    let base = null, rest = t;
    const rel = t.match(/^(today|yesterday)\s*(?:at\s*)?(.*)$/);
    if (rel) { base = new Date(now); if (rel[1] === "yesterday") base.setDate(base.getDate() - 1); rest = rel[2]; }
    let m;
    if (!base && (m = t.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ t]+(.*))?$/))) { base = new Date(+m[1], +m[2] - 1, +m[3]); rest = m[4] || ""; }
    else if (!base && (m = t.match(/^(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{2,4})(?:[ ,]+(?:at\s*)?(.*))?$/))) { base = new Date(+(m[3].length === 2 ? "20" + m[3] : m[3]), +m[2] - 1, +m[1]); rest = m[4] || ""; }
    else if (!base && (m = t.match(/^(\d{1,2})\s+([a-z]{3})[a-z]*\s+(\d{4})(?:[ ,]+(?:at\s*)?(.*))?$/))) {
      const mi = MON.findIndex(x => x.toLowerCase() === m[2]); if (mi < 0) return null; base = new Date(+m[3], mi, +m[1]); rest = m[4] || ""; }
    if (!base || isNaN(base)) return null;
    let hh = 12, mm = 0;
    if (rest) {
      const tm = rest.match(/^(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?$/);
      if (!tm) return null;
      hh = +tm[1]; mm = +(tm[2] || 0);
      if (tm[3] === "pm" && hh < 12) hh += 12; if (tm[3] === "am" && hh === 12) hh = 0;
      if (hh > 23 || mm > 59) return null;
    } else if (!rel) return null;      // a date needs a time ("26/02/2025 19:30")
    return `${base.getFullYear()}-${pad(base.getMonth() + 1)}-${pad(base.getDate())}T${pad(hh)}:${pad(mm)}`;
  }
  const fmtDT = iso => { if (!iso) return "—"; const [d, t] = iso.split("T"); const [y, mo, da] = d.split("-"); return `${+da} ${MON[+mo - 1]} ${y} · ${t || ""}`; };
  const dmy = iso => { const [y, mo, da] = iso.split("T")[0].split("-"); return `${da}/${mo}/${y}`; };
  const hm = iso => (iso.split("T")[1] || "").slice(0, 5);
  const parsePhone = t => { const d = String(t || "").replace(/\D/g, ""); return d.length >= 10 ? `+91-${d.slice(-10)}` : null; };
  const listOf = t => String(t || "").split(/[,;\n]+/).map(x => x.trim()).filter(Boolean);
  function classify(t) {
    const out = { accounts: [], vehicles: [], devices: [] };
    listOf(t).forEach(x => {
      const u = x.toUpperCase().replace(/\s+/g, "");
      if (/^[A-Z]{2}\d{1,2}[A-Z]{0,3}\d{3,4}$/.test(u) || /^[A-Z]{2}\d{1,2}[A-Z]?-[A-Z]{1,2}-\d{4}$/.test(u)) out.vehicles.push(u.includes("-") ? u : u.replace(/^([A-Z]{2})(\d{1,2})([A-Z]{0,3})(\d{3,4})$/, "$1$2-$3-$4"));
      else if (/^(IMEI-?)?\d{15}$/.test(u)) out.devices.push(u.startsWith("IMEI") ? u.replace(/^IMEI-?/, "IMEI-") : "IMEI-" + u);
      else out.accounts.push(x.trim());
    });
    return out;
  }
  const YES = /^(y|yes|yeah|yep|haan|ha|han|ok|okay|sure|correct|true|हाँ|हां)\b/i, NO = /^(n|no|nope|nah|none|nil|nahi|nahin|नहीं|false)\b/i;
  const delayH = d => { const a = Date.parse(d.occurrence.from || ""), b = Date.parse(d.registration.registeredAt || ""); return isNaN(a) || isNaN(b) ? 0 : (b - a) / 36e5; };
  const shortCat = c => String(c || "Case").replace(/\s*\(.*\)\s*/, "").trim();
  const cityOf = d => d.registration.district || (String(d.occurrence.place || "").split(",").pop() || "").trim();
  const suggestTitle = d => d.offence.category ? `${shortCat(d.offence.category)}${cityOf(d) ? " — " + cityOf(d) : ""}` : "";
  const particular = e => `${e.name}${e.alias ? ` @ ${e.alias}` : ""}${e.relative ? ` ${e.relation || "S/o"} ${e.relative}` : ""}`;
  function draftNarrative(d) {
    const c = d.complainant, oc = d.occurrence, pr = d.property || {};
    const acc = d.accused.filter(a => !a.unknown && a.name), unk = d.accused.filter(a => a.unknown);
    const cat = String(d.offence.category || "an offence").toLowerCase();
    let s = `The complainant ${c.name || "[name]"}${c.relative ? ` ${c.relation || "S/o"} ${c.relative}` : ""}${c.phone ? ` (mobile ${c.phone})` : ""}` +
      `${c.address ? `, resident of ${c.address}` : ""}, stated that${oc.from ? ` on ${dmy(oc.from)} at about ${hm(oc.from)} hrs` : ""}${oc.place ? ` at ${oc.place}` : ""}, ` +
      (c.isVictim === false ? `an offence of ${cat} was committed.` : `the complainant was the victim of ${cat}.`);
    if (oc.to) s += ` The acts continued until ${dmy(oc.to)} at about ${hm(oc.to)} hrs.`;
    if (acc.length) s += ` The complainant named ${acc.map(particular).join(" and ")} as the accused${unk.length ? `, and stated that ${unk.length} unidentified person(s) were also involved` : ""}.`;
    else if (unk.length) s += ` The accused ${unk.length > 1 ? "persons are" : "person is"} not yet identified${unk[0].description ? ` (${unk[0].description})` : ""}.`;
    if (pr.description || pr.value) s += ` Property involved: ${pr.description || "not specified"}${pr.value ? `, valued at approximately Rs ${pr.value}` : ""}.`;
    const ac = listOf(pr.accounts); if (ac.length) s += ` Money was transferred to ${ac.join(", ")}.`;
    const ve = listOf(pr.vehicles); if (ve.length) s += ` Vehicle(s) ${ve.join(", ")} were involved.`;
    const wi = d.others.filter(o => o.name);
    if (wi.length) s += ` ${wi.map(o => `${o.name} (${o.role === "VICTIM" ? "victim" : "witness"})`).join(", ")} ${wi.length > 1 ? "were" : "was"} also named.`;
    if (oc.delayReason) s += ` The delay in reporting is explained as: ${oc.delayReason}.`;
    return s + " The complainant requested that legal action be taken against the accused.";
  }
  async function applyStation(d, name) {
    const o = await options().catch(() => null);
    const st = o && o.stations.find(s => s.name.toLowerCase() === String(name).toLowerCase());
    d.registration.policeStation = st ? st.name : name;
    if (st) { d.registration.district = st.district; d.registration.agencyId = st.agencyId; }
    await refreshFir(d);
    return st;
  }
  async function refreshFir(d) {
    if (!d.registration.policeStation) return;
    const y = (d.registration.registeredAt || "").slice(0, 4) || new Date().getFullYear();
    const r = await api(`/intake/next-fir?station=${encodeURIComponent(d.registration.policeStation)}&year=${y}`, {}, 15000).catch(() => null);
    if (r && r.ok && (!d.registration.firNumber || d.registration._firAuto)) { d.registration.firNumber = r.data.firNumber; d.registration._firAuto = true; }
  }
  async function applyPlace(d, place) {
    d.occurrence.place = place;
    const o = await options().catch(() => null);
    const p = o && o.places.find(x => x.name.toLowerCase() === String(place).toLowerCase());
    if (p) { d.occurrence.place = p.name; d.occurrence.lat = p.lat; d.occurrence.lon = p.lon; d.occurrence._known = true; }
    else { delete d.occurrence.lat; delete d.occurrence.lon; d.occurrence._known = false; }
    return p;
  }
  const AGENCY = { "AGY-PB": "Punjab Police", "AGY-HR": "Haryana Police", "AGY-DL": "Delhi Police", "AGY-CHD": "Chandigarh Police" };
  function syncTxt(d) {   // identifier lists are edited as comma-separated text in the form
    const p = d.property || (d.property = {});
    ["accounts", "vehicles", "devices"].forEach(k => { if (p[k + "Txt"] == null) p[k + "Txt"] = (p[k] || []).join(", "); p[k] = listOf(p[k + "Txt"]); });
  }
  const payload = (d, channel) => { syncTxt(d); const p = JSON.parse(JSON.stringify(d)); p.channel = channel; p.clientNow = nowLocal(); return p; };

  /* ------------------------------------------------------------------ the conversation (Copilot + home chat) */
  const STEPS = ["Registration", "Offence", "Occurrence", "Complainant", "Accused", "Victims & witnesses", "Property & identifiers", "Statement", "Officer", "Review"];
  const curA = d => d.accused[d._ai ?? d.accused.length - 1], curO = d => d.others[d._oi ?? d.others.length - 1];
  const Q = [
    { id: "station", step: 1, ask: () => "Which <b>police station</b> is registering the FIR?", chips: async () => ((await options()).stations || []).slice(0, 5).map(s => s.name),
      set: async (d, t) => { const st = await applyStation(d, t); return st ? null : { note: `New station — please also give the district. Example: <i>District: SAS Nagar</i>` }; } },
    { id: "district", step: 1, when: d => !d.registration.district, ask: () => "Which <b>district</b>?", set: async (d, t) => { d.registration.district = t.replace(/^district:?\s*/i, ""); const o = await options(); const di = o.districts.find(x => x.name.toLowerCase() === d.registration.district.toLowerCase()); if (di) d.registration.agencyId = di.agencyId; } },
    { id: "agency", step: 1, when: d => !d.registration.agencyId, ask: () => "Which <b>state police unit</b>?", chips: () => Object.values(AGENCY),
      set: (d, t) => { const k = Object.keys(AGENCY).find(k => AGENCY[k].toLowerCase().startsWith(t.toLowerCase().slice(0, 4)) || k.toLowerCase() === t.toLowerCase()); if (!k) return "Choose Punjab, Haryana, Delhi or Chandigarh Police."; d.registration.agencyId = k; } },
    { id: "registeredAt", step: 1, ask: d => `When was the FIR <b>registered</b>? (e.g. <i>now</i>, <i>today 11:20</i>, <i>02/03/2025 11:20</i>)`, chips: () => ["now"],
      set: async (d, t) => { const v = parseDT(t); if (!v) return "I couldn't read that date and time. Try <i>now</i> or <i>02/03/2025 11:20</i>."; if (Date.parse(v) > Date.now() + 6e4) return "Registration can't be in the future."; d.registration.registeredAt = v; await refreshFir(d); } },
    { id: "category", step: 2, ask: () => "What is the <b>offence category</b>?", chips: async () => ((await options()).categories || []).slice(0, 7).map(c => c.name),
      set: async (d, t) => {
        const o = await options(); const RESTR = /sexual|rape|molest|pocso|child|minor|juvenile|kidnap|abduct|traffick|dowry|matrimon|498|sc\/?st|atrocit/i;
        if (RESTR.test(t)) return o.restrictedNote;
        const c = o.categories.find(x => x.name.toLowerCase() === t.toLowerCase()) || o.categories.find(x => x.name.toLowerCase().includes(t.toLowerCase()));
        d.offence.category = c ? c.name : t; d.offence._suggestedSections = c ? c.sections : ""; } },
    { id: "sections", step: 2, optional: true, ask: d => `Which <b>Acts &amp; Sections</b>?${d.offence._suggestedSections ? ` Usual for this category: <b>${esc(d.offence._suggestedSections)}</b>.` : ""}`,
      chips: d => d.offence._suggestedSections ? ["use suggested"] : [], set: (d, t) => { d.offence.sections = /^use suggested|^suggested|^ok$/i.test(t) ? d.offence._suggestedSections : t; } },
    { id: "title", step: 2, ask: d => `A short <b>case title</b>?`, chips: d => suggestTitle(d) ? [suggestTitle(d)] : [], set: (d, t) => { d.offence.title = t; } },
    { id: "priority", step: 2, ask: () => "<b>Priority</b> for administrative triage? (not an assessment of anyone)", chips: () => ["Low", "Medium", "High", "Critical"],
      set: (d, t) => { const v = t.toUpperCase(); if (!["LOW", "MEDIUM", "HIGH", "CRITICAL"].includes(v)) return "Low, Medium, High or Critical."; d.offence.priority = v; } },
    { id: "from", step: 3, ask: () => "When did the <b>offence occur</b>? (date and time; e.g. <i>26/02/2025 19:30</i>)",
      set: d => null, parse: true },
    { id: "place", step: 3, ask: () => "Where did it <b>occur</b>? (place / address)", chips: async () => ((await options()).places || []).slice(0, 4).map(p => p.name),
      set: async (d, t) => { const p = await applyPlace(d, t); return p ? { note: `Known place — coordinates ${p.lat.toFixed(3)}, ${p.lon.toFixed(3)} added for the location engines.` } : null; } },
    { id: "delay", step: 3, when: d => delayH(d) > 24, ask: d => `The FIR was registered <b>${Math.round(delayH(d))} h</b> after the occurrence. What is the <b>reason for the delay</b>? (FIR item 8)`,
      set: (d, t) => { d.occurrence.delayReason = t; } },
    { id: "c.name", step: 4, ask: () => "Name of the <b>complainant / informant</b>?", set: (d, t) => { d.complainant.name = t; } },
    { id: "c.relative", step: 4, optional: true, ask: () => "Father's / husband's name? (e.g. <i>S/o Ram Prakash</i>, <i>W/o Balwinder Singh</i>, or skip)",
      set: (d, t) => { const m = t.match(/^([SDW])\/?o\.?\s+(.+)$/i); d.complainant.relation = m ? m[1].toUpperCase() + "/o" : "S/o"; d.complainant.relative = m ? m[2] : t; } },
    { id: "c.phone", step: 4, optional: true, ask: () => "Complainant's <b>mobile number</b>?", set: (d, t) => { const p = parsePhone(t); if (!p) return "That isn't a 10-digit mobile number."; d.complainant.phone = p; } },
    { id: "c.address", step: 4, optional: true, ask: () => "Complainant's <b>address</b>?", set: (d, t) => { d.complainant.address = t; } },
    { id: "c.victim", step: 4, ask: () => "Is the complainant also the <b>victim</b>?", chips: () => ["yes", "no"], set: (d, t) => { if (!YES.test(t) && !NO.test(t)) return "yes or no?"; d.complainant.isVictim = YES.test(t); } },
    { id: "a.name", step: 5, ask: d => `Name of <b>accused #${d.accused.length + 1}</b>? (type <i>unknown</i> if not yet identified)`, chips: d => ["unknown"],
      set: (d, t) => { if (/^(unknown|not known|unidentified|unknown persons?)$/i.test(t)) d.accused.push({ unknown: true }); else d.accused.push({ name: t, relation: "S/o", role: d.accused.some(a => a.role === "PRINCIPAL_ACCUSED") ? "ACCUSED" : "PRINCIPAL_ACCUSED" }); d._ai = d.accused.length - 1; } },
    { id: "a.desc", step: 5, optional: true, when: d => curA(d) && curA(d).unknown, ask: () => "Any <b>description</b> of the unknown person(s)?", set: (d, t) => { curA(d).description = t; } },
    { id: "a.alias", step: 5, optional: true, when: d => curA(d) && !curA(d).unknown, ask: d => `Any <b>alias</b> (@) for ${esc(curA(d).name)}?`, set: (d, t) => { curA(d).alias = t.replace(/^@\s*/, ""); } },
    { id: "a.relative", step: 5, optional: true, when: d => curA(d) && !curA(d).unknown, ask: d => `${esc(curA(d).name)}'s father's name? (e.g. <i>S/o Mahinder Dhillon</i>)`,
      set: (d, t) => { const m = t.match(/^([SDW])\/?o\.?\s+(.+)$/i); curA(d).relation = m ? m[1].toUpperCase() + "/o" : "S/o"; curA(d).relative = m ? m[2] : t; } },
    { id: "a.address", step: 5, optional: true, when: d => curA(d) && !curA(d).unknown, ask: d => `${esc(curA(d).name)}'s <b>address</b>?`, set: (d, t) => { curA(d).address = t; } },
    { id: "a.phone", step: 5, optional: true, when: d => curA(d) && !curA(d).unknown, ask: d => `${esc(curA(d).name)}'s <b>mobile number</b>?`, set: (d, t) => { const p = parsePhone(t); if (!p) return "That isn't a 10-digit mobile number."; curA(d).phone = p; } },
    { id: "a.more", step: 5, ask: () => "Add <b>another accused</b>?", chips: () => ["yes", "no"], set: (d, t) => { if (YES.test(t)) return { goto: "a.name" }; if (!NO.test(t)) return "yes or no?"; } },
    { id: "o.name", step: 6, ask: d => d.others.length ? "Name of the next <b>victim or witness</b>? (or <i>none</i>)" : "Any other <b>victim or witness</b> to record? Give a name, or <i>none</i>.", chips: () => ["none"],
      set: (d, t) => { if (NO.test(t)) return { goto: "idents" }; d.others.push({ name: t, role: "WITNESS" }); d._oi = d.others.length - 1; } },
    { id: "o.role", step: 6, ask: d => `Is ${esc(curO(d).name)} a <b>victim</b> or a <b>witness</b>?`, chips: () => ["victim", "witness"],
      set: (d, t) => { if (!/^(victim|witness)/i.test(t)) return "victim or witness?"; curO(d).role = /^victim/i.test(t) ? "VICTIM" : "WITNESS"; } },
    { id: "o.phone", step: 6, optional: true, ask: d => `${esc(curO(d).name)}'s mobile number?`, set: (d, t) => { const p = parsePhone(t); if (!p) return "That isn't a 10-digit mobile number."; curO(d).phone = p; } },
    { id: "o.more", step: 6, ask: () => "Another victim or witness?", chips: () => ["yes", "no"], set: (d, t) => { if (YES.test(t)) return { goto: "o.name" }; if (!NO.test(t)) return "yes or no?"; } },
    { id: "idents", step: 7, optional: true, ask: () => "Any <b>bank accounts / UPI IDs, vehicle numbers or phones/IMEIs</b> involved? Separate with commas.",
      set: (d, t) => { const c = classify(t); ["accounts", "vehicles", "devices"].forEach(k => { d.property[k] = c[k]; d.property[k + "Txt"] = c[k].join(", "); });
        return { note: [c.accounts.length && `${c.accounts.length} account(s)`, c.vehicles.length && `${c.vehicles.length} vehicle(s)`, c.devices.length && `${c.devices.length} device(s)`].filter(Boolean).join(", ") + " noted." }; } },
    { id: "value", step: 7, optional: true, ask: () => "<b>Property</b> involved and its approximate <b>value</b>? (e.g. <i>money via UPI, 2,40,000</i>)",
      set: (d, t) => { const m = t.match(/([\d,]+(?:\.\d+)?)\s*(?:rs|₹|inr)?\s*$/i) || t.match(/(?:rs\.?|₹)\s*([\d,]+)/i); d.property.value = m ? m[1] : ""; d.property.description = t.replace(m ? m[0] : "", "").replace(/[,;\s]+$/, "").trim() || d.property.description || ""; } },
    { id: "narrative", step: 8, ask: () => "Now the <b>FIR contents</b>: type the complainant's statement in their words — or say <i>draft</i> and I'll compose one from the particulars for you to review.",
      chips: () => ["draft"], set: (d, t) => { if (/^draft/i.test(t)) { d.narrative = draftNarrative(d); return { goto: "narrative.ok", note: `Draft statement:<div class="kri-quote">${esc(d.narrative)}</div>` }; } if (t.length < 40) return "Please give at least a few sentences."; d.narrative = t; return { goto: "officer" }; } },
    { id: "narrative.ok", step: 8, when: () => false, ask: () => "Use this statement? (<i>yes</i>, or type the complainant's own words to replace it)", chips: () => ["yes"],
      set: (d, t) => { if (YES.test(t)) return; if (t.length < 40) return "Please give at least a few sentences, or say yes."; d.narrative = t; } },
    { id: "officer", step: 9, ask: () => "Your <b>name and rank</b> as investigating officer? (e.g. <i>SI Amandeep Singh</i>)",
      set: (d, t) => { const R = { si: "Sub-Inspector", asi: "Assistant Sub-Inspector", insp: "Inspector", inspector: "Inspector", dsp: "Deputy Superintendent of Police", hc: "Head Constable" };
        const m = t.match(/^(si|asi|insp\.?|inspector|dsp|hc|sub-inspector|assistant sub-inspector|head constable)\s+(.+)$/i);
        d.officer.rank = m ? (R[m[1].toLowerCase().replace(".", "")] || m[1]) : d.officer.rank; d.officer.name = m ? m[2] : t; } },
  ];
  const qIndex = id => Q.findIndex(q => q.id === id);
  const nextQ = (d, from) => { for (let i = from; i < Q.length; i++) if (!Q[i].when || Q[i].when(d)) return i; return Q.length; };
  const bar = step => `<div class="kri-prog"><span>STEP ${Math.min(step, 10)} OF 10 · ${esc(STEPS[step - 1] || "Review").toUpperCase()}</span><i style="width:${Math.min(step, 10) * 10}%"></i></div>`;
  const chipBtns = (ch, list) => list.length ? `<div class="kri-chips">${list.map(c => `<button type="button" class="kri-chip" data-v="${esc(c)}" onclick="KRintake.say('${ch}', this.dataset.v)">${esc(c)}</button>`).join("")}</div>` : "";
  const ctrl = (ch, q) => chipBtns(ch, [...(q && q.optional ? ["skip"] : []), "back", "form", "cancel"]).replace('class="kri-chips"', 'class="kri-chips kri-ctl"');

  async function askHTML(ch, d, note) {
    if (S.qi >= Q.length) return reviewChat(ch, note);
    const q = Q[S.qi];
    const chips = q.chips ? await Promise.resolve(q.chips(d)).catch(() => []) : [];
    return `${note ? `<div class="kri-note">${note}</div>` : ""}${bar(q.step)}<div class="kri-q">${q.ask(d)}</div>${chipBtns(ch, chips)}${ctrl(ch, q)}`;
  }
  const INTENT = /\b(add|register|file|lodge|create|start|open)\b[^.?!]{0,24}\b(new\s+)?(case|fir|complaint)\b|\bnew\s+(case|fir|complaint)\b|नया (केस|मामला)|(केस|मामला|एफआईआर|fir) दर्ज|નવો કેસ|ਨਵਾਂ ਕੇਸ/i;
  const wants = (ch, text) => (S.active && S.channel === ch) || (INTENT.test(text) && !/\b(open|show|go to)\s+case\s*\d/i.test(text) && !/\bCASE\d{3}\b/i.test(text));

  async function chat(ch, raw, put) {
    const t = String(raw || "").trim();
    const d = S.draft;
    try {
      if (!S.active || S.channel !== ch) {
        if (!live()) { put("Registering a case needs the live KRONOS backend, which isn't reachable right now."); return; }
        const inProgress = S.active || (S.qi > 0 && S.qi < Q.length) || S.review;
        S.active = true; S.channel = ch; save();
        if (inProgress) { put(`You have a case draft in progress (${esc(d.offence.title || d.registration.policeStation || "untitled")}). Continue where you left off, or start over?${chipBtns(ch, ["continue", "start over"])}`); S._resume = true; save(); return; }
        S.draft = emptyDraft(); S.qi = nextQ(S.draft, 0); S.stack = []; S.review = null; save();
        put(`<div class="kri-hello"><b>Let's register a new case.</b> I'll ask for each FIR particular one at a time — about 2 minutes. ` +
            `Say <i>skip</i> for optional items, <i>back</i> to change the previous answer, <i>form</i> to continue in the full form, or <i>cancel</i> to stop.</div>` + await askHTML(ch, S.draft));
        return;
      }
      if (S._resume) {
        S._resume = false;
        if (/^start over|^restart|^new$/i.test(t)) { S.draft = emptyDraft(); S.qi = 0; S.stack = []; S.review = null; }
        save(); put(await askHTML(ch, S.draft)); return;
      }
      if (/^(cancel|stop|quit|exit)$/i.test(t)) { S.active = false; save(); put(`Stopped. Your draft is kept — say <i>add a new case</i> to resume, or <i>discard draft</i> to clear it.${chipBtns(ch, ["discard draft"])}`); return; }
      if (/^discard( draft)?$/i.test(t)) { S = { draft: emptyDraft(), qi: 0, active: false, stack: [], review: null }; save(); put("Draft discarded."); return; }
      if (/^(form|open form|full form)$/i.test(t)) { S.active = false; save(); open(S.qi >= Q.length ? 10 : Q[S.qi].step); put("Opened the full form with everything entered so far."); return; }
      if (/^back$/i.test(t)) {
        const prev = S.stack.pop();
        if (prev) { S.draft = prev.draft; S.qi = prev.qi; S.review = null; }
        save(); put(await askHTML(ch, S.draft, prev ? "Going back." : "This is the first question.")); return;
      }
      if (S.qi >= Q.length) return reviewCommand(ch, t, put);
      const q = Q[S.qi];
      S.stack.push({ draft: JSON.parse(JSON.stringify(d)), qi: S.qi }); if (S.stack.length > 60) S.stack.shift();
      let res = null;
      if (/^skip$/i.test(t)) {
        if (!q.optional) { S.stack.pop(); put(await askHTML(ch, d, "This one is required.")); return; }
      } else if (q.id === "from") {
        const v = parseDT(t);
        if (!v) res = "I couldn't read that. Try <i>26/02/2025 19:30</i> or <i>yesterday 19:30</i>.";
        else if (Date.parse(v) > Date.parse(d.registration.registeredAt)) res = "The occurrence can't be after the FIR was registered.";
        else d.occurrence.from = v;
      } else {
        res = await Promise.resolve(q.set(d, t));
      }
      if (typeof res === "string") { S.stack.pop(); save(); put(await askHTML(ch, d, `<span class="kri-bad">${res}</span>`)); return; }
      let note = res && res.note ? res.note : "";
      if (q.id === "station" && d.registration.district) note = `${esc(d.registration.policeStation)} · ${esc(d.registration.district)} · ${esc(AGENCY[d.registration.agencyId] || "")}` +
        `${d.registration.firNumber ? ` · FIR number <b>${esc(d.registration.firNumber)}</b> (next in sequence)` : ""}` + (note ? `<br>${note}` : "");
      S.qi = res && res.goto ? qIndex(res.goto) : nextQ(d, S.qi + 1);
      if (S.qi >= Q.length) S.qi = Q.length;
      save();
      put(await askHTML(ch, d, note));
    } catch (e) {
      put(`Something went wrong (${esc(e.message || e)}). Your answers are saved — try again, or say <i>form</i>.`);
    }
  }

  /* ------------------------------------------------------------------ review (chat) */
  const refLabel = (d, ref) => { const [g, i] = ref.split("."); if (g === "complainant") return `complainant ${d.complainant.name}`;
    const e = (g === "accused" ? d.accused : d.others)[+i] || {}; return `${g === "accused" ? "accused" : (e.role || "").toLowerCase() || "person"} ${e.name || ""}`; };
  const entryOf = (d, ref) => { const [g, i] = ref.split("."); return g === "complainant" ? d.complainant : (g === "accused" ? d.accused : d.others)[+i]; };
  function summaryHTML(d) {
    const acc = d.accused.map(a => a.unknown ? `unknown${a.description ? ` (${esc(a.description)})` : ""}` : `${esc(particular(a))}${a.linkTo ? ` → <b>${esc(a.linkTo)}</b>` : ""}`).join("; ") || "—";
    return `<div class="kri-sum">
      <div><span>FIR</span>${esc(d.registration.firNumber || "—")} · ${esc(d.registration.policeStation || "")}, ${esc(d.registration.district || "")} · registered ${esc(fmtDT(d.registration.registeredAt))}</div>
      <div><span>Offence</span>${esc(d.offence.category || "—")}${d.offence.sections ? ` · ${esc(d.offence.sections)}` : ""} · ${esc(d.offence.priority || "")}</div>
      <div><span>Occurrence</span>${esc(fmtDT(d.occurrence.from))} at ${esc(d.occurrence.place || "—")}</div>
      <div><span>Complainant</span>${esc(d.complainant.name || "—")}${d.complainant.phone ? ` · ${esc(d.complainant.phone)}` : ""}${d.complainant.linkTo ? ` → <b>${esc(d.complainant.linkTo)}</b>` : ""}</div>
      <div><span>Accused</span>${acc}</div>
      ${d.others.length ? `<div><span>Victims / witnesses</span>${d.others.map(o => `${esc(o.name)} (${esc((o.role || "").toLowerCase())})`).join(", ")}</div>` : ""}
      <div><span>Officer</span>${esc([d.officer.rank, d.officer.name].filter(Boolean).join(" ") || "—")}</div></div>`;
  }
  function checkHTML(d, c, ch) {
    let h = "";
    if (c.errors.length) h += `<div class="kri-box bad"><b>To fix before registering</b>${c.errors.map(e => `<div>• ${esc(e.message)}</div>`).join("")}</div>`;
    if (c.warnings.length) h += `<div class="kri-box warn">${c.warnings.map(e => `<div>• ${esc(e.message)}</div>`).join("")}</div>`;
    if (c.matches.length) h += `<div class="kri-box"><b>Already on record?</b> ${esc(c.note)}` + c.matches.map(m => {
      const e = entryOf(d, m.ref) || {};
      return `<div class="kri-match"><div>For <b>${esc(refLabel(d, m.ref))}</b>:</div>${m.candidates.map(x => `<div class="kri-cand"><b>${esc(x.personId)}</b> ${esc(x.name)} — ${esc(x.basis.join(", "))}${x.recordedRoles.length ? `<br><small>${esc(x.recordedRoles.join(" · "))}</small>` : ""}<br><small>${esc(x.note)}</small></div>`).join("")}
        ${ch ? chipBtns(ch, [...m.candidates.map(x => `link ${m.ref} ${x.personId}`), `new ${m.ref}`]) : ""}${e.linkTo ? `<div class="kri-ok">Linked to ${esc(e.linkTo)}</div>` : ""}</div>`;
    }).join("") + "</div>";
    if (c.identifierHits.length) h += `<div class="kri-box intel"><b>Seen in other cases</b>${c.identifierHits.map(x => `<div>• ${esc(x.kind.toLowerCase())} <span class="mono">${esc(x.value)}</span> — ${x.records} record(s) in ${x.cases.map(k => `<a class="kr-a" href="#case/${esc(k.caseId)}">${esc(k.caseId)}</a> (${k.records})`).join(", ")}</div>`).join("")}</div>`;
    return h;
  }
  async function reviewChat(ch, note) {
    const d = S.draft;
    const r = await api("/intake/check", { method: "POST", body: JSON.stringify(payload(d, ch)) }, 60000);
    if (!r.ok) return `${note ? `<div class="kri-note">${note}</div>` : ""}Couldn't run the intake checks (${r.status}).`;
    S.review = r.data; save();
    return `${note ? `<div class="kri-note">${note}</div>` : ""}${bar(10)}<div class="kri-q"><b>Review before registering</b> — this becomes <b>${esc(r.data.caseIdPreview)}</b>.</div>
      ${summaryHTML(d)}${checkHTML(d, r.data, ch)}
      ${chipBtns(ch, r.data.ok ? ["register case"] : [])}${chipBtns(ch, ["form", "back", "cancel"]).replace('class="kri-chips"', 'class="kri-chips kri-ctl"')}`;
  }
  async function reviewCommand(ch, t, put) {
    const d = S.draft;
    let m;
    if ((m = t.match(/^link\s+(complainant|accused\.\d+|others\.\d+)\s+(P\d{5})$/i))) { const e = entryOf(d, m[1].toLowerCase()); if (e) e.linkTo = m[2].toUpperCase(); save(); put(await reviewChat(ch, `${esc(refLabel(d, m[1].toLowerCase()))} will be linked to existing record <b>${esc(m[2].toUpperCase())}</b>.`)); return; }
    if ((m = t.match(/^new\s+(complainant|accused\.\d+|others\.\d+)$/i))) { const e = entryOf(d, m[1].toLowerCase()); if (e) delete e.linkTo; save(); put(await reviewChat(ch, `${esc(refLabel(d, m[1].toLowerCase()))} will be a new record; an identity candidate is raised if KRONOS finds a likely match.`)); return; }
    if (/^(register|register case|submit|yes|confirm)$/i.test(t)) {
      put(`<div class="kri-q">Registering… <span class="kri-spin"></span></div><div class="kri-muted">Hashing the record, writing the ledger block, extracting entities, checking identities, writing the summary and the search index.</div>`);
      const r = await register(d, ch);
      if (!r.ok) { put(`<span class="kri-bad">Not registered.</span>${(r.data && r.data.errors || []).map(e => `<div>• ${esc(e.message)}</div>`).join("") || esc(r.status)}${chipBtns(ch, ["form", "back"])}`); return; }
      S = { draft: emptyDraft(), qi: 0, active: false, stack: [], review: null }; save();
      put(resultHTML(r.data) + chipBtns(ch, [`open ${r.data.caseId}`]));
      return;
    }
    put(await reviewChat(ch, "Use the buttons: link a person, keep as new, or register."));
  }

  /* ------------------------------------------------------------------ registration + result */
  async function register(d, channel) {
    const r = await api("/cases", { method: "POST", body: JSON.stringify(payload(d, channel)) }, 240000);
    if (r.ok) {
      try { if (window.KR && KR.refresh) await KR.refresh(); } catch (e) { /* the case is registered; the list refreshes on reload */ }
      if (typeof toast === "function") toast(`Registered ${r.data.caseId}`);
    }
    return r;
  }
  function resultHTML(x) {
    const ent = x.entities || {}, by = ent.byType || {};
    const rows = [
      ["Record hashed", `SHA-256 <span class="mono">${esc(x.sha256.slice(0, 16))}…</span> · ${esc(x.evidenceId)}`],
      ["Evidence ledger", `INGEST block + Merkle anchor <span class="mono">${esc(String((x.ledger || {}).anchor || "").slice(0, 12))}…</span>, signed by the agency quorum`],
      ["Recorded roles", x.roles.map(r => `${esc(r.personId)} ${esc(r.role.toLowerCase().replace("_", " "))}`).join(" · ")],
      ["People", x.persons.map(p => `${esc(p.personId)} ${esc(p.name)}${p.linked ? " (existing record)" : " (new)"}`).join(" · ")],
      ["Entities read from the FIR", `${ent.total || 0} — ${Object.entries(by).map(([k, v]) => `${v} ${k.toLowerCase().replace("_", " ")}`).join(", ")}`],
      ["Identity candidates", x.identityCandidates.length ? x.identityCandidates.map(c => `${esc(c.other)} (${esc(c.band)}, ${c.score})`).join(", ") + " — for review, never merged" : "none raised"],
      ["Prior-record links", `${x.priorRecordLinks} (context only, not scored)`],
      ["Case summary &amp; search index", `${(x.index || {}).chunks || 0} chunk(s)${(x.index || {}).embedded ? `, ${x.index.embedded} embedded` : ""}`],
    ];
    if ((x.identifierHits || []).length) rows.push(["Seen in other cases", x.identifierHits.map(h => `${esc(h.kind.toLowerCase())} ${esc(h.value)} → ${h.cases.map(c => esc(c.caseId)).join(", ")}`).join("<br>")]);
    return `<div class="kri-done"><div class="kri-done-h">✓ ${esc(x.caseId)} registered <small>${x.seconds}s</small></div>${rows.map(([k, v], i) => `<div class="kri-pipe" style="--i:${i}"><span>${k}</span><div>${v}</div></div>`).join("")}</div>`;
  }

  /* ------------------------------------------------------------------ the form */
  const FSTEPS = [
    { t: "Registration", s: "Where and when the FIR is registered" }, { t: "Offence", s: "Category, Acts & Sections, priority" },
    { t: "Occurrence", s: "When and where it happened" }, { t: "Complainant", s: "The informant's particulars" },
    { t: "Accused", s: "Known, suspected or unknown" }, { t: "Victims & witnesses", s: "Other people to record" },
    { t: "Property & identifiers", s: "Money, accounts, vehicles, devices" }, { t: "Statement", s: "FIR contents in the complainant's words" },
    { t: "Officer", s: "Who is registering and investigating" }, { t: "Review & register", s: "Checks against existing records" },
  ];
  let ov = null, step = 1, busy = false;
  const fld = (k, label, o = {}) => {
    const v = get(S.draft, k) ?? "";
    const attrs = `data-k="${k}" id="kri-${k.replace(/\./g, "-")}" ${o.list ? `list="${o.list}"` : ""} ${o.ph ? `placeholder="${esc(o.ph)}"` : ""}`;
    const input = o.type === "select" ? `<select ${attrs}>${o.opts.map(x => `<option value="${esc(x[0])}" ${String(v) === String(x[0]) ? "selected" : ""}>${esc(x[1])}</option>`).join("")}</select>`
      : o.type === "textarea" ? `<textarea ${attrs} rows="${o.rows || 8}">${esc(v)}</textarea>`
      : o.type === "check" ? `<label class="kri-check"><input type="checkbox" ${attrs} ${v ? "checked" : ""}> ${esc(o.text)}</label>`
      : `<input ${attrs} type="${o.type || "text"}" value="${esc(v)}" autocomplete="off">`;
    return `<div class="kri-f ${o.req ? "req" : ""} ${o.wide ? "wide" : ""}">${o.type === "check" ? "" : `<label for="kri-${k.replace(/\./g, "-")}">${esc(label)}</label>`}${input}${o.hint ? `<div class="kri-hint">${o.hint}</div>` : ""}</div>`;
  };
  function stepHTML(o) {
    const d = S.draft;
    const rel = [["S/o", "S/o (son of)"], ["D/o", "D/o (daughter of)"], ["W/o", "W/o (wife of)"]];
    switch (step) {
      case 1: return fld("registration.policeStation", "Police station", { req: true, list: "kri-stations", ph: "e.g. PS Cyber Crime Mohali" }) +
        fld("registration.district", "District", { req: true, list: "kri-districts" }) +
        fld("registration.agencyId", "State police unit", { req: true, type: "select", opts: [["", "Choose…"], ...Object.entries(AGENCY)] }) +
        fld("registration.firNumber", "FIR number", { req: true, hint: "Next number in the station's sequence; edit if your register differs." }) +
        fld("registration.registeredAt", "Registered at", { req: true, type: "datetime-local" }) +
        fld("registration.informationType", "Type of information", { type: "select", opts: (o.informationTypes || ["Written complaint"]).map(x => [x, x]) });
      case 2: return fld("offence.category", "Offence category", { req: true, list: "kri-cats", ph: "Choose or type", hint: esc(o.restrictedNote || "") }) +
        fld("offence.sections", "Acts & Sections", { ph: "e.g. BNS 318(4), 319; IT Act 66D", hint: "Filled with the usual sections for the category — check them." }) +
        fld("offence.title", "Case title", { req: true, wide: true }) +
        fld("offence.priority", "Priority (administrative triage)", { type: "select", opts: [["LOW", "Low"], ["MEDIUM", "Medium"], ["HIGH", "High"], ["CRITICAL", "Critical"]] });
      case 3: return fld("occurrence.from", "Occurred from", { req: true, type: "datetime-local" }) + fld("occurrence.to", "Occurred until (if a period)", { type: "datetime-local" }) +
        fld("occurrence.place", "Place of occurrence", { req: true, wide: true, list: "kri-places", hint: d.occurrence._known ? `Known place · ${(+d.occurrence.lat).toFixed(4)}, ${(+d.occurrence.lon).toFixed(4)} — used by the travel and location engines` : "Pick a known place to add coordinates, or type an address." }) +
        (delayH(d) > 24 ? fld("occurrence.delayReason", `Reason for delay — reported ${Math.round(delayH(d))} h later (FIR item 8)`, { wide: true }) : "");
      case 4: return fld("complainant.name", "Name", { req: true }) + fld("complainant.relation", "Relation", { type: "select", opts: rel }) + fld("complainant.relative", "Father's / husband's name") +
        fld("complainant.age", "Age", { type: "number" }) + fld("complainant.phone", "Mobile number", { ph: "10-digit mobile" }) + fld("complainant.occupation", "Occupation") +
        fld("complainant.address", "Address", { wide: true }) + fld("complainant.isVictim", "", { type: "check", text: "The complainant is also the victim", wide: true });
      case 5: return (d.accused.map((a, i) => `<div class="kri-card"><div class="kri-card-h">${a.unknown ? "Unknown accused" : `Accused #${i + 1}`}<button type="button" class="kri-x" data-del="accused.${i}" aria-label="Remove">✕</button></div>
          <div class="kri-grid">${a.unknown ? fld(`accused.${i}.description`, "Description", { wide: true, ph: "e.g. the man who operated the Telegram channel" }) :
          fld(`accused.${i}.name`, "Name", { req: true }) + fld(`accused.${i}.alias`, "Alias (@)") + fld(`accused.${i}.relation`, "Relation", { type: "select", opts: rel }) + fld(`accused.${i}.relative`, "Father's name") +
          fld(`accused.${i}.phone`, "Mobile number") + fld(`accused.${i}.role`, "Recorded as", { type: "select", opts: [["PRINCIPAL_ACCUSED", "Principal accused"], ["ACCUSED", "Co-accused"]] }) +
          fld(`accused.${i}.address`, "Address", { wide: true })}</div></div>`).join("") || `<div class="kri-empty">No accused yet.</div>`) +
        `<div class="kri-add"><button type="button" class="kri-btn ghost" data-add="accused">+ Add accused</button><button type="button" class="kri-btn ghost" data-add="unknown">+ Unknown person(s)</button></div>`;
      case 6: return (d.others.map((x, i) => `<div class="kri-card"><div class="kri-card-h">${x.role === "VICTIM" ? "Victim" : "Witness"} #${i + 1}<button type="button" class="kri-x" data-del="others.${i}" aria-label="Remove">✕</button></div>
          <div class="kri-grid">${fld(`others.${i}.name`, "Name", { req: true }) + fld(`others.${i}.role`, "Recorded as", { type: "select", opts: [["WITNESS", "Witness"], ["VICTIM", "Victim"]] }) + fld(`others.${i}.phone`, "Mobile number")}</div></div>`).join("") ||
        `<div class="kri-empty">Optional — add anyone else the FIR should record.</div>`) + `<div class="kri-add"><button type="button" class="kri-btn ghost" data-add="others">+ Add victim / witness</button></div>`;
      case 7: return fld("property.description", "Property involved", { wide: true, ph: "e.g. money transferred via UPI and NEFT" }) + fld("property.value", "Approximate value (₹)") +
        fld("property.accountsTxt", "Bank accounts / UPI IDs", { wide: true, ph: "comma-separated, e.g. KKBK-55829849330" }) +
        fld("property.vehiclesTxt", "Vehicle numbers", { ph: "e.g. PB10-AB-1234" }) + fld("property.devicesTxt", "Devices / IMEI", { ph: "e.g. IMEI-350060827705646" });
      case 8: return fld("narrative", "FIR contents — the complainant's statement", { req: true, wide: true, type: "textarea", rows: 12,
          hint: `<button type="button" class="kri-btn ghost sm" data-draft="1">Draft from the particulars</button> <span>Review the draft and add the complainant's own account. KRONOS appends the particulars in the standard FIR form so they can be read by the entity extractor.</span>` });
      case 9: return fld("officer.rank", "Rank", { type: "select", opts: (o.ranks || []).map(x => [x, x]) }) + fld("officer.name", "Investigating officer", { req: true }) +
        fld("officer.leadInvestigator", "Lead investigator (if different)", { wide: true });
      default: return `<div id="kri-review" class="wide"><div class="kri-muted">Checking against existing records… <span class="kri-spin"></span></div></div>`;
    }
  }
  const REQ = {
    1: d => [["registration.policeStation", "Police station"], ["registration.district", "District"], ["registration.agencyId", "State police unit"], ["registration.firNumber", "FIR number"], ["registration.registeredAt", "Registration time"]].filter(([k]) => !get(d, k)),
    2: d => [["offence.category", "Offence category"], ["offence.title", "Case title"]].filter(([k]) => !get(d, k)),
    3: d => [["occurrence.from", "Occurred from"], ["occurrence.place", "Place"]].filter(([k]) => !get(d, k)),
    4: d => [["complainant.name", "Complainant name"]].filter(([k]) => !get(d, k)),
    5: d => d.accused.length ? d.accused.map((a, i) => !a.unknown && !a.name ? [`accused.${i}.name`, `Accused #${i + 1} name`] : null).filter(Boolean) : [["", "Add at least one accused (or 'Unknown person(s)')"]],
    6: d => d.others.map((x, i) => !x.name ? [`others.${i}.name`, `Name of person #${i + 1}`] : null).filter(Boolean),
    8: d => (d.narrative || "").trim().length < 40 ? [["narrative", "The statement (a few sentences)"]] : [],
    9: d => [["officer.name", "Investigating officer"]].filter(([k]) => !get(d, k)),
  };
  async function render() {
    if (!ov) return;
    const o = await options().catch(() => ({}));
    syncTxt(S.draft);
    const errs = {};
    for (let i = 1; i <= 9; i++) errs[i] = (REQ[i] ? REQ[i](S.draft) : []).length;
    ov.querySelector(".kri-rail").innerHTML = FSTEPS.map((s, i) => `<button type="button" class="kri-step ${i + 1 === step ? "on" : ""} ${i + 1 < step && !errs[i + 1] ? "done" : ""}" data-step="${i + 1}">
      <b>${i + 1 < step && !errs[i + 1] ? "✓" : i + 1}</b><span>${esc(s.t)}<small>${esc(s.s)}</small></span></button>`).join("");
    ov.querySelector(".kri-head").innerHTML = `<small>STEP ${step} OF 10</small><h3>${esc(FSTEPS[step - 1].t)}</h3><p>${esc(FSTEPS[step - 1].s)}</p><div class="kri-bar"><i style="width:${step * 10}%"></i></div>`;
    const body = ov.querySelector(".kri-body");
    body.innerHTML = `<div class="kri-grid">${stepHTML(o)}</div>
      <datalist id="kri-stations">${(o.stations || []).map(s => `<option value="${esc(s.name)}">${esc(s.district)}</option>`).join("")}</datalist>
      <datalist id="kri-districts">${(o.districts || []).map(s => `<option value="${esc(s.name)}">`).join("")}</datalist>
      <datalist id="kri-cats">${(o.categories || []).map(s => `<option value="${esc(s.name)}">`).join("")}</datalist>
      <datalist id="kri-places">${(o.places || []).map(s => `<option value="${esc(s.name)}">`).join("")}</datalist>`;
    body.scrollTop = 0;
    ov.querySelector(".kri-prev").disabled = step === 1;
    const nx = ov.querySelector(".kri-next");
    nx.textContent = step === 9 ? "Review →" : step === 10 ? "Register case" : "Next →";
    nx.classList.toggle("go2", step === 10);
    ov.querySelector(".kri-msg").innerHTML = "";
    if (step === 10) review();
    const first = body.querySelector("input,select,textarea"); if (first && matchMedia("(hover:hover)").matches) first.focus({ preventScroll: true });
  }
  async function review() {
    const box = ov.querySelector("#kri-review");
    const r = await api("/intake/check", { method: "POST", body: JSON.stringify(payload(S.draft, "form")) }, 60000).catch(() => null);
    if (!r || !r.ok) { box.innerHTML = `<div class="kri-box bad">Couldn't run the checks — is the backend running?</div>`; return; }
    S.review = r.data; save();
    const d = S.draft;
    box.innerHTML = `<div class="kri-q">This becomes <b>${esc(r.data.caseIdPreview)}</b>.</div>${summaryHTML(d)}` + checkHTML(d, r.data, null) +
      (r.data.matches.length ? `<div class="kri-box"><b>Your decision</b>${r.data.matches.map(m => { const e = entryOf(d, m.ref) || {};
        return `<div class="kri-dec"><div>${esc(refLabel(d, m.ref))}</div>${m.candidates.map(x => `<label><input type="radio" name="dec-${m.ref}" value="${esc(x.personId)}" data-ref="${m.ref}" ${e.linkTo === x.personId ? "checked" : ""}> Same person as <b>${esc(x.personId)}</b> ${esc(x.name)}</label>`).join("")}
          <label><input type="radio" name="dec-${m.ref}" value="" data-ref="${m.ref}" ${!e.linkTo ? "checked" : ""}> Keep as a new record</label></div>`; }).join("")}</div>` : "");
    ov.querySelector(".kri-next").disabled = !r.data.ok;
  }
  function onInput(e) {
    const el = e.target, k = el.dataset && el.dataset.k;
    if (!k) return;
    const v = el.type === "checkbox" ? el.checked : el.value;
    set(S.draft, k, v);
    if (k === "registration.firNumber") S.draft.registration._firAuto = false;
    save();
    if (e.type !== "change") return;
    const d = S.draft;
    if (k === "registration.policeStation") applyStation(d, v).then(() => { save(); render(); });
    else if (k === "registration.registeredAt") refreshFir(d).then(() => { save(); render(); });
    else if (k === "offence.category") options().then(o => { const c = o.categories.find(x => x.name === v); if (c && !d.offence.sections) d.offence.sections = c.sections; if (!d.offence.title) d.offence.title = suggestTitle(d); save(); render(); });
    else if (k === "occurrence.place") applyPlace(d, v).then(() => { save(); render(); });
    else if (k === "occurrence.from" || k === "occurrence.to") render();
    else if (k.endsWith(".phone") && v && parsePhone(v)) { set(d, k, parsePhone(v)); save(); el.value = parsePhone(v); }
  }
  function onClick(e) {
    if (!ov) return;
    const b = e.target.closest("button,input[type=radio]"); if (!b || !ov.contains(b)) return;
    const d = S.draft;
    if (b.dataset.step) { step = +b.dataset.step; render(); }
    else if (b.dataset.add) { if (b.dataset.add === "unknown") d.accused.push({ unknown: true }); else if (b.dataset.add === "accused") d.accused.push({ name: "", relation: "S/o", role: d.accused.some(a => a.role === "PRINCIPAL_ACCUSED") ? "ACCUSED" : "PRINCIPAL_ACCUSED" }); else d.others.push({ name: "", role: "WITNESS" }); save(); render(); }
    else if (b.dataset.del) { const [g, i] = b.dataset.del.split("."); d[g].splice(+i, 1); save(); render(); }
    else if (b.dataset.draft) { if (!d.narrative || confirm("Replace the current statement with a draft from the particulars?")) { d.narrative = draftNarrative(d); save(); render(); } }
    else if (b.type === "radio" && b.dataset.ref) { const en = entryOf(d, b.dataset.ref); if (en) { if (b.value) en.linkTo = b.value; else delete en.linkTo; save(); } }
    else if (b.classList.contains("kri-prev")) { if (step > 1) { step--; render(); } }
    else if (b.classList.contains("kri-next")) next();
    else if (b.classList.contains("kri-close")) close();
    else if (b.classList.contains("kri-chatbtn")) { close(); startChat("copilot", true); }
  }
  async function next() {
    if (busy) return;
    const miss = REQ[step] ? REQ[step](S.draft) : [];
    if (miss.length && step < 10) {
      ov.querySelector(".kri-msg").innerHTML = `<span class="kri-bad">Required: ${miss.map(m => esc(m[1])).join(", ")}</span>`;
      const f = miss[0][0] && ov.querySelector(`[data-k="${miss[0][0]}"]`); if (f) f.focus();
      return;
    }
    if (step < 10) { step++; render(); return; }
    busy = true;
    const nx = ov.querySelector(".kri-next"); nx.disabled = true; nx.innerHTML = `Registering… <span class="kri-spin"></span>`;
    ov.querySelector(".kri-body").innerHTML = `<div class="kri-proc">${["Hashing the original record (SHA-256)", "Writing the evidence-ledger block and Merkle anchor", "Recording roles and reading entities from the statement",
      "Checking identities against existing records", "Linking prior records (context only)", "Writing the case summary and search index"].map((t, i) => `<div style="--i:${i}"><span class="kri-spin"></span>${esc(t)}</div>`).join("")}</div>`;
    const r = await register(S.draft, "form").catch(e => ({ ok: false, data: { errors: [{ message: e.message }] } }));
    busy = false;
    if (!r.ok) { nx.disabled = false; nx.textContent = "Register case"; ov.querySelector(".kri-body").innerHTML = `<div class="kri-box bad"><b>Not registered</b>${((r.data || {}).errors || []).map(e => `<div>• ${esc(e.message)}</div>`).join("")}</div>`; return; }
    S = { draft: emptyDraft(), qi: 0, active: false, stack: [], review: null }; save();
    ov.querySelector(".kri-head").innerHTML = `<small>REGISTERED</small><h3>${esc(r.data.caseId)} is in KRONOS</h3><p>Processed like every other source — nothing was merged automatically.</p><div class="kri-bar"><i style="width:100%"></i></div>`;
    ov.querySelector(".kri-body").innerHTML = resultHTML(r.data);
    ov.querySelector(".kri-foot").innerHTML = `<button type="button" class="kri-btn ghost" onclick="KRintake.open(1)">Register another</button><span class="kri-msg"></span>
      <button type="button" class="kri-btn" onclick="KRintake.close();location.hash='#case/${esc(r.data.caseId)}'">Open case workspace →</button>`;
  }
  function open(at) {
    if (!live()) { if (typeof toast === "function") toast("Registering a case needs the live KRONOS backend"); return; }
    close(true);
    step = Math.min(Math.max(+at || 1, 1), 10);
    ov = document.createElement("div");
    ov.className = "kri-ov"; ov.setAttribute("role", "dialog"); ov.setAttribute("aria-modal", "true"); ov.setAttribute("aria-label", "Register a new case");
    ov.innerHTML = `<div class="kri-modal"><aside class="kri-side"><div class="kri-brand">KRONOS <span>CASE INTAKE</span></div><div class="kri-rail" role="navigation" aria-label="Intake steps"></div>
        <button type="button" class="kri-chatbtn">Prefer a conversation? Do it with the Copilot →</button></aside>
      <section class="kri-main"><button type="button" class="kri-close" aria-label="Close (your draft is kept)">✕</button><header class="kri-head"></header><div class="kri-body"></div>
        <footer class="kri-foot"><button type="button" class="kri-btn ghost kri-prev">← Back</button><span class="kri-msg"></span><button type="button" class="kri-btn kri-next">Next →</button></footer></section></div>`;
    document.body.append(ov);
    ov.addEventListener("input", onInput); ov.addEventListener("change", onInput); ov.addEventListener("click", onClick);
    ov.addEventListener("keydown", e => { if (e.key === "Escape") close(); });
    requestAnimationFrame(() => ov && ov.classList.add("in"));
    document.getElementById("copilot-panel")?.classList.remove("open");
    render();
  }
  function close(now) {
    if (!ov) return;
    const o = ov; ov = null;
    if (now) { o.remove(); return; }
    o.classList.remove("in"); setTimeout(() => o.remove(), 300);
  }

  /* ------------------------------------------------------------------ entry points */
  function say(ch, text) { const s = (window._krSend || {})[ch]; if (s) s(text); }
  function startChat(ch, fromForm) {
    if (ch === "copilot") {
      const panel = document.getElementById("copilot-panel"), btn = document.getElementById("copilot-btn");
      if (panel && !panel.classList.contains("open") && btn) btn.click();
      setTimeout(() => say("copilot", fromForm ? "continue the case intake" : "Register a new case"), 380);
      if (fromForm) { S.active = false; save(); }
    } else say("home", "Register a new case");
  }
  function homeSection() {
    return `<div class="blk ki-blk"><small class="no">05 CASE INTAKE</small>
      <h2>Register a case — by <em>form</em> or by <em>conversation</em>.</h2>
      <p class="lead">Ten steps cover every FIR particular. Before anything is saved, KRONOS checks whether the people are already on record and whether
        the phones, accounts or vehicles appear in other cases. On registration the FIR is hashed onto the evidence ledger and runs through the same engines as every other record.</p>
      <ol class="ki-steps">${FSTEPS.map((s, i) => `<li style="--i:${i}"><b>${pad(i + 1)}</b><span>${esc(s.t)}</span></li>`).join("")}</ol>
      <div class="ctas"><button class="btn p" type="button" onclick="KRintake.open(1)">REGISTER A NEW CASE →</button>
        <button class="btn" type="button" onclick="KRintake.startChat('home')">DO IT WITH THE ASSISTANT</button></div>
      <p class="ki-small">Or ask the Copilot anywhere: <i>"add a new case"</i>. Sexual offences, POCSO, juvenile, kidnapping, matrimonial and SC/ST cases are handled in a restricted module.</p></div>`;
  }
  function scan() {
    const v = document.querySelector(".view.hero");
    if (v && !v.querySelector("#ki")) {
      const after = v.querySelector("#kt") || v.querySelector(".story");
      if (after) { const sec = document.createElement("section"); sec.id = "ki"; sec.className = "story ki"; sec.setAttribute("aria-label", "Case intake"); sec.innerHTML = homeSection(); after.after(sec); }
    }
    const pane = document.querySelector(".pane.c h3");
    if (pane && !pane.querySelector(".kri-new")) {
      const b = document.createElement("button"); b.type = "button"; b.className = "kri-new"; b.textContent = "+ New case"; b.onclick = () => open(1);
      pane.append(b);
    }
  }
  new MutationObserver(scan).observe(document.getElementById("app") || document.body, { childList: true, subtree: true });
  scan();

  window.KRintake = { wants, chat, say, open, close, startChat, get state() { return S; }, draftNarrative, parseDT };
})();
