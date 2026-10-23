"""skin images: PNG skins replace stub assets

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-23

"""
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.seed_skins import SEED_IMAGE_NAMES, seed_image_id, seed_image_rows

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STUB_W = {"type": "stub", "color": "#f4f6ff"}
_STUB_B = {"type": "stub", "color": "#ff5470"}
_STUB_BOARD = {"type": "stub", "light": "#454f77", "dark": "#262e4d"}


def _png(name: str) -> dict:
    return {"type": "png", "image": seed_image_id(name)}


def _fallback_name(code: str | None, slot: str, side: str | None) -> str:
    """Имя картинки сида для скина: свой code, если он из сида, иначе базовая картинка слота."""
    if code in SEED_IMAGE_NAMES:
        return code
    if slot == "board":
        return "base-board"
    return f"base-{side}{slot.lower()}"


def _as_dict(value) -> dict:
    return json.loads(value) if isinstance(value, str) else value


def upgrade() -> None:
    op.create_table(
        "skin_images",
        sa.Column("id", sa.CHAR(64), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('piece', 'board')", name=op.f("ck_skin_images_kind_whitelist")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skin_images")),
    )

    op.bulk_insert(
        sa.table(
            "skin_images",
            sa.column("id"),
            sa.column("kind"),
            sa.column("data", sa.LargeBinary),
        ),
        seed_image_rows(),
    )

    conn = op.get_bind()

    rows = conn.execute(
        sa.text("SELECT id, code, kind, side, piece_type FROM item_defs WHERE asset->>'type' = 'stub'")
    ).all()
    for row in rows:
        slot = "board" if row.kind == "board" else row.piece_type
        name = _fallback_name(row.code, slot, row.side)
        conn.execute(
            sa.text("UPDATE item_defs SET asset = CAST(:a AS jsonb) WHERE id = :id"),
            {"a": json.dumps(_png(name)), "id": row.id},
        )

    rows = conn.execute(sa.text("SELECT id, white_loadout, black_loadout FROM games")).all()
    for row in rows:
        white = _as_dict(row.white_loadout)
        black = _as_dict(row.black_loadout)
        changed = False
        for loadout, side in ((white, "w"), (black, "b")):
            for slot, item in loadout.items():
                if isinstance(item, dict) and item.get("asset", {}).get("type") == "stub":
                    item["asset"] = _png(_fallback_name(item.get("code"), slot, side))
                    changed = True
        if changed:
            conn.execute(
                sa.text(
                    "UPDATE games SET white_loadout = CAST(:w AS jsonb), "
                    "black_loadout = CAST(:b AS jsonb) WHERE id = :id"
                ),
                {"w": json.dumps(white), "b": json.dumps(black), "id": row.id},
            )


def downgrade() -> None:
    conn = op.get_bind()

    rows = conn.execute(
        sa.text("SELECT id, kind, side FROM item_defs WHERE asset->>'type' = 'png'")
    ).all()
    for row in rows:
        if row.kind == "board":
            asset = _STUB_BOARD
        else:
            asset = _STUB_W if row.side == "w" else _STUB_B
        conn.execute(
            sa.text("UPDATE item_defs SET asset = CAST(:a AS jsonb) WHERE id = :id"),
            {"a": json.dumps(asset), "id": row.id},
        )

    rows = conn.execute(sa.text("SELECT id, white_loadout, black_loadout FROM games")).all()
    for row in rows:
        white = _as_dict(row.white_loadout)
        black = _as_dict(row.black_loadout)
        changed = False
        for loadout, side_stub in ((white, _STUB_W), (black, _STUB_B)):
            for slot, item in loadout.items():
                if isinstance(item, dict) and item.get("asset", {}).get("type") == "png":
                    item["asset"] = _STUB_BOARD if slot == "board" else side_stub
                    changed = True
        if changed:
            conn.execute(
                sa.text(
                    "UPDATE games SET white_loadout = CAST(:w AS jsonb), "
                    "black_loadout = CAST(:b AS jsonb) WHERE id = :id"
                ),
                {"w": json.dumps(white), "b": json.dumps(black), "id": row.id},
            )

    op.drop_table("skin_images")
