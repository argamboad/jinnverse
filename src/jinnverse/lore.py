"""The lorebook: authored text that belongs to a character and is sent only when the scene calls
for it (#266, #267).

A card is sent whole, every turn. That is right for a card of three thousand tokens and wrong for
one of twenty-seven thousand — the *Blake Jameson University* card, forty-three characters with a
full sheet each, left a story four thousand tokens of a thirty-two-thousand budget. An entry is a
piece of such a card moved out of it: a cast member's sheet, a building, a timetable. It carries
the keys that bring it in — a name, a nickname, a role, a place — and comes into the prompt only
while one of them is in the scene.

What is here: the entries' API under a character, and the matcher that picks the entries for a
turn. The matcher is pure; the builder (`context.py`) fits what it picks under a share of the
budget and places it after the history, beside the memories, where a change of scene does not
break the cached prefix.
"""

import re
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from jinnverse.blocks import RECENT_TURNS
from jinnverse.context import Lore
from jinnverse.deps import Session
from jinnverse.library import check_description, check_name
from jinnverse.models import Character, LibraryHistory, LibraryKind, LoreEntry, Message, StatusValue

router = APIRouter(prefix="/library/characters/{character_id}/lore", tags=["library"])

MOST_KEYS = 40
KEY_LENGTH = 60
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Body = Annotated[str, StringConstraints(min_length=1)]


def clean_keys(given: Sequence[str]) -> list[str]:
    """The keys as they are kept: lowercased, trimmed, inner whitespace collapsed, without
    repeats, in the order given. Blank ones are dropped; an empty list is refused by the caller,
    since an entry nothing can bring in is a card paragraph that was lost."""
    seen: dict[str, None] = {}
    for key in given:
        cleaned = " ".join(key.casefold().split())
        if cleaned:
            seen.setdefault(cleaned, None)
    return list(seen)


def check_keys(keys: Sequence[str]) -> list[str]:
    cleaned = clean_keys(keys)
    if not cleaned:
        raise ValueError("An entry needs at least one key: a word that brings it in.")
    if len(cleaned) > MOST_KEYS:
        raise ValueError(f"An entry has at most {MOST_KEYS} keys.")
    if any(len(key) > KEY_LENGTH for key in cleaned):
        raise ValueError(f"A key is at most {KEY_LENGTH} characters.")
    return cleaned


class NewLore(BaseModel):
    name: Name
    keys: list[str]
    text: Body
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _usable(cls, name: str) -> str:
        return check_name(name)

    @field_validator("keys")
    @classmethod
    def _clean(cls, keys: list[str]) -> list[str]:
        return check_keys(keys)

    @field_validator("description")
    @classmethod
    def _short(cls, description: str | None) -> str | None:
        return check_description(description)


class LoreChanges(BaseModel):
    """What a save may change. Only the fields given are touched; the version is the one the
    editor started from, as for any entry of the library."""

    version: int
    name: Name | None = None
    keys: list[str] | None = None
    text: Body | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def _usable(cls, name: str | None) -> str | None:
        return None if name is None else check_name(name)

    @field_validator("keys")
    @classmethod
    def _clean(cls, keys: list[str] | None) -> list[str] | None:
        return None if keys is None else check_keys(keys)

    @field_validator("description")
    @classmethod
    def _short(cls, description: str | None) -> str | None:
        return check_description(description)


class LoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    character_id: uuid.UUID
    name: str
    keys: list[str]
    text: str
    description: str | None
    version: int
    updated_at: datetime


class LoreHistoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version: int
    name: str
    text: str
    description: str | None
    saved_at: datetime


async def entries_of(session: AsyncSession, character_id: uuid.UUID) -> list[LoreEntry]:
    """A character's entries in creation order: the order of the card they came from."""
    rows = await session.scalars(
        select(LoreEntry).where(LoreEntry.character_id == character_id).order_by(LoreEntry.id)
    )
    return list(rows)


async def _character(session: AsyncSession, character_id: uuid.UUID) -> Character:
    character = await session.get(Character, character_id)
    if character is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no character with that id.")
    return character


async def _one(session: AsyncSession, character_id: uuid.UUID, entry_id: uuid.UUID) -> LoreEntry:
    entry = await session.get(LoreEntry, entry_id)
    if entry is None or entry.character_id != character_id:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "This character has no lore entry with that id."
        )
    return entry


async def _taken(
    session: AsyncSession, character_id: uuid.UUID, name: str, but: uuid.UUID | None = None
) -> bool:
    query = select(LoreEntry.id).where(
        LoreEntry.character_id == character_id, func.lower(LoreEntry.name) == name.lower()
    )
    if but is not None:
        query = query.where(LoreEntry.id != but)
    return await session.scalar(query) is not None


def _remembered(entry: LoreEntry, version: int) -> LibraryHistory:
    return LibraryHistory(
        kind=LibraryKind.LORE,
        entry_id=entry.id,
        version=version,
        name=entry.name,
        text=entry.text,
        opening=None,
        description=entry.description,
    )


def _changed_elsewhere(current: LoreEntry) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {
            "message": "This entry changed somewhere else since you opened it. Nothing was "
            "saved. Here is what it says now; save again to replace it.",
            "current": LoreOut.model_validate(current).model_dump(mode="json"),
        },
    )


@router.get("")
async def list_lore(character_id: uuid.UUID, session: Session) -> list[LoreOut]:
    """Every entry of the character, text included: a lorebook is read whole in an editor, and
    forty entries of five hundred tokens are one card's worth."""
    await _character(session, character_id)
    return [LoreOut.model_validate(entry) for entry in await entries_of(session, character_id)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_lore(character_id: uuid.UUID, new: NewLore, session: Session) -> LoreOut:
    await _character(session, character_id)
    if await _taken(session, character_id, new.name):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"This character already has an entry called '{new.name}'. Edit it, or pick "
            "another name.",
        )
    entry = LoreEntry(
        character_id=character_id,
        name=new.name,
        keys=new.keys,
        text=new.text,
        description=new.description,
    )
    session.add(entry)
    await session.flush()
    session.add(_remembered(entry, version=1))
    await session.commit()
    await session.refresh(entry)
    return LoreOut.model_validate(entry)


@router.get("/{entry_id}")
async def read_lore(character_id: uuid.UUID, entry_id: uuid.UUID, session: Session) -> LoreOut:
    return LoreOut.model_validate(await _one(session, character_id, entry_id))


@router.patch("/{entry_id}")
async def save_lore(
    character_id: uuid.UUID, entry_id: uuid.UUID, changes: LoreChanges, session: Session
) -> LoreOut:
    """Saves what was given over the version the editor started from; 409 with the current
    entry when it has moved on, as a card's save does. A save that changes nothing writes
    nothing."""
    entry = await _one(session, character_id, entry_id)
    if changes.version != entry.version:
        raise _changed_elsewhere(entry)
    if changes.name is not None and changes.name != entry.name:
        if await _taken(session, character_id, changes.name, but=entry.id):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"This character already has an entry called '{changes.name}'.",
            )
        entry.name = changes.name
    if changes.keys is not None:
        entry.keys = changes.keys
    if changes.text is not None:
        entry.text = changes.text
    if "description" in changes.model_fields_set:
        entry.description = changes.description
    if session.is_modified(entry):
        session.add(_remembered(entry, version=entry.version + 1))
        try:
            await session.commit()
        except StaleDataError:
            await session.rollback()
            raise _changed_elsewhere(await _one(session, character_id, entry_id)) from None
        await session.refresh(entry)
    return LoreOut.model_validate(entry)


@router.get("/{entry_id}/history")
async def read_lore_history(
    character_id: uuid.UUID, entry_id: uuid.UUID, session: Session
) -> list[LoreHistoryOut]:
    """Every version ever saved, newest first. The keys are not in it: the history keeps the
    text, as it does for a card, and a key is a handle, not prose."""
    await _one(session, character_id, entry_id)
    rows = await session.scalars(
        select(LibraryHistory)
        .where(LibraryHistory.kind == LibraryKind.LORE, LibraryHistory.entry_id == entry_id)
        .order_by(LibraryHistory.version.desc())
    )
    return [LoreHistoryOut.model_validate(row) for row in rows]


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lore(character_id: uuid.UUID, entry_id: uuid.UUID, session: Session) -> None:
    """Removes an entry. No story holds one: a story holds its character, and reads whatever
    entries the character has at its next turn."""
    entry = await _one(session, character_id, entry_id)
    await session.delete(entry)
    await session.commit()


# -- the matcher ----------------------------------------------------------------------------------

LOOKBACK = 6
"""How many of the newest turns an entry's keys are looked for in: the scene in progress, the same
six the summariser never compresses. One turn would drop a character from the prompt the moment
nobody named her; six keeps her through a short exchange about something else."""


def _pattern(keys: Sequence[str]) -> re.Pattern[str]:
    """One pattern for all the keys: each as whole words, so `jax` is not in `jaxon` but is in
    `Jax's`. Case does not matter; accents do, since the text spells them."""
    alternatives = "|".join(re.escape(key) for key in keys)
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


def matched(
    entries: Sequence[LoreEntry], recent: Sequence[str], status_lines: Sequence[str] = ()
) -> list[Lore]:
    """The entries called for by the last `LOOKBACK` of `recent` (oldest first) or by the status
    block's lines, freshest first; ties in creation order. An entry's own text is never looked
    in, so one entry cannot bring in another."""
    scene = list(recent[-LOOKBACK:])
    status_text = "\n".join(status_lines)
    found: list[Lore] = []
    for position, entry in enumerate(entries):
        if not entry.keys:
            continue
        pattern = _pattern(entry.keys)
        if status_text and pattern.search(status_text):
            found.append(Lore(position, entry.text, len(scene)))
            continue
        newest = next((i for i in range(len(scene) - 1, -1, -1) if pattern.search(scene[i])), None)
        if newest is not None:
            found.append(Lore(position, entry.text, newest))
    found.sort(key=lambda hit: (-hit.freshness, hit.position))
    return found


async def status_lines(session: AsyncSession, story_id: uuid.UUID, newest: int) -> list[str]:
    """What the status block says the scene is: the scene's values (the place, the time), and
    the names of the characters whose lines were written within `RECENT_TURNS` of `newest` —
    the same rule by which the block itself shows them. A place named there keeps its entry in
    the prompt for as long as the scene stays there, whether or not anyone says its name."""
    rows = await session.scalars(select(StatusValue).where(StatusValue.story_id == story_id))
    lines: list[str] = []
    for value in rows:
        if not value.subject_key:
            lines.append(value.value)
        elif (value.updated_at_sequence or 0) >= newest - RECENT_TURNS:
            lines.append(value.subject)
    return lines


async def for_turn(
    session: AsyncSession, character_id: uuid.UUID, story_id: uuid.UUID, history: Sequence[Message]
) -> list[Lore]:
    """The entries the next prompt of a story gets: the character's, matched against the end
    of the visible transcript and the status block. A character without entries costs one
    query and nothing else."""
    entries = await entries_of(session, character_id)
    if not entries:
        return []
    newest = history[-1].sequence if history else 0
    lines = await status_lines(session, story_id, newest)
    return matched(entries, [turn.text for turn in history], lines)
