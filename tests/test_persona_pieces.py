"""Persona pieces: the pool, the joiner that builds a persona from a pick, and the persona it makes.

The format under test is the one the owner's personas already have: paragraphs in a fixed order,
a line break between them, the vehicle and the pets in the home paragraph.
"""

from typing import Any

import httpx2
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lustjinn.models import Persona, PersonaPiece, PieceSlot, Voice
from lustjinn.persona_pieces import PieceError, assemble, check_voice, slots, slug

Json = dict[str, Any]


def a_piece(
    slot: PieceSlot,
    text: str,
    *,
    voice: Voice = Voice.HE,
    name: str = "a piece",
    short: str | None = None,
) -> PersonaPiece:
    return PersonaPiece(slot=slot, voice=voice, name=name, text=text, short=short)


def a_name(full: str = "Allan Sanlúcar El Kettani", short: str = "Allan") -> PersonaPiece:
    return a_piece(PieceSlot.NAME, full, name=full, short=short)


# --- the joiner, as pure functions -----------------------------------------------------------


def test_the_paragraphs_come_in_their_order_whatever_the_order_of_the_pick() -> None:
    picks = {
        PieceSlot.PASSIONS: [a_piece(PieceSlot.PASSIONS, "His passions include music.")],
        PieceSlot.LOOK: [a_piece(PieceSlot.LOOK, "He is tall.")],
        PieceSlot.HUMOUR: [a_piece(PieceSlot.HUMOUR, "His humor is dry.")],
        PieceSlot.PERSONALITY: [a_piece(PieceSlot.PERSONALITY, "He is curious.")],
    }

    assert assemble(picks) == (
        "He is tall.\nHe is curious.\nHis humor is dry.\nHis passions include music."
    )


def test_an_empty_slot_is_skipped_and_leaves_no_blank_line() -> None:
    picks = {
        PieceSlot.LOOK: [a_piece(PieceSlot.LOOK, "He is tall.")],
        PieceSlot.HOME: [],
        PieceSlot.PASSIONS: [a_piece(PieceSlot.PASSIONS, "He likes coffee.")],
    }

    assert assemble(picks) == "He is tall.\nHe likes coffee."


def test_home_vehicle_and_pets_are_one_paragraph() -> None:
    picks = {
        PieceSlot.PETS: [a_piece(PieceSlot.PETS, "He has a corgi named Lupo.")],
        PieceSlot.HOME: [a_piece(PieceSlot.HOME, "He lives in a penthouse.")],
        PieceSlot.VEHICLE: [a_piece(PieceSlot.VEHICLE, "He rides a motorcycle.")],
        PieceSlot.PERSONALITY: [a_piece(PieceSlot.PERSONALITY, "He is curious.")],
    }

    assert assemble(picks) == (
        "He lives in a penthouse. He rides a motorcycle. He has a corgi named Lupo.\nHe is curious."
    )


def test_a_slot_with_two_pieces_writes_two_paragraphs() -> None:
    picks = {
        PieceSlot.FAMILY: [
            a_piece(PieceSlot.FAMILY, "He is the son of a guitarist."),
            a_piece(PieceSlot.FAMILY, "His twin sister is an artist."),
        ]
    }

    assert assemble(picks) == "He is the son of a guitarist.\nHis twin sister is an artist."


def test_a_piece_may_hold_more_than_one_paragraph() -> None:
    picks = {PieceSlot.WORK: [a_piece(PieceSlot.WORK, "He runs a channel.\nHe is recognised.")]}

    assert assemble(picks) == "He runs a channel.\nHe is recognised."


def test_a_piece_is_trimmed_so_no_stray_space_reaches_the_persona() -> None:
    picks = {
        PieceSlot.LOOK: [a_piece(PieceSlot.LOOK, "  He is tall.\n")],
        PieceSlot.HUMOUR: [a_piece(PieceSlot.HUMOUR, "His humor is dry. ")],
    }

    assert assemble(picks) == "He is tall.\nHis humor is dry."


def test_the_name_is_written_where_the_pieces_ask_for_it() -> None:
    picks = {
        PieceSlot.NAME: [a_name()],
        PieceSlot.LOOK: [a_piece(PieceSlot.LOOK, "{name} is an athletic young man.")],
        PieceSlot.FAMILY: [a_piece(PieceSlot.FAMILY, "{short} is the son of a guitarist.")],
    }

    assert assemble(picks) == (
        "Allan Sanlúcar El Kettani is an athletic young man.\nAllan is the son of a guitarist."
    )


def test_a_piece_that_asks_for_a_name_is_refused_when_none_was_picked() -> None:
    picks = {PieceSlot.LOOK: [a_piece(PieceSlot.LOOK, "{name} is tall.")]}

    with pytest.raises(PieceError, match="pick a name piece"):
        assemble(picks)


def test_pieces_with_no_placeholder_need_no_name() -> None:
    assert assemble({PieceSlot.LOOK: [a_piece(PieceSlot.LOOK, "He is tall.")]}) == "He is tall."


def test_a_persona_has_one_name() -> None:
    with pytest.raises(PieceError, match="one name"):
        assemble({PieceSlot.NAME: [a_name(), a_name("Allan McAllister", "Allan")]})


def test_an_empty_pick_makes_nothing() -> None:
    with pytest.raises(PieceError, match="at least one"):
        assemble({})
    with pytest.raises(PieceError, match="at least one"):
        assemble({PieceSlot.NAME: [a_name()]})  # a name alone is not a persona


def test_a_piece_written_in_another_voice_is_refused_and_one_with_none_is_not() -> None:
    she = a_piece(PieceSlot.LOOK, "She is tall.", voice=Voice.SHE, name="tall")
    anyone = a_piece(PieceSlot.HOME, "A flat by the sea.", voice=Voice.ANY)

    check_voice(Voice.SHE, [she, anyone])
    check_voice(Voice.HE, [anyone])
    with pytest.raises(PieceError, match="'tall' is written in the she voice"):
        check_voice(Voice.HE, [she, anyone])


def test_the_slots_are_the_names_then_the_paragraphs_in_order() -> None:
    found = slots()

    assert [info.key for info in found] == list(PieceSlot)
    assert found[0].key is PieceSlot.NAME
    assert found[0].paragraph is None
    home = {info.key: info.paragraph for info in found}
    assert home[PieceSlot.HOME] == home[PieceSlot.VEHICLE] == home[PieceSlot.PETS]
    assert home[PieceSlot.LOOK] == 0
    assert home[PieceSlot.PASSIONS] == 8


def test_a_name_becomes_a_library_name() -> None:
    assert slug("Allan Sanlúcar El Kettani") == "allan-sanlucar-el-kettani"
    assert slug("  Dr. Mei-Ling Wu ") == "dr-mei-ling-wu"
    assert slug("!!!") == "persona"


# --- the pool ------------------------------------------------------------------------------------


async def piece(
    client: httpx2.AsyncClient,
    slot: str,
    name: str,
    text: str,
    voice: str = "he",
    **more: object,
) -> Json:
    response = await client.post(
        "/persona-pieces", json={"slot": slot, "voice": voice, "name": name, "text": text, **more}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_the_slots_are_served_so_a_client_does_not_hard_code_them(
    client: httpx2.AsyncClient,
) -> None:
    found = (await client.get("/persona-pieces/slots")).json()

    assert [slot["key"] for slot in found] == [slot.value for slot in PieceSlot]
    assert found[1] == {"key": "look", "label": "Identity and look", "paragraph": 0}


async def test_a_piece_can_be_created_listed_by_slot_and_voice_and_deleted(
    client: httpx2.AsyncClient,
) -> None:
    penthouse = await piece(client, "home", "Penthouse", "He lives in a penthouse.")
    await piece(client, "home", "Flat by the sea", "A flat by the sea.", voice="any")
    await piece(client, "home", "Her loft", "She lives in a loft.", voice="she")
    await piece(client, "pets", "Lupo", "He has a corgi named Lupo.")

    assert penthouse["version"] == 1
    homes = (await client.get("/persona-pieces", params={"slot": "home"})).json()
    assert [p["name"] for p in homes] == ["Flat by the sea", "Her loft", "Penthouse"]
    he_homes = (await client.get("/persona-pieces", params={"slot": "home", "voice": "he"})).json()
    assert [p["name"] for p in he_homes] == ["Flat by the sea", "Penthouse"]  # his, and no one's
    assert len((await client.get("/persona-pieces")).json()) == 4
    assert (await client.delete(f"/persona-pieces/{penthouse['id']}")).status_code == 204
    assert (await client.delete(f"/persona-pieces/{penthouse['id']}")).status_code == 404


async def test_a_name_piece_has_a_short_form_and_no_other_piece_does(
    client: httpx2.AsyncClient,
) -> None:
    named = await piece(client, "name", "Allan", "Allan Sanlúcar El Kettani", short="Allan")
    without = await client.post(
        "/persona-pieces",
        json={"slot": "name", "voice": "he", "name": "No short", "text": "Allan Ramos"},
    )
    with_one = await client.post(
        "/persona-pieces",
        json={"slot": "look", "voice": "he", "name": "Tall", "text": "x", "short": "Al"},
    )

    assert named["short"] == "Allan"
    assert without.status_code == 422
    assert with_one.status_code == 422


async def test_a_name_is_taken_in_a_slot_and_a_voice_in_any_case_but_not_across_voices(
    client: httpx2.AsyncClient,
) -> None:
    await piece(client, "home", "Penthouse", "He lives in a penthouse.")

    again = await client.post(
        "/persona-pieces",
        json={"slot": "home", "voice": "he", "name": "PENTHOUSE", "text": "Another."},
    )
    hers = await piece(client, "home", "Penthouse", "She lives in a penthouse.", voice="she")

    assert again.status_code == 409
    assert hers["voice"] == "she"


async def test_a_piece_is_saved_by_version_and_a_stale_save_gets_the_current_piece(
    client: httpx2.AsyncClient,
) -> None:
    made = await piece(client, "home", "Penthouse", "He lives in a penthouse.")

    saved = await client.patch(
        f"/persona-pieces/{made['id']}", json={"version": 1, "text": "He lives in a loft."}
    )
    stale = await client.patch(
        f"/persona-pieces/{made['id']}", json={"version": 1, "text": "Another edit."}
    )

    assert saved.status_code == 200
    assert (saved.json()["version"], saved.json()["text"]) == (2, "He lives in a loft.")
    assert stale.status_code == 409
    assert stale.json()["detail"]["current"]["text"] == "He lives in a loft."


async def test_only_a_name_piece_can_be_given_a_short_form_and_a_rename_cannot_take_a_name(
    client: httpx2.AsyncClient,
) -> None:
    home = await piece(client, "home", "Penthouse", "He lives in a penthouse.")
    await piece(client, "home", "Loft", "He lives in a loft.")

    short = await client.patch(f"/persona-pieces/{home['id']}", json={"version": 1, "short": "x"})
    taken = await client.patch(f"/persona-pieces/{home['id']}", json={"version": 1, "name": "loft"})

    assert short.status_code == 422
    assert taken.status_code == 409


# --- building a persona --------------------------------------------------------------------------


async def a_pool(client: httpx2.AsyncClient) -> dict[str, str]:
    """A name, a look, a home and a pet: the id of each, by slot."""
    return {
        "name": (await piece(client, "name", "Allan", "Allan Sanlúcar", short="Allan"))["id"],
        "look": (await piece(client, "look", "Athletic", "{name} is an athletic young man."))["id"],
        "home": (await piece(client, "home", "Penthouse", "{short} lives in a penthouse."))["id"],
        "pets": (await piece(client, "pets", "Lupo", "He has a corgi named Lupo."))["id"],
    }


def pick(ids: dict[str, str], *slots: str, **more: object) -> Json:
    return {"voice": "he", "pieces": {slot: [ids[slot]] for slot in slots}, **more}


async def test_a_pick_is_previewed_without_saving_anything(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    ids = await a_pool(client)

    preview = (
        await client.post("/persona-pieces/preview", json=pick(ids, "name", "look", "home", "pets"))
    ).json()

    assert preview == {
        "name": "allan-sanlucar",
        "text": "Allan Sanlúcar is an athletic young man.\n"
        "Allan lives in a penthouse. He has a corgi named Lupo.",
    }
    assert list(await session.scalars(select(Persona))) == []


async def test_a_pick_makes_an_ordinary_persona_in_the_library(
    client: httpx2.AsyncClient,
) -> None:
    ids = await a_pool(client)

    built = await client.post("/persona-pieces/build", json=pick(ids, "name", "look", "home"))

    assert built.status_code == 201, built.text
    made = built.json()
    assert made["name"] == "allan-sanlucar"
    read = (await client.get(f"/library/personas/{made['id']}")).json()
    assert read["text"] == ("Allan Sanlúcar is an athletic young man.\nAllan lives in a penthouse.")
    assert read["version"] == 1
    history = (await client.get(f"/library/personas/{made['id']}/history")).json()
    assert [row["version"] for row in history] == [1]


async def test_a_second_persona_from_the_same_name_gets_a_number(
    client: httpx2.AsyncClient,
) -> None:
    ids = await a_pool(client)

    first = (await client.post("/persona-pieces/build", json=pick(ids, "name", "look"))).json()
    second = (await client.post("/persona-pieces/build", json=pick(ids, "name", "look"))).json()
    preview = (await client.post("/persona-pieces/preview", json=pick(ids, "name", "look"))).json()

    assert [first["name"], second["name"], preview["name"]] == [
        "allan-sanlucar",
        "allan-sanlucar-2",
        "allan-sanlucar-3",
    ]


async def test_a_name_given_is_used_as_it_is_and_refused_when_taken(
    client: httpx2.AsyncClient,
) -> None:
    ids = await a_pool(client)

    named = await client.post(
        "/persona-pieces/build", json=pick(ids, "name", "look", name="allan-roomie")
    )
    again = await client.post(
        "/persona-pieces/build", json=pick(ids, "name", "look", name="Allan-Roomie")
    )
    reserved = await client.post(
        "/persona-pieces/build", json=pick(ids, "name", "look", name="a:b")
    )

    assert named.json()["name"] == "allan-roomie"
    assert again.status_code == 409
    assert reserved.status_code == 422


async def test_editing_or_deleting_a_piece_later_changes_no_persona_already_made(
    client: httpx2.AsyncClient,
) -> None:
    ids = await a_pool(client)
    made = (await client.post("/persona-pieces/build", json=pick(ids, "name", "look"))).json()

    await client.patch(
        f"/persona-pieces/{ids['look']}", json={"version": 1, "text": "{name} is short."}
    )
    await client.delete(f"/persona-pieces/{ids['look']}")

    read = (await client.get(f"/library/personas/{made['id']}")).json()
    assert read["text"] == "Allan Sanlúcar is an athletic young man."
    assert read["version"] == 1


async def test_a_persona_with_no_name_piece_needs_a_name_to_be_given(
    client: httpx2.AsyncClient,
) -> None:
    pet = await piece(client, "pets", "Lupo", "He has a corgi named Lupo.")
    body = {"voice": "he", "pieces": {"pets": [pet["id"]]}}

    refused = await client.post("/persona-pieces/build", json=body)
    given = await client.post("/persona-pieces/build", json={**body, "name": "just-a-dog-owner"})

    assert refused.status_code == 422
    assert given.status_code == 201


async def test_a_pick_that_cannot_make_a_persona_is_refused_with_the_reason(
    client: httpx2.AsyncClient,
) -> None:
    ids = await a_pool(client)
    hers = await piece(client, "look", "Tall", "She is tall.", voice="she")

    wrong_slot = await client.post(
        "/persona-pieces/build", json={"voice": "he", "pieces": {"home": [ids["look"]]}}
    )
    wrong_voice = await client.post(
        "/persona-pieces/build", json={"voice": "he", "pieces": {"look": [hers["id"]]}}
    )
    gone = await client.post(
        "/persona-pieces/build",
        json={"voice": "he", "pieces": {"look": ["01a11de3-c9c7-7508-91f6-e5e3bdd12b01"]}},
    )
    empty = await client.post("/persona-pieces/build", json={"voice": "he", "pieces": {}})

    assert wrong_slot.status_code == 422
    assert "is a look piece" in wrong_slot.json()["detail"]
    assert wrong_voice.status_code == 422
    assert "she voice" in wrong_voice.json()["detail"]
    assert gone.status_code == 422
    assert empty.status_code == 422


async def test_a_voice_is_a_choice_and_a_female_persona_is_built_from_her_own_pieces(
    client: httpx2.AsyncClient,
) -> None:
    name = await piece(client, "name", "Mara", "Mara Quinn", voice="she", short="Mara")
    look = await piece(client, "look", "Tall", "{name} is tall. She has red hair.", voice="she")

    built = await client.post(
        "/persona-pieces/build",
        json={"voice": "she", "pieces": {"name": [name["id"]], "look": [look["id"]]}},
    )

    assert built.status_code == 201
    assert built.json()["text"] == "Mara Quinn is tall. She has red hair."
