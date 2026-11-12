# Цель
Миграция `backend/alembic/versions/0008_skin_images.py`: таблица `skin_images`, картинки сида, перевод всех asset `stub` → `png` (в `item_defs` и снапшотах партий).

# Контекст
Прочитай: `docs/contracts-skins.md` (§2, §5, §6 — главное), `backend/app/seed_skins.py` (`SEED_IMAGE_NAMES`, `seed_image_id`, `seed_image_rows`), модель `SkinImage` в конце `backend/app/models/items.py`, образец миграции — `backend/alembic/versions/0007_sets.py` (шапка, `op.bulk_insert`, `sa.table`). Миграции пишутся руками, обязательно `downgrade`.

# Область
Создать только `backend/alembic/versions/0008_skin_images.py`.

# Контракт
Шапка: docstring `"""skin images: PNG skins replace stub assets"""` + `Revision ID: 0008`, `Revises: 0007`; `revision = "0008"`, `down_revision = "0007"`.
Импорты: `import json`, `import sqlalchemy as sa`, `from alembic import op`, `from app.seed_skins import SEED_IMAGE_NAMES, seed_image_id, seed_image_rows`. `app.seed_data` НЕ импортировать.

`upgrade()`:
1. Создать таблицу ровно так (имена ограничений — как в 0007, через `op.f`):
```python
    op.create_table(
        "skin_images",
        sa.Column("id", sa.CHAR(64), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("kind IN ('piece', 'board')", name=op.f("ck_skin_images_kind_whitelist")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_skin_images")),
    )
```
2. `op.bulk_insert(<sa.table("skin_images", sa.column("id"), sa.column("kind"), sa.column("data", sa.LargeBinary))>, seed_image_rows())`.
3. Функция-хелпер:
```python
def _png(name: str) -> dict:
    return {"type": "png", "image": seed_image_id(name)}


def _fallback_name(code: str | None, slot: str, side: str | None) -> str:
    """Имя картинки сида для скина: свой code, если он из сида, иначе базовая картинка слота."""
    if code in SEED_IMAGE_NAMES:
        return code
    if slot == "board":
        return "base-board"
    return f"base-{side}{slot.lower()}"
```
4. item_defs: `conn = op.get_bind()`; `rows = conn.execute(sa.text("SELECT id, code, kind, side, piece_type FROM item_defs WHERE asset->>'type' = 'stub'")).all()`; для каждой: `slot = "board" if kind == "board" else piece_type`, `name = _fallback_name(code, slot, side)`, `conn.execute(sa.text("UPDATE item_defs SET asset = CAST(:a AS jsonb) WHERE id = :id"), {"a": json.dumps(_png(name)), "id": id})`.
5. games: `rows = conn.execute(sa.text("SELECT id, white_loadout, black_loadout FROM games")).all()`; для каждой стороны (`white_loadout` → side `"w"`, `black_loadout` → `"b"`) пройти по слотам `for slot, item in loadout.items()`: если `isinstance(item, dict)` и `item.get("asset", {}).get("type") == "stub"` → `item["asset"] = _png(_fallback_name(item.get("code"), slot, side))`. Если что-то поменялось — `UPDATE games SET white_loadout = CAST(:w AS jsonb), black_loadout = CAST(:b AS jsonb) WHERE id = :id` с `json.dumps(...)`. (JSONB приходит уже как dict; если вдруг str — `json.loads`.)

`downgrade()`:
1. Константы: `_STUB_W = {"type": "stub", "color": "#f4f6ff"}`, `_STUB_B = {"type": "stub", "color": "#ff5470"}`, `_STUB_BOARD = {"type": "stub", "light": "#454f77", "dark": "#262e4d"}`.
2. item_defs с `asset->>'type' = 'png'`: доска → `_STUB_BOARD`; фигура `side == "w"` → `_STUB_W`, иначе `_STUB_B`.
3. games: каждому слоту со `asset.type == "png"`: `board` → `_STUB_BOARD`, иначе по стороне снапшота (`white_loadout` → `_STUB_W`, `black_loadout` → `_STUB_B`).
4. `op.drop_table("skin_images")`.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_shop.py` проходит (скрипт сам делает `alembic upgrade head` — значит миграция применяется). Дополнительно проверь откат: в том же compose можно не делать; достаточно, что `python3 -m py_compile backend/alembic/versions/0008_skin_images.py` ок. В SUMMARY напиши, применилась ли миграция.

# Нельзя
Трогать другие файлы (модели, сид, conftest). Если что-то не сходится — остановиться и описать в SUMMARY.
