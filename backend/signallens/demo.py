"""Demo data: a demo login and the demo lab (fictional company pages you can edit live).

Nimbus Pay is fictional. Its pages are served from the database through the
``sandbox://`` scheme, so a presenter can change a price and watch SignalLens detect,
verify, assess and route the change — without staging anything about a real company.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from signallens.api.security import hash_password
from signallens.db.models import (
    MonitoringPolicy,
    Organization,
    SandboxPage,
    Team,
    User,
    Workspace,
    WorkspaceMember,
)
from signallens.pipeline.activation import activate_plan
from signallens.plan import MonitoringPlan, PlanArea, PlanAttribute, PlanDomain, PlanEntity, PlanSource

DEMO_EMAIL = "demo@signallens.app"
DEMO_PASSWORD = "signallens-demo"

PRICING_HTML = """<!doctype html>
<html lang="en"><head><title>Pricing | Nimbus Pay</title>
<meta name="description" content="Simple, transparent pricing for Nimbus Pay payment gateway."></head>
<body>
<nav><a href="/">Home</a> <a href="/products">Products</a> <a href="/pricing">Pricing</a> <a href="/login">Log in</a></nav>
<div class="cookie-banner" id="cookie-consent">We use cookies to improve your experience. <button>Accept</button></div>
<main>
  <h1>Simple, transparent pricing</h1>
  <p>No setup fee. No annual maintenance fee. Pay only for successful transactions.</p>
  <section>
    <h2>Standard plan</h2>
    <p>Accept domestic cards, UPI, netbanking and wallets at a flat 2% per successful transaction.</p>
    <table>
      <tr><th>Payment method</th><th>Fee per transaction</th></tr>
      <tr><td>Domestic cards, UPI, netbanking, wallets</td><td>2%</td></tr>
      <tr><td>International cards</td><td>3.5%</td></tr>
      <tr><td>Corporate credit cards</td><td>2.9%</td></tr>
    </table>
    <p>Settlement: T+2 working days. GST of 18% applies on fees.</p>
  </section>
  <section>
    <h2>Enterprise</h2>
    <p>Processing more than &#8377;50 lakh a month? Talk to us for custom pricing and T+1 settlement.</p>
  </section>
</main>
<footer><p>&copy; 2026 Nimbus Pay Technologies (fictional demo company). All rights reserved.</p></footer>
</body></html>"""

PRODUCTS_HTML = """<!doctype html>
<html lang="en"><head><title>Products | Nimbus Pay</title></head>
<body>
<nav><a href="/">Home</a> <a href="/pricing">Pricing</a></nav>
<main>
  <h1>Everything you need to accept payments</h1>
  <ul>
    <li><strong>Payment Gateway</strong> - accept cards, UPI, netbanking and wallets online.</li>
    <li><strong>Payment Links</strong> - share a link on chat or email and get paid.</li>
    <li><strong>Subscriptions</strong> - recurring billing with UPI AutoPay and card mandates.</li>
  </ul>
</main>
<footer><p>&copy; 2026 Nimbus Pay Technologies (fictional demo company).</p></footer>
</body></html>"""

SANDBOX_PAGES = {
    "nimbus-pay-pricing": ("Nimbus Pay — Pricing (fictional)", PRICING_HTML),
    "nimbus-pay-products": ("Nimbus Pay — Products (fictional)", PRODUCTS_HTML),
}


async def seed_demo_user(s: AsyncSession) -> tuple[Organization, User, bool]:
    user = (await s.execute(select(User).where(User.email == DEMO_EMAIL))).scalar_one_or_none()
    if user is not None:
        return await s.get(Organization, user.org_id), user, False
    org = Organization(id=uuid.uuid4(), name="SignalLens Demo")
    user = User(id=uuid.uuid4(), org_id=org.id, email=DEMO_EMAIL, name="Demo Analyst",
                password_hash=hash_password(DEMO_PASSWORD))
    s.add_all([org, user])
    await s.flush()
    return org, user, True


async def seed_sandbox(s: AsyncSession, *, reset: bool = False) -> int:
    n = 0
    for slug, (title, html) in SANDBOX_PAGES.items():
        page = await s.get(SandboxPage, slug)
        if page is None:
            s.add(SandboxPage(slug=slug, title=title, html=html))
            n += 1
        elif reset:
            page.title, page.html = title, html
            n += 1
    await s.flush()
    return n


def lab_plan() -> MonitoringPlan:
    return MonitoringPlan(
        summary="Demo lab: monitor the fictional payment gateway Nimbus Pay's pricing and products.",
        domain=PlanDomain(industry="Financial technology", sector="Digital payments", geographies=["India"],
                          rationale="Fictional company used to demonstrate live change detection."),
        entities=[PlanEntity(ref="nimbus-pay", name="Nimbus Pay", kind="company", role="subject",
                             official_domains=["nimbuspay.example"], description="Fictional payment gateway (demo).",
                             reason="Demo subject")],
        areas=[
            PlanArea(key="pricing", label="Pricing & fees", importance="critical", reason="Fee changes move deals",
                     route_to=["Strategy", "Product"]),
            PlanArea(key="products", label="Products", importance="high", reason="New products change positioning",
                     route_to=["Product"]),
        ],
        attributes=[
            PlanAttribute(key="pricing.standard_domestic_fee", entity_ref="nimbus-pay", area="pricing",
                          label="Standard domestic transaction fee", value_type="percent",
                          hint="The per-transaction fee on the Standard plan for domestic cards, UPI, netbanking "
                               "and wallets, including any introductory offer or condition.",
                          source_refs=["nimbus-pricing"]),
            PlanAttribute(key="pricing.international_card_fee", entity_ref="nimbus-pay", area="pricing",
                          label="International card fee", value_type="percent",
                          hint="Per-transaction fee for international cards.", source_refs=["nimbus-pricing"]),
            PlanAttribute(key="pricing.settlement_time", entity_ref="nimbus-pay", area="pricing",
                          label="Standard settlement time", value_type="text",
                          hint="Settlement cycle for the Standard plan, e.g. T+2.", source_refs=["nimbus-pricing"]),
        ],
        sources=[
            PlanSource(ref="nimbus-pricing", kind="page", url="sandbox://nimbus-pay-pricing", entity_ref="nimbus-pay",
                       areas=["pricing"], authority="official", priority="high", check_every_hours=1,
                       reason="Official pricing page (demo lab)"),
            PlanSource(ref="nimbus-products", kind="page", url="sandbox://nimbus-pay-products", entity_ref="nimbus-pay",
                       areas=["products"], authority="official", priority="medium", check_every_hours=6,
                       reason="Official products page (demo lab)"),
        ],
        open_questions=[],
    )


async def seed_lab_workspace(s: AsyncSession, org: Organization, user: User) -> Workspace | None:
    existing = (await s.execute(select(Workspace).where(Workspace.org_id == org.id,
                                                        Workspace.name == "Demo lab: Nimbus Pay"))).scalar_one_or_none()
    if existing is not None:
        return None
    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Demo lab: Nimbus Pay", status="setup", profile={
        "company_name": "Orbit Payments", "website": None,
        "description": "Payment gateway for Indian SMBs and D2C brands (fictional).",
        "products": ["Payment gateway", "Payment links"], "markets": ["India", "SMB merchants"],
        "competitors": ["Nimbus Pay"], "relationship_to_subjects": "Nimbus Pay is a direct competitor.",
    })
    s.add(ws)
    await s.flush()
    for name, areas in (("Strategy", []), ("Product", ["pricing", "products"]), ("Sales & BD", ["pricing"])):
        s.add(Team(id=uuid.uuid4(), workspace_id=ws.id, name=name, areas=areas))
    s.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role="owner"))
    policy = MonitoringPolicy(id=uuid.uuid4(), workspace_id=ws.id, version=1, status="pending_approval",
                              request_text="Monitor Nimbus Pay's pricing and products (demo lab).",
                              created_by=user.id)
    s.add(policy)
    await s.flush()
    await activate_plan(s, policy=policy, plan=lab_plan(), user_id=user.id)
    return ws
