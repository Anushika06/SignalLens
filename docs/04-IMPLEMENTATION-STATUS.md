# SignalLens — Implementation Status

The single honest record of what exists. **Built** means the code exists in this repository.
**Tested** means automated tests exercise it. **Verified live** means it was run against real
external services. As of 28 Sep 2026.

> **The one thing to know:** every part of the system is built and tested end to end, but
> the model-driven steps (planning, extraction, materiality, triage, investigation, impact
> analysis) have been exercised with a **scripted model**, not yet with a real model API,
> because no model or search API key was available while building. Adding one model key
> and one search key to `backend/.env` is the only step between this repository and a live
> run on real companies. The non-model parts (fetching, robots.txt, SSRF protection,
> extraction, the web-archive client, quality gate, diffing) **were** verified against live
> sites.

---

## 1. Summary

| Area | Built | Tested | Verified live |
|---|---|---|---|
| Onboarding → planner agent → plan with reasons + live source checks | ✅ | ✅ integration | ⏳ needs model + search keys |
| Human plan approval/edit → entities, facts, sources, jobs | ✅ | ✅ integration | — |
| Company Profile ("us") + teams | ✅ | ✅ integration | — |
| Baseline with quote-verified tracked values | ✅ | ✅ integration | ⏳ extraction needs a model key |
| 12-month web-archive backfill (same pipeline, historical events/cards) | ✅ | ✅ integration (incl. skipped anti-bot capture) | ✅ archive client and quality gate on razorpay.com; ⏳ extraction |
| Page monitoring: conditional GET, quality gate, hash, diff, noise filter | ✅ | ✅ unit + integration | ✅ on razorpay.com/pricing |
| Tracked-value change detection (phrasing-insensitive) | ✅ | ✅ unit + integration | ⏳ |
| Tier-2 materiality (fast model) with learned preferences | ✅ | ✅ integration (scripted) | ⏳ |
| News monitoring: unseen items, triage, entity resolution, clustering | ✅ | ✅ integration | ⏳ needs search key |
| Verifier agent loop with tools, budgets, guardrails | ✅ | ✅ integration | ⏳ |
| Deterministic evidence rubric, source classes, syndication, quote verification | ✅ | ✅ unit + integration | ✅ quote check is pure code |
| Impact analysis grounded in Company Profile; severity caps | ✅ | ✅ unit + integration | ⏳ |
| Routing: inbox + Slack (immediate) / daily digest | ✅ | ✅ integration (inbox) | ⏳ Slack needs a webhook |
| Feedback reasons → visible, reversible learned rules | ✅ | ✅ unit + integration | — |
| Human approvals for external actions; execution record | ✅ | ✅ integration | ⏳ email needs SMTP |
| Run traces with tokens, latency, estimated cost | ✅ | ✅ integration | — |
| Scheduler (adaptive intervals, baseline retry, digest), job queue, worker | ✅ | ✅ integration | ✅ worker + heartbeat on dev DB |
| Auth (email + password), organisations, workspaces | ✅ | ✅ integration | ✅ on dev server |
| REST API per contract | ✅ | ✅ integration | ✅ every endpoint answered on dev server |
| Demo lab (fictional company pages, edit → detect live) | ✅ | ✅ integration | ✅ baseline on dev server |
| Web frontend: every product screen | ✅ | type-check + lint (no automated UI tests) | ✅ clicked through against the real backend (§3) |
| Card re-notifies its teams when evidence later turns Conflicting | ✅ | ✅ integration | — |

---

## 2. Backend

### 2.1 What is tested, and how

`uv run pytest` → **385 tests pass** (378 unit, 7 integration) in about 6 seconds; `ruff`
reports no issues.

- **Unit tests (378):** evidence rubric (primary/independent/community, syndication, distrust,
  unverified quotes, contradiction cases), policy thresholds and learned-rule effects,
  severity caps, feedback interpretation, clustering keys, adaptive scheduling, value
  equivalence, relative quality gate, context-aware date masking; provider modules with
  mocked HTTP: Anthropic/OpenAI/Gemini request formats, schema handling, retries and error
  mapping; Tavily/Exa/Serper mapping and date parsing; SSRF (private, loopback, link-local,
  metadata, encoded IPs, redirect to private); robots.txt (RFC 9309 longest-match, crawl-
  delay, 5xx → disallow); fetcher (304, size cap, charset, sandbox scheme); extraction
  (pricing page, article, challenge page, PDF); Wayback CDX parsing and retries; diffing;
  quote verification (numbers and negations must match).
- **Integration tests (7), against PostgreSQL built by the real migrations:**
  1. Auth: 401 without a session, signup, me, logout, bad password, login.
  2. Full loop: company profile → "I want to monitor Nimbus Pay" → planner run (decision →
     tool call → finish) → plan with live-validated sources → approval → baseline (values
     with verified quotes) → no cards at baseline → the competitor edits its page (fee 2% →
     1.8%, new 90-day offer, © year) → © change dropped at tier 1, fee change detected as a
     tracked value, offer judged material at tier 2, one cosmetic hunk filtered with a
     reason → two investigations (quote-verified primary evidence → Confirmed) → two cards
     (facts vs assessment, unknown team names dropped) → immediate inbox notifications →
     attention funnel and activity feed → "too minor" twice creates a threshold rule →
     rule undone → external share requires approval and records that nothing was sent
     without SMTP → three news items (two about one partnership, one irrelevant) become
     one event with evidence from two outlets plus a third found by the investigator →
     Corroborated → partner entity and `partners_with` relationship created → re-checking
     finds no new items.
  3. Backfill: four archived captures including an anti-bot page → the anti-bot capture is
     skipped and logged → dated fact history (archive → archive → archive → live) → three
     historical events with archived primary evidence → historical cards → zero
     notifications.
  4. Scheduler: due sources get checks, a failed baseline is retried, the digest is
     enqueued once.
  5. Demo lab: seeding is idempotent; editing the fictional page and letting the scheduler
     run produces one Confirmed card.
  6. Evidence after publication: single source → corroborated updates silently; a primary
     source contradicting it turns the card Conflicting and re-notifies its team once.
  7. Baseline taken before a model key existed: once a model is configured, an unchanged
     page's tracked values are read once (not on every check), and the next price change is
     reported as a proper before → after change.

### 2.2 Verified against real sites (28 Sep 2026)

- `razorpay.com/pricing/`: fetched with robots.txt honoured (it allows `/`, crawl-delay 1);
  extraction produced 129 blocks / 2,121 words with the "2%" headline, "0%*", "platform fees
  for first 90 days" and "Platform fee 2.15% + GST" intact; navigation, cookie banner and
  footer removed.
- SSRF: a request to `http://169.254.169.254/…` is refused.
- Internet Archive: 10 monthly captures since Sep 2025; 4 were empty JavaScript shells and are
  rejected by the quality gate; Oct–Dec 2025 captures are a genuinely shorter older page and
  are kept; the "0%* platform fees for first 90 days" offer is absent from the 9 Mar 2026
  capture and present from the 6 Jul 2026 capture.
- Dev server: `signallens dev` serves every API route against PostgreSQL with the
  in-process worker; the demo-lab baseline ran.

### 2.3 Not built (roadmap)

- Rendering JavaScript-only pages (Playwright fallback) — such pages are detected and
  skipped, not rendered.
- Email digest and Microsoft Teams delivery (Slack and in-app exist).
- "Ask" — natural-language questions over the world state.
- Semantic search with pgvector.
- SSO/SCIM, roles beyond organisation membership, billing.
- Replay evaluation harness for detection precision/recall.
- First-class RSS, filings and GitHub-release source types (news search and pages exist).

### 2.4 Known limitations

- Model-driven quality is unmeasured until live runs; prompts may need tuning on real data.
- Entity resolution uses names, aliases and domains only.
- The daily digest marks items as sent in-app and posts to Slack when a webhook is set.
- DNS-rebinding is not fully closed by the fetcher's SSRF check; production should add an
  egress proxy (documented in `fetch/ssrf.py`).
- Cost figures in the docs are estimates from code paths, not measurements.

---

## 3. Frontend

**Built:** Next.js 16 (App Router) + TypeScript + Tailwind + shadcn/ui + SWR; 17 routes, ~150
feature files. Screens: sign in / sign up; workspaces; onboarding wizard (company profile,
teams, request); live planner view and plan review (toggle entities, areas, tracked values
and sources; change importance, frequency, priority, history replay; see each source's
reason and live check; approve or reject); dashboard (subjects, since-your-last-visit,
attention funnel, live agent activity, source health, approvals callout); intelligence feed
with filters and Live/Historical/All; intelligence card (facts vs agent assessment,
evidence with verified quotes and source classes, fact history, detection and diff,
investigation trace, feedback with reasons, external share); world state (entities, facts
with version history, relationships, live + historical timeline); monitoring (policy,
sources with check-now and check history, areas, learned rules with undo, filtered
changes with reasons); agent runs and run traces (usage, budget, every step); approvals;
settings (profile, teams, Slack webhook); demo lab (edit fictional pages with live preview);
notifications; "API keys not configured" banner; light/dark; responsive to 375 px.

**Verified:**
- `npm run build` (0 type errors) and `npm run lint` pass.
- The build agent checked every route at 1440 px and 375 px in light and dark mode against
  a mock API (`npm run dev:mock`).
- Against the **real backend** (production build, PostgreSQL data produced by running the
  full pipeline with the scripted model): sign-in, workspaces, dashboard, intelligence card,
  entity/world state, monitoring, run trace, plan review → approve (HTTP 200, redirected to
  the dashboard), demo lab, and the card at 375 px — with no failed API calls.
- One real bug found in that walkthrough and fixed in the backend: a fact's "last changed"
  date was not recomputed when archived history arrived after the baseline.

**Not built / gaps:** no automated frontend tests; an active plan's areas and entities can
only be changed by proposing a new plan version (sources can be tuned directly); long lists
(runs, approvals, filtered changes) are not paginated beyond API limits; a single
notification cannot be marked read (only "mark all").

---

## 4. How to verify it yourself

```bash
cd backend && uv run pytest -q                 # 385 tests
uv run signallens config                       # which providers are active
uv run signallens seed-demo --lab && uv run signallens dev
cd ../frontend && npm run build && npm run dev # then sign in as demo@signallens.app / signallens-demo
```
