"""Create SOX Section 404 Cryptographic Audit Ledger Table

Revision ID: 004_sox_audit_ledger
Revises: 003_rename_gsu_to_rsu
Create Date: 2026-09-09 10:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "004_sox_audit_ledger"
down_revision: str | None = "003_rename_gsu_to_rsu"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sox_audit_ledger",
        sa.Column("sequence_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entry_id", sa.UUID(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("actor_email", sa.String(length=255), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("block_hash", sa.String(length=64), nullable=False),
        sa.Column("signature", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("sequence_id"),
        sa.UniqueConstraint("entry_id"),
        sa.UniqueConstraint("block_hash"),
    )
    op.create_index(
        "ix_sox_audit_ledger_timestamp", "sox_audit_ledger", ["timestamp"], unique=False
    )
    op.create_index("ix_sox_audit_ledger_trace_id", "sox_audit_ledger", ["trace_id"], unique=False)
    op.create_index(
        "ix_sox_audit_ledger_entity_type", "sox_audit_ledger", ["entity_type"], unique=False
    )
    op.create_index(
        "ix_sox_audit_ledger_entity_id", "sox_audit_ledger", ["entity_id"], unique=False
    )
    op.create_index("ix_sox_audit_ledger_action", "sox_audit_ledger", ["action"], unique=False)
    op.create_index(
        "ix_sox_audit_ledger_block_hash", "sox_audit_ledger", ["block_hash"], unique=False
    )


def downgrade() -> None:
    op.drop_table("sox_audit_ledger")
