"""add Google identity to dashboard users

Revision ID: cb1f16b2237a
Revises: b0271231ca60
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cb1f16b2237a"
down_revision: str | Sequence[str] | None = "b0271231ca60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("google_subject", sa.String(length=255), nullable=True))
    op.create_unique_constraint("uq_users_google_subject", "users", ["google_subject"])


def downgrade() -> None:
    op.drop_constraint("uq_users_google_subject", "users", type_="unique")
    op.drop_column("users", "google_subject")
