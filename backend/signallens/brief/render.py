"""Render a brief as tight, scannable markdown (judges and executives skim; every claim links out).

Structure: title and context line, executive summary, what changed (before -> after table),
recent developments, current snapshot with quotes, why it matters (cited facts vs
assessment), recommended actions, how the agent worked, and the web-app footer. Section
labels are localised; quotes are always shown verbatim.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from signallens.brief.models import BriefInput
from signallens.brief.state import STATUS_LABELS, BriefState
from signallens.util.text import truncate
from signallens.util.urls import host_of

LABELS: dict[str, dict[str, str]] = {
    "English": {
        "title": "intelligence brief", "for": "For", "general": "a general competitor view", "focus": "Focus",
        "date": "Date", "site": "Official site", "summary": "Executive summary",
        "changed": "What changed in the last {n} months", "change": "Change", "before": "Before", "now": "Now",
        "when": "When", "evidence": "Evidence", "source": "Source", "live": "live", "archive": "archive",
        "between": "between {a} and {b}", "not_on_page": "Not on the page",
        "changed_intro": "Wayback Machine capture vs. the live page today. Both sides are quotes verified on the "
                         "company's own website.",
        "no_changes": "No verified change to the tracked facts was found between the archived capture and today.",
        "developments": "Recent developments (last {d} days)", "no_news": "No material developments found in the "
        "last {d} days.", "sources": "Sources", "snapshot": "Current snapshot", "no_snapshot":
        "The official pages could not be read, so there is no verified snapshot.",
        "why": "Why it matters to {who}", "why_generic": "Why it matters", "facts": "Facts",
        "assessment": "Assessment", "assessment_note": "SignalLens's interpretation, not established fact",
        "assumptions": "Assumptions", "actions": "Recommended actions", "action": "Action", "owner": "Owner",
        "reason": "Why", "watch": "Watch next", "how": "How the agent worked", "step": "Step", "tool": "Tool",
        "result": "Result", "time": "Time", "calls": "Model calls",
        "totals": "Total {s} s · {calls} model calls{model} · pages read via {reader} · {dropped} unverifiable "
                  "quote(s) dropped.",
        "legend": "Evidence status is computed by code, not by the model: **Confirmed** = quoted from an official "
                  "source; **Corroborated** = 2+ independent outlets; **Single source** = one outlet; "
                  "**Unverified** = no quote could be verified.",
        "footer": "For continuous monitoring, approvals and team routing use the SignalLens web app at {url}",
        "no_impact": "The impact analysis could not be completed in the time budget; the verified facts above "
                     "stand on their own.",
        "notes": "Notes",
    },
    "Hindi": {
        "title": "इंटेलिजेंस ब्रीफ़", "for": "किसके लिए", "general": "सामान्य प्रतिस्पर्धी दृष्टिकोण", "focus": "फ़ोकस",
        "date": "तारीख", "site": "आधिकारिक वेबसाइट", "summary": "कार्यकारी सारांश",
        "changed": "पिछले {n} महीनों में क्या बदला", "change": "बदलाव", "before": "पहले", "now": "अब",
        "when": "कब", "evidence": "प्रमाण", "source": "स्रोत", "live": "लाइव", "archive": "आर्काइव",
        "between": "{a} और {b} के बीच", "not_on_page": "पेज पर नहीं था",
        "changed_intro": "Wayback Machine कैप्चर बनाम आज का लाइव पेज। दोनों पक्ष कंपनी की अपनी वेबसाइट पर सत्यापित "
                         "उद्धरण हैं।",
        "no_changes": "आर्काइव कैप्चर और आज के बीच ट्रैक किए गए तथ्यों में कोई सत्यापित बदलाव नहीं मिला।",
        "developments": "हाल के घटनाक्रम (पिछले {d} दिन)", "no_news": "पिछले {d} दिनों में कोई महत्वपूर्ण घटनाक्रम नहीं मिला।",
        "sources": "स्रोत", "snapshot": "वर्तमान स्थिति", "no_snapshot":
        "आधिकारिक पेज पढ़े नहीं जा सके, इसलिए कोई सत्यापित स्नैपशॉट नहीं है।",
        "why": "{who} के लिए इसका महत्व", "why_generic": "इसका महत्व", "facts": "तथ्य",
        "assessment": "आकलन", "assessment_note": "SignalLens की व्याख्या, स्थापित तथ्य नहीं",
        "assumptions": "मान्यताएँ", "actions": "अनुशंसित कदम", "action": "कदम", "owner": "ज़िम्मेदार टीम",
        "reason": "क्यों", "watch": "आगे क्या देखें", "how": "एजेंट ने कैसे काम किया", "step": "चरण", "tool": "टूल",
        "result": "परिणाम", "time": "समय", "calls": "मॉडल कॉल",
        "totals": "कुल {s} s · {calls} मॉडल कॉल{model} · पेज पढ़े गए: {reader} · {dropped} असत्यापित उद्धरण हटाए गए।",
        "legend": "प्रमाण की स्थिति कोड तय करता है, मॉडल नहीं: **Confirmed** = आधिकारिक स्रोत से उद्धरण; "
                  "**Corroborated** = 2+ स्वतंत्र प्रकाशन; **Single source** = एक प्रकाशन; **Unverified** = कोई उद्धरण "
                  "सत्यापित नहीं।",
        "footer": "लगातार निगरानी, अनुमोदन और टीम रूटिंग के लिए SignalLens वेब ऐप का उपयोग करें: {url}",
        "no_impact": "समय सीमा में प्रभाव विश्लेषण पूरा नहीं हो सका; ऊपर दिए सत्यापित तथ्य स्वयं में पूर्ण हैं।",
        "notes": "टिप्पणियाँ",
    },
}

CATEGORY_TITLES = {
    "pricing": "Pricing", "product": "Products", "partnership": "Partnerships", "funding": "Funding",
    "regulatory": "Regulatory", "leadership": "Leadership", "hiring": "Hiring", "customers": "Customers & scale",
    "company": "Company", "other": "Other",
}


def _cell(text: str, n: int = 160) -> str:
    flat = " ".join(str(text or "").replace("\\n", " ").split())  # models sometimes emit a literal "\n"
    return truncate(flat, n).replace("|", "\\|")


def _q(text: str, n: int = 180) -> str:
    return "“" + truncate(" ".join(text.split()), n).replace("|", "\\|") + "”"


def _short_url(url: str) -> str:
    host = host_of(url).removeprefix("www.")
    path = url.split(host, 1)[-1].split("?")[0].rstrip("/") if host else ""
    return truncate(host + path, 48)


def _fmt_date(d: date | None) -> str:
    return d.strftime("%d %b %Y").lstrip("0") if d else "date unknown"


def _ms(ms: int) -> str:
    return f"{ms / 1000:.1f} s"


def render_markdown(
    state: BriefState,
    inputs: BriefInput,
    trace: list[dict[str, Any]],
    stats: dict[str, Any],
    *,
    today: date,
    app_url: str | None = None,
    your_company: str | None = None,
    news_days: int = 90,
) -> str:
    L = LABELS[inputs.language]
    c = state.company
    lines: list[str] = []
    add = lines.append
    refs = {f.id: f.url for f in state.facts} | {ch.id: ch.url for ch in state.changes} | {
        s.id: (s.sources[0].url if s.sources else "") for s in state.stories}

    # --- title -------------------------------------------------------------------------
    add(f"# {c.name} — {L['title']}")
    meta = [f"**{L['for']}:** {_cell(your_company, 90) if your_company else L['general']}",
            f"**{L['focus']}:** {inputs.focus}", f"**{L['date']}:** {_fmt_date(today)}"]
    if c.domain:
        meta.append(f"**{L['site']}:** [{c.domain}](https://{c.domain})")
    add(" · ".join(meta))
    add("")
    if c.description:
        add(c.description)
        add("")
    impact = state.impact or {}
    if impact.get("executive_summary"):
        add(f"> **{L['summary']}.** {impact['executive_summary']}")
        add("")
    for w in state.warnings[:3]:
        add(f"> _{w}_")
    if state.warnings:
        add("")

    # --- what changed ------------------------------------------------------------------
    add(f"## {L['changed'].format(n=inputs.months_back)}")
    if state.changes:
        add(f"_{L['changed_intro']}_")
        add("")
        add(f"| | {L['change']} | {L['before']} | {L['now']} | {L['when']} | {L['evidence']} | {L['source']} |")
        add("|---|---|---|---|---|---|---|")
        for ch in state.changes:
            before = L["not_on_page"] if ch.kind == "added" else ch.before
            when = L["between"].format(a=ch.captured_on.strftime("%b %Y"), b=today.strftime("%b %Y"))
            add(f"| {ch.id} | **{_cell(ch.label, 70)}** | {_cell(before)} | {_cell(ch.after)} | {when} | "
                f"{STATUS_LABELS[ch.status]} | [{L['live']}]({ch.url}) · [{L['archive']}]({ch.archive_url}) |")
        notes = [ch for ch in state.changes if ch.note]
        if notes:
            add("")
            for ch in notes:
                add(f"- **{ch.id}** {ch.note}")
    else:
        add(state.history_note or L["no_changes"])
    add("")

    # --- recent developments -------------------------------------------------------------
    add(f"## {L['developments'].format(d=news_days)}")
    if state.stories:
        for i, s in enumerate(state.stories, 1):
            add(f"{i}. **{_cell(s.headline, 160)}** — {_fmt_date(s.when)} · **{STATUS_LABELS[s.status]}** "
                f"({s.id})")
            if s.claim and inputs.language == "English" and s.claim.lower() != s.headline.lower():
                add(f"   {_cell(s.claim, 260)}")
            quoted = next((src for src in s.sources if src.quote), None)
            if quoted:
                add(f"   > {_q(quoted.quote)} — [{quoted.publisher}]({quoted.url})")
            others = [src for src in s.sources if src is not quoted][:4]
            if others:
                add(f"   {L['sources']}: " + ", ".join(f"[{src.publisher}]({src.url})" for src in others))
    else:
        add(L["no_news"].format(d=news_days))
    add("")

    # --- snapshot --------------------------------------------------------------------------
    add(f"## {L['snapshot']}")
    if state.facts:
        by_page: dict[str, list] = {}
        for f in state.facts:
            by_page.setdefault(f.url, []).append(f)
        for url, facts in by_page.items():
            kind = facts[0].page_kind
            add(f"**{kind.capitalize()}** — [{_short_url(url)}]({url})")
            for f in facts[:5]:
                add(f"- **{_cell(f.label, 80)}:** {_cell(f.value, 200)} — _{_q(f.quote, 150)}_ ({f.id})")
            add("")
    else:
        add(L["no_snapshot"])
        add("")

    # --- why it matters ----------------------------------------------------------------------
    who = _cell(your_company.split("—")[0].split(",")[0].split(" - ")[0], 60) if your_company else None
    add(f"## {L['why'].format(who=who) if who else L['why_generic']}")
    if impact:
        if impact.get("facts"):
            add(f"**{L['facts']}**")
            for f in impact["facts"]:
                cites = " ".join(f"[{r}]({refs[r]})" if refs.get(r) else f"[{r}]" for r in f["refs"])
                add(f"- {f['statement']} {cites}")
            add("")
        if impact.get("assessment"):
            add(f"**{L['assessment']}** — _{L['assessment_note']}_")
            for a in impact["assessment"]:
                add(f"- {a}")
            add("")
        if impact.get("assumptions"):
            add(f"_{L['assumptions']}: {'; '.join(impact['assumptions'])}_")
            add("")
    else:
        add(L["no_impact"])
        add("")

    # --- actions -------------------------------------------------------------------------------
    if impact.get("actions"):
        add(f"## {L['actions']}")
        add(f"| # | {L['action']} | {L['owner']} | {L['reason']} |")
        add("|---|---|---|---|")
        for i, a in enumerate(impact["actions"], 1):
            add(f"| {i} | {_cell(a['action'], 260)} | **{a['owner']}** | {_cell(a.get('why', ''), 220)} |")
        add("")
        if impact.get("watch_next"):
            add(f"**{L['watch']}:** " + " · ".join(impact["watch_next"]))
            add("")

    # --- how the agent worked ----------------------------------------------------------------------
    add(f"## {L['how']}")
    add(f"| # | {L['step']} | {L['tool']} | {L['result']} | {L['time']} | {L['calls']} |")
    add("|---|---|---|---|---|---|")
    for i, st in enumerate(trace, 1):
        status = "" if st["status"] == "ok" else f" _({st['status']})_"
        add(f"| {i} | {st['name']}{status} | {st['tool']} | {_cell(st['detail'], 220)} | {_ms(st['ms'])} | "
            f"{st['model_calls']} |")
    model = f" ({stats['model']})" if stats.get("model") else ""
    add("")
    add(L["totals"].format(s=stats.get("seconds", 0), calls=stats.get("model_calls", 0), model=model,
                           reader=stats.get("reader", "direct"), dropped=state.dropped_quotes))
    add("")
    add(L["legend"])
    add("")
    add("---")
    add(f"_{L['footer'].format(url=app_url or _default_app_url())}_")
    return "\n".join(lines).rstrip() + "\n"


def _default_app_url() -> str:
    from signallens.config import get_settings

    return get_settings().public_app_url
