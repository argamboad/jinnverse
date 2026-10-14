"""Extraction: the personas already in the library, turned into pieces, and proved by joining.

The persona here is invented; its shape is the one the owner's personas have.
"""

import httpx2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lustjinn.models import Persona, PersonaPiece, PieceSlot, Voice
from lustjinn.persona_extract import (
    plan_persona,
    plans_for_all,
    review,
    save,
    suggest_names,
    suggest_slot,
)

PARAGRAPHS = [
    "Dr. Owen Quill is a tall, quiet physician from Leeds with grey eyes and a soft accent.",
    "He dresses in plain wool and carries a leather satchel everywhere.",
    "His tattoos are small and private. A swallow rests on his wrist.",
    "Owen is the son of a miner and a teacher. His younger sister, Isla, runs a bakery.",
    "He runs the night clinic at the hospital and writes a column about sleep.",
    "He lives in a narrow flat above a bookshop. He rides a green bicycle.",
    "He is patient, curious and kind. He dislikes cruelty.",
    "His humor is dry and rarely heard.",
    "His passions include chess, tea and long walks.",
]
TEXT = "\n".join(PARAGRAPHS)
SLOTS = [
    PieceSlot.LOOK,
    PieceSlot.STYLE,
    PieceSlot.MARKS,
    PieceSlot.FAMILY,
    PieceSlot.WORK,
    PieceSlot.HOME,
    PieceSlot.PERSONALITY,
    PieceSlot.HUMOUR,
    PieceSlot.PASSIONS,
]


# --- the suggestions -----------------------------------------------------------------------------


def test_each_paragraph_is_given_the_slot_the_skeleton_gives_it() -> None:
    assert [suggest_slot(text, i) for i, text in enumerate(PARAGRAPHS)] == SLOTS


def test_a_tattoo_artist_in_the_family_paragraph_does_not_make_it_a_tattoo_paragraph() -> None:
    twin = "His twin sister, Macarena, is a gifted visual artist and tattoo artist."

    assert suggest_slot(twin, 4) is PieceSlot.FAMILY


def test_the_names_are_read_from_the_first_paragraph() -> None:
    assert suggest_names(PARAGRAPHS[0]) == ("Dr. Owen Quill", "Owen")
    assert suggest_names("Allan Ramos de Ávila is a lean young man.") == (
        "Allan Ramos de Ávila",
        "Allan",
    )
    assert suggest_names("Professor Allan McAllister is a philosopher.") == (
        "Professor Allan McAllister",
        "Allan",
    )
    assert suggest_names("A tall man stands at the door.") == (None, None)


def test_the_persona_s_name_becomes_the_placeholders() -> None:
    plan = plan_persona("owen", TEXT)

    pieces = plan.pieces()

    assert pieces[0] == (
        PieceSlot.LOOK,
        "{name} is a tall, quiet physician from Leeds with grey eyes and a soft accent.",
    )
    assert pieces[3][1] == (
        "{short} is the son of a miner and a teacher. His younger sister, Isla, runs a bakery."
    )


# --- the proof -----------------------------------------------------------------------------------


def test_a_plan_whose_pieces_give_back_the_text_exactly_rejoins() -> None:
    assert plan_persona("owen", TEXT).rejoins()


def test_a_trailing_newline_does_not_matter() -> None:
    assert plan_persona("owen", TEXT + "\n").rejoins()


def test_a_wrong_slot_that_changes_the_order_does_not_rejoin() -> None:
    plan = plan_persona("owen", TEXT)
    plan.paragraphs[4].slot = PieceSlot.PERSONALITY  # the work paragraph, after the home one

    assert not plan.rejoins()


def test_a_persona_with_blank_lines_between_paragraphs_does_not_rejoin() -> None:
    assert not plan_persona("owen", TEXT.replace("\n", "\n\n")).rejoins()


def test_a_literal_placeholder_in_a_persona_does_not_rejoin_silently() -> None:
    plan = plan_persona("owen", TEXT + "\nHe writes {name} on every parcel.")

    assert not plan.rejoins()


# --- the review ----------------------------------------------------------------------------------


def answers(*given: str) -> tuple[list[str], list[str], object]:
    """A scripted owner: the answers in order, and what was shown."""
    queue = list(given)
    shown: list[str] = []

    def ask(prompt: str) -> str:
        shown.append(prompt)
        return queue.pop(0)

    return queue, shown, ask


def test_enter_accepts_a_plan_that_rejoins() -> None:
    plan = plan_persona("owen", TEXT)
    shown: list[str] = []

    assert review(plan, lambda _: "", shown.append) is True
    assert any("rejoins exactly" in line for line in shown)


def test_a_slot_can_be_changed_and_enter_is_refused_until_the_plan_rejoins() -> None:
    plan = plan_persona("owen", TEXT)
    given = iter(["5=personality", "", "5=work", ""])
    shown: list[str] = []

    accepted = review(plan, lambda _: next(given), shown.append)

    assert accepted is True
    assert plan.paragraphs[4].slot is PieceSlot.WORK
    assert any("does not rejoin exactly; change a slot" in line for line in shown)


def test_several_changes_can_be_given_at_once() -> None:
    plan = plan_persona("owen", TEXT)
    plan.paragraphs[3].slot = PieceSlot.WORK
    plan.paragraphs[4].slot = PieceSlot.FAMILY
    given = iter(["4=family 5=work", ""])

    assert review(plan, lambda _: next(given), lambda _: None) is True
    assert plan.paragraphs[3].slot is PieceSlot.FAMILY
    assert plan.paragraphs[4].slot is PieceSlot.WORK


def test_a_persona_can_be_skipped() -> None:
    assert review(plan_persona("owen", TEXT), lambda _: "skip", lambda _: None) is False


def test_the_names_can_be_set_by_hand() -> None:
    plan = plan_persona("owen", "A tall man stands at the door.\nHe is patient and kind.")
    given = iter(["names=Owen Quill|Owen", "skip"])

    review(plan, lambda _: next(given), lambda _: None)

    assert (plan.full_name, plan.short_name) == ("Owen Quill", "Owen")


def test_a_bad_answer_is_explained_and_asked_again() -> None:
    plan = plan_persona("owen", TEXT)
    given = iter(["99=work", "3=nonsense", ""])
    shown: list[str] = []

    assert review(plan, lambda _: next(given), shown.append) is True
    assert sum("is not a paragraph number and a slot" in line for line in shown) == 2


# --- saving --------------------------------------------------------------------------------------


async def a_persona(session: AsyncSession, name: str, text: str) -> Persona:
    persona = Persona(name=name, text=text)
    session.add(persona)
    await session.commit()
    return persona


async def test_saving_makes_a_piece_of_each_paragraph_and_a_name_piece(
    session: AsyncSession,
) -> None:
    await a_persona(session, "owen", TEXT)

    report = await save(session, await plans_for_all(session))

    assert (report.personas, report.created, report.reused, report.skipped) == (1, 10, 0, [])
    pieces = list(await session.scalars(select(PersonaPiece)))
    assert {p.voice for p in pieces} == {Voice.HE}
    [name] = [p for p in pieces if p.slot is PieceSlot.NAME]
    assert (name.text, name.short, name.name) == ("Dr. Owen Quill", "Owen", "Dr. Owen Quill")
    assert len([p for p in pieces if p.slot is not PieceSlot.NAME]) == 9


async def test_a_paragraph_two_personas_share_becomes_one_piece(session: AsyncSession) -> None:
    roomie = "\n".join(p for p in PARAGRAPHS if "bookshop" not in p)
    await a_persona(session, "owen", TEXT)
    await a_persona(session, "owen-roomie", roomie)

    report = await save(session, await plans_for_all(session))

    assert report.personas == 2
    assert report.created == 10  # the roommate's eight paragraphs and its name already exist
    assert report.reused == 9
    homes = list(await session.scalars(select(PersonaPiece).where(PersonaPiece.slot == "home")))
    assert len(homes) == 1


async def test_running_it_again_adds_nothing(session: AsyncSession) -> None:
    await a_persona(session, "owen", TEXT)
    await save(session, await plans_for_all(session))

    again = await save(session, await plans_for_all(session))

    assert (again.created, again.reused) == (0, 10)
    assert len(list(await session.scalars(select(PersonaPiece)))) == 10


async def test_the_personas_are_never_touched(session: AsyncSession) -> None:
    owen = await a_persona(session, "owen", TEXT)

    await save(session, await plans_for_all(session))
    await session.refresh(owen)

    assert (owen.text, owen.version) == (TEXT, 1)


async def test_a_plan_that_does_not_rejoin_is_left_out_and_named(session: AsyncSession) -> None:
    await a_persona(session, "owen", TEXT)
    await a_persona(session, "odd", TEXT.replace("\n", "\n\n"))

    report = await save(session, await plans_for_all(session))

    assert report.skipped == ["odd"]
    assert report.personas == 1


async def test_two_paragraphs_of_one_slot_get_two_names(session: AsyncSession) -> None:
    twins = TEXT.replace(
        PARAGRAPHS[3], PARAGRAPHS[3] + "\nHis twin sister, Macarena, is a gifted visual artist."
    )
    await a_persona(session, "owen", twins)

    await save(session, await plans_for_all(session))

    families = list(
        await session.scalars(
            select(PersonaPiece.name).where(PersonaPiece.slot == "family").order_by("name")
        )
    )
    assert families == ["owen · Family", "owen · Family 2"]


async def test_the_pieces_build_back_the_persona_they_came_from_exactly(
    client: httpx2.AsyncClient, session: AsyncSession
) -> None:
    """The acceptance: pick a persona's pieces in its own order and the builder gives its text."""
    await a_persona(session, "owen", TEXT)
    [plan] = await plans_for_all(session)
    await save(session, [plan])
    pieces = list(await session.scalars(select(PersonaPiece)))
    by_content = {(p.slot, p.text): p for p in pieces}
    picks: dict[str, list[str]] = {}
    for slot, text in plan.pieces():
        picks.setdefault(slot.value, []).append(str(by_content[(slot, text)].id))
    [name] = [p for p in pieces if p.slot is PieceSlot.NAME]
    picks["name"] = [str(name.id)]

    built = await client.post(
        "/persona-pieces/build", json={"voice": "he", "pieces": picks, "name": "owen-again"}
    )

    assert built.status_code == 201, built.text
    assert built.json()["text"] == TEXT
