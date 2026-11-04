"""A character's lore from the library (#269): the entries with their keys, creating one in three
questions, editing the text and the keys, renaming, removing, and a save over an edit made
elsewhere."""

from collections.abc import Callable
from typing import Any

from textual.pilot import Pilot

from jinnverse_tui.api import LoreEntry
from jinnverse_tui.app import JinnverseApp
from jinnverse_tui.confirm import ConfirmScreen
from jinnverse_tui.conflict import ConflictScreen
from jinnverse_tui.library import LibraryScreen
from jinnverse_tui.lore import LoreScreen, keys_note, parse_keys
from jinnverse_tui.status import Kind
from jinnverse_tui.stories import StoriesScreen
from tui_support import fake_server as fake
from tui_support.waits import settle

CARD = "You are the narrator of the Gilded Heron.\n\n=== THE WORLD ===\n\nA gaming house."
ISAURE = "ISAURE VANTONGEREN — proprietor of the Gilded Heron. Thirty-six."
BLAKE = "TEODOR BLAKE — harbour inspector for the Port Authority. Forty-one."


def heron_with_lore(server: fake.FakeServer) -> dict[str, Any]:
    heron = server.shelve("characters", "The Gilded Heron", CARD)
    server.shelve_lore(heron["id"], "Isaure Vantongeren", ["isaure", "proprietor"], ISAURE)
    server.shelve_lore(heron["id"], "Teodor Blake", ["blake", "inspector"], BLAKE)
    return heron


def lore(app: JinnverseApp) -> LoreScreen:
    screen = app.screen
    assert isinstance(screen, LoreScreen)
    return screen


def names(app: JinnverseApp) -> list[str]:
    return [e.name for e in lore(app).rows.items]


def prose(app: JinnverseApp) -> str:
    return str(lore(app).query_one("#prose").render())


async def open_lore(app: JinnverseApp, pilot: Pilot[None]) -> LoreScreen:
    await settle(pilot)
    assert isinstance(app.screen, StoriesScreen)
    await pilot.press("m")
    await settle(pilot)
    await pilot.press("l")
    await settle(pilot)
    return lore(app)


def scripted_editor(replies: list[str | None]) -> Callable[..., str | None]:
    handed: list[str] = []

    def edit(app: JinnverseApp, text: str, suffix: str) -> str | None:
        handed.append(text)
        return replies.pop(0) if replies else None

    edit.handed = handed  # type: ignore[attr-defined]
    return edit


def test_the_keys_are_read_from_one_line_as_the_api_keeps_them() -> None:
    assert parse_keys(" Jax, BARTENDER, the  Brewery ,, jax") == ["jax", "bartender", "the brewery"]
    assert parse_keys("   ") == []
    assert keys_note(["jax", "the brewery"]) == "jax · the brewery"
    assert keys_note([]) == "no keys — never sent"


async def test_l_opens_a_characters_lore_with_the_keys_under_each_name(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    heron_with_lore(server)
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("m")
        await settle(pilot)
        library = app.screen
        assert isinstance(library, LibraryScreen)
        assert "2 lore entries" in str(library.query_one("#caption").render())
        await pilot.press("l")
        await settle(pilot)
        screen = lore(app)
        assert names(app) == ["Isaure Vantongeren", "Teodor Blake"]
        assert screen.summary() == "The Gilded Heron · 2 entries"
        assert screen.status_line.text == (
            "2 entries of 'The Gilded Heron', in the order they were made."
        )
        assert "isaure · proprietor" in screen.rows.render().plain
        assert prose(app).startswith("ISAURE VANTONGEREN")
        assert "keys: isaure, proprietor" in str(screen.query_one("#keys").render())
        await pilot.press("down")
        await settle(pilot)
        assert prose(app).startswith("TEODOR BLAKE")
        await pilot.press("escape")
        await settle(pilot)
        assert isinstance(app.screen, LibraryScreen)


async def test_only_a_character_has_lore(app: JinnverseApp, server: fake.FakeServer) -> None:
    server.shelve("personas", "Me", "A tall man.")
    async with app.run_test(size=(100, 30)) as pilot:
        await settle(pilot)
        await pilot.press("m")
        await settle(pilot)
        await pilot.press("right")
        await settle(pilot)
        await pilot.press("l")
        await settle(pilot)
        screen = app.screen
        assert isinstance(screen, LibraryScreen)
        assert screen.status_line.text == "Only a character has lore; a persona is sent whole."
        assert screen.status_line.kind is Kind.WARNING


async def test_n_asks_the_name_then_the_keys_and_opens_the_editor_on_the_skeleton(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    heron = server.shelve("characters", "The Gilded Heron", CARD)
    editor = scripted_editor(["PELL — the night porter, with a bad knee.\n"])
    app.editor = editor
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_lore(app, pilot)
        assert "N starts an entry" in screen.rows.render().plain
        await pilot.press("n")
        await pilot.pause()
        assert screen.legend.text.startswith(" Enter Go on")
        await pilot.press(*"Pell", "enter")
        await pilot.pause()
        assert "keys" in screen.query_one("#field").placeholder  # type: ignore[attr-defined]
        await pilot.press(*"Pell, porter", "enter")
        await settle(pilot)
        assert names(app) == ["Pell"]
        assert editor.handed[0].startswith("[ A piece of the card")  # type: ignore[attr-defined]
        [pell] = server.lore[heron["id"]]
        assert (pell["keys"], pell["text"], pell["version"]) == (
            ["pell", "porter"],
            "PELL — the night porter, with a bad knee.\n",
            2,
        )
        assert screen.status_line.text.startswith("Saved. 'Pell' is sent from the next turn")
        assert prose(app).startswith("PELL")


async def test_an_entry_needs_at_least_one_key(app: JinnverseApp, server: fake.FakeServer) -> None:
    heron = server.shelve("characters", "The Gilded Heron", CARD)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_lore(app, pilot)
        await pilot.press("n", *"Pell", "enter", "enter")
        await settle(pilot)
        assert server.lore.get(heron["id"], []) == []
        assert screen.status_line.text.startswith("An entry needs at least one key")


async def test_enter_edits_the_text_k_the_keys_and_f2_the_name(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    heron = heron_with_lore(server)
    app.editor = scripted_editor([ISAURE + " She touches the comb.\n"])
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_lore(app, pilot)
        await pilot.press("enter")
        await settle(pilot)
        isaure = server.lore[heron["id"]][0]
        assert isaure["text"].endswith("She touches the comb.\n")
        assert isaure["version"] == 2
        await pilot.press("k")
        await pilot.pause()
        field = screen.query_one("#field")
        assert field.value == "isaure, proprietor"  # type: ignore[attr-defined]
        await pilot.press("end", *", Innkeeper", "enter")
        await settle(pilot)
        assert isaure["keys"] == ["isaure", "proprietor", "innkeeper"]
        assert screen.status_line.text == "Keys saved: isaure, proprietor, innkeeper."
        await pilot.press("f2")
        await pilot.pause()
        await pilot.press("ctrl+u", *"Isaure", "enter")
        await settle(pilot)
        assert isaure["name"] == "Isaure"
        assert names(app) == ["Isaure", "Teodor Blake"]
        assert isaure["version"] == 4


async def test_an_unchanged_text_saves_nothing(app: JinnverseApp, server: fake.FakeServer) -> None:
    heron = heron_with_lore(server)
    app.editor = scripted_editor([ISAURE + "\n"])
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_lore(app, pilot)
        await pilot.press("enter")
        await settle(pilot)
        assert server.lore[heron["id"]][0]["version"] == 1
        assert screen.status_line.text == "Nothing changed."


async def test_a_save_over_an_edit_made_elsewhere_shows_theirs_and_asks(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    heron = heron_with_lore(server)
    isaure = server.lore[heron["id"]][0]
    app.editor = scripted_editor(["Mine.\n"])
    async with app.run_test(size=(100, 30)) as pilot:
        await open_lore(app, pilot)
        isaure["text"] = "Theirs, from the phone."
        isaure["version"] = 2
        await pilot.press("enter")
        await settle(pilot)
        conflict = app.screen
        assert isinstance(conflict, ConflictScreen)
        theirs = conflict.theirs
        assert isinstance(theirs, LoreEntry)
        assert theirs.text == "Theirs, from the phone."
        await pilot.press("enter")
        await settle(pilot)
        screen = lore(app)
        assert (isaure["text"], isaure["version"]) == ("Mine.\n", 3)
        assert screen.status_line.text == "Saved over version 2."


async def test_del_asks_and_removes(app: JinnverseApp, server: fake.FakeServer) -> None:
    heron = heron_with_lore(server)
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_lore(app, pilot)
        await pilot.press("down", "delete")
        await settle(pilot)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("enter")
        await settle(pilot)
        assert names(app) == ["Isaure Vantongeren"]
        assert [e["name"] for e in server.lore[heron["id"]]] == ["Isaure Vantongeren"]
        assert screen.status_line.text == "Removed 'Teodor Blake'."
