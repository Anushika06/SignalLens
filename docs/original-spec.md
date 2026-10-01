# Original Product Specification (as received, 28 Sep 2026)

> Kept verbatim for reference. The reviewed and amended version of this specification is
> `00-SPEC-REVIEW.md`; the implemented design is `02-TECHNICAL.md`.

---

PRODUCT SPECIFICATION — Autonomous Business Intelligence Agent

## 1. Product

Build a SaaS product that acts as an always-on intelligence analyst for businesses.

A user should be able to say:

"I want to monitor Razorpay."

or:

"Monitor our competitors, pricing, product launches and regulatory changes."

The system autonomously understands the request, researches the company/domain, discovers relevant entities and information sources, creates a monitoring configuration, establishes a baseline of the current state, and then continuously monitors for meaningful changes.

When a potential change is detected, the system determines whether it is relevant, investigates it across multiple sources, resolves conflicting information where possible, assesses its business significance, updates its persistent knowledge, and presents an evidence-backed intelligence item to the appropriate user/team.

The system should be domain-agnostic: fintech, SaaS, pharma, manufacturing, cybersecurity, retail, etc.

## 2. Core User Problem

Businesses have fragmented information about competitors, markets, regulations, technologies and industry developments across websites, news, reports, APIs, GitHub, documents and other sources.

The problem is not merely finding information.

The real problem is:

"What materially changed, is it actually true, why does it matter to us, and who needs to know?"

Today this requires repeated manual research and monitoring.

The product replaces that repetitive monitoring workflow with an autonomous agent.

## 3. Primary Users / ICP

Users: Strategy teams · Product managers · Competitive intelligence analysts · Business development teams · Market research teams · Corporate strategy · Regulatory/compliance teams · Founders/executives

Typical Buyer: Head of Strategy · VP Strategy · CPO · Competitive Intelligence lead · Business/Market Intelligence lead

Core JTBD: Keep me continuously informed about material changes in the external environment relevant to my business without requiring me to manually monitor dozens of sources.

Secondary JTBDs:

- "Tell me what changed since I last checked."
- "Show me evidence that this actually happened."
- "Explain why this matters."
- "Remember what we've learned."
- "Don't flood me with irrelevant alerts."
- "Send important developments to the people responsible for them."

## 4. The Complete Workflow

The workflow is the product.

### PHASE 1 — Initial Setup

**1. User Request** — Example: "I want to monitor Razorpay." The user can also specify: "Monitor Razorpay's pricing, products, partnerships and regulatory developments."

**2. Intent & Domain Understanding Agent** — The agent determines: What company/entity is being monitored? What industry/domain is it in? What are the important entities? What areas are likely relevant? What does the user appear to care about?

```
Razorpay
↓
Fintech
↓
Products
Pricing
Partnerships
Funding
Regulation
Technology
Executives
```

**3. Configuration & Planning** — The system autonomously: discovers relevant sources, identifies entities, identifies attributes to monitor, creates a domain/monitoring model, determines source priorities, proposes monitoring frequencies.

The user gets a human approval step: "Here's what I propose monitoring." User can: Approve / Edit / Remove / Add. This is the first important human-in-the-loop point.

**4. Monitoring Configuration** — Create a persistent monitoring specification.

```json
{
  "company": "Razorpay",
  "areas": ["products", "pricing", "partnerships", "regulation", "funding"],
  "sources": [
    { "type": "official", "priority": "high" },
    { "type": "news", "priority": "medium" }
  ]
}
```

This configuration becomes the system's long-term understanding of what matters to this user.

**5. Initial Research / Baseline** — The agent performs deeper research. It: collects information, extracts facts, normalizes them, identifies entities, links relationships, stores evidence, creates the initial state/baseline.

```
Razorpay
│
├── Products
│   ├── Payment Gateway
│   ├── RazorpayX
│   └── ...
│
├── Pricing
│   ├── Domestic Cards → 2.0%
│   └── ...
│
├── Partnerships
├── Funding
└── Regulatory
```

The system now has a Version 1 representation of the external world.

### PHASE 2 — Continuous Monitoring

**6. Scheduler** — Sources are checked according to their nature. News → frequently. Regulatory sources → frequently. Official website → periodically. GitHub → periodically. Reports → when available. Do not blindly crawl everything continuously. The scheduler manages source-specific monitoring.

**7. Data Collection Agents** — The system fetches the latest information. Logical components: Source Scout (finds/fetches relevant new material), Extraction Agent (extracts structured information), Normalization Agent (converts information into consistent formats), Entity Resolution Agent (determines that "Razorpay Payments Pvt Ltd" and "Razorpay" refer to the same entity).

**8. Comparison & Change Detection** — This is the heart of the system. Compare CURRENT STATE vs PREVIOUS STATE. Detect: numerical changes, pricing changes, product changes, new partnerships, new executives, funding, regulatory changes, new technologies, textual/structural changes. But: a detected difference is not automatically an intelligence event.

**9. Materiality / Relevance Filtering** — Before spending expensive agent reasoning on something: Potential change → Is it meaningful? → NO → ignore/store; YES → investigate. Examples: Ignore — website footer changed. Investigate — pricing changed from 2.0% → 1.8%. Investigate urgently — regulatory authority introduced a rule affecting the company's product. This prevents alert fatigue.

**10. Investigation & Verification** — For every material potential change, the agent autonomously decides: "Do I have enough evidence?" If not, it investigates. It can: search the web, open websites, inspect official documentation, read PDFs, inspect GitHub, search news, compare historical information, search additional sources. It should actively look for confirmation and contradiction.

**11. Evidence Model** — Every important claim must maintain provenance.

```
CLAIM
"Domestic card fee changed from 2.0% to 1.8%"
       │
       ├── Official pricing page
       ├── Official announcement
       └── Independent news source
```

Instead of blindly saying "Confidence: 94%", use evidence states such as: Confirmed · Corroborated · Single source · Conflicting · Unverified. This makes the system trustworthy.

**12. Investigation & Impact Analysis** — Once the change is verified the agent determines: What changed? (Razorpay reduced domestic card transaction fees from 2.0% to 1.8%.) Why does it matter? (Potential competitive pricing pressure.) Who should care? (Product + Strategy.) What should be considered? (Review current pricing assumptions.) The system should distinguish evidence-backed facts from agent-generated interpretation.

**13. Intelligence Output** — Every meaningful event should become an Intelligence Card. Example: Pricing Change · What changed: 2.0% → 1.8% · Why it matters: potential competitive pricing pressure in the payments market · Affected areas: Product · Strategy · Evidence: official pricing page, official announcement, independent source · Evidence status: Corroborated · Detected: 28 Sep 2026 · Previous state: 2.0% · Current state: 1.8%.

**14. Persistent Knowledge / World State** — This is critical. Do not make this just a RAG chatbot. The system maintains historical state.

```
Razorpay → Pricing → Domestic Card Fee
Sep 01 → 2.2%
Sep 15 → 2.0%
Sep 28 → 1.8%
```

Each state stores: value, timestamp, source, evidence, related event. Therefore the system can answer "What changed?" without starting research from zero every time.

**15. User Dashboard** — Company overview (Razorpay ● Monitoring; monitored: products, pricing, partnerships, regulation, funding). Recent changes (🔴 Pricing changed 8m ago · 🟡 Product update 1d ago · 🔵 Partnership 2d ago). Clicking an event opens the intelligence card and evidence.

**16. Human-in-the-Loop** — The system should be autonomous for research and analysis, but humans remain in control of consequential actions. Autonomous: search, browse, extract, compare, investigate, verify, analyze, update knowledge, generate intelligence, notify internally. Human approval initially required for: sending external emails, changing business systems, publishing reports externally, taking consequential actions. The user should always be able to inspect: what did the agent find? why did it think this mattered? what evidence supports it?

**17. Feedback Loop** — Intelligence → user feedback → relevant / not relevant → monitoring preferences improve → future detection improves. This allows the product to learn "the user doesn't care about minor product-page changes" but "the user always wants regulatory changes immediately". That makes the monitoring increasingly personalized.

**18. Our Agent Runtime** — Build our own domain-specific agent runtime, not a generic Hermes clone. Core abstractions: Agent, Task, Run, Tool, Observation, Evidence, Claim, Investigation, Decision, Event, WorldState. Logical agents: Planner → Scout → Analyst → Verifier → Impact Analyst → Router. These are logical capabilities, not necessarily six independent LLM processes. The runtime should allow an agent to: observe state, decide what to do, select a tool, execute it, inspect the result, decide whether more investigation is needed, update state, terminate when sufficient evidence exists. That is the actual agentic core.

**19. Tech Stack** — Frontend: Next.js, TypeScript, Tailwind, shadcn/ui. Backend: Python, FastAPI, Pydantic. Agent runtime: custom Python orchestration, tool registry, async execution, agent/task state, retry/budget controls. Database: PostgreSQL, pgvector, JSONB. Background execution: Redis, Celery initially. Browser: Playwright. Search: one provider initially (Tavily / Exa / Serper). Documents: PDF extraction, HTML extraction, structured parsers. LLM: provider abstraction (OpenAI, Gemini, Anthropic). Use cheaper models for extraction/classification and stronger models for investigation/reasoning.

**20. Core Database Model** — At minimum: organizations, users, workspaces, companies, entities, entity_relationships, monitoring_policies, sources, source_snapshots, facts, claims, evidence, state_versions, events, investigations, intelligence_reports, notifications, user_feedback. The key relationship is: Entity → State → Change/Event → Claim → Evidence → Intelligence.

**21. What the Product Is NOT** — Not a generic ChatGPT clone, a simple RAG chatbot, a news aggregator, a web scraper, an automated newsletter, "six LLM agents talking to each other", or merely Hermes with a UI. It is a persistent, autonomous system for maintaining an evidence-backed understanding of a company's changing external environment.

**22. The Universal Demo** — The onboarding should work for any company. "I want to monitor Stripe." → system learns Stripe → creates monitoring model → baseline → continuous monitoring. Then "I want to monitor Tata Motors." — same system; it discovers automotive, products, EVs, pricing, factories, partnerships, regulation, competitors, technology. Then "I want to monitor Pfizer." — it discovers a completely different domain model. That is the proof that the product is real. Razorpay is simply a clean demonstration because the changes are easy to understand.
