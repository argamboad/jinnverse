"""The library: characters, personas and snippets, read and kept from the terminal
(``Views/LibraryView.cs``).

Three shelves across the top, the names down the left, the text on the right. Under each name,
a line as the web's list has it: the version, how many stories use the entry, and its note or
the start of its text. ``N`` names a
new entry and opens it in the editor with a skeleton to fill in; ``Enter`` edits the text,
``O`` a character's opening, ``F2`` renames, ``Del`` removes after asking (the server refuses
while a live story uses it, and says which); ``D`` makes a persona the default. A name
starting with ``_`` is kept but not listed; ``_`` shows those too, and puts them away again.
``H`` opens the entry's history (``history.py``), where an old version can be put back.

A save carries the version the editor started from. When the entry moved on in between —
edited on the phone while the laptop had it open — the API refuses with the entry as it is now,
and ``ConflictScreen`` shows that text so the reader decides: ``Enter`` saves theirs over it,
``Esc`` keeps the server's and drops theirs. Nothing is overwritten by accident.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, Sequence
from functools import partial
from typing import ClassVar, Literal, cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import Input, Static

from lustjinn_tui import skeletons
from lustjinn_tui.api import (
    ApiError,
    Built,
    ConflictError,
    Counts,
    Entry,
    EntryFull,
    PieceEntry,
    Shelf,
    UnreachableError,
    Version,
    Voice,
)
from lustjinn_tui.builder import PersonaBuilderScreen
from lustjinn_tui.confirm import ConfirmScreen
from lustjinn_tui.editor import editor_name
from lustjinn_tui.hairline import Hairline
from lustjinn_tui.history import HistoryScreen
from lustjinn_tui.legend import Hint
from lustjinn_tui.listing import Rows
from lustjinn_tui.palette import PaletteCommand
from lustjinn_tui.status import Kind
from lustjinn_tui.textfmt import count, fit, pad
from lustjinn_tui.theme import HEADING, SELECTION
from lustjinn_tui.view import View

SHELVES: tuple[Shelf, ...] = ("characters", "personas", "snippets", "pieces")
KINDS: dict[Shelf, str] = {
    "characters": "character",
    "personas": "persona",
    "snippets": "snippet",
    "pieces": "piece",
}
VOICES: tuple[Voice, ...] = ("he", "she", "they", "any")
Mode = Literal["list", "naming", "renaming", "describing", "shorting"]


def about(entry: Entry, shelf: Shelf) -> str:
    """The line under a name, as the web's list has it: the version, how many stories use the
    entry (a snippet is copied when used, so it says only its version), then the owner's note,
    or the first line of the text when there is none."""
    parts = ["hidden", f"v{entry.version}"] if entry.hidden else [f"v{entry.version}"]
    if shelf != "snippets":
        parts.append(f"in {count(entry.used, 'story', 'stories')}" if entry.used else "unused")
    note = (entry.description or "").strip() or next(
        (line.strip() for line in entry.preview.splitlines() if line.strip()), ""
    )
    if note:
        parts.append(note)
    return " · ".join(parts)


class ConflictScreen(View):
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

    def __init__(
        self, message: str, theirs: EntryFull, save: Callable[[EntryFull], Awaitable[object]]
    ) -> None:
        super().__init__()
        self.theirs = theirs
        self._message = message
        self._save = save

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
        app = self.lustjinn
        app.pop_screen()
        await app.call("Saving", self._save(self.theirs))

    def action_back(self) -> None:
        below = self.lustjinn.screen_stack[-2]
        self.lustjinn.pop_screen()
        if isinstance(below, View):
            below.status("Kept the server's text. Yours was not saved.", Kind.WARNING)


class LibraryScreen(View):
    TITLE = "Library"
    HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("←→", "Shelf"),
        Hint("Enter", "Edit"),
        Hint("N", "New"),
        Hint("O", "Opening"),
        Hint("E", "Describe"),
        Hint("F2", "Rename"),
        Hint("D", "Default persona"),
        Hint("B", "Build persona"),
        Hint("Del", "Remove"),
        Hint("H", "History"),
        Hint("_", "Hidden"),
        Hint("PgUp/PgDn", "Read"),
        Hint("Esc", "Back"),
    )
    NAMING_HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("Enter", "Create and edit"),
        Hint("Esc", "Cancel"),
    )
    RENAMING_HINTS: ClassVar[tuple[Hint, ...]] = (Hint("Enter", "Rename"), Hint("Esc", "Cancel"))
    DESCRIBING_HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("Enter", "Save the description"),
        Hint("Esc", "Cancel"),
    )
    SHORTING_HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("Enter", "Save the short name"),
        Hint("Esc", "Cancel"),
    )
    PIECE_HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("←→", "Shelf"),
        Hint("Enter", "Edit the text"),
        Hint("N", "New piece"),
        Hint("E", "Describe"),
        Hint("F2", "Rename"),
        Hint("V", "Voice"),
        Hint("S", "Short name"),
        Hint("Del", "Remove"),
        Hint("PgUp/PgDn", "Read"),
        Hint("Esc", "Back"),
    )
    AUTO_FOCUS: ClassVar[str | None] = ""
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("left", "shelf(-1)", "Previous shelf", show=False),
        Binding("right,tab", "shelf(1)", "Next shelf", show=False),
        Binding("up", "move(-1)", "Up", show=False),
        Binding("down", "move(1)", "Down", show=False),
        Binding("home", "first", "First", show=False),
        Binding("end", "last", "Last", show=False),
        Binding("pageup", "page(-1)", "Read up", show=False),
        Binding("pagedown", "page(1)", "Read down", show=False),
        Binding("n,N", "new", "New", show=False),
        Binding("enter", "edit", "Edit", show=False),
        Binding("o,O", "opening", "Opening", show=False),
        Binding("e,E", "describe", "Describe", show=False),
        Binding("f2", "rename", "Rename", show=False),
        Binding("d,D", "default", "Default persona", show=False),
        Binding("b,B", "build", "Build a persona", show=False),
        Binding("v,V", "voice", "Voice of the piece", show=False),
        Binding("s,S", "short", "Short name", show=False),
        Binding("delete", "remove", "Remove", show=False),
        Binding("underscore", "hidden", "Hidden entries", show=False),
        Binding("h,H", "history", "History", show=False),
        Binding("r,R,ctrl+r", "refresh", "Refresh", show=False),
    ]

    DEFAULT_CSS = """
    LibraryScreen #tabs { height: 1; padding: 0 1; }
    LibraryScreen #split { height: 1fr; }
    LibraryScreen #pane { width: 30%; min-width: 16; height: 1fr; background: $surface; }
    LibraryScreen #pane Input { background: $surface; }
    LibraryScreen #text { width: 1fr; height: 1fr; padding: 0 1; }
    LibraryScreen #text VerticalScroll { height: 1fr; }
    LibraryScreen .caption { color: $muted; height: 1; }
    LibraryScreen #description { color: $foreground; height: auto; }
    LibraryScreen .prose { color: $muted; }
    """

    def __init__(self, shelf: Shelf = "characters", select: uuid.UUID | None = None) -> None:
        super().__init__()
        self.shelf: Shelf = shelf
        self._first_pick = select
        self._mode: Mode = "list"
        self._default_persona: uuid.UUID | None = None
        self._shown: EntryFull | None = None
        self._counts = Counts()
        self._show_hidden = False
        """Whether the shelves list their ``_name`` entries too; kept across shelves."""

    # -- the frame ------------------------------------------------------------------------------

    def hints(self) -> tuple[Hint, ...]:
        if self._mode == "naming":
            return self.NAMING_HINTS
        if self._mode == "renaming":
            return self.RENAMING_HINTS
        if self._mode == "describing":
            return self.DESCRIBING_HINTS
        if self._mode == "shorting":
            return self.SHORTING_HINTS
        if self.shelf == "pieces":
            return self.PIECE_HINTS
        return tuple(self._hidden_hint() if hint.key == "_" else hint for hint in self.HINTS)

    def _hidden_hint(self) -> Hint:
        """The key that shows the ``_name`` entries, with how many there are, as the web puts
        the count beside its toggle."""
        if self._show_hidden:
            return Hint("_", "Put hidden away")
        hidden = self._hidden_count()
        return Hint("_", f"Hidden ({hidden})" if hidden else "Hidden")

    def _hidden_count(self) -> int:
        hidden: int = getattr(self._counts.hidden, self.shelf, 0)
        return hidden

    def summary(self) -> str | None:
        return count(len(self.rows.items), KINDS[self.shelf])

    def layout_changed(self, narrow: bool) -> None:
        """On a phone the names sit above the text instead of beside it."""
        split = self.query_one("#split")
        split.styles.layout = "vertical" if narrow else "horizontal"
        pane = self.query_one("#pane")
        pane.styles.width = "100%" if narrow else "30%"
        pane.styles.height = 8 if narrow else "1fr"

    def commands(self) -> list[PaletteCommand]:
        return [
            PaletteCommand("Edit the text", "in your editor", self.action_edit),
            PaletteCommand("Edit the opening", "a character's first message", self.action_opening),
            PaletteCommand(
                "Describe the entry", "a short note for lists, never sent", self.action_describe
            ),
            PaletteCommand("New entry", "on this shelf, from a skeleton", self.action_new),
            PaletteCommand("Rename the entry", "the one the cursor is on", self.action_rename),
            PaletteCommand(
                "Default persona", "make the selected persona the default", self.action_default
            ),
            PaletteCommand("Build a persona", "from pieces", self.action_build),
            PaletteCommand("Change the voice", "of the selected piece", self.action_voice),
            PaletteCommand("Short name", "of the selected name piece", self.action_short),
            PaletteCommand("Remove the entry", "asks first", self.action_remove),
            PaletteCommand(
                "Hidden entries", "show or put away names starting with _", self.action_hidden
            ),
            PaletteCommand(
                "History", "every saved version; put an old one back", self.action_history
            ),
        ]

    def body(self) -> ComposeResult:
        yield Static("", id="tabs")
        yield Hairline()
        with Horizontal(id="split"):
            with Vertical(id="pane"):
                yield Input(placeholder="name…", id="name", compact=True)
                yield Rows[Entry](self._row, empty="", id="list")
            with Vertical(id="text"):
                yield Static("", classes="caption", id="caption")
                yield Static("", id="description")
                with VerticalScroll():
                    yield Static("", classes="prose", id="prose")

    def on_mount(self) -> None:
        self.query_one("#name", Input).display = False
        self._show_tabs()
        self.run_worker(partial(self._load, True, select=self._first_pick), exclusive=True)

    @property
    def rows(self) -> Rows[Entry]:
        return cast("Rows[Entry]", self.query_one("#list", Rows))

    @property
    def selected(self) -> Entry | None:
        return self.rows.selected

    @property
    def kind(self) -> str:
        return KINDS[self.shelf]

    # -- loading --------------------------------------------------------------------------------

    async def _load(self, announce: bool, *, select: uuid.UUID | None = None) -> None:
        api = self.lustjinn.api
        listed = await self.lustjinn.call(
            f"Reading the {self.shelf}", api.entries(self.shelf, hidden=self._show_hidden)
        )
        if listed is None:
            return
        if self.shelf == "personas":
            defaults = await self.lustjinn.call("Reading the default", api.defaults())
            self._default_persona = defaults.default_persona_id if defaults else None
        counted = await self.lustjinn.call("Counting the shelves", api.counts())
        if counted is not None:
            self._counts = counted
        self.rows.rows_per_item = 1 if self.shelf == "pieces" else 2
        self.rows.set_items(listed, empty=f"No {self.kind}s yet — N starts one.")
        if select is not None:
            index = next((i for i, e in enumerate(listed) if e.id == select), -1)
            if index >= 0:
                self.rows.select(index)
        self._show_tabs()
        self.refresh_summary()
        self.refresh_hints()
        await self._show_text()
        if announce:
            self.status(f"{count(len(listed), self.kind)} on the shelf.", Kind.SUCCESS)

    def _show_tabs(self) -> None:
        parts: list[str] = []
        for shelf in SHELVES:
            label = Content(f" {shelf.capitalize()} {getattr(self._counts, shelf)} ").markup
            parts.append(f"{SELECTION}{label}[/]" if shelf == self.shelf else f"[$muted]{label}[/]")
        self.query_one("#tabs", Static).update(Content.from_markup("  ".join(parts)))

    def _row(self, entry: Entry, selected: bool, width: int) -> Content:
        """Two rows: the name, then ``about`` under it, muted. A piece takes one: its name
        already says its slot and its voice, and its note follows it."""
        if isinstance(entry, PieceEntry):
            return self._piece_row(entry, selected, width)
        marker = "★ " if self.shelf == "personas" and entry.id == self._default_persona else "  "
        name = Content(pad(f"{marker}{entry.name}", width)).markup
        line = Content(pad(f"  {about(entry, self.shelf)}", width)).markup
        if selected:
            return Content.from_markup(f"{SELECTION}{name}[/]\n{SELECTION}{line}[/]")
        return Content.from_markup(f"{name}\n[$muted]{line}[/]")

    @staticmethod
    def _piece_row(entry: PieceEntry, selected: bool, width: int) -> Content:
        head = f"  {entry.name}"
        if not entry.description:
            line = Content(pad(head, width)).markup
            return Content.from_markup(f"{SELECTION}{line}[/]" if selected else line)
        # The note after the name, muted, as much of it as the width leaves room for.
        room = width - len(head) - 2
        note = fit(entry.description, room) if room > 2 else ""
        used = len(head) + (2 + len(note) if note else 0)
        gap = " " * max(0, width - used)
        name = Content(head).markup
        tail = f"  {Content(note).markup}" if note else ""
        if selected:
            return Content.from_markup(f"{SELECTION}{name}{tail}{gap}[/]")
        return Content.from_markup(f"{name}[$muted]{tail}[/]{gap}")

    async def _show_text(self) -> None:
        entry = self.selected
        caption = self.query_one("#caption", Static)
        note = self.query_one("#description", Static)
        prose = self.query_one("#prose", Static)
        if entry is None:
            self._shown = None
            caption.update("")
            note.display = False
            prose.update("")
            return
        if isinstance(entry, PieceEntry):
            full: EntryFull = entry  # a piece's list already carries its whole text
        else:
            try:
                full = await self.lustjinn.api.entry(self.shelf, entry.id)
            except ApiError, UnreachableError:
                return
        self._shown = full
        used = f"used by {', '.join(full.used_by)}" if full.used_by else "used by no live story"
        if self.shelf == "snippets":
            used = "copied into a message when :name is typed"
        if isinstance(full, PieceEntry):
            caption.update(
                f"{full.piece_name}   ·   {full.slot_label}   ·   {full.voice} voice   ·   "
                f"version {full.version}"
            )
        else:
            caption.update(f"{full.name}   ·   version {full.version}   ·   {used}")
        note.display = bool(full.description)
        note.update(full.description or "")
        text = full.text
        if isinstance(full, PieceEntry) and full.short:
            text += f"\n\n(short form: {full.short})"
        if self.shelf == "characters":
            opening = full.opening.strip() if full.opening else "(none — O writes one)"
            text += f"\n\n=== THE OPENING ===\n\n{opening}"
        prose.update(text)
        self.query_one(VerticalScroll).scroll_home(animate=False)

    @on(Rows.Selected)
    async def _selection_moved(self) -> None:
        await self._show_text()

    @on(Rows.Opened)
    def _row_opened(self) -> None:
        self.action_edit()

    # -- moving ---------------------------------------------------------------------------------

    def action_shelf(self, delta: int) -> None:
        if self._mode != "list":
            return
        at = SHELVES.index(self.shelf)
        self.shelf = SHELVES[(at + delta) % len(SHELVES)]
        self.rows.set_items(())
        self.run_worker(partial(self._load, False), exclusive=True)

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

    def action_refresh(self) -> None:
        self.run_worker(partial(self._load, True), exclusive=True)

    def action_hidden(self) -> None:
        """Shows the entries whose name starts with ``_`` — kept, but not listed — or puts them
        away again. Without it, an entry renamed to ``_x`` here could not be reached here."""
        if self._mode != "list":
            return
        if self.shelf == "pieces":
            self.status("A piece is never hidden: this shelf shows every one.", Kind.WARNING)
            return
        self.run_worker(self._toggle_hidden, exclusive=True)

    async def _toggle_hidden(self) -> None:
        keep = self.selected.id if self.selected is not None else None
        self._show_hidden = not self._show_hidden
        await self._load(False, select=keep)
        if not self._show_hidden:
            self.status("Hidden entries put away.")
            return
        hidden = self._hidden_count()
        if hidden:
            self.status(f"Showing {count(hidden, f'hidden {self.kind}')} too.", Kind.SUCCESS)
        else:
            self.status(f"No hidden {self.kind}s: a name starting with _ hides one.")

    def action_back(self) -> None:
        if self._mode != "list":
            self._leave_field()
            self.status("Cancelled.")
            return
        self.lustjinn.go_back()

    # -- naming and renaming --------------------------------------------------------------------

    def _open_field(self, mode: Mode, value: str, placeholder: str) -> None:
        self._mode = mode
        field = self.query_one("#name", Input)
        field.value = value
        field.placeholder = placeholder
        field.display = True
        field.focus()
        self.refresh_hints()

    def _leave_field(self) -> None:
        self._mode = "list"
        field = self.query_one("#name", Input)
        field.display = False
        field.value = ""
        self.set_focus(None)
        self.refresh_hints()

    def action_describe(self) -> None:
        entry = self._shown
        if self._mode == "list" and entry is not None:
            self._open_field("describing", entry.description or "", "a short note for lists")

    def action_new(self) -> None:
        if self._mode != "list":
            return
        if self.shelf == "pieces":
            self._open_field(
                "naming",
                "",
                "new piece: its slot, then its name (home Penthouse); V changes the voice",
            )
        else:
            self._open_field("naming", "", f"new {self.kind}: its name")

    def action_voice(self) -> None:
        shown = self._shown
        if self._mode != "list" or not isinstance(shown, PieceEntry):
            if self._mode == "list":
                self.status("Only a piece has a voice.", Kind.WARNING)
            return
        wanted = VOICES[(VOICES.index(shown.voice) + 1) % len(VOICES)]
        self.run_worker(partial(self._set_voice, shown, wanted), exclusive=True)

    async def _set_voice(self, shown: PieceEntry, voice: Voice) -> None:
        try:
            saved = await self.lustjinn.api.save_piece(shown.id, shown.version, voice=voice)
        except ConflictError as conflict:
            self.status(conflict.detail, Kind.WARNING)
            await self._load(False, select=shown.id)
            return
        except ApiError as refused:
            self.status(refused.detail, Kind.ERROR)
            return
        except UnreachableError:
            self.lustjinn.lost("The server stopped answering while saving.")
            return
        await self._load(False, select=saved.id)
        self.status(f"Now written in the {saved.voice} voice.", Kind.SUCCESS)

    def action_short(self) -> None:
        shown = self._shown
        if self._mode != "list":
            return
        if not isinstance(shown, PieceEntry) or shown.slot != "name":
            self.status("Only a name piece has a short form.", Kind.WARNING)
            return
        self._open_field(
            "shorting", shown.short or "", "the short name, used after the first mention"
        )

    async def _set_short(self, shown: PieceEntry, short: str) -> None:
        if not short:
            self.status("A name piece needs a short form.", Kind.WARNING)
            return
        if short == (shown.short or ""):
            self.status("Nothing changed.")
            return
        try:
            saved = await self.lustjinn.api.save_piece(shown.id, shown.version, short=short)
        except ConflictError as conflict:
            self.status(conflict.detail, Kind.WARNING)
            await self._load(False, select=shown.id)
            return
        except ApiError as refused:
            self.status(refused.detail, Kind.ERROR)
            return
        except UnreachableError:
            self.lustjinn.lost("The server stopped answering while saving.")
            return
        await self._load(False, select=saved.id)
        self.status(f"Short name: {short}.", Kind.SUCCESS)

    async def _create_piece(self, answer: str) -> None:
        """``slot [voice] name``: a new piece in the pool, then the editor for its text. A name
        piece is its name: its text is the full name, and S gives it a short form."""
        api = self.lustjinn.api
        slots = await self.lustjinn.call("Reading the slots", api.piece_slots())
        if slots is None:
            return
        words = answer.split()
        keys = {slot.key: slot.label for slot in slots}
        if not words or words[0].lower() not in keys:
            self.status(f"Start with a slot: {', '.join(keys)}.", Kind.WARNING)
            return
        slot = words[0].lower()
        voice: Voice = "he"
        rest = words[1:]
        if rest and rest[0].lower() in VOICES:
            voice = rest[0].lower()  # type: ignore[assignment]
            rest = rest[1:]
        name = " ".join(rest)
        if not name:
            self.status("A piece needs a name.", Kind.WARNING)
            return
        if slot == "name":
            text, short = name, name.split()[0]
        else:
            before = skeletons.piece(keys[slot].lower(), voice)
            self.status(f"Waiting for {editor_name()} — save and close to come back.")
            after = self.lustjinn.editor(self.lustjinn, before, "-piece.txt")
            if after is None or not after.strip() or after.strip() == before.strip():
                self.status("Nothing was written.")
                return
            text, short = after.strip(), None
        created = await self.lustjinn.call(
            "Saving the piece", api.create_piece(slot, voice, name, text, short)
        )
        if created is None:
            return
        await self._load(False, select=created.id)
        self.status(f"'{created.name}' is in the pool.", Kind.SUCCESS)

    def action_rename(self) -> None:
        entry = self.selected
        if self._mode == "list" and entry is not None:
            bare = entry.piece_name if isinstance(entry, PieceEntry) else entry.name
            self._open_field("renaming", bare, "new name")

    @on(Input.Submitted, "#name")
    def _named(self, event: Input.Submitted) -> None:
        name = event.value.strip()
        mode = self._mode
        entry = self.selected
        self._leave_field()
        if mode == "describing":
            shown = self._shown
            if shown is not None:
                self.run_worker(partial(self._describe, shown, name), exclusive=True)
            return
        if mode == "shorting":
            shown = self._shown
            if isinstance(shown, PieceEntry):
                self.run_worker(partial(self._set_short, shown, name), exclusive=True)
            return
        if not name:
            self.status(f"A {self.kind} needs a name.", Kind.WARNING)
            return
        if mode == "naming" and self.shelf == "pieces":
            self.run_worker(partial(self._create_piece, name), exclusive=True)
        elif mode == "naming":
            self.run_worker(partial(self._create, name), exclusive=True)
        elif entry is not None:
            if name == (entry.piece_name if isinstance(entry, PieceEntry) else entry.name):
                self.status("That is already its name.")
                return
            self.run_worker(partial(self._rename, entry, name), exclusive=True)

    async def _create(self, name: str) -> None:
        created = await self.lustjinn.call(
            "Creating",
            self.lustjinn.api.create_entry(self.shelf, name, skeletons.BY_SHELF[self.shelf]),
        )
        if created is None:
            return
        await self._load(False, select=created.id)
        await self._edit(created, "text")

    async def _describe(self, entry: EntryFull, description: str) -> None:
        """Saves the description over the version on screen; blank clears it."""
        if description == (entry.description or ""):
            self.status("Nothing changed.")
            return
        saved = await self._save(
            entry.id,
            entry.version,
            description=description or None,
            clear_description=not description,
        )
        if saved is not None:
            await self._load(False, select=saved.id)
            self.status(
                "Description saved." if saved.description else "Description cleared.",
                Kind.SUCCESS,
            )

    async def _rename(self, entry: Entry, name: str) -> None:
        renamed = await self._save(entry.id, entry.version, name=name)
        if renamed is not None:
            await self._load(False, select=renamed.id)
            if isinstance(renamed, PieceEntry):
                self.status(f'Renamed to "{renamed.piece_name}".', Kind.SUCCESS)
                return
            if renamed.hidden and not self._show_hidden:
                self.status(
                    f'Renamed to "{renamed.name}": a name starting with _ is hidden. _ shows it.',
                    Kind.SUCCESS,
                )
                return
            self.status(
                f'Renamed to "{renamed.name}". Every story using it sees the name at once.',
                Kind.SUCCESS,
            )

    # -- editing --------------------------------------------------------------------------------

    def action_edit(self) -> None:
        entry = self._shown
        if self._mode != "list" or entry is None:
            return
        self.run_worker(partial(self._edit, entry, "text"), exclusive=True)

    def action_opening(self) -> None:
        entry = self._shown
        if self._mode != "list" or entry is None:
            return
        if self.shelf != "characters":
            self.status(f"A {self.kind} has no opening.", Kind.WARNING)
            return
        self.run_worker(partial(self._edit, entry, "opening"), exclusive=True)

    async def _edit(self, entry: EntryFull, field: Literal["text", "opening"]) -> None:
        """Hands the text to the reader's editor and saves what comes back over the version
        the editor started from."""
        before = entry.text if field == "text" else (entry.opening or skeletons.OPENING)
        self.status(f"Waiting for {editor_name()} — save and close to come back.")
        after = self.lustjinn.editor(self.lustjinn, before, f"-{self.kind}.txt")
        if after is None or after.strip() == before.strip():
            self.status("Nothing changed.")
            return
        if field == "text":
            saved = await self._save(entry.id, entry.version, text=after.rstrip() + "\n")
        else:
            saved = await self._save(
                entry.id, entry.version, opening=after.strip() or None, clear_opening=True
            )
        if saved is not None:
            await self._load(False, select=saved.id)
            if self.shelf == "pieces":
                self.status(
                    "Saved. Personas already built from it keep the text they were made with.",
                    Kind.SUCCESS,
                )
                return
            self.status(
                f"Saved. Every story using '{saved.name}' sees the change from its next turn.",
                Kind.SUCCESS,
            )

    async def _save(
        self,
        entry_id: uuid.UUID,
        version: int,
        *,
        name: str | None = None,
        text: str | None = None,
        opening: str | None = None,
        clear_opening: bool = False,
        description: str | None = None,
        clear_description: bool = False,
    ) -> EntryFull | None:
        """A save over ``version``; a conflict opens the screen that shows the server's text."""
        api = self.lustjinn.api
        line = self.status_line
        line.busy("Saving")
        try:
            return await api.save_entry(
                self.shelf,
                entry_id,
                version,
                name=name,
                text=text,
                opening=opening,
                clear_opening=clear_opening,
                description=description,
                clear_description=clear_description,
            )
        except ConflictError as conflict:

            async def over(theirs: EntryFull) -> None:
                saved = await api.save_entry(
                    self.shelf,
                    entry_id,
                    theirs.version,
                    name=name,
                    text=text,
                    opening=opening,
                    clear_opening=clear_opening,
                    description=description,
                    clear_description=clear_description,
                )
                await self._load(False, select=saved.id)
                self.status(f"Saved over version {theirs.version}.", Kind.SUCCESS)

            self.lustjinn.push_screen(ConflictScreen(conflict.detail, conflict.current, over))
        except ApiError as refused:
            self.status(refused.detail, Kind.ERROR)
        except UnreachableError:
            self.lustjinn.lost("The server stopped answering while saving.")
        finally:
            line.idle()
        return None

    # -- the default persona and removing --------------------------------------------------------

    def action_default(self) -> None:
        if self._mode != "list":
            return
        if self.shelf != "personas":
            self.status("Only a persona can be the default.", Kind.WARNING)
            return
        entry = self.selected
        if entry is not None:
            self.run_worker(partial(self._set_default, entry), exclusive=True)

    async def _set_default(self, entry: Entry) -> None:
        clearing = entry.id == self._default_persona
        set_to = await self.lustjinn.call(
            "Setting the default",
            self.lustjinn.api.set_default_persona(None if clearing else entry.id),
        )
        if set_to is None:
            return
        self._default_persona = set_to.default_persona_id
        self.rows.refresh()
        if clearing:
            self.status("No default persona: a story that names none plays as nobody.")
        else:
            self.status(
                f"{entry.name} is the default persona: every story that names none plays as it.",
                Kind.SUCCESS,
            )

    def action_build(self) -> None:
        """A persona made from pieces, opened on top of this screen; the new one is selected."""
        if self._mode != "list":
            return

        async def built(persona: Built) -> None:
            self.shelf = "personas"
            await self._load(False, select=persona.id)
            self.status(
                f"Built '{persona.name}' from pieces. It is an ordinary persona now: edit it "
                "here like any other.",
                Kind.SUCCESS,
            )

        self.lustjinn.push_screen(PersonaBuilderScreen(built))

    # -- history ---------------------------------------------------------------------------------

    def action_history(self) -> None:
        """Every saved version of the entry, on its own screen, where one can be put back."""
        entry = self._shown
        if self._mode != "list" or entry is None:
            return
        if isinstance(entry, PieceEntry):
            self.status("A piece has no history to show.", Kind.WARNING)
            return
        self.lustjinn.push_screen(HistoryScreen(self.shelf, entry, partial(self._put_back, entry)))

    async def _put_back(self, entry: EntryFull, old: Version) -> None:
        """Saves an old version as a new one over the version the history was opened on: an
        ordinary save, so a change made elsewhere meanwhile meets the conflict screen."""
        if isinstance(self.lustjinn.screen, HistoryScreen):
            self.lustjinn.pop_screen()
        character = self.shelf == "characters"
        saved = await self._save(
            entry.id,
            entry.version,
            name=old.name,
            text=old.text,
            opening=old.opening if character else None,
            clear_opening=character,
            description=old.description,
            clear_description=True,
        )
        if saved is None:
            return
        await self._load(False, select=saved.id)
        if saved.version == entry.version:
            self.status(f"Version {old.version} says what the current one says: nothing changed.")
            return
        reach = (
            "" if self.shelf == "snippets" else " Every story using it reads it from its next turn."
        )
        self.status(
            f"Version {old.version} is back, saved as version {saved.version}.{reach}",
            Kind.SUCCESS,
        )

    def action_remove(self) -> None:
        entry = self._shown
        if self._mode != "list" or entry is None:
            return
        consequences: Sequence[str]
        if isinstance(entry, PieceEntry):
            consequences = (
                "Nothing depends on a piece: personas built from it keep their own copy.",
                "This cannot be undone.",
            )
        elif entry.used_by:
            consequences = (
                "The server will refuse while a live story uses it:",
                *(f"  {name}" for name in entry.used_by),
            )
        else:
            consequences = (
                f"No live story uses this {self.kind}. Its history stays; the entry goes.",
                "This cannot be undone.",
            )

        async def remove() -> None:
            await self.lustjinn.api.delete_entry(self.shelf, entry.id)
            await self._load(False)
            self.status(f"Removed '{entry.name}'.", Kind.SUCCESS)

        self.lustjinn.push_screen(
            ConfirmScreen(
                "Remove", f'Delete the {self.kind} "{entry.name}"?', consequences, "Delete", remove
            )
        )
