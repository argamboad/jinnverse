"""Condense summaries: the oldest N merged into one, on request, billed, the cost shown first."""

from decimal import Decimal

import httpx2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lustjinn import condense
from lustjinn.models import Spend, SpendKind, Story, Summary
from tests.scripted_model import ScriptedModel
from tests.streaming import send
from tests.test_summaries import a_long_story
from tests.test_turns import ledger

STRETCHES = ((1, 10), (11, 20), (21, 30))


async def a_story_with_summaries(session: AsyncSession) -> Story:
    """Thirty-one turns, the first thirty covered by three summaries, each a paragraph long."""
    story = await a_long_story(session, 30)
    for n, (low, high) in enumerate(STRETCHES, 1):
        session.add(
            Summary(
                story_id=story.id,
                from_sequence=low,
                to_sequence=high,
                text=f"Stretch {n}. " + "Rowan took a room and paid for the week. " * 8,
                model="m",
                message_count=high - low + 1,
            )
        )
    await session.commit()
    return story


async def summaries(session: AsyncSession, story: Story) -> list[Summary]:
    return list(
        await session.scalars(
            select(Summary)
            .where(Summary.story_id == story.id)
            .order_by(Summary.from_sequence)
            .execution_options(populate_existing=True)
        )
    )


async def post_condense(client: httpx2.AsyncClient, story: Story, **params: str):
    return await client.post(f"/stories/{story.id}/memory/condense", params=params)


async def test_a_dry_run_says_what_would_merge_and_calls_nothing(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_summaries(session)

    response = await post_condense(client, story, dry_run="true")

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert (body["summaries"], body["from_sequence"], body["to_sequence"]) == (2, 1, 20)
    assert body["tokens_before"] > 0
    assert body["tokens_after"] is None
    assert body["estimated_cost"] is None  # no summary has been priced in this story
    assert model.calls == []
    assert len(await summaries(session, story)) == 3


async def test_the_oldest_summaries_become_one_and_the_newest_is_kept(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_summaries(session)
    model.summarises("Rowan arrived and took a room, then paid for the week.")

    response = await post_condense(client, story)

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is False
    assert (body["summaries"], body["from_sequence"], body["to_sequence"]) == (2, 1, 20)
    assert body["tokens_after"] < body["tokens_before"]
    assert Decimal(body["cost"]) == Decimal("0.0002")
    merged, newest = await summaries(session, story)
    assert (merged.from_sequence, merged.to_sequence, merged.message_count) == (1, 20, 20)
    assert merged.text.startswith("Rowan arrived and took a room, then paid for the week.")
    assert merged.model == "test-model"
    assert (newest.from_sequence, newest.to_sequence) == (21, 30)
    [call] = model.calls
    assert call["messages"][0]["content"] == condense.INSTRUCTION
    sent = call["messages"][1]["content"]
    assert '<summary turns="1-10">\nStretch 1.' in sent
    assert '<summary turns="11-20">' in sent
    assert "Stretch 3." not in sent
    assert sent.endswith(f"Use at most {condense.CONDENSE_WORDS} words.")
    assert call["temperature"] == condense.CONDENSE_TEMPERATURE
    assert call["max_tokens"] == condense.CONDENSE_MAX_TOKENS
    assert call["reasoning"] == {"enabled": False}


async def test_a_count_merges_that_many_including_the_newest(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_summaries(session)
    model.summarises("All of it.")

    response = await post_condense(client, story, count="3")

    assert response.status_code == 200
    [only] = await summaries(session, story)
    assert (only.from_sequence, only.to_sequence, only.message_count) == (1, 30, 30)


async def test_the_condensed_summary_is_what_the_next_prompt_carries(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_summaries(session)
    model.summarises("Rowan arrived and took a room, then paid for the week.").says("Hm.")
    await post_condense(client, story)

    await send(client, story.id, "I come in.")

    texts = [m["content"] for m in model.last["messages"]]
    layer = next(t for t in texts if "Rowan arrived and took a room, then paid" in t)
    assert "Stretch 1." not in layer
    assert "Stretch 3." in layer  # the newest, still its own


async def test_it_is_billed_as_its_own_kind(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_summaries(session)
    model.summarises("Merged.")

    await post_condense(client, story)

    [row] = await ledger(session, story)
    assert row.kind is SpendKind.CONDENSE
    assert row.message_id is None


async def test_the_estimate_is_the_story_average_priced_summary(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_story_with_summaries(session)
    for cost in (Decimal("0.0002"), Decimal("0.0004"), None):  # an unpriced row is not averaged
        session.add(Spend(story_id=story.id, kind=SpendKind.SUMMARY, model="m", cost=cost))
    session.add(Spend(story_id=story.id, kind=SpendKind.REPLY, model="m", cost=Decimal("0.01")))
    await session.commit()

    body = (await post_condense(client, story, dry_run="true")).json()

    assert Decimal(body["estimated_cost"]) == Decimal("0.0003")
    assert body["based_on"] == 2


async def test_an_account_cut_off_or_too_short_is_refused_and_still_billed(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_summaries(session)
    model.truncated("Rowan arrived and" + " then" * 30)
    model.says("##")

    cut = await post_condense(client, story)
    short = await post_condense(client, story)

    assert cut.status_code == 502
    assert "cut off" in cut.json()["detail"]
    assert short.status_code == 502
    assert "too short" in short.json()["detail"]
    assert len(await summaries(session, story)) == 3
    assert [row.kind for row in await ledger(session, story)] == [
        SpendKind.CONDENSE,
        SpendKind.CONDENSE,
    ]


async def test_a_model_that_fails_twice_changes_nothing_and_bills_nothing(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_summaries(session)
    model.fails().fails()

    response = await post_condense(client, story)

    assert response.status_code == 502
    assert len(await summaries(session, story)) == 3
    assert await ledger(session, story) == []


async def test_fewer_than_two_summaries_is_nothing_to_condense(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_long_story(session, 10)

    none = await post_condense(client, story)
    one = await post_condense(client, story, count="1")

    assert none.status_code == 409
    assert one.status_code == 422
    assert model.calls == []
