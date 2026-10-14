"""The short description on characters, personas, snippets and persona pieces, and the counts of
the shelves (#160). A note for the owner: shown in lists, versioned with the entry, never read by
anything that builds a prompt."""

from typing import Any

import httpx2
import pytest

from lustjinn.library import Slug
from tests.factories import a_character, a_persona, a_story
from tests.scripted_model import ScriptedModel
from tests.streaming import send

Json = dict[str, Any]
SHELVES: list[Slug] = ["characters", "personas", "snippets"]


async def create(client: httpx2.AsyncClient, shelf: str, **body: object) -> Json:
    response = await client.post(f"/library/{shelf}", json=body)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("shelf", SHELVES)
async def test_an_entry_can_be_created_with_a_description_and_a_list_serves_it(
    client: httpx2.AsyncClient, shelf: Slug
) -> None:
    made = await create(client, shelf, name="elena", text="You are Elena.", description="A cook.")

    assert made["description"] == "A cook."
    read = (await client.get(f"/library/{shelf}/{made['id']}")).json()
    assert read["description"] == "A cook."
    [listed] = (await client.get(f"/library/{shelf}")).json()
    assert listed["description"] == "A cook."
    assert listed["preview"] == "You are Elena."  # the preview stays, as the fallback


@pytest.mark.parametrize("shelf", SHELVES)
async def test_an_entry_has_no_description_unless_one_is_given(
    client: httpx2.AsyncClient, shelf: Slug
) -> None:
    made = await create(client, shelf, name="elena", text="You are Elena.")

    assert made["description"] is None


async def test_a_description_is_trimmed_and_a_blank_one_is_none(
    client: httpx2.AsyncClient,
) -> None:
    padded = await create(client, "personas", name="a", text="x", description="  A cook.  ")
    blank = await create(client, "personas", name="b", text="x", description="   ")

    assert padded["description"] == "A cook."
    assert blank["description"] is None


async def test_a_description_over_the_limit_is_refused_with_a_sentence(
    client: httpx2.AsyncClient,
) -> None:
    response = await client.post(
        "/library/personas", json={"name": "a", "text": "x", "description": "x" * 201}
    )

    assert response.status_code == 422
    assert "A description is at most 200 characters." in response.text
    exactly = await create(client, "personas", name="b", text="x", description="x" * 200)
    assert len(exactly["description"]) == 200


async def test_a_save_that_changes_only_the_description_is_a_version_with_a_history_row(
    client: httpx2.AsyncClient,
) -> None:
    made = await create(client, "personas", name="elena", text="You are Elena.")

    saved = await client.patch(
        f"/library/personas/{made['id']}", json={"version": 1, "description": "A cook."}
    )

    assert saved.status_code == 200
    assert (saved.json()["version"], saved.json()["description"]) == (2, "A cook.")
    history = (await client.get(f"/library/personas/{made['id']}/history")).json()
    assert [(h["version"], h["description"]) for h in history] == [(2, "A cook."), (1, None)]


async def test_a_description_can_be_cleared_with_null_or_blank(
    client: httpx2.AsyncClient,
) -> None:
    made = await create(client, "snippets", name="storm", text="Rain.", description="Weather.")

    cleared = await client.patch(
        f"/library/snippets/{made['id']}", json={"version": 1, "description": None}
    )
    again = await client.patch(
        f"/library/snippets/{made['id']}", json={"version": 2, "description": "Back."}
    )
    blank = await client.patch(
        f"/library/snippets/{made['id']}", json={"version": 3, "description": "  "}
    )

    assert cleared.json()["description"] is None
    assert again.json()["description"] == "Back."
    assert blank.json()["description"] is None


async def test_a_save_that_leaves_the_description_out_does_not_touch_it(
    client: httpx2.AsyncClient,
) -> None:
    made = await create(client, "personas", name="elena", text="x", description="A cook.")

    renamed = await client.patch(
        f"/library/personas/{made['id']}", json={"version": 1, "name": "Elena Hale"}
    )

    assert renamed.json()["description"] == "A cook."


async def test_a_save_that_changes_nothing_writes_nothing(client: httpx2.AsyncClient) -> None:
    made = await create(client, "personas", name="elena", text="x", description="A cook.")

    same = await client.patch(
        f"/library/personas/{made['id']}", json={"version": 1, "description": "A cook."}
    )

    assert same.json()["version"] == 1
    history = (await client.get(f"/library/personas/{made['id']}/history")).json()
    assert [h["version"] for h in history] == [1]


async def test_the_first_history_row_carries_the_description_given_at_creation(
    client: httpx2.AsyncClient,
) -> None:
    made = await create(client, "characters", name="Elena", text="x", description="A cook.")

    [first] = (await client.get(f"/library/characters/{made['id']}/history")).json()

    assert first["description"] == "A cook."


async def test_a_description_over_the_limit_is_refused_on_a_save_too(
    client: httpx2.AsyncClient,
) -> None:
    made = await create(client, "personas", name="elena", text="x")

    response = await client.patch(
        f"/library/personas/{made['id']}", json={"version": 1, "description": "x" * 201}
    )

    assert response.status_code == 422


async def test_no_description_reaches_the_prompt(
    client: httpx2.AsyncClient, session: Any, model: ScriptedModel
) -> None:
    character = await a_character(session)
    persona = await a_persona(session)
    character.description = "A NOTE ABOUT THE CARD"
    persona.description = "A NOTE ABOUT THE PERSONA"
    story = await a_story(session, character)
    story.persona_id = persona.id
    await session.commit()
    model.says("Hm.")

    await send(client, story.id, "Hello.")

    sent = " ".join(m["content"] for m in model.last["messages"])
    assert "A NOTE ABOUT THE CARD" not in sent
    assert "A NOTE ABOUT THE PERSONA" not in sent


# --- the counts ----------------------------------------------------------------------------------


async def test_the_counts_say_how_many_entries_each_shelf_holds(
    client: httpx2.AsyncClient,
) -> None:
    await create(client, "characters", name="Elena", text="x")
    await create(client, "characters", name="Marta", text="x")
    await create(client, "personas", name="Me", text="x")
    await create(client, "snippets", name="storm", text="x")
    await client.post(
        "/persona-pieces", json={"slot": "look", "voice": "he", "name": "Tall", "text": "x"}
    )

    counts = (await client.get("/library/counts")).json()

    assert counts == {
        "characters": 2,
        "personas": 1,
        "snippets": 1,
        "pieces": 1,
        "hidden": {"characters": 0, "personas": 0, "snippets": 0},
    }


async def test_an_empty_library_counts_zero_everywhere(client: httpx2.AsyncClient) -> None:
    counts = (await client.get("/library/counts")).json()

    assert counts["characters"] == counts["personas"] == counts["snippets"] == 0
    assert counts["pieces"] == 0


async def test_the_counts_are_what_a_list_shows_and_the_underscore_ones_are_counted_apart(
    client: httpx2.AsyncClient,
) -> None:
    await create(client, "characters", name="Elena", text="x")
    await create(client, "characters", name="_template", text="x")
    await create(client, "characters", name="_notes", text="x")
    await create(client, "snippets", name="a_b", text="x")  # an underscore inside is not hidden

    counts = (await client.get("/library/counts")).json()
    listed = (await client.get("/library/characters")).json()

    assert counts["characters"] == len(listed) == 1
    assert counts["hidden"]["characters"] == 2
    assert counts["snippets"] == 1
    assert counts["hidden"]["snippets"] == 0


async def test_counts_is_not_mistaken_for_a_shelf(client: httpx2.AsyncClient) -> None:
    assert (await client.get("/library/counts")).status_code == 200
    assert (await client.get("/library/nonsense")).status_code == 422


# --- persona pieces ------------------------------------------------------------------------------


async def piece(client: httpx2.AsyncClient, **more: object) -> Json:
    body = {"slot": "home", "voice": "he", "name": "Penthouse", "text": "x", **more}
    response = await client.post("/persona-pieces", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def test_a_piece_can_carry_a_description_that_is_served_set_and_cleared(
    client: httpx2.AsyncClient,
) -> None:
    made = await piece(client, description="Across from the university")

    assert made["description"] == "Across from the university"
    listed = (await client.get("/persona-pieces")).json()
    assert listed[0]["description"] == "Across from the university"
    changed = await client.patch(
        f"/persona-pieces/{made['id']}", json={"version": 1, "description": "A loft"}
    )
    cleared = await client.patch(
        f"/persona-pieces/{made['id']}", json={"version": 2, "description": None}
    )
    assert (changed.json()["version"], changed.json()["description"]) == (2, "A loft")
    assert cleared.json()["description"] is None


async def test_a_piece_description_is_limited_like_the_others(client: httpx2.AsyncClient) -> None:
    response = await client.post(
        "/persona-pieces",
        json={
            "slot": "home",
            "voice": "he",
            "name": "x",
            "text": "x",
            "description": "x" * 201,
        },
    )

    assert response.status_code == 422


async def test_a_persona_built_from_a_piece_does_not_carry_its_description(
    client: httpx2.AsyncClient,
) -> None:
    look = await piece(client, slot="look", name="Tall", text="He is tall.", description="NOTE")

    built = await client.post(
        "/persona-pieces/build",
        json={"voice": "he", "pieces": {"look": [look["id"]]}, "name": "tall-man"},
    )

    persona = (await client.get(f"/library/personas/{built.json()['id']}")).json()
    assert persona["text"] == "He is tall."
    assert persona["description"] is None
