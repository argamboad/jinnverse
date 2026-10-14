"""Building a persona from pieces (#157): a voice, one pick per slot, a preview, a name.

Slots down the left, the pool of the selected slot on the right, the persona as it will read
underneath. ``Space`` picks a piece (or takes it back), ``N`` writes a new one into the slot
and keeps it in the pool, ``V`` changes the voice, ``R`` picks one at random, ``Ctrl+S`` names
the persona and makes it. The server joins the pick into the persona's format
(``src/lustjinn/persona_pieces.py``); this screen only chooses and shows what it answers.

The persona that comes out is an ordinary library persona: the text is copied into it, so
editing a piece later changes nothing already made. The screen that opened this one is told
which persona was made and does what it needs (the library selects it, the new-story form
picks it).

.NET readers: a master-detail form with a live preview, the preview being a call to the API on
every change rather than a model of the join kept here, so the client cannot disagree with the
server about what a persona looks like.
"""

from __future__ import annotations

import random
import uuid
from collections.abc import Awaitable, Callable
from functools import partial
from typing import ClassVar, Literal, cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.content import Content
from textual.widgets import Input, Static

from lustjinn_tui import skeletons
from lustjinn_tui.api import ApiError, Built, Piece, Slot, UnreachableError, Voice
from lustjinn_tui.confirm import ConfirmScreen
from lustjinn_tui.editor import editor_name
from lustjinn_tui.hairline import Hairline
from lustjinn_tui.legend import Hint
from lustjinn_tui.listing import Rows
from lustjinn_tui.palette import PaletteCommand
from lustjinn_tui.status import Kind
from lustjinn_tui.textfmt import count, pad
from lustjinn_tui.theme import SELECTION
from lustjinn_tui.view import View

VOICES: tuple[Voice, ...] = ("he", "she", "they")
Pane = Literal["slots", "pieces"]
Mode = Literal["browse", "label", "full", "short", "name"]
OnBuilt = Callable[[Built], Awaitable[None]]

choose = random.choice
"""How a random piece is picked; the tests hand in a fixed one."""

NEEDED: dict[str, str] = {"name": "a name", "look": "an identity and look"}
"""The slots a persona is not made without, as the screens ask (the API itself only needs one
piece): every persona opens with its name and its look, and a piece that writes the name needs a
name piece. Every other slot is optional."""


class PersonaBuilderScreen(View):
    TITLE = "Build a persona"
    HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("←→", "Slots/pieces"),
        Hint("Space", "Pick"),
        Hint("N", "New piece"),
        Hint("E", "Edit piece"),
        Hint("V", "Voice"),
        Hint("R", "Random"),
        Hint("Ctrl+S", "Make it"),
        Hint("Esc", "Back"),
    )
    TYPING_HINTS: ClassVar[tuple[Hint, ...]] = (Hint("Enter", "Go on"), Hint("Esc", "Cancel"))
    AUTO_FOCUS: ClassVar[str | None] = ""
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", "Up", show=False),
        Binding("down", "move(1)", "Down", show=False),
        Binding("home", "first", "First", show=False),
        Binding("end", "last", "Last", show=False),
        Binding("left", "pane('slots')", "Slots", show=False),
        Binding("right,tab", "pane('pieces')", "Pieces", show=False),
        Binding("space,enter", "pick", "Pick", show=False),
        Binding("n,N", "new_piece", "New piece", show=False),
        Binding("e,E", "edit_piece", "Edit the piece", show=False),
        Binding("v,V", "voice", "Voice", show=False),
        Binding("r,R", "random", "Random", show=False),
        Binding("pageup", "page(-1)", "Read up", show=False),
        Binding("pagedown", "page(1)", "Read down", show=False),
        Binding("ctrl+s,ctrl+enter", "make", "Make it", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    PersonaBuilderScreen #caption { height: 1; padding: 0 1; }
    PersonaBuilderScreen #split { height: 3fr; }
    PersonaBuilderScreen #slots { width: 40%; min-width: 24; padding: 0 1; }
    PersonaBuilderScreen #pieces { width: 1fr; padding: 0 1; }
    PersonaBuilderScreen .pane-title { color: $muted; height: 1; }
    PersonaBuilderScreen .pane-title.active { color: $primary; text-style: bold; }
    PersonaBuilderScreen #field { margin: 0 1; }
    PersonaBuilderScreen #preview { height: 2fr; padding: 0 1; }
    PersonaBuilderScreen #preview VerticalScroll { height: 1fr; }
    PersonaBuilderScreen #preview-text { color: $muted; }
    """

    def __init__(self, on_built: OnBuilt) -> None:
        super().__init__()
        self._on_built = on_built
        self.voice: Voice = "he"
        self.slots: list[Slot] = []
        self.pool: dict[str, list[Piece]] = {}
        self.picks: dict[str, list[uuid.UUID]] = {}
        self.pane: Pane = "slots"
        self._mode: Mode = "browse"
        self._label = ""
        self._full = ""
        self._suggested: str | None = None
        self._preview_text = ""

    # -- the frame ------------------------------------------------------------------------------

    def hints(self) -> tuple[Hint, ...]:
        return self.HINTS if self._mode == "browse" else self.TYPING_HINTS

    def summary(self) -> str | None:
        return count(sum(len(ids) for ids in self.picks.values()), "piece") + " picked"

    def commands(self) -> list[PaletteCommand]:
        return [
            PaletteCommand("Make the persona", "from the pieces picked", self.action_make),
            PaletteCommand("New piece", "written into the selected slot", self.action_new_piece),
            PaletteCommand("Change the voice", "he, she or they", self.action_voice),
            PaletteCommand("Pick at random", "one piece for the selected slot", self.action_random),
        ]

    def body(self) -> ComposeResult:
        yield Static("", id="caption")
        yield Hairline()
        with Horizontal(id="split"):
            with Vertical(id="slots"):
                yield Static("Slots", classes="pane-title", id="slots-title")
                yield Rows[Slot](self._slot_row, empty="(reading the slots…)", id="slot-list")
            with Vertical(id="pieces"):
                yield Static("Pieces", classes="pane-title", id="pieces-title")
                yield Rows[Piece](self._piece_row, empty="", id="piece-list")
        yield Input(placeholder="", id="field", compact=True)
        yield Hairline()
        with Vertical(id="preview"), VerticalScroll():
            yield Static("", id="preview-text")

    def on_screen_resume(self) -> None:
        super().on_screen_resume()
        if self.slots:  # back from the library, where a piece may have changed
            self.run_worker(self._load, exclusive=True)

    def on_mount(self) -> None:
        self.query_one("#field", Input).display = False
        self._show_caption()
        self._show_panes()
        self.run_worker(self._load, exclusive=True)

    @property
    def slot_rows(self) -> Rows[Slot]:
        return cast("Rows[Slot]", self.query_one("#slot-list", Rows))

    @property
    def piece_rows(self) -> Rows[Piece]:
        return cast("Rows[Piece]", self.query_one("#piece-list", Rows))

    @property
    def slot(self) -> Slot | None:
        return self.slot_rows.selected

    @property
    def piece(self) -> Piece | None:
        return self.piece_rows.selected

    def _active(self) -> Rows[Slot] | Rows[Piece]:
        return self.slot_rows if self.pane == "slots" else self.piece_rows

    # -- loading and drawing --------------------------------------------------------------------

    async def _load(self) -> None:
        api = self.lustjinn.api
        if not self.slots:
            slots = await self.lustjinn.call("Reading the slots", api.piece_slots())
            if slots is None:
                return
            self.slots = slots
            self.slot_rows.set_items(slots)
        pieces = await self.lustjinn.call("Reading the pieces", api.pieces(voice=self.voice))
        if pieces is None:
            return
        self.pool = {}
        for piece in pieces:
            self.pool.setdefault(piece.slot, []).append(piece)
        known = {piece.id for piece in pieces}
        self.picks = {
            slot: [i for i in ids if i in known]
            for slot, ids in self.picks.items()
            if any(i in known for i in ids)
        }
        self._show_pool()
        self._show_caption()
        self.refresh_summary()
        await self._preview()

    def _show_caption(self) -> None:
        self.query_one("#caption", Static).update(
            Content.from_markup(
                f"[$muted]Voice[/]  {Content(self.voice).markup}   "
                "[$muted]— pieces written in it, or in none, are offered[/]"
            )
        )

    def _show_panes(self) -> None:
        for name in ("slots", "pieces"):
            self.query_one(f"#{name}-title", Static).set_class(self.pane == name, "active")
        self.slot_rows.refresh()
        self.piece_rows.refresh()

    def _show_pool(self) -> None:
        slot = self.slot
        pieces = self.pool.get(slot.key, []) if slot is not None else []
        empty = "Nothing here yet — N writes the first one." if slot is not None else ""
        self.piece_rows.set_items(pieces, empty=empty)
        self.query_one("#pieces-title", Static).update(
            f"Pieces — {slot.label}" if slot is not None else "Pieces"
        )
        self.slot_rows.refresh()

    def _slot_row(self, slot: Slot, selected: bool, width: int) -> Content:
        picked = self.picks.get(slot.key, [])
        mark = "✓ " if picked else "  "
        names = ", ".join(self.name_of(slot.key, i) for i in picked)
        if not picked and slot.key in NEEDED:
            names = "needed"
        line = Content(pad(f"{mark}{slot.label}", min(width, 32)) + names).markup
        return self._styled(line, selected and self.pane == "slots", selected)

    def _piece_row(self, piece: Piece, selected: bool, width: int) -> Content:
        picked = piece.id in self.picks.get(piece.slot, [])
        voice = "" if piece.voice == "he" or piece.voice == self.voice else f"  ({piece.voice})"
        line = Content(pad(f"{'✓ ' if picked else '  '}{piece.name}{voice}", width)).markup
        return self._styled(line, selected and self.pane == "pieces", selected)

    @staticmethod
    def _styled(line: str, active: bool, selected: bool) -> Content:
        if active:
            return Content.from_markup(f"{SELECTION}{line}[/]")
        return Content.from_markup(f"[bold]{line}[/]" if selected else line)

    def name_of(self, slot: str, piece_id: uuid.UUID) -> str:
        found = next((p for p in self.pool.get(slot, []) if p.id == piece_id), None)
        return found.name if found is not None else "?"

    async def _preview(self) -> None:
        """The persona as the server joins it; a pick it cannot join says why, in place of it."""
        text = ""
        self._suggested = None
        if any(self.picks.values()):
            try:
                preview = await self.lustjinn.api.preview_persona(self.voice, self.picks)
            except ApiError as refused:
                text = f"({refused.detail})"
            except UnreachableError:
                self.lustjinn.lost("The server stopped answering.")
                return
            else:
                text = preview.text
                self._suggested = preview.name
        else:
            text = "(pick a piece to see the persona)"
        self._preview_text = text
        self.query_one("#preview-text", Static).update(text)
        self.query_one(VerticalScroll).scroll_home(animate=False)

    # -- moving ---------------------------------------------------------------------------------

    def action_move(self, delta: int) -> None:
        if self._mode != "browse":
            return
        self._active().move(delta)

    def action_first(self) -> None:
        if self._mode == "browse":
            self._active().first()

    def action_last(self) -> None:
        if self._mode == "browse":
            self._active().last()

    def action_pane(self, pane: Pane) -> None:
        if self._mode != "browse":
            return
        self.pane = pane
        self._show_panes()

    def action_page(self, direction: int) -> None:
        scroller = self.query_one(VerticalScroll)
        if direction > 0:
            scroller.scroll_page_down(animate=False)
        else:
            scroller.scroll_page_up(animate=False)

    @on(Rows.Selected, "#slot-list")
    def _slot_moved(self) -> None:
        self._show_pool()

    # -- picking --------------------------------------------------------------------------------

    def action_pick(self) -> None:
        if self._mode != "browse":
            return
        if self.pane == "slots":
            self.action_pane("pieces")
            return
        piece = self.piece
        if piece is None:
            return
        picked = self.picks.setdefault(piece.slot, [])
        if piece.id in picked:
            picked.remove(piece.id)
        else:
            picked.append(piece.id)
        if not picked:
            del self.picks[piece.slot]
        self._after_picking()

    def action_random(self) -> None:
        slot = self.slot
        if self._mode != "browse" or slot is None:
            return
        pieces = self.pool.get(slot.key, [])
        if not pieces:
            self.status(f"There is no {slot.label.lower()} piece to pick yet.", Kind.WARNING)
            return
        self.picks[slot.key] = [choose(pieces).id]
        self._after_picking()

    def _after_picking(self) -> None:
        self.slot_rows.refresh()
        self.piece_rows.refresh()
        self.refresh_summary()
        self.run_worker(self._preview, exclusive=True)

    def action_voice(self) -> None:
        if self._mode != "browse":
            return
        self.voice = VOICES[(VOICES.index(self.voice) + 1) % len(VOICES)]
        self.status(
            f"Voice: {self.voice}. Pieces written in another voice are put back.", Kind.INFO
        )
        self.run_worker(self._load, exclusive=True)

    # -- a new piece ----------------------------------------------------------------------------

    def _ask(self, mode: Mode, placeholder: str, value: str = "") -> None:
        self._mode = mode
        field = self.query_one("#field", Input)
        field.value = value
        field.placeholder = placeholder
        field.display = True
        field.focus()
        self.refresh_hints()

    def _stop_asking(self) -> None:
        self._mode = "browse"
        field = self.query_one("#field", Input)
        field.display = False
        field.value = ""
        self.set_focus(None)
        self.refresh_hints()

    def action_new_piece(self) -> None:
        slot = self.slot
        if self._mode != "browse" or slot is None:
            return
        if slot.key == "name":
            self._ask("full", "the full name, as it opens the persona")
        else:
            self._ask("label", f"a name for this {slot.label.lower()} piece, for the picker")

    def action_edit_piece(self) -> None:
        """The piece under the cursor, in the library's Pieces shelf; Esc comes back here."""
        from lustjinn_tui.library import LibraryScreen  # here: the library opens this screen

        piece = self.piece
        if self._mode != "browse" or self.pane != "pieces" or piece is None:
            if self._mode == "browse":
                self.status("Move to a piece first (→), then E edits it.", Kind.WARNING)
            return
        self.lustjinn.push_screen(LibraryScreen("pieces", select=piece.id))

    @on(Input.Submitted, "#field")
    def _answered(self, event: Input.Submitted) -> None:
        answer = event.value.strip()
        mode = self._mode
        if mode == "name":
            self._stop_asking()
            self.run_worker(partial(self._make, answer or None), exclusive=True)
            return
        if not answer:
            self._stop_asking()
            self.status("Nothing was written.", Kind.WARNING)
            return
        if mode == "label":
            self._stop_asking()
            self.run_worker(partial(self._write_piece, answer), exclusive=True)
        elif mode == "full":
            self._full = answer
            self._ask("short", "the short name the text uses after the first mention")
        elif mode == "short":
            self._stop_asking()
            self.run_worker(partial(self._add_name, self._full, answer), exclusive=True)

    async def _write_piece(self, label: str) -> None:
        slot = self.slot
        if slot is None:
            return
        before = skeletons.piece(slot.label.lower(), self.voice)
        self.status(f"Waiting for {editor_name()} — save and close to come back.")
        after = self.lustjinn.editor(self.lustjinn, before, "-piece.txt")
        if after is None or after.strip() == before.strip() or not after.strip():
            self.status("Nothing was written.")
            return
        await self._add_piece(slot.key, label, after.strip())

    async def _add_name(self, full: str, short: str) -> None:
        await self._add_piece("name", full, full, short)

    async def _add_piece(self, slot: str, name: str, text: str, short: str | None = None) -> None:
        created = await self.lustjinn.call(
            "Saving the piece",
            self.lustjinn.api.create_piece(slot, self.voice, name, text, short),
        )
        if created is None:
            return
        self.picks.setdefault(slot, []).append(created.id)
        await self._load()
        self.status(f"'{created.name}' is in the pool, and picked.", Kind.SUCCESS)

    # -- making the persona ---------------------------------------------------------------------

    def action_make(self) -> None:
        if self._mode != "browse":
            return
        missing = [wanted for slot, wanted in NEEDED.items() if not self.picks.get(slot)]
        if missing:
            first = "them" if len(missing) > 1 else "it"
            self.status(
                f"A persona needs {' and '.join(missing)}: pick {first} first.", Kind.WARNING
            )
            return
        self._ask("name", "the persona's name in the library", self._suggested or "")

    async def _make(self, name: str | None) -> None:
        built = await self.lustjinn.call(
            "Making the persona", self.lustjinn.api.build_persona(self.voice, self.picks, name)
        )
        if built is None:
            return
        self.lustjinn.pop_screen()
        await self._on_built(built)

    # -- leaving --------------------------------------------------------------------------------

    def action_back(self) -> None:
        if self._mode != "browse":
            self._stop_asking()
            self.status("Cancelled.")
            return
        if not any(self.picks.values()):
            self.lustjinn.pop_screen()
            return

        async def throw_away() -> None:
            self.lustjinn.pop_screen()

        self.lustjinn.push_screen(
            ConfirmScreen(
                "Cancel",
                "Throw away this pick?",
                ("No persona has been made yet; the pieces stay in the pool.",),
                "Throw away",
                throw_away,
            )
        )
