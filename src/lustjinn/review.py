"""Review facts: the model proposes changes to what a story believes; the reader confirms.

A story's world state only grows. The extractor reads one stretch at a time and retires what
that stretch moved past (#231), but a plan made at turn 100 goes stale at turn 300, when the
extractor is not looking at it, and two facts recorded a hundred turns apart can say the same
thing. A review reads the whole list against the whole story — the prompt the reply model sees:
summaries, live history, facts — and proposes retirements, rewrites and merges, each with a
reason. Sent only the facts and the summaries, a reviewer believed an evening the summaries did
not yet cover was still ahead; it has to see what the reply model sees.

Nothing is applied until the reader confirms it, proposal by proposal: the reasons are there to
be judged, not believed. One billed call, about a reply's worth, and the cost is estimated from
the ledger before it is made.
"""

import json
import logging
import uuid
from collections.abc import Sequence
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lustjinn import dials, facts, ledger, memory, trackers
from lustjinn.deps import CurrentSettings, Model, Session
from lustjinn.facts import FactOut
from lustjinn.library import persona_of
from lustjinn.models import Fact, Spend, SpendKind, Story
from lustjinn.openrouter import ModelError, OpenRouter
from lustjinn.settings import Settings
from lustjinn.stories import playable_story, visible_messages

log = logging.getLogger(__name__)

REVIEW_TEMPERATURE = 0.2
"""Cold, like the extractor: a proposal the reader confirms becomes a fact in every prompt."""
REVIEW_MAX_TOKENS = 4000
"""Twelve proposals ran to about a thousand tokens; the room is for the model's manners."""
MOST_PROPOSALS = 12
"""Uncapped, a review of fifty-two facts rewrote forty-seven of them, most of them for nothing."""

Action = Literal["retire", "rewrite", "merge"]

DIRECTIVE = (
    "A request from the reader, out of character: review the facts this story believes, "
    "numbered below, against everything above — the summaries and the transcript since them. "
    "Do not continue the story; reply with JSON only, in this shape:\n"
    "{\n"
    '  "proposals": [\n'
    '    { "action": "retire", "facts": [3], "reason": "..." },\n'
    '    { "action": "rewrite", "facts": [7], "text": "...", "reason": "..." },\n'
    '    { "action": "merge", "facts": [2, 9], "subject": "...", "text": "...", '
    '"reason": "..." }\n'
    "  ]\n"
    "}\n\n"
    "Rules:\n"
    "- A plan, invitation or appointment that has since happened is rewritten into its outcome "
    '("invited to the open house tonight" becomes "attended the open house on Monday evening"), '
    "never dropped: what happened must stay known.\n"
    "- A fact that only records an event (a post published, a message sent) with nothing durable "
    "left behind is retired: the summaries hold what happened. If it left something durable (a "
    "standing, a possession, a promise), rewrite it as that.\n"
    "- Never retire a trait, a skill, a possession, a relationship, a role or who someone is "
    "because the story shows it: the summaries are compressed away over time, and these facts "
    "are what remains of them. Only an event with nothing durable behind it is retired.\n"
    "- Two facts that say the same thing, or one that contains another, are merged into one "
    "sentence that keeps every detail.\n"
    "- A fact that is still true as written is not listed.\n"
    "- Never invent: a rewrite or a merge may only say what the facts and the story above "
    "already say. Say that something happened only where the summaries or the transcript above "
    "show it happening; a plan whose day has not come in the story stays a plan.\n"
    f"- Propose only the changes the story above forces, at most {MOST_PROPOSALS}, the most "
    "important first. Each fact appears in at most one proposal: a merge replaces the rewrites "
    "of its parts.\n"
    '- "text" is one plain sentence in the language of the facts, without the subject\'s name '
    'in front; a merge of facts about different subjects names its "subject". Each reason is '
    "one short sentence a person can judge quickly.\n\n"
    "The facts:\n"
)


def directive(live: Sequence[Fact]) -> str:
    """The instruction, with the facts numbered from 1 in the order given — the order the
    answer's numbers are read in (#231: never an id prefix)."""
    lines = (
        f"{n}. {fact.subject}: {fact.text} (turn {fact.valid_from_sequence}"
        + (", pinned)" if fact.pinned else ")")
        for n, fact in enumerate(live, 1)
    )
    return DIRECTIVE + "\n".join(lines)


class Proposal(BaseModel):
    """One change the model proposes. `facts` are the live facts it would touch, in full, so a
    client can show what was there beside what it would become."""

    action: Action
    facts: list[FactOut]
    subject: str | None = None
    """For a rewrite or a merge: whose the new sentence is. Default: the first fact's."""
    text: str | None = None
    """For a rewrite or a merge: the new sentence."""
    reason: str


class Reviewed(BaseModel):
    dry_run: bool
    """True: no call was made; `estimated_cost` says what one would cost, and nothing else."""
    estimated_cost: Decimal | None
    """The story's average priced reply — what a review's prompt is — or None with no priced
    reply to go on."""
    based_on: int
    """How many priced replies the estimate averages."""
    proposals: list[Proposal]
    skipped: int
    """Proposals the model made that were not kept: a pinned fact, a number off the list, a fact
    already in an earlier proposal, a shape not agreed."""
    cost: Decimal | None = None
    """What the call was charged, when one was made and the API said."""


async def estimate(session: AsyncSession, story_id: uuid.UUID) -> tuple[Decimal | None, int]:
    """What a review would cost: the story's average priced reply, since the prompt is the
    same. (None, 0) when no reply has been priced yet."""
    row = (
        await session.execute(
            select(func.avg(Spend.cost), func.count()).where(
                Spend.story_id == story_id,
                Spend.kind == SpendKind.REPLY,
                Spend.cost.is_not(None),
            )
        )
    ).one()
    average, count = row
    if average is None:
        return None, 0
    return Decimal(average), int(count)


def _numbers(raw: object) -> list[int] | None:
    """The fact numbers of one proposal, or None when the entry is not a list of them."""
    if not isinstance(raw, list):
        return None
    numbers: list[int] = []
    for item in raw:  # pyright: ignore[reportUnknownVariableType]
        if isinstance(item, bool):
            return None
        if isinstance(item, int):
            numbers.append(item)
        elif isinstance(item, str) and item.strip().isdigit():
            numbers.append(int(item.strip()))
        else:
            return None
    return numbers


def parse(answer: str, live: Sequence[Fact]) -> tuple[list[Proposal], int]:
    """The proposals in the model's answer, read generously (the JSON from the first `{` to the
    last `}`), and how many were refused: a number off the list, a pinned fact, a fact already
    taken by an earlier proposal, a retire with text or a rewrite without, a merge of one.
    Anything doubtful is dropped rather than guessed at — the reader is about to confirm these."""
    start, end = answer.find("{"), answer.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in the answer")
    document = json.loads(answer[start : end + 1])
    if not isinstance(document, dict):
        raise ValueError("the answer is not a JSON object")
    kept: list[Proposal] = []
    skipped = 0
    taken: set[int] = set()
    for entry in document.get("proposals") or []:  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        if len(kept) >= MOST_PROPOSALS:
            skipped += 1
            continue
        proposal = _proposal(entry, live, taken)  # pyright: ignore[reportUnknownArgumentType]
        if proposal is None:
            skipped += 1
            continue
        kept.append(proposal)
    return kept, skipped


def _proposal(entry: object, live: Sequence[Fact], taken: set[int]) -> Proposal | None:
    if not isinstance(entry, dict):
        return None
    action = entry.get("action")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    numbers = _numbers(entry.get("facts"))  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
    text = entry.get("text")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    subject = entry.get("subject")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    reason = entry.get("reason")  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if action not in ("retire", "rewrite", "merge") or not numbers:
        return None
    if any(not 1 <= n <= len(live) for n in numbers) or len(set(numbers)) != len(numbers):
        return None
    chosen = [live[n - 1] for n in numbers]
    if any(fact.pinned for fact in chosen) or any(n in taken for n in numbers):
        return None
    wants_text = action != "retire"
    has_text = isinstance(text, str) and bool(text.strip())
    if wants_text != has_text or (action == "merge") != (len(numbers) > 1):
        return None
    taken.update(numbers)
    return Proposal(
        action=action,
        facts=[FactOut.model_validate(fact) for fact in chosen],
        subject=subject.strip() if isinstance(subject, str) and subject.strip() else None,
        text=text.strip() if isinstance(text, str) and wants_text else None,
        reason=reason.strip() if isinstance(reason, str) else "",
    )


async def propose(
    session: AsyncSession, openrouter: OpenRouter, settings: Settings, story: Story
) -> Reviewed:
    """One call over the story's own prompt, the facts numbered in the instruction; the answer
    read into proposals. Billed before it is judged, like every background call."""
    estimated, based_on = await estimate(session, story.id)
    persona = await persona_of(session, story)
    history = await visible_messages(session, story.id)
    directives, _reminders, _knobs = await dials.of_story(session, story.id)
    meters = trackers.render(await trackers.of(session, story.id))

    async def composed(live: Sequence[Fact]) -> memory.Composed:
        # The same compose as a turn, so the reviewer sees what the character sees — and so it
        # may compress what no longer fits, as a turn would.
        return await memory.compose(
            session,
            openrouter,
            settings,
            story,
            persona,
            history,
            directives=directives,
            trackers=meters,
            instruction=directive(live),
            reply_tokens=REVIEW_MAX_TOKENS,
            retrieval=False,
        )

    live = await facts.live_facts(session, story.id)
    built = await composed(live)
    # A compression extracts facts, and then the numbers in the instruction no longer match the
    # list: number them again until nothing moved.
    for _ in range(memory.MOST_SUMMARIES_A_TURN):
        if built.summarised is None:
            break
        live = await facts.live_facts(session, story.id)
        built = await composed(live)
    try:
        reply = await openrouter.complete(
            built.messages,
            model=settings.model,
            temperature=REVIEW_TEMPERATURE,
            max_tokens=REVIEW_MAX_TOKENS,
            reasoning=False,  # thinking ate the whole ceiling on thirteen facts and said nothing
        )
    except ModelError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"The review was not made: {error}"
        ) from error
    session.add(ledger.row(story.id, SpendKind.REVIEW, reply))
    if reply.truncated:
        await session.commit()
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"The review was cut off at {REVIEW_MAX_TOKENS} tokens and nothing of it is kept.",
        )
    try:
        proposals, skipped = parse(reply.text, live)
    except (ValueError, json.JSONDecodeError) as error:
        await session.commit()
        log.warning("review unreadable: %s", error)
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "The review was not readable as JSON."
        ) from error
    await session.commit()
    return Reviewed(
        dry_run=False,
        estimated_cost=estimated,
        based_on=based_on,
        proposals=proposals,
        skipped=skipped,
        cost=reply.cost,
    )


# --- applying what the reader confirmed -----------------------------------------------------------

Words = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Subject = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class Confirmed(BaseModel):
    """A proposal the reader confirmed, as the client sends it back: the facts by id."""

    action: Action
    fact_ids: list[uuid.UUID] = Field(min_length=1)
    subject: Subject | None = None
    text: Words | None = None


class Applied(BaseModel):
    retired: int
    added: int


async def apply(
    session: AsyncSession, settings: Settings, story: Story, confirmed: Sequence[Confirmed]
) -> Applied:
    """Retires the facts of every confirmed proposal at the story's current turn and adds the new
    sentence of each rewrite or merge, as one transaction: a proposal that no longer applies — a
    fact retired or pinned meanwhile, an id that is not this story's — refuses the whole set."""
    live = {fact.id: fact for fact in await facts.live_facts(session, story.id)}
    at = await facts.newest_sequence(session, story.id)
    seen: set[uuid.UUID] = set()
    retired = added = 0
    for proposal in confirmed:
        sources = [live.get(fact_id) for fact_id in proposal.fact_ids]
        if any(fact is None or fact.pinned or fact.id in seen for fact in sources):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A confirmed proposal names a fact that is pinned, already retired, or in "
                "another proposal. Review again.",
            )
        if (proposal.action == "retire") == (proposal.text is not None):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "A retire carries no text; a rewrite or a merge carries the new sentence.",
            )
        for fact in sources:
            assert fact is not None  # checked above; for the type checker
            fact.valid_to_sequence = max(fact.valid_from_sequence, at)
            seen.add(fact.id)
            retired += 1
        if proposal.text is not None:
            first = sources[0]
            assert first is not None
            session.add(
                facts.add(
                    story,
                    proposal.subject or first.subject,
                    proposal.text,
                    at,
                    model=settings.model,  # the model proposed it; a person only confirmed
                )
            )
            added += 1
    await session.commit()
    return Applied(retired=retired, added=added)


router = APIRouter(prefix="/stories/{story_id}/facts/review", tags=["facts"])


@router.post("")
async def review_facts(
    story_id: uuid.UUID,
    session: Session,
    openrouter: Model,
    settings: CurrentSettings,
    dry_run: bool = False,
) -> Reviewed:
    """Asks the model what to retire, rewrite or merge among the story's live facts, from the
    story's own prompt. Billed; `dry_run` only estimates the cost. Nothing is changed until the
    confirmed proposals come back to `/apply`."""
    story = await playable_story(session, story_id)
    if dry_run:
        estimated, based_on = await estimate(session, story.id)
        return Reviewed(
            dry_run=True, estimated_cost=estimated, based_on=based_on, proposals=[], skipped=0
        )
    return await propose(session, openrouter, settings, story)


@router.post("/apply")
async def apply_review(
    story_id: uuid.UUID, confirmed: list[Confirmed], session: Session, settings: CurrentSettings
) -> Applied:
    """Applies the proposals the reader confirmed, all or none. No model call."""
    story = await playable_story(session, story_id)
    return await apply(session, settings, story, confirmed)
