# Контракт: PNG-скины фигур и досок

Заменяет цветные заглушки (`asset.type = "stub"`) из `docs/contracts-collections.md`. Тип `stub` удалён полностью: в БД, сиде и API остаётся только `png`.

## 1. Форматы картинок

| Вид | Размер | Требования |
|---|---|---|
| Фигура (`piece`) | ровно 128×128 px | PNG; фон прозрачный: альфа всех 4 угловых пикселей = 0 |
| Доска (`board`) | ровно 1088×1088 px | PNG; рамка 32 px с каждой стороны, игровое поле 1024×1024 начинается с (32, 32), клетка 128×128; клетка a8 (у белых) — левый верхний угол поля |

Константы (бэк `app/services/skin_images.py`, фронт `frontend/js/pieces.js`):
`PIECE_PX = 128`, `BOARD_PX = 1088`, `BOARD_FRAME_PX = 32`, `MAX_UPLOAD_BYTES = 8 * 1024 * 1024`.

Сервер перекодирует картинку через Pillow (`img.convert("RGBA")`, `save(format="PNG", optimize=True)`) и хранит результат. Идентификатор картинки — sha256 (hex, 64 символа) **перекодированных** байт.

Доска рисуется картинкой целиком; у чёрных доска НЕ переворачивается как картинка — переворачивается только раскладка клеток, как сейчас. Подписи a–h и 1–8 фронт рисует сам поверх рамки (левая и нижняя полоса рамки).

## 2. Таблица `skin_images` (модель `SkinImage`, `app/models/items.py`)

| Поле | Тип |
|---|---|
| `id` | `CHAR(64)` PK — sha256 hex |
| `kind` | `TEXT NOT NULL`, `CHECK kind IN ('piece', 'board')` (имя ограничения `kind_whitelist`) |
| `data` | `BYTEA NOT NULL` |
| `created_at` | `timestamptz NOT NULL DEFAULT now()` |

## 3. Asset скина

`SkinAsset {type: "png", image: "<sha256 hex>"}` — одинаковый для фигур и досок (`app/schemas/items.py`, `image` — строка по регэкспу `^[0-9a-f]{64}$`, `extra="forbid"`). Классы `PieceAsset` и `BoardAsset` удалены.

При создании коллекции, доски и при `PATCH /admin/item-defs/{id}` сервер проверяет картинку (`skin_images.ensure_image(db, image, kind)`):
- картинки нет → `404 SKIN_IMAGE_NOT_FOUND` «Картинка скина не найдена»;
- `kind` картинки ≠ `kind` скина → `422 VALIDATION_ERROR` «asset не соответствует виду скина».

URL картинки фронт строит сам: `/api/v1/skins/<image>.png`.

## 4. API

### `POST /api/v1/admin/skin-images?kind=piece|board` (только админ)
Тело — сырые байты PNG, заголовок `Content-Type: image/png`. Ответ `201` `SkinImageOut {image: str, kind: "piece"|"board", url: str}`, где `url = "/api/v1/skins/" + image + ".png"`. Повторная загрузка той же картинки — тот же ответ `201`, без дубля.

Ошибки (все `422 SKIN_IMAGE_INVALID`):
- `Content-Type` не `image/png`, тело пустое или Pillow не открывает его как PNG → «Нужен файл PNG»;
- тело больше `MAX_UPLOAD_BYTES` → «Файл больше 8 МБ»;
- фигура не 128×128 → «Фигура должна быть PNG 128×128»;
- доска не 1088×1088 → «Доска должна быть PNG 1088×1088»;
- у фигуры хотя бы один угловой пиксель с альфой > 0 → «У фигуры должен быть прозрачный фон».

`kind` не из списка → `422 VALIDATION_ERROR` (обычная валидация query FastAPI). Аудит: `admin_audit` action `skin_image.upload`, target `skin_image:<sha>`, payload `{"kind": kind}`.

nginx: для `location = /api/v1/admin/skin-images` `client_max_body_size 9m` (во всём остальном 64k).

### `GET /api/v1/skins/{image}.png` (публично, без сессии)
`200`, `Content-Type: image/png`, `Cache-Control: public, max-age=31536000, immutable`, тело — байты из `skin_images.data`. Нет такой картинки или `image` не 64 hex → `404 SKIN_IMAGE_NOT_FOUND`.

## 5. Сид

Картинки-заглушки лежат в репозитории: `backend/app/seed_images/<name>.png`, генерируются `scripts/gen_seed_images.py` (Pillow + шрифт DejaVu Sans, запускается руками на машине разработчика, результат коммитится).

Имена (27 файлов): `base-wp … base-wk`, `base-bp … base-bk`, `base-board`, `genesis-wp … genesis-bk`, `genesis-board-paper`, `genesis-board-albion` (совпадают с `code` скинов сида).

Модуль `app/seed_skins.py`:
- `SEED_IMAGE_NAMES: tuple[str, ...]` — 27 имён в порядке выше;
- `seed_image_id(name) -> str` — sha256 байт файла (кэшируется);
- `seed_image_rows() -> list[dict]` — строки для `skin_images`: `{"id", "kind", "data"}` (`kind = "board"`, если в имени есть `board`, иначе `"piece"`).

Байты файлов сида кладутся как есть (без перекодирования), поэтому `id = sha256(file bytes)`.

`seed_data.seed_rows()`: asset каждого скина сида = `{"type": "png", "image": seed_image_id(code)}`. Старый сид v3 заморожен в `seed_data_v3.py` (для миграции 0007).

## 6. Миграция 0008 (`0008_skin_images.py`)

upgrade:
1. создать `skin_images`;
2. вставить `seed_image_rows()`;
3. каждому `item_defs` с `asset->>'type' = 'stub'`: если `code` есть среди `SEED_IMAGE_NAMES` → картинка с этим именем; иначе фигура → `base-<side><piece_type в нижнем регистре>`, доска → `base-board`;
4. в `games.white_loadout` / `games.black_loadout` каждому слоту со `stub`: если `code` слота есть среди `SEED_IMAGE_NAMES` → эта картинка; иначе слот `board` → `base-board`, слот фигуры `X` → `base-w<x>` для белых и `base-b<x>` для чёрных.

downgrade: всем `item_defs` и слотам снапшотов с `png` вернуть заглушки базового набора (фигуры белых `{"type":"stub","color":"#f4f6ff"}`, чёрных `{"type":"stub","color":"#ff5470"}`, доски `{"type":"stub","light":"#454f77","dark":"#262e4d"}`), удалить `skin_images`.

## 7. Фронт

`frontend/js/pieces.js`:
- `skinUrl(asset) -> string | null` — `/api/v1/skins/<image>.png` для `type === 'png'`, иначе `null`;
- `pieceNode(loadout, piece, color, extraClass) -> HTMLElement` — `<img class="piece-img <extraClass>" src alt="" draggable="false">`, если у слота `loadout[piece]` есть картинка; иначе запасной `<span class="<extraClass>">` с глифом и цветом `DEFAULT_PIECE_COLOR[color]` (снапшот без слота);
- `boardUrl(loadout) -> string | null` — картинка доски или `null` (тогда доска рисуется цветами `DEFAULT_BOARD`).

Доска с картинкой: у `.board-zone` класс `skinned`, у `.board` — CSS-переменная `--board-image: url("…")`; клетки прозрачные; подписи `.ranks`/`.files` абсолютно позиционированы в полосах рамки (`32 / 1088 = 2.9412 %` ширины).

Админка: вместо полей цвета — `<input type="file" accept="image/png">`; файл сразу грузится `apiUpload('/admin/skin-images?kind=…', file)` (`frontend/js/api.js`), в форму подставляется `image` из ответа, рядом превью.

## 8. Картинки по качеству (exterior)

У каждого скина (фигуры и доски) **обязательно** есть PNG для каждого из пяти качеств плюс основная картинка `image`. `image` — превью скина без экземпляра (дропы кейса, лента открытия, цели апгрейда, страница предмета маркета, админка); картинки качеств — то, что видно у конкретного экземпляра и в партии.

### Asset
`SkinAsset {type: "png", image: ImageId, exteriors: {FN, MW, FT, WW, BS: ImageId}}` (`app/schemas/items.py`):
- `Exterior = Literal["FN", "MW", "FT", "WW", "BS"]`, `EXTERIORS: tuple[str, ...] = ("FN", "MW", "FT", "WW", "BS")`;
- `exteriors: dict[Exterior, ImageId]` — обязательное поле, ключи ровно все пять. Нет поля или не хватает ключа → `422 VALIDATION_ERROR` «Нужны картинки для всех качеств: FN, MW, FT, WW, BS»; неизвестный ключ → `422 VALIDATION_ERROR`.

`resolve_image(asset: dict, ext: str) -> str` (там же) = `asset["exteriors"][ext]`.

Хелпер сида `app/seed_skins.py::seed_asset(name) -> dict` = `{"type": "png", "image": seed_image_id(name), "exteriors": {ext: seed_image_id(name) for ext in EXTERIORS}}` — у скинов сида все качества совпадают с основной картинкой.

### Проверка (админка)
При создании коллекции, доски и `PATCH /admin/item-defs/{id}` сервер проверяет `image` и каждую из пяти картинок качеств через `skin_images.ensure_asset(db, asset, kind)` → `ensure_image` (`SKIN_IMAGE_NOT_FOUND` / `VALIDATION_ERROR`). `PATCH` заменяет asset целиком.

### Выдача экземпляра
- `ItemOut.image: str | None` — `resolve_image(def.asset, exterior)` для скина, `null` для предмета-кейса.
- `ListingItemOut.image: str | None = None` — то же для лотов маркета и подарков.
- `ItemDefOut.asset` — asset целиком, всегда с `exteriors`.

### Партия
`loadout_snapshot` кладёт в слот `asset = {"type": "png", "image": resolve_image(def.asset, exterior(wear))}`. Снапшоты уже сыгранных партий не меняются. Фронт партии не меняется.

### Миграция 0009 (`0009_exterior_images.py`)
upgrade: каждому `item_defs` asset получает `exteriors` со всеми пятью ключами; значение ключа — уже имеющаяся картинка этого качества, если есть, иначе `asset->>'image'`. downgrade: из всех asset удаляется ключ `exteriors`.

### Фронт
- `skinPreview(def, image = null)` (`frontend/js/items.js`): `image` задан → эта картинка, иначе `def.asset.image`. Экземплярные карточки (`invItemCard`, маркет, апгрейд, итог кейса/апгрейда) передают `image: item.image`.
- Админка: в формах создания коллекции (в каждой строке фигуры), создания доски и в окне «Изменить скин» — основная картинка и пять обязательных полей «Картинка: <качество>» (подписи `EXTERIOR_RU`). Без всех шести картинок форма не отправляется (тост).
