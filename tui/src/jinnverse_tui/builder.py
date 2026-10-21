"""Building a persona from pieces (#157): a voice, one pick per slot, a preview, a name.

Slots down the left, the pool of the selected slot on the right, the persona as it will read
underneath. Slots that write one paragraph together (home, vehicle, pets) share a row, as on the
web; each piece's row says what it says, and the highlighted one is read whole under the list.
``Space`` picks a piece (or takes it back), ``N`` writes a new one into the slot (a shared row
asks which slot first) and keeps it in the pool, ``V`` changes the voice, ``R`` picks at random
for the row, ``F`` fills every slot still empty at random, ``Ctrl+S`` names the persona and
makes it. The caption counts the
slots picked and the needed ones still empty, as the web's builder does. The server joins the
pick into the persona's format (``src/jinnverse/persona_pieces.py``); this screen only chooses
and shows what it answers.

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
from jinnverse_tui.api import ApiError, Built, Piece, Slot, UnreachableError, Voice
from jinnverse_tui.confirm import ConfirmScreen
from jinnverse_tui.editor import editor_name
from jinnverse_tui.hairline import Hairline
from jinnverse_tui.legend import Hint
from jinnverse_tui.listing import Rows
from jinnverse_tui.palette import PaletteCommand
from jinnverse_tui.status import Kind
from jinnverse_tui.textfmt import count, pad
from jinnverse_tui.theme import SELECTION
from jinnverse_tui.view import View

VOICES: tuple[Voice, ...] = ("he", "she", "they")
Pane = Literal["slots", "pieces"]
Mode = Literal["browse", "label", "slot-label", "full", "short", "name"]
OnBuilt = Callable[[Built], Awaitable[None]]

choose = random.choice
"""How a random piece is picked; the tests hand in a fixed one."""

NEEDED: dict[str, str] = {"name": "a name", "look": "an identity and look"}
"""The slots a persona is not made without, as the screens ask (the API itself only needs one
piece): every persona opens with its name and its look, and a piece that writes the name needs a
name piece. Every other slot is optional."""


@dataclass(frozen=True, slots=True)
class SlotGroup:
    """A row of the slot list: one slot, or the slots that write one paragraph together (home,
    vehicle and pets), as the web's checklist groups them."""

    key: str
    label: str
    slots: tuple[Slot, ...]

    @property
    def shared(self) -> bool:
        return len(self.slots) > 1


def group_slots(slots: list[Slot]) -> list[SlotGroup]:
    """The slots in order, those sharing a paragraph in one row (the web's ``groupSlots``)."""
    groups: list[SlotGroup] = []
    for slot in slots:
        last = groups[-1] if groups else None
        if slot.paragraph is not None and last and last.slots[0].paragraph == slot.paragraph:
            groups[-1] = SlotGroup(
                f"{last.key}+{slot.key}", f"{last.label} · {slot.label}", (*last.slots, slot)
            )
        else:
            groups.append(SlotGroup(slot.key, slot.label, (slot,)))
    return groups


def blurb(piece: Piece) -> str:
    """What a piece's row says under its name: its description, or the start of its text."""
    note = (piece.description or "").strip()
    return note or next((line.strip() for line in piece.text.splitlines() if line.strip()), "")


def builder_line(slots: list[Slot], picks: dict[str, list[uuid.UUID]]) -> str:
    """How far the pick has got, in the web builder's words: ``3 of 12 slots picked · 1 needed``."""
    picked = sum(1 for slot in slots if picks.get(slot.key))
    needed = sum(1 for slot in NEEDED if not picks.get(slot))
    return f"{picked} of {len(slots)} slots picked" + (f" · {needed} needed" if needed else "")


class PersonaBuilderScreen(View):
    TITLE = "Build a persona"
    HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("←→", "Slots/pieces"),
        Hint("Space", "Pick"),
        Hint("N", "New piece"),
        Hint("E", "Edit piece"),
        Hint("V", "Voice"),
        Hint("R", "Random"),
        Hint("F", "Fill the rest"),
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
        Binding("f,F", "fill", "Fill the rest", show=False),
        Binding("pageup", "page(-1)", "Read up", show=False),
        Binding("pagedown", "page(1)", "Read down", show=False),
        Binding("ctrl+s,ctrl+enter", "make", "Make it", show=False, priority=True),
    ]

    DEFAULT_CSS = """
    PersonaBuilderScreen #caption { height: 1; padding: 0 1; }
    PersonaBuilderScreen #split { height: 3fr; }
    PersonaBuilderScreen #slots { width: 40%; min-width: 24; padding: 0 1; }
    PersonaBuilderScreen #pieces { width: 1fr; padding: 0 1; }
    PersonaBuilderScreen #piece-text { color: $muted; height: auto; max-height: 6; }
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
        self._writing: Slot | None = None
        """The slot a new piece is being written for."""
        self._suggested: str | None = None
        self._preview_text = ""

    # -- the frame ------------------------------------------------------------------------------

    def hints(self) -> tuple[Hint, ...]:
        return self.HINTS if self._mode == "browse" else self.TYPING_HINTS

    def summary(self) -> str | None:
        return builder_line(self.slots, self.picks) if self.slots else None

    def commands(self) -> list[PaletteCommand]:
        return [
            PaletteCommand("Make the persona", "from the pieces picked", self.action_make),
            PaletteCommand("New piece", "written into the selected slot", self.action_new_piece),
            PaletteCommand("Change the voice", "he, she or they", self.action_voice),
            PaletteCommand("Pick at random", "one piece for the selected slot", self.action_random),
            PaletteCommand(
                "Fill the rest at random", "a piece for every slot still empty", self.action_fill
            ),
        ]

    def body(self) -> ComposeResult:
        yield Static("", id="caption")
        yield Hairline()
        with Horizontal(id="split"):
            with Vertical(id="slots"):
                yield Static("Slots", classes="pane-title", id="slots-title")
                yield Rows[SlotGroup](self._slot_row, empty="(reading the slots…)", id="slot-list")
            with Vertical(id="pieces"):
                yield Static("Pieces", classes="pane-title", id="pieces-title")
                yield Rows[Piece](self._piece_row, empty="", id="piece-list")
                yield Static("", id="piece-text")
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
        self.piece_rows.rows_per_item = 2  # the name, then what the piece says
        self._show_caption()
        self._show_panes()
        self.run_worker(self._load, exclusive=True)

    @property
    def slot_rows(self) -> Rows[SlotGroup]:
        return cast("Rows[SlotGroup]", self.query_one("#slot-list", Rows))

    @property
    def piece_rows(self) -> Rows[Piece]:
        return cast("Rows[Piece]", self.query_one("#piece-list", Rows))

    @property
    def group(self) -> SlotGroup | None:
        """The selected row of the slot list: one slot, or the slots sharing a paragraph."""
        return self.slot_rows.selected

    @property
    def piece(self) -> Piece | None:
        return self.piece_rows.selected

    def _active(self) -> Rows[SlotGroup] | Rows[Piece]:
        return self.slot_rows if self.pane == "slots" else self.piece_rows

    # -- loading and drawing --------------------------------------------------------------------

    async def _load(self) -> None:
        api = self.jinnverse.api
        if not self.slots:
            slots = await self.jinnverse.call("Reading the slots", api.piece_slots())
            if slots is None:
                return
            self.slots = slots
            self.slot_rows.set_items(group_slots(slots))
        pieces = await self.jinnverse.call("Reading the pieces", api.pieces(voice=self.voice))
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
        """How far the pick has got, then the voice: on a wide screen the masthead has no room
        for the summary, so the caption carries it."""
        line = builder_line(self.slots, self.picks) if self.slots else ""
        self.query_one("#caption", Static).update(
            Content.from_markup(
                (f"[$accent]{Content(line).markup}[/]   " if line else "")
                + f"[$muted]Voice[/]  {Content(self.voice).markup}   "
                "[$muted]— pieces written in it, or in none, are offered[/]"
            )
        )

    def _show_panes(self) -> None:
        for name in ("slots", "pieces"):
            self.query_one(f"#{name}-title", Static).set_class(self.pane == name, "active")
        self.slot_rows.refresh()
        self.piece_rows.refresh()

    def _show_pool(self) -> None:
        """The pieces of the selected row, slot by slot in a shared row."""
        group = self.group
        pieces = [p for slot in group.slots for p in self.pool.get(slot.key, [])] if group else []
        empty = "Nothing here yet — N writes the first one." if group is not None else ""
        self.piece_rows.set_items(pieces, empty=empty)
        self.query_one("#pieces-title", Static).update(
            f"Pieces — {group.label}" if group is not None else "Pieces"
        )
        self.slot_rows.refresh()
        self._show_piece_text()

    def _show_piece_text(self) -> None:
        """The highlighted piece's whole text under the list, as written ({name}, {short})."""
        piece = self.piece
        self.query_one("#piece-text", Static).update(
            Content(piece.text.strip()) if piece is not None else ""
        )

    def _slot_row(self, group: SlotGroup, selected: bool, width: int) -> Content:
        picked = [(slot.key, i) for slot in group.slots for i in self.picks.get(slot.key, [])]
        mark = "✓ " if picked else "  "
        names = ", ".join(self.name_of(slot, i) for slot, i in picked)
        if not picked and any(slot.key in NEEDED for slot in group.slots):
            names = "needed"
        elif not picked and group.shared:
            names = f"one paragraph, up to {len(group.slots)} pieces"
        line = Content(pad(f"{mark}{group.label}", min(width, 32)) + names).markup
        return self._styled(line, selected and self.pane == "slots", selected)

    def _piece_row(self, piece: Piece, selected: bool, width: int) -> Content:
        """Two rows: the name (and, in a shared row, which slot it writes), then what it says."""
        picked = piece.id in self.picks.get(piece.slot, [])
        voice = "" if piece.voice == "he" or piece.voice == self.voice else f"  ({piece.voice})"
        group = self.group
        where = ""
        if group is not None and group.shared:
            where = next(f"  · {s.label}" for s in group.slots if s.key == piece.slot)
        head = f"{'✓ ' if picked else '  '}{piece.name}{voice}{where}"
        name = Content(pad(head, width)).markup
        under = Content(pad(f"    {blurb(piece)}", width)).markup
        active = selected and self.pane == "pieces"
        if active:
            return Content.from_markup(f"{SELECTION}{name}[/]\n{SELECTION}{under}[/]")
        first = f"[bold]{name}[/]" if selected else name
        return Content.from_markup(f"{first}\n[$muted]{under}[/]")

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
                preview = await self.jinnverse.api.preview_persona(self.voice, self.picks)
            except ApiError as refused:
                text = f"({refused.detail})"
            except UnreachableError:
                self.jinnverse.lost("The server stopped answering.")
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

    @on(Rows.Selected, "#piece-list")
    def _piece_moved(self) -> None:
        self._show_piece_text()

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
        """A piece at random for the selected row: for each of its slots in a shared row, as
        the web's Random does."""
        group = self.group
        if self._mode != "browse" or group is None:
            return
        chosen = False
        for slot in group.slots:
            pieces = self.pool.get(slot.key, [])
            if pieces:
                self.picks[slot.key] = [choose(pieces).id]
                chosen = True
        if not chosen:
            self.status(f"There is no {group.label.lower()} piece to pick yet.", Kind.WARNING)
            return
        self._after_picking()

    def action_fill(self) -> None:
        """A piece at random for every slot still empty, as the web's "Fill the rest at random";
        what is picked stays picked, and a slot with no piece in this voice stays empty."""
        if self._mode != "browse" or not self.slots:
            return
        filled = 0
        for slot in self.slots:
            pieces = self.pool.get(slot.key, [])
            if self.picks.get(slot.key) or not pieces:
                continue
            self.picks[slot.key] = [choose(pieces).id]
            filled += 1
        if not filled:
            self.status("Every slot that has a piece in this voice is picked already.")
            return
        self._after_picking()
        self.status(f"Filled {count(filled, 'empty slot')} at random.", Kind.SUCCESS)

    def _after_picking(self) -> None:
        self.slot_rows.refresh()
        self.piece_rows.refresh()
        self._show_piece_text()
        self._show_caption()
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
        # A suggested persona name is replaced by typing; an offered slot is typed after.
        field.select_on_focus = mode == "name"
        field.cursor_position = len(value)
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
        """A new piece for the selected row. A shared row asks which of its slots first, as
        the library's Pieces shelf does (``vehicle Royal Enfield``), starting from the slot of
        the piece under the cursor."""
        group = self.group
        if self._mode != "browse" or group is None:
            return
        slot = group.slots[0]
        if group.shared:
            piece = self.piece if self.pane == "pieces" else None
            keys = ", ".join(s.key for s in group.slots)
            self._ask(
                "slot-label",
                f"its slot ({keys}), then a name for the picker",
                f"{piece.slot} " if piece is not None else "",
            )
        elif slot.key == "name":
            self._ask("full", "the full name, as it opens the persona")
        else:
            self._writing = slot
            self._ask("label", f"a name for this {slot.label.lower()} piece, for the picker")

    def action_edit_piece(self) -> None:
        """The piece under the cursor, in the library's Pieces shelf; Esc comes back here."""
        from jinnverse_tui.library import LibraryScreen  # here: the library opens this screen

        piece = self.piece
        if self._mode != "browse" or self.pane != "pieces" or piece is None:
            if self._mode == "browse":
                self.status("Move to a piece first (→), then E edits it.", Kind.WARNING)
            return
        self.jinnverse.push_screen(LibraryScreen("pieces", select=piece.id))

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
        if mode == "label" and self._writing is not None:
            self._stop_asking()
            self.run_worker(partial(self._write_piece, self._writing, answer), exclusive=True)
        elif mode == "slot-label":
            self._stop_asking()
            self._slot_and_label(answer)
        elif mode == "full":
            self._full = answer
            self._ask("short", "the short name the text uses after the first mention")
        elif mode == "short":
            self._stop_asking()
            self.run_worker(partial(self._add_name, self._full, answer), exclusive=True)

    def _slot_and_label(self, answer: str) -> None:
        """``slot name`` for a shared row: the slot must be one of the row's."""
        group = self.group
        if group is None:
            return
        word, _, label = answer.partition(" ")
        slot = next((s for s in group.slots if s.key == word.lower()), None)
        if slot is None:
            keys = ", ".join(s.key for s in group.slots)
            self.status(f"Start with one of this row's slots: {keys}.", Kind.WARNING)
            return
        if not label.strip():
            self.status("A piece needs a name.", Kind.WARNING)
            return
        self.run_worker(partial(self._write_piece, slot, label.strip()), exclusive=True)

    async def _write_piece(self, slot: Slot, label: str) -> None:
        before = skeletons.piece(slot.label.lower(), self.voice)
        self.status(f"Waiting for {editor_name()} — save and close to come back.")
        after = self.jinnverse.editor(self.jinnverse, before, "-piece.txt")
        if after is None or after.strip() == before.strip() or not after.strip():
            self.status("Nothing was written.")
            return
        await self._add_piece(slot.key, label, after.strip())

    async def _add_name(self, full: str, short: str) -> None:
        await self._add_piece("name", full, full, short)

    async def _add_piece(self, slot: str, name: str, text: str, short: str | None = None) -> None:
        created = await self.jinnverse.call(
            "Saving the piece",
            self.jinnverse.api.create_piece(slot, self.voice, name, text, short),
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
        built = await self.jinnverse.call(
            "Making the persona", self.jinnverse.api.build_persona(self.voice, self.picks, name)
        )
        if built is None:
            return
        self.jinnverse.pop_screen()
        await self._on_built(built)

    # -- leaving --------------------------------------------------------------------------------

    def action_back(self) -> None:
        if self._mode != "browse":
            self._stop_asking()
            self.status("Cancelled.")
            return
        if not any(self.picks.values()):
            self.jinnverse.pop_screen()
            return

        async def throw_away() -> None:
            self.jinnverse.pop_screen()

        self.jinnverse.push_screen(
            ConfirmScreen(
                "Cancel",
                "Throw away this pick?",
                ("No persona has been made yet; the pieces stay in the pool.",),
                "Throw away",
                throw_away,
            )
        )
