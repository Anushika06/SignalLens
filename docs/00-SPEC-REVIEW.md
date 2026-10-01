# SignalLens — Specification Review

**What this document is:** an honest review of the original product specification
(`original-spec.md`), the changes made to it, and why. Every decision here is made for the
real product and its real customers. The rest of the documentation (`01-PRODUCT.md`,
`02-TECHNICAL.md`) describes the product *after* these changes.

**Product name:** SignalLens
**One line:** An always-on analyst that tells a business what materially changed in its
external environment, whether it is actually true, why it matters *to that business*, and
who needs to know.

---

## 1. Verdict

The specification is fundamentally right. The problem is real, the framing is sharp
("what materially changed, is it actually true, why does it matter to us, and who needs to
know?"), and three of its design choices are genuinely differentiating:

1. **A persistent, versioned world state** instead of a RAG chatbot.
2. **Evidence states** (Confirmed, Corroborated, Single source, Conflicting, Unverified)
   instead of fake confidence percentages.
3. **A materiality gate** before any expensive reasoning.

But built exactly as written, the product would fail real users in five specific ways:

| # | Failure as written | Root cause |
|---|---|---|
| 1 | "Why it matters" is generic LLM commentary | The system never learns who **"us"** is |
| 2 | Day one: nothing to show for weeks; first crawl looks like "everything changed" | No history and no first-run handling |
| 3 | One funding round becomes fifteen alerts | Page diffs and news events are treated as the same thing; no deduplication |
| 4 | "Corroborated" is only as reliable as the model's judgment | Evidence states are named but never defined; nothing checks that quotes are real |
| 5 | The agent can be manipulated by the pages it reads and can be used to probe internal networks | No prompt-injection, SSRF or crawling-policy design |

It is also heavier than a first real version needs in two places (Celery + Redis, pgvector)
and missing two things every production system needs (evaluation, cost model).

The eighteen changes below fix these. None of them changes the product's identity; they
make its promises true.

### Scorecard

| Dimension | As written | After changes | Changes |
|---|---|---|---|
| Problem and value proposition | Strong | Strong | — |
| Core concept (state + evidence + materiality) | Strong | Strong | — |
| Personal relevance ("why it matters to *us*") | Weak | Strong | C1 |
| Signal-to-noise (alert fatigue) | Medium | Strong | C2, C3, C6, C7, C11 |
| Trustworthiness of verification | Medium | Strong | C4, C8, C9 |
| Time to first value | Weak | Strong | C5, C17 |
| Security and responsible data collection | Missing | Adequate for v1 | C12 |
| Feasibility of the stack | Medium | Strong | C13, C14 |
| Measurability of quality | Missing | Adequate | C15 |
| Go-to-market clarity | Broad | Focused | C16 |

---

## 2. What the specification gets right — keep unchanged

1. **The problem statement.** "Finding information" is solved; *knowing what changed and
   whether to act* is not. This is the correct problem.
2. **"The workflow is the product."** Customers buy the outcome (a trusted, routed, timely
   intelligence item), not the search, the scraping or the model.
3. **World state instead of RAG.** Keeping typed, versioned facts per entity is what allows
   "what changed since…" without re-researching from zero. This is the core moat.
4. **Evidence states instead of confidence scores.** A strategy lead can defend
   "Corroborated by two independent publications" in a meeting. Nobody can defend "94%".
5. **Materiality before reasoning.** It is both the cost model and the anti-noise model.
6. **Human approval of the monitoring plan.** It builds trust and catches wrong entity
   resolution early (e.g. monitoring the wrong "Mercury").
7. **Autonomy for research, humans for consequences.** Exactly the right boundary.
8. **Logical agents are capabilities, not six LLM processes.** This avoids the most common
   failure of agent products (expensive, slow, non-deterministic agent chatter).
9. **The "what it is NOT" list.** Keeps scope honest.
10. **Model tiering.** Cheap models for extraction/classification, strong models only for
    investigation and impact reasoning.

---

## 3. Changes

Each change states the problem, the change, and what the user gets.

### C1. Add "us": the customer's own company context — *critical*

**Problem.** The workflow never captures who the customer is. Without that, the system can
say *what* changed but not *why it matters to this customer* or *who in the company should
care*. The spec's own example — "potential competitive pricing pressure" — is what any model
says about any price cut.

**Change.** Every workspace has a **Company Profile**: our company, what we sell, where, our
known competitors, and our **teams** (Strategy, Product, Compliance, Sales…) with the areas
each team owns. It is captured in onboarding (optional, editable) and used by impact
analysis and routing.

**Result.** The same event produces different, specific intelligence:

| Who "we" are | Razorpay offers new merchants 0% fees for 90 days |
|---|---|
| A competing payment gateway | Direct acquisition threat in the SMB segment → Pricing + Sales |
| A D2C brand that *uses* Razorpay | Leverage to renegotiate our gateway contract → Finance |
| An investor holding a competitor | Margin pressure on the portfolio company → Portfolio team |

That difference is the difference between an alert and intelligence.

### C2. Two detection modes: tracked state vs. event streams

**Problem.** The spec models everything as `CURRENT STATE vs PREVIOUS STATE`. That fits a
pricing page. It does not fit a funding round, a partnership or a regulator's circular:
those are *new events in a stream*, usually reported by many outlets, with no "previous
version" to diff against.

**Change.** Two complementary detection modes that produce the same `Event` object:

- **Tracked-state monitoring** — pages the system snapshots (pricing, product, leadership,
  regulator notification pages). Block-level diff + typed attribute extraction →
  `value changed from X to Y`.
- **Event-stream monitoring** — news, regulatory feeds, filings, release feeds. New items →
  triage → structured event (type, entity, counterparty, amount, date).

### C3. Event clustering (deduplication)

**Problem.** Not in the spec. One funding announcement = fifteen articles = fifteen alerts.

**Change.** Every detected item gets a structured **event key** (event type + entity +
counterparty/product/amount + time window). Items that match an open event attach to it as
additional **evidence** instead of creating a new event; near-identical headlines are caught
by fuzzy matching.

**Result.** Fewer alerts — and, usefully, *clustering becomes corroboration*: fifteen
independent outlets become the evidence for one event.

### C4. Evidence states as deterministic rules, with quote verification

**Problem.** The five states are named but not defined. If a model decides that something
is "Corroborated", the trust promise is only as good as the model's judgment on that day.

**Change.** The model does only two narrow things: (a) copy a quote from a page it actually
fetched, and (b) label the quote's stance (supports / contradicts / context). Code does the
rest:

- **Quote verification.** Evidence is rejected unless its quote is found in the text of a
  document the agent actually retrieved in that run.
- **Source class.** *Primary* = the entity's own official domains, the issuing regulator, or
  a statutory registry. *Independent* = a distinct publisher. Syndicated copies (same wire
  text on different sites) count once.
- **Status rubric** (evaluated in order):

| Status | Rule |
|---|---|
| **Conflicting** | Primary sources disagree; or a primary source contradicts the claim; or — when no primary source supports it — independent sources both support and contradict it |
| **Confirmed** | At least one primary source supports it (secondary disagreement is shown as a note) |
| **Corroborated** | No primary source, but ≥ 2 independent publishers support it and none contradict |
| **Single source** | Exactly one independent publisher supports it |
| **Unverified** | No verified supporting evidence yet |

**Result.** Every status is reproducible and explainable:
"Corroborated — Economic Times and Mint; no contradicting sources."

### C5. Cold start: backfill history from web archives

**Problem.** As written, a new customer's history starts today. The spec's own example
("Sep 01 → 2.2%, Sep 15 → 2.0%, Sep 28 → 1.8%") only exists if the product has been running
for a month. Most trials are decided in the first week.

**Change.** During baseline, official pages can be **backfilled** from the Internet Archive
(Wayback CDX API): roughly one capture per month for the last 12 months is replayed through
the same extraction and change-detection pipeline, producing dated historical state versions
and historical events (never notifications).

**Result.** Day-one value: "here is how Razorpay's pricing page changed over the last year."
(Checked: `razorpay.com/pricing/` has monthly captures from 2024 through August 2026.) The
same mechanism gives an honest demonstration on real, historical changes instead of staged
ones.

### C6. Snapshot quality gate

**Problem.** Real fetches return bot challenges, error pages, cookie walls and empty
JavaScript shells. Diffing one of those against a good snapshot produces an "everything was
removed" false alarm. (Observed: several archived captures of the Razorpay pricing page are
an order of magnitude smaller than the rest — typical of challenge or error pages.)

**Change.** Every snapshot is classified `ok / degenerate / blocked` before it is used. Only
`ok` snapshots are compared.

### C7. Layered materiality — cheapest filter first

**Problem.** The spec says "is it meaningful?" but not how, and doing it with an LLM on every
change would be slow and expensive.

**Change.**

| Tier | Mechanism | Cost |
|---|---|---|
| 0 | Content hash unchanged; only volatile tokens changed (timestamps, relative dates, © year, session IDs) | Free |
| 1 | Rules: boilerplate blocks, learned suppressions (C10); *tracked-attribute value changes always pass* | Free |
| 2 | Fast model classifies remaining changes against the policy and the user's learned preferences | Cheap |
| 3 | Investigation + impact analysis, only above the area's threshold | Expensive, rare |

Every tier is counted, which produces the **attention funnel** shown on the dashboard
("1,240 checks → 38 changes → 6 material → 3 alerts") — visible proof that noise was removed
on the user's behalf.

### C8. Severity and evidence status are two separate axes

**Problem.** The spec's 🔴🟡🔵 is undefined and mixes *how important* with *how sure*.

**Change.** **Severity** (critical / high / medium / low — how much it matters to us) and
**Evidence status** (how sure we are) are shown separately. Guardrails in code: an
*Unverified* item cannot be more than Medium; a *Single source* item cannot be Critical.

### C9. Time has two meanings: observed vs. effective

**Problem.** "Timestamp" is ambiguous. We *observed* a price change on 28 Sep; the company
may have *made* it on 20 Sep, or announced it effective 1 Oct.

**Change.** Every state version records `observed_at` (when we saw it), `valid_from` (when
it took effect, if known), the source, the evidence and the causing event. Needed for
correct "what changed since…" answers and for backfilled history.

### C10. Feedback with reasons → visible, reversible learned rules

**Problem.** "Relevant / not relevant" is too coarse to learn from, and silent learning
erodes trust ("why did I stop getting these?").

**Change.** Feedback carries a reason, and each reason maps to a specific, explainable
policy adjustment the user can see and undo:

| Feedback reason | What the system learns |
|---|---|
| Not relevant — too minor | After repeated signals, raises the materiality threshold for that area and change type |
| Not relevant — not our area | Lowers that area's importance (digest instead of immediate) |
| Inaccurate | Stops counting that publisher toward corroboration in this workspace |
| Wrong company/entity | Adds an exclusion to entity resolution |
| Relevant — always tell me immediately | Raises the area to critical |

Shown as, e.g.: *"Because you marked 2 minor product-page changes as not relevant, I now
alert only on medium or higher changes there. [Undo]"*

### C11. Delivery: immediate for what's urgent, digest for the rest

**Problem.** Every item as an immediate alert recreates the flood the product exists to
remove. "Tell me what changed since I last checked" has no mechanism.

**Change.** Critical/high items notify their teams immediately (in-app inbox, Slack);
everything else goes to a daily digest. The dashboard marks **"since your last visit"**.

### C12. Security and responsible data collection — missing entirely

An autonomous agent that reads arbitrary web pages is an attack surface. Required from v1:

- **Prompt injection containment.** Fetched content is treated as untrusted data, never as
  instructions. Research tools are read-only. No tool available to a research agent can
  change configuration or send anything externally. Evidence status is computed by code,
  not asserted by the model. External actions always require human approval.
- **SSRF protection.** Every URL the agent fetches is resolved and rejected if it points to
  private, loopback, link-local or cloud-metadata addresses; redirects are re-checked.
- **Responsible collection.** Honour `robots.txt` and crawl-delay, identify the crawler,
  rate-limit per domain, never bypass logins or paywalls, store excerpts and hashes for
  evidence rather than republishing content.
- **Tenant isolation and secrets.** Every query is scoped to a workspace; API keys live in
  the environment / secret manager, never in the database.

### C13. Be precise about what is agentic

**Problem.** "Planner → Scout → Analyst → Verifier → Impact Analyst → Router" reads like six
agents. Built that way it is slow, costly and non-deterministic.

**Change.** Deterministic code wherever judgment is not needed (fetching, hashing, diffing,
scheduling, evidence rules, routing). Models only where judgment is needed:

| Logical agent | Implementation |
|---|---|
| Planner | **Agent loop** — researches the subject with tools, proposes the monitoring plan |
| Scout | Deterministic fetch/snapshot + fast-model extraction and triage |
| Analyst | Deterministic diff + tiered materiality (fast model only at tier 2) |
| Verifier | **Agent loop** — chooses searches, opens pages, records quoted evidence, decides when it has enough; hard budget + guardrails |
| Impact Analyst | One strong-model structured call, grounded in the Company Profile |
| Router | Deterministic rules from teams, areas and severity |

Every model call and tool call is recorded as a step of a **Run**, visible in the UI
("show your work").

### C14. Stack adjustments

| Spec | Decision | Reason |
|---|---|---|
| Redis + Celery | **Postgres-backed job queue** (`FOR UPDATE SKIP LOCKED`) + async worker | Jobs are created in the *same transaction* as the state change that causes them (no lost or phantom jobs); async-native (the runtime is asyncio, Celery is not); one fewer service to run; jobs are rows the UI can show as live agent activity; works on every developer OS. Upgrade path (dedicated broker or a durable-workflow engine) when volume demands it. |
| pgvector | **Deferred** (schema-ready) | Clustering and entity resolution work better with structured keys + fuzzy matching; retrieval uses Postgres full-text search. Add pgvector when semantic search across evidence becomes a feature. |
| Playwright | **Fallback only, added next** | Most official pages are server-rendered (Razorpay's pricing page is). Plain HTTP is far cheaper; a browser should be used only when a page needs JavaScript. v1 detects JavaScript-only pages (empty extraction) and skips them rather than rendering them. |
| `companies` table | **Merged into `entities`** (`kind = company`) | Pharma needs drugs and trials, automotive needs vehicle models, fintech needs regulators. One polymorphic entity model is what makes the product domain-agnostic. |
| — | **Added** `documents`, `source_checks`, `learned_rules`, `agent_runs`, `run_steps`, `approvals`, `jobs`, `teams`, `workspace_members` | Needed for evidence storage, observability, feedback learning, the audit trail, human approvals and scheduling. |
| One search provider | Kept, behind an interface (Tavily, Exa, Serper implemented) | Swappable per cost/coverage. |
| LLM provider abstraction | Kept (Anthropic, OpenAI, Gemini) with fast/reasoning tiers | As specified. |

### C15. Evaluation and quality metrics

**Problem.** No way to know whether the product is getting better or worse.

**Change.**

- **Product metrics:** alert precision (share of items marked relevant), time-to-detection,
  evidence coverage (share Confirmed/Corroborated), false-alarm rate, cost per monitored
  subject per month.
- **Test suite:** deterministic tests for diffing, materiality tiers, evidence rules, quote
  verification, clustering, feedback learning, scheduling and the end-to-end pipeline with
  scripted models.
- **Evaluation harness (next):** replay archived history of real pages with labelled
  changes to measure detection precision/recall per model and prompt version.

### C16. Focus the go-to-market, not the product

**Problem.** Eight user types and five buyer titles is not an ideal customer profile.

**Change.** The *product* stays domain-agnostic. The *go-to-market* starts with a beachhead:

- **Beachhead:** B2B companies (≈100–2,000 employees) in fast-moving, publicly observable
  markets — payments/fintech, B2B SaaS, commerce enablement — with 5–20 direct competitors,
  meaningful regulatory exposure, and a small strategy or product-marketing function but no
  dedicated CI team.
- **Add the missing persona:** in B2B software companies, competitive intelligence most
  often sits with **Product Marketing**. The primary user is "the person who maintains the
  competitor spreadsheet"; the buyer is the Head of Strategy / VP Product Marketing / CPO.
- **Expansion:** enterprise CI and market-intelligence teams (pharma, automotive,
  manufacturing), regulatory horizon-scanning for compliance teams, and investors
  monitoring portfolio companies and their competitors.

### C17. The plan proposal must show its reasoning and pass live checks

Each proposed source shows *why* it was chosen and a live validation (reachable, allowed by
`robots.txt`, extractable content). Users approve faster and catch wrong sources before they
cause noise.

### C18. First run is a baseline, never an alert

The first successful observation of any source is recorded as the baseline and cannot
produce notifications. Historical events from backfill are labelled *historical* and are
never sent as alerts.

---

## 4. What is really needed — scope for the first real version

| Capability | v1 (build now) | Next | Not needed |
|---|---|---|---|
| Natural-language onboarding → researched plan → approval | ✅ | | |
| Company Profile + teams (C1) | ✅ | Auto-draft profile from our website | |
| Baseline + typed facts + versioned state | ✅ | | |
| History backfill from web archive (C5) | ✅ | | |
| Page monitoring (diff + attribute extraction) | ✅ | Visual/screenshot diff | |
| News / event-stream monitoring + clustering | ✅ | RSS, filings, GitHub releases as first-class sources | |
| Tiered materiality + attention funnel | ✅ | | |
| Investigation agent + deterministic evidence rules | ✅ | | |
| Impact analysis grounded in Company Profile | ✅ | | |
| Intelligence cards, world-state explorer, run traces | ✅ | | |
| Feedback reasons → learned rules with undo | ✅ | | |
| Routing: in-app inbox + Slack webhook; digest | ✅ | Email digest (SMTP), Teams | |
| Human approval queue for external actions | ✅ | More action types (CRM updates) | |
| Adaptive scheduling, robots/SSRF/rate limits | ✅ | | |
| Auth, organisations, workspaces | ✅ (email + password) | SSO / SCIM | |
| Ask questions of the world state | | ✅ | |
| Semantic search (pgvector) | | ✅ | |
| Playwright rendering | Detects JS-only pages and skips them | ✅ | |
| Billing, usage-based plans | | ✅ | |
| Six independent LLM agents talking to each other | | | ❌ |
| Blanket crawling of whole sites | | | ❌ |
| Generic chat interface | | | ❌ |

---

## 5. Industry domain

**SignalLens belongs in _Business_.**

- **What it is for:** better and faster business decisions by strategy, product-marketing,
  competitive-intelligence and compliance teams. The buyer, budget and value are business
  functions.
- **Why not FinTech:** Razorpay is only the demonstration subject. The same product monitors
  Tata Motors (automotive) or Pfizer (pharma) with a different domain model discovered at
  onboarding. Classifying it by its demo subject would misdescribe it.
- **Why not AI & Developer Tools:** the users are not developers and the product is not a
  tool for building AI. Agentic AI is *how* it works, not *what it is for*.
- **Why not Open Innovation:** that category is for work that fits no defined domain; this
  fits Business cleanly.

---

## 6. Decision log

| ID | Decision | Status |
|---|---|---|
| D1 | Product name **SignalLens** | Adopted |
| D2 | Company Profile + teams per workspace (C1) | Implemented in v1 |
| D3 | Two detection modes feeding one Event model (C2) | Implemented in v1 |
| D4 | Structured event keys + fuzzy matching for clustering (C3) | Implemented in v1 |
| D5 | Deterministic evidence rubric + quote verification (C4) | Implemented in v1 |
| D6 | Web-archive backfill during baseline (C5) | Implemented in v1 |
| D7 | Snapshot quality gate (C6) | Implemented in v1 |
| D8 | Four-tier materiality + attention funnel (C7) | Implemented in v1 |
| D9 | Severity and evidence status as separate axes with guardrails (C8) | Implemented in v1 |
| D10 | `observed_at` + `valid_from` on every state version (C9) | Implemented in v1 |
| D11 | Feedback reasons → visible, reversible learned rules (C10) | Implemented in v1 |
| D12 | Immediate vs digest delivery; "since your last visit" (C11) | Implemented in v1 |
| D13 | Prompt-injection containment, SSRF guard, robots/rate limits (C12) | Implemented in v1 |
| D14 | Two true agent loops (Planner, Verifier); rest deterministic or single calls (C13) | Implemented in v1 |
| D15 | Postgres job queue instead of Celery + Redis (C14) | Implemented in v1 |
| D16 | pgvector deferred; Playwright as a later fallback; `companies` merged into `entities` (C14) | Adopted (Playwright not yet built) |
| D17 | Metrics + deterministic test suite now; replay evaluation harness next (C15) | Tests in v1; harness next |
| D18 | Beachhead ICP + Product Marketing persona (C16) | Adopted in product docs |
| D19 | Plan proposals carry reasons + live validation (C17) | Implemented in v1 |
| D20 | First observation = baseline; historical items never alert (C18) | Implemented in v1 |

The "Status" column is kept honest in `04-IMPLEMENTATION-STATUS.md`, which is the single
place that records what is built, what is tested, and what is not.

---

## 7. Open questions (none block the build)

1. **Model and search provider accounts.** The system supports Anthropic, OpenAI and Gemini
   (models) and Tavily, Exa and Serper (search). A live run needs at least one key of each
   kind in `backend/.env`.
2. **Beachhead confirmation.** Payments/fintech + B2B SaaS in India is the proposed first
   market; confirm or replace.
3. **Name clearance.** Check trademark and domain availability for "SignalLens" before any
   public launch.
