"""Condense summaries: the oldest summaries of a story merged into one shorter account.

The summary layer only grows: every stretch that no longer fits adds a summary, and every
summary is in every prompt after it. One long story carried twenty-seven, twelve thousand tokens
a reply. Condensing reads the oldest N in order and writes one account of them — the same rules
as the summariser: factual, in order, nothing invented — and replaces the N rows with it. Seven
summaries of a real story (5,090 tokens) came back as one of 1,058, every name, time and open
thread still there, for a twentieth of a cent.

The reader asks for it and is told the cost first; nothing else here fires on its own. The turns
and their embeddings are untouched: a summary is derived, and the rebuild can make it again.
"""

import logging
import uuid
from collections.abc import Sequence
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lustjinn import background, ledger, memory, tokens
from lustjinn.deps import CurrentSettings, Model, Session
from lustjinn.models import Spend, SpendKind, Story, Summary
from lustjinn.openrouter import ChatMessage, ModelError, OpenRouter, Reply
from lustjinn.settings import Settings
from lustjinn.stories import visible_story

log = logging.getLogger(__name__)

CONDENSE_TEMPERATURE = memory.SUMMARY_TEMPERATURE
CONDENSE_MAX_TOKENS = 1500
CONDENSE_WORDS = 700
"""Asked after the summaries, like the summariser's length: seven real summaries came back in
about a thousand tokens."""

INSTRUCTION = (
    "You are condensing several consecutive summaries of a roleplay transcript into one, so "
    "the story can be carried forward in less room. They are given in story order.\n\n"
    "Write one factual account, in the same language, that keeps:\n"
    "- what happened, in order\n"
    "- every name, place and commitment the summaries mention\n"
    "- what changed between the participants, and what was left unresolved\n"
    "- where the last summary left the scene\n\n"
    "Drop repetition between the summaries, headings, bullet lists and anything said twice. "
    "Do not write in character, do not add events, and do not editorialise."
)


def stretch(summaries: Sequence[Summary]) -> str:
    """The summaries as the model is sent them: each closed off in a tag with its turns, then
    the task said again with its length — the summariser's lesson (#226, #229)."""
    blocks = "\n\n".join(
        f'<summary turns="{s.from_sequence}-{s.to_sequence}">\n{s.text}\n</summary>'
        for s in summaries
    )
    return (
        f"{blocks}\n\nThe summaries end here. Write the one account now, as instructed. "
        f"Use at most {CONDENSE_WORDS} words."
    )


class Condensed(BaseModel):
    dry_run: bool
    """True: nothing was called or changed; the rest says what a condense would do."""
    summaries: int
    """How many summaries are merged, or would be."""
    from_sequence: int | None
    to_sequence: int | None
    tokens_before: int
    tokens_after: int | None
    estimated_cost: Decimal | None
    """The story's average priced summary: a condense is the same kind of call."""
    based_on: int
    cost: Decimal | None = None


async def oldest(session: AsyncSession, story_id: uuid.UUID, count: int | None) -> list[Summary]:
    """The summaries to merge: the oldest `count`, or all but the newest — the newest is the
    stretch the scene in progress leans on, and it goes in only when asked for by number."""
    rows = await memory.summaries_of(session, story_id)
    wanted = len(rows) - 1 if count is None else count
    return rows[:wanted]


async def estimate(session: AsyncSession, story_id: uuid.UUID) -> tuple[Decimal | None, int]:
    row = (
        await session.execute(
            select(func.avg(Spend.cost), func.count()).where(
                Spend.story_id == story_id,
                Spend.kind == SpendKind.SUMMARY,
                Spend.cost.is_not(None),
            )
        )
    ).one()
    average, count = row
    if average is None:
        return None, 0
    return Decimal(average), int(count)


def _plan(chosen: Sequence[Summary], estimated: Decimal | None, based_on: int) -> Condensed:
    before = sum(tokens.count(s.text) for s in chosen)
    return Condensed(
        dry_run=True,
        summaries=len(chosen),
        from_sequence=chosen[0].from_sequence if chosen else None,
        to_sequence=chosen[-1].to_sequence if chosen else None,
        tokens_before=before,
        tokens_after=None,
        estimated_cost=estimated,
        based_on=based_on,
    )


async def condense(
    session: AsyncSession,
    openrouter: OpenRouter,
    settings: Settings,
    story: Story,
    chosen: Sequence[Summary],
) -> Condensed:
    """One call, one row in place of `chosen`, in one transaction. Refused — billed, nothing
    replaced — when the answer stopped at the ceiling or is too short to have kept the stretch,
    by the summariser's own floor."""
    estimated, based_on = await estimate(session, story.id)
    messages = [ChatMessage("system", INSTRUCTION), ChatMessage("user", stretch(chosen))]

    async def call() -> Reply:
        return await openrouter.complete(
            messages,
            model=settings.background_model or settings.model,
            temperature=CONDENSE_TEMPERATURE,
            max_tokens=CONDENSE_MAX_TOKENS,
            reasoning=False,
        )

    try:
        reply = await background.once_more_if_worth_it(call)
    except ModelError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Nothing was condensed: {error}"
        ) from error
    session.add(ledger.row(story.id, SpendKind.CONDENSE, reply))
    text = reply.text.strip()
    before = sum(tokens.count(s.text) for s in chosen)
    produced = tokens.count(text)
    floor = max(memory.LEAST_SUMMARY_TOKENS, before // memory.LEAST_COMPRESSION)
    if reply.truncated or produced < floor:
        await session.commit()
        why = "was cut off at the ceiling" if reply.truncated else "is too short to be believed"
        log.warning("condense refused: %d tokens for %d summaries (%s)", produced, len(chosen), why)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"The account {why}; the summaries are as they were."
        )
    # The old rows go first, explicitly: the unit of work would insert before it deletes, and
    # the new row takes the first one's starting turn, which is unique per story.
    await session.execute(delete(Summary).where(Summary.id.in_([s.id for s in chosen])))
    session.add(
        Summary(
            story_id=story.id,
            from_sequence=chosen[0].from_sequence,
            to_sequence=chosen[-1].to_sequence,
            text=text,
            model=reply.model,
            message_count=sum(s.message_count for s in chosen),
        )
    )
    await session.commit()
    return Condensed(
        dry_run=False,
        summaries=len(chosen),
        from_sequence=chosen[0].from_sequence,
        to_sequence=chosen[-1].to_sequence,
        tokens_before=before,
        tokens_after=produced,
        estimated_cost=estimated,
        based_on=based_on,
        cost=reply.cost,
    )


router = APIRouter(prefix="/stories/{story_id}/memory", tags=["memory"])


@router.post("/condense")
async def condense_summaries(
    story_id: uuid.UUID,
    session: Session,
    openrouter: Model,
    settings: CurrentSettings,
    count: int | None = None,
    dry_run: bool = False,
) -> Condensed:
    """Merges the story's oldest `count` summaries — all but the newest when not given — into
    one. Billed; `dry_run` says what would be merged and what it would cost, and calls nothing."""
    story = await visible_story(session, story_id)
    if count is not None and count < 2:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A condense merges at least two summaries."
        )
    chosen = await oldest(session, story.id, count)
    if len(chosen) < 2:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "This story has fewer than two summaries to merge."
        )
    if dry_run:
        return _plan(chosen, *await estimate(session, story.id))
    return await condense(session, openrouter, settings, story, chosen)
