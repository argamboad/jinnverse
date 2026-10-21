"""An entry's history from the library: every version, newest first, read beside the list, and an
old one put back as a new version after asking (#213)."""

from typing import Any

from textual.pilot import Pilot

from jinnverse_tui.app import JinnverseApp
from jinnverse_tui.confirm import ConfirmScreen
from jinnverse_tui.history import HistoryScreen
from jinnverse_tui.library import ConflictScreen, LibraryScreen
from jinnverse_tui.status import Kind
from jinnverse_tui.stories import StoriesScreen
from tui_support import fake_server as fake


def elena_in_three_versions(server: fake.FakeServer) -> dict[str, Any]:
    elena = server.shelve(
        "characters", "Elena", "You are Elena.", opening="*The door opens.*", description="Inn"
    )
    server.revise(elena, text="You are Elena, older.")
    server.revise(elena, name="Elena Vell", text="You are Elena Vell.", description=None)
    return elena


async def open_history(app: JinnverseApp, pilot: Pilot[None]) -> HistoryScreen:
    await pilot.pause(0.1)
    assert isinstance(app.screen, StoriesScreen)
    await pilot.press("m")
    await pilot.pause(0.3)
    await pilot.press("h")
    await pilot.pause(0.3)
    screen = app.screen
    assert isinstance(screen, HistoryScreen)
    return screen


def caption(screen: HistoryScreen) -> str:
    return str(screen.query_one("#caption").render())


def prose(screen: HistoryScreen) -> str:
    return str(screen.query_one("#prose").render())


async def test_h_lists_every_version_newest_first_and_reads_the_one_highlighted(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    elena_in_three_versions(server)
    async with app.run_test(size=(120, 30)) as pilot:
        screen = await open_history(app, pilot)
        assert [v.version for v in screen.rows.items] == [3, 2, 1]
        lines = screen.rows.render().plain.splitlines()
        assert lines[0].rstrip().endswith("current")
        assert "current" not in lines[1]
        assert caption(screen).startswith("Elena Vell   ·   version 3")
        assert "You are Elena Vell." in prose(screen)
        assert screen.status_line.text == "3 versions of 'Elena Vell', newest first."
        await pilot.press("down", "down")
        await pilot.pause(0.2)
        assert caption(screen).startswith("Elena   ·   version 1")
        assert str(screen.query_one("#description").render()) == "Inn"
        assert "You are Elena." in prose(screen)
        assert "The door opens." in prose(screen)  # a character's opening, as the library reads


async def test_enter_asks_then_puts_the_old_version_back_as_a_new_one(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    elena = elena_in_three_versions(server)
    async with app.run_test(size=(120, 30)) as pilot:
        await open_history(app, pilot)
        await pilot.press("down", "down", "enter")
        await pilot.pause(0.2)
        assert isinstance(app.screen, ConfirmScreen)
        await pilot.press("enter")
        await pilot.pause(0.4)
        library = app.screen
        assert isinstance(library, LibraryScreen)
        assert elena["version"] == 4
        assert (elena["name"], elena["text"], elena["description"]) == (
            "Elena",
            "You are Elena.",
            "Inn",
        )
        assert [v["version"] for v in server.history[elena["id"]]] == [1, 2, 3, 4]  # it grew
        assert library.status_line.text == (
            "Version 1 is back, saved as version 4. Every story using it reads it from its "
            "next turn."
        )
        assert library.status_line.kind == Kind.SUCCESS


async def test_the_current_version_is_not_put_back(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    elena = elena_in_three_versions(server)
    async with app.run_test(size=(120, 30)) as pilot:
        screen = await open_history(app, pilot)
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen is screen
        assert screen.status_line.text == "That is the current version."
        assert elena["version"] == 3


async def test_esc_on_the_question_leaves_the_entry_as_it_is(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    elena = elena_in_three_versions(server)
    async with app.run_test(size=(120, 30)) as pilot:
        screen = await open_history(app, pilot)
        await pilot.press("down", "enter")
        await pilot.pause(0.2)
        await pilot.press("escape")
        await pilot.pause(0.2)
        assert app.screen is screen
        assert screen.status_line.text == "Cancelled."
        assert elena["version"] == 3


async def test_a_put_back_over_a_save_made_elsewhere_meets_the_conflict_screen(
    app: JinnverseApp, server: fake.FakeServer
) -> None:
    elena = elena_in_three_versions(server)
    async with app.run_test(size=(120, 30)) as pilot:
        await open_history(app, pilot)
        server.revise(elena, text="Changed on the phone.")  # version 4, while the list is open
        await pilot.press("down", "down", "enter")
        await pilot.pause(0.2)
        await pilot.press("enter")
        await pilot.pause(0.4)
        assert isinstance(app.screen, ConflictScreen)
        assert elena["text"] == "Changed on the phone."  # nothing overwritten by accident


async def test_a_piece_has_no_history_to_show(app: JinnverseApp, server: fake.FakeServer) -> None:
    server.piece("look", "Athletic", "{short} is athletic.")
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause(0.1)
        await pilot.press("m")
        await pilot.pause(0.3)
        await pilot.press("left")  # round to the pieces
        await pilot.pause(0.3)
        await pilot.press("h")
        await pilot.pause()
        screen = app.screen
        assert isinstance(screen, LibraryScreen)
        assert screen.status_line.text == "A piece has no history to show."
