"""add geo enrichment columns to submissions

Revision ID: 0005_submission_geo
Revises: 0004_submissions
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_submission_geo"
down_revision: str | None = "0004_submissions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("geo_country", sa.String(length=2), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("geo_city", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "submissions",
        sa.Column("geo_provider", sa.String(length=30), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("submissions", "geo_provider")
    op.drop_column("submissions", "geo_city")
    op.drop_column("submissions", "geo_country")
