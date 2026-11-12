"""sale notices: market_listings.seller_seen; empty loadout slots get base skins

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-24

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Пустые слоты экипировки получают базовый скин владельца (теперь слот не пустеет сам).
_FILL_SLOTS = """
INSERT INTO loadouts (user_id, slot, inventory_item_id)
SELECT ii.user_id,
       CASE WHEN d.kind = 'board' THEN 'board' ELSE d.side || d.piece_type END,
       ii.id
FROM inventory_items ii
JOIN item_defs d ON d.id = ii.item_def_id
WHERE ii.source = 'base' AND ii.status = 'owned'
ON CONFLICT DO NOTHING
"""


def upgrade() -> None:
    op.add_column(
        "market_listings",
        sa.Column("seller_seen", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.execute(_FILL_SLOTS)


def downgrade() -> None:
    # Надетые базовые скины не снимаем: это валидная экипировка.
    op.drop_column("market_listings", "seller_seen")
