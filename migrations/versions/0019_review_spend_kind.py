"""The ledger learns a kind: `review`, a review of the facts the reader asked for (#232).

Revision ID: 0019
Revises: 0018
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = "kind IN ('reply', 'aside', 'summary', 'facts')"
AFTER = "kind IN ('reply', 'aside', 'summary', 'facts', 'review')"


def upgrade() -> None:
    # The ledger's trigger refuses changes to rows; a constraint on the table is not a row.
    op.drop_constraint("ck_spend_kind", "spend", type_="check")
    op.create_check_constraint("ck_spend_kind", "spend", AFTER)


def downgrade() -> None:
    op.drop_constraint("ck_spend_kind", "spend", type_="check")
    op.create_check_constraint("ck_spend_kind", "spend", BEFORE)
