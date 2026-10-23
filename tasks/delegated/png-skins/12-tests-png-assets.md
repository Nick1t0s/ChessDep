# Цель
Перевести существующие тесты со старых asset `{"type": "stub", …}` на PNG-asset `{"type": "png", "image": <id>}`.

# Контекст
Прочитай `docs/contracts-skins.md` §3, §5. В тестах картинки сида уже в БД; `from app.seed_skins import seed_image_id` → `seed_image_id("base-wp")`, `seed_image_id("genesis-wq")`, `seed_image_id("base-board")` и т. п. (имя = code скина сида). `BASE_COLORS` из `app.seed_data` удалён. Сервер проверяет, что картинка существует и её вид (фигура/доска) совпадает со скином.

# Область
Только: `backend/tests/test_catalog.py`, `backend/tests/test_cases_admin.py`, `backend/tests/test_upgrade.py`, `backend/tests/test_catalog_admin.py`, `backend/tests/test_inventory.py`.

# Правки
В каждом файле, где нужен id, добавить импорт `from app.seed_skins import seed_image_id`.
- Любое тело запроса с asset фигуры `{"type": "stub", "color": …}` (pieces коллекции в test_cases_admin, test_upgrade, test_catalog_admin) → `{"type": "png", "image": seed_image_id("base-wp")}`.
- test_catalog.py: убрать `asset_white`/`asset_black`; проверку → `assert item["asset"] == {"type": "png", "image": seed_image_id(item["code"])}`.
- test_catalog_admin.py:
  - `_BOARD_ASSET = {"type": "png", "image": seed_image_id("base-board")}`;
  - кейс «asset с color вместо light/dark → 422» → комментарий `# asset с картинкой фигуры → 422.` и `"asset": {"type": "png", "image": seed_image_id("base-wp")}` (ожидание 422 то же);
  - patch фигуры: `"asset": {"type": "png", "image": seed_image_id("genesis-wq")}` и `assert body["asset"] == {"type": "png", "image": seed_image_id("genesis-wq")}`;
  - «Фигуре asset доски → 422»: `{"type": "png", "image": seed_image_id("base-board")}`;
  - «Доске asset фигуры → 422»: `{"type": "png", "image": seed_image_id("base-wp")}`.
- test_inventory.py: импорт `from app.seed_data import BASE_COLORS, item_name` → `from app.seed_data import item_name`; в `_base_skin` asset → `{"type": "png", "image": seed_image_id(f"base-{side}{piece_type.lower()}")}`; `BASE_BOARD` asset → `seed_image_id("base-board")`; `GENESIS_BOARD_PAPER` → `seed_image_id("genesis-board-paper")`; `genesis_q` → `seed_image_id("genesis-wq")`; `genesis_q_black` → `seed_image_id("genesis-bq")` (везде в форме `{"type": "png", "image": …}`).
После правок `grep -n "stub" <эти 5 файлов>` должен быть пуст.

# Готово, когда
`bash scripts/test_isolated.sh tests/test_catalog.py tests/test_cases_admin.py tests/test_upgrade.py tests/test_catalog_admin.py tests/test_inventory.py` — все зелёные. Если тест падает из-за поведения сервера — не трогай сервер, опиши в SUMMARY.

# Нельзя
Трогать другие файлы, менять логику тестов кроме asset. Если что-то не сходится — остановиться и описать в SUMMARY.
