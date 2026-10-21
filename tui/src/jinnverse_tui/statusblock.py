"""A story's status block: the lines its replies open with (the day, the place, each character's
outfit and mood), kept by the app (#169).

One screen is the whole of it, and it is also the quick on/off from the chat: the fields with a
switch each, the shipped starter fields the story does not have yet, the characters that are
always sent, and what each line holds now. Every change is saved the moment it is made, and the
API answers each with the whole block, which is what the list is drawn from.

Keys: ``Space``/``Enter`` switches a field on or off, adds a starter, or edits a value; ``A``
writes a field of your own (``scene: Label`` for a scene line, ``Label = Low, High`` for a list of
words); ``N`` pins a character; ``Del`` deletes a field, unpins a character, or clears a value.

.NET readers: a list screen with an inline editor, like the settings screen, but with no
staging — an ASP.NET page that posts on every click rather than on a Save button.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from typing import ClassVar, Literal, cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.content import Content
from textual.widgets import Input, Static

from jinnverse_tui.api import StatusBlock, StatusField
from jinnverse_tui.confirm import ConfirmScreen
from jinnverse_tui.hairline import Hairline
from jinnverse_tui.legend import Hint
from jinnverse_tui.listing import Rows
from jinnverse_tui.status import Kind
from jinnverse_tui.view import View

RECENT_TURNS = 12
"""A character who wrote a line within this many messages of the newest is in scene; the same
number the API uses when it builds the prompt."""
MOST_CHARACTERS = 12

ItemKind = Literal["field", "starter", "pin", "value"]


@dataclass(frozen=True, slots=True)
class Item:
    """One row of the list."""

    kind: ItemKind
    label: str
    """What the row names: a field's label, a character, or `Peach · Outfit`."""
    icon: str = ""
    note: str = ""
    on: bool = False
    """For a field: whether it is switched on."""
    key: str = ""
    """The field's key, for a field, a starter or a value."""
    who: str = ""
    """The character, for a pin or a value; empty for the scene."""
    value: str = ""


def scope_note(field: StatusField) -> str:
    who = "scene" if field.scope == "scene" else "each character"
    return f"{who} · words" if field.kind == "words" else who


def build_items(block: StatusBlock) -> list[Item]:
    """The rows: fields, then starters, then pins, then what each line holds, scene first."""
    items = [
        Item(
            "field",
            field.label,
            icon=field.icon or "",
            note=scope_note(field),
            on=field.enabled,
            key=field.key,
        )
        for field in sorted(block.fields, key=lambda f: f.position)
    ]
    items += [
        Item(
            "starter",
            starter.label,
            icon=starter.icon or "",
            note=f"{starter.scope} · a starter, not in this story",
            key=starter.key,
        )
        for starter in block.starters
    ]
    items += [Item("pin", name, who=name, note="always sent") for name in block.pins]
    fields = {field.key: field for field in block.fields}
    for value in sorted(
        (v for v in block.values if v.field in fields),
        key=lambda v: (v.who != "", v.who.casefold(), fields[v.field].position),
    ):
        field = fields[value.field]
        items.append(
            Item(
                "value",
                f"{value.who or 'Scene'} · {field.label}",
                icon=field.icon or "",
                note="by hand" if value.by_hand else "",
                key=value.field,
                who=value.who,
                value=value.value,
            )
        )
    return items


def parse_new_field(typed: str) -> tuple[str, str, list[str]] | None:
    """What was typed for a new field: ``Label`` (for each character), ``scene: Label`` (for the
    scene), ``Label = Low, High`` (words from a list). None when there is no label."""
    text = typed.strip()
    scope = "character"
    if text.casefold().startswith("scene:"):
        scope, text = "scene", text[len("scene:") :].strip()
    label, equals, listed = text.partition("=")
    words: list[str] = []
    seen: set[str] = set()
    if equals:
        for part in listed.replace("|", ",").replace(";", ",").split(","):
            word = part.strip()
            if word and word.casefold() not in seen:
                seen.add(word.casefold())
                words.append(word)
    label = label.strip()
    return (label, scope, words) if label else None


def in_scene(block: StatusBlock, newest: int) -> list[str]:
    """The characters to name beside the scene: pinned ones first, then those who wrote a line
    within ``RECENT_TURNS`` of ``newest``, most recent first."""
    keys = {f.key for f in block.fields if f.scope == "character"}
    last: dict[str, tuple[str, int]] = {}
    for value in block.values:
        if not value.who or value.field not in keys:
            continue
        key = value.who.strip().casefold()
        known = last.get(key)
        last[key] = (
            known[0] if known else value.who,
            max(known[1] if known else 0, value.seen or 0),
        )
    pinned = [last[p.strip().casefold()][0] for p in block.pins if p.strip().casefold() in last]
    recent = sorted(
        (
            name
            for name, seen in last.values()
            if name not in pinned and seen >= newest - RECENT_TURNS
        ),
        key=lambda name: (-last[name.strip().casefold()][1], name),
    )
    return [*pinned, *recent][:MOST_CHARACTERS]


def scene_line(block: StatusBlock, newest: int) -> str | None:
    """One line for the conversation's header: the scene's values and who is in it; None when
    there is nothing to say."""
    on = {f.key: f for f in block.fields if f.enabled and f.scope == "scene"}
    parts: list[str] = []
    for v in sorted(block.values, key=lambda v: on[v.field].position if v.field in on else 0):
        if v.who or v.field not in on:
            continue
        icon = on[v.field].icon
        parts.append(f"{icon} {v.value}" if icon else v.value)
    people = in_scene(block, newest)
    if people:
        parts.append("with " + ", ".join(people))
    return "  ·  ".join(parts) or None


class StatusBlockScreen(View):
    TITLE = "Status block"
    HINTS: ClassVar[tuple[Hint, ...]] = (
        Hint("↑↓", "Choose"),
        Hint("Space", "On / off · add · edit"),
        Hint("A", "New field"),
        Hint("N", "Pin a character"),
        Hint("Del", "Delete · unpin · clear"),
        Hint("R", "Reload"),
        Hint("Esc", "Back"),
    )
    TYPING_HINTS: ClassVar[tuple[Hint, ...]] = (Hint("Enter", "Keep"), Hint("Esc", "Cancel"))
    AUTO_FOCUS: ClassVar[str | None] = ""
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(-1)", "Up", show=False),
        Binding("down,tab", "move(1)", "Down", show=False),
        Binding("pageup", "page(-1)", "Page up", show=False),
        Binding("pagedown", "page(1)", "Page down", show=False),
        Binding("home", "first", "First", show=False),
        Binding("end", "last", "Last", show=False),
        Binding("space,enter", "primary", "Switch", show=False),
        Binding("a,A", "add", "New field", show=False),
        Binding("n,N", "pin", "Pin", show=False),
        Binding("delete,backspace", "remove", "Remove", show=False),
        Binding("r,R", "reload", "Reload", show=False),
    ]

    DEFAULT_CSS = """
    StatusBlockScreen #body { padding: 0 1; }
    StatusBlockScreen .heading { margin-top: 1; }
    StatusBlockScreen Rows { height: 1fr; }
    StatusBlockScreen #typed { }
    """

    def __init__(self, story_id: uuid.UUID, story_name: str) -> None:
        super().__init__()
        self.story_id = story_id
        self.story_name = story_name
        self.block = StatusBlock()
        self._typing: Literal["add", "pin", "value"] | None = None
        self._editing: Item | None = None

    def hints(self) -> Sequence[Hint]:
        return self.TYPING_HINTS if self._typing else self.HINTS

    def body(self) -> ComposeResult:
        yield Static(
            Content.from_markup(
                f"[$muted]{Content(self.story_name).markup}  ·  lines the replies open with, "
                "saved as you change them[/]"
            ),
            classes="heading",
        )
        yield Hairline()
        yield Rows(self._row, empty="Reading the status block…", id="rows")
        yield Input(placeholder="", id="typed", compact=True)
        yield Hairline()

    def on_mount(self) -> None:
        self.query_one("#typed", Input).display = False
        self.run_worker(self._load, exclusive=True)

    @property
    def rows(self) -> Rows[Item]:
        return cast("Rows[Item]", self.query_one("#rows", Rows))  # pyright: ignore[reportUnknownVariableType]

    # -- drawing --------------------------------------------------------------------------------

    def _row(self, item: Item, selected: bool, width: int) -> Content:
        marker = "[$accent]▌ [/]" if selected else "  "
        role = "$accent" if selected else "$foreground"
        icon = f"{Content(item.icon).markup} " if item.icon else ""
        name = Content(item.label).markup
        if item.kind == "field":
            box = "[$success]\\[x][/]" if item.on else "[$border]\\[ ][/]"
            note = Content(item.note).markup
            return Content.from_markup(f"{marker}{box} {icon}[{role}]{name}[/]  [$muted]{note}[/]")
        if item.kind == "starter":
            return Content.from_markup(
                f"{marker}[$warning]\\[+][/] {icon}[$muted]{name}  {Content(item.note).markup}[/]"
            )
        if item.kind == "pin":
            return Content.from_markup(
                f"{marker}[$accent]pin[/] [{role}]{name}[/]  [$muted]always sent[/]"
            )
        by_hand = f"  [$muted]({item.note})[/]" if item.note else ""
        return Content.from_markup(
            f"{marker}[$muted]{name}[/]  [{role}]{Content(item.value).markup}[/]{by_hand}"
        )

    def _show(self, block: StatusBlock) -> None:
        self.block = block
        rows = self.rows
        rows.set_items(
            build_items(block),
            empty="This story has no status lines yet. A adds one of your own.",
        )

    # -- loading --------------------------------------------------------------------------------

    async def _load(self) -> None:
        read = await self.jinnverse.call(
            "Reading the status block", self.jinnverse.api.status_block(self.story_id)
        )
        if read is not None:
            self._show(read)

    def action_reload(self) -> None:
        if self._typing:
            return
        self.run_worker(self._load, exclusive=True)

    async def _change(self, label: str, work: Awaitable[StatusBlock], done: str = "") -> bool:
        """One change to the block: the answer replaces the list; a refusal is the status row."""
        changed = await self.jinnverse.call(label, work)
        if changed is None:
            return False
        self._show(changed)
        if done:
            self.status(done, Kind.SUCCESS)
        return True

    # -- the keys -------------------------------------------------------------------------------

    def action_move(self, delta: int) -> None:
        if not self._typing:
            self.rows.move(delta)

    def action_page(self, direction: int) -> None:
        if not self._typing:
            self.rows.page(direction)

    def action_first(self) -> None:
        if not self._typing:
            self.rows.first()

    def action_last(self) -> None:
        if not self._typing:
            self.rows.last()

    @on(Rows.Opened)
    def _opened(self) -> None:
        self.action_primary()

    def action_primary(self) -> None:
        item = self.rows.selected
        if self._typing or item is None:
            return
        api = self.jinnverse.api
        if item.kind == "field":
            self.run_worker(
                self._change(
                    "Saving",
                    api.change_status_field(self.story_id, item.key, enabled=not item.on),
                    f"{item.label} {'off' if item.on else 'on'}: from the next reply.",
                ),
                exclusive=True,
            )
        elif item.kind == "starter":
            self.run_worker(
                self._change(
                    "Adding",
                    api.adopt_status_fields(self.story_id, [item.key]),
                    f"{item.label} added, switched on.",
                ),
                exclusive=True,
            )
        elif item.kind == "value":
            self._type("value", f"{item.label}: the new value, blank clears it", item.value, item)

    def action_add(self) -> None:
        if not self._typing:
            self._type(
                "add",
                "new field: Label · scene: Label · Label = Low, High",
                "",
                None,
            )

    def action_pin(self) -> None:
        if not self._typing:
            self._type("pin", "pin a character: always sent", "", None)

    def action_remove(self) -> None:
        item = self.rows.selected
        if self._typing or item is None:
            return
        api = self.jinnverse.api
        if item.kind == "pin":
            names = [p for p in self.block.pins if p != item.who]
            self.run_worker(
                self._change("Saving", api.set_status_pins(self.story_id, names), "Unpinned."),
                exclusive=True,
            )
        elif item.kind == "value":
            self.run_worker(
                self._change(
                    "Saving",
                    api.set_status_value(self.story_id, item.key, item.who, ""),
                    "Cleared.",
                ),
                exclusive=True,
            )
        elif item.kind == "field":
            story_id, key = self.story_id, item.key

            async def delete() -> None:
                await self._change(
                    "Deleting",
                    self.jinnverse.api.remove_status_field(story_id, key),
                    f"{item.label} deleted.",
                )

            self.jinnverse.push_screen(
                ConfirmScreen(
                    "Delete",
                    f"Delete {item.label}, with what it holds?",
                    (
                        "The line is no longer asked for, and every value it holds is gone.",
                        "To keep the values, switch it off instead.",
                    ),
                    "Delete",
                    delete,
                )
            )
        else:
            self.status("A starter is not in this story; there is nothing to delete.")

    # -- typing ---------------------------------------------------------------------------------

    def _type(
        self,
        mode: Literal["add", "pin", "value"],
        placeholder: str,
        value: str,
        item: Item | None,
    ) -> None:
        self._typing = mode
        self._editing = item
        field = self.query_one("#typed", Input)
        field.placeholder = placeholder
        field.value = value
        field.display = True
        field.focus()
        self.refresh_hints()

    def _leave_typing(self) -> None:
        self._typing = None
        self._editing = None
        field = self.query_one("#typed", Input)
        field.display = False
        self.set_focus(None)
        self.refresh_hints()

    @on(Input.Submitted, "#typed")
    def _typed(self, event: Input.Submitted) -> None:
        mode, item = self._typing, self._editing
        typed = event.value
        self._leave_typing()
        api = self.jinnverse.api
        if mode == "add":
            parsed = parse_new_field(typed)
            if parsed is None:
                self.status("A field needs a label.", Kind.WARNING)
                return
            label, scope, words = parsed
            self.run_worker(
                self._change(
                    "Adding",
                    api.add_status_field(self.story_id, label, scope=scope, words=words or None),
                    f"{label} added: asked for from the next reply.",
                ),
                exclusive=True,
            )
        elif mode == "pin":
            name = typed.strip()
            if not name:
                return
            self.run_worker(
                self._change(
                    "Saving",
                    api.set_status_pins(self.story_id, [*self.block.pins, name]),
                    f"{name} pinned.",
                ),
                exclusive=True,
            )
        elif mode == "value" and item is not None:
            self.run_worker(
                self._change(
                    "Saving",
                    api.set_status_value(self.story_id, item.key, item.who, typed.strip()),
                    "Set." if typed.strip() else "Cleared.",
                ),
                exclusive=True,
            )

    def action_back(self) -> None:
        if self._typing:
            self._leave_typing()
            return
        self.jinnverse.pop_screen()
