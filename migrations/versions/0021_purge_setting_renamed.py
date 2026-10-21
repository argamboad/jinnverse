"""The purge setting the append-only trigger reads is `jinnverse.purging` (#247).

The trigger function of 0002 lives in the database, so the app's new name reaches it only
through a migration: the function is replaced with the same body under the new setting name,
and the downgrade puts the old name back. CREATE OR REPLACE keeps the trigger that calls it.

Revision ID: 0021
Revises: 0020
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def function(setting: str) -> str:
    """The body of 0002's `messages_append_only`, reading the purge announcement from `setting`."""
    return f"""
        CREATE OR REPLACE FUNCTION messages_append_only() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                -- The one way through: a purge announces itself for the length of its own
                -- transaction with  SET LOCAL {setting} = 'on'.
                IF current_setting('{setting}', true) = 'on' THEN
                    RETURN OLD;
                END IF;
                RAISE EXCEPTION
                    'messages are append-only: a message is hidden with deleted_at, never deleted'
                    USING ERRCODE = 'restrict_violation';
            END IF;

            -- What a turn said, who said it and where it sits never change. Everything else on
            -- the row may: deleted_at (hiding), request_hash, and the columns later steps add.
            IF NEW.text IS DISTINCT FROM OLD.text
               OR NEW.role IS DISTINCT FROM OLD.role
               OR NEW.story_id IS DISTINCT FROM OLD.story_id
               OR NEW.sequence IS DISTINCT FROM OLD.sequence THEN
                RAISE EXCEPTION
                    'messages are append-only: text, role, story and sequence cannot be changed'
                    USING ERRCODE = 'restrict_violation';
            END IF;
            RETURN NEW;
        END
        $$
        """


def upgrade() -> None:
    op.execute(function("jinnverse.purging"))


def downgrade() -> None:
    op.execute(function("lustjinn.purging"))
