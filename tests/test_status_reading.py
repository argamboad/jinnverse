"""Status blocks: a reply's lines read into stored values, and rewound when the transcript changes
(#171)."""

import httpx2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lustjinn import blocks
from lustjinn.blocks import Reading, read
from lustjinn.models import Message, StatusField, StatusValue, Story
from tests.scripted_model import ScriptedModel
from tests.streaming import send, stream
from tests.test_turns import a_played_story


def field(
    key: str,
    label: str,
    icon: str | None,
    scope: str,
    kind: str = "text",
    words: list[str] | None = None,
) -> StatusField:
    return StatusField(
        key=key, label=label, icon=icon, scope=scope, kind=kind, words=words, enabled=True
    )


def the_fields() -> list[StatusField]:
    return [
        field("time", "Day and time", "📅", "scene"),
        field("place", "Place", "📍", "scene"),
        field("outfit", "Outfit", "👗", "character"),
        field(
            "mood",
            "Mood",
            "🎭",
            "character",
            kind="words",
            words=["Guarded", "Teasing", "Rattled", "Calm"],
        ),
    ]


def values_of(readings: list[Reading]) -> list[tuple[str, str, str]]:
    return [(r.field_key, r.subject, r.value) for r in readings]


# --- reading ----------------------------------------------------------------------------------


def test_a_block_with_labels_and_icons_is_read_the_same_way() -> None:
    reply = """📅 Day and time: Day 1, 11:52 PM
📍: Eclipse VIP booth
📛 Name: Peach
👗 Outfit: black micro bikini, open robe
Mood: Guarded

*Peach laughs and leans back.*"""

    assert values_of(read(reply, the_fields())) == [
        ("time", "", "Day 1, 11:52 PM"),
        ("place", "", "Eclipse VIP booth"),
        ("outfit", "Peach", "black micro bikini, open robe"),
        ("mood", "Peach", "Guarded"),
    ]


def test_a_word_field_keeps_only_its_own_words() -> None:
    reply = "📛 Name: Peach\n🎭 Mood: guarded | Teasing | furious / Calm | Teasing\n*She smiles.*"

    assert values_of(read(reply, the_fields())) == [("mood", "Peach", "Guarded | Teasing | Calm")]
    assert read("📛 Name: Peach\n🎭 Mood: furious\n", the_fields()) == []


def test_each_character_has_a_block_and_prose_closes_it() -> None:
    reply = """📍 Place: the kitchen
📛 Name: Peach
👗 Outfit: a robe
*She pours coffee.*

📛 Name: Sammy Jones
👗 Outfit: a hoodie
*He yawns.*
👗 Outfit: this line follows prose, with nobody's name before it"""

    assert values_of(read(reply, the_fields(), default_subject="Peach Monroe")) == [
        ("place", "", "the kitchen"),
        ("outfit", "Peach", "a robe"),
        ("outfit", "Sammy Jones", "a hoodie"),
        ("outfit", "Peach Monroe", "this line follows prose, with nobody's name before it"),
    ]


def test_a_character_line_with_no_name_and_no_default_belongs_to_nobody() -> None:
    assert read("👗 Outfit: a robe\n", the_fields()) == []
    assert values_of(read("📍 Place: the bar\n", the_fields())) == [("place", "", "the bar")]


def test_the_models_decoration_is_not_part_of_the_value() -> None:
    reply = '**📍 Place:** *the bar*\n📛 Name: Peach [she/her]\n- 👗 Outfit: "a robe"\n'

    assert values_of(read(reply, the_fields())) == [
        ("place", "", "the bar"),
        ("outfit", "Peach", "a robe"),
    ]


def test_a_line_with_nothing_new_leaves_the_stored_value_alone() -> None:
    reply = "📍 Place: unchanged\n📅 Day and time: —\n📛 Name: Peach\n👗 Outfit: n/a\n"

    assert read(reply, the_fields()) == []


def test_prose_that_looks_like_a_label_is_not_a_field() -> None:
    reply = "She says: not tonight.\nWeather: rain on the glass.\nThe place: closed, it seems.\n"

    assert read(reply, the_fields()) == []


def test_a_sentence_after_name_is_not_a_name() -> None:
    reply = (
        "Name: this is a long sentence that is certainly not anybody's name at all\n👗 Outfit: x"
    )

    assert read(reply, the_fields(), default_subject="Peach") == [Reading("outfit", "Peach", "x")]


def test_a_field_that_is_off_is_not_read() -> None:
    fields = the_fields()
    fields[1].enabled = False

    assert values_of(
        read("📍 Place: the bar\n📅 Day and time: Day 2", [f for f in fields if f.enabled])
    ) == [("time", "", "Day 2")]


# --- storing and rewinding --------------------------------------------------------------------


async def a_story_with_fields(session: AsyncSession) -> Story:
    story = await a_played_story(session)
    await blocks.adopt(session, story.id, ["time", "place", "outfit", "mood"])
    await session.commit()
    return story


async def state(session: AsyncSession, story: Story) -> dict[tuple[str, str], str]:
    await session.commit()  # end the transaction, so a read sees what another session wrote
    rows = await session.scalars(select(StatusValue).where(StatusValue.story_id == story.id))
    return {(row.field_key, row.subject): row.value for row in rows}


async def test_a_turn_reads_the_block_into_the_state(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    model.says("📍 Place: the bar\n📛 Name: Peach\n👗 Outfit: a robe\n*She smiles.*")

    await send(client, story.id, "I come in.")

    assert await state(session, story) == {("place", ""): "the bar", ("outfit", "Peach"): "a robe"}


async def test_a_reply_without_a_block_changes_nothing_and_a_new_one_replaces_a_field(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    model.says("📍 Place: the bar\n📛 Name: Peach\n👗 Outfit: a robe\n*Hi.*")
    await send(client, story.id, "One.")
    model.says("*She pours a drink.*")
    await send(client, story.id, "Two.")
    model.says("📛 Name: peach\n👗 Outfit: nothing but heels\n*Hm.*")

    await send(client, story.id, "Three.")

    assert await state(session, story) == {
        ("place", ""): "the bar",
        ("outfit", "Peach"): "nothing but heels",  # one character, however the name is cased
    }


async def test_a_story_with_no_fields_reads_nothing(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_played_story(session)
    model.says("📍 Place: the bar\n*Hi.*")

    await send(client, story.id, "One.")

    assert await state(session, story) == {}


async def test_a_reroll_takes_the_rejected_replys_values_with_it(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    model.says("📍 Place: the bar\n📛 Name: Peach\n👗 Outfit: a robe\n*Hi.*")
    await send(client, story.id, "One.")
    model.says("📛 Name: Peach\n👗 Outfit: nothing at all\n*Hm.*")
    await send(client, story.id, "Two.")
    assert (await state(session, story))[("outfit", "Peach")] == "nothing at all"
    model.says("*A reply that leaves the outfit out.*")

    await stream(client, f"/stories/{story.id}/reroll")

    # The new reply wrote nothing, so the outfit is the one before the rejected reply.
    assert await state(session, story) == {("place", ""): "the bar", ("outfit", "Peach"): "a robe"}
    # And the model was told that outfit, not the rejected one's.
    assert "nothing at all" not in str(model.last["messages"])


async def test_a_cut_reads_the_state_again_from_what_remains(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    story_id = story.id
    model.says("📍 Place: the bar\n📛 Name: Peach\n👗 Outfit: a robe\n*Hi.*")
    await send(client, story_id, "One.")
    model.says("📍 Place: her flat\n📛 Name: Peach\n👗 Outfit: nothing\n*Hm.*")
    await send(client, story_id, "Two.")
    second_turn = (
        await session.scalars(
            select(Message).where(Message.story_id == story_id, Message.text == "Two.")
        )
    ).one()

    response = await client.delete(f"/stories/{story_id}/messages/{second_turn.id}")

    assert response.status_code == 200, response.text
    assert await state(session, story) == {("place", ""): "the bar", ("outfit", "Peach"): "a robe"}


async def test_a_value_set_by_hand_survives_a_replay_until_a_later_reply_writes_it(
    session: AsyncSession,
) -> None:
    story = await a_story_with_fields(session)
    session.add(
        StatusValue(
            story_id=story.id,
            field_key="outfit",
            subject="Peach",
            subject_key="peach",
            value="a trench coat",
            updated_at_sequence=1,
            by_hand=True,
        )
    )
    await session.commit()

    await blocks.replay(session, story)
    assert await state(session, story) == {("outfit", "Peach"): "a trench coat"}

    # A reply written after the hand-set value wins over it; one written before does not.
    blocks_later = [Reading("outfit", "Peach", "a robe")]
    stored = await blocks._stored(session, story.id)  # pyright: ignore[reportPrivateUsage]
    blocks._apply(session, story.id, stored, blocks_later, 1)  # pyright: ignore[reportPrivateUsage]
    assert stored[("outfit", "peach")].value == "a trench coat"
    blocks._apply(session, story.id, stored, blocks_later, 2)  # pyright: ignore[reportPrivateUsage]
    assert stored[("outfit", "peach")].value == "a robe"
    assert not stored[("outfit", "peach")].by_hand


async def test_a_branch_holds_the_state_as_it_stood_at_the_point(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    story_id = story.id
    model.says("📍 Place: the bar\n📛 Name: Peach\n👗 Outfit: a robe\n*Hi.*")
    await send(client, story_id, "One.")
    model.says("📍 Place: her flat\n📛 Name: Peach\n👗 Outfit: nothing\n*Hm.*")
    await send(client, story_id, "Two.")
    first_reply = (
        await session.scalars(
            select(Message).where(Message.story_id == story_id, Message.text.like("%the bar%"))
        )
    ).one()

    response = await client.post(
        f"/stories/{story_id}/branch", json={"message_id": str(first_reply.id)}
    )

    assert response.status_code == 201, response.text
    copy = response.json()["id"]
    rows = await session.scalars(select(StatusValue).where(StatusValue.story_id == copy))
    assert {(row.field_key, row.subject): row.value for row in rows} == {
        ("place", ""): "the bar",
        ("outfit", "Peach"): "a robe",
    }
    assert await state(session, story) == {
        ("place", ""): "her flat",
        ("outfit", "Peach"): "nothing",
    }
