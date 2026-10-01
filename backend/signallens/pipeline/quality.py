"""Relative snapshot quality (spec review C6), applied on top of the absolute checks in extraction.

Absolute checks (anti-bot markers, near-empty text) happen in ``fetch.extract``. The
relative check asks: is this version suspiciously smaller than the *previous accepted
version of the same page*? Comparing with the neighbouring version rather than today's
page matters: pages grow. On razorpay.com/pricing the October 2025 capture had ~350
words and the March 2026 capture ~2,150 after an FAQ section was added; comparing old
captures to today's size would wrongly discard real history.

A genuine shrink (a redesign) is accepted when two consecutive versions agree on the
new, smaller size.
"""

from __future__ import annotations

RELATIVE_FLOOR = 0.35
AGREEMENT = 0.25


def relative_verdict(words: int, reference: int | None, last_rejected: int | None) -> tuple[bool, str | None]:
    """(accept, note) for a version that already passed the absolute checks."""
    if not reference or words >= RELATIVE_FLOOR * reference:
        return True, None
    if last_rejected and abs(words - last_rejected) <= AGREEMENT * max(words, last_rejected):
        return True, (f"accepted as a restructured page: two consecutive versions agree on ~{words} words "
                      f"(previously ~{reference})")
    return False, f"only {words} words vs about {reference} in the previous good version"
