"""Status blocks in the prompt: the format to write and the state to keep (#172)."""

import httpx2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lustjinn import blocks
from lustjinn.blocks import FRAME, MOST_CHARACTERS, RECENT_TURNS, STANDS, render
from lustjinn.context import Layers, build
from lustjinn.models import Character, Message, Role, StatusField, StatusValue
from tests.scripted_model import ScriptedModel
from tests.streaming import send, stream
from tests.test_status_reading import a_story_with_fields, the_fields
from tests.test_turns import a_played_story


def value(field: str, subject: str, text: str, seen: int) -> StatusValue:
    return StatusValue(
        field_key=field,
        subject=subject,
        subject_key=subject.casefold(),
        value=text,
        updated_at_sequence=seen,
    )


# --- the layer --------------------------------------------------------------------------------


def test_no_field_on_means_no_layer() -> None:
    fields = the_fields()
    for field in fields:
        field.enabled = False

    assert render(fields, [], [], 10) is None
    assert render([], [], [], 10) is None


def test_the_format_lists_the_scene_lines_then_the_name_line_then_the_characters() -> None:
    fields = the_fields()
    for position, field in enumerate(fields):
        field.position = position
        field.hint = None

    layer = render(fields, [], [], 10)

    assert layer is not None
    assert layer.startswith(FRAME)
    assert (
        "\n📅 Day and time: <its value>\n"
        "📍 Place: <its value>\n"
        "📛 Name: <the character's name>\n"
        "👗 Outfit: <its value>\n"
        "🎭 Mood: <one or more of: Guarded, Teasing, Rattled, Calm>\n"
    ) in layer
    assert STANDS not in layer  # nothing is known yet


def test_a_field_that_is_off_is_neither_asked_for_nor_reported() -> None:
    fields = the_fields()
    fields[1].enabled = False  # place

    layer = render(fields, [value("place", "", "the bar", 9)], [], 10)

    assert layer is not None
    assert "Place" not in layer


def test_only_the_scene_and_the_characters_in_scene_are_reported() -> None:
    fields = the_fields()
    values = [
        value("place", "", "the bar", 30),
        value("outfit", "Peach", "a robe", 30),
        value("mood", "Peach", "Calm", 30),
        value("outfit", "Sammy", "a hoodie", 30 - RECENT_TURNS),  # just inside the window
        value("outfit", "Old Friend", "a suit", 30 - RECENT_TURNS - 1),  # just outside
    ]

    layer = render(fields, values, [], 30)

    assert layer is not None
    stands = layer.split(STANDS + "\n")[1]
    assert stands == (
        "Scene\n- Place: the bar\nPeach\n- Outfit: a robe\n- Mood: Calm\nSammy\n- Outfit: a hoodie"
    )


def test_a_pinned_character_is_sent_however_long_they_have_been_away() -> None:
    values = [
        value("outfit", "Peach", "a robe", 30),
        value("outfit", "Old Friend", "a suit", 2),
    ]

    layer = render(the_fields(), values, ["old friend"], 30)

    assert layer is not None
    assert layer.split(STANDS + "\n")[1] == "Old Friend\n- Outfit: a suit\nPeach\n- Outfit: a robe"


def test_no_more_than_the_most_characters_are_sent() -> None:
    values = [
        value("outfit", f"Person {n:02}", "a coat", 30 - n % 3) for n in range(MOST_CHARACTERS + 5)
    ]

    layer = render(the_fields(), values, [], 30)

    assert layer is not None
    assert layer.count("- Outfit: a coat") == MOST_CHARACTERS


def test_the_layer_sits_after_the_trackers_and_before_the_reminders_and_the_instruction() -> None:
    character = Character(name="Peach", card="Card.")
    history = [Message(sequence=1, role=Role.USER, text="Hi.")]

    built = build(
        Layers(
            character=character,
            history=history,
            trackers="[TRUST] ##........ 20/100",
            status="STATUS",
            reminders="Remind.",
            instruction="Now.",
        )
    )

    contents = [m.content for m in built.messages]
    assert contents[-4] == "[TRUST] ##........ 20/100"
    assert contents[-3] == "STATUS"
    assert contents[-2].endswith("Remind.")
    assert contents[-1] == "Now."
    assert "status" in built.spent


# --- in a turn --------------------------------------------------------------------------------


async def test_a_story_with_fields_is_sent_the_format_and_then_the_state(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    model.says("📍 Place: the bar\n📛 Name: Peach\n👗 Outfit: a robe\n*Hi.*")
    await send(client, story.id, "One.")

    model.says("*Hm.*")
    await send(client, story.id, "Two.")

    sent = model.last["messages"]
    assert sent[-2] == {"role": "user", "content": "Two."}
    assert sent[-1]["role"] == "system"
    assert sent[-1]["content"].startswith(FRAME)
    assert sent[-1]["content"].endswith(
        STANDS + "\nScene\n- Place: the bar\nPeach\n- Outfit: a robe"
    )


async def test_the_first_turn_is_asked_for_the_block_with_nothing_yet_to_report(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    model.says("*Hi.*")

    await send(client, story.id, "One.")

    last = model.last["messages"][-1]["content"]
    assert last.startswith(FRAME)
    assert STANDS not in last


async def test_a_story_without_fields_is_sent_no_layer(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_played_story(session)
    model.says("*Hi.*")

    await send(client, story.id, "One.")

    assert not any(FRAME in m["content"] for m in model.last["messages"])
    assert await blocks.layer(session, story) is None


async def test_the_audit_line_names_the_status_layer(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    model.says("*Hi.*")

    await send(client, story.id, "One.")

    reply = await session.scalar(
        select(Message)
        .where(Message.story_id == story.id, Message.role == Role.ASSISTANT)
        .order_by(Message.sequence.desc())
    )
    assert reply is not None
    assert reply.context_audit is not None
    assert " · status " in reply.context_audit


async def test_a_question_out_of_character_is_not_asked_for_a_block(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    model.says("She is wearing a robe.")

    await stream(client, f"/stories/{story.id}/send", text="/ask What is she wearing?")

    assert not any(FRAME in m["content"] for m in model.last["messages"])


async def test_a_field_switched_off_is_no_longer_asked_for(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_story_with_fields(session)
    for field in await blocks.fields_of(session, story.id):
        field.enabled = False
    await session.commit()
    model.says("*Hi.*")

    await send(client, story.id, "One.")

    assert not any(FRAME in m["content"] for m in model.last["messages"])


async def test_the_fields_a_test_uses_are_the_story_s_own(session: AsyncSession) -> None:
    story = await a_story_with_fields(session)

    fields = await blocks.fields_of(session, story.id)

    assert [f.key for f in fields] == ["time", "place", "outfit", "mood"]
    assert all(isinstance(f, StatusField) for f in fields)
