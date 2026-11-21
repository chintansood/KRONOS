# Frontend inventory and integration map

**The website that is actually served is `kronos-app/index.html`**, a single-file vanilla-JS app (about 500 KB, with GSAP and Three.js). The React/TypeScript code in `kronos-app/src/` is an earlier version that `index.html` never loads, so it was left untouched.

## How the integration works
- A new file, `kronos-app/public/kronos-live.js`, is loaded before the main script. On start-up it calls `GET /api/health`. If that succeeds, it fills the app's existing data arrays (`CASES`, `PERS`, `EVT`, `GRAPH_NODES`, `GRAPH_EDGES`) from the API and wraps the view functions (`profV`, `caseV`, `graphV`) to lazy-load data. If it fails, nothing changes and the original offline demo runs.
- `index.html` received about 60 lines of targeted edits. Each keeps the original code as the offline path:
  1. The first `route()` waits for `KR.ready`.
  2. Both evidence drawers lazy-load records that aren't in memory and show a provenance badge with a "Verify integrity" button for backend records.
  3. The dossier, home and Copilot chats call `POST /api/assistant/query` when live. Copilot navigation commands stay local.
  4. The suggestion chips are now generic when live.
  5. The notifications drawer reads `GET /api/alerts`.
  6. In live mode, the graph detail card's "Classified in criminal syndicate topology" becomes neutral wording.
  7. In live mode the dossier column scrolls vertically, the same rule the app already applies on small screens, so the added boxes never hide the original buttons.
- `vite.config.ts`: added the `/api` proxy to `http://127.0.0.1:8000`.
- The visual design is unchanged. All generated markup reuses the app's existing classes, CSS variables and inline-style patterns. See `screenshots/before` and `screenshots/after`.

## Feature map

| UI feature | Shows | Data source before | Backend source now | Endpoint |
|---|---|---|---|---|
| Dashboard metrics, case list, person list | Counts, filters, sorting | Embedded `CASES` / `PERS` | Case and person aggregation over all 5 sources plus recorded roles | `GET /api/cases`, `/api/persons` |
| Dossier header and facts | Identifiers, first/last activity, case chips | Embedded | Person registry | `GET /api/persons/{id}` |
| Dossier timeline, filters, replay | Chronological records with anomaly markers | Embedded `EVT` (17 events) | Temporal engine (timeline plus travel, financial, burst and co-location flags) | `GET /api/persons/{id}/timeline` |
| Dossier "Next best evidence" panel | One recommendation | Hard-coded | Next-best-evidence engine | `GET /api/cases/{id}/next-evidence` |
| Identity review box (new, in the panel's style) | Candidate, score, reasons, contradictions, Confirm/Reject/Defer | — | Identity resolution | `GET /api/persons/{id}/identity-candidates`, `POST /api/identity/candidates/{id}/review` |
| Travel-feasibility line (new, dossier) | Location pairs checked, plausible / needs air travel / impossible | — | Temporal engine (Haversine, accuracy-aware) | `GET /api/persons/{id}/feasibility` |
| Criminal-history linkage box (new, dossier) | Linked prior records (band, disposition, reasons, contradictions, Confirm/Reject link), records via possible identity, network-associated cases | — | Criminal-history linkage engine | `GET /api/persons/{id}/history`, `POST /api/history/links/{id}/review` |
| Case workspace, tab 1 | Summary, people, financial, communication, location, observations, gaps, chronology | Hand-written text | Case summary (JSON) and case intelligence | `GET /api/cases/{id}/summary`, `?llm=true` for the LLM narrative |
| Case workspace, tab 2 | Priority, hypotheses (both sides) with evidential balance and completeness, prior records as unscored context, next-best-evidence with value score breakdown and editable status | Hard-coded hypotheses | Priority, hypothesis and next-best-evidence engines | `/priority`, `/hypotheses`, `/next-evidence` (PATCH status) |
| Case workspace, tab 3 | Evidence list and ledger verification | Embedded | Evidence store and ledger | `GET /api/cases/{id}/evidence`, `GET /api/ledger/verify` |
| Case workspace, tab 4 | Live panel (new): federated results per agency node, global vs centralised model, "run" button; ledger chain status and per-file Merkle anchors with 3-of-4 signature quorum. Below it, the original static text, unchanged. | Static | Federated simulation and ledger | `GET /api/federated/report`, `POST /api/federated/run`, `GET /api/ledger/status` |
| Evidence drawer | Record, provenance, integrity check, Merkle inclusion proof with agency signatures, chain of custody | Embedded | Events, raw records and ledger (access is logged) | `GET /api/evidence/{id}`, `POST /api/evidence/{id}/verify`, `GET /api/evidence/{id}/proof`, `GET /api/evidence/{id}/history` |
| 3D network graph | Ego network | Embedded 18 nodes | Heterogeneous graph subgraph | `GET /api/graph/subgraph?focus=` |
| Dossier, home and Copilot chats | Answers | Keyword rules | LLM layer (retrieval, engines, Llama 3.1, citation and grounding checks) | `POST /api/assistant/query` |
| Notifications | Alerts | Last 5 embedded events | Travel, identity, financial and co-presence flags | `GET /api/alerts` |
| Export timeline / summary | Download | Client-side | Client-side, plus server TXT summary | `GET /api/cases/{id}/summary.txt` |
| Case tab 3 evidence search (new) | Natural-language evidence search with interpretation and "why matched" | — | Evidence retrieval engine | `GET /api/search/evidence?q=&caseId=` |
| Case tab 5 (new): case diary and draft report | Draft diary by day (BNSS s.192 sections), add-entry form, links to the printable draft report and diary in the selected language | — | Diary and report generators | `GET /api/cases/{id}/diary`, `POST /api/cases/{id}/diary/entries`, `GET /api/cases/{id}/report.html?lang=`, `GET /api/cases/{id}/diary.html?lang=` |
| Language setting (Punjabi added) and all chats | Chats send conversation history and language; translated answers include the verified English | Copilot-only canned multilingual | Multilingual layer | `POST /api/assistant/query` (`history`, `lang`) |

Other endpoints, not yet surfaced in the UI: `/api/ledger/verify`, `/api/graph/path`, `/graph/metrics`, `/graph/cross-case`, `/graph/hidden-links`, `/graph/gnn`, `/persons/{id}/routine`, `/persons/{id}/travel`, `/persons/{id}/financial`, `/cases/{id}/financial`, `/cases/{id}/intelligence`, `/federated/report`, `POST /federated/run`, `/ingestion/report`, `/search`, `/stats`, and `POST/PUT /api/cases`. Interactive docs are at `http://localhost:8000/docs`.

## Premium interface layer

`kronos-app/public/kronos-premium.css` and `kronos-app/public/kronos-premium.js` are loaded after the original page and
`kronos-live.js`. They refine the existing design without changing its layout, palette, typography or illustrations.

| Area | Change |
|---|---|
| Buttons | One system for the whole app: pill shape, terra-gradient primary with a light sweep, glass-outline secondary that fills with espresso on hover, a gentle magnetic pull toward the cursor, and press feedback. Before this, there was no base `.btn` style at all, so story-section buttons showed browser defaults. |
| 3D (three.js) | Hero layer: three thin gold armillary rings, beads travelling along the inner orbit, 900 evidence particles orbiting the hourglass and slowly rising dust, with mouse-parallax camera. It pauses when off-screen or when the tab is hidden, and is disposed on navigation. |
| Motion | First-load preloader (dial wordmark, gold progress line, counter); a page-turn curtain on every view change; dashboard numbers count up; cards tilt slightly in 3D and show a cursor-following sheen. |
| Details | Animated nav underline; glass nav and icon buttons; colour-coded priority and status tags; styled inputs and dropdowns with a focus ring; thin gold scrollbars; a warm selection colour; a cursor halo on mouse devices (the native cursor is kept). |
| Fixes | Hero side labels were clipped off-screen. "SCROLL" sat under the chat bar. The hero intro took about 5 s (now about 3 s). An invisible reveal layer blocked the home chat's suggestions button. A JS error was thrown when leaving a dossier. The case header card was transparent (undefined `--parchment`). The case header repeated the police station. The demo-only person link (P-0427) now goes to a real person or the network graph. Mobile: the dashboard panels overflowed, and Copilot covered the chat input. |
| Home chat | Navigation requests such as "explore the intelligence network", "open CASE905" or "open case 12" now run instantly through the same command router as Copilot, with no LLM wait; "explore" and "visit" are recognised verbs. Real questions still go to the assistant. The chat panel starts collapsed on each visit, opens when you use it, closes on Esc or a click outside, and the hero buttons step aside while it is open, so it never covers them. Pseudonym labels such as "Accused A1 · CASE905" no longer make case commands ambiguous. |
| Accessibility | `prefers-reduced-motion` disables the preloader, curtain, cursor halo and all transitions. Touch devices get no cursor effects. Focus rings stay visible. |

**Interaction test:** a browser test (Playwright with the installed Chrome) clicks every important control and checks its specific outcome. It covers the nav, hero, story buttons, home chat, Copilot (button, ⌘K, a typed command), dashboard filters, rows and chips, all five case tabs, evidence drawers, downloads, the dossier's replay, bookmark, export, graph drawer and chips, and the 3D graph.

Screenshots are in `docs/screenshots/after/premium_*.png`.

## Temporal Engine on the home page

The home page has a "04 TEMPORAL ENGINE" section (`kronos-app/public/kronos-temporal.js` and `.css`), so the temporal engine can be used without opening a dossier.

| Part | What it does |
|---|---|
| Person picker | Search by name or ID. Suggestions come from the new `GET /api/temporal/highlights`: people with travel-feasibility flags first (impossible, then needs a flight), then the most active subjects. |
| Time river | Every record placed in time on five lanes: location, calls, messages, money, case records. Anomalies are ringed. Hover shows the record; click or drag the playhead; ← → keys step through records. |
| Travel flags | Pins above the river label each flag with its implied speed. Arcs join the two records. Clicking a flag zooms to that day so the journey is visible. |
| Zoom | Whole span, 30, 7 or 1 day, centred on the playhead and following it during replay. |
| Replay | Sweeps the whole record span in about 22 s at 1× (2× and 4× available), lighting each record as it passes. The day's routine loads only after the playhead settles, so replay doesn't flood the API. |
| Cards | **At the playhead:** the record, its place, its case and an evidence button that opens the evidence drawer. **Travel feasibility:** moves checked, plausible, needs a flight, impossible, plus the flags. **Day routine:** the day's records and gaps, with ‹ › to step through days. |
| Actions | "Open full dossier →", and "Ask KRONOS about this timeline", which sends the question to Copilot. |

The section loads only when it scrolls near the screen, so the hero stays fast. In offline mode it shows a notice instead.
