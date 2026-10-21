"""The library's Pieces shelf: the pool listed by slot, a piece read whole and edited, its voice,
its short form, a new piece, removing one, a save over a change made elsewhere, and the builder's
way in (#165)."""

from collections.abc import Callable
from typing import Any

from textual.pilot import Pilot

from jinnverse_tui.app import JinnverseApp
from jinnverse_tui.builder import PersonaBuilderScreen
from jinnverse_tui.confirm import ConfirmScreen
from jinnverse_tui.library import ConflictScreen, LibraryScreen
from jinnverse_tui.stories import StoriesScreen
from tui_support import fake_server as fake


def pool(server: fake.FakeServer) -> dict[str, dict[str, Any]]:
    return {
        "name": server.piece("name", "Allan", "Allan Sanlúcar", short="Allan"),
        "look": server.piece(
            "look", "Athletic", "{name} is an athletic young man.", description="The default look"
        ),
        "home": server.piece("home", "Penthouse", "{short} lives in a penthouse."),
        "loft": server.piece("home", "Loft", "{short} lives in a loft.", voice="she"),
        "pet": server.piece("pets", "Lupo", "He has a corgi named Lupo."),
    }


def library(app: JinnverseApp) -> LibraryScreen:
    screen = app.screen
    assert isinstance(screen, LibraryScreen)
    return screen


def names(app: JinnverseApp) -> list[str]:
    return [e.name for e in library(app).rows.items]


def prose(app: JinnverseApp) -> str:
    return str(library(app).query_one("#prose").render())


def caption(app: JinnverseApp) -> str:
    return str(library(app).query_one("#caption").render())


def scripted_editor(replies: list[str | None]) -> Callable[..., str | None]:
    handed: list[str] = []

    def edit(app: JinnverseApp, text: str, suffix: str) -> str | None:
        handed.append(text)
        return replies.pop(0) if replies else None

    edit.handed = handed  # type: ignore[attr-defined]
    return edit


async def open_pieces(app: JinnverseApp, pilot: Pilot[None]) -> LibraryScreen:
    await pilot.pause(0.1)
    assert isinstance(app.screen, StoriesScreen)
    await pilot.press("m")
    await pilot.pause(0.3)
    await pilot.press("right", "right", "right")
    await pilot.pause(0.4)
    assert library(app).shelf == "pieces"
    return library(app)


async def test_the_fourth_shelf_lists_the_pool_by_slot_with_its_count(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await open_pieces(app, pilot)
        assert " Pieces 5 " in str(screen.query_one("#tabs").render())
        assert names(app) == [
            "Name · Allan (he)",
            "Look, style and marks · Athletic (he)",
            "Home · Loft (she)",
            "Home · Penthouse (he)",
            "Pets · Lupo (he)",
        ]
        assert screen.summary() == "5 pieces"
        assert screen.legend.text.startswith(" ←→ Shelf")
        assert "V Voice" in screen.legend.text


async def test_a_row_shows_the_description_when_the_piece_has_one(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(200, 30)) as pilot:
        screen = await open_pieces(app, pilot)
        assert "Athletic (he)  The default look" in screen.rows.render().plain


async def test_the_selected_piece_is_read_whole_with_its_slot_voice_and_version(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await open_pieces(app, pilot)
        assert "Allan   ·   Name   ·   he voice   ·   version 1" in caption(app)
        assert "Allan Sanlúcar" in prose(app)
        assert "(short form: Allan)" in prose(app)
        await pilot.press("down")
        await pilot.pause(0.2)
        assert "{name} is an athletic young man." in prose(app)
        assert str(screen.query_one("#description").render()) == "The default look"


async def test_enter_edits_the_text_and_says_what_it_does_not_reach(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    ids = pool(server)
    editor = scripted_editor(["{short} lives in a lighthouse.\n"])
    app.editor = editor
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await open_pieces(app, pilot)
        await pilot.press("down", "down", "down", "enter")
        await pilot.pause(0.4)
        assert editor.handed[0] == "{short} lives in a penthouse."  # type: ignore[attr-defined]
        assert ids["home"]["text"] == "{short} lives in a lighthouse.\n"
        assert ids["home"]["version"] == 2
        assert screen.status_line.text.startswith("Saved. Personas already built from it")


async def test_f2_renames_the_piece_by_its_own_name_not_the_one_the_row_shows(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    ids = pool(server)
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await open_pieces(app, pilot)
        await pilot.press("down", "down", "down", "f2")
        await pilot.pause()
        assert screen.query_one("#name").value == "Penthouse"  # type: ignore[attr-defined]
        await pilot.press("ctrl+u", *"Skyline", "enter")
        await pilot.pause(0.4)
        assert ids["home"]["name"] == "Skyline"
        assert screen.status_line.text == 'Renamed to "Skyline".'
        assert "Home · Skyline (he)" in names(app)


async def test_e_describes_a_piece(app: JinnverseApp, server: fake.FakeServer) -> None:
    ids = pool(server)
    async with app.run_test(size=(110, 30)) as pilot:
        await open_pieces(app, pilot)
        await pilot.press("down", "down", "down", "e", *"Across from the university", "enter")
        await pilot.pause(0.4)
        assert ids["home"]["description"] == "Across from the university"
        assert ids["home"]["version"] == 2


async def test_v_cycles_the_voice_and_a_taken_name_in_that_voice_is_refused(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    ids = pool(server)
    server.piece("home", "Penthouse", "She lives in a penthouse.", voice="she")
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await open_pieces(app, pilot)
        await pilot.press("down", "down", "down")  # the he Penthouse (her own comes after it)
        await pilot.pause(0.2)
        assert "Penthouse   ·   Home   ·   he voice" in caption(app)
        await pilot.press("v")
        await pilot.pause(0.4)
        # she already has a Penthouse: the server refuses, and nothing changed.
        assert ids["home"]["voice"] == "he"
        assert "already exists" in screen.status_line.text


async def test_v_changes_the_voice_to_the_next_one(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    ids = pool(server)
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await open_pieces(app, pilot)
        await pilot.press("down", "down", "down", "v")
        await pilot.pause(0.4)
        assert ids["home"]["voice"] == "she"
        assert screen.status_line.text == "Now written in the she voice."


async def test_s_gives_a_name_piece_its_short_form_and_refuses_any_other(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    ids = pool(server)
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await open_pieces(app, pilot)
        await pilot.press("s")
        await pilot.pause()
        assert screen.legend.text.startswith(" Enter Save the short name")
        await pilot.press("ctrl+u", *"Al", "enter")
        await pilot.pause(0.4)
        assert ids["name"]["short"] == "Al"
        assert "(short form: Al)" in prose(app)
        await pilot.press("down", "s")
        await pilot.pause(0.2)
        assert screen.status_line.text == "Only a name piece has a short form."


async def test_n_asks_for_a_slot_and_a_name_then_the_editor_and_keeps_the_piece(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    pool(server)
    editor = scripted_editor(["He has a scooter.\n"])
    app.editor = editor
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await open_pieces(app, pilot)
        await pilot.press("n")
        await pilot.pause()
        assert "slot" in screen.query_one("#name").placeholder  # type: ignore[attr-defined]
        await pilot.press(*"vehicle Scooter", "enter")
        await pilot.pause(0.3)
        await pilot.press(*"Red, a little dented", "enter")  # its description (#220)
        await pilot.pause(0.5)
        made = next(p for p in server.pieces if p["name"] == "Scooter")
        assert (made["slot"], made["voice"], made["text"]) == ("vehicle", "he", "He has a scooter.")
        assert made["description"] == "Red, a little dented"
        assert "vehicle paragraph" in editor.handed[0]  # type: ignore[attr-defined]
        assert "Vehicle · Scooter (he)" in names(app)


async def test_n_takes_a_voice_after_the_slot(app: JinnverseApp, server: fake.FakeServer) -> None:
    pool(server)
    app.editor = scripted_editor(["{name} is tall.\n"])
    async with app.run_test(size=(110, 30)) as pilot:
        await open_pieces(app, pilot)
        await pilot.press("n", *"look she Her look", "enter")
        await pilot.pause(0.3)
        await pilot.press("enter")  # no description
        await pilot.pause(0.5)
        made = next(p for p in server.pieces if p["name"] == "Her look")
        assert (made["slot"], made["voice"], made["description"]) == ("look", "she", None)


async def test_a_new_name_piece_is_its_name_and_offers_its_first_word_as_the_short_form(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await open_pieces(app, pilot)
        await pilot.press("n", *"name Owen Quill", "enter")
        await pilot.pause(0.3)
        assert screen.query_one("#name").value == "Owen"  # type: ignore[attr-defined]
        await pilot.press("enter", "enter")  # the offered short form, no description
        await pilot.pause(0.5)
        [made] = server.pieces
        assert (made["slot"], made["text"], made["short"]) == ("name", "Owen Quill", "Owen")


async def test_a_new_name_piece_takes_its_own_short_form_and_a_description(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    async with app.run_test(size=(110, 30)) as pilot:
        await open_pieces(app, pilot)
        await pilot.press("n", *"name Owen Quill", "enter")
        await pilot.pause(0.3)
        await pilot.press(*"Quill", "enter")  # typing replaces the offered word
        await pilot.pause(0.3)
        await pilot.press(*"The pianist's name", "enter")
        await pilot.pause(0.5)
        [made] = server.pieces
        assert (made["short"], made["description"]) == ("Quill", "The pianist's name")


async def test_esc_while_asking_creates_nothing(app: JinnverseApp, server: fake.FakeServer) -> None:
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await open_pieces(app, pilot)
        await pilot.press("n", *"name Owen Quill", "enter")
        await pilot.pause(0.3)
        await pilot.press("escape")
        await pilot.pause()
        assert screen.status_line.text == "Cancelled."
        assert server.pieces == []


async def test_a_slot_that_does_not_exist_is_refused_with_the_list(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    async with app.run_test(size=(110, 30)) as pilot:
        screen = await open_pieces(app, pilot)
        await pilot.press("n", *"garage Big", "enter")
        await pilot.pause(0.3)
        assert screen.status_line.text.startswith("Start with a slot: name, look, family")
        assert server.pieces == []


async def test_delete_asks_first_and_says_personas_keep_their_copy(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    pool(server)
    async with app.run_test(size=(110, 30)) as pilot:
        await open_pieces(app, pilot)
        await pilot.press("delete")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("enter")
        await pilot.pause(0.4)
        assert len(server.pieces) == 4
        assert "Name · Allan (he)" not in names(app)


async def test_a_save_over_a_change_made_elsewhere_shows_the_pieces_as_the_server_has_it(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    ids = pool(server)
    app.editor = scripted_editor(["Mine.\n"])
    async with app.run_test(size=(110, 30)) as pilot:
        await open_pieces(app, pilot)
        await pilot.press("down", "down", "down")
        ids["home"]["version"] = 5  # edited on the phone since the list was read
        ids["home"]["text"] = "Theirs."
        await pilot.press("enter")
        await pilot.pause(0.5)
        assert isinstance(app.screen, ConflictScreen)
        assert app.screen.theirs.text == "Theirs."


async def test_e_in_the_builder_opens_the_piece_in_the_library_and_esc_comes_back(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    ids = pool(server)
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("m")
        await pilot.pause(0.3)
        await pilot.press("b")
        await pilot.pause(0.4)
        assert isinstance(app.screen, PersonaBuilderScreen)
        await pilot.press("down", "down", "down", "down")  # the home row
        await pilot.press("right", "e")
        await pilot.pause(0.5)
        assert isinstance(app.screen, LibraryScreen)
        assert app.screen.shelf == "pieces"
        selected = app.screen.selected
        assert selected is not None
        assert selected.name == "Home · Penthouse (he)"
        ids["home"]["name"] = "Skyline"  # renamed meanwhile
        await pilot.press("escape")
        await pilot.pause(0.5)
        assert isinstance(app.screen, PersonaBuilderScreen)
        # The shared row lists home, then vehicle, then pets (#218).
        assert [p.name for p in app.screen.piece_rows.items] == ["Skyline", "Lupo"]
