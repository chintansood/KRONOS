// Browser smoke test of a running KRONOS (headless Chromium via Playwright).
//   cd ci && npm install --no-save playwright@1 && npx playwright install --with-deps chromium && node ui_smoke.js http://localhost:8000
// Opens every main view on desktop and phone sizes, uses the Copilot and the case-intake form, and fails on any JS error.
const { chromium } = require("playwright");
const BASE = (process.argv[2] || "http://localhost:8000").replace(/\/$/, "") + "/";
const results = [];
const check = async (name, fn) => {
  const t = Date.now();
  try { const note = await fn(); results.push([true, name]); console.log(`PASS  ${name.padEnd(46)} ${((Date.now() - t) / 1000).toFixed(1)}s  ${note || ""}`); }
  catch (e) {
    const msg = String(e.message || e).split("\n")[0].slice(0, 300);
    results.push([false, name]); console.log(`FAIL  ${name.padEnd(46)} ${((Date.now() - t) / 1000).toFixed(1)}s  ${msg}`);
    if (process.env.GITHUB_ACTIONS) console.log(`::error title=Browser check failed: ${name}::${msg.replace(/[\r\n%]/g, " ")}`);
  }
};
(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const page = async (w, h) => {
    const p = await (await browser.newContext({ viewport: { width: w, height: h }, isMobile: w < 800, hasTouch: w < 800 })).newPage();
    p.on("pageerror", e => errors.push(`${w}px: ${e.message.slice(0, 160)}`));
    return p;
  };
  const p = await page(1440, 900);
  const go = async (hash, sel, ms = 90000) => { await p.evaluate(h => { location.hash = h; }, hash); await p.waitForSelector(sel, { timeout: ms }); };
  await check("site loads and connects to the live backend", async () => {
    await p.goto(BASE, { waitUntil: "domcontentloaded" });
    await p.waitForFunction(() => window.KR && window.KR.live, null, { timeout: 120000 });
    return `${await p.evaluate(() => CASES.length)} cases`;
  });
  await check("home: hero, temporal engine, case-intake section", async () => {
    await p.waitForSelector("#kt", { timeout: 30000 }); await p.waitForSelector("#ki", { timeout: 30000 });
    await p.evaluate(() => document.querySelector("#kt").scrollIntoView()); await p.waitForSelector(".kt-chip", { timeout: 90000 });
  });
  await check("investigations dashboard", () => go("#dash", "#cl .row"));
  await check("case workspace (CASE002)", () => go("#case/CASE002", ".kr-case"));
  await check("hypotheses + alternates tab", async () => {
    await p.evaluate(() => { window._kr_cur_tab = "nbe"; window.setCaseTab("nbe"); });
    await p.waitForSelector(".kh .kh-alt", { timeout: 120000 });
    return `${await p.locator(".kh").count()} hypothesis cards`;
  });
  await check("evidence drawer + ledger verification", async () => {
    await p.evaluate(() => { window._kr_cur_tab = "summary"; window.setCaseTab("summary"); });
    await p.waitForSelector(".kr-case .ev2", { timeout: 60000 });
    await p.evaluate(() => document.querySelector(".kr-case .ev2").click());
    await p.waitForSelector(".dr button", { timeout: 30000 });
    await p.evaluate(() => [...document.querySelectorAll(".dr button")].find(b => /Verify integrity/.test(b.textContent)).click());
    await p.waitForFunction(() => /VERIFIED/.test((document.querySelector(".dr .kr-verify") || {}).innerText || ""), null, { timeout: 30000 });
    await p.evaluate(() => closeDr());
  });
  await check("dossier + identity + alternates (P00023)", async () => {
    try { await go("#p/P00023", ".kh-dossier .kh", 240000); }
    catch (e) {   // say what is on screen, so a failure on a remote machine can be diagnosed from the annotation
      const s = await p.evaluate(() => ({ dossier: !!document.querySelector(".dos"), slot: (document.querySelector(".kh-dossier") || {}).innerText || "no card slot",
        nbe: /NEXT BEST EVIDENCE TO EXAMINE/.test(document.body.innerText), hash: location.hash }));
      throw new Error(`${e.message.split("\n")[0]} · ${JSON.stringify(s).slice(0, 220)}`);
    }
  });
  await check("3D network graph", () => go("#graph/P00023", ".graph-view canvas", 120000));
  await check("header: temporal engine page", async () => {
    await p.evaluate(() => document.querySelector("nav a[data-n=temporal]").click());   // works whether the links or the menu are showing
    await p.waitForSelector(".kt-page .kt-dot", { timeout: 120000 });
    return await p.evaluate(() => location.hash);
  });
  await check("header: workspace menu opens the active case", async () => {
    await go("#p/P00023", ".dos", 240000);
    await p.click("#kr-ws"); await p.waitForSelector(".kr-wsp.open .kr-wsp-title", { timeout: 10000 });
    const cid = (await p.textContent("#kr-ws-c")).trim();
    if (!cid) throw new Error("no active case on the workspace button");
    await p.click(".kr-wsp [data-tab=nbe]");
    await p.waitForFunction(c => location.hash === `#case/${c}`, cid, { timeout: 20000 });
    return `active case ${cid}`;
  });
  await check("Copilot opens and runs a command", async () => {
    await p.click("#copilot-btn"); await p.fill("#c-input", "open investigations"); await p.click("#c-send-btn");
    await p.waitForFunction(() => location.hash === "#dash", null, { timeout: 20000 });
  });
  await check("Copilot guided case intake starts", async () => {
    await p.evaluate(() => localStorage.removeItem("kr_intake_v1"));
    if (!(await p.evaluate(() => document.getElementById("copilot-panel").classList.contains("open")))) await p.click("#copilot-btn");
    await p.fill("#c-input", "add a new case"); await p.click("#c-send-btn");
    await p.waitForFunction(() => /STEP 1 OF 10/.test(document.getElementById("c-stream").innerText), null, { timeout: 30000 });
    await p.fill("#c-input", "cancel"); await p.click("#c-send-btn");
  });
  await check("header NEW CASE opens the intake form", async () => {
    const at = await p.evaluate(() => { document.getElementById("copilot-panel").classList.remove("open"); document.querySelector('nav a[href="#new"]').click(); return location.hash; });
    await p.waitForSelector(".kri-modal [data-k='registration.policeStation']", { timeout: 30000 });
    if (await p.evaluate(() => location.hash) !== at) throw new Error("NEW CASE navigated away instead of opening the form in place");
    const n = await p.evaluate(() => document.querySelectorAll("#kri-stations option").length);
    if (!n) throw new Error("no stations in the form");
    await p.evaluate(() => KRintake.close(true));
    return `${n} stations`;
  });
  const m = await page(390, 844);
  await check("phone layout: menu + no sideways scrolling", async () => {
    await m.goto(BASE + "#case/CASE002", { waitUntil: "domcontentloaded" });
    await m.waitForFunction(() => window.KR && window.KR.live, null, { timeout: 120000 });
    await m.waitForSelector(".kr-case", { timeout: 90000 });
    if (!(await m.isVisible(".kr-burger"))) throw new Error("menu button not visible");
    const over = await m.evaluate(() => { const v = document.querySelector(".view"); return Math.max(document.documentElement.scrollWidth - innerWidth, v.scrollWidth - v.clientWidth); });
    if (over > 1) throw new Error(`content is ${over}px wider than the screen`);
  });
  await check("no JavaScript errors", async () => { if (errors.length) throw new Error(errors.slice(0, 3).join(" | ")); });
  // machines without WebGL (no GPU, VMs, remote desktops): the network graph must fall back to 2D, without errors
  const b2 = await chromium.launch({ args: ["--disable-webgl", "--disable-3d-apis"] });
  await check("network graph without WebGL (2D fallback)", async () => {
    const q = await (await b2.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
    const errs = []; q.on("pageerror", e => errs.push(e.message.slice(0, 160)));
    await q.goto(BASE + "#graph/P00023", { waitUntil: "domcontentloaded" });
    await q.waitForFunction(() => window.KR && window.KR.live, null, { timeout: 120000 });
    await q.waitForSelector(".graph-view canvas.g2d", { timeout: 60000 });
    if (errs.length) throw new Error(errs.join(" | "));
  });
  await b2.close();
  await browser.close();
  const bad = results.filter(r => !r[0]).length;
  console.log(`\n${results.length - bad}/${results.length} checks passed`);
  process.exit(bad ? 1 : 0);
})();
