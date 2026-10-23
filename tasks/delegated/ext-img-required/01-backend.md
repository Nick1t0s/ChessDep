# ТЗ ext-req-back: обязательные картинки всех качеств — бэкенд, миграция 0009, тесты

Рабочая папка: /home/nik/PycharmProjects/.oc-wt/ChessDep/ext-req/back (ветка ext-req-back).
НИКОГДА не заходи в /home/nik/PycharmProjects/ChessDep и не переключай там ветки; git checkout/switch не делать.
Контракт: docs/contracts-skins.md §8 (прочитай целиком — он уже обновлён). Меняй ТОЛЬКО перечисленные файлы.

## 1. backend/app/schemas/items.py
- После `Exterior = Literal[...]` добавить `EXTERIORS: tuple[str, ...] = ("FN", "MW", "FT", "WW", "BS")`.
- `resolve_image` тело заменить на `return asset["exteriors"][ext]`; docstring: `"""Картинка скина для качества ext (asset.exteriors обязателен)."""`.
- `SkinAsset`: удалить метод `_drop_empty_exteriors` и импорт `model_serializer`. Поле: `exteriors: dict[Exterior, ImageId]` (без default — обязательное). Добавить:
```python
    @model_validator(mode="after")
    def check_exteriors(self) -> "SkinAsset":
        if set(self.exteriors) != set(EXTERIORS):
            raise ValueError("Нужны картинки для всех качеств: FN, MW, FT, WW, BS")
        return self
```

## 2. backend/app/seed_skins.py
Добавить в конец (импорт `from app.schemas.items import EXTERIORS` наверху; если будет циклический импорт — объяви локальный кортеж `_EXTERIORS = ("FN", "MW", "FT", "WW", "BS")` с комментарием «те же, что schemas.items.EXTERIORS» и используй его):
```python
def seed_asset(name: str) -> dict:
    """asset скина сида: картинка name основной и во всех качествах."""
    image = seed_image_id(name)
    return {"type": "png", "image": image, "exteriors": {ext: image for ext in EXTERIORS}}
```
Docstring модуля: в перечень пользователей добавить «seed_asset — asset скинов сида и тестов».

## 3. backend/app/seed_data.py
Все 5 мест `"asset": {"type": "png", "image": seed_image_id(X)}` → `"asset": seed_asset(X)` (X тот же). Импорт поправить (seed_image_id, если больше не используется, убрать из импорта).

## 4. backend/alembic/versions/0009_exterior_images.py (новый)
Образец оформления — backend/alembic/versions/0008_skin_images.py (шапка, revision="0009", down_revision="0008", Create Date: 2026-10-23, заголовок «exterior images: required per-quality PNG in skin assets»). Только SQL, без импорта app.*:
```python
_EXTERIORS = ("FN", "MW", "FT", "WW", "BS")


def upgrade() -> None:
    pairs = ", ".join(
        f"'{e}', COALESCE(asset->'exteriors'->'{e}', asset->'image')" for e in _EXTERIORS
    )
    op.execute(f"UPDATE item_defs SET asset = asset || jsonb_build_object('exteriors', jsonb_build_object({pairs}))")


def downgrade() -> None:
    op.execute("UPDATE item_defs SET asset = asset - 'exteriors'")
```

## 5. Тесты
- Во всех тестах, где asset пишется как `{"type": "png", "image": seed_image_id(X)}` (backend/tests/test_catalog.py, test_cases_admin.py, test_skin_images.py, test_inventory.py, test_catalog_admin.py, test_upgrade.py), заменить на `seed_asset(X)` (импорт из app.seed_skins). Если в тесте asset строится из картинки, загруженной в самом тесте (не seed), — заменить на `{"type": "png", "image": img, "exteriors": {e: img for e in EXTERIORS}}` (EXTERIORS из app.schemas.items). Логику и проверки тестов не менять; если тест проверял, что asset с чужим видом картинки даёт 422 — оставь ту же проверку, но asset строй полностью (все exteriors той же неверной картинкой).
- backend/tests/test_exterior_images.py переписать под обязательность:
  1. `test_resolve_image`: `resolve_image({"type":"png","image":"a"*64,"exteriors":{e:"b"*64 for e in EXTERIORS} | {"BS":"c"*64}}, "BS") == "c"*64`, для "FN" — `"b"*64`.
  2. `test_skin_asset_requires_all_exteriors`: SkinAsset без exteriors → ValidationError; с exteriors из 4 ключей → ValidationError; с неизвестным ключом "XX" (плюс все пять) → ValidationError; со всеми пятью — `model_dump()["exteriors"]` содержит 5 ключей.
  3. `test_patch_exteriors`: как сейчас, но asset = seed_asset("genesis-wq") с `exteriors["BS"] = seed_image_id("base-wq")`; ответ 200, `asset["exteriors"]["BS"] == seed_image_id("base-wq")`. PATCH с exteriors без ключа "MW" → 422 VALIDATION_ERROR. BS = картинка доски → 422 VALIDATION_ERROR. BS = "f"*64 → 404 SKIN_IMAGE_NOT_FOUND.
  4. `test_item_image_by_exterior` и 5. `test_snapshot_uses_item_image` — как сейчас, только PATCH-asset строится как в п.3.
  6. `test_create_board_requires_exteriors`: POST создания доски (образец — test_catalog_admin.py) с asset без exteriors → 422 VALIDATION_ERROR.
  7. `test_seed_assets_full`: все item_defs из БД (select ItemDef) имеют `set(asset["exteriors"]) == set(EXTERIORS)`.

## Проверка
`bash scripts/test_isolated.sh` (timeout 600000) — все тесты зелёные (миграции прогоняются в нём через alembic upgrade head). Затем `git add -A && git commit -m "Бэкенд: обязательные картинки всех качеств, миграция 0009"`.

## Если что-то не сходится
Остановись, ничего не придумывай, опиши проблему в отчёте. В отчёте: изменённые файлы и последние строки вывода тестов.
