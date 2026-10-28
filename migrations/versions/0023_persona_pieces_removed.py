"""The pool is gone: persona pieces are removed, with the table and its rows (#258).

Built in 0016, given a description in 0017, folded to eight slots in 0022; taken out on the
owner's decision of 2026-10-27, rows included. No persona is touched: a persona built from
pieces holds a copy of their text, never a reference. The downgrade puts the table back as
0022 left it — the same columns, constraints and index, under the names the earlier
migrations use — but empty: the rows are not recoverable from here.

Revision ID: 0023
Revises: 0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SLOTS = "('name', 'look', 'family', 'work', 'home', 'vehicle', 'pets', 'personality')"


def upgrade() -> None:
    op.drop_index("uq_persona_pieces_slot_voice_name_lower", table_name="persona_pieces")
    op.drop_table("persona_pieces")


def downgrade() -> None:
    op.create_table(
        "persona_pieces",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("slot", sa.String(length=20), nullable=False),
        sa.Column("voice", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("short", sa.String(length=100), nullable=True),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.CheckConstraint(f"slot IN {SLOTS}", name="ck_persona_pieces_slot"),
        sa.CheckConstraint("voice IN ('he', 'she', 'they', 'any')", name="ck_persona_pieces_voice"),
        sa.CheckConstraint(
            "(slot = 'name') = (short IS NOT NULL)", name="ck_persona_pieces_short_only_for_names"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_persona_pieces"),
    )
    op.create_index(
        "uq_persona_pieces_slot_voice_name_lower",
        "persona_pieces",
        ["slot", "voice", sa.literal_column("lower(name)")],
        unique=True,
    )
