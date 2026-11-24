/* KRONOS online prototype (static hosting such as GitHub Pages).
   Answers the website's API calls from a read-only snapshot made by backend/scripts/make_prototype.py, instead of the
   live backend. Active only when window.KRONOS_STATIC is set (the prototype build injects it).
   - Every case, dossier, time river, graph, hypothesis and report comes from the snapshot.
   - Evidence ledger: the Merkle inclusion proof is recomputed here (SHA-256) from the records' hashes, and the agencies'
     Ed25519 signatures on the anchored root are checked with Web Crypto.
   - Evidence search runs as a keyword search in the browser.
   - The local AI and case registration need the full install; where they are used, the prototype says so. */
(() => {
  "use strict";
  const CFG = window.KRONOS_STATIC;
  if (!CFG) return;
  const BASE = CFG.base || "snapshot/";
  const REPO = CFG.repo || "https://github.com/chintansood/KRONOS";
  const READ_ONLY = "Read-only online prototype: install KRONOS from GitHub to do this.";
  const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---- snapshot files (cached; a failed load can be retried)
  const cache = new Map();
  function file(f) {
    if (!cache.has(f)) cache.set(f, fetch(BASE + f).then(r => {
      if (!r.ok) throw new Error(`${f} is not in the prototype snapshot (HTTP ${r.status})`);
      return f.endsWith(".json") ? r.json() : r.text();
    }).catch(e => { cache.delete(f); throw e; }));
    return cache.get(f);
  }
  // same rule as make_prototype.py: '/cases/CASE002/hypotheses?personId=P00019' → 'cases/CASE002/hypotheses__personId_P00019.json'
  const key = path => { const [p, q = ""] = path.replace(/^\/+/, "").split("?"); const s = q.replace(/[^A-Za-z0-9._-]/g, "_"); return `${p}${s ? "__" + s : ""}.json`; };
  const params = path => new URLSearchParams(path.split("?")[1] || "");

  async function get(path, opt = {}) {
    const method = (opt.method || "GET").toUpperCase();
    const p = path.split("?")[0];
    let m;
    if (method === "POST" && p === "/assistant/query") return answer(JSON.parse(opt.body || "{}"));
    if (method === "POST" && (m = p.match(/^\/evidence\/([^/]+)\/verify$/))) return verify(decodeURIComponent(m[1]));
    if (method !== "GET") throw new Error(READ_ONLY);
    if ((m = p.match(/^\/persons\/([^/]+)\/timeline$/))) {
      const t = await file(`persons/${m[1]}/timeline.json`), n = +params(path).get("limit") || 0;
      return n && n < t.length ? t.slice(0, n) : t;
    }
    if ((m = p.match(/^\/persons\/([^/]+)\/routine$/))) return routine(m[1], params(path).get("date"));
    if ((m = p.match(/^\/evidence\/([^/]+)\/proof$/))) return proof(decodeURIComponent(m[1]));
    if ((m = p.match(/^\/evidence\/([^/]+)\/history$/))) return history(decodeURIComponent(m[1]));
    if ((m = p.match(/^\/evidence\/([^/]+)$/))) return evidence(decodeURIComponent(m[1]));
    if (p === "/search/evidence") return search(params(path));
    if (p === "/intake/next-fir" || p === "/search") throw new Error(READ_ONLY);
    return file(key(path));
  }
  // the intake form's helper expects {ok, status, data}
  const api = (path, opt) => get(path, opt).then(data => ({ ok: true, status: 200, data }),
    e => ({ ok: false, status: 503, data: { detail: String(e.message || e) } }));

  // ---- day routine (one file per person)
  async function routine(pid, date) {
    const R = await file(`persons/${pid}/routine.json`);
    const d = date || R.defaultDate;
    if (!d) return { personId: pid, date: null, ...(R.empty || { entries: [], gaps: [] }) };
    return { personId: pid, date: d, recordCount: 0, entries: [], gaps: [], ...(R.days[d] || {}), availableDates: R.availableDates };
  }

  // ---- an exhibit opened from anywhere: find its case, then the record
  async function evidence(eid) {
    const idx = await file(`evidence/index/${eid.slice(-2)}.json`);
    const cid = idx[eid];
    if (!cid) throw new Error(`${eid} is not in the prototype snapshot`);
    const e = (await file(`cases/${cid}/evidence.json`)).find(x => x.evidenceId === eid);
    if (!e) throw new Error(`${eid} is not in the prototype snapshot`);
    return e;
  }

  // ---- evidence search: keywords (and "above 40,000") over the open case, in the browser
  const STOP = new Set("the a an of for to in on at by with and or from show find list me all any records record evidence events event this case about which who what when where how is are was were".split(" "));
  async function search(q) {
    const text = (q.get("q") || "").toLowerCase(), cid = q.get("caseId"), limit = +q.get("limit") || 60;
    const evs = cid ? await file(`cases/${cid}/evidence.json`) : [];
    const am = text.match(/(?:above|over|more than|greater than|exceeding|>)\s*(?:rs\.?|₹|inr)?\s*([\d,]+)/);
    const min = am ? +am[1].replace(/,/g, "") : null;
    const words = text.replace(/(?:above|over|more than|greater than|exceeding|>)\s*(?:rs\.?|₹|inr)?\s*[\d,]+/, " ").split(/[^a-z0-9ऀ-෿]+/)
      .filter(w => w.length > 2 && !STOP.has(w)).map(w => w.replace(/(ies)$/, "y").replace(/(es|s)$/, ""));
    const amountOf = e => { const m = e.metadata || {}; const v = m.amount ?? m.amountInr ?? m.amount_inr ?? m.value; return v == null ? null : +v; };
    const results = [];
    for (const e of evs) {
      const hay = `${e.description || ""} ${e.locationName || ""} ${e.modality || ""} ${JSON.stringify(e.metadata || {})}`.toLowerCase();
      const hit = words.filter(w => hay.includes(w));
      if (words.length && !hit.length) continue;
      if (min != null) { const a = amountOf(e); if (a == null || a <= min) continue; }
      if (!words.length && min == null) continue;
      const why = [...(hit.length ? [`keywords: ${hit.join(", ")}`] : []), ...(min != null ? [`amount above ₹${min.toLocaleString("en-IN")}`] : [])];
      results.push({ score: hit.length, r: { evidenceId: e.evidenceId, modality: e.modality, caseId: e.caseId, timestamp: e.timestamp || e.iso, description: e.description, whyMatched: why } });
    }
    results.sort((a, b) => b.score - a.score);
    return { interpretation: { explain: [`keyword search in ${cid} (online prototype; the full install also uses vector search across every case)`, ...(min != null ? [`amount > ₹${min.toLocaleString("en-IN")}`] : [])], keywords: words },
      total: results.length, results: results.slice(0, limit).map(x => x.r) };
  }

  // ---- evidence ledger, verified in the browser
  const K = new Uint32Array([0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d,
    0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
    0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);
  const W = new Uint32Array(64);
  function sha256(msg) {                 // synchronous SHA-256 (tens of thousands of small hashes per proof)
    const l = msg.length, nb = ((l + 9 + 63) >> 6) << 6, m = new Uint8Array(nb);
    m.set(msg); m[l] = 0x80;
    const dv = new DataView(m.buffer);
    dv.setUint32(nb - 4, (l * 8) >>> 0); dv.setUint32(nb - 8, Math.floor(l / 0x20000000));
    let h0 = 0x6a09e667, h1 = 0xbb67ae85, h2 = 0x3c6ef372, h3 = 0xa54ff53a, h4 = 0x510e527f, h5 = 0x9b05688c, h6 = 0x1f83d9ab, h7 = 0x5be0cd19;
    for (let o = 0; o < nb; o += 64) {
      for (let i = 0; i < 16; i++) W[i] = dv.getUint32(o + i * 4);
      for (let i = 16; i < 64; i++) {
        const x = W[i - 15], y = W[i - 2];
        W[i] = (W[i - 16] + ((x >>> 7 | x << 25) ^ (x >>> 18 | x << 14) ^ (x >>> 3)) + W[i - 7] + ((y >>> 17 | y << 15) ^ (y >>> 19 | y << 13) ^ (y >>> 10))) | 0;
      }
      let a = h0, b = h1, c = h2, d = h3, e = h4, f = h5, g = h6, h = h7;
      for (let i = 0; i < 64; i++) {
        const t1 = (h + ((e >>> 6 | e << 26) ^ (e >>> 11 | e << 21) ^ (e >>> 25 | e << 7)) + ((e & f) ^ (~e & g)) + K[i] + W[i]) | 0;
        const t2 = (((a >>> 2 | a << 30) ^ (a >>> 13 | a << 19) ^ (a >>> 22 | a << 10)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      h0 = (h0 + a) | 0; h1 = (h1 + b) | 0; h2 = (h2 + c) | 0; h3 = (h3 + d) | 0; h4 = (h4 + e) | 0; h5 = (h5 + f) | 0; h6 = (h6 + g) | 0; h7 = (h7 + h) | 0;
    }
    const out = new Uint8Array(32), ov = new DataView(out.buffer);
    [h0, h1, h2, h3, h4, h5, h6, h7].forEach((x, i) => ov.setUint32(i * 4, x >>> 0));
    return out;
  }
  const fromHex = h => { const b = new Uint8Array(h.length / 2); for (let i = 0; i < b.length; i++) b[i] = parseInt(h.substr(i * 2, 2), 16); return b; };
  const toHex = b => Array.from(b, x => x.toString(16).padStart(2, "0")).join("");
  const join = (tag, ...parts) => { const n = parts.reduce((s, p) => s + p.length, 1), o = new Uint8Array(n); o[0] = tag; let k = 1; parts.forEach(p => { o.set(p, k); k += p.length; }); return o; };
  const leaf = hex => sha256(join(0x00, fromHex(hex)));
  const parent = (l, r) => sha256(join(0x01, l, r));

  async function locate(eid) {
    const B = await file("provenance/batches.json");
    const sid = eid.replace(/^EVD-/, "SRC-");
    const b = B.batches.find(x => sid.startsWith(x.prefix) && /^\d+$/.test(sid.slice(x.prefix.length)));
    if (!b) return null;
    const L = await file(`provenance/${b.n}.json`);
    const i = L.ids ? L.ids.indexOf(sid) : +sid.slice(b.prefix.length) - 1;
    return i >= 0 && i < L.leaves.length ? { B, b, L, i, sid } : null;
  }
  function levels(L) {                   // the whole tree, once per batch
    if (L._lv) return L._lv;
    const lv = [L.leaves.map(leaf)];
    while (lv[lv.length - 1].length > 1) {
      let cur = lv[lv.length - 1];
      if (cur.length % 2) cur = cur.concat([cur[cur.length - 1]]);
      const nxt = [];
      for (let k = 0; k < cur.length; k += 2) nxt.push(parent(cur[k], cur[k + 1]));
      lv.push(nxt);
    }
    return (L._lv = lv);
  }
  async function signatures(B, b) {      // Ed25519 with Web Crypto; falls back to the result recorded in the snapshot
    if (b._sig) return b._sig;
    const payload = new TextEncoder().encode(`KRONOS-ANCHOR|${b.runId}|${b.file}|${b.records}|${b.merkleRoot}`);
    const sigs = {}; let here = true;
    for (const [n, pub] of Object.entries(B.nodes)) {
      try {
        const k = await crypto.subtle.importKey("raw", fromHex(pub), { name: "Ed25519" }, false, ["verify"]);
        sigs[n] = await crypto.subtle.verify({ name: "Ed25519" }, k, fromHex(b.signatures[n] || ""), payload);
      } catch (e) { here = false; sigs[n] = !!(b.sigOkAtSnapshot || {})[n]; }
    }
    return (b._sig = { sigs, here });
  }
  const quorum = B => +(String(B.quorum || "3").split("-")[0]) || 3;
  async function proof(eid) {
    const x = await locate(eid);
    if (!x) return { evidenceId: eid, result: "NOT_ANCHORED" };
    const { B, b, L, i } = x, lv = levels(L);
    const path = []; let k = i;
    for (const lvl of lv.slice(0, -1)) {
      const row = lvl.length % 2 ? lvl.concat([lvl[lvl.length - 1]]) : lvl, sib = k ^ 1;
      path.push({ position: sib < k ? "left" : "right", hash: toHex(row[sib]) });
      k >>= 1;
    }
    let h = leaf(L.leaves[i]);           // walk the path independently, as the backend does
    for (const s of path) h = s.position === "left" ? parent(fromHex(s.hash), h) : parent(h, fromHex(s.hash));
    const { sigs, here } = await signatures(B, b);
    const ok = toHex(h) === b.merkleRoot, q = Object.values(sigs).filter(Boolean).length >= quorum(B);
    return { evidenceId: eid, sourceRecordId: x.sid, file: b.file, leafHash: L.leaves[i], path, computedRoot: toHex(h), anchoredRoot: b.merkleRoot,
      anchorBlock: b.anchorBlock, batchRecords: b.records, signatures: sigs, quorumMet: q, result: ok && q ? "INCLUDED" : "PROOF_FAILED",
      note: `Recomputed in your browser from the ${b.records} record hashes of this batch${here ? "; agency signatures checked with Web Crypto (Ed25519)" : "; this browser cannot check Ed25519, so the signature results recorded in the snapshot are shown"}. ` +
        "Proves the record is unchanged since it was anchored. It does not establish the authenticity or lawful collection of the original evidence." };
  }
  async function verify(eid) {
    const x = await locate(eid);
    if (!x) return { evidenceId: eid, result: "NOT_ON_LEDGER" };
    const p = await proof(eid);
    return { evidenceId: eid, sourceRecordId: x.sid, algorithm: "SHA-256", recomputedHash: x.L.leaves[x.i], recordedHash: x.L.leaves[x.i],
      ledgerBlock: x.L.blocks[x.i], recordedAt: x.L.ms[x.i] == null ? null : new Date(Date.parse(x.b.t0) + x.L.ms[x.i]).toISOString(),
      blockIntegrity: true, result: p.result === "INCLUDED" ? "VERIFIED" : "MISMATCH",
      note: "Online prototype: the hash recorded at ingestion was checked in your browser against the Merkle root that the agencies signed. " +
        "In the full install the record itself is re-hashed from storage. Integrity does not establish authenticity or lawful collection." };
  }
  async function history(eid) {
    const x = await locate(eid);
    if (!x) return [];
    const { b, L, i } = x, ts = L.ms[i] == null ? b.t0 : new Date(Date.parse(b.t0) + L.ms[i]).toISOString();
    return [{ block: L.blocks[i], ts, eventType: "INGEST", actor: "ingestion", contentHash: L.leaves[i], metadata: { file: b.file, run_id: b.runId, source_record_id: x.sid } },
            { block: b.anchorBlock, ts: b.anchorTs, eventType: "ANCHOR", actor: "consortium", contentHash: b.merkleRoot,
              metadata: { result: `Merkle root of ${b.records} records, signed by the agencies` } }];
  }

  // ---- the AI assistant is not available here
  async function answer(body) {
    const text = "**The local AI does not run in this online prototype.** KRONOS answers questions with Llama 3.1 8B on the investigator's own machine, so no case data goes to a cloud service; a static website cannot run it.\n\n" +
      "Here you can still use every engine's results: hypotheses with alternates, next best evidence, the temporal engine, identity matching, the network graph and the evidence ledger. " +
      "Navigation commands work too, for example “open CASE002”, “open temporal engine for P00024” or “show evidence of cash deposits above 40,000”.\n\n" +
      `To ask questions like this one, install KRONOS from GitHub (${REPO}) — about 15 minutes with one command — or watch the demo video, which shows the AI answering: https://youtu.be/o1BP-umvR6c`;
    return { text, referencedEvidenceIds: [], meta: { intents: ["prototype"], sources: ["online prototype"], evidenceItems: 0, evidenceCandidates: 0, batches: 0,
      model: "none (online prototype)", removedCitations: [], latencyMs: 0 } };
  }

  // ---- report, diary and summary links point at the snapshot copies
  document.addEventListener("click", e => {
    const a = e.target.closest && e.target.closest('a[href*="/api/"]');
    if (!a) return;
    const m = (a.getAttribute("href") || "").match(/\/api\/cases\/([^/?#]+)\/(report\.html|diary\.html|summary\.txt)/);
    if (m) a.setAttribute("href", `${BASE}cases/${m[1]}/${m[2]}`);
    else { e.preventDefault(); if (typeof toast === "function") toast(READ_ONLY); }
  }, true);

  // ---- a short notice on the first visit
  function notice() {
    let seen = false; try { seen = localStorage.getItem("kr_proto_seen") === "1"; } catch (e) { /* ignore */ }
    if (seen) return;
    const s = document.createElement("style");
    s.textContent = `.kr-proto{position:fixed;z-index:65;top:74px;right:14px;width:min(360px,calc(100vw - 28px));background:#FAF5EC;border:1px solid rgba(198,154,85,.45);border-radius:16px;
      padding:14px 16px;font:13px/1.5 var(--sans,Inter,sans-serif);color:#30251F;box-shadow:0 24px 50px -24px rgba(48,37,31,.5)}
      .kr-proto b{font-family:var(--mono,monospace);font-size:10.5px;letter-spacing:.18em;color:#B96D50;display:block;margin-bottom:4px}
      .kr-proto a{color:#B96D50;font-weight:600}.kr-proto button{position:absolute;top:8px;right:10px;border:0;background:none;font-size:18px;color:#8a7a6c;cursor:pointer}`;
    document.head.append(s);
    const d = document.createElement("div");
    d.className = "kr-proto"; d.setAttribute("role", "status");
    d.innerHTML = `<button type="button" aria-label="Close">×</button><b>ONLINE PROTOTYPE</b>A read-only snapshot of KRONOS with its real data: every case, dossier, hypothesis, time river, graph and ledger proof.
      The local AI and case registration run in the <a href="${esc(REPO)}" target="_blank" rel="noopener">full install</a>.`;
    d.querySelector("button").onclick = () => { d.remove(); try { localStorage.setItem("kr_proto_seen", "1"); } catch (e) { /* ignore */ } };
    document.body.append(d);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", notice); else notice();

  window.KRstatic = { get, api, file, key, sha256, toHex, fromHex, proof, verify, READ_ONLY, REPO, built: CFG.built };
})();
