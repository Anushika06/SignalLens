"""Evidence tools for the verification agent.

``record_evidence`` is the only write an investigating agent can perform. It refuses
quotes that are not present in a page the agent opened during this run, classifies the
source with code (primary / independent / community), and returns the recomputed
evidence status — which the agent can read but never set.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from signallens.db.models import Evidence
from signallens.db.session import transaction
from signallens.domain.evidence import classify_source
from signallens.runtime.core import Observation, RunContext, Tool
from signallens.store.evidence import add_evidence, refresh_status
from signallens.util.text import quote_in_text


def original_url(archive_url: str) -> str:
    """``https://web.archive.org/web/<ts>/<original>`` → ``<original>`` (archived primary stays primary)."""
    parts = archive_url.split("/", 5)
    return parts[5] if len(parts) == 6 and parts[3] == "web" else archive_url


class RecordEvidenceArgs(BaseModel):
    url: str = Field(description="URL of a page you opened in this run")
    quote: str = Field(description="exact words copied from that page (a phrase or one or two sentences)")
    stance: Literal["supports", "contradicts", "context"]
    note: str | None = Field(None, description="optional: why this matters")


class RecordEvidenceTool(Tool):
    name = "record_evidence"
    description = ("Record a verbatim quote from an opened page as evidence for or against the claim. "
                   "Returns the recomputed evidence status.")
    Args = RecordEvidenceArgs
    side_effect = "internal_write"

    async def run(self, ctx: RunContext, args: RecordEvidenceArgs) -> Observation:
        doc = ctx.recall(args.url)
        if doc is None:
            return Observation.error("You have not opened this URL in this run. Open it with open_page first, "
                                     "then quote it.")
        if not quote_in_text(args.quote, doc.text):
            return Observation.error(f"Quote not found in the text of {doc.final_url}. Copy the exact words "
                                     "from the page (paraphrases are rejected).")
        source_class = classify_source(
            original_url(doc.final_url or doc.url) if doc.is_archive else (doc.final_url or doc.url),
            entity_domains=ctx.scratch.get("entity_domains", []),
            regulator_domains=ctx.scratch.get("regulator_domains", []),
            distrusted_publishers=ctx.scratch.get("distrusted", set()),
        )
        async with transaction(ctx.services.session_factory) as s:
            ev = await add_evidence(
                s, workspace_id=ctx.workspace_id, claim_id=ctx.scratch["claim_id"], url=doc.final_url or doc.url,
                quote=args.quote, stance=args.stance, source_class=source_class, publisher=doc.publisher,
                quote_verified=True, title=doc.title, document_id=doc.document_id, published_at=doc.published_at,
                is_archive=doc.is_archive, added_by="agent", run_id=ctx.run_id, note=args.note,
            )
            assessment = await refresh_status(s, claim_id=ctx.scratch["claim_id"], event_id=ctx.scratch["event_id"],
                                              distrusted=ctx.scratch.get("distrusted", set()))
        ctx.scratch["evidence_status"] = assessment.status
        prefix = "Already recorded." if ev is None else f"Recorded {args.stance} evidence ({source_class})."
        return Observation(
            ok=True,
            content=f"{prefix} Evidence status is now: {assessment.status}. {assessment.summary}",
            summary=f"{'Duplicate' if ev is None else 'Recorded'} {args.stance} evidence from {doc.publisher} "
                    f"({source_class}) → {assessment.status}",
            data={"status": assessment.status, "summary": assessment.summary, "source_class": source_class},
        )


class ListEvidenceArgs(BaseModel):
    pass


class ListEvidenceTool(Tool):
    name = "list_evidence"
    description = "Show the evidence recorded so far for the claim and its current status."
    Args = ListEvidenceArgs

    async def run(self, ctx: RunContext, args: ListEvidenceArgs) -> Observation:
        async with ctx.services.session_factory() as s:
            rows = (await s.execute(
                select(Evidence).where(Evidence.claim_id == ctx.scratch["claim_id"]).order_by(Evidence.created_at)
            )).scalars().all()
        lines = [f"- [{e.stance}] {e.publisher} ({e.source_class}{', archive' if e.is_archive else ''}"
                 f"{'' if e.quote_verified else ', UNVERIFIED quote'}): “{e.quote[:200]}”" for e in rows]
        status = ctx.scratch.get("evidence_status", "unverified")
        return Observation(ok=True, content=f"Status: {status}\n" + ("\n".join(lines) or "No evidence yet."),
                           summary=f"Reviewed {len(rows)} evidence items (status {status})")
