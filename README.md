# SignalLens

**An always-on intelligence analyst for businesses.** Tell it "I want to monitor Razorpay".
It researches the company, proposes what to watch (you approve), builds a memory of the
current state — including a year of history from web archives — and then keeps watching.
When something changes, it decides whether it matters, verifies it with quoted evidence,
explains why it matters **to your company**, and sends it to the team that owns it.

*Know what changed, whether it's true, and why it matters to you.*

---

## Documentation

| Document | What it is |
|---|---|
| [`docs/00-SPEC-REVIEW.md`](docs/00-SPEC-REVIEW.md) | Review of the original specification: what was right, the 18 changes made, scope, industry domain, decision log |
| [`docs/01-PRODUCT.md`](docs/01-PRODUCT.md) | Product explainer: problem, ICP and personas, jobs to be done, how it works, trust, competition, business model, roadmap, FAQ |
| [`docs/product-explainer.html`](docs/product-explainer.html) | The same story as a single visual page (open in a browser) |
| [`docs/02-TECHNICAL.md`](docs/02-TECHNICAL.md) | Architecture, agent runtime, pipelines, evidence model, data model, security, cost, scaling |
| [`docs/03-USER-WORKFLOWS.md`](docs/03-USER-WORKFLOWS.md) | Step-by-step user workflows with where the agent decides and where a human approves |
| [`docs/04-IMPLEMENTATION-STATUS.md`](docs/04-IMPLEMENTATION-STATUS.md) | Exactly what is built, tested and verified — and what is not |
| [`docs/05-DEMO-SCRIPT.md`](docs/05-DEMO-SCRIPT.md) | 2–3 minute demo video script and shot list |
| [`docs/06-SUBMISSION.md`](docs/06-SUBMISSION.md) | Submission pack: name, problem, solution, architecture, stack, demo, Q&A |
| [`docs/pitch-deck.html`](docs/pitch-deck.html) | Pitch deck (open in a browser; print to PDF) |
| [`docs/api-contract.md`](docs/api-contract.md) | Frontend ↔ backend API contract |
| [`docs/original-spec.md`](docs/original-spec.md) | The original specification, verbatim |

---

## Repository

```
backend/     Python 3.12 · FastAPI · custom agent runtime · PostgreSQL · job queue + worker
frontend/    Next.js · TypeScript · Tailwind · shadcn/ui
docs/        product, technical and submission documentation
```

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
cp .env.example .env        # then add ONE model key and ONE search key (see below)
uv sync
uv run signallens migrate
uv run signallens seed-demo --lab
uv run signallens dev       # API + background worker on http://127.0.0.1:8000
```

`uv run signallens config` shows which providers are active (it never prints keys).

| Needed for | Put in `backend/.env` (any one of each) |
|---|---|
| Planning, extraction, investigation, impact analysis | `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `GEMINI_API_KEY` |
| News monitoring and web search | `TAVILY_API_KEY`, `EXA_API_KEY` or `SERPER_API_KEY` |

Without keys the app runs, pages are fetched and snapshotted, and the UI shows a banner; the
agents need a model key to plan, extract and investigate.

Production-style run: `uv run signallens api` and `uv run signallens worker` as separate
processes (scale workers horizontally).

### 3. Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:3000
```

Sign in with **demo@signallens.app / signallens-demo**, or create an account.

- **Demo lab:** the *Demo lab: Nimbus Pay* workspace monitors a fictional company's pages
  served by SignalLens itself. Edit them under *Demo lab*, press *Check now* on the source,
  and watch detection → verification → card → routing happen live.
- **Real company:** create a workspace, describe your company, and type
  "I want to monitor Razorpay" (or any company).

### 4. Tests

```bash
cd backend
uv run pytest -q            # unit + integration (integration uses the signallens_test database)
uv run ruff check signallens tests

cd ../frontend
npm run build && npm run lint
```

---

## How it works (one paragraph)

A **planner agent** researches the request and proposes a monitoring plan with a reason and a
live check for every source; a human approves it. SignalLens records a **baseline** of tracked
facts (with verified quotes) and **replays a year of archived versions** through the same
pipeline to reconstruct history. A **scheduler** re-checks sources; most checks stop at a
content hash, volatile noise is filtered deterministically, and a fast model judges what
remains against the user's priorities. Material changes go to a **verification agent** that
may only quote pages it actually opened; code checks each quote and **computes** the evidence
status. An **impact analyst** writes a card that separates facts from assessment, grounded in
the user's company profile, and a **router** delivers it to the right team — now or in the
daily digest. Feedback becomes **visible, reversible rules**. External actions wait for
**human approval**. Details: [`docs/02-TECHNICAL.md`](docs/02-TECHNICAL.md).
