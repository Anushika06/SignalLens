"""Block-level diffing of page snapshots (tracked-state monitoring, C2 / C7).

A snapshot is a list of text blocks (headings, paragraphs, list items, table rows). Two
snapshots are aligned with :class:`difflib.SequenceMatcher` on *masked* keys
(``mask_volatile(normalize_ws(line))``), so a changed timestamp or copyright year never
even produces a hunk, while the hunks we do report carry the original, readable lines.

:func:`drop_noise_hunks` then removes what is left of the noise (formatting-only edits,
re-wrapped text, lines matching learned suppression rules) and says why for each hunk it
drops - the reasons feed the attention funnel ("38 changes -> 6 material").
"""

from __future__ import annotations

import difflib
import logging
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from signallens.util.text import mask_volatile, normalize_ws, truncate

__all__ = ["DiffHunk", "PageDiff", "diff_lines", "drop_noise_hunks", "render_diff"]

logger = logging.getLogger(__name__)

HunkOp = Literal["added", "removed", "changed"]
_OPS: dict[str, HunkOp] = {"replace": "changed", "insert": "added", "delete": "removed"}


@dataclass
class DiffHunk:
    """One contiguous change: ``before`` lines were replaced by ``after`` lines."""

    op: HunkOp
    before: list[str]
    after: list[str]
    context_before: list[str] = field(default_factory=list)
    context_after: list[str] = field(default_factory=list)


@dataclass
class PageDiff:
    """All hunks between two snapshots plus the counts materiality rules look at."""

    hunks: list[DiffHunk]
    lines_added: int
    lines_removed: int
    old_line_count: int
    new_line_count: int

    @property
    def changed_ratio(self) -> float:
        """Share of all lines involved in a change (0 = identical, 1 = nothing in common)."""
        return (self.lines_added + self.lines_removed) / max(1, self.old_line_count + self.new_line_count)

    @property
    def is_empty(self) -> bool:
        return not self.hunks

    @property
    def is_restructure(self) -> bool:
        """More than half the page changed: likely a redesign, not a content edit."""
        return self.changed_ratio > 0.5


def _key(line: str) -> str:
    return mask_volatile(normalize_ws(line))


def diff_lines(old: list[str], new: list[str], *, context: int = 2) -> PageDiff:
    """Diff two block lists. Alignment uses masked keys; hunks report the original lines.

    Context lines come from the new snapshot and never overlap a neighbouring hunk.
    """
    old_keys = [_key(line) for line in old]
    new_keys = [_key(line) for line in new]
    matcher = difflib.SequenceMatcher(a=old_keys, b=new_keys, autojunk=False)
    opcodes = matcher.get_opcodes()

    hunks: list[DiffHunk] = []
    for index, (tag, i1, i2, j1, j2) in enumerate(opcodes):
        if tag == "equal":
            continue
        ctx_before: list[str] = []
        ctx_after: list[str] = []
        if context > 0:
            if index > 0 and opcodes[index - 1][0] == "equal":
                prev_j1 = opcodes[index - 1][3]
                ctx_before = new[max(prev_j1, j1 - context) : j1]
            if index + 1 < len(opcodes) and opcodes[index + 1][0] == "equal":
                next_j2 = opcodes[index + 1][4]
                ctx_after = new[j2 : min(next_j2, j2 + context)]
        hunks.append(
            DiffHunk(
                op=_OPS[tag],
                before=list(old[i1:i2]),
                after=list(new[j1:j2]),
                context_before=list(ctx_before),
                context_after=list(ctx_after),
            )
        )
    return _build(hunks, len(old), len(new))


def _build(hunks: list[DiffHunk], old_count: int, new_count: int) -> PageDiff:
    return PageDiff(
        hunks=hunks,
        lines_added=sum(len(h.after) for h in hunks),
        lines_removed=sum(len(h.before) for h in hunks),
        old_line_count=old_count,
        new_line_count=new_count,
    )


def _formatting_key(text: str) -> str:
    """Text with whitespace, case and cosmetic punctuation removed.

    Punctuation next to a digit or ``%`` is kept, because there it carries meaning:
    "2.5%" vs "25%", "-5%" vs "5%" and "0%*" vs "0%" are real changes.
    """
    out: list[str] = []
    for i, ch in enumerate(text):
        if ch.isalnum() or unicodedata.category(ch) == "Sc" or ch == "%":
            out.append(ch)
        elif not ch.isspace():
            prev = text[i - 1] if i > 0 else ""
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if any(c.isdigit() or c == "%" for c in (prev, nxt)):
                out.append(ch)
    return "".join(out).casefold()


def _describe(hunk: DiffHunk, limit: int = 120) -> str:
    before = truncate(" / ".join(hunk.before), limit)
    after = truncate(" / ".join(hunk.after), limit)
    if hunk.op == "added":
        return f"+ {after!r}"
    if hunk.op == "removed":
        return f"- {before!r}"
    return f"{before!r} -> {after!r}"


def _noise_reason(hunk: DiffHunk, patterns: list[re.Pattern[str]]) -> str | None:
    before = " ".join(hunk.before)
    after = " ".join(hunk.after)
    if hunk.before and hunk.after:
        masked_before = mask_volatile(normalize_ws(before))
        masked_after = mask_volatile(normalize_ws(after))
        if normalize_ws(before) != normalize_ws(after) and masked_before == masked_after:
            return f"volatile-only change (dates/times/ids): {_describe(hunk)}"
        if masked_before == masked_after or _formatting_key(masked_before) == _formatting_key(masked_after):
            return f"formatting-only change (whitespace/punctuation/case): {_describe(hunk)}"
    lines = [line for line in (*hunk.before, *hunk.after) if line.strip()]
    if not lines:
        return f"whitespace-only change: {_describe(hunk)}"
    if patterns and all(any(p.search(line) for p in patterns) for line in lines):
        matched = next(p for p in patterns if any(p.search(line) for line in lines))
        return f"matched suppression rule {matched.pattern!r}: {_describe(hunk)}"
    return None


def drop_noise_hunks(diff: PageDiff, *, suppress_patterns: Sequence[str] = ()) -> tuple[PageDiff, list[str]]:
    """Remove hunks that cannot be material and explain each removal.

    A hunk is dropped when it is volatile-only (identical once dates/times/ids are
    masked), formatting-only (whitespace, re-wrapping, cosmetic punctuation or case), or
    when every changed line matches one of ``suppress_patterns`` (case-insensitive regexes;
    invalid ones are logged and ignored). Returns the kept diff with recomputed counts and
    one human-readable reason per dropped hunk.
    """
    patterns: list[re.Pattern[str]] = []
    for raw in suppress_patterns:
        try:
            patterns.append(re.compile(raw, re.IGNORECASE))
        except re.error as exc:
            logger.warning("ignoring invalid suppression pattern %r: %s", raw, exc)

    kept: list[DiffHunk] = []
    reasons: list[str] = []
    for hunk in diff.hunks:
        reason = _noise_reason(hunk, patterns)
        if reason is None:
            kept.append(hunk)
        else:
            reasons.append(reason)
    return _build(kept, diff.old_line_count, diff.new_line_count), reasons


def _render_hunk(number: int, hunk: DiffHunk) -> list[str]:
    lines = [f"@@ {number} {hunk.op}"]
    lines += [f"  {line}" for line in hunk.context_before]
    lines += [f"- {line}" for line in hunk.before]
    lines += [f"+ {line}" for line in hunk.after]
    lines += [f"  {line}" for line in hunk.context_after]
    return lines


def render_diff(diff: PageDiff, *, max_chars: int = 6000) -> str:
    """Compact, readable rendering for humans and models::

        @@ 1 changed
          context line
        - old line
        + new line

    Whole hunks are included while they fit in ``max_chars``; the rest are summarised in a
    final note ("… 3 more hunks omitted"). A single oversized hunk is cut at a line
    boundary.
    """
    if diff.is_empty:
        return "(no changes)"
    total = len(diff.hunks)
    out: list[str] = []
    used = 0
    included = 0
    for number, hunk in enumerate(diff.hunks, start=1):
        block = "\n".join(_render_hunk(number, hunk))
        sep = 2 if out else 0  # blank line between hunks
        remaining_after = total - number
        reserve = 40 if remaining_after else 0  # room for the omission note
        if used + sep + len(block) + reserve <= max_chars:
            out.append(block)
            used += sep + len(block)
            included += 1
            continue
        if not out:  # first hunk alone is too big: keep as many whole lines as fit
            partial: list[str] = []
            budget = max_chars - 60
            for line in block.split("\n"):
                cost = len(line) + (1 if partial else 0)
                if used + cost > budget:
                    if not partial:
                        partial.append(truncate(line, max(1, budget)))
                    break
                partial.append(line)
                used += cost
            partial.append("  … (hunk truncated)")
            out.append("\n".join(partial))
            included = 1
        break
    omitted = total - included
    text = "\n\n".join(out)
    if omitted:
        text += f"\n\n… {omitted} more hunk{'s' if omitted != 1 else ''} omitted"
    return text if len(text) <= max_chars else truncate(text, max_chars)
