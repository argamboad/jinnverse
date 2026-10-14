"""The library screen's counts on the shelf tabs and the short description of an entry: in the
tabs, beside the names, over the text, edited on one line, and on the new-story form (#162)."""

from textual.pilot import Pilot

from lustjinn_tui.app import LustjinnApp
from lustjinn_tui.library import LibraryScreen
from lustjinn_tui.newstory import NewStoryScreen, Panel
from lustjinn_tui.stories import StoriesScreen
from tui_support import fake_server as fake


def library(app: LustjinnApp) -> LibraryScreen:
    screen = app.screen
    assert isinstance(screen, LibraryScreen)
    return screen


async def open_library(app: LustjinnApp, pilot: Pilot[None]) -> LibraryScreen:
    await pilot.pause(0.1)
    assert isinstance(app.screen, StoriesScreen)
    await pilot.press("m")
    await pilot.pause(0.3)
    return library(app)


def tabs(app: LustjinnApp) -> str:
    return str(library(app).query_one("#tabs").render())


def description(app: LustjinnApp) -> str:
    return str(library(app).query_one("#description").render())


async def test_the_tabs_say_how_many_entries_each_shelf_holds(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    server.shelve("characters", "Elena", "You are Elena.")
    server.shelve("characters", "Marta", "You are Marta.")
    server.shelve("personas", "Me", "A tall man.")
    async with app.run_test(size=(100, 30)) as pilot:
        await open_library(app, pilot)
        assert " Characters 2 " in tabs(app)
        assert " Personas 1 " in tabs(app)
        assert " Snippets 0 " in tabs(app)


async def test_a_name_starting_with_an_underscore_is_not_counted(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    server.shelve("characters", "Elena", "You are Elena.")
    server.shelve("characters", "_template", "A template.")
    async with app.run_test(size=(100, 30)) as pilot:
        await open_library(app, pilot)
        assert " Characters 1 " in tabs(app)


async def test_a_refresh_counts_again(app: LustjinnApp, server: fake.FakeServer) -> None:
    server.shelve("characters", "Elena", "You are Elena.")
    async with app.run_test(size=(100, 30)) as pilot:
        await open_library(app, pilot)
        server.shelve("snippets", "storm", "Rain.")
        server.shelve("snippets", "fog", "Fog.")
        await pilot.press("r")
        await pilot.pause(0.3)
        assert " Snippets 2 " in tabs(app)


async def test_the_description_of_the_selected_entry_sits_over_its_text(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    server.shelve("characters", "Elena", "You are Elena.", description="The innkeeper.")
    server.shelve("characters", "Marta", "You are Marta.")
    async with app.run_test(size=(100, 30)) as pilot:
        await open_library(app, pilot)
        assert description(app) == "The innkeeper."
        assert library(app).query_one("#description").display
        await pilot.press("down")
        await pilot.pause(0.2)
        assert not library(app).query_one("#description").display  # none: nothing shown


async def test_the_row_shows_the_description_after_the_name_when_there_is_room(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    server.shelve("personas", "Elena", "You are Elena.", description="The innkeeper")
    server.shelve("personas", "Marta", "You are Marta.")
    async with app.run_test(size=(120, 30)) as pilot:
        screen = await open_library(app, pilot)
        await pilot.press("right")
        await pilot.pause(0.3)
        rows = screen.rows.render().plain
        assert "Elena  The innkeeper" in rows
        assert "Marta" in rows


async def test_a_long_description_is_cut_to_the_width_of_the_row(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    server.shelve("characters", "Elena", "You are Elena.", description="x" * 120)
    async with app.run_test(size=(80, 30)) as pilot:
        screen = await open_library(app, pilot)
        first = screen.rows.render().plain.splitlines()[0]
        assert "…" in first
        assert len(first) <= screen.rows.size.width


async def test_e_edits_the_description_on_one_line_and_saves_it_as_a_version(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    server.shelve("characters", "Elena", "You are Elena.")
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_library(app, pilot)
        await pilot.press("e")
        await pilot.pause()
        assert screen.legend.text.startswith(" Enter Save the description")
        await pilot.press(*"The innkeeper.", "enter")
        await pilot.pause(0.4)
        [made] = server.library["characters"]
        assert (made["description"], made["version"]) == ("The innkeeper.", 2)
        assert description(app) == "The innkeeper."
        assert screen.status_line.text == "Description saved."


async def test_a_description_can_be_cleared_by_saving_it_empty(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    server.shelve("characters", "Elena", "You are Elena.", description="The innkeeper.")
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_library(app, pilot)
        await pilot.press("e")
        await pilot.pause()
        await pilot.press("ctrl+u", "enter")
        await pilot.pause(0.4)
        [made] = server.library["characters"]
        assert made["description"] is None
        assert screen.status_line.text == "Description cleared."
        assert not screen.query_one("#description").display


async def test_an_unchanged_description_saves_nothing(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    server.shelve("characters", "Elena", "You are Elena.", description="The innkeeper.")
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_library(app, pilot)
        await pilot.press("e", "enter")
        await pilot.pause(0.3)
        assert server.library["characters"][0]["version"] == 1
        assert screen.status_line.text == "Nothing changed."


async def test_escape_leaves_the_description_as_it_was(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    server.shelve("characters", "Elena", "You are Elena.", description="The innkeeper.")
    async with app.run_test(size=(100, 30)) as pilot:
        screen = await open_library(app, pilot)
        await pilot.press("e", *"more", "escape")
        await pilot.pause(0.2)
        assert screen.status_line.text == "Cancelled."
        assert server.library["characters"][0]["description"] == "The innkeeper."


async def test_the_new_story_form_shows_the_description_of_the_character_and_the_persona(
    app: LustjinnApp, server: fake.FakeServer
) -> None:
    server.shelve("characters", "Elena", "You are Elena.", description="The innkeeper.")
    server.default_persona = server.shelve(
        "personas", "Me", "A tall man.", description="The pianist."
    )
    async with app.run_test(size=(110, 40)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("n")
        await pilot.pause(0.3)
        assert isinstance(app.screen, NewStoryScreen)
        world = app.screen.query_one("#world", Panel).query_one(".caption")
        persona = app.screen.query_one("#persona-text", Panel).query_one(".caption")
        assert "The innkeeper." in str(world.render())
        assert "The pianist." in str(persona.render())
