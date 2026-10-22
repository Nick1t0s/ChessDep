# Цель
Обновить Pydantic-схемы предметов под коллекции v2.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 6.1, 6.2), `backend/app/schemas/items.py`.

# Область
Только `backend/app/schemas/items.py`.

# Что сделать (всё остальное в файле оставить как есть)
- `Side = Literal["w", "b"]` рядом с `PieceType`.
- `Slot = Literal["wP", "wN", "wB", "wR", "wQ", "wK", "bP", "bN", "bB", "bR", "bQ", "bK"]`.
- Удалить класс `BoardAsset`.
- `ItemDefOut`: удалить `kind`; добавить `side: Side` перед `piece_type`; `piece_type: PieceType` (не Optional); `asset: PieceAsset`. Порядок полей: id, code, name, side, piece_type, rarity, value, asset, collection.
- `LoadoutOut`: вместо полей P…board — 12 полей `wP, wN, wB, wR, wQ, wK, bP, bN, bB, bR, bQ, bK`, каждое `ItemOut | None`.
- `CaseOut`: поле `collection: CollectionRef` заменить на `collections: list[CollectionRef]`.
- Новый класс перед `CollectionCreateIn`:
```python
class PieceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Side
    piece_type: PieceType
    rarity: Rarity
    value: int = Field(ge=1, le=10_000_000)
    asset: PieceAsset
    is_upgrade_target: bool = True
```
- `CollectionCreateIn`: добавить `pieces: list[PieceIn]` и валидатор:
```python
    @model_validator(mode="after")
    def check_pieces(self) -> "CollectionCreateIn":
        keys = [p.side + p.piece_type for p in self.pieces]
        if len(keys) != 12 or len(set(keys)) != 12:
            raise ValueError("Нужно ровно 12 фигур: по одной на каждую сторону и тип")
        return self
```
- Удалить `ItemDefCreateIn`.
- `ItemDefPatchIn`: оставить только `name`, `rarity`, `value`, `asset: PieceAsset | None = None`, `is_upgrade_target` (удалить `kind`, `piece_type`).
- `CasePatchIn`: удалить `is_active`.
- `AutoDropsIn`: вместо `kind` — `collection_ids: conlist(int, min_length=1, max_length=20)  # type: ignore[valid-type]` и валидатор `@model_validator(mode="after")`, который бросает `ValueError("Повторяющиеся collection_ids")` при дубликатах.
- `AdminCollectionOut`: удалить `cases_count`.
- `AdminCaseOut`: удалить `collection` и `is_active`; поля строго в порядке: `id, code, name, price, status: str, sort, collections: list[CollectionRef], drops: list[AdminDropOut]`.
- `AdminCollectionDetailOut`: удалить поле `cases`.

# Готово, когда
`python3 -m py_compile backend/app/schemas/items.py` без ошибок.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md`. Имена, поля, коды ошибок и тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`.
- Тесты бэкенда в этой волне НЕ запускаются и будут падать — это ожидаемо, их чинит следующая волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
