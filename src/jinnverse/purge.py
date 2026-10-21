"""Erasing a story for good. Delete only hides; this is the real erasure.

A purge removes the story and every row that carries its text — messages, their embeddings,
summaries, facts, meters, questions, dial choices, status blocks — and keeps the ledger. The
spend rows hold no story text, the money left the account whatever became of the story, and
dropping them would make every report for that month wrong; they report under "(purged)" from
then on.

It erases only a story already deleted: two deliberate acts, not one. And it is the one path on
which the append-only trigger stands aside, by a setting local to this transaction, which the
trigger itself insists on (migration 0002).

Every deleted story can also be erased at once, from You: a client never sees a deleted story,
so it could not name them one by one. The same two acts hold — only stories already deleted go.
"""

import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from jinnverse.deps import Session
from jinnverse.library import alphabetical
from jinnverse.models import (
    Aside,
    DialValue,
    Embedding,
    Fact,
    Message,
    Spend,
    StatusField,
    StatusPin,
    StatusValue,
    Story,
    Summary,
    Tracker,
)

router = APIRouter(prefix="/stories/{story_id}", tags=["editing"])
everything = APIRouter(prefix="/stories", tags=["editing"])
"""`POST /stories/purge`: no POST route takes a bare story id, so `purge` cannot be read as one."""

# What a purge erases, in an order the foreign keys accept: embeddings point at messages.
ERASED = (
    ("embeddings", Embedding),
    ("messages", Message),
    ("summaries", Summary),
    ("facts", Fact),
    ("trackers", Tracker),
    ("asides", Aside),
    ("dial_values", DialValue),
    ("status_fields", StatusField),
    ("status_values", StatusValue),
    ("status_pins", StatusPin),
)


class Purged(BaseModel):
    """What was erased, and what was kept."""

    messages: int
    embeddings: int
    summaries: int
    facts: int
    trackers: int
    asides: int
    dial_values: int
    status_fields: int
    status_values: int
    status_pins: int
    ledger_rows_kept: int
    ledger_cost_kept: Decimal


class PurgedAll(Purged):
    """What erasing every deleted story did, or with `dry_run` would do."""

    dry_run: bool
    stories: int
    names: list[str]
    """The stories erased, or that would be, alphabetically."""


async def _counts(session: AsyncSession, ids: list[uuid.UUID]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for name, table in ERASED:
        counts[name] = (
            await session.scalar(select(func.count()).where(table.story_id.in_(ids))) or 0
        )
    return counts


async def _ledger(session: AsyncSession, ids: list[uuid.UUID]) -> tuple[int, Decimal]:
    """The spend rows the stories leave behind, and what they cost."""
    rows, cost = (
        await session.execute(
            select(func.count(), func.coalesce(func.sum(Spend.cost), 0)).where(
                Spend.story_id.in_(ids)
            )
        )
    ).one()
    return int(rows), Decimal(cost or 0)


async def _erase(session: AsyncSession, ids: list[uuid.UUID]) -> dict[str, int]:
    """Erases the stories' rows and the stories, with the trigger told why; the caller commits."""
    counts = await _counts(session, ids)
    # What SET LOCAL does, as a function call: on for this transaction only. The trigger
    # reads it and lets the DELETE through; it still refuses an UPDATE of a message's text.
    await session.execute(text("SELECT set_config('jinnverse.purging', 'on', true)"))
    for _name, table in ERASED:
        await session.execute(delete(table).where(table.story_id.in_(ids)))
    await session.execute(delete(Story).where(Story.id.in_(ids)))
    return counts


async def purge(session: AsyncSession, story: Story) -> Purged:
    """Erases one story's rows, in one transaction."""
    rows, cost = await _ledger(session, [story.id])
    counts = await _erase(session, [story.id])
    await session.commit()
    return Purged(**counts, ledger_rows_kept=rows, ledger_cost_kept=cost)


@router.post("/purge")
async def purge_story(story_id: uuid.UUID, session: Session) -> Purged:
    """Erases a deleted story and everything that carries its text. The ledger survives: the
    story's spend reports under "(purged)" from now on. This cannot be undone."""
    story = await session.get(Story, story_id)
    if story is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no story with that id.")
    if story.deleted_at is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Delete the story first: a purge erases only stories already deleted.",
        )
    return await purge(session, story)


@everything.post("/purge")
async def purge_deleted(session: Session, dry_run: bool = False) -> PurgedAll:
    """Erases every deleted story and everything that carries their text, in one transaction;
    the ledger survives, as for one. With `dry_run`, counts what would go and erases nothing.
    Live stories are never touched. This cannot be undone."""
    found = (
        await session.execute(
            select(Story.id, Story.name)
            .where(Story.deleted_at.is_not(None))
            .order_by(alphabetical(Story.name))
        )
    ).all()
    ids = [story_id for story_id, _name in found]
    rows, cost = await _ledger(session, ids)
    if dry_run:
        counts = await _counts(session, ids)
    else:
        counts = await _erase(session, ids)
        await session.commit()
    return PurgedAll(
        **counts,
        ledger_rows_kept=rows,
        ledger_cost_kept=cost,
        dry_run=dry_run,
        stories=len(ids),
        names=[name for _story_id, name in found],
    )
