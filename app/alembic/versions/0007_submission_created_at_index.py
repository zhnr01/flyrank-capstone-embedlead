"""add created_at index for submission time series

Revision ID: 0007_submission_created_at_index
Revises: 0006_outbox_messages
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0007_submission_created_at_index"
down_revision: str | None = "0006_outbox_messages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "ix_submissions_tenant_id_created_at"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "submissions",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="submissions")
