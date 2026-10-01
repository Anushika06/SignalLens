"""One-shot intelligence brief: research a company once and explain why it matters to you.

The continuous product (plans, baselines, scheduled checks, routing) lives in
``signallens.pipeline``. This package runs the same judgment as a single bounded run with
no database, for the CLI (``signallens brief``), the aiKart container
(``signallens aikart-run``) and the hosted ``/api/agent`` endpoint.
"""

from signallens.brief.agent import run_brief
from signallens.brief.models import (
    FOCUS_OPTIONS,
    INPUT_FIELDS,
    LANGUAGE_OPTIONS,
    BriefInput,
    BriefRequestError,
    BriefResult,
    parse_brief_request,
)

__all__ = [
    "FOCUS_OPTIONS",
    "INPUT_FIELDS",
    "LANGUAGE_OPTIONS",
    "BriefInput",
    "BriefRequestError",
    "BriefResult",
    "parse_brief_request",
    "run_brief",
]
