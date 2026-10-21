"""Four slots fold into two: style and marks into look, humour and passions into personality (#254).

A closed list of slots changes by migration, never by an edit: the pieces already in the old
slots move to the one that absorbed theirs, and the CHECK constraint is narrowed only once no
row can fail it. A piece whose name is already taken in its new slot and voice gets a number,
as the API does. Nothing is deleted, and no persona is touched: a persona holds a copy of its
text, never a reference to a piece.

Revision ID: 0022
Revises: 0021
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ABSORBED: dict[str, str] = {
    "style": "look",
    "marks": "look",
    "humour": "personality",
    "passions": "personality",
}

OLD = (
    "('name', 'look', 'style', 'marks', 'family', 'work', 'home', 'vehicle', 'pets', "
    "'personality', 'humour', 'passions')"
)
NEW = "('name', 'look', 'family', 'work', 'home', 'vehicle', 'pets', 'personality')"


def _free_name(connection: sa.Connection, slot: str, voice: str, wanted: str) -> str:
    """`wanted`, or `wanted 2`, `wanted 3`… the first no piece of that slot and voice has."""
    taken = {
        name.lower()
        for name in connection.scalars(
            sa.text("SELECT name FROM persona_pieces WHERE slot = :slot AND voice = :voice"),
            {"slot": slot, "voice": voice},
        )
    }
    candidate, number = wanted, 1
    while candidate.lower() in taken:
        number += 1
        candidate = f"{wanted} {number}"
    return candidate


def upgrade() -> None:
    connection = op.get_bind()
    moving = connection.execute(
        sa.text(
            "SELECT id, slot, voice, name FROM persona_pieces "
            "WHERE slot IN ('style', 'marks', 'humour', 'passions') ORDER BY slot, name"
        )
    ).all()
    for piece_id, slot, voice, name in moving:
        new_slot = ABSORBED[slot]
        connection.execute(
            sa.text("UPDATE persona_pieces SET slot = :new_slot, name = :name WHERE id = :id"),
            {
                "new_slot": new_slot,
                "name": _free_name(connection, new_slot, voice, name),
                "id": piece_id,
            },
        )
    op.drop_constraint("ck_persona_pieces_slot", "persona_pieces", type_="check")
    op.create_check_constraint("ck_persona_pieces_slot", "persona_pieces", f"slot IN {NEW}")


def downgrade() -> None:
    """The constraint widens again; a moved piece stays where it is, as its slot is still one
    of the list, and the text of a merged piece cannot be split back by a migration."""
    op.drop_constraint("ck_persona_pieces_slot", "persona_pieces", type_="check")
    op.create_check_constraint("ck_persona_pieces_slot", "persona_pieces", f"slot IN {OLD}")
