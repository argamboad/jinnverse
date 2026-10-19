"""Review facts: the model proposes from the story's own prompt, the reader confirms, the
confirmed set is applied as one. Billed, with the cost estimated first."""

import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lustjinn import facts, review
from lustjinn.models import Fact, SpendKind, Story
from tests.scripted_model import ScriptedModel
from tests.streaming import send
from tests.test_turns import a_played_story, ledger


async def a_story_with_facts(session: AsyncSession, story: Story | None = None) -> Story:
    """A played story believing three things, one of them pinned, in a known order."""
    story = story or await a_played_story(session)
    session.add(facts.add(story, "Rowan Hale", "is expected at the dock at dawn.", 1, model="m"))
    session.add(facts.add(story, "Rowan Hale", "carries a knife.", 1, model="m"))
    session.add(facts.add(story, "Isaure", "is allergic to shellfish.", 1))  # pinned
    await session.commit()
    return story


async def live(session: AsyncSession, story: Story) -> list[Fact]:
    return list(
        await session.scalars(
            select(Fact)
            .where(Fact.story_id == story.id, Fact.valid_to_sequence.is_(None))
            .order_by(Fact.valid_from_sequence, Fact.created_at)
            .execution_options(populate_existing=True)
        )
    )


def proposing(*proposals: Mapping[str, object]) -> str:
    return json.dumps({"proposals": list(proposals)})


async def post_review(client: httpx2.AsyncClient, story: Story, **params: str):
    return await client.post(f"/stories/{story.id}/facts/review", params=params)


async def test_a_dry_run_estimates_from_the_priced_replies_and_calls_nothing(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_played_story(session)
    model.says("Hm.")
    await send(client, story.id, "I come in.")  # one priced reply at 0.0002
    calls = len(model.calls)

    response = await post_review(client, story, dry_run="true")

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert Decimal(body["estimated_cost"]) == Decimal("0.0002")
    assert body["based_on"] == 1
    assert body["proposals"] == []
    assert len(model.calls) == calls


async def test_a_story_with_no_priced_reply_has_no_estimate(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_played_story(session)

    body = (await post_review(client, story, dry_run="true")).json()

    assert body["estimated_cost"] is None
    assert body["based_on"] == 0


async def test_the_review_is_asked_from_the_story_prompt_with_the_facts_numbered(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_facts(session)
    model.says(proposing())

    response = await post_review(client, story)

    assert response.status_code == 200
    [call] = model.calls
    assert call["temperature"] == review.REVIEW_TEMPERATURE
    assert call["max_tokens"] == review.REVIEW_MAX_TOKENS
    assert call["reasoning"] == {"enabled": False}
    texts = [m["content"] for m in call["messages"]]
    assert texts[0].startswith("You are the narrator")  # the dummy's card: the prompt first…
    assert "1. Rowan Hale: is expected at the dock at dawn. (turn 1)" in texts[-1]
    assert "3. Isaure: is allergic to shellfish. (turn 1, pinned)" in texts[-1]
    assert texts[-1].startswith("A request from the reader, out of character")  # …then the ask


async def test_proposals_come_back_with_the_facts_they_touch_and_change_nothing(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_facts(session)
    model.says(
        proposing(
            {
                "action": "rewrite",
                "facts": [1],
                "text": "went to the dock at dawn.",
                "reason": "The dawn has come.",
            },
            {"action": "retire", "facts": [2], "reason": "Dropped in the river."},
        )
    )

    body = (await post_review(client, story)).json()

    assert body["dry_run"] is False
    assert [p["action"] for p in body["proposals"]] == ["rewrite", "retire"]
    rewrite = body["proposals"][0]
    assert rewrite["facts"][0]["text"] == "is expected at the dock at dawn."
    assert rewrite["text"] == "went to the dock at dawn."
    assert rewrite["reason"] == "The dawn has come."
    assert body["skipped"] == 0
    assert Decimal(body["cost"]) == Decimal("0.0002")
    assert [f.text for f in await live(session, story)] == [
        "is expected at the dock at dawn.",
        "carries a knife.",
        "is allergic to shellfish.",
    ]  # proposed, not applied


async def test_the_review_is_billed_as_its_own_kind(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_facts(session)
    model.says(proposing())

    await post_review(client, story)

    [row] = await ledger(session, story)
    assert row.kind is SpendKind.REVIEW
    assert row.message_id is None


async def test_a_review_cut_off_at_the_ceiling_is_refused_and_still_billed(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_facts(session)
    model.truncated('{"proposals": [{"action": "retire", "facts": [2]')

    response = await post_review(client, story)

    assert response.status_code == 502
    assert "cut off" in response.json()["detail"]
    assert [row.kind for row in await ledger(session, story)] == [SpendKind.REVIEW]


async def test_a_review_that_is_not_json_is_refused_and_still_billed(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_facts(session)
    model.says("I would rather not.")

    response = await post_review(client, story)

    assert response.status_code == 502
    assert [row.kind for row in await ledger(session, story)] == [SpendKind.REVIEW]


async def test_a_model_that_fails_costs_nothing_and_says_so(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_facts(session)
    model.fails()

    response = await post_review(client, story)

    assert response.status_code == 502
    assert await ledger(session, story) == []


# --- what is kept of an answer --------------------------------------------------------------------


def unsaved(subject: str, text: str, *, pinned: bool = False) -> Fact:
    """A fact that never reached the database, with the id and time it would have got there."""
    fact = facts.add(Story(name="s"), subject, text, 1, model=None if pinned else "m")
    fact.id = uuid.uuid4()
    fact.created_at = datetime.now(UTC)
    return fact


def three() -> list[Fact]:
    return [unsaved("A", "one."), unsaved("B", "two."), unsaved("C", "three.", pinned=True)]


def test_a_pinned_fact_is_never_proposed() -> None:
    kept, skipped = review.parse(proposing({"action": "retire", "facts": [3]}), three())

    assert kept == []
    assert skipped == 1


def test_a_fact_appears_in_one_proposal_at_most() -> None:
    answer = proposing(
        {"action": "rewrite", "facts": [1], "text": "one, now."},
        {"action": "merge", "facts": [1, 2], "text": "one and two."},
        {"action": "retire", "facts": [2]},
    )

    kept, skipped = review.parse(answer, three())

    assert [(p.action, [f.text for f in p.facts]) for p in kept] == [
        ("rewrite", ["one."]),
        ("retire", ["two."]),
    ]
    assert skipped == 1  # the merge: fact 1 was taken


def test_a_number_off_the_list_or_the_wrong_shape_is_dropped() -> None:
    answer = proposing(
        {"action": "retire", "facts": [4]},
        {"action": "retire", "facts": [1], "text": "a retire carries no text"},
        {"action": "rewrite", "facts": [1]},
        {"action": "merge", "facts": [1], "text": "a merge of one"},
        {"action": "rewrite", "facts": [1, 2], "text": "a rewrite of two"},
        {"action": "forget", "facts": [1]},
        {"action": "retire", "facts": ["2"], "reason": "a number as a string still counts"},
    )

    kept, skipped = review.parse(answer, three())

    assert [(p.action, p.facts[0].text) for p in kept] == [("retire", "two.")]
    assert skipped == 6


def test_at_most_twelve_proposals_are_kept() -> None:
    many = [unsaved("S", f"{i}.") for i in range(20)]
    answer = proposing(*({"action": "retire", "facts": [i + 1]} for i in range(20)))

    kept, skipped = review.parse(answer, many)

    assert (len(kept), skipped) == (review.MOST_PROPOSALS, 20 - review.MOST_PROPOSALS)


def test_an_answer_with_no_object_is_refused() -> None:
    with pytest.raises(ValueError, match="no JSON object"):
        review.parse("No.", three())


# --- applying -------------------------------------------------------------------------------------


async def post_apply(client: httpx2.AsyncClient, story: Story, confirmed: list[dict[str, object]]):
    return await client.post(f"/stories/{story.id}/facts/review/apply", json=confirmed)


async def test_confirmed_proposals_retire_their_facts_and_add_the_new_sentence(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_facts(session)
    plan, knife, _pinned = await live(session, story)
    model.says("Hm.").says("Hm.")
    await send(client, story.id, "I come in.")  # the story moves to turn 3
    await send(client, story.id, "I sit.")  # and to turn 5

    response = await post_apply(
        client,
        story,
        [
            {
                "action": "rewrite",
                "fact_ids": [str(plan.id)],
                "text": "went to the dock at dawn.",
            },
            {"action": "retire", "fact_ids": [str(knife.id)]},
        ],
    )

    assert response.status_code == 200
    assert response.json() == {"retired": 2, "added": 1}
    now = await live(session, story)
    assert [(f.subject, f.text, f.valid_from_sequence, f.pinned) for f in now] == [
        ("Isaure", "is allergic to shellfish.", 1, True),
        ("Rowan Hale", "went to the dock at dawn.", 5, False),
    ]
    gone = await session.get(Fact, plan.id)
    assert gone is not None
    assert gone.valid_to_sequence == 5
    assert now[-1].model is not None  # proposed by a model, confirmed by a person: not pinned


async def test_a_merge_takes_its_subject_from_the_proposal_or_the_first_fact(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_story_with_facts(session)
    plan, knife, _pinned = await live(session, story)

    response = await post_apply(
        client,
        story,
        [
            {
                "action": "merge",
                "fact_ids": [str(plan.id), str(knife.id)],
                "subject": "Rowan Hale and the dock",
                "text": "is expected at the dock at dawn, with a knife.",
            }
        ],
    )

    assert response.status_code == 200
    [_pinned, merged] = await live(session, story)
    assert merged.subject == "Rowan Hale and the dock"
    assert merged.text == "is expected at the dock at dawn, with a knife."


async def test_a_pinned_or_retired_fact_refuses_the_whole_set(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    """All or none: the reader confirmed the set against the list as it was."""
    story = await a_story_with_facts(session)
    plan, _knife, pinned = await live(session, story)

    response = await post_apply(
        client,
        story,
        [
            {"action": "retire", "fact_ids": [str(plan.id)]},
            {"action": "retire", "fact_ids": [str(pinned.id)]},
        ],
    )

    assert response.status_code == 409
    assert all(f.valid_to_sequence is None for f in await live(session, story))


async def test_a_retire_with_text_or_a_rewrite_without_is_refused(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story = await a_story_with_facts(session)
    plan, *_ = await live(session, story)

    retire = await post_apply(
        client, story, [{"action": "retire", "fact_ids": [str(plan.id)], "text": "no"}]
    )
    rewrite = await post_apply(client, story, [{"action": "rewrite", "fact_ids": [str(plan.id)]}])

    assert retire.status_code == 422
    assert rewrite.status_code == 422
    assert len(await live(session, story)) == 3


async def test_another_story_cannot_be_reviewed_through_this_one(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    mine = await a_story_with_facts(session)
    theirs = await a_story_with_facts(session, await a_played_story(session))
    foreign, *_ = await live(session, theirs)

    response = await post_apply(client, mine, [{"action": "retire", "fact_ids": [str(foreign.id)]}])

    assert response.status_code == 409
    assert all(f.valid_to_sequence is None for f in await live(session, theirs))
