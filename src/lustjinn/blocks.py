"""Status blocks: the state a reply opens with, kept by the app (#169).

A reply may begin with a small block — the day and time, the place, and for each character who
speaks or acts a name line, their outfit, their mood. Asked for in a card, the model drifts from
the format within a long chat and forgets what was worn three hundred turns ago. So the app keeps
the state: it reads the block back from each reply, stores the current value of every field, and
sends it again with the format at the end of the next prompt.

This module is the fields themselves — the shipped starter set, a story's own fields, adopting the
starter ones — and the reading of a reply into stored values. The prompt layer and the API are
added to it by the issues that follow (#172, #173).

The state is a function of the visible transcript, plus what the owner set by hand. That is why a
reroll, a cut or a branch can rewind it: `replay` reads the visible replies again from the start.
"""

import json
import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from importlib import resources
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lustjinn.models import (
    Character,
    Message,
    Role,
    StatusField,
    StatusKind,
    StatusPin,
    StatusScope,
    StatusValue,
    Story,
)

LONGEST_KEY = 60
LONGEST_NAME = 120
LONGEST_VALUE = 300
MOST_NAME_WORDS = 6
NAME_ICON = "📛"
NAME_LABEL = "name"
"""The name line is built in: a character's block is found by it, so it is never a field a
story can switch off or rename."""
Json = dict[str, Any]

RIGHT_QUOTE = chr(0x2019)
NOISE = re.compile(r"[*_`]+")
"""Markdown the model wraps a line in; none of it is part of a label or a value."""
LINE = re.compile(
    r"^\s*(?:[>#•-]\s*)*"
    r"(?P<icon>[^\w\s:>#•-]{1,8})?\s*"
    r"(?P<label>\w[\w '" + RIGHT_QUOTE + r"/&-]{0,58}?)?\s*"
    r":\s*(?P<value>\S.*?)\s*$"
)
"""`📍 Place: the bar`, `📍: the bar` and `Place: the bar` are the same line."""
SEPARATORS = re.compile(r"[|,/;]")
EMPTY = frozenset({"-", chr(0x2014), chr(0x2013), "n/a", "unchanged", "same", "?"})
"""What a model writes when it has nothing new: the stored value stays."""
VARIATION = chr(0xFE0F)
"""The invisible mark some emoji carry; `🕐` with it and without are the same icon."""


@dataclass(frozen=True)
class Starter:
    """One field of the shipped starter set."""

    key: str
    label: str
    icon: str | None
    scope: StatusScope
    kind: StatusKind
    hint: str | None


def slug(label: str) -> str:
    """`Day and time` → `day-and-time`: the unchanging key of a field a person names."""
    return re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-")[:LONGEST_KEY]


def _starter(raw: object) -> Starter | None:
    """A starter field, or None when the entry cannot be used as written."""
    if not isinstance(raw, dict):
        return None
    node: Json = raw  # pyright: ignore[reportUnknownVariableType]
    key, label = node.get("key"), node.get("label")
    icon, hint = node.get("icon"), node.get("hint")
    try:
        scope, kind = StatusScope(node.get("scope")), StatusKind(node.get("kind"))
    except ValueError:
        return None
    if not (isinstance(key, str) and key == slug(key) and isinstance(label, str) and label):
        return None
    return Starter(
        key=key,
        label=label,
        icon=icon if isinstance(icon, str) and icon else None,
        scope=scope,
        kind=kind,
        hint=hint if isinstance(hint, str) and hint else None,
    )


def parse_starters(text: str) -> tuple[Starter, ...]:
    """The starter set from its JSON; an entry that cannot be used is left out."""
    root: object = json.loads(text)
    declared = root.get("fields") if isinstance(root, dict) else None  # pyright: ignore[reportUnknownMemberType, reportUnknownVariableType]
    if not isinstance(declared, list):
        return ()
    nodes: list[object] = declared  # pyright: ignore[reportUnknownVariableType]
    found = (_starter(node) for node in nodes)
    return tuple(starter for starter in found if starter is not None)


@lru_cache
def starters() -> tuple[Starter, ...]:
    """The set shipped with the package, in the order a screen lists it. Read once."""
    return parse_starters(
        resources.files("lustjinn").joinpath("status_fields.json").read_text(encoding="utf-8")
    )


def starter_named(key: str) -> Starter | None:
    return next((starter for starter in starters() if starter.key == key), None)


async def fields_of(session: AsyncSession, story_id: uuid.UUID) -> list[StatusField]:
    """A story's own fields, in the order it lists them."""
    rows = await session.scalars(
        select(StatusField)
        .where(StatusField.story_id == story_id)
        .order_by(StatusField.position, StatusField.key)
    )
    return list(rows)


async def adopt(session: AsyncSession, story_id: uuid.UUID, keys: list[str]) -> list[StatusField]:
    """Gives a story the starter fields it names. One it already has is switched on and left as
    it is; a key that is not in the starter set is ignored. Returns the story's fields."""
    have = {field.key: field for field in await fields_of(session, story_id)}
    position = max((field.position for field in have.values()), default=-1) + 1
    for starter in starters():
        if starter.key not in keys:
            continue
        if (existing := have.get(starter.key)) is not None:
            existing.enabled = True
            continue
        field = StatusField(
            story_id=story_id,
            key=starter.key,
            label=starter.label,
            icon=starter.icon,
            hint=starter.hint,
            kind=starter.kind.value,
            scope=starter.scope.value,
            words=None,
            enabled=True,
            position=position,
        )
        position += 1
        session.add(field)
        have[starter.key] = field
    await session.flush()
    return await fields_of(session, story_id)


# --- reading a reply --------------------------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    """One value read from a reply."""

    field_key: str
    subject: str
    """Whose it is, as the model wrote the name; empty for the scene."""
    value: str


def subject_key(subject: str) -> str:
    """The form names are matched on: `Peach `, `PEACH` and `peach` are one character."""
    return " ".join(subject.casefold().split())


def _plain(icon: str) -> str:
    return icon.replace(VARIATION, "")


def _field_for(
    icon: str | None, label: str | None, fields: Sequence[StatusField]
) -> StatusField | None:
    """The field a line speaks for: by its label or key when it has one, else by its icon."""
    named = (label or "").casefold().strip()
    if named:
        return next((f for f in fields if named in (f.label.casefold(), f.key)), None)
    if icon:
        return next((f for f in fields if f.icon and _plain(f.icon) == _plain(icon)), None)
    return None


def _name(value: str) -> str | None:
    """A character's name from a name line: what comes before a bracket or a parenthesis, and
    short — a sentence that happens to start with `Name:` is not a name."""
    name = re.split(r"[\[(]", value, maxsplit=1)[0].strip(" .:-")
    if not name or len(name) > LONGEST_NAME or len(name.split()) > MOST_NAME_WORDS:
        return None
    return name


def value_of(field: StatusField, raw: str) -> str | None:
    """A value as it will be stored, or None when there is nothing to store."""
    text = " ".join(raw.strip().strip('[]"“”').split())
    if text.casefold() in EMPTY:
        return None
    if field.kind == StatusKind.WORDS.value:
        allowed = {word.casefold(): word for word in field.words or []}
        chosen: list[str] = []
        for part in SEPARATORS.split(text):
            word = allowed.get(part.strip().casefold())
            if word is not None and word not in chosen:
                chosen.append(word)
        return " | ".join(chosen) or None
    return text[:LONGEST_VALUE] or None


def read(reply: str, fields: Sequence[StatusField], default_subject: str = "") -> list[Reading]:
    """The values a reply's blocks give, in the order written.

    A line is `icon label: value`, either part optional. A name line opens a character's block;
    the lines after it are that character's until a line of prose closes the block. Scene fields
    belong to the scene wherever they stand. A character field with no name line before it
    belongs to `default_subject` (the story's character), or to nobody and is dropped. Anything
    that is not a field of the story, and every word not in a word field's list, is ignored.
    """
    found: list[Reading] = []
    subject: str | None = None
    for raw in reply.splitlines():
        line = NOISE.sub("", raw).strip()
        if not line:
            continue
        match = LINE.match(line)
        icon, label = (match.group("icon"), match.group("label")) if match else (None, None)
        if match is None or not (icon or label):
            subject = None  # prose closes the block
            continue
        value = match.group("value")
        if (label or "").casefold().strip() == NAME_LABEL or (
            not label and icon and _plain(icon) == _plain(NAME_ICON)
        ):
            subject = _name(value)
            continue
        field = _field_for(icon, label, fields)
        if field is None:
            subject = None
            continue
        kept = value_of(field, value)
        if kept is None:
            continue
        who = "" if field.scope == StatusScope.SCENE.value else subject or default_subject
        if field.scope == StatusScope.CHARACTER.value and not who:
            continue
        found.append(Reading(field.key, who, kept))
    return found


def _starter_labels() -> frozenset[str]:
    return frozenset(
        {NAME_LABEL} | {s.label.casefold() for s in starters()} | {s.key for s in starters()}
    )


def is_block_line(raw: str) -> bool:
    """Whether a line reads as a line of a status block when the story's own fields are not at
    hand (the list's previews): `icon label: value` with an icon, or a label the shipped starter
    set knows. A custom field without an icon is let through; a sentence with a colon in it
    (`Rowan asks: …`) is prose, and is never taken for a block."""
    match = LINE.match(NOISE.sub("", raw).strip())
    if match is None:
        return False
    if match.group("icon"):
        return True
    label = (match.group("label") or "").casefold().strip()
    return bool(label) and label in _starter_labels()


def prose_start(reply: str) -> str:
    """The reply from where its prose begins: the status block it opens with, if any, left out.
    A reply that is only a block gives its first line, so a list still has something to show."""
    lines = reply.splitlines()
    for index, raw in enumerate(lines):
        if raw.strip() and not is_block_line(raw):
            return "\n".join(lines[index:]).strip()
    return next((raw.strip() for raw in lines if raw.strip()), "")


# --- storing it -------------------------------------------------------------------------------


type Stored = dict[tuple[str, str], StatusValue]


async def _stored(session: AsyncSession, story_id: uuid.UUID) -> Stored:
    rows = await session.scalars(select(StatusValue).where(StatusValue.story_id == story_id))
    return {(row.field_key, row.subject_key): row for row in rows}


def _apply(
    session: AsyncSession,
    story_id: uuid.UUID,
    stored: Stored,
    readings: Sequence[Reading],
    sequence: int,
) -> int:
    """Writes readings into the stored values; returns how many values changed.

    A value the owner set by hand yields to a reply written after it, and not to one written
    before — which is what a replay of the transcript meets.
    """
    changed = 0
    for reading in readings:
        key = (reading.field_key, subject_key(reading.subject))
        row = stored.get(key)
        if row is None:
            row = StatusValue(
                story_id=story_id,
                field_key=reading.field_key,
                subject=reading.subject,
                subject_key=key[1],
                value=reading.value,
                updated_at_sequence=sequence,
                by_hand=False,
            )
            session.add(row)
            stored[key] = row
            changed += 1
            continue
        if row.by_hand and (row.updated_at_sequence or 0) >= sequence:
            continue
        if row.value != reading.value:
            changed += 1
        row.value = reading.value
        row.updated_at_sequence = sequence
        row.by_hand = False
        row.updated_at = datetime.now(UTC)
    return changed


async def absorb(session: AsyncSession, story: Story, text: str, sequence: int) -> int:
    """Reads the reply just written into the story's state. Only fields that are on are looked
    for: a field switched off is no longer asked for, and what a model writes anyway is noise.
    Returns how many values changed."""
    fields = [field for field in await fields_of(session, story.id) if field.enabled]
    if not fields:
        return 0
    name = await session.scalar(select(Character.name).where(Character.id == story.character_id))
    readings = read(text, fields, name or "")
    if not readings:
        return 0
    return _apply(session, story.id, await _stored(session, story.id), readings, sequence)


async def replay(session: AsyncSession, story: Story) -> None:
    """Rebuilds the state from the visible replies, oldest first, keeping what was set by hand.

    Called when the transcript changes under the state — a reroll hides a reply, a cut hides
    several, a branch copies some — so a value written by a reply that is gone does not stay
    behind. Every field the story has is read, on or off: switching one off keeps its values.
    """
    fields = await fields_of(session, story.id)
    if not fields:
        return
    await session.execute(
        delete(StatusValue).where(StatusValue.story_id == story.id, StatusValue.by_hand.is_(False))
    )
    await session.flush()
    name = await session.scalar(select(Character.name).where(Character.id == story.character_id))
    stored = await _stored(session, story.id)
    replies = await session.execute(
        select(Message.sequence, Message.text)
        .where(
            Message.story_id == story.id,
            Message.role == Role.ASSISTANT,
            Message.deleted_at.is_(None),
        )
        .order_by(Message.sequence)
    )
    for sequence, text in replies:
        _apply(session, story.id, stored, read(text, fields, name or ""), sequence)
    await session.flush()


# --- sending it -------------------------------------------------------------------------------

RECENT_TURNS = 12
"""A character whose block was written within this many messages of the newest is in scene; a
pinned character is always sent."""
MOST_CHARACTERS = 12
"""However many are in scene, the state sent has at most this many characters' blocks."""
FRAME = (
    "Every reply begins with a status block that keeps this story's state. First the scene "
    "lines, then, for each character who speaks or acts in the reply, their name line followed "
    "by their lines, placed right before that character's part of the reply and never inside "
    "the prose. Write each line exactly in this shape, in this order, one line each:"
)
RULES = (
    "Change a line only when the story changed it; otherwise write it as it stands below. Write "
    "the scene lines once, at the top. Never write a block for the user."
)
STANDS = "Where things stand now:"


def _prefix(field: StatusField) -> str:
    return f"{field.icon} " if field.icon else ""


def _shape(field: StatusField) -> str:
    """The line the model is shown for a field: its icon and label, and what goes after."""
    if field.kind == StatusKind.WORDS.value and field.words:
        what = "one or more of: " + ", ".join(field.words)
    else:
        what = field.hint or "its value"
    return f"{_prefix(field)}{field.label}: <{what}>"


def render(
    fields: Sequence[StatusField],
    values: Sequence[StatusValue],
    pinned: Sequence[str],
    newest: int,
) -> str | None:
    """The status layer: the format to write and the state as it stands, or None when no field is
    on. The scene's values are always sent; a character's only when they were written within
    `RECENT_TURNS` of `newest` or they are pinned, at most `MOST_CHARACTERS` of them."""
    on = sorted((f for f in fields if f.enabled), key=lambda f: f.position or 0)
    if not on:
        return None
    scene = [f for f in on if f.scope == StatusScope.SCENE.value]
    people = [f for f in on if f.scope == StatusScope.CHARACTER.value]
    # The scene's lines first, then the name line and the character's, as they are to be written.
    shape = [_shape(f) for f in scene]
    if people:
        shape += [f"{NAME_ICON} Name: <the character's name>", *(_shape(f) for f in people)]
    lines = [FRAME, "", *shape, "", RULES]

    held = {(v.field_key, v.subject_key): v for v in values}
    stands = _stands(scene, "", held)
    if stands:
        stands.insert(0, "Scene")
    # When each character last wrote a line, and how they were spelt: who is in scene.
    last: dict[str, int] = {}
    spelt: dict[str, str] = {}
    keys = {f.key for f in people}
    for value in values:
        if value.subject_key and value.field_key in keys:
            last[value.subject_key] = max(
                last.get(value.subject_key, 0), value.updated_at_sequence or 0
            )
            spelt.setdefault(value.subject_key, value.subject)
    wanted = [key for key in pinned if key in last]
    in_scene = (key for key in last if last[key] >= newest - RECENT_TURNS and key not in wanted)
    wanted += sorted(in_scene, key=lambda key: (-last[key], key))
    for key in wanted[:MOST_CHARACTERS]:
        theirs = _stands(people, key, held)
        if theirs:
            stands += [spelt[key], *theirs]
    if stands:
        lines += ["", STANDS, *stands]
    return "\n".join(lines)


def _stands(
    fields: Sequence[StatusField], subject: str, held: dict[tuple[str, str], StatusValue]
) -> list[str]:
    """One subject's lines of the state, for the fields they have a value for."""
    return [
        f"- {f.label}: {held[(f.key, subject)].value}" for f in fields if (f.key, subject) in held
    ]


async def layer(session: AsyncSession, story: Story) -> str | None:
    """The status layer for the next prompt, or None for a story with no field on."""
    fields = await fields_of(session, story.id)
    if not any(field.enabled for field in fields):
        return None
    values = list(
        await session.scalars(select(StatusValue).where(StatusValue.story_id == story.id))
    )
    pins = list(
        await session.scalars(
            select(StatusPin.key).where(StatusPin.story_id == story.id).order_by(StatusPin.name)
        )
    )
    newest = await session.scalar(
        select(func.max(Message.sequence)).where(
            Message.story_id == story.id, Message.deleted_at.is_(None)
        )
    )
    return render(fields, values, pins, newest or 0)
