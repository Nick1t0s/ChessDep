# Цель
Добавить один тест `test_upgrade_set_mismatch` в конец файла `backend/tests/test_upgrade.py`.

# Контекст
Бэкенд уже сделан: `backend/app/services/upgrade.py`, функция `compute()` — если хотя бы один входной предмет не из набора цели, ошибка `UPGRADE_SET_MISMATCH` (400). В `/upgrade/preview` это приходит как `{"allowed": false, "reason": "UPGRADE_SET_MISMATCH"}` со статусом 200.
Образец создания второго набора — функция `test_upgrade_validation` в том же файле (строки ~100–130: POST `/api/v1/admin/sets` и POST `/api/v1/admin/sets/{set_id}/collections`). Хелперы `give_items`, `def_id_by_code` уже есть в файле.

# Область
Только `backend/tests/test_upgrade.py`, только дописать новую функцию в конец файла. Существующие функции и импорты не трогать.

# Контракт
Вставь в конец файла ровно эту функцию (с двумя пустыми строками перед ней):

```python
async def test_upgrade_set_mismatch(alice, admin) -> None:
    # Второй выпущенный набор Winter (12 фигур).
    resp = await admin.post(
        "/api/v1/admin/sets",
        json={"code": "winter", "name": "Winter", "description": "Зимний набор"},
    )
    assert resp.status_code == 201, resp.text
    set_id = resp.json()["id"]
    resp = await admin.post(
        f"/api/v1/admin/sets/{set_id}/collections",
        json={
            "code": "winter",
            "name": "Winter",
            "description": "Зимняя коллекция",
            "pieces": [
                {
                    "side": side,
                    "piece_type": piece_type,
                    "rarity": "epic",
                    "value": 500,
                    "asset": {"type": "stub", "color": "#ffffff"},
                }
                for side in ("w", "b")
                for piece_type in ("P", "N", "B", "R", "Q", "K")
            ],
        },
    )
    assert resp.status_code == 201, resp.text
    resp = await admin.post(f"/api/v1/admin/sets/{set_id}/release")
    assert resp.status_code == 200, resp.text
    winter_wq = await def_id_by_code("winter-wq")
    genesis_wk = await def_id_by_code("genesis-wk")

    # Входы Genesis -> цель Winter: preview запрещает.
    inputs = await give_items("alice", ["genesis-wr", "genesis-br"])
    resp = await alice.post(
        "/api/v1/upgrade/preview",
        json={"input_ids": inputs, "target_def_id": winter_wq},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["allowed"] is False
    assert resp.json()["reason"] == "UPGRADE_SET_MISMATCH"

    # То же через /upgrade — 400, предметы не сгорают.
    resp = await alice.post(
        "/api/v1/upgrade", json={"input_ids": inputs, "target_def_id": winter_wq}
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["error"]["code"] == "UPGRADE_SET_MISMATCH"
    async with SessionLocal() as db:
        statuses = (
            await db.scalars(select(InventoryItem.status).where(InventoryItem.id.in_(inputs)))
        ).all()
    assert sorted(statuses) == ["owned", "owned"]

    # Смешанные входы (Genesis + Winter) -> цель Genesis: тоже запрещено.
    mixed = await give_items("alice", ["genesis-wr", "winter-wr"])
    resp = await alice.post(
        "/api/v1/upgrade/preview",
        json={"input_ids": mixed, "target_def_id": genesis_wk},
    )
    assert resp.json()["reason"] == "UPGRADE_SET_MISMATCH"
```

# Готово, когда
`bash scripts/test_isolated.sh tests/test_upgrade.py` — все тесты проходят (8 passed).

# Нельзя
Менять что-либо, кроме добавления этой функции. Менять код в `backend/app`. Если тест падает — не чинить бэкенд и не менять ожидания, а остановиться и описать ошибку в SUMMARY.
