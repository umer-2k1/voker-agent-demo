"""add analysis controls and evaluator metrics

Revision ID: e41c8f27ad03
Revises: d92a61c46f10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e41c8f27ad03"
down_revision: str | Sequence[str] | None = "d92a61c46f10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "semantic_analysis_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "semantic_content_exclusions",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("schema_version", sa.String(length=32), server_default="1", nullable=False),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("evaluator_latency_ms", sa.Numeric(precision=14, scale=3), nullable=True),
    )
    op.add_column("analysis_runs", sa.Column("input_tokens", sa.Integer(), nullable=True))
    op.add_column("analysis_runs", sa.Column("output_tokens", sa.Integer(), nullable=True))
    op.add_column("analysis_runs", sa.Column("cost_micros", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_runs", "cost_micros")
    op.drop_column("analysis_runs", "output_tokens")
    op.drop_column("analysis_runs", "input_tokens")
    op.drop_column("analysis_runs", "evaluator_latency_ms")
    op.drop_column("analysis_runs", "schema_version")
    op.drop_column("projects", "semantic_content_exclusions")
    op.drop_column("projects", "semantic_analysis_enabled")
