"""The API of the status blocks (#169): a story's fields, their values and its pinned characters,
and the `/status` command that sets a value by hand.

Every call that changes something answers with the whole state, so a client draws one response and
keeps no copy of its own to drift.
"""

import uuid
from collections.abc import AsyncIterator, Sequence
from typing import Annotated, Self

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jinnverse import blocks
from jinnverse.deps import Session
from jinnverse.models import (
    Message,
    StatusField,
    StatusKind,
    StatusPin,
    StatusScope,
    StatusValue,
    Story,
)
from jinnverse.stories import visible_story
from jinnverse.streams import Said, event

router = APIRouter(prefix="/stories/{story_id}/status", tags=["status"])
catalogue = APIRouter(tags=["status"])
"""What needs no story: the shipped starter fields, which the new-chat screen offers before the
story exists."""

MOST_FIELDS = 24
MOST_WORDS = 40
MOST_PINS = 24
Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]
Icon = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8)]
Hint = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Word = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


def _refuse(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def _words(words: Sequence[str]) -> list[str]:
    """The allowed words without repeats (case aside), in the order given."""
    seen: dict[str, str] = {}
    for word in words:
        seen.setdefault(word.casefold(), word)
    return list(seen.values())


class NewField(BaseModel):
    label: Label
    icon: Icon | None = None
    hint: Hint | None = None
    """What the model is told to write on the line: `what they are wearing now, briefly`."""
    kind: StatusKind = StatusKind.TEXT
    scope: StatusScope = StatusScope.SCENE
    words: list[Word] | None = None
    """The allowed words of a `words` field; nothing on a text field."""

    @model_validator(mode="after")
    def _words_match_the_kind(self) -> Self:
        if self.kind is StatusKind.WORDS:
            self.words = _words(self.words or [])
            if not self.words or len(self.words) > MOST_WORDS:
                raise ValueError(f"A words field takes between 1 and {MOST_WORDS} words.")
        elif self.words:
            raise ValueError("Only a words field has a list of words.")
        return self


class FieldChanges(BaseModel):
    """What to change on a field; what is left out stays. Its key, kind and scope cannot change:
    the values already read were read under them."""

    label: Label | None = None
    icon: Icon | None = None
    hint: Hint | None = None
    words: list[Word] | None = None
    enabled: bool | None = None
    position: int | None = None


class Adopt(BaseModel):
    keys: list[str]
    """Keys of the shipped starter fields to give the story, switched on."""


class Pins(BaseModel):
    names: list[Name]


class HandValue(BaseModel):
    field: str
    """The field's key or its label."""
    who: Name | None = None
    """The character, for a character field; nothing for a scene field."""
    value: str | None = None
    """Blank clears it."""


class FieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    label: str
    icon: str | None
    hint: str | None
    kind: StatusKind
    scope: StatusScope
    words: list[str] | None
    enabled: bool
    position: int


class StarterOut(BaseModel):
    key: str
    label: str
    icon: str | None
    hint: str | None
    kind: StatusKind
    scope: StatusScope


class ValueOut(BaseModel):
    field: str
    who: str
    """Empty for the scene."""
    value: str
    by_hand: bool
    seen: int | None
    """The message that last wrote it."""


class StatusOut(BaseModel):
    fields: list[FieldOut]
    starters: list[StarterOut]
    """The shipped starter fields this story does not have yet."""
    values: list[ValueOut]
    pins: list[str]


def _starter_out(s: blocks.Starter) -> StarterOut:
    return StarterOut(
        key=s.key, label=s.label, icon=s.icon, hint=s.hint, kind=s.kind, scope=s.scope
    )


@catalogue.get("/status-starters")
async def read_starters() -> list[StarterOut]:
    """The shipped starter fields, in the order a screen lists them."""
    return [_starter_out(s) for s in blocks.starters()]


async def state_of(session: AsyncSession, story_id: uuid.UUID) -> StatusOut:
    fields = await blocks.fields_of(session, story_id)
    have = {field.key for field in fields}
    values = await session.scalars(
        select(StatusValue)
        .where(StatusValue.story_id == story_id)
        .order_by(StatusValue.subject_key, StatusValue.field_key)
    )
    pins = await session.scalars(
        select(StatusPin.name).where(StatusPin.story_id == story_id).order_by(StatusPin.name)
    )
    return StatusOut(
        fields=[FieldOut.model_validate(field) for field in fields],
        starters=[_starter_out(s) for s in blocks.starters() if s.key not in have],
        values=[
            ValueOut(
                field=v.field_key,
                who=v.subject,
                value=v.value,
                by_hand=v.by_hand,
                seen=v.updated_at_sequence,
            )
            for v in values
        ],
        pins=list(pins),
    )


async def _field(session: AsyncSession, story_id: uuid.UUID, ref: str) -> StatusField:
    """A field of the story by its key or its label."""
    wanted = ref.strip().casefold()
    found = next(
        (
            f
            for f in await blocks.fields_of(session, story_id)
            if wanted in (f.key, f.label.casefold())
        ),
        None,
    )
    if found is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"This story has no status field called {ref.strip()}."
        )
    return found


@router.get("")
async def read_status(story_id: uuid.UUID, session: Session) -> StatusOut:
    """The story's fields, what each holds now, the pinned characters, and the shipped starter
    fields it could still adopt."""
    await visible_story(session, story_id)
    return await state_of(session, story_id)


@router.post("/adopt")
async def adopt_starters(story_id: uuid.UUID, body: Adopt, session: Session) -> StatusOut:
    """Gives the story the starter fields named, switched on. One it already has is switched on
    and left as it is; a key that is not a starter is ignored."""
    await visible_story(session, story_id)
    unknown = [k for k in body.keys if blocks.starter_named(k) is None]
    if unknown:
        raise _refuse(f"There is no starter field called {', '.join(unknown)}.")
    await blocks.adopt(session, story_id, body.keys)
    await session.commit()
    return await state_of(session, story_id)


@router.post("/fields", status_code=status.HTTP_201_CREATED)
async def add_field(story_id: uuid.UUID, new: NewField, session: Session) -> StatusOut:
    """Writes a field of the story's own. Its key comes from its label."""
    await visible_story(session, story_id)
    fields = await blocks.fields_of(session, story_id)
    if len(fields) >= MOST_FIELDS:
        raise _refuse(f"A story keeps at most {MOST_FIELDS} status fields.")
    base = blocks.slug(new.label)
    if not base or base == blocks.NAME_LABEL:
        raise _refuse(f"“{new.label}” cannot be a field: the name line is built in.")
    taken = {f.key for f in fields}
    key, n = base, 2
    while key in taken:
        key = f"{base[: blocks.LONGEST_KEY - 4]}-{n}"
        n += 1
    session.add(
        StatusField(
            story_id=story_id,
            key=key,
            label=new.label,
            icon=new.icon,
            hint=new.hint,
            kind=new.kind.value,
            scope=new.scope.value,
            words=new.words,
            enabled=True,
            position=max((f.position for f in fields), default=-1) + 1,
        )
    )
    await session.commit()
    return await state_of(session, story_id)


@router.patch("/fields/{key}")
async def change_field(
    story_id: uuid.UUID, key: str, change: FieldChanges, session: Session
) -> StatusOut:
    """Renames a field, changes its icon, its hint or its words, or switches it on or off. A
    switched-off field is no longer asked for, and what it holds is kept."""
    await visible_story(session, story_id)
    field = await _field(session, story_id, key)
    sent = change.model_fields_set
    if change.label is not None:
        if blocks.slug(change.label) == blocks.NAME_LABEL:
            raise _refuse("The name line is built in.")
        field.label = change.label
    if "icon" in sent:
        field.icon = change.icon
    if "hint" in sent:
        field.hint = change.hint
    if change.words is not None:
        if field.kind != StatusKind.WORDS.value:
            raise _refuse(f"{field.label} is a text field: it has no list of words.")
        words = _words(change.words)
        if not words or len(words) > MOST_WORDS:
            raise _refuse(f"A words field takes between 1 and {MOST_WORDS} words.")
        field.words = words
    if change.enabled is not None:
        field.enabled = change.enabled
    if change.position is not None:
        field.position = change.position
    await session.commit()
    return await state_of(session, story_id)


@router.delete("/fields/{key}")
async def remove_field(story_id: uuid.UUID, key: str, session: Session) -> StatusOut:
    """Deletes a field and everything it holds. To keep the values, switch it off instead."""
    await visible_story(session, story_id)
    field = await _field(session, story_id, key)
    await session.execute(
        delete(StatusValue).where(
            StatusValue.story_id == story_id, StatusValue.field_key == field.key
        )
    )
    await session.delete(field)
    await session.commit()
    return await state_of(session, story_id)


@router.put("/pins")
async def set_pins(story_id: uuid.UUID, body: Pins, session: Session) -> StatusOut:
    """The characters whose state is always sent, however long since they appeared. The list
    replaces the old one."""
    await visible_story(session, story_id)
    named: dict[str, str] = {}
    for name in body.names:
        named.setdefault(blocks.subject_key(name), name)
    if len(named) > MOST_PINS:
        raise _refuse(f"At most {MOST_PINS} characters can be pinned.")
    await session.execute(delete(StatusPin).where(StatusPin.story_id == story_id))
    for key, name in named.items():
        session.add(StatusPin(story_id=story_id, name=name, key=key))
    await session.commit()
    return await state_of(session, story_id)


@router.put("/values")
async def set_hand_value(story_id: uuid.UUID, body: HandValue, session: Session) -> StatusOut:
    """Sets what a field holds, for the scene or for one character, as if a reply had said it.
    A reply written later takes over; a blank value clears it."""
    story = await visible_story(session, story_id)
    await set_by_hand(session, story, body.field, body.who, body.value)
    await session.commit()
    return await state_of(session, story_id)


async def set_by_hand(
    session: AsyncSession, story: Story, ref: str, who: str | None, value: str | None
) -> tuple[StatusField, StatusValue | None]:
    """Sets one value, or clears it. Returns the field and the row (None once cleared)."""
    field = await _field(session, story.id, ref)
    scene = field.scope == StatusScope.SCENE.value
    who = (who or "").strip()
    if scene and who:
        raise _refuse(f"{field.label} is a scene field: it belongs to no character.")
    if not scene and not who:
        raise _refuse(f"{field.label} belongs to a character: say whose.")
    key = blocks.subject_key(who)
    row = await session.scalar(
        select(StatusValue).where(
            StatusValue.story_id == story.id,
            StatusValue.field_key == field.key,
            StatusValue.subject_key == key,
        )
    )
    if not (value or "").strip():
        if row is not None:
            await session.delete(row)
        return field, None
    text = blocks.value_of(field, value or "")
    if text is None:
        allowed = ", ".join(field.words or [])
        raise _refuse(f"{field.label} takes some of these words: {allowed}.")
    newest = await session.scalar(
        select(func.max(Message.sequence)).where(
            Message.story_id == story.id, Message.deleted_at.is_(None)
        )
    )
    if row is None:
        row = StatusValue(
            story_id=story.id, field_key=field.key, subject=who, subject_key=key, value=text
        )
        session.add(row)
    row.value = text
    row.by_hand = True
    row.updated_at_sequence = newest or 0
    return field, row


def split_command(argument: str) -> tuple[str, str, str] | None:
    """`Peach: Outfit = nothing` → ("Peach", "Outfit", "nothing"); `Place = the bar` → ("",
    "Place", "the bar"). None when there is no `=`."""
    left, equals, value = argument.partition("=")
    if not equals:
        return None
    who, colon, ref = left.rpartition(":")
    if not colon:
        who, ref = "", left
    return who.strip(), ref.strip(), value.strip()


async def set_command(session: AsyncSession, story: Story, argument: str) -> AsyncIterator[str]:
    """`/status [who: ]field = value`: sets a status line by hand and says so. No model call. A
    field the story does not have, or a value it does not take, is refused before the stream's
    first event."""
    split = split_command(argument)
    if split is None or not split[1]:
        raise _refuse("/status [who: ]field = value — nothing was stored.")
    who, ref, value = split
    field, row = await set_by_hand(session, story, ref, who or None, value)
    await session.commit()
    whose = f" for {who}" if who else ""
    said = f"{field.label}{whose} is now {row.value}." if row else f"{field.label}{whose} cleared."
    yield event("done", Said(text=said))
