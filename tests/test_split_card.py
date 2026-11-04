"""The split of a card into a lorebook character (#274), on the dummy card: its cast becomes the
entries, a roster takes their place, and the rest of the card stays as it was."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jinnverse import tokens
from jinnverse.models import Character, LibraryHistory, LibraryKind, LoreEntry
from scripts.seed_dummy import Dummy, seed
from scripts.split_card import ROSTER_NOTE, Extras, Plan, heading_keys, name_keys, plan, write


def heron_plan(dummy: Dummy, extras: Extras | None = None) -> Plan:
    return plan(dummy.card, keep=[], extras=extras or Extras({}, set()))


def test_every_cast_sheet_becomes_an_entry_and_the_roster_takes_their_place(dummy: Dummy) -> None:
    made = heron_plan(dummy)

    assert [e.name for e in made.entries] == [
        "ISAURE VANTONGEREN",
        "TEODOR BLAKE",
        "MARGUERITE OYELARAN, called MAGS",
        "BROTHER ANSELM",
        "CAPTAIN YSOLDE MARRIN",
        "MINOR FIGURES",
    ]
    assert made.entries[0].text.startswith("ISAURE VANTONGEREN — proprietor of the Gilded Heron.")
    assert made.entries[0].text.endswith("She touches the steel comb when she is weighing a risk.")
    assert "=== THE CHARACTERS ===" in made.card
    assert ROSTER_NOTE in made.card
    assert (
        "ISAURE VANTONGEREN — proprietor of the Gilded Heron. Thirty-six. Tall, dark hair"
        in made.card
    )
    assert "She touches the steel comb" not in made.card  # the sheet's body left the card
    # Everything else is as it was.
    for section in ("=== THE WORLD ===", "=== WHO PLAYS WHOM ===", "=== HOW TO WRITE ==="):
        assert section in made.card
    assert "The Gilded Heron is a gaming house and inn" in made.card
    assert "The smugglers' stair is not bricked up." in made.card
    # The card lost the sheets' bodies and gained a note: what left it is in the entries.
    moved = sum(e.tokens() for e in made.entries)
    assert tokens.for_message(made.card) + moved == pytest.approx(
        tokens.for_message(dummy.card) + tokens.for_message(ROSTER_NOTE), abs=moved // 5
    )


def test_a_sheet_is_keyed_on_the_names_its_person_is_called() -> None:
    assert name_keys("ISAURE VANTONGEREN") == ["isaure vantongeren", "isaure", "vantongeren"]
    assert name_keys("MARGUERITE OYELARAN, called MAGS") == [
        "marguerite oyelaran",
        "mags",
        "marguerite",
        "oyelaran",
    ]
    assert name_keys('Samantha "Sammy" Jones') == ["samantha jones", "sammy", "samantha", "jones"]
    assert name_keys("Lieutenant Alexis Tromblay") == ["alexis tromblay", "alexis", "tromblay"]
    assert name_keys("Maria de la Cruz") == ["maria de la cruz", "maria", "cruz"]
    assert name_keys("Dr. Mei-Ling Wu") == ["mei-ling wu", "mei-ling", "wu"]


def test_a_world_sub_section_is_keyed_on_its_heading_and_what_its_lines_open_with() -> None:
    lines = [
        "",
        "Another Cup — a popular coffee chain with four locations on campus.",
        "The Brewery — the campus drinking hole: bar snacks, live music on the weekend.",
        "",
        "Aniston Hall is the coed five-storey dormitory for first-year students. Two",
        "elevators, though nobody uses them.",
    ]

    assert heading_keys("DINING", lines) == [
        "dining",
        "another cup",
        "the brewery",
        "brewery",
        "aniston hall",
    ]
    assert heading_keys("FROSH WEEK, DAY BY DAY", []) == ["frosh", "week", "frosh week, day by day"]
    assert heading_keys("THE ATHLETIC TIMETABLE", ["Men's volleyball — Monday to Friday."]) == [
        "athletic",
        "timetable",
        "athletic timetable",
        "men's volleyball",
    ]


def test_a_line_of_a_sheet_that_holds_a_dash_is_not_a_new_sheet() -> None:
    from scripts.split_card import sheet_header

    assert sheet_header("Lieutenant Alexis Tromblay — 29, BJU Police Department") == (
        "Lieutenant Alexis Tromblay"
    )
    assert sheet_header("MARGUERITE OYELARAN, called MAGS — dealer at the high table.") is not None
    assert sheet_header('Samantha "Sammy" Jones — 19, second-year Science') is not None
    assert sheet_header('Says: "I\'m Sabrina Kim. We had an appointment — she said."') is None
    assert sheet_header("When they escalate: she notices a body — and says so.") is None
    assert sheet_header("She likes being watched — on a stage, in a room.") is None
    assert sheet_header("Tells: reads a room the way she reads a listing — fast.") is None


def test_extras_add_keys_and_drop_the_words_prose_uses(dummy: Dummy) -> None:
    extras = Extras({"TEODOR BLAKE": ["the inspector", "Blake"]}, {"blake"})

    made = heron_plan(dummy, extras)

    assert made.entries[1].keys == ["teodor blake", "teodor", "the inspector"]


async def test_the_split_makes_a_second_character_with_its_entries_and_history(
    session: AsyncSession, dummy: Dummy
) -> None:
    heron, _ = await seed(session)
    made = heron_plan(dummy)

    lore = await write(session, heron, "The Gilded Heron · Lorebook", made, "A split.")

    assert lore.id != heron.id
    assert lore.opening == heron.opening
    assert lore.card == made.card
    original = await session.get_one(Character, heron.id)
    assert original.card == dummy.card  # untouched
    entries = list(
        await session.scalars(
            select(LoreEntry).where(LoreEntry.character_id == lore.id).order_by(LoreEntry.id)
        )
    )
    assert [e.name for e in entries] == [e.name for e in made.entries]
    assert entries[2].keys == ["marguerite oyelaran", "mags", "marguerite", "oyelaran"]
    kinds = list(
        await session.scalars(
            select(LibraryHistory.kind).where(
                LibraryHistory.entry_id.in_([lore.id, *(e.id for e in entries)])
            )
        )
    )
    assert kinds.count(LibraryKind.CHARACTER) == 1
    assert kinds.count(LibraryKind.LORE) == len(entries)
