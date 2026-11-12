# T1. Базовый скин в освободившийся слот (бэкенд)

Worktree: /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t1

Сейчас, когда надетый предмет уходит (выставлен на маркет, подарен, сгорел в апгрейде), `unequip_items` просто удаляет строку экипировки и слот пустеет. Нужно: в слот сразу надевается базовый скин владельца для этого слота.

## 1. `backend/app/services/items.py` — заменить функцию `unequip_items` целиком на:

```python
async def unequip_items(db: AsyncSession, item_ids: list[int]) -> None:
    """Снять предметы с экипировки; в их слоты надеть базовые скины владельца."""
    if not item_ids:
        return
    rows = (
        await db.execute(
            select(Loadout.user_id, Loadout.slot).where(Loadout.inventory_item_id.in_(item_ids))
        )
    ).all()
    await db.execute(delete(Loadout).where(Loadout.inventory_item_id.in_(item_ids)))
    for user_id, slot in rows:
        base_def_id = BASE_DEF_IDS[LOADOUT_SLOTS.index(slot)]
        base_id = await db.scalar(
            select(InventoryItem.id)
            .where(
                InventoryItem.user_id == user_id,
                InventoryItem.source == "base",
                InventoryItem.item_def_id == base_def_id,
                InventoryItem.status == "owned",
            )
            .order_by(InventoryItem.id)
            .limit(1)
        )
        if base_id is not None:
            await db.execute(
                insert(Loadout).values(user_id=user_id, slot=slot, inventory_item_id=base_id)
            )
```

Добавь `insert` в существующий импорт из `sqlalchemy` в начале файла (если его там нет). `BASE_DEF_IDS`, `LOADOUT_SLOTS`, `Loadout`, `InventoryItem`, `delete`, `select` уже импортированы — проверь, не дублируй.

## 2. Обновить существующие тесты (только эти строки)

- `backend/tests/test_market.py` ~строка 42–43: комментарий `# Слот освободился, предмет listed.` → `# В слот вернулся базовый скин, предмет listed.`; `assert loadout["wP"] is None` → две строки:
  ```python
  assert loadout["wP"]["bound"] is True
  assert loadout["complete"] is True
  ```
- `backend/tests/test_gifts.py` ~строка 42: `assert loadout["wN"] is None` → `assert loadout["wN"]["bound"] is True`
- `backend/tests/test_upgrade.py` ~строки 199 и 223: `assert loadout["bR"] is None` → `assert loadout["bR"]["bound"] is True`

## 3. Новый тест в конец `backend/tests/test_inventory.py`

```python
async def test_lost_item_slot_gets_base_skin(alice) -> None:
    ids = await give_items("alice", ["genesis-wp"])
    resp = await alice.put("/api/v1/loadout/wP", json={"inventory_item_id": ids[0]})
    assert resp.status_code == 200, resp.text
    resp = await alice.post("/api/v1/market/listings", json={"item_id": ids[0], "price": 100})
    assert resp.status_code == 201, resp.text
    loadout = (await alice.get("/api/v1/loadout")).json()
    assert loadout["wP"]["bound"] is True
    assert loadout["wP"]["id"] != ids[0]
    assert loadout["complete"] is True
```
Если `give_items` в этом файле не импортирован — добавь в существующий импорт из `tests.conftest`.

## Проверка
`cd /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t1 && bash scripts/test_isolated.sh tests/test_inventory.py tests/test_market.py tests/test_gifts.py tests/test_upgrade.py` — все зелёные.
