"""Deadline and trace bookkeeping for a brief run - no database needed.

The full product records agent steps as ``RunStep`` rows through :class:`RunContext`. A
brief must also run inside a throwaway container with no PostgreSQL (aiKart), so it keeps
its own in-memory trace with the same spirit: every step says what was done, with which
tool, how long it took and how many model calls it cost. The trace is rendered into the
brief ("How the agent worked") and returned as data.
"""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

StepCallback = Callable[[dict[str, Any]], Awaitable[None] | None]


class Deadline:
    """Wall-clock budget for one run. Stages ask for a slice of what is left.

    Stage caps and reserves are written for the production budget (``REFERENCE_S``); a
    shorter budget scales them down proportionally so every stage still gets a share.
    """

    REFERENCE_S = 240.0

    def __init__(self, seconds: float):
        self.total = seconds
        self.scale = min(1.0, max(0.01, seconds / self.REFERENCE_S))
        self._t0 = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._t0

    def remaining(self) -> float:
        return self.total - self.elapsed

    def slice(self, cap: float, *, reserve: float = 0.0) -> float:
        """Seconds a stage may use: at most ``cap``, leaving ``reserve`` for later stages."""
        return max(0.0, min(cap * self.scale, self.remaining() - reserve * self.scale))


@dataclass
class Step:
    name: str
    tool: str
    detail: str = ""
    status: str = "ok"  # ok | partial | skipped | failed
    model_calls: int = 0
    tool_calls: int = 0
    ms: int = 0
    started_s: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "tool": self.tool, "detail": self.detail, "status": self.status,
                "model_calls": self.model_calls, "tool_calls": self.tool_calls, "ms": self.ms,
                "started_s": round(self.started_s, 1)}


@dataclass
class Trace:
    deadline: Deadline
    on_step: StepCallback | None = None
    steps: list[Step] = field(default_factory=list)
    model_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0

    @asynccontextmanager
    async def step(self, name: str, tool: str):
        st = Step(name=name, tool=tool, started_s=self.deadline.elapsed)
        t0 = time.monotonic()
        try:
            yield st
        except Exception as e:
            st.status = "failed"
            st.detail = (st.detail + "; " if st.detail else "") + f"failed: {type(e).__name__}: {str(e)[:160]}"
            raise
        finally:
            st.ms = int((time.monotonic() - t0) * 1000)
            self.steps.append(st)
            await self._notify(st)

    async def _notify(self, st: Step) -> None:
        if self.on_step is None:
            return
        try:
            out = self.on_step(st.as_dict())
            if inspect.isawaitable(out):
                await out
        except Exception:  # a progress callback must never break the run
            log.debug("on_step callback failed", exc_info=True)

    def as_list(self) -> list[dict[str, Any]]:
        return [s.as_dict() for s in sorted(self.steps, key=lambda s: s.started_s)]
