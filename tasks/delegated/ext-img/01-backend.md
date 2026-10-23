# ТЗ ext-img-back: картинки скинов по качеству — бэкенд + тесты

Рабочая папка: /home/nik/PycharmProjects/.oc-wt/ChessDep/ext-img/back (ветка ext-img-back).
НИКОГДА не заходи в /home/nik/PycharmProjects/ChessDep и не переключай там ветки. git checkout/switch не делать.
Контракт: docs/contracts-skins.md §8 (прочитай целиком). Меняй ТОЛЬКО файлы, перечисленные ниже.

## 1. backend/app/schemas/items.py
- После `DefKind` добавить: `Exterior = Literal["FN", "MW", "FT", "WW", "BS"]`.
- Импорт: `from pydantic import model_serializer` (добавить к существующим импортам pydantic).
- `SkinAsset` привести к виду:
```python
class SkinAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["png"]
    image: ImageId
    exteriors: dict[Exterior, ImageId] = Field(default_factory=dict)

    @model_serializer(mode="wrap")
    def _drop_empty_exteriors(self, handler):  # type: ignore[no-untyped-def]
        data = handler(self)
        if not data.get("exteriors"):
            data.pop("exteriors", None)
        return data
```
- Сразу после функции `exterior(...)` добавить:
```python
def resolve_image(asset: dict, ext: str) -> str:
    """Картинка скина для качества ext: своя из asset.exteriors или основная image."""
    return asset.get("exteriors", {}).get(ext) or asset["image"]
```
- `ItemOut`: после поля `exterior: str | None` добавить `image: str | None`.

## 2. backend/app/schemas/market.py
`ListingItemOut`: после `exterior: str | None = None` добавить `image: str | None = None`.

## 3. backend/app/services/skin_images.py
После `ensure_image` добавить:
```python
async def ensure_asset(db: AsyncSession, asset: SkinAsset, kind: str) -> None:
    """ensure_image для основной картинки и каждой картинки качества."""
    await ensure_image(db, asset.image, kind)
    for image_id in asset.exteriors.values():
        await ensure_image(db, image_id, kind)
```
Импорт `from app.schemas.items import SkinAsset` (если будет циклический импорт — остановись и опиши в отчёте).

## 4. backend/app/services/catalog_admin.py
Три вызова `ensure_image(db, X.asset.image, kind)` (create_collection, create_board, patch_item_def) заменить на `ensure_asset(db, X.asset, kind)` с тем же kind. Импорт поправить. `model_dump()` не трогать.

## 5. backend/app/services/items.py
- Импорт `resolve_image` из app.schemas.items.
- `_skin_out`: после `exterior=exterior(wear),` добавить `image=resolve_image(d.asset.model_dump(), exterior(wear)),`.
- `_case_item_out`: после `exterior=None,` добавить `image=None,`.
- `loadout_snapshot`: выбирать ещё InventoryItem: `select(Loadout, InventoryItem, ItemDef)`, цикл `for loadout, item, item_def in rows:`; в слот класть
  `"asset": {"type": "png", "image": resolve_image(item_def.asset, exterior(float(item.wear or 0.0)))},` вместо `"asset": item_def.asset`.

## 6. backend/app/services/market.py и backend/app/services/gifts.py
Там, где строится `ListingItemOut(...)` из item_out, после `exterior=item_out.exterior,` добавить `image=item_out.image,`.

## 7. Тесты: новый файл backend/tests/test_exterior_images.py
Образец стиля и фикстур: backend/tests/test_catalog_admin.py и backend/tests/test_skin_images.py (как грузят картинки, как получают admin/клиентов, seed_image_id). Тесты (async, как в образцах):
1. `test_resolve_image` — юнит: `resolve_image({"type":"png","image":"a"*64}, "FN") == "a"*64`; с `exteriors={"FN":"b"*64}` → для FN `"b"*64`, для MW `"a"*64`.
2. `test_skin_asset_serialization` — `SkinAsset(type="png", image="a"*64).model_dump() == {"type":"png","image":"a"*64}`; с exteriors — ключ присутствует; `SkinAsset(type="png", image="a"*64, exteriors={"XX":"a"*64})` → ValidationError.
3. `test_patch_exteriors` — админ PATCH `/api/v1/admin/item-defs/{id}` скину genesis-wq (id найти как в test_catalog_admin.py) с `asset={"type":"png","image":seed_image_id("genesis-wq"),"exteriors":{"BS":seed_image_id("base-wq")}}` → 200, в ответе asset содержит exteriors. Затем: exteriors с картинкой доски `seed_image_id("base-board")` → 422 VALIDATION_ERROR; с несуществующим `"f"*64` → 404 SKIN_IMAGE_NOT_FOUND.
4. `test_item_image_by_exterior` — выдать игроку предмет genesis-wq (admin grant, как в существующих тестах), руками в БД выставить ему wear=0.5 (BS); после PATCH из п.3 (exteriors BS → base-wq) `GET /api/v1/inventory` отдаёт у этого предмета `image == seed_image_id("base-wq")`, `exterior == "BS"`; у базового предмета `image == seed_image_id` его кода. У кейса в инвентаре `image is None` (если есть удобный способ выдать кейс — admin grant с case_id).
5. `test_snapshot_uses_item_image` — юнит/интеграционно вызвать `loadout_snapshot` (или создать партию как в test_games.py) для игрока, у которого надет предмет с wear BS и exteriors BS → в снапшоте слот содержит `{"type":"png","image": <BS-картинка>}`. Если собрать сценарий сложно — допускается вызвать `loadout_snapshot(db, user_id, "w")` напрямую в сессии из conftest.

Если какой-то существующий тест падает из-за нового поля `image` в ItemOut/ListingItemOut (точное сравнение словаря) — поправь в нём ожидание, добавив `image`. Других правок в существующих тестах не делать.

## Проверка
`bash scripts/test_isolated.sh` из рабочей папки — все тесты зелёные (запуск долгий, timeout ставь 600000). Затем `git add -A && git commit -m "Бэкенд: картинки скинов по качеству"` в ветке ext-img-back.

## Если что-то не сходится
Остановись, ничего не придумывай, опиши проблему в финальном отчёте. В отчёте: список изменённых файлов и итог тестов (последние строки вывода).
