# Цель
Asset скина — `SkinAsset {type: "png", image}` в `backend/app/schemas/items.py`; сервис `backend/app/services/catalog_admin.py` проверяет картинку через `skin_images.ensure_image`.

# Контекст
Прочитай: `docs/contracts-skins.md` §3, `backend/app/schemas/items.py` (классы `PieceAsset`, `BoardAsset` и их использование), `backend/app/services/catalog_admin.py` (`create_collection`, `create_board`, `patch_item_def`), `backend/app/services/skin_images.py` (сигнатура `ensure_image(db, image_id, kind)` и константа `ASSET_KIND_MISMATCH`; тела функций реализует другой исполнитель — файл НЕ трогать).

# Область
Только `backend/app/schemas/items.py` и `backend/app/services/catalog_admin.py`.

# Правки schemas/items.py
1. Классы `PieceAsset` и `BoardAsset` удалить; на их месте:
```python
ImageId = constr(pattern=r"^[0-9a-f]{64}$")


class SkinAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["png"]
    image: ImageId
```
(`constr` уже импортирован. Объявление `HexColor = constr(...)` в строке ~16 удалить, если после правок оно нигде не используется — проверь `grep -n HexColor`).
2. Все аннотации `PieceAsset | BoardAsset`, `PieceAsset`, `BoardAsset` (в `ItemDefOut`, `PieceIn`, `BoardCreateIn`, `ItemDefPatchIn` и где ещё найдёшь `grep -n "PieceAsset\|BoardAsset"`) → `SkinAsset` (в `ItemDefPatchIn` — `SkinAsset | None = None`).
3. Добавить схему ответа загрузки (рядом с другими выходными схемами):
```python
class SkinImageOut(BaseModel):
    image: str
    kind: Literal["piece", "board"]
    url: str
```

# Правки services/catalog_admin.py
1. Из импорта схем убрать `BoardAsset`, `PieceAsset`. Добавить `from app.services.skin_images import ensure_image`.
2. Удалить константу `ASSET_KIND_MISMATCH` из этого файла (если на неё есть другие ссылки в файле — заменить их по пункту 5).
3. `create_collection`: сразу после `await _draft_set(db, set_id)` добавить
```python
    for p in body.pieces:
        await ensure_image(db, p.asset.image, "piece")
```
4. `create_board`: сразу после `await _draft_set(db, set_id)` добавить `    await ensure_image(db, body.asset.image, "board")`.
5. `patch_item_def`: блок
```python
    if "asset" in fields:
        if item_def.kind == "piece":
            ...
        else:
            ...
```
(проверка isinstance) заменить на
```python
    if "asset" in fields:
        if body.asset is None:
            raise ASSET_REQUIRED
        await ensure_image(db, body.asset.image, item_def.kind)
```
и рядом с другими ошибками в начале файла добавить `ASSET_REQUIRED = AppError(422, "VALIDATION_ERROR", "asset не может быть пустым")`.

# Готово, когда
`cd backend && python3 -m py_compile app/schemas/items.py app/services/catalog_admin.py` без ошибок; `grep -rn "PieceAsset\|BoardAsset" backend/app` пусто. Тесты бэкенда в этой волне НЕ запускать (сид ещё на старых asset — их чинит следующая волна).

# Нельзя
Трогать другие файлы (в т.ч. skin_images.py, тесты, seed_data.py). Если что-то не сходится — остановиться и описать в SUMMARY.
