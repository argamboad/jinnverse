"""The matcher and the lore layer (#267): which of a character's entries a turn gets, and where
they go. On the Gilded Heron's cast as entries of realistic size, never a few inline words."""

import httpx2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jinnverse import tokens
from jinnverse.context import LORE_FRAME, Layers, Lore, build, lore_layer
from jinnverse.lore import LOOKBACK, matched
from jinnverse.models import Character, LoreEntry, Message, Role, StatusField, StatusValue
from scripts.seed_dummy import Dummy
from tests.factories import a_lore_entry, a_message
from tests.scripted_model import ScriptedModel
from tests.streaming import send
from tests.test_context import heron
from tests.test_turns import a_played_story


def entries(dummy: Dummy) -> list[LoreEntry]:
    """The Heron's cast as entries, not yet in any database."""
    return [LoreEntry(name=e.name, keys=list(e.keys), text=e.text) for e in dummy.lore]


def texts(found: list[Lore], dummy: Dummy) -> list[str]:
    """The names of the entries found, in the order found."""
    return [dummy.lore[hit.position].name for hit in found]


# -- the matcher ---------------------------------------------------------------------------------


def test_an_entry_fires_when_one_of_its_keys_is_in_the_scene(dummy: Dummy) -> None:
    found = matched(entries(dummy), ["I ask the proprietor for a room.", "*Mags deals.*"])

    assert texts(found, dummy) == ["Marguerite Oyelaran, called Mags", "Isaure Vantongeren"]


def test_the_freshest_mention_comes_first_and_ties_follow_the_card(dummy: Dummy) -> None:
    found = matched(
        entries(dummy),
        ["Blake looks at the door.", "Anselm and Isaure are at breakfast.", "Pell takes my coat."],
    )

    assert texts(found, dummy) == [
        "Minor figures",
        "Isaure Vantongeren",
        "Brother Anselm",
        "Teodor Blake",
    ]
    assert [hit.freshness for hit in found] == [2, 1, 1, 0]


def test_a_key_matches_whole_words_in_any_case_and_through_a_possessive(dummy: Dummy) -> None:
    cast = entries(dummy)

    assert texts(matched(cast, ["BLAKE's coat."]), dummy) == ["Teodor Blake"]
    assert texts(matched(cast, ["Blakely Street."]), dummy) == []
    assert texts(matched(cast, ["the brother anselm of legend"]), dummy) == ["Brother Anselm"]
    assert texts(matched(cast, ["She watches the harbour."]), dummy) == []


def test_only_the_scene_in_progress_is_looked_in(dummy: Dummy) -> None:
    """Six turns, the same six the summariser never compresses: a character stays through a
    short exchange about something else, and goes once the scene has moved on."""
    older = ["Isaure sets down the cup."]
    filler = ["Rain.", "Dice overhead.", "The fire.", "A pot goes down.", "Fog.", "The tide bell."]

    assert texts(matched(entries(dummy), older + filler[: LOOKBACK - 1]), dummy) == [
        "Isaure Vantongeren"
    ]
    assert texts(matched(entries(dummy), older + filler[:LOOKBACK]), dummy) == []


def test_the_status_block_calls_for_an_entry_and_counts_as_the_newest_mention(
    dummy: Dummy,
) -> None:
    found = matched(
        entries(dummy), ["Mags shuffles."], status_lines=["The card room", "Captain Marrin"]
    )

    assert texts(found, dummy) == ["Captain Ysolde Marrin", "Marguerite Oyelaran, called Mags"]
    assert found[0].freshness == 1 == len(["Mags shuffles."])


def test_an_entry_never_brings_in_another(dummy: Dummy) -> None:
    """Isaure's sheet names Derrow & Sons; the minor figures' entry is keyed on `derrow`. Only
    the scene is looked in, so her entry alone does not pull theirs."""
    found = matched(entries(dummy), ["Isaure touches the comb."])

    assert texts(found, dummy) == ["Isaure Vantongeren"]


def test_an_entry_with_no_keys_never_fires(dummy: Dummy) -> None:
    silent = LoreEntry(name="Silent", keys=[], text="Never sent.")

    assert matched([silent], ["Silent. Never sent."]) == []


# -- the layer -----------------------------------------------------------------------------------


def test_the_layer_is_the_texts_whole_in_the_order_of_the_card(dummy: Dummy) -> None:
    found = matched(entries(dummy), ["Pell nods to Isaure."])  # the porter is fresher
    built = build(Layers(character=heron(dummy), lore=found))

    layer = built.messages[-1].content
    assert layer == LORE_FRAME + dummy.lore[0].text.strip() + "\n\n" + dummy.lore[5].text.strip()
    assert built.spent["lore"].tokens == tokens.for_message(layer)
    assert built.spent["lore"].dropped == 0


def test_the_lore_is_capped_at_its_share_of_the_budget_freshest_first(dummy: Dummy) -> None:
    """Every sheet called for in one turn: under a cap that holds about two of them, the two
    freshest are kept and sent in the order of the card, and the audit says what was left out."""
    cast = entries(dummy)
    found = matched(cast, ["Blake, Mags, Anselm and the captain are all here.", "Isaure looks up."])
    assert len(found) == 5
    two = tokens.for_message(lore_layer(found[:2]) or "") + 10
    budget = two * 100 // 20  # a 20% share that holds exactly two

    built = build(Layers(character=heron(dummy), lore=found), budget=budget, lore_percent=20)

    layer = built.messages[-1].content
    assert layer.startswith(LORE_FRAME + dummy.lore[0].text.strip())  # Isaure: freshest
    assert dummy.lore[1].text.strip() in layer  # Blake: the first named in the older turn
    assert dummy.lore[2].text.strip() not in layer
    assert built.spent["lore"].dropped == 3
    assert layer.index(dummy.lore[0].text.strip()) < layer.index(dummy.lore[1].text.strip())


def test_no_lore_is_no_layer(dummy: Dummy) -> None:
    built = build(Layers(character=heron(dummy), lore=[]))

    assert "lore" not in built.spent
    assert not any(LORE_FRAME in m.content for m in built.messages)


# -- a turn ----------------------------------------------------------------------------------------


async def test_a_turn_sends_the_entries_its_scene_calls_for_and_audits_them(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel, dummy: Dummy
) -> None:
    story = await a_played_story(session)
    character = await session.get_one(Character, story.character_id)
    for entry in dummy.lore:
        await a_lore_entry(session, character, entry.name, entry.keys, entry.text)
    await session.commit()
    model.says("*Blake sets down his spoon.*")

    await send(client, story.id, "I nod to the inspector in the corner.")

    sent = [(m["role"], m["content"]) for m in model.last["messages"]]
    lore = [content for _, content in sent if content.startswith(LORE_FRAME)]
    assert len(lore) == 1
    assert dummy.lore[1].text.strip() in lore[0]  # Blake, the inspector
    assert dummy.lore[0].text.strip() in lore[0]  # Isaure, named in the opening still in scene
    assert dummy.lore[4].text.strip() not in lore[0]  # the captain is at berth six
    transcript = [m for m in sent if m[0] in ("user", "assistant")]
    # After the transcript, before the reader's newest turn, which closes the prompt (#280).
    assert sent.index(transcript[-2]) < sent.index(("system", lore[0])) < sent.index(transcript[-1])
    reply = await session.scalar(
        select(Message)
        .where(Message.story_id == story.id, Message.role == Role.ASSISTANT)
        .order_by(Message.sequence.desc())
    )
    assert reply is not None
    assert reply.context_audit is not None
    assert f"lore {tokens.for_message(lore[0])}" in reply.context_audit


async def test_the_status_block_keeps_a_places_entry_in_while_the_scene_is_there(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel, dummy: Dummy
) -> None:
    story = await a_played_story(session)
    character = await session.get_one(Character, story.character_id)
    await a_lore_entry(
        session,
        character,
        "The card rooms",
        ("card room", "card rooms", "baize"),
        "THE CARD ROOMS — green baize tables, lamps trimmed low, the high table at the back.",
    )
    session.add(StatusField(story_id=story.id, key="place", label="Place", hint="where"))
    session.add(StatusValue(story_id=story.id, field_key="place", value="The card rooms, upstairs"))
    for n in range(LOOKBACK):
        await a_message(session, story, f"Nothing about the room, {n}.", Role.USER)
    await session.commit()
    model.says("*The dice stop.*")

    await send(client, story.id, "I wait.")

    lore = [m["content"] for m in model.last["messages"] if m["content"].startswith(LORE_FRAME)]
    assert len(lore) == 1
    assert "THE CARD ROOMS" in lore[0]


async def test_a_character_without_entries_sends_what_it_always_sent(
    client: httpx2.AsyncClient, session: AsyncSession, model: ScriptedModel
) -> None:
    story = await a_played_story(session)
    model.says("Hm.")

    await send(client, story.id, "I come in.")

    reply = await session.scalar(
        select(Message)
        .where(Message.story_id == story.id, Message.role == Role.ASSISTANT)
        .order_by(Message.sequence.desc())
    )
    assert reply is not None
    assert reply.context_audit is not None
    assert "lore" not in reply.context_audit
    assert not any(LORE_FRAME in m["content"] for m in model.last["messages"])
