"""A character's lore, from the library (#269): the entries sent only while one of their keys is in
the scene, read and kept from the terminal.

The entries go down the left in the order they were made — the order of the card they came
from — with their keys under each name, and the text on the right. ``N`` names a new entry,
asks for its keys (comma-separated, Enter with none cancels) and opens the editor on a skeleton;
``Enter`` edits the text in the reader's editor; ``K`` edits the keys; ``F2`` renames; ``Del``
removes after asking. A save carries the version the editor started from and meets the same
conflict screen as a card's save when the entry moved on in between.

.NET readers: the library's master-detail view again, over ``GET …/characters/{id}/lore``, with
the one-question-at-a-time input the library uses for ``N`` and ``F2``.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial
from typing import ClassVar, Literal, cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import Input, Static

from jinnverse_tui import skeletons
from jinnverse_tui.api import ApiError, ConflictError, EntryFull, LoreEntry, UnreachableError
from jinnverse_tui.confirm import ConfirmScreen
from jinnverse_tui.conflict import ConflictScreen
from jinnverse_tui.editor import editor_name
from jinnverse_tui.hairline import Hairline
from jinnverse_tui.legend import Hint
from jinnverse_tui.listing import Rows
from jinnverse_tui.palette import PaletteCommand
from jinnverse_tui.status import Kind
from jinnverse_tui.textfmt import count, pad
from jinnverse_tui.theme import SELECTION
from jinnverse_tui.view import View

Mode = Literal["list", "naming", "keys-new", "keys", "renaming"]
NEEDS_A_KEY = "An entry needs at least one key: nothing would bring it in."


def parse_keys(line: str) -> list[str]:
    """The keys as typed on one line — ``jax, bartender, the brewery`` — split on commas,
    trimmed, lowercased, blanks and repeats dropped. The API keeps them the same way."""
    seen: dict[str, None] = {}
    for piece in line.split(","):
        key = " ".join(piece.casefold().split())
        if key:
            seen.setdefault(key, None)
    return list(seen)


def keys_line(keys: Sequence[str]) -> str:
    return ", ".join(keys)


def keys_note(keys: Sequence[str]) -> str:
    """The line under an entry's name: its keys, or that it has none."""
    return " · ".join(keys) if keys else "no keys — never sent"


@dataclass(slots=True)
class Pending:
    """What ``N`` has gathered so far, one question at a time, before anything is saved."""

    name: str


class LoreScreen(View):
    TITLE = "Lore"
    HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("↑↓", "Entry"),
        Hint("Enter", "Edit"),
        Hint("N", "New"),
        Hint("K", "Keys"),
        Hint("F2", "Rename"),
        Hint("Del", "Remove"),
        Hint("PgUp/PgDn", "Read"),
        Hint("Esc", "Back"),
    )
    NAMING_HINTS: ClassVar[tuple[Hint, ...]] = (Hint("Enter", "Go on"), Hint("Esc", "Cancel"))
    KEYS_HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("Enter", "Save the keys"),
        Hint("Esc", "Cancel"),
    )
    RENAMING_HINTS: ClassVar[tuple[Hint, ...]] = (Hint("Enter", "Rename"), Hint("Esc", "Cancel"))
    AUTO_FOCUS: ClassVar[str | None] = ""
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", "Up", show=False),
        Binding("down", "move(1)", "Down", show=False),
        Binding("home", "first", "First", show=False),
        Binding("end", "last", "Last", show=False),
        Binding("pageup", "page(-1)", "Read up", show=False),
        Binding("pagedown", "page(1)", "Read down", show=False),
        Binding("n,N", "new", "New", show=False),
        Binding("enter", "edit", "Edit", show=False),
        Binding("k,K", "keys", "Keys", show=False),
        Binding("f2", "rename", "Rename", show=False),
        Binding("delete", "remove", "Remove", show=False),
        Binding("r,R,ctrl+r", "refresh", "Refresh", show=False),
    ]

    DEFAULT_CSS = """
    LoreScreen #split { height: 1fr; }
    LoreScreen #pane { width: 30%; min-width: 16; height: 1fr; background: $surface; }
    LoreScreen #pane Input { background: $surface; }
    LoreScreen #text { width: 1fr; height: 1fr; padding: 0 1; }
    LoreScreen #text VerticalScroll { height: 1fr; }
    LoreScreen .caption { color: $muted; height: 1; }
    LoreScreen #keys { color: $accent; height: auto; }
    LoreScreen .prose { color: $muted; }
    """

    def __init__(self, character: EntryFull) -> None:
        super().__init__()
        self.character = character
        self._mode: Mode = "list"
        self._pending: Pending | None = None

    # -- the frame ------------------------------------------------------------------------------

    def hints(self) -> tuple[Hint, ...]:
        if self._mode == "naming":
            return self.NAMING_HINTS
        if self._mode in ("keys", "keys-new"):
            return self.KEYS_HINTS
        if self._mode == "renaming":
            return self.RENAMING_HINTS
        return self.HINTS

    def summary(self) -> str | None:
        return f"{self.character.name} · {count(len(self.rows.items), 'entry', 'entries')}"

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
            PaletteCommand("New entry", "its name, its keys, then the text", self.action_new),
            PaletteCommand("Edit the keys", "the words that bring it in", self.action_keys),
            PaletteCommand("Rename the entry", "a handle, never sent", self.action_rename),
            PaletteCommand("Remove the entry", "asks first", self.action_remove),
        ]

    def body(self) -> ComposeResult:
        with Horizontal(id="split"):
            with Vertical(id="pane"):
                yield Input(placeholder="name…", id="field", compact=True)
                yield Rows[LoreEntry](self._row, empty="", id="list")
            with Vertical(id="text"):
                yield Static("", classes="caption", id="caption")
                yield Static("", id="keys")
                yield Hairline()
                with VerticalScroll():
                    yield Static("", classes="prose", id="prose")

    def on_mount(self) -> None:
        self.query_one("#field", Input).display = False
        self.run_worker(partial(self._load, True), exclusive=True)

    @property
    def rows(self) -> Rows[LoreEntry]:
        return cast("Rows[LoreEntry]", self.query_one("#list", Rows))

    @property
    def selected(self) -> LoreEntry | None:
        return self.rows.selected

    # -- loading --------------------------------------------------------------------------------

    async def _load(self, announce: bool, *, select: uuid.UUID | None = None) -> None:
        listed = await self.jinnverse.call(
            "Reading the lore", self.jinnverse.api.lore(self.character.id)
        )
        if listed is None:
            return
        self.rows.rows_per_item = 2
        self.rows.set_items(
            listed, empty=f"No lore yet: '{self.character.name}' is sent whole. N starts an entry."
        )
        if select is not None:
            index = next((i for i, e in enumerate(listed) if e.id == select), -1)
            if index >= 0:
                self.rows.select(index)
        self.refresh_summary()
        self.refresh_hints()
        self._show_text()
        if announce:
            self.status(
                f"{count(len(listed), 'entry', 'entries')} of '{self.character.name}', in the "
                "order they were made.",
                Kind.SUCCESS,
            )

    def _row(self, entry: LoreEntry, selected: bool, width: int) -> Content:
        """Two rows: the name, then its keys under it, muted."""
        name = Content(pad(f"  {entry.name}", width)).markup
        line = Content(pad(f"  {keys_note(entry.keys)}", width)).markup
        if selected:
            return Content.from_markup(f"{SELECTION}{name}[/]\n{SELECTION}{line}[/]")
        return Content.from_markup(f"{name}\n[$muted]{line}[/]")

    def _show_text(self) -> None:
        entry = self.selected
        caption = self.query_one("#caption", Static)
        keys = self.query_one("#keys", Static)
        prose = self.query_one("#prose", Static)
        if entry is None:
            caption.update("")
            keys.update("")
            prose.update("")
            return
        caption.update(f"{entry.name}   ·   version {entry.version}   ·   sent while in scene")
        keys.update(f"keys: {keys_line(entry.keys)}" if entry.keys else "no keys — never sent")
        prose.update(entry.text)
        self.query_one(VerticalScroll).scroll_home(animate=False)

    @on(Rows.Selected)
    def _selection_moved(self) -> None:
        self._show_text()

    @on(Rows.Opened)
    def _row_opened(self) -> None:
        self.action_edit()

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

    def action_refresh(self) -> None:
        self.run_worker(partial(self._load, True), exclusive=True)

    def action_back(self) -> None:
        if self._mode != "list":
            self._pending = None
            self._leave_field()
            self.status("Cancelled.")
            return
        self.jinnverse.go_back()

    # -- the one-line questions ----------------------------------------------------------------

    def _open_field(self, mode: Mode, value: str, placeholder: str) -> None:
        self._mode = mode
        field = self.query_one("#field", Input)
        field.value = value
        field.placeholder = placeholder
        field.display = True
        field.focus()
        self.refresh_hints()

    def _leave_field(self) -> None:
        self._mode = "list"
        field = self.query_one("#field", Input)
        field.display = False
        field.value = ""
        self.set_focus(None)
        self.refresh_hints()

    def action_new(self) -> None:
        if self._mode != "list":
            return
        self._open_field("naming", "", "new entry: its name (a handle, never sent)")

    def action_keys(self) -> None:
        entry = self.selected
        if self._mode == "list" and entry is not None:
            self._open_field("keys", keys_line(entry.keys), "keys, comma-separated")

    def action_rename(self) -> None:
        entry = self.selected
        if self._mode == "list" and entry is not None:
            self._open_field("renaming", entry.name, "new name")

    @on(Input.Submitted, "#field")
    def _submitted(self, event: Input.Submitted) -> None:
        answer = event.value.strip()
        mode = self._mode
        entry = self.selected
        self._leave_field()
        if mode == "naming":
            if not answer:
                self.status("An entry needs a name.", Kind.WARNING)
                return
            self._pending = Pending(answer)
            self._open_field("keys-new", "", "its keys, comma-separated: jax, bartender")
            return
        if mode == "keys-new":
            pending = self._pending
            self._pending = None
            keys = parse_keys(answer)
            if pending is None:
                return
            if not keys:
                self.status(NEEDS_A_KEY, Kind.WARNING)
                return
            self.run_worker(partial(self._create, pending, keys), exclusive=True)
            return
        if entry is None:
            return
        if mode == "keys":
            keys = parse_keys(answer)
            if not keys:
                self.status(NEEDS_A_KEY, Kind.WARNING)
                return
            if keys == entry.keys:
                self.status("Those are already its keys.")
                return
            self.run_worker(partial(self._save_keys, entry, keys), exclusive=True)
        elif mode == "renaming":
            if not answer:
                self.status("An entry needs a name.", Kind.WARNING)
                return
            if answer == entry.name:
                self.status("That is already its name.")
                return
            self.run_worker(partial(self._rename, entry, answer), exclusive=True)

    # -- creating, editing, saving --------------------------------------------------------------

    async def _create(self, pending: Pending, keys: list[str]) -> None:
        """The entry with its name and keys, then its text in the editor from the skeleton."""
        created = await self.jinnverse.call(
            "Creating",
            self.jinnverse.api.create_lore(self.character.id, pending.name, keys, skeletons.LORE),
        )
        if created is None:
            return
        await self._load(False, select=created.id)
        if await self._edit(created) is None:
            self.status(f"'{created.name}' is saved with its skeleton for a text: Enter writes it.")

    def action_edit(self) -> None:
        entry = self.selected
        if self._mode != "list" or entry is None:
            return
        self.run_worker(partial(self._edit, entry), exclusive=True)

    async def _edit(self, entry: LoreEntry) -> LoreEntry | None:
        """Hands the text to the reader's editor and saves what comes back over the version the
        editor started from; the entry as saved, or None when nothing was."""
        self.status(f"Waiting for {editor_name()} — save and close to come back.")
        after = self.jinnverse.editor(self.jinnverse, entry.text, "-lore.txt")
        if after is None or after.strip() == entry.text.strip():
            self.status("Nothing changed.")
            return None
        saved = await self._save(entry, text=after.rstrip() + "\n")
        if saved is not None:
            await self._load(False, select=saved.id)
            self.status(
                f"Saved. '{saved.name}' is sent from the next turn its keys are in the scene.",
                Kind.SUCCESS,
            )
        return saved

    async def _save_keys(self, entry: LoreEntry, keys: list[str]) -> None:
        saved = await self._save(entry, keys=keys)
        if saved is not None:
            await self._load(False, select=saved.id)
            self.status(f"Keys saved: {keys_line(saved.keys)}.", Kind.SUCCESS)

    async def _rename(self, entry: LoreEntry, name: str) -> None:
        saved = await self._save(entry, name=name)
        if saved is not None:
            await self._load(False, select=saved.id)
            self.status(f'Renamed to "{saved.name}".', Kind.SUCCESS)

    async def _save(
        self,
        entry: LoreEntry,
        *,
        name: str | None = None,
        keys: Sequence[str] | None = None,
        text: str | None = None,
    ) -> LoreEntry | None:
        """A save over the entry's version; a conflict opens the screen that shows the server's
        text, and Enter there saves the same change over it."""
        api = self.jinnverse.api
        line = self.status_line
        line.busy("Saving")
        try:
            return await api.save_lore(
                self.character.id, entry.id, entry.version, name=name, keys=keys, text=text
            )
        except ConflictError as conflict:
            if not isinstance(conflict.current, LoreEntry):
                raise  # a card's conflict cannot come from a lore save

            async def over(theirs: LoreEntry) -> None:
                saved = await api.save_lore(
                    self.character.id, entry.id, theirs.version, name=name, keys=keys, text=text
                )
                await self._load(False, select=saved.id)
                self.status(f"Saved over version {theirs.version}.", Kind.SUCCESS)

            self.jinnverse.push_screen(ConflictScreen(conflict.detail, conflict.current, over))
        except ApiError as refused:
            self.status(refused.detail, Kind.ERROR)
        except UnreachableError:
            self.jinnverse.lost("The server stopped answering while saving.")
        finally:
            line.idle()
        return None

    # -- removing -------------------------------------------------------------------------------

    def action_remove(self) -> None:
        entry = self.selected
        if self._mode != "list" or entry is None:
            return

        async def remove() -> None:
            await self.jinnverse.api.delete_lore(self.character.id, entry.id)
            await self._load(False)
            self.status(f"Removed '{entry.name}'.", Kind.SUCCESS)

        self.jinnverse.push_screen(
            ConfirmScreen(
                "Remove",
                f'Delete the entry "{entry.name}"?',
                (
                    "Its history stays; the entry goes, and no turn sends it again.",
                    "This cannot be undone.",
                ),
                "Delete",
                remove,
            )
        )
