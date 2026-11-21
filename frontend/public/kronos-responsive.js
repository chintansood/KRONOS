/* KRONOS — responsive helpers: mobile navigation menu and tab-strip positioning. */
(function () {
  "use strict";
  const nav = document.querySelector("nav"), rt = nav && nav.querySelector(".rt");
  if (!nav || !rt) return;

  // ---- mobile menu: the same links as the desktop bar (read at open time, so live-mode hrefs stay current)
  const btn = document.createElement("button");
  btn.className = "ib kr-burger"; btn.type = "button";
  btn.setAttribute("aria-label", "Menu"); btn.setAttribute("aria-expanded", "false"); btn.setAttribute("aria-controls", "kr-mnav");
  btn.innerHTML = "<i></i><i></i><i></i>";
  rt.prepend(btn);
  const sheet = document.createElement("div");
  sheet.className = "kr-mnav"; sheet.id = "kr-mnav"; sheet.setAttribute("role", "menu");
  const scrim = document.createElement("div");
  scrim.className = "kr-mscrim";
  document.body.append(scrim, sheet);

  function build() {
    const v = (location.hash.slice(1) || "home").split("/")[0];
    const links = [...nav.querySelectorAll(".links a")];
    const seen = new Set();
    sheet.innerHTML = links.filter(a => !seen.has(a.textContent) && seen.add(a.textContent)).map(a =>
      `<a role="menuitem" href="${a.getAttribute("href")}" class="${a.dataset.n === v ? "on" : ""}">${a.textContent}</a>`).join("") +
      (nav.querySelector(".demo") ? `<div class="kr-mstatus">${nav.querySelector(".demo").textContent}</div>` : "");
  }
  function open(on) {
    if (on) build();
    sheet.classList.toggle("open", on); scrim.classList.toggle("open", on);
    btn.setAttribute("aria-expanded", String(on));
    if (on) { const f = sheet.querySelector("a.on") || sheet.querySelector("a"); f && f.focus({ preventScroll: true }); }
  }
  btn.addEventListener("click", e => { e.stopPropagation(); open(!sheet.classList.contains("open")); });
  scrim.addEventListener("click", () => open(false));
  sheet.addEventListener("click", e => { if (e.target.closest("a")) open(false); });
  addEventListener("keydown", e => { if (e.key === "Escape" && sheet.classList.contains("open")) { open(false); btn.focus(); } });
  addEventListener("hashchange", () => open(false));
  matchMedia("(min-width:801px)").addEventListener("change", m => { if (m.matches) open(false); });

  // ---- case tabs on phones: keep the active tab in view inside the horizontal strip
  const app = document.getElementById("app");
  if (app) new MutationObserver(() => {
    const strip = app.querySelector(".kr-tabs");
    if (!strip || strip.scrollWidth <= strip.clientWidth) return;
    const act = [...strip.querySelectorAll("button")].find(b => /3px solid var\(--terra\)/.test(b.getAttribute("style") || ""));
    if (act && strip.dataset.pos !== act.textContent) {
      strip.dataset.pos = act.textContent;
      strip.scrollLeft = act.offsetLeft - strip.clientWidth / 2 + act.offsetWidth / 2;
    }
  }).observe(app, { childList: true, subtree: true });
})();
