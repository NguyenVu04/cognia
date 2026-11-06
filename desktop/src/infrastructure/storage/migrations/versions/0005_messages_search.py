"""A full-text index of the messages, for searching earlier conversations.

Revision ID: 0005
Revises: 0004

The index holds the words of each message, so it follows the messages through
triggers: a message deleted, or deleted with its conversation, leaves the index
at once. With secure-delete, a deleted entry is removed from the index rather
than masked, and the connection's ``secure_delete`` zeroes the freed pages, so
the words do not stay in the file. Written by hand: autogenerate does not know
virtual tables or triggers.
"""

from alembic import op

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE VIRTUAL TABLE messages_fts USING fts5("
        "text, content='messages', content_rowid='rowid', "
        "tokenize='unicode61 remove_diacritics 2')"
    )
    op.execute(
        "INSERT INTO messages_fts(messages_fts, rank) VALUES ('secure-delete', 1)"
    )
    op.execute(
        "CREATE TRIGGER messages_fts_insert AFTER INSERT ON messages BEGIN "
        "INSERT INTO messages_fts(rowid, text) VALUES (new.rowid, new.text); END"
    )
    op.execute(
        "CREATE TRIGGER messages_fts_delete AFTER DELETE ON messages BEGIN "
        "INSERT INTO messages_fts(messages_fts, rowid, text) "
        "VALUES ('delete', old.rowid, old.text); END"
    )
    op.execute(
        "CREATE TRIGGER messages_fts_update AFTER UPDATE OF text ON messages BEGIN "
        "INSERT INTO messages_fts(messages_fts, rowid, text) "
        "VALUES ('delete', old.rowid, old.text); "
        "INSERT INTO messages_fts(rowid, text) VALUES (new.rowid, new.text); END"
    )
    op.execute("INSERT INTO messages_fts(messages_fts) VALUES ('rebuild')")


def downgrade() -> None:
    op.execute("DROP TRIGGER messages_fts_update")
    op.execute("DROP TRIGGER messages_fts_delete")
    op.execute("DROP TRIGGER messages_fts_insert")
    op.execute("DROP TABLE messages_fts")
