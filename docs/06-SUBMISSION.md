# SignalLens — Submission Pack

Everything the submission form asks for, ready to paste. Keep this file in sync with the
product: if the product changes, update the matching section here.

---

## 1. Project name

**SignalLens**

Tagline: *Know what changed, whether it's true, and why it matters to you.*

Category: **Business** (B2B intelligence for strategy, product-marketing, competitive-
intelligence and compliance teams; domain-agnostic across industries).

---

## 2. Problem statement (≈150 words)

Businesses make pricing, product and compliance decisions based on what competitors,
partners and regulators are doing. That information is public but scattered across websites,
news, regulator notices and filings, and it changes without warning. Strategy and
product-marketing teams keep up by manually re-checking dozens of sources, which is slow and
still misses changes. Alerts and page-change monitors only add noise: they report that
*something* changed, not *whether it matters*, *whether it is true*, or *who should act*. And
nothing remembers what was known before, so every question starts from scratch.

The real problem is not finding information. It is answering, continuously and reliably:
**what materially changed, is it actually true, why does it matter to us, and who needs to
know?**

---

## 3. Solution overview (≈250 words)

SignalLens is an always-on intelligence analyst. A user writes "I want to monitor Razorpay."
A **planning agent** researches the company, discovers its official pages, relevant
regulators and competitors, and proposes a monitoring plan with a reason and a live check for
every source. The user approves or edits it — nothing runs without that approval.

SignalLens then builds a **persistent, versioned world state**: tracked facts (e.g. the
standard transaction fee) with dated values and quoted evidence. It **backfills a year of
history** from the Internet Archive, so the first day already shows how things changed.

Monitoring is **cheap by design**: most checks stop at a content hash; volatile noise is
filtered deterministically; a fast model judges what remains against the user's priorities.
Only material changes reach an **investigation agent**, which searches, opens sources and
records quotes. Evidence status (Confirmed, Corroborated, Single source, Conflicting,
Unverified) is **computed by rules**, and every quote is checked against the page it came
from. An impact analyst writes a card that separates **facts** from **assessment**, grounded
in the user's own company profile, and routes it to the right team — immediately if urgent,
in a digest otherwise.

Feedback becomes visible, reversible **learned rules**. Anything consequential — like sharing
outside the company — waits for **human approval**. It works for any company in any
industry.

---

## 4. Agent workflow / architecture

```
Request ─▶ PLANNER (agent loop: search, open pages) ─▶ plan + live source checks ─▶ HUMAN APPROVAL
                                                                                   │
           ┌──────────────────────────── activation: entities, facts, sources ◀────┘
           ▼
  BASELINE (today's values, quoted) + BACKFILL (12 months of archived versions, same pipeline)
           │
  SCHEDULER ─▶ CHECK SOURCE
                 ├─ page: 304/hash (tier 0) → quality gate → tracked values + noise-filtered diff (tier 1)
                 │        → fast-model materiality vs policy + learned preferences (tier 2)
                 └─ news: unseen items → triage → entity resolution → clustering (= corroboration)
           │ material only
           ▼
  VERIFIER (agent loop: search, open pages/archives, record verbatim quotes; guardrail vs single-source)
           │  evidence status computed by deterministic rules
           ▼
  IMPACT ANALYST (grounded in "who we are") ─▶ INTELLIGENCE CARD (facts vs assessment, severity caps)
           │
  ROUTER ─▶ team inbox / Slack now, or daily digest        FEEDBACK ─▶ learned rules (visible, undoable)
           │
  External actions ─▶ HUMAN APPROVAL queue
```

**Agentic core (custom runtime):** Runs with budgets (steps, tool calls, model calls, time,
cost) enforced by the runtime; typed tools with side-effect classes; one typed Decision per
step (`thought, action, args`) validated before execution; every decision and tool call
recorded as an inspectable trace; web content fenced as untrusted data; guardrails that can
send the agent back to work. Two capabilities are true agent loops (planning, verification);
the rest are deterministic code or single typed model calls — cheaper, faster, testable.

---

## 5. Technology stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, SWR |
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| Agent runtime | Custom Python async runtime: runs, steps, tools, budgets, guardrails, model gateway |
| Models | Provider abstraction: Anthropic, OpenAI (and any OpenAI-compatible server), Gemini; fast tier for extraction/triage/materiality, reasoning tier for planning/investigation/impact |
| Search | Provider abstraction: Tavily, Exa, Serper |
| Collection | httpx with SSRF protection, robots.txt (RFC 9309), per-host politeness; lxml/BeautifulSoup/trafilatura extraction; pypdf; Internet Archive (Wayback CDX) |
| Data | PostgreSQL (JSONB), SQLAlchemy 2 async + asyncpg, Alembic migrations |
| Background work | Postgres-backed job queue (`FOR UPDATE SKIP LOCKED`) + async worker + scheduler |
| Quality | pytest (unit + integration against PostgreSQL), respx, ruff |

---

## 6. GitHub repository

**To be published at submission time.** By decision, nothing has been pushed yet. When
publishing: create the repository, add `README.md` as the landing page, confirm
`backend/.env` is not committed (it is git-ignored), then paste the URL here.

Repository URL: `________________________`

---

## 7. Working demo

**Local (works today):**

```bash
# backend
cd backend
cp .env.example .env            # add one model key and one search key
uv sync
uv run signallens migrate
uv run signallens seed-demo --lab
uv run signallens dev           # API + worker on http://127.0.0.1:8000

# frontend (second terminal)
cd frontend
npm install
npm run dev                     # http://localhost:3000  → sign in as demo@signallens.app / signallens-demo
```

**Hosted demo:** to be deployed at a later stage. Hosted URL: `________________________`

---

## 8. Demo video (2–3 minutes)

Script and shot list: `docs/05-DEMO-SCRIPT.md`. Video link: `________________________`

---

## 9. Pitch deck

`docs/pitch-deck.html` — open in a browser; arrow keys to navigate; print to PDF for upload.

---

## 10. Requirements check

| Requirement | How SignalLens meets it |
|---|---|
| Uses agentic AI meaningfully | Two autonomous agent loops (planning, verification) that choose tools, inspect results, decide when to stop; plus typed model calls for extraction, triage, materiality and impact |
| Solves a real-world problem | Continuous competitive, market and regulatory monitoring for strategy/PMM/compliance teams |
| Not a chatbot or thin wrapper | Persistent world state, scheduling, evidence rules, feedback learning and approvals — the model is one component |
| Reasoning | Materiality judgments against a policy; impact analysis grounded in the user's company profile |
| Planning | The planner designs the whole monitoring plan (entities, areas, attributes, sources, frequencies) |
| Tool/API use | Web search, page fetching, archive lookups, world-state queries, evidence recording; model and search provider APIs |
| Multi-step workflows | Request → plan → approval → baseline → backfill → monitor → filter → investigate → assess → route → learn |
| Taking actions | Routes intelligence to teams (inbox, Slack), queues external actions for approval and executes them once approved |

## 11. Judging criteria → where to look

| Criterion | Evidence in the product |
|---|---|
| Agentic capability | Planner and Verifier run traces (every decision, tool call, guardrail); budgets; self-correction on invalid tool arguments |
| Problem relevance & impact | Company-profile-grounded "why it matters"; routing to owning teams; alert-fatigue controls (attention funnel, digest) |
| Technical implementation | Custom runtime, Postgres job queue with transactional enqueue, deterministic evidence rubric with quote verification, 380+ tests incl. full-loop integration |
| Innovation | Archive backfill for day-one history; clustering-as-corroboration; computed (not generated) evidence status; visible, reversible learned rules |
| User experience | Plan review with reasons and live checks; cards separating facts from assessment; "since your last visit"; show-your-work traces |
| Scalability & feasibility | Model spend scales with changes, not checks (≈$4–6/workspace/month estimated model cost); stateless API; horizontally scalable workers |
| Demo quality | Real Razorpay data (live + archived), deterministic demo lab for the live moment, honest labels |

## 12. Explaining the implementation (60-second version)

> "SignalLens is a FastAPI backend with our own agent runtime and a Next.js frontend, on
> PostgreSQL. The planner is an agent loop: it decides what to search, opens pages, then
> writes a plan a human approves. Approval creates entities, tracked facts and scheduled
> sources in one transaction, plus baseline and backfill jobs in a Postgres queue. Checks
> are tiered: hash first, deterministic noise filtering, then a cheap model for materiality.
> Material changes go to a second agent loop that verifies them — it can only quote pages
> it opened, and code checks every quote and computes the evidence status. A final model
> call writes the card for this company, code caps severity and routes it. Feedback becomes
> explicit rules the user can undo. Every model and tool call is traced with tokens and cost."

## 13. Likely questions

| Question | Answer |
|---|---|
| What stops the agent from making up evidence? | It can only quote documents it retrieved in that run; code verifies each quote (numbers and negations must match) and computes the status. |
| What if a web page tells the agent to do something? | Web text is fenced as untrusted data; research agents hold no tools that change configuration or reach outside; external actions need human approval. |
| Why not just use ChatGPT with search? | No memory of prior state, no schedule, no noise filtering, no computed evidence status, no routing, no learning. The workflow is the product. |
| How do you avoid alert fatigue? | Tiered materiality (most checks never reach a model), clustering, severity caps, digest for non-urgent items, and feedback-driven thresholds. |
| Is scraping allowed? | SignalLens reads public pages only, honours robots.txt and crawl-delay, identifies itself, rate-limits per site, and never bypasses logins or paywalls. |
| What does it cost to run? | Estimated $4–6 per workspace per month in model spend for a typical plan; real usage is recorded per run. |
| Does it work outside fintech? | Yes — the planner discovers a different domain model per company (e.g. EVs and plants for Tata Motors; trials and approvals for Pfizer). |
