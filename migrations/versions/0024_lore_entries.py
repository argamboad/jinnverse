"""A character's lorebook: `lore_entries`, and `library_history` keeps their versions too (#266).

An entry is authored text that belongs to a character and is sent only when one of its keys is in
the scene. The keys are a Postgres array column (`TEXT[]`), read by the app, not indexed: a
character holds tens of entries, and the matching happens in Python over the last few turns.

Nothing existing is touched: a character without entries sends exactly what it sent before.

Revision ID: 0024
Revises: 0023
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lore_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("character_id", sa.Uuid(), nullable=False),
        sa.Column("keys", postgresql.ARRAY(sa.String(length=60)), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["character_id"],
            ["characters.id"],
            name="fk_lore_entries_character_id_characters",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_lore_entries"),
    )
    op.create_index("ix_lore_entries_character_id", "lore_entries", ["character_id"])
    op.create_index(
        "uq_lore_entries_character_name_lower",
        "lore_entries",
        ["character_id", sa.literal_column("lower(name)")],
        unique=True,
    )
    # The history keeps every version of an entry, as it does a card's.
    op.drop_constraint("ck_library_history_kind", "library_history", type_="check")
    op.create_check_constraint(
        "ck_library_history_kind",
        "library_history",
        "kind IN ('character', 'persona', 'snippet', 'lore')",
    )


def downgrade() -> None:
    # The history keeps every version and its trigger refuses a delete, so the rows of the kind
    # `lore` stay. The narrower check is put back NOT VALID: it holds for every row written from
    # here on and tolerates the ones already there, as Postgres allows and Alembic cannot say.
    op.drop_constraint("ck_library_history_kind", "library_history", type_="check")
    op.execute(
        "ALTER TABLE library_history ADD CONSTRAINT ck_library_history_kind "
        "CHECK (kind IN ('character', 'persona', 'snippet')) NOT VALID"
    )
    op.drop_index("uq_lore_entries_character_name_lower", table_name="lore_entries")
    op.drop_index("ix_lore_entries_character_id", table_name="lore_entries")
    op.drop_table("lore_entries")
