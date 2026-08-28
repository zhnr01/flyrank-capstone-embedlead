"""add nullable config column to widgets

Revision ID: 0008_widget_config
Revises: 0007_submission_created_at_index
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_widget_config"
down_revision: str | None = "0007_submission_created_at_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "widgets",
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("widgets", "config")
