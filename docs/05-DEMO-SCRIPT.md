# SignalLens — Demo Video Script (2 min 50 s)

**Goal of the video:** show, on real data, an agent that plans its own monitoring, builds a
memory of the world, notices what changed, proves it with evidence, explains why it matters
to *this* company, routes it to the right people — and learns from feedback, with a human
in control of anything consequential.

**Honesty rules for the recording (non-negotiable):**
1. Razorpay segments use real, live and archived public pages. Nothing about Razorpay is
   staged or edited.
2. The live "change happens right now" moment uses **Nimbus Pay**, a fictional company in
   SignalLens's demo lab. Say so on screen.
3. Time compression (the agent's work takes minutes) is shown with an on-screen
   "⏩ sped up" label.

---

## Before recording

| Item | Setting |
|---|---|
| Keys | One model key + one search key in `backend/.env` (`signallens config` shows both configured) |
| Data | `signallens seed-demo --lab` done; the Razorpay workspace created **30–40 minutes before** recording so baseline + 12-month backfill have finished |
| Your company profile (Razorpay workspace) | Name *Orbit Payments* (fictional), "Payment gateway for Indian SMBs and D2C brands", competitors *Razorpay, Cashfree*, relationship "Razorpay is our main competitor" |
| Browser | 1440×900 window, 110% zoom, light theme, bookmarks bar hidden, notifications off |
| Tabs | (1) SignalLens dashboard, (2) Demo lab, (3) a clean tab for onboarding |
| Recording | 1080p, cursor highlight on, mic with noise suppression; record each scene separately and edit |

**Dry run first.** The real historical change used in Scene 3 was found on 28 Sep 2026 by
replaying archived captures of `razorpay.com/pricing/`: the "0%* platform fees for first 90
days" offer is absent from the 9 Mar 2026 capture and present in the 6 Jul 2026 capture.
Confirm that your workspace's *Historical* feed shows it before recording; if the archive or
the model phrases it differently, use the wording the product actually shows.

---

## Scene 1 — The problem (0:00–0:15)

**Screen:** SignalLens logo on a plain background → quick cut of a messy spreadsheet of
competitor links and 40 open browser tabs.

**Voiceover:**
> "Every strategy team checks the same competitor pages, news and regulator sites every week
> — and still misses the change that matters. The hard part isn't finding information. It's
> knowing what changed, whether it's true, and why it matters to *you*."

---

## Scene 2 — Ask in plain English; the agent plans (0:15–0:45)

**Screen:** New workspace → Step 1 shows the Orbit Payments profile (already filled) →
Step 2, type **"I want to monitor Razorpay"** → submit. The plan page shows the planner at
work: searching, opening razorpay.com, opening the pricing page, checking the RBI site.
⏩ sped up label.

**Voiceover:**
> "I tell SignalLens who we are — Orbit Payments — and what I want watched. An agent takes it
> from there: it identifies the company, finds its official pricing, product and news
> pages, works out that the Reserve Bank of India regulates it, and picks competitors."

**Screen:** Plan review. Hover a source to show its *reason* and the live ✓ validation
(reachable, allowed by robots.txt). Toggle one source off, change news frequency, click
**Approve & start monitoring**.

**Voiceover:**
> "Nothing is monitored until I approve. Every source comes with a reason and a live check —
> and I can edit anything."

---

## Scene 3 — Day-one memory, from real history (0:45–1:15)

**Screen:** World state → Razorpay → Pricing facts, each with its current value and a
✓ Confirmed badge, then the fact's history timeline. Switch the intelligence feed to
**Historical**: open the card for the 90-day 0% platform-fee offer. Show *Previous → Current*,
the archived evidence quotes, and the date range.

**Voiceover:**
> "It doesn't start from zero. It reads today's pages into a structured memory, then replays
> a year of Razorpay's pricing page from the Internet Archive. Here's a real change it
> reconstructed: sometime between March and July, Razorpay started offering new merchants 0%
> platform fees for their first 90 days. Four archived captures were empty shells — the
> agent skipped them instead of raising false alarms."

(Optional one-second cut: the backfill run trace showing "Skipped capture … 0 words".)

---

## Scene 4 — A change happens now: detect → verify → explain (1:15–2:05)

**Screen:** Demo lab tab, banner "Nimbus Pay is a fictional company". Edit the pricing page:
change **2%** to **1.8%** and add *"New merchants pay 0% platform fee for the first 90 days."*
Save. Switch to the *Demo lab: Nimbus Pay* workspace → Monitoring → **Check now**.

**Voiceover:**
> "To show the live loop on demand, here's our demo lab — a fictional competitor, Nimbus Pay.
> I'll cut its fee and add an offer."

**Screen:** Dashboard: activity feed ticks — "Checked… changes found", "Investigating…",
"New intelligence". The **attention funnel** updates (checks → changes → filtered →
material → published). ⏩

**Voiceover:**
> "It compares the page with what it knew. A copyright-year change is ignored for free. Two
> changes are material, so an investigator agent verifies them."

**Screen:** Open the pricing card. Point at: *What changed 2% → 1.8%* · **✓ Confirmed**
badge (tooltip: a primary source states it) · evidence quote with "quote verified" ·
**Why it matters — agent assessment** mentioning Orbit Payments' SMB business · routed to
Strategy and Product. Expand the investigation trace: decision → tool call → recorded
evidence → finish.

**Voiceover:**
> "Every card separates facts from interpretation. The status is computed by rules, not by
> the model: the agent may only quote pages it actually opened, and the quote is checked
> word for word. And because it knows who we are, it explains the impact on our SMB
> business — and sends it to the teams that own pricing."

---

## Scene 5 — It learns, and humans stay in control (2:05–2:35)

**Screen:** On a low-value card, click **Not relevant → Too minor**; on a second similar card,
same again. Toast: *"I now only alert on medium or higher…"*. Open Monitoring → Learned
rules → show the rule and the **Undo** button.

**Voiceover:**
> "Feedback turns into rules I can read — and undo."

**Screen:** On the pricing card, **Share externally…** → enter an advisor's email → toast
"Sent for approval". Approvals page → the pending item → Approve.

**Voiceover:**
> "Research and analysis are autonomous. Anything that leaves the company waits for a human."

---

## Scene 6 — Any company, any industry (2:35–2:50)

**Screen:** Two plan reviews side by side (prepared earlier): **Tata Motors** (areas: models &
launches, EV & technology, plants & capacity, pricing, regulation) and **Pfizer** (pipeline &
trials, approvals, pricing & access, manufacturing, legal & patents). End on the SignalLens
logo and tagline.

**Voiceover:**
> "Same product, a different domain model every time. SignalLens: know what changed, whether
> it's true, and why it matters to you."

---

## Fallbacks

| If… | Do this |
|---|---|
| The planner is slow | Record it earlier and speed it up; the trace is the proof |
| The archive is rate-limited during the backfill | Create the Razorpay workspace the day before |
| The historical card's wording differs | Read what the product shows; don't read this script's wording |
| No news event happens | Scene 4 does not depend on news; the demo lab is deterministic |
| A model call fails | The run trace shows the error; re-run with **Check now** |

## Shot list (for the editor)

| # | Time | Screen | Label on screen |
|---|---|---|---|
| 1 | 0:00 | Logo → spreadsheet/tabs montage | — |
| 2 | 0:15 | Onboarding + planner trace | "⏩ sped up" |
| 3 | 0:35 | Plan review, approve | "Human approval" |
| 4 | 0:45 | World state, fact history, historical card | "Real archived pages" |
| 5 | 1:15 | Demo lab edit | "Fictional company" |
| 6 | 1:30 | Dashboard activity + funnel | "⏩ sped up" |
| 7 | 1:45 | Card detail + investigation trace | "Evidence status is computed, not guessed" |
| 8 | 2:05 | Feedback → learned rule → undo | — |
| 9 | 2:20 | Share → approval | "Human in control" |
| 10 | 2:35 | Tata Motors / Pfizer plans, logo | Tagline |
