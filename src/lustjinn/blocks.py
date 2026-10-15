"""Status blocks: the state a reply opens with, kept by the app (#169).

A reply may begin with a small block — the day and time, the place, and for each character who
speaks or acts a name line, their outfit, their mood. Asked for in a card, the model drifts from
the format within a long chat and forgets what was worn three hundred turns ago. So the app keeps
the state: it reads the block back from each reply, stores the current value of every field, and
sends it again with the format at the end of the next prompt.

This module is the fields themselves — the shipped starter set, a story's own fields, and adopting
the starter ones. Reading a reply, the prompt layer and the API are added to it by the issues
that follow (#171-#173).
"""

import json
import re
import uuid
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lustjinn.models import StatusField, StatusKind, StatusScope

LONGEST_KEY = 60
Json = dict[str, Any]


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
