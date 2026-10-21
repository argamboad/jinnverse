"""An entry's history: every version ever saved, newest first, and putting an old one back
(#213; the web's history drawer).

The versions go down the left and the highlighted one is read on the right, as the library
reads an entry. ``Enter`` puts that version back after asking: its name, text, description and,
for a character, opening are saved **as a new version** over the current one, through the
library's own save — a version changed elsewhere meanwhile meets the same conflict screen as
any other save. Nothing is overwritten in place: the history only grows, so putting back is
itself undone by putting back the version before it.

.NET readers: a read-only master-detail view over ``GET …/history``, the kind a WPF app binds a
``ListBox`` and a ``TextBlock`` to; the restore is the ordinary ``PATCH`` with old values.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from functools import partial
from typing import ClassVar, cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import Static

from jinnverse_tui import buttons as phone
from jinnverse_tui.api import EntryFull, Shelf, Version
from jinnverse_tui.confirm import ConfirmScreen
from jinnverse_tui.legend import Hint
from jinnverse_tui.listing import Rows
from jinnverse_tui.palette import PaletteCommand
from jinnverse_tui.status import Kind
from jinnverse_tui.textfmt import count, pad
from jinnverse_tui.theme import SELECTION
from jinnverse_tui.view import View

KINDS: dict[Shelf, str] = {"characters": "character", "personas": "persona", "snippets": "snippet"}


def stamp(when: datetime) -> str:
    """When a version was saved, in the reader's own time: ``2026-10-16 14:02``."""
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.astimezone().strftime("%Y-%m-%d %H:%M")


class HistoryScreen(View):
    TITLE = "History"
    HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("↑↓", "Version"),
        Hint("Enter", "Put it back"),
        Hint("PgUp/PgDn", "Read"),
        Hint("Esc", "Back"),
    )
    BUTTONS: ClassVar[tuple[phone.Button, ...]] = (phone.BACK, phone.Button("Put back", "enter"))
    AUTO_FOCUS: ClassVar[str | None] = ""
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", "Up", show=False),
        Binding("down", "move(1)", "Down", show=False),
        Binding("home", "first", "First", show=False),
        Binding("end", "last", "Last", show=False),
        Binding("pageup", "page(-1)", "Read up", show=False),
        Binding("pagedown", "page(1)", "Read down", show=False),
        Binding("enter", "put_back", "Put it back", show=False),
    ]

    DEFAULT_CSS = """
    HistoryScreen #split { height: 1fr; }
    HistoryScreen #pane { width: 30%; min-width: 16; height: 1fr; background: $surface; }
    HistoryScreen #text { width: 1fr; height: 1fr; padding: 0 1; }
    HistoryScreen #text VerticalScroll { height: 1fr; }
    HistoryScreen .caption { color: $muted; height: 1; }
    HistoryScreen #description { color: $foreground; height: auto; }
    HistoryScreen .prose { color: $muted; }
    """

    def __init__(
        self, shelf: Shelf, entry: EntryFull, put_back: Callable[[Version], Awaitable[object]]
    ) -> None:
        super().__init__()
        self.shelf: Shelf = shelf
        self.entry = entry
        self._put_back = put_back

    @property
    def kind(self) -> str:
        return KINDS.get(self.shelf, "entry")

    def summary(self) -> str | None:
        return count(len(self.rows.items), "version")

    def layout_changed(self, narrow: bool) -> None:
        """On a phone the versions sit above the text instead of beside it."""
        split = self.query_one("#split")
        split.styles.layout = "vertical" if narrow else "horizontal"
        pane = self.query_one("#pane")
        pane.styles.width = "100%" if narrow else "30%"
        pane.styles.height = 6 if narrow else "1fr"

    def commands(self) -> list[PaletteCommand]:
        return [
            PaletteCommand(
                "Put this version back", "saved as a new version; asks first", self.action_put_back
            )
        ]

    def body(self) -> ComposeResult:
        with Horizontal(id="split"):
            with Vertical(id="pane"):
                yield Rows[Version](self._row, empty="Reading the history…", id="versions")
            with Vertical(id="text"):
                yield Static("", classes="caption", id="caption")
                yield Static("", id="description")
                with VerticalScroll():
                    yield Static("", classes="prose", id="prose")

    def on_mount(self) -> None:
        self.run_worker(self._load, exclusive=True)

    @property
    def rows(self) -> Rows[Version]:
        return cast("Rows[Version]", self.query_one("#versions", Rows))

    @property
    def selected(self) -> Version | None:
        return self.rows.selected

    async def _load(self) -> None:
        versions = await self.jinnverse.call(
            "Reading the history", self.jinnverse.api.history(self.shelf, self.entry.id)
        )
        if versions is None:
            self.rows.set_items((), empty="No history could be read.")
            return
        self.rows.set_items(versions, empty="No saved versions.")
        self.refresh_summary()
        self._show()
        self.status(
            f"{count(len(versions), 'version')} of '{self.entry.name}', newest first.",
            Kind.SUCCESS,
        )

    def _row(self, version: Version, selected: bool, width: int) -> Content:
        current = "  current" if version.version == self.entry.version else ""
        head = pad(f"  v{version.version}  {stamp(version.saved_at)}", max(1, width - len(current)))
        line = Content(head).markup
        tail = Content(current).markup
        if selected:
            return Content.from_markup(f"{SELECTION}{line}{tail}[/]")
        return Content.from_markup(f"{line}[$accent]{tail}[/]")

    def _show(self) -> None:
        version = self.selected
        caption = self.query_one("#caption", Static)
        note = self.query_one("#description", Static)
        prose = self.query_one("#prose", Static)
        if version is None:
            caption.update("")
            note.display = False
            prose.update("")
            return
        caption.update(
            f"{version.name}   ·   version {version.version}   ·   {stamp(version.saved_at)}"
        )
        note.display = bool(version.description)
        note.update(version.description or "")
        text = version.text
        if self.shelf == "characters":
            opening = version.opening.strip() if version.opening else "(none)"
            text += f"\n\n=== THE OPENING ===\n\n{opening}"
        prose.update(text)
        self.query_one(VerticalScroll).scroll_home(animate=False)

    @on(Rows.Selected)
    def _selection_moved(self) -> None:
        self._show()

    @on(Rows.Opened)
    def _row_opened(self) -> None:
        self.action_put_back()

    # -- moving ---------------------------------------------------------------------------------

    def action_move(self, delta: int) -> None:
        self.rows.move(delta)

    def action_first(self) -> None:
        self.rows.first()

    def action_last(self) -> None:
        self.rows.last()

    def action_page(self, direction: int) -> None:
        scroller = self.query_one(VerticalScroll)
        if direction > 0:
            scroller.scroll_page_down(animate=False)
        else:
            scroller.scroll_page_up(animate=False)

    # -- putting a version back -----------------------------------------------------------------

    def action_put_back(self) -> None:
        version = self.selected
        if version is None:
            return
        if version.version == self.entry.version:
            self.status("That is the current version.", Kind.WARNING)
            return
        uses = (
            "Every story using it reads it from its next turn."
            if self.shelf != "snippets"
            else "A snippet already copied into a message stays as it was."
        )
        self.jinnverse.push_screen(
            ConfirmScreen(
                "Put back",
                f'Put version {version.version} of "{self.entry.name}" back?',
                (
                    f"It is saved as version {self.entry.version + 1}: its name, text, "
                    "description" + (" and opening." if self.shelf == "characters" else "."),
                    f"Version {self.entry.version} and every other stay in the history.",
                    uses,
                ),
                "Put back",
                partial(self._put_back, version),
            )
        )
