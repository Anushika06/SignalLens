"""Single-call analysts on the fast model tier: extraction, materiality and news triage.

These are deliberately *not* agent loops. Each is one typed call with a narrow job, run
only after cheap deterministic filters have decided a model is worth asking (C7, C13).
"""

from __future__ import annotations

from dataclasses import dataclass

from signallens.agents import prompts
from signallens.agents.schemas import ExtractedValueOut, ExtractionOut, MaterialityOut, TriageOut
from signallens.runtime.core import RunContext
from signallens.search.base import SearchResult
from signallens.util.text import window_around

PAGE_CHARS = 14000


@dataclass
class AttributeSpec:
    key: str
    label: str
    hint: str
    value_type: str
    previous_display: str | None = None


async def extract_attributes(
    ctx: RunContext, *, url: str, page_text: str, attributes: list[AttributeSpec], when: str | None = None
) -> list[ExtractedValueOut]:
    if not attributes:
        return []
    if len(page_text) > PAGE_CHARS:
        terms = [w for a in attributes for w in (a.label.split() + a.hint.split()) if len(w) > 3][:40]
        page_text = window_around(page_text, terms, radius=900, max_chars=PAGE_CHARS)
    specs = "\n".join(
        f"- key: {a.key}\n  label: {a.label}\n  type: {a.value_type}\n  extract: {a.hint}"
        + (f"\n  previous value: {a.previous_display}" if a.previous_display else "")
        for a in attributes
    )
    prompt = (f"PAGE: {url}" + (f" (as captured {when})" if when else "") + f"\n\nATTRIBUTES:\n{specs}\n\n"
              f"PAGE TEXT:\n<untrusted_content>\n{page_text}\n</untrusted_content>")
    out = await ctx.services.require_llm().structured(
        ExtractionOut, tier="fast", system=prompts.EXTRACTOR, messages=prompt, ctx=ctx,
        purpose=f"Extract {len(attributes)} tracked values", max_tokens=6000,
    )
    wanted = {a.key for a in attributes}
    return [v for v in out.values if v.key in wanted]


async def assess_page_changes(
    ctx: RunContext,
    *,
    url: str,
    entity_name: str,
    diff_text: str,
    policy_text: str,
    already_detected: list[str],
    when: str | None = None,
) -> MaterialityOut:
    known = "\n".join(f"- {x}" for x in already_detected) or "- none"
    prompt = (
        f"MONITORED ENTITY: {entity_name}\nPAGE: {url}" + (f"\nCHANGE OBSERVED: {when}" if when else "") +
        f"\n\n{policy_text}\n\nALREADY CAPTURED AS TRACKED-VALUE CHANGES (do not repeat these):\n{known}\n\n"
        f"DIFF (hunks numbered; '-' old line, '+' new line):\n<untrusted_content>\n{diff_text}\n</untrusted_content>"
    )
    return await ctx.services.require_llm().structured(
        MaterialityOut, tier="fast", system=prompts.MATERIALITY, messages=prompt, ctx=ctx,
        purpose="Assess materiality of page changes", max_tokens=6000,
    )


async def triage_news(
    ctx: RunContext,
    *,
    items: list[SearchResult],
    entities_text: str,
    policy_text: str,
    today: str,
    window_days: int,
) -> TriageOut:
    lines = []
    for i, r in enumerate(items):
        when = r.published_at.date().isoformat() if r.published_at else "unknown date"
        body = " ".join(((r.content or r.snippet) or "").split())[:900]
        lines.append(f"[{i}] {r.title}\n    publisher: {r.publisher} | date: {when} | url: {r.url}\n    {body}")
    prompt = (
        f"TODAY: {today}. Window: last {window_days} days.\n\nMONITORED ENTITIES:\n{entities_text}\n\n{policy_text}\n\n"
        "ITEMS:\n<untrusted_content>\n" + "\n".join(lines) + "\n</untrusted_content>\n\n"
        "Return one entry per item id."
    )
    return await ctx.services.require_llm().structured(
        TriageOut, tier="fast", system=prompts.TRIAGE, messages=prompt, ctx=ctx,
        purpose=f"Triage {len(items)} news items", max_tokens=8000,
    )
