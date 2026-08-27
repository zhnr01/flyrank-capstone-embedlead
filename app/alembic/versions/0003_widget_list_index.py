"""add composite widget list index

Revision ID: 0003_widget_list_index
Revises: 0002_memberships
Create Date: 2026-08-19
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_widget_list_index"
down_revision: str | None = "0002_memberships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_widgets_tenant_id_id_desc",
        "widgets",
        ["tenant_id", "id"],
        unique=False,
        postgresql_using="btree",
    )
    op.drop_index("ix_widgets_tenant_id", table_name="widgets")


def downgrade() -> None:
    op.create_index("ix_widgets_tenant_id", "widgets", ["tenant_id"], unique=False)
    op.drop_index("ix_widgets_tenant_id_id_desc", table_name="widgets")
