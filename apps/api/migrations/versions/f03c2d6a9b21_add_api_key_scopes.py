"""add API key scopes

Revision ID: f03c2d6a9b21
Revises: e41c8f27ad03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f03c2d6a9b21"
down_revision: str | Sequence[str] | None = "e41c8f27ad03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column(
            "scopes",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'[\"ingest:write\"]'::jsonb"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("api_keys", "scopes")
