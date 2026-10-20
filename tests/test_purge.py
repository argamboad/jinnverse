"""Purge: the real erasure. Nothing of the story's text stays; its spend does."""

from decimal import Decimal

import httpx2
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lustjinn.models import (
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
from lustjinn.spend import PURGED
from tests.test_branching import a_story_with_a_memory

TABLES = (
    Message,
    Embedding,
    Summary,
    Fact,
    Tracker,
    Aside,
    DialValue,
    StatusField,
    StatusValue,
    StatusPin,
)


async def rows_of(session: AsyncSession, story_id: object) -> dict[str, int]:
    found: dict[str, int] = {}
    for table in TABLES:
        count = await session.scalar(select(func.count()).where(table.story_id == story_id))
        found[table.__tablename__] = count or 0
    return found


async def test_a_purged_story_leaves_no_text_in_any_table_and_its_spend_still_reports(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story, _turns = await a_story_with_a_memory(session)
    before = await rows_of(session, story.id)
    assert all(before.values())
    await client.delete(f"/stories/{story.id}")

    response = await client.post(f"/stories/{story.id}/purge")

    assert response.status_code == 200, response.text
    report = response.json()
    assert report["messages"] == 10
    assert report["embeddings"] == 7
    assert (report["summaries"], report["facts"], report["trackers"]) == (2, 4, 1)
    assert (report["asides"], report["dial_values"]) == (2, 1)
    assert (report["status_fields"], report["status_values"], report["status_pins"]) == (1, 2, 1)
    assert report["ledger_rows_kept"] == 1
    assert Decimal(report["ledger_cost_kept"]) == Decimal("0.0002")
    assert set((await rows_of(session, story.id)).values()) == {0}
    assert await session.get(Story, story.id) is None
    [spend] = await session.scalars(select(Spend).where(Spend.story_id == story.id))
    assert spend.cost == Decimal("0.0002")
    spent = (await client.get("/spend")).json()
    assert [(s["name"], s["calls"]) for s in spent["by_story"]] == [(PURGED, 1)]


async def test_a_visible_story_cannot_be_purged(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story, _turns = await a_story_with_a_memory(session)

    response = await client.post(f"/stories/{story.id}/purge")

    assert response.status_code == 409
    assert "Delete the story first" in response.json()["detail"]
    assert (await rows_of(session, story.id))["messages"] == 10


async def test_a_purged_story_is_gone_for_good(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    story, _turns = await a_story_with_a_memory(session)
    await client.delete(f"/stories/{story.id}")
    await client.post(f"/stories/{story.id}/purge")

    again = await client.post(f"/stories/{story.id}/purge")
    read = await client.get(f"/stories/{story.id}")

    assert again.status_code == 404
    assert read.status_code == 404


async def test_other_stories_are_untouched(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    doomed, _turns = await a_story_with_a_memory(session)
    kept, _more = await a_story_with_a_memory(session)
    await client.delete(f"/stories/{doomed.id}")

    await client.post(f"/stories/{doomed.id}/purge")

    assert (await rows_of(session, kept.id))["messages"] == 10
    assert await session.get(Story, kept.id) is not None


async def test_every_deleted_story_is_erased_at_once_and_the_live_ones_are_spared(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    first, _turns = await a_story_with_a_memory(session)
    second, _more = await a_story_with_a_memory(session)
    kept, _still = await a_story_with_a_memory(session)
    await client.patch(f"/stories/{second.id}", json={"name": "A second night"})
    await client.delete(f"/stories/{first.id}")
    await client.delete(f"/stories/{second.id}")

    looked = (await client.post("/stories/purge", params={"dry_run": True})).json()

    assert (looked["dry_run"], looked["stories"]) == (True, 2)
    assert looked["names"] == ["A second night", "First night"]
    assert (looked["messages"], looked["embeddings"], looked["ledger_rows_kept"]) == (20, 14, 2)
    assert (await rows_of(session, first.id))["messages"] == 10  # a dry run erases nothing

    response = await client.post("/stories/purge")

    assert response.status_code == 200, response.text
    erased = response.json()
    assert (erased["dry_run"], erased["stories"]) == (False, 2)
    assert {k: v for k, v in erased.items() if k != "dry_run"} == {
        k: v for k, v in looked.items() if k != "dry_run"
    }
    for gone in (first, second):
        assert set((await rows_of(session, gone.id)).values()) == {0}
        assert await session.get(Story, gone.id) is None
    assert (await rows_of(session, kept.id))["messages"] == 10
    assert await session.get(Story, kept.id) is not None
    assert len(list(await session.scalars(select(Spend)))) == 3  # the ledger keeps every bill


async def test_with_nothing_deleted_erasing_everything_erases_nothing(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    kept, _turns = await a_story_with_a_memory(session)

    erased = (await client.post("/stories/purge")).json()

    assert (erased["stories"], erased["names"], erased["messages"]) == (0, [], 0)
    assert Decimal(erased["ledger_cost_kept"]) == Decimal(0)
    assert (await rows_of(session, kept.id))["messages"] == 10
