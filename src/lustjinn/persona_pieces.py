"""Persona pieces: a pool of texts, one slot each, and the joiner that builds a persona from a pick.

A persona stays what it always was — a name and a page of text, linked from stories — and the
page has a fixed shape: identity and look, style, marks, family, work, home, personality, humour,
passions, one paragraph each. This module keeps the pieces of those paragraphs and joins a pick
into that exact shape. The text is copied into an ordinary persona: editing a piece later changes
no persona already made.

The slots are a closed list on purpose. A persona has to come out in the card's format, and free
text dropped into one may be ignored or overused by the model.
"""

import re
import unicodedata
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, StringConstraints, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from lustjinn.deps import Session
from lustjinn.library import SHELVES, Name, add_entry, alphabetical, check_name
from lustjinn.models import Persona, PersonaPiece, PieceSlot, Voice

router = APIRouter(prefix="/persona-pieces", tags=["persona-pieces"])

FULL_NAME = "{name}"
SHORT_NAME = "{short}"
"""Where a piece writes the persona's name: the full form, and the short one a persona uses after
the first mention ("Allan Sanlúcar El Kettani", then "Allan")."""

PARAGRAPHS: tuple[tuple[PieceSlot, ...], ...] = (
    (PieceSlot.LOOK,),
    (PieceSlot.STYLE,),
    (PieceSlot.MARKS,),
    (PieceSlot.FAMILY,),
    (PieceSlot.WORK,),
    (PieceSlot.HOME, PieceSlot.VEHICLE, PieceSlot.PETS),
    (PieceSlot.PERSONALITY,),
    (PieceSlot.HUMOUR,),
    (PieceSlot.PASSIONS,),
)
"""The persona's paragraphs, in order, and the slots that write each. Home, vehicle and pets share
one paragraph, their sentences joined with a space, as the vehicle and the Hi-Fi sit in the home
paragraph of the personas this was taken from."""


@dataclass(frozen=True)
class SlotInfo:
    key: PieceSlot
    label: str
    paragraph: int | None
    """Which paragraph the slot writes; None for the name, which is written into the others."""


SLOT_LABELS: dict[PieceSlot, str] = {
    PieceSlot.NAME: "Name",
    PieceSlot.LOOK: "Identity and look",
    PieceSlot.STYLE: "Style and what they carry",
    PieceSlot.MARKS: "Tattoos and marks",
    PieceSlot.FAMILY: "Family",
    PieceSlot.WORK: "Occupation and public profile",
    PieceSlot.HOME: "Home",
    PieceSlot.VEHICLE: "Vehicle",
    PieceSlot.PETS: "Pets",
    PieceSlot.PERSONALITY: "Personality and values",
    PieceSlot.HUMOUR: "Humour",
    PieceSlot.PASSIONS: "Passions",
}


def slots() -> list[SlotInfo]:
    """The slots in the order a builder shows them: the name first, then the paragraphs."""
    found = [SlotInfo(PieceSlot.NAME, SLOT_LABELS[PieceSlot.NAME], None)]
    for index, group in enumerate(PARAGRAPHS):
        found += [SlotInfo(slot, SLOT_LABELS[slot], index) for slot in group]
    return found


class PieceError(ValueError):
    """A pick that cannot make a persona; the message says why, for the person who picked."""


def check_voice(voice: Voice, pieces: Sequence[PersonaPiece]) -> None:
    """Every piece must be written in the persona's voice, or in none."""
    for piece in pieces:
        if piece.voice not in (voice, Voice.ANY):
            raise PieceError(
                f"'{piece.name}' is written in the {piece.voice.value} voice; this persona is "
                f"{voice.value}."
            )


def assemble(picks: Mapping[PieceSlot, Sequence[PersonaPiece]]) -> str:
    """The persona's text from a pick: the paragraphs in their order, a line break between,
    empty slots skipped, the name written in where the pieces ask for it."""
    names = picks.get(PieceSlot.NAME, ())
    if len(names) > 1:
        raise PieceError("A persona has one name.")
    paragraphs: list[str] = []
    for group in PARAGRAPHS:
        texts = [
            piece.text.strip()
            for slot in group
            for piece in picks.get(slot, ())
            if piece.text.strip()
        ]
        if len(group) == 1:
            paragraphs += texts  # one paragraph a piece; a piece may hold more than one
        elif texts:
            paragraphs.append(" ".join(texts))
    if not paragraphs:
        raise PieceError("Pick at least one piece.")
    text = "\n".join(paragraphs)
    if names:
        short = names[0].short or names[0].text
        text = text.replace(FULL_NAME, names[0].text).replace(SHORT_NAME, short)
    elif FULL_NAME in text or SHORT_NAME in text:
        raise PieceError(f"These pieces write the persona's name ({FULL_NAME}): pick a name piece.")
    return text


def slug(name: str) -> str:
    """A name as the library's personas are named: lower case, ASCII, hyphens."""
    ascii_only = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_only.lower()).strip("-")[:180] or "persona"


async def free_name(session: AsyncSession, wanted: str) -> str:
    """`wanted`, or `wanted-2`, `wanted-3`… the first no persona has, in any case."""
    taken = {
        name.lower()
        for name in await session.scalars(
            select(Persona.name).where(Persona.name.ilike(f"{wanted}%"))
        )
    }
    candidate, number = wanted, 1
    while candidate.lower() in taken:
        number += 1
        candidate = f"{wanted}-{number}"
    return candidate


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class NewPiece(BaseModel):
    slot: PieceSlot
    voice: Voice
    name: Name
    """What the picker shows."""
    text: Text
    short: Short | None = None
    """A name piece only: its short form."""

    @model_validator(mode="after")
    def _short_belongs_to_names(self) -> NewPiece:
        if (self.slot is PieceSlot.NAME) != (self.short is not None):
            raise ValueError("a name piece has a short form, and no other piece has")
        return self


class PieceChanges(BaseModel):
    """What a save may change; a piece never moves to another slot."""

    version: int
    name: Name | None = None
    voice: Voice | None = None
    text: Text | None = None
    short: Short | None = None


class PieceOut(BaseModel):
    id: uuid.UUID
    slot: PieceSlot
    voice: Voice
    name: str
    text: str
    short: str | None
    version: int
    updated_at: datetime


class SlotOut(BaseModel):
    key: PieceSlot
    label: str
    paragraph: int | None


class Pick(BaseModel):
    voice: Voice
    pieces: dict[PieceSlot, list[uuid.UUID]]
    """The pieces by slot, in the order they should read."""
    name: Name | None = None
    """The persona's name in the library; by default the name piece's, as a slug."""

    @field_validator("name")
    @classmethod
    def _usable(cls, name: str | None) -> str | None:
        return None if name is None else check_name(name)


class Preview(BaseModel):
    name: str | None
    """The name the persona would get, already free; None when nothing says one."""
    text: str


class Built(BaseModel):
    id: uuid.UUID
    name: str
    text: str


def _out(piece: PersonaPiece) -> PieceOut:
    return PieceOut(
        id=piece.id,
        slot=piece.slot,
        voice=piece.voice,
        name=piece.name,
        text=piece.text,
        short=piece.short,
        version=piece.version,
        updated_at=piece.updated_at,
    )


async def _piece(session: AsyncSession, piece_id: uuid.UUID) -> PersonaPiece:
    piece = await session.get(PersonaPiece, piece_id)
    if piece is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "There is no piece with that id.")
    return piece


async def _taken(
    session: AsyncSession, slot: PieceSlot, voice: Voice, name: str, but: uuid.UUID | None = None
) -> bool:
    query = select(PersonaPiece.id).where(
        PersonaPiece.slot == slot,
        PersonaPiece.voice == voice,
        func.lower(PersonaPiece.name) == name.lower(),
    )
    if but is not None:
        query = query.where(PersonaPiece.id != but)
    return await session.scalar(query) is not None


def _conflict(slot: PieceSlot, voice: Voice, name: str) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        f"A {slot.value} piece called '{name}' already exists in the {voice.value} voice. "
        "Edit it, or pick another name.",
    )


@router.get("/slots")
async def read_slots() -> list[SlotOut]:
    """The fixed list, in the order a builder shows it."""
    return [SlotOut(key=info.key, label=info.label, paragraph=info.paragraph) for info in slots()]


@router.get("")
async def list_pieces(
    session: Session, slot: PieceSlot | None = None, voice: Voice | None = None
) -> list[PieceOut]:
    """The pool, by slot and name. `voice` asks for the pieces a persona of that voice may use:
    written in it, or in none."""
    query = select(PersonaPiece).order_by(PersonaPiece.slot, alphabetical(PersonaPiece.name))
    if slot is not None:
        query = query.where(PersonaPiece.slot == slot)
    if voice is not None:
        query = query.where(PersonaPiece.voice.in_([voice, Voice.ANY]))
    return [_out(piece) for piece in await session.scalars(query)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_piece(new: NewPiece, session: Session) -> PieceOut:
    if await _taken(session, new.slot, new.voice, new.name):
        raise _conflict(new.slot, new.voice, new.name)
    piece = PersonaPiece(
        slot=new.slot, voice=new.voice, name=new.name, text=new.text, short=new.short
    )
    session.add(piece)
    await session.commit()
    await session.refresh(piece)
    return _out(piece)


@router.patch("/{piece_id}")
async def save_piece(piece_id: uuid.UUID, changes: PieceChanges, session: Session) -> PieceOut:
    """Saves what was given. Refused with 409 when the piece has moved past the version the
    editor started from, with the piece as it is now."""
    piece = await _piece(session, piece_id)
    if changes.version != piece.version:
        raise _changed_elsewhere(piece)
    if changes.short is not None and piece.slot is not PieceSlot.NAME:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Only a name piece has a short form."
        )
    name = changes.name if changes.name is not None else piece.name
    voice = changes.voice if changes.voice is not None else piece.voice
    if (name, voice) != (piece.name, piece.voice) and await _taken(
        session, piece.slot, voice, name, but=piece.id
    ):
        raise _conflict(piece.slot, voice, name)
    piece.name = name
    piece.voice = voice
    if changes.text is not None:
        piece.text = changes.text
    if changes.short is not None:
        piece.short = changes.short
    if session.is_modified(piece):
        try:
            await session.commit()
        except StaleDataError:
            await session.rollback()
            raise _changed_elsewhere(await _piece(session, piece_id)) from None
        await session.refresh(piece)
    return _out(piece)


def _changed_elsewhere(piece: PersonaPiece) -> HTTPException:
    return HTTPException(
        status.HTTP_409_CONFLICT,
        {
            "message": "This piece changed somewhere else since you opened it. Nothing was "
            "saved. Here is what it says now; save again to replace it.",
            "current": _out(piece).model_dump(mode="json"),
        },
    )


@router.delete("/{piece_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_piece(piece_id: uuid.UUID, session: Session) -> None:
    """Removes a piece. Nothing depends on one: a persona holds a copy of its text."""
    await session.delete(await _piece(session, piece_id))
    await session.commit()


async def _picked(
    session: AsyncSession, pick: Pick
) -> tuple[dict[PieceSlot, list[PersonaPiece]], str]:
    """The pieces a pick names, and the persona's text. Refuses a piece that is not there, one
    placed in a slot it does not belong to, and one written in another voice."""
    ids = {piece_id for ids in pick.pieces.values() for piece_id in ids}
    found = {
        piece.id: piece
        for piece in await session.scalars(select(PersonaPiece).where(PersonaPiece.id.in_(ids)))
    }
    chosen: dict[PieceSlot, list[PersonaPiece]] = {}
    try:
        for slot, piece_ids in pick.pieces.items():
            for piece_id in piece_ids:
                piece = found.get(piece_id)
                if piece is None:
                    raise PieceError("A piece you picked is gone. Pick again.")
                if piece.slot is not slot:
                    raise PieceError(f"'{piece.name}' is a {piece.slot.value} piece.")
                chosen.setdefault(slot, []).append(piece)
        check_voice(pick.voice, [piece for pieces in chosen.values() for piece in pieces])
        return chosen, assemble(chosen)
    except PieceError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from None


def _suggested(chosen: Mapping[PieceSlot, Sequence[PersonaPiece]]) -> str | None:
    names = chosen.get(PieceSlot.NAME)
    return slug(names[0].text) if names else None


@router.post("/preview")
async def preview_persona(pick: Pick, session: Session) -> Preview:
    """The persona a pick would make, and the name it would get. Saves nothing."""
    chosen, text = await _picked(session, pick)
    name = pick.name
    if name is None and (wanted := _suggested(chosen)) is not None:
        name = await free_name(session, wanted)
    return Preview(name=name, text=text)


@router.post("/build", status_code=status.HTTP_201_CREATED)
async def build_persona(pick: Pick, session: Session) -> Built:
    """Makes an ordinary persona from a pick. A name given is used as it is, and refused when
    taken; otherwise the name piece's, with a number when that is taken."""
    chosen, text = await _picked(session, pick)
    wanted = pick.name or _suggested(chosen)
    if wanted is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Name the persona, or pick a name piece.",
        )
    name = wanted if pick.name is not None else await free_name(session, wanted)
    persona = await add_entry(session, SHELVES["personas"], name, text)
    return Built(id=persona.id, name=persona.name, text=text)
