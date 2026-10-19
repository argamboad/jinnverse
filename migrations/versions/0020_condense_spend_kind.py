"""The ledger learns a kind: `condense`, the oldest summaries merged into one on request (#233).

Revision ID: 0020
Revises: 0019
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BEFORE = "kind IN ('reply', 'aside', 'summary', 'facts', 'review')"
AFTER = "kind IN ('reply', 'aside', 'summary', 'facts', 'review', 'condense')"


def upgrade() -> None:
    op.drop_constraint("ck_spend_kind", "spend", type_="check")
    op.create_check_constraint("ck_spend_kind", "spend", AFTER)


def downgrade() -> None:
    op.drop_constraint("ck_spend_kind", "spend", type_="check")
    op.create_check_constraint("ck_spend_kind", "spend", BEFORE)
