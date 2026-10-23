"""exterior images: required per-quality PNG in skin assets

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-23

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EXTERIORS = ("FN", "MW", "FT", "WW", "BS")


def upgrade() -> None:
    pairs = ", ".join(
        f"'{e}', COALESCE(asset->'exteriors'->'{e}', asset->'image')" for e in _EXTERIORS
    )
    op.execute(f"UPDATE item_defs SET asset = asset || jsonb_build_object('exteriors', jsonb_build_object({pairs}))")


def downgrade() -> None:
    op.execute("UPDATE item_defs SET asset = asset - 'exteriors'")
