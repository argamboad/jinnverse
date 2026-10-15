"""Status blocks: the fields a story's replies open with, their current values, and the
characters whose state is always sent (#170).

Revision ID: 0018
Revises: 0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "status_fields",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("icon", sa.String(length=8), nullable=True),
        sa.Column("hint", sa.String(length=200), nullable=True),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("scope", sa.String(length=10), nullable=False),
        sa.Column("words", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint("kind IN ('text', 'words')", name="ck_status_fields_kind"),
        sa.CheckConstraint("scope IN ('scene', 'character')", name="ck_status_fields_scope"),
        sa.ForeignKeyConstraint(
            ["story_id"],
            ["stories.id"],
            name="fk_status_fields_story_id_stories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_status_fields"),
        sa.UniqueConstraint("story_id", "key", name="uq_status_fields_story_key"),
    )
    op.create_table(
        "status_values",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("field_key", sa.String(length=60), nullable=False),
        sa.Column("subject", sa.String(length=120), server_default="", nullable=False),
        sa.Column("subject_key", sa.String(length=120), server_default="", nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_at_sequence", sa.Integer(), nullable=True),
        sa.Column("by_hand", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["story_id"],
            ["stories.id"],
            name="fk_status_values_story_id_stories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_status_values"),
        sa.UniqueConstraint(
            "story_id", "field_key", "subject_key", name="uq_status_values_story_field_subject"
        ),
    )
    op.create_table(
        "status_pins",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("story_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(
            ["story_id"],
            ["stories.id"],
            name="fk_status_pins_story_id_stories",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_status_pins"),
        sa.UniqueConstraint("story_id", "key", name="uq_status_pins_story_key"),
    )


def downgrade() -> None:
    op.drop_table("status_pins")
    op.drop_table("status_values")
    op.drop_table("status_fields")
