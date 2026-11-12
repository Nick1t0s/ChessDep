# Цель
Реализовать функции в `backend/app/services/skin_images.py` (сейчас там заглушки `raise NotImplementedError`) и написать для них юнит-тест `backend/tests/test_skin_images_unit.py`.

# Контекст
Прочитай: `docs/contracts-skins.md` (§1, §2, §4), `backend/app/services/skin_images.py` (константы и сигнатуры уже есть — НЕ менять их), модель `SkinImage` в конце `backend/app/models/items.py`, образец аудита — функция `_audit` в `backend/app/services/catalog_admin.py` (строки ~73–85), образец теста — `backend/tests/test_catalog_admin.py`. Pillow добавлен в `backend/requirements.txt`.

# Область
Менять только `backend/app/services/skin_images.py` (тела функций + импорты + новые константы ошибок) и создать `backend/tests/test_skin_images_unit.py`. Всё остальное не трогать.

# Контракт
Добавить импорты: `import hashlib`, `import io`, `import re`, `from PIL import Image`, `from app.models import AdminAudit, SkinImage, User`.
Добавить константы ошибок (дословно):
```python
_IMAGE_ID_RE = re.compile(r"[0-9a-f]{64}")
NOT_PNG = AppError(422, "SKIN_IMAGE_INVALID", "Нужен файл PNG")
TOO_BIG = AppError(422, "SKIN_IMAGE_INVALID", "Файл больше 2 МБ")
BAD_PIECE_SIZE = AppError(422, "SKIN_IMAGE_INVALID", "Фигура должна быть PNG 128×128")
BAD_BOARD_SIZE = AppError(422, "SKIN_IMAGE_INVALID", "Доска должна быть PNG 1088×1088")
NOT_TRANSPARENT = AppError(422, "SKIN_IMAGE_INVALID", "У фигуры должен быть прозрачный фон")
```
`normalize_png(kind, data)` — строго в таком порядке:
1. `len(data) > MAX_UPLOAD_BYTES` → `raise TOO_BIG`; `len(data) == 0` → `raise NOT_PNG`.
2. В `try:` `img = Image.open(io.BytesIO(data))`; если `img.format != "PNG"` → NOT_PNG. `except Exception as exc: raise NOT_PNG from exc` (но AppError из блока не перехватывать — проверку формата сделай после try).
3. Размер (до `load()`): `kind == "piece"` и `img.size != (PIECE_PX, PIECE_PX)` → `BAD_PIECE_SIZE`; `kind == "board"` и `img.size != (BOARD_PX, BOARD_PX)` → `BAD_BOARD_SIZE`.
4. `try: rgba = img.convert("RGBA")` `except Exception as exc: raise NOT_PNG from exc`.
5. Для `piece`: если у любого из пикселей `(0, 0), (127, 0), (0, 127), (127, 127)` `rgba.getpixel(p)[3] != 0` → `NOT_TRANSPARENT`.
6. `out = io.BytesIO(); rgba.save(out, format="PNG", optimize=True); return out.getvalue()`.

`store_image(db, admin, kind, data)`:
```python
png = normalize_png(kind, data)
image_id = hashlib.sha256(png).hexdigest()
image = await db.get(SkinImage, image_id)
if image is None:
    image = SkinImage(id=image_id, kind=kind, data=png)
    db.add(image)
    await db.flush()
db.add(AdminAudit(admin_id=admin.id, action="skin_image.upload", target=f"skin_image:{image_id}", payload={"kind": kind}))
return image
```
(Сверь поля `AdminAudit` с `_audit` в catalog_admin.py и пиши так же.)

`get_image(db, image_id)`: если `not _IMAGE_ID_RE.fullmatch(image_id)` → `raise SKIN_IMAGE_NOT_FOUND`; `image = await db.get(SkinImage, image_id)`; `None` → `SKIN_IMAGE_NOT_FOUND`; вернуть image.

`ensure_image(db, image_id, kind)`: `image = await get_image(db, image_id)`; `image.kind != kind` → `raise ASSET_KIND_MISMATCH`.

# Тест `backend/tests/test_skin_images_unit.py`
Только синхронные тесты `normalize_png` (без БД), картинки строить Pillow в памяти через хелпер:
```python
def _png(size, mode="RGBA", color=(0, 0, 0, 0)):
    buf = io.BytesIO(); Image.new(mode, size, color).save(buf, format="PNG"); return buf.getvalue()
```
Тесты (у каждого `pytest.raises(AppError)` проверять `.code == "SKIN_IMAGE_INVALID"` и `.message`):
- `test_piece_ok`: фигура 128×128 RGBA, прозрачная, в центре закрашенный пиксель (`img.putpixel((64, 64), (255, 0, 0, 255))`) → результат открывается Pillow, `size == (128, 128)`, `mode == "RGBA"`.
- `test_board_ok`: доска 1088×1088 RGB `(10, 20, 30)` → `size == (1088, 1088)`.
- `test_not_png`: `b"hello"` → «Нужен файл PNG»; пустые байты → «Нужен файл PNG»; JPEG 128×128 (`Image.new("RGB",(128,128)).save(buf, format="JPEG")`) → «Нужен файл PNG».
- `test_too_big`: `b"0" * (MAX_UPLOAD_BYTES + 1)` → «Файл больше 2 МБ».
- `test_bad_sizes`: фигура 64×64 → «Фигура должна быть PNG 128×128»; доска 1024×1024 → «Доска должна быть PNG 1088×1088».
- `test_piece_opaque_background`: фигура 128×128 RGB (без альфы) → «У фигуры должен быть прозрачный фон».

# Готово, когда
`bash scripts/test_isolated.sh tests/test_skin_images_unit.py` — все тесты зелёные (нужен Docker). Если Docker недоступен — напиши об этом в SUMMARY, но код всё равно закоммить.

# Нельзя
Менять сигнатуры и существующие константы, трогать другие файлы, ставить зависимости. Если что-то не сходится — остановиться и описать в SUMMARY.
