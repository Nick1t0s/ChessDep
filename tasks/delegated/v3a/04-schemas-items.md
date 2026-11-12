# Цель
Pydantic-схемы предметов под контракт v3.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 6.1, 6.2), `backend/app/schemas/items.py`.

# Область
Только `backend/app/schemas/items.py`.

# Что сделать (всё не упомянутое — оставить)
- `Slot = Literal["wP", "wN", "wB", "wR", "wQ", "wK", "bP", "bN", "bB", "bR", "bQ", "bK", "board"]`. `DefKind = Literal["piece", "board"]`. `CaseKind = Literal["set", "collection", "custom"]`.
- Вернуть `BoardAsset` (`extra="forbid"`, `type: Literal["stub"]`, `light: HexColor`, `dark: HexColor`).
- Выход: `SetRef {code, name}`; `CollectionRef` — как есть; `ItemDefOut {id, code, name, kind: DefKind, side: Side | None, piece_type: PieceType | None, rarity, value, asset: PieceAsset | BoardAsset, set: SetRef, collection: CollectionRef | None}`; `CaseRefOut {id, code, name, kind: str, price}`; `ItemOut {id, kind: Literal["skin", "case"], item_def: ItemDefOut | None = Field(alias="def"), case: CaseRefOut | None, wear: float | None, exterior: str | None, status, equipped_slot: Slot | None, source, bound: bool, acquired_at}` (`populate_by_name=True`, как сейчас).
- `LoadoutOut`: 13 полей `ItemOut | None` (12 фигур + `board`) и `complete: bool`.
- `ShopCaseOut`, `CaseDetailOut(ShopCaseOut)` (+ `on_sale_now: bool`, `drops: list[CaseDropOut]`), `CaseBuyOut {item: ItemOut, balance: int}`, `CaseOpenOut {item, strip, win_index, defs}` (БЕЗ `balance`), `PublicSetOut`, `SetCollectionOut {code, name, description, items: list[ItemDefOut]}`, `SetDetailOut {code, name, description, status, released_at, collections: list[SetCollectionOut], boards: list[ItemDefOut]}`, `CollectionDetailOut {code, name, description, set: SetRef, items}`, `DailyRewardOut`, `DailyRewardClaimOut {case: CaseRefOut, item: ItemOut, roll_id: int}` — поля ровно по п. 6.1. Удалить `CaseOut`, `PublicCollectionOut`.
- Админ-выход: `AdminSetOut`, `AdminSetCollectionOut {id, code, name, description, items: list[ItemDefOut]}`, `AdminSetDetailOut(AdminSetOut)` (+ `collections: list[AdminSetCollectionOut]`, `boards: list[ItemDefOut]`), `AdminCaseOut` (поля ровно п. 6.1, `drops: list[AdminDropOut]`), `DailyPoolEntryOut {case: CaseRefOut, weight: int}`. Удалить `AdminCollectionOut`, `AdminCollectionDetailOut`.
- Вход: `SetCreateIn {code: SlugCode, name: NameStr, description: DescriptionStr}`, `SetPatchIn {name?, description?}`; `CollectionCreateIn`, `PieceIn` — без изменений; `CollectionPatchIn` — без изменений; `BoardCreateIn {code: SlugCode, name: NameStr, rarity: Rarity, value: int = Field(ge=1, le=10_000_000), asset: BoardAsset, is_upgrade_target: bool = True}`; `ItemDefPatchIn` — `asset: PieceAsset | BoardAsset | None = None`, остальное как есть.
- `CaseCreateIn {code, name, price (1…10 000 000), sort: int = 0, kind: CaseKind, set_id: int | None = None, collection_id: int | None = None, stock_limit: int | None = Field(default=None, ge=1), sale_starts_at: datetime | None = None, sale_ends_at: datetime | None = None}` + `@model_validator(mode="after")`: `kind == "set"` ⇔ `set_id` задан и `collection_id is None`; `kind == "collection"` ⇔ `collection_id` задан и `set_id is None`; `kind == "custom"` ⇒ оба None; если оба времени заданы — `sale_starts_at < sale_ends_at`; иначе `ValueError` с русским текстом.
- `CasePatchIn {name?, price?, sort?, stock_limit: int | None = Field(default=None, ge=1), sale_starts_at: datetime | None = None, sale_ends_at: datetime | None = None}` (сервис различает «не передано» и `null` через `model_fields_set`).
- `AutoDropsIn {set_ids: conlist(int, max_length=20) = [], collection_ids: conlist(int, max_length=20) = []}` + валидатор без повторов в каждом списке.
- `DailyPoolEntryIn {case_id: int, weight: int = Field(ge=1)}`; `DailyPoolIn(RootModel[list[DailyPoolEntryIn]])` с валидатором: длина ≤ 50, без повторов `case_id`.
- `GrantItemIn {item_def_id: int | None = None, case_id: int | None = None}` + валидатор «ровно одно».

# Готово, когда
`python3 -m py_compile backend/app/schemas/items.py` без ошибок.

# Общие правила
- ЕДИНСТВЕННЫЙ источник истины — `docs/contracts-collections.md` (контракт предметов v3). Имена, поля, коды ошибок, тексты — дословно оттуда.
- Ошибки — только `AppError(status, code, message)` из `app.core.errors`.
- Python 3.12, type hints, async SQLAlchemy 2.0 (`select()`). Время — только `clock.now()` (`import app.core.clock as clock`). Случайность — только `get_rng()` из `app.services.rolls`. Любой `FOR UPDATE` — с `.execution_options(populate_existing=True)`. Баланс — только `economy.apply_delta`.
- Порядок блокировок: `market_listings` → `inventory_items` → `cases` → `games` → `users`.
- Тесты бэкенда в этой волне НЕ запускаются и могут падать — их чинит отдельная волна. Тесты не трогать.
- Менять только файлы из раздела «Область». Не добавлять зависимостей.
- Если что-то не сходится с контрактом или кодом — не придумывать обход, остановиться и описать проблему в SUMMARY.
