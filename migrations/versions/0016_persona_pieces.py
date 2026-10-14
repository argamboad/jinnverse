"""The pool a persona is built from: pieces, one slot and one voice each (#154).

Revision ID: 0016
Revises: 0015
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
        sa.CheckConstraint(
            "slot IN ('name', 'look', 'style', 'marks', 'family', 'work', 'home', 'vehicle', "
            "'pets', 'personality', 'humour', 'passions')",
            name="ck_persona_pieces_slot",
        ),
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


def downgrade() -> None:
    op.drop_index("uq_persona_pieces_slot_voice_name_lower", table_name="persona_pieces")
    op.drop_table("persona_pieces")
