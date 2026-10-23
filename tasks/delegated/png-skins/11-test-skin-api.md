# Цель
Интеграционные тесты API картинок скинов: `backend/tests/test_skin_images.py`.

# Контекст
Прочитай: `docs/contracts-skins.md` (§3, §4), `backend/app/api/skins.py`, `backend/app/services/skin_images.py`, фикстуры в `backend/tests/conftest.py` (`admin`, `alice`, `anonymous`, `client`), образец — `backend/tests/test_catalog_admin.py` (функции `create_set`, `pieces_body`, `board_body` — НЕ импортируй их, напиши свои маленькие хелперы в новом файле). В тестах сид уже залит, `seed_image_id(name)` из `app.seed_skins` даёт id картинок сида (`"base-wp"`, `"base-board"` …).

# Область
Создать только `backend/tests/test_skin_images.py`.

# Хелперы
```python
def _png(size, mode="RGBA", color=(0, 0, 0, 0)) -> bytes:
    img = Image.new(mode, size, color)
    if mode == "RGBA" and size == (128, 128):
        img.putpixel((64, 64), (255, 0, 0, 255))
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()

async def _upload(client, kind, data, content_type="image/png"):
    return await client.post(f"/api/v1/admin/skin-images?kind={kind}", content=data, headers={"Content-Type": content_type})
```

# Тесты (каждый — отдельная async-функция)
1. `test_upload_piece_and_get`: админ грузит `_png((128, 128))` как `piece` → 201; тело `{"image", "kind": "piece", "url"}`, `len(image) == 64`, `url == f"/api/v1/skins/{image}.png"`. `anonymous` GET `url` → 200, `headers["content-type"] == "image/png"`, `headers["cache-control"] == "public, max-age=31536000, immutable"`, `Image.open(io.BytesIO(resp.content)).size == (128, 128)`. В `admin_audit` есть строка `action == "skin_image.upload"`, `target == f"skin_image:{image}"` (образец запроса к AdminAudit — в test_catalog_admin.py).
2. `test_upload_same_twice`: две загрузки одинаковых байт → оба 201 и одинаковый `image`.
3. `test_upload_board`: `_png((1088, 1088), "RGB", (1, 2, 3))` как `board` → 201, `kind == "board"`.
4. `test_upload_errors`: каждый случай → 422, `json()["error"]["code"] == "SKIN_IMAGE_INVALID"` и точный `message`:
   - `b"not a png"` → «Нужен файл PNG»;
   - корректный PNG с `content_type="image/jpeg"` → «Нужен файл PNG»;
   - `_png((64, 64))` как `piece` → «Фигура должна быть PNG 128×128»;
   - `_png((128, 128))` как `board` → «Доска должна быть PNG 1088×1088»;
   - `_png((128, 128), "RGB", (255, 255, 255))` как `piece` → «У фигуры должен быть прозрачный фон».
   - `kind=hat` → 422, `code == "VALIDATION_ERROR"`.
5. `test_upload_requires_admin`: `alice` → 403; `anonymous` → 401.
6. `test_get_missing`: `anonymous` GET `/api/v1/skins/{"0" * 64}.png` → 404, code `SKIN_IMAGE_NOT_FOUND`; GET `/api/v1/skins/abc.png` → 404.
7. `test_seed_images_served`: GET `/api/v1/skins/{seed_image_id("base-board")}.png` → 200, размер картинки `(1088, 1088)`.
8. `test_asset_validation_in_catalog`: админ создаёт набор `POST /api/v1/admin/sets` (тело как в `create_set` из test_catalog_admin.py) и доску `POST /api/v1/admin/sets/{id}/boards` (тело как `board_body`), но:
   - `asset {"type": "png", "image": seed_image_id("base-wp")}` (картинка фигуры) → 422, code `VALIDATION_ERROR`;
   - `asset {"type": "png", "image": "0" * 64}` → 404, code `SKIN_IMAGE_NOT_FOUND`;
   - `asset {"type": "stub", "light": "#ffffff", "dark": "#000000"}` → 422;
   - `asset {"type": "png", "image": seed_image_id("base-board")}` → 201.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_skin_images.py` — все зелёные. Если тест падает из-за поведения сервера, а не теста, — НЕ меняй сервер, опиши расхождение в SUMMARY.

# Нельзя
Трогать любые файлы, кроме нового теста. Если что-то не сходится — остановиться и описать в SUMMARY.
