"""A character's lore entries (#266): kept under the character, saved by version, remembered in
the history, and gone with the character."""

from typing import Any

import httpx2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jinnverse.lore import clean_keys
from jinnverse.models import LibraryHistory, LibraryKind, LoreEntry
from scripts.seed_dummy import Dummy
from tests.factories import a_character, a_lore_entry

Json = dict[str, Any]


async def create(client: httpx2.AsyncClient, character_id: object, **body: object) -> Json:
    response = await client.post(f"/library/characters/{character_id}/lore", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_an_entry_can_be_created_listed_read_saved_and_deleted(
    client: httpx2.AsyncClient, session: AsyncSession, dummy: Dummy
) -> None:
    heron = await a_character(session, "The Gilded Heron")
    isaure = dummy.lore[0]

    made = await create(
        client, heron.id, name=isaure.name, keys=list(isaure.keys), text=isaure.text
    )

    assert made["name"] == "Isaure Vantongeren"
    assert made["keys"] == ["isaure", "vantongeren", "proprietor"]
    assert made["text"] == isaure.text
    assert made["version"] == 1
    assert made["description"] is None
    base = f"/library/characters/{heron.id}/lore"
    assert (await client.get(base)).json() == [made]
    assert (await client.get(f"{base}/{made['id']}")).json() == made

    saved = await client.patch(
        f"{base}/{made['id']}",
        json={"version": 1, "keys": ["Isaure", "the innkeeper"], "description": "The owner"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["keys"] == ["isaure", "the innkeeper"]
    assert saved.json()["description"] == "The owner"
    assert saved.json()["version"] == 2
    assert saved.json()["text"] == isaure.text  # not given, not touched

    assert (await client.delete(f"{base}/{made['id']}")).status_code == 204
    assert (await client.get(f"{base}/{made['id']}")).status_code == 404
    assert (await client.get(base)).json() == []


async def test_entries_are_listed_in_the_order_they_were_made(
    client: httpx2.AsyncClient, session: AsyncSession, dummy: Dummy
) -> None:
    """The order of the card they came from, not the alphabet: a lorebook is read as a card."""
    heron = await a_character(session, "The Gilded Heron")
    for entry in dummy.lore:
        await create(client, heron.id, name=entry.name, keys=list(entry.keys), text=entry.text)

    listed = (await client.get(f"/library/characters/{heron.id}/lore")).json()

    assert [e["name"] for e in listed] == [e.name for e in dummy.lore]


def test_keys_are_kept_lowercased_trimmed_and_without_repeats() -> None:
    assert clean_keys(["  Jax ", "BARTENDER", "jax", "", "Preston   Centre"]) == [
        "jax",
        "bartender",
        "preston centre",
    ]


async def test_an_entry_without_a_key_is_refused(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    heron = await a_character(session)

    response = await client.post(
        f"/library/characters/{heron.id}/lore", json={"name": "Jax", "keys": [" "], "text": "x"}
    )

    assert response.status_code == 422
    assert "at least one key" in response.text


async def test_a_name_is_unique_per_character_whatever_its_case(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    heron = await a_character(session, "The Gilded Heron")
    other = await a_character(session, "Elsewhere")
    await create(client, heron.id, name="Jax", keys=["jax"], text="A bartender.")

    again = await client.post(
        f"/library/characters/{heron.id}/lore", json={"name": "JAX", "keys": ["jax"], "text": "x"}
    )
    elsewhere = await create(client, other.id, name="Jax", keys=["jax"], text="Another Jax.")

    assert again.status_code == 409
    assert "already has an entry called 'JAX'" in again.json()["detail"]
    assert elsewhere["name"] == "Jax"


async def test_an_entry_belongs_to_its_character(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    heron = await a_character(session, "The Gilded Heron")
    other = await a_character(session, "Elsewhere")
    entry = await a_lore_entry(session, heron)

    assert (await client.get(f"/library/characters/{other.id}/lore/{entry.id}")).status_code == 404
    assert (await client.get(f"/library/characters/{heron.id}/lore/{entry.id}")).status_code == 200


async def test_a_save_over_an_edit_made_elsewhere_is_refused_with_the_current_text(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    heron = await a_character(session)
    opened = await create(client, heron.id, name="Jax", keys=["jax"], text="First.")
    base = f"/library/characters/{heron.id}/lore/{opened['id']}"
    laptop = await client.patch(base, json={"version": 1, "text": "From the laptop."})
    assert laptop.status_code == 200

    phone = await client.patch(base, json={"version": 1, "text": "From the phone."})

    assert phone.status_code == 409
    refused = phone.json()["detail"]
    assert "changed somewhere else" in refused["message"]
    assert refused["current"]["text"] == "From the laptop."
    assert refused["current"]["version"] == 2


async def test_every_version_is_kept_in_the_history(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    heron = await a_character(session)
    made = await create(client, heron.id, name="Jax", keys=["jax"], text="First.")
    base = f"/library/characters/{heron.id}/lore/{made['id']}"
    await client.patch(base, json={"version": 1, "text": "Second."})
    await client.patch(base, json={"version": 2, "text": "Second."})  # nothing changed: no row

    history = (await client.get(f"{base}/history")).json()

    assert [(h["version"], h["text"]) for h in history] == [(2, "Second."), (1, "First.")]
    kinds = await session.scalars(
        select(LibraryHistory.kind).where(LibraryHistory.entry_id == made["id"])
    )
    assert set(kinds) == {LibraryKind.LORE}


async def test_deleting_the_character_takes_its_entries(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    heron = await a_character(session, "The Gilded Heron")
    entry = await a_lore_entry(session, heron)
    await session.commit()

    assert (await client.delete(f"/library/characters/{heron.id}")).status_code == 204

    # The database cascaded; asked of the table, not of the session's copy of the entry.
    assert await session.scalar(select(LoreEntry.id).where(LoreEntry.id == entry.id)) is None


async def test_a_character_that_does_not_exist_has_no_lore(client: httpx2.AsyncClient) -> None:
    response = await client.get("/library/characters/01a11ce2-813c-7302-bdc3-ce3906805924/lore")

    assert response.status_code == 404
