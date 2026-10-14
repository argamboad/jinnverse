"""A short description on characters, personas, snippets and persona pieces, kept in the history
too (#160). A note for the owner, shown in lists; nothing that builds a prompt reads it.

Revision ID: 0017
Revises: 0016
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("characters", "personas", "snippets", "persona_pieces", "library_history")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("description", sa.String(length=200), nullable=True))


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_column(table, "description")
