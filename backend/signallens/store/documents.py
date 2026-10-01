"""Persisting retrieved content (live pages, archive captures, articles, search results)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from signallens.db.models import Document
from signallens.fetch.extract import ExtractedDoc
from signallens.fetch.http import FetchResult
from signallens.util.text import sha256_text
from signallens.util.urls import publisher_key


def publisher_of(url: str) -> str:
    if url.startswith("sandbox://"):
        return "sandbox:" + url.removeprefix("sandbox://").split("/")[0]
    try:
        return publisher_key(url)
    except Exception:
        return url[:255]


async def save_document(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    url: str,
    extracted: ExtractedDoc | None = None,
    fetch: FetchResult | None = None,
    origin: str = "live",
    title: str | None = None,
    text: str | None = None,
    published_at: datetime | None = None,
    archive_timestamp: str | None = None,
    meta: dict[str, Any] | None = None,
) -> Document:
    final_url = (fetch.final_url if fetch else None) or url
    body = extracted.text if extracted else (text or "")
    doc = Document(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        url=url,
        final_url=final_url,
        publisher=publisher_of(url if origin == "archive" else final_url),
        title=(extracted.title if extracted and extracted.title else title),
        content_type=fetch.content_type if fetch else None,
        content_hash=extracted.content_hash if extracted else sha256_text(body),
        text=body,
        blocks=[{"t": b.text, "k": b.kind} for b in extracted.blocks] if extracted else [],
        word_count=extracted.word_count if extracted else len(body.split()),
        quality=extracted.quality if extracted else "ok",
        quality_reason=extracted.quality_reason if extracted else None,
        published_at=(extracted.published_at if extracted and extracted.published_at else published_at),
        origin=origin,
        archive_timestamp=archive_timestamp,
        meta=meta or {},
    )
    session.add(doc)
    await session.flush()
    return doc


def block_lines(doc: Document) -> list[str]:
    return [b.get("t", "") for b in (doc.blocks or []) if b.get("t")]
