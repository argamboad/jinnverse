"""The conflict screen: an entry as the server has it now, beside what the reader was about to
save over it. Shared by the library (a card's save) and a character's lore (an entry's save).

A save carries the version the editor started from. When the entry moved on in between —
edited on the phone while the laptop had it open — the API refuses with the entry as it is now,
and this screen shows that text so the reader decides: ``Enter`` saves theirs over it, ``Esc``
keeps the server's and drops theirs. Nothing is overwritten by accident.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import ClassVar, Protocol

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import VerticalScroll
from textual.content import Content
from textual.widgets import Static

from jinnverse_tui.hairline import Hairline
from jinnverse_tui.legend import Hint
from jinnverse_tui.status import Kind
from jinnverse_tui.theme import HEADING
from jinnverse_tui.view import View


class Conflicted(Protocol):
    """What the conflict screen needs of an entry: a card's, or a lore entry's."""

    @property
    def name(self) -> str: ...
    @property
    def version(self) -> int: ...
    @property
    def text(self) -> str: ...


class ConflictScreen[T: Conflicted](View):
    """The entry as the server has it now, beside what the reader was about to save."""

    TITLE = "Changed elsewhere"
    HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("Enter", "Save mine over it"),
        Hint("PgUp/PgDn", "Read theirs"),
        Hint("Esc", "Keep theirs"),
    )
    AUTO_FOCUS: ClassVar[str | None] = ""
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "save_mine", "Save mine", show=False),
        Binding("pageup", "page(-1)", "Up", show=False),
        Binding("pagedown", "page(1)", "Down", show=False),
    ]

    DEFAULT_CSS = """
    ConflictScreen #body { padding: 0 2; }
    ConflictScreen .heading { margin-top: 1; }
    ConflictScreen .why { color: $warning; }
    ConflictScreen VerticalScroll { height: 1fr; }
    ConflictScreen .theirs { padding-left: 2; color: $muted; }
    """

    def __init__(self, message: str, theirs: T, save: Callable[[T], Awaitable[object]]) -> None:
        super().__init__()
        self._theirs: T = theirs
        self._message = message
        self._save = save

    @property
    def theirs(self) -> Conflicted:
        """The entry as the server has it: a card's, or a lore entry's. A test asks which."""
        return self._theirs

    def body(self) -> ComposeResult:
        yield Static(
            Content.from_markup(
                f"{HEADING}{Content(self.theirs.name).markup}[/]   "
                f"[$muted]version {self.theirs.version}, as the server has it now[/]"
            ),
            classes="heading",
        )
        yield Static(self._message, classes="why")
        yield Hairline()
        with VerticalScroll():
            yield Static(self.theirs.text, classes="theirs")

    def action_page(self, direction: int) -> None:
        scroller = self.query_one(VerticalScroll)
        if direction > 0:
            scroller.scroll_page_down(animate=False)
        else:
            scroller.scroll_page_up(animate=False)

    async def action_save_mine(self) -> None:
        app = self.jinnverse
        app.pop_screen()
        await app.call("Saving", self._save(self._theirs))

    def action_back(self) -> None:
        below = self.jinnverse.screen_stack[-2]
        self.jinnverse.pop_screen()
        if isinstance(below, View):
            below.status("Kept the server's text. Yours was not saved.", Kind.WARNING)
