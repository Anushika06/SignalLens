"""Inputs and outputs of the one-shot intelligence brief.

The same input contract is used by every entry point - the CLI, the aiKart "Try Me Now"
container (``/aikart/input.json``) and the hosted ``/api/agent/brief`` endpoint - so the
manifest, the API description and validation all come from :data:`INPUT_FIELDS`.

Callers are not always careful about shape (aiKart forms, curl one-liners, other agents),
so :func:`parse_brief_request` accepts the inputs object itself, ``{"input": {...}}``,
``{"inputs": {...}}`` or a single free-text field (``query``/``message``/``prompt``/
``topic``) and normalises loose values ("hindi", "pricing", "12") instead of rejecting them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

Focus = Literal[
    "Everything", "Pricing & products", "Regulatory & compliance", "Partnerships & funding", "Leadership & hiring",
]
Language = Literal["English", "Hindi"]

FOCUS_OPTIONS: tuple[str, ...] = (
    "Everything", "Pricing & products", "Regulatory & compliance", "Partnerships & funding", "Leadership & hiring",
)
LANGUAGE_OPTIONS: tuple[str, ...] = ("English", "Hindi")
TEAMS: tuple[str, ...] = ("Strategy", "Product", "Sales", "Compliance", "Marketing")

AGENT_NAME = "signallens"
AGENT_DISPLAY_NAME = "SignalLens — Market & Competitor Intelligence Agent"
AGENT_DESCRIPTION = ("Researches any company in one run: what changed on its official pages over the last year "
                     "(Wayback-verified), recent news with evidence status, and why it matters to you.")

# One definition for the aiKart manifest, the hosted manifest endpoint and the docs.
INPUT_FIELDS: list[dict[str, Any]] = [
    {"name": "company", "label": "Company to analyse (name or website)", "type": "text", "required": True},
    {"name": "your_company", "label": "Your company (optional: who you are and what you sell)", "type": "textarea",
     "required": False},
    {"name": "focus", "label": "Focus", "type": "select", "required": False, "options": list(FOCUS_OPTIONS),
     "default": "Everything"},
    {"name": "language", "label": "Language", "type": "select", "required": False,
     "options": list(LANGUAGE_OPTIONS), "default": "English"},
    {"name": "months_back", "label": "History window (months)", "type": "number", "required": False, "default": 12},
]

_FOCUS_KEYWORDS: list[tuple[str, str]] = [
    ("pric", "Pricing & products"), ("product", "Pricing & products"), ("fee", "Pricing & products"),
    ("regul", "Regulatory & compliance"), ("compli", "Regulatory & compliance"), ("legal", "Regulatory & compliance"),
    ("partner", "Partnerships & funding"), ("fund", "Partnerships & funding"), ("invest", "Partnerships & funding"),
    ("leader", "Leadership & hiring"), ("hir", "Leadership & hiring"), ("people", "Leadership & hiring"),
    ("talent", "Leadership & hiring"),
]


class BriefInput(BaseModel):
    company: str = Field(min_length=1, max_length=500, description="company name, website, or a free-text request")
    your_company: str | None = Field(None, max_length=2000)
    focus: Focus = "Everything"
    language: Language = "English"
    months_back: int = Field(12, ge=1, le=36)

    @field_validator("company", mode="before")
    @classmethod
    def _company(cls, v: Any) -> Any:
        return " ".join(str(v).split()) if v is not None else v

    @field_validator("your_company", mode="before")
    @classmethod
    def _your_company(cls, v: Any) -> Any:
        if v is None:
            return None
        text = str(v).strip()
        return text or None

    @field_validator("focus", mode="before")
    @classmethod
    def _focus(cls, v: Any) -> str:
        text = str(v or "").strip()
        if not text:
            return "Everything"
        for option in FOCUS_OPTIONS:
            if text.casefold() == option.casefold():
                return option
        lowered = text.casefold()
        for needle, option in _FOCUS_KEYWORDS:
            if needle in lowered:
                return option
        return "Everything"

    @field_validator("language", mode="before")
    @classmethod
    def _language(cls, v: Any) -> str:
        text = str(v or "").strip().casefold()
        return "Hindi" if text in {"hindi", "hi", "hin", "हिंदी", "हिन्दी"} else "English"

    @field_validator("months_back", mode="before")
    @classmethod
    def _months(cls, v: Any) -> int:
        try:
            n = int(float(str(v).strip())) if v not in (None, "") else 12
        except ValueError:
            return 12
        return min(36, max(1, n))


class BriefRequestError(ValueError):
    """The request body could not be turned into brief inputs (message is user-facing)."""


_TEXT_KEYS = ("company", "query", "message", "prompt", "topic", "question", "text", "q", "input_text")
_COMPANY_ALIASES = ("company_name", "competitor", "target", "subject", "url", "website", "name")
_YOUR_ALIASES = ("your_company", "for", "my_company", "context", "about_us", "yourCompany")


def parse_brief_request(body: Any) -> BriefInput:
    """Lenient request parsing (see module docstring). Raises :class:`BriefRequestError`."""
    if isinstance(body, str):
        body = {"company": body}
    if not isinstance(body, dict):
        raise BriefRequestError("Send a JSON object such as {\"company\": \"Razorpay\"}.")
    for wrapper in ("input", "inputs", "data", "params", "arguments"):
        inner = body.get(wrapper)
        if isinstance(inner, dict):
            body = {**{k: v for k, v in body.items() if k != wrapper}, **inner}
            break
        if isinstance(inner, str) and inner.strip() and not any(body.get(k) for k in _TEXT_KEYS):
            body = {**body, "company": inner}
            break
    data: dict[str, Any] = {}
    company = next((body[k] for k in (*_TEXT_KEYS, *_COMPANY_ALIASES)
                    if isinstance(body.get(k), str | int | float) and str(body.get(k)).strip()), None)
    if company is None:
        raise BriefRequestError(
            "Missing 'company'. Send {\"company\": \"Razorpay\"} (optional: your_company, focus, language, "
            "months_back) or {\"query\": \"What is Razorpay up to?\"}."
        )
    data["company"] = str(company)
    your = next((body[k] for k in _YOUR_ALIASES if isinstance(body.get(k), str) and body[k].strip()), None)
    if your:
        data["your_company"] = your
    for key in ("focus", "language", "months_back"):
        if body.get(key) not in (None, ""):
            data[key] = body[key]
    try:
        return BriefInput.model_validate(data)
    except ValidationError as e:
        problems = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()[:5])
        raise BriefRequestError(f"Invalid brief input: {problems}") from e


@dataclass
class BriefResult:
    """What a brief run returns: the rendered markdown, structured data and the agent trace."""

    markdown: str
    data: dict[str, Any] = field(default_factory=dict)
    trace: list[dict[str, Any]] = field(default_factory=list)
