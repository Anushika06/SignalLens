# SignalLens

**An always-on AI analyst that watches competitors, partners and regulators for you.**
Tell it *"I want to monitor Razorpay"*. It researches the company, proposes what to watch (you
approve), records today's facts with quoted evidence, replays a year of history from web
archives, and then keeps watching. When something changes it decides whether it matters,
verifies it, explains why it matters **to your company**, and routes it to the team that owns it.

*Know what changed, whether it's true, and why it matters to you.*

## Live Demo

- **Web App**: [https://signallens-xi.vercel.app](https://signallens-xi.vercel.app/)
- **Agent API**: [https://signallens-api-pa36.onrender.com](https://signallens-api-pa36.onrender.com/)
- **Agent Health**: [https://signallens-api-pa36.onrender.com/api/agent/health](https://signallens-api-pa36.onrender.com/api/agent/health)
- **Agent Manifest**: [https://signallens-api-pa36.onrender.com/api/agent/manifest](https://signallens-api-pa36.onrender.com/api/agent/manifest)

---

## The problem

Pricing, product and compliance decisions depend on what competitors, partners and regulators
do. That information is public but scattered across websites, news, regulator notices and
filings, and it changes without warning. Teams re-check dozens of sources by hand, and still
miss changes. Page-change alerts only add noise: they say *something* changed, not *whether it
matters*, *whether it is true*, or *who should act*. Indian startups and MSMEs feel this most —
they compete with well-funded players but can't afford a competitive-intelligence team.

## What makes it agentic

| The agent… | How |
|---|---|
| **Plans** | A planner agent searches the web, opens pages and proposes a monitoring plan: entities, areas, tracked facts and sources, each with a reason and a live check. |
| **Asks before acting** | Nothing is monitored until a human approves the plan; external actions (sharing a card outside the company) wait in an approvals queue with owner/admin rules. |
| **Remembers** | A versioned world state: tracked facts with dated values and verbatim, machine-checked quotes, plus a year of history rebuilt from the Internet Archive. |
| **Watches** | A scheduler re-checks sources. Most checks stop at a content hash; noise is filtered by rules; a fast model judges what remains against your priorities. |
| **Verifies** | An investigator agent searches, opens sources and records quotes. Evidence status (Confirmed, Corroborated, Single source, Conflicting, Unverified) is computed by code, never guessed by the model. |
| **Reasons about impact** | An impact analyst writes a card that separates facts from assessment, grounded in *your* company profile. |
| **Acts** | Routes cards to the right team: in-app, Slack, email alerts or the daily email digest. |
| **Learns** | Feedback ("too minor", "not relevant") becomes visible, reversible rules. |
| **Answers** | *Ask*: natural-language questions over everything it knows, answered with citations to cards and facts. |
| **Shows its work** | Every run is a trace: each decision, tool call, model call, latency and token count. |

## Agent workflow

```
Request ─▶ PLANNER (agent loop: search, open pages) ─▶ plan + live source checks ─▶ HUMAN APPROVAL
                                                                                   │
           ┌──────────────────────────── activation: entities, facts, sources ◀────┘
           ▼
  BASELINE (today's values, quoted) + BACKFILL (12 months of archived versions, same pipeline)
           │
  SCHEDULER ─▶ CHECK SOURCE
                 ├─ page: 304/hash → quality gate (JS rendering optional) → tracked values + diff
                 │        → fast-model materiality vs policy + learned preferences
                 └─ news: unseen items → triage → entity resolution → clustering (= corroboration)
           │ material only
           ▼
  VERIFIER (agent loop: search, open pages/archives, record verbatim quotes)
           │  evidence status computed by deterministic rules
           ▼
  IMPACT ANALYST (grounded in "who we are") ─▶ INTELLIGENCE CARD (facts vs assessment)
           │
  ROUTER ─▶ team inbox / Slack / email now, or daily digest      FEEDBACK ─▶ learned rules
  External actions ─▶ HUMAN APPROVAL (owners/admins; no self-approval)
  ASK ─▶ agent over the world state (full-text memory search, fact history, cards) with citations
```

---

## Two ways to run the agent (aiKart submission)

### Method 2 — hosted API endpoint (the full, always-on agent)

```bash
API=https://<your-api-host>          # e.g. the Render URL; locally http://127.0.0.1:8000

curl $API/api/agent/health
curl $API/api/agent/manifest

# One-shot intelligence brief (synchronous, ~1–3 minutes)
curl -X POST $API/api/agent/brief -H 'Content-Type: application/json' \
  -d '{"company": "Razorpay", "your_company": "Cashfree Payments, a payment gateway for Indian businesses"}'

# Asynchronous: start, then poll
curl -X POST $API/api/agent/briefs -H 'Content-Type: application/json' -d '{"query": "What is PhonePe up to?"}'
curl $API/api/agent/briefs/<brief_id>
```

Responses are `{"format": "markdown", "response": "...", "brief_id", "data", "trace"}`. Bodies may
be the inputs object, `{"input": {...}}`, or free text in `query` / `message` / `prompt`. When
`SL_AGENT_API_KEYS` is set, send `X-API-Key: <key>`.

### Method 1 — aiKart "Try Me Now" container

[`aikart-manifest.yaml`](aikart-manifest.yaml) follows the aiKart Agent Manifest v1 spec. The image
(`ghcr.io/pratyushmishra-2nd/signallens-agent`) is built by
[`.github/workflows/docker-publish.yml`](.github/workflows/docker-publish.yml). The container reads
`/aikart/input.json` (or `AIKART_INPUT`), runs the brief agent and writes
`/aikart/output.json` as `{"format": "markdown", "response": "..."}`.

```bash
docker build -t signallens-agent backend
mkdir -p run && cp examples/aikart/input.json run/
docker run --rm -e NVIDIA_API_KEY -e TAVILY_API_KEY -v "$PWD/run:/aikart" signallens-agent signallens aikart-run
cat run/output.json
```

Without keys the container delegates to the hosted API (`SL_REMOTE_AGENT_URL`, baked in at build
time), so the public image never contains secrets. Under aiKart's egress allowlist, company pages
are read through Tavily's extract API (`SL_BRIEF_READER=tavily`). A sample output is in
[`examples/aikart/sample-output.md`](examples/aikart/sample-output.md).

**The brief agent** (both methods): resolves the company and its official domain → reads key
official pages and extracts facts with verified quotes → compares them with Wayback Machine
captures from up to 12 months ago → searches recent news and computes evidence status →
writes "why it matters to you" (facts vs assessment) and recommended actions per team →
markdown with the full agent trace. English or Hindi.

---

## Repository

```
backend/     Python 3.12 · FastAPI · custom agent runtime · PostgreSQL · job queue + worker
frontend/    Next.js · TypeScript · Tailwind · shadcn/ui · SWR
examples/    aiKart input and a sample brief
aikart-manifest.yaml · render.yaml · .github/workflows/{ci,docker-publish}.yml
```

## Technology

| Layer | Technology |
|---|---|
| Models | NVIDIA NIM (`nvidia/nemotron-3-super-120b-a12b`, with automatic failover to other NIM models when one stalls) |
| Search | Tavily (Exa and Serper also supported) |
| Agent runtime | Custom async runtime: runs, steps, typed tools, budgets, guardrails, model gateway with schema validation and repair |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async + asyncpg, Alembic |
| Background work | Postgres job queue (`FOR UPDATE SKIP LOCKED`) + async worker + scheduler |
| Collection | httpx with SSRF protection, robots.txt (RFC 9309), per-host politeness; trafilatura/lxml; pypdf; Internet Archive; optional Playwright rendering for JavaScript-only pages |
| Delivery | In-app inbox, Slack webhooks, email (Brevo / Resend / SMTP) alerts and daily digest |
| Auth | Email + password, OpenID Connect SSO (Google, Microsoft Entra, Okta); workspace roles |
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS, shadcn/ui, SWR |
| Quality | pytest (unit + integration on PostgreSQL), ruff, Vitest + Testing Library, Playwright e2e + axe, GitHub Actions CI |
| Deployment | Docker; Vercel (frontend) + Render (API + worker) + Supabase (Postgres); GHCR image for aiKart |

---

## Run it locally

**Prerequisites:** Python 3.12 with [uv](https://docs.astral.sh/uv/), Node.js 20+, PostgreSQL 15+
(a local install, or `docker compose up -d db` which starts one on port 5433).

### 1. Database

```sql
-- as a PostgreSQL superuser
CREATE ROLE signallens LOGIN PASSWORD 'signallens';
CREATE DATABASE signallens OWNER signallens;
CREATE DATABASE signallens_test OWNER signallens;   -- only needed for the test suite
```

### 2. Backend

```bash
cd backend
cp .env.example .env        # then add NVIDIA_API_KEY and TAVILY_API_KEY
uv sync
uv run signallens migrate
uv run signallens seed-demo --lab
uv run signallens dev       # API + background worker on http://127.0.0.1:8000
```

| Needed for | Put in `backend/.env` |
|---|---|
| Planning, extraction, investigation, impact analysis, Ask, briefs | `NVIDIA_API_KEY` (free at [build.nvidia.com](https://build.nvidia.com)) |
| News monitoring and web search | `TAVILY_API_KEY` (free at [app.tavily.com](https://app.tavily.com)) |
| Optional: email alerts and digests | `BREVO_API_KEY` + `SL_EMAIL_FROM` (or Resend / SMTP) |
| Optional: single sign-on | `SL_OIDC_ISSUER`, `SL_OIDC_CLIENT_ID`, `SL_OIDC_CLIENT_SECRET`, `SL_PUBLIC_APP_URL` |
| Optional: JavaScript rendering | `uv sync --extra browser`, `uv run playwright install chromium`, `SL_RENDER_JS=true` |

`uv run signallens config` shows which providers are active (it never prints keys).
Production-style: `uv run signallens api` and `uv run signallens worker` as separate processes
(scale workers horizontally), or one process with `SL_RUN_WORKER_IN_API=true`.

One-shot brief from the command line:

```bash
uv run signallens brief "Razorpay" --for "Cashfree Payments, a payment gateway for Indian businesses"
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:3000
```

Sign in with **demo@signallens.app / signallens-demo** (a second demo admin,
**meera@signallens.app**, shows the "someone else approves" flow), or create an account.

- **Demo lab:** the *Demo lab: Nimbus Pay* workspace monitors a fictional company's pages served
  by SignalLens itself. Edit them under *Demo lab*, press *Check now* on the source, and watch
  detection → verification → card → routing happen live.
- **Real company:** create a workspace, describe your company, and type
  "I want to monitor Razorpay" (or any company).
- **Ask:** open *Ask* in a workspace and ask "What changed in pricing this year?".

### Roles and single sign-on

- **Roles** (per workspace): *owner* (whoever created it), *admin*, *member*, managed under
  Settings → Members & roles. Only owners and admins approve external actions. Nobody approves
  their own request unless they are the only owner/admin, and then the decision note says
  "(self-approved: sole approver)". Adding a new email creates an invited account in your
  organisation that signs in with SSO.
- **Single sign-on** (OpenID Connect) is turned on by the `SL_OIDC_*` variables above. Register
  `{SL_PUBLIC_APP_URL}/api/auth/sso/callback` as the redirect URI with the provider (Google:
  Cloud Console → APIs & Services → Credentials → OAuth client ID → *Web application*).

### 4. Tests

```bash
cd backend
uv run pytest -q            # unit + integration (integration uses the signallens_test database;
                            # override with SL_TEST_DATABASE_URL)
uv run ruff check signallens tests

cd ../frontend
npm run lint && npm run typecheck
npm test                    # Vitest + Testing Library: lib helpers and components
npx playwright install chromium   # once
npm run test:e2e            # Playwright end-to-end journeys + axe accessibility checks
npm run build
```

The end-to-end tests need no backend: Playwright starts the mock API and a production build of
the app via `frontend/scripts/e2e-server.mjs`. Every test fails on console errors, uncaught
exceptions or failed requests. CI (`.github/workflows/ci.yml`) runs everything on each push and
pull request: backend ruff + pytest against Postgres, frontend lint, typecheck, unit, build and
e2e on Node 20 and 22, and a Docker build.

---

## Deployment

Free-tier setup: **Vercel** (frontend) → proxies `/api/*` to **Render** (one Docker web service
running the API and the worker, [`render.yaml`](render.yaml)) → **Supabase** (Postgres). The
aiKart image is published to **GHCR** by GitHub Actions. On Render's 512 MB free instance the
headless browser is off; JavaScript-only pages are detected and skipped with a clear reason.

## Responsible by design

- Human approval before monitoring starts and before anything leaves the company.
- Evidence status computed by rules; every quote is checked against the page it came from; facts
  and the agent's assessment are always shown separately.
- Web content is fenced as untrusted data in every prompt; agents have budgets and guardrails.
- Collection honours robots.txt, rate-limits per host, refuses private/internal addresses (SSRF
  protection, also inside the headless browser) and never tries to bypass anti-bot challenges.
- Secrets live only in environment variables; the public container image contains none.

## Roadmap

Semantic search with pgvector for Ask; Microsoft Teams delivery; first-class RSS, filings and
GitHub-release sources; SCIM provisioning and billing; a replay harness to measure detection
precision and recall.
