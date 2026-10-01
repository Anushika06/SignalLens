# SignalLens — web frontend

The web app for **SignalLens**, an always-on analyst that tells a business what materially
changed in its external environment, whether it is actually true, why it matters *to that
business*, and who needs to know.

A user types "I want to monitor Razorpay"; an agent researches the company and proposes a
monitoring plan the user approves; SignalLens builds a baseline world state, watches pages and
news, filters noise, verifies material changes with quoted evidence, explains their impact, and
routes intelligence cards to the right teams. Feedback becomes visible, reversible learned rules.

- API contract (source of truth): [`../docs/api-contract.md`](../docs/api-contract.md)
- Product decisions: [`../docs/00-SPEC-REVIEW.md`](../docs/00-SPEC-REVIEW.md)

## Stack

Next.js 16 (App Router, `src/`, TypeScript strict) · Tailwind CSS 4 · shadcn/ui (Radix base) ·
SWR for data fetching and polling · lucide-react · date-fns · next-themes (light/dark/system) ·
sonner (toasts).

## Running it

Requires Node.js 20.9+ (22 recommended).

```bash
npm install
npm run dev            # http://localhost:3000, API proxied to http://127.0.0.1:8000
```

The browser only ever talks to this app's origin. `next.config.ts` rewrites `/api/*` to the
backend, so the backend's httpOnly `sl_session` cookie is first-party and no CORS setup is
needed. Point the proxy elsewhere with `SIGNALLENS_API_URL`:

```bash
SIGNALLENS_API_URL=http://127.0.0.1:8000 npm run dev      # bash / zsh
$env:SIGNALLENS_API_URL="http://127.0.0.1:8000"; npm run dev   # PowerShell
```

| Variable | Default | Notes |
|---|---|---|
| `SIGNALLENS_API_URL` | `http://127.0.0.1:8000` | Backend base URL (without `/api`). Rewrites are resolved when `next dev` starts and **at build time** for `next build`, so set it before building. |

Demo account (seeded by the backend's `signallens seed-demo`, also accepted by the mock):
`demo@signallens.app` / `signallens-demo`.

### Scripts

| Script | What it does |
|---|---|
| `npm run dev` | Development server on port 3000 |
| `npm run build` / `npm start` | Production build / serve it |
| `npm run lint` | ESLint (Next.js core-web-vitals + TypeScript rules) |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run mock` | Dependency-free mock API on port 8010 (see below) |
| `npm run dev:mock` | Mock API **and** `next dev` pointed at it, in one command (any OS) |

## Working without the backend: the mock API

`scripts/mock-api.mjs` is a dependency-free Node HTTP server that implements every endpoint in
the contract with realistic, in-memory fixtures. It exists only for local development and
visual checks — the app contains no mock data.

```bash
npm run dev:mock                                   # both servers; Ctrl+C stops both
# or, in two terminals:
npm run mock                                       # API on http://127.0.0.1:8010
SIGNALLENS_API_URL=http://127.0.0.1:8010 npm run dev
```

Sign in with `demo@signallens.app` / `signallens-demo` (or create any account). The fixtures
tell one coherent story: **Kivo Payments**, a payment gateway for Indian SMBs, watching
Razorpay.

| Fixture | Id / how to reach it |
|---|---|
| Workspace A — "Razorpay watch", monitoring, rich data | `/w/00000000-0000-4000-8000-001000000001` |
| Headline card — "Razorpay introduces 0% platform fee for first 90 days" | `…/intel/00000000-0000-4000-8000-004000000001` |
| Workspace B — Stripe plan awaiting approval (plan review) | `/w/00000000-0000-4000-8000-001000000002/plan/00000000-0000-4000-8000-002000000002` |
| Workspace C — Tata Motors plan still researching (live planner view) | `/w/00000000-0000-4000-8000-001000000003/plan/00000000-0000-4000-8000-002000000003` (turns into a reviewable plan ~3 min after the mock starts) |
| A running investigation (live run trace, ~2 min) | `…/runs/00000000-0000-4000-8000-003000000012` |
| Demo lab pages | `acme-pay-pricing` (change the fee → a pricing card appears ~4 s later), `northwind-newsroom` |

Also covered: RBI regulatory item, partnership news, conflicting and unverified reports,
historical (backfilled) reports, filtered changes (tiers 0–2), learned rules (one already
undone), pending and decided approvals, failing sources and a new check appearing every ~20 s.
New workspaces created through `/new` get a planner run that finishes in ~20 s; include the
word "fail" in the request to see the failure path.

| Mock env var | Effect |
|---|---|
| `MOCK_PORT` | Port (default `8010`) |
| `MOCK_NO_KEYS=1` | Reports no LLM/search keys, so the "API keys not configured" banner shows |
| `MOCK_LATENCY_MS` | Artificial latency per request (default `120`) |

State is in memory and resets when the mock restarts.

## Screens

| Route | Screen | Main endpoints |
|---|---|---|
| `/login` | Sign in / create account; returns to `?next=` | `POST /auth/login`, `POST /auth/signup`, `GET /auth/me` |
| `/` | Workspace list (status, subjects, unread) | `GET /workspaces` |
| `/new` | Onboarding: company profile + teams, then "what should SignalLens monitor?" | `POST /workspaces`, `POST /workspaces/{wid}/plans` |
| `/w/[wid]/plan/[pid]` | Live planner view while planning; plan review and approval (the first human-in-the-loop step); failure/retry | `GET /plans/{pid}` (2 s poll), `GET /runs/{run_id}` (2 s poll), `POST …/approve`, `POST …/reject`, `POST /plans` |
| `/w/[wid]` | Dashboard: subjects, intelligence with a "since your last visit" divider, attention funnel, live agent activity, sources health, pending approvals | `GET /overview` (5 s poll), `POST /seen` (after 3 s), `GET /workspaces/{wid}` |
| `/w/[wid]/intel` | Intelligence feed with severity/area/entity/evidence filters and Live / Historical / All | `GET /reports` (cursor pagination), `GET /policy`, `GET /entities` |
| `/w/[wid]/intel/[rid]` | Intelligence card: what changed, agent assessment, evidence, fact history, detection, investigation trace, feedback, external sharing | `GET /reports/{rid}`, `POST …/read`, `POST …/feedback`, `POST …/share`, `GET /runs/{id}` |
| `/w/[wid]/world` | World state: entities grid | `GET /entities` |
| `/w/[wid]/world/[eid]` | Entity: facts (history drawer), relationships, live + historical timeline | `GET /entities/{eid}`, `GET /facts/{fid}` |
| `/w/[wid]/monitoring` | Policy, areas, sources (check now, pause, recent checks), learned rules (undo), filtered changes | `GET /policy`, `GET/PATCH /sources`, `POST …/check`, `GET …/checks`, `GET/DELETE /learned-rules`, `GET /filtered` |
| `/w/[wid]/runs` | Agent runs | `GET /runs` |
| `/w/[wid]/runs/[runId]` | Run trace: usage, budget, step timeline with raw input/output | `GET /runs/{runId}` (2 s poll while running) |
| `/w/[wid]/approvals` | Pending and decided external actions; approve/reject with a note | `GET /approvals`, `POST …/decide` |
| `/w/[wid]/settings` | Company profile and teams (areas, members, Slack webhook — write-only) | `PATCH /workspaces/{wid}`, `GET/POST/PATCH/DELETE /teams` |
| `/lab` | Demo lab: edit fictional sandbox pages with live preview | `GET/PUT /sandbox/pages` |

Every `/w/[wid]/*` page shares the workspace shell: a sidebar (workspace switcher, navigation
with unread and pending-approval badges, the demo lab when `sandbox_enabled`, user menu) that
becomes a sheet below 768 px, a top bar with the page title and a notifications inbox, and a
banner when the backend has no LLM or search API keys configured.

## How the code is organised

```
src/
  app/                    Routes only. Each page.tsx awaits params and renders one screen.
  components/
    ui/                   shadcn/ui primitives (generated; lightly adjusted use-mobile hook)
    common/               Badges, relative time, empty/error states, headers, JSON view, links…
    shell/                Workspace sidebar + top bar, simple shell for non-workspace pages
    <feature>/            One folder per screen area: dashboard, intel, report, plan,
                          onboarding, world, monitoring, runs, approvals, settings, lab…
  lib/
    types.ts              Contract types, transcribed section by section
    api.ts                Typed fetch client, URL builders (`paths`), one function per write
    hooks.ts              SWR hooks per resource, with the contract's polling intervals
    labels.ts             Product vocabulary: every enum → label, colour tone, icon, explanation
    format.ts             Dates, numbers, durations, intervals
    routes.ts             Every in-app URL
scripts/                  Mock API and the dev:mock launcher (development only)
```

Conventions worth knowing:

- **Reads** use the hooks in `lib/hooks.ts`; **writes** use `api.*` from `lib/api.ts`, then
  `revalidate(prefix)` to refresh what they touched. A 401 anywhere sends the user to
  `/login?next=…`.
- **Severity and evidence status are separate axes** and always rendered with separate badges
  (`SeverityBadge`, `EvidenceBadge`); colours come from `lib/labels.ts` and every badge carries
  text, so colour is never the only signal.
- Agent interpretation ("why it matters") is always labelled as an assessment, distinct from
  the facts in "what changed".
- Links built from fetched content go through `safeHref`: only http(s) URLs become clickable.
- Light and dark themes use CSS variables (`src/app/globals.css`); the accent is indigo
  (`--primary` for fills, `--brand` for text).

## Contract notes and assumptions

Where the contract is silent or ambiguous, the frontend assumes the following (each is easy to
change in one place):

- **Share body.** `POST /reports/{rid}/share` has no documented body; the UI sends
  `{recipient, note?}` (`ShareReportInput` in `lib/types.ts`). The recipient is free text.
- **"All areas".** The default Strategy team owns "all areas", but `TeamInput.areas` has no way
  to say so. `areas: []` is treated and displayed as "All areas". Onboarding omits `teams` (and
  `profile`) unless the user changed them, so backend defaults apply.
- **Feedback reason `other`.** It is in the enum but not in the chip lists; it is offered as
  "Other" for both verdicts, with the note field.
- **Event links.** Activity items (and run subjects) can link to an `event`, which has no page
  of its own; they open Monitoring → Filtered changes with that event highlighted.
- **Notifications.** There is no endpoint to mark one notification read, so the bell lists
  unread items and offers "Mark all as read"; opening a report marks the report read.
- **Missing policy / overview.** `GET /policy` returning 404 means "no active plan yet"; a
  404/409 from `GET /overview` before approval shows the workspace's status callouts instead of
  an error.
- **Plan drafts.** Edits during plan review are autosaved with `PUT /plans/{pid}/spec`; approval
  still sends the full edited spec, with sources and tracked values of turned-off entities or
  areas explicitly set to `enabled: false`.
- **Planner run.** While a plan is `planning`, its run is polled even if the first request fails
  (the worker may not have created it yet).
- **Decision notes.** The note sent with `POST /approvals/{aid}/decide` is not part of
  `Approval`, so it cannot be shown after the decision.
- **Funnel.** `filtered` is read as the subset of `changes` that was dropped; the dashboard shows
  checks as a headline number and plots the other stages on one scale of changes.
