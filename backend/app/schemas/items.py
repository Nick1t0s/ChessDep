from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, conlist, constr
from pydantic import model_validator

from app.chess_engine import format_chance

Rarity = Literal["common", "uncommon", "rare", "epic", "legendary", "mythic"]
PieceType = Literal["P", "N", "B", "R", "Q", "K"]
Side = Literal["w", "b"]
Slot = Literal["wP", "wN", "wB", "wR", "wQ", "wK", "bP", "bN", "bB", "bR", "bQ", "bK", "board"]
DefKind = Literal["piece", "board"]
Exterior = Literal["FN", "MW", "FT", "WW", "BS"]
EXTERIORS: tuple[str, ...] = ("FN", "MW", "FT", "WW", "BS")
CaseKind = Literal["set", "collection", "custom"]

ImageId = constr(pattern=r"^[0-9a-f]{64}$")
SlugCode = constr(pattern=r"^[a-z0-9-]{2,40}$")

NameStr = constr(min_length=1, max_length=60)
DescriptionStr = constr(max_length=500)

RARITY_ORDER: dict[str, int] = {
    "common": 1,
    "uncommon": 2,
    "rare": 3,
    "epic": 4,
    "legendary": 5,
    "mythic": 6,
}


def exterior(wear: float) -> str:
    """Exterior по границам TZ 4.3 (левая граница включительно)."""
    if wear < 0.07:
        return "FN"
    if wear < 0.15:
        return "MW"
    if wear < 0.38:
        return "FT"
    if wear < 0.45:
        return "WW"
    return "BS"


def resolve_image(asset: dict, ext: str) -> str:
    """Картинка скина для качества ext (asset.exteriors обязателен)."""
    return asset["exteriors"][ext]


class SkinAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["png"]
    image: ImageId
    exteriors: dict[Exterior, ImageId]

    @model_validator(mode="after")
    def check_exteriors(self) -> "SkinAsset":
        if set(self.exteriors) != set(EXTERIORS):
            raise ValueError("Нужны картинки для всех качеств: FN, MW, FT, WW, BS")
        return self


# --- Выходные схемы ---------------------------------------------------------


class SetRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str


class CollectionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str


class ItemDefOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    code: str
    name: str
    kind: DefKind
    side: Side | None
    piece_type: PieceType | None
    rarity: str
    value: int
    asset: SkinAsset
    set: SetRef
    collection: CollectionRef | None


class SkinImageOut(BaseModel):
    image: str
    kind: Literal["piece", "board"]
    url: str


class CaseRefOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    code: str
    name: str
    kind: str
    price: int


class ItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: int
    kind: Literal["skin", "case"]
    item_def: ItemDefOut | None = Field(alias="def")
    case: CaseRefOut | None
    wear: float | None
    exterior: str | None
    image: str | None
    status: str
    equipped_slot: Slot | None
    source: str
    bound: bool
    acquired_at: datetime


class LoadoutOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wP: ItemOut | None
    wN: ItemOut | None
    wB: ItemOut | None
    wR: ItemOut | None
    wQ: ItemOut | None
    wK: ItemOut | None
    bP: ItemOut | None
    bN: ItemOut | None
    bB: ItemOut | None
    bR: ItemOut | None
    bQ: ItemOut | None
    bK: ItemOut | None
    board: ItemOut | None
    complete: bool


class PublicSetOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    description: str
    status: str
    released_at: datetime | None
    collections_count: int
    boards_count: int


class SetCollectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    description: str
    items: list[ItemDefOut]


class SetDetailOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    description: str
    status: str
    released_at: datetime | None
    collections: list[SetCollectionOut]
    boards: list[ItemDefOut]


class CollectionDetailOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    description: str
    set: SetRef
    items: list[ItemDefOut]


class ShopCaseOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    code: str
    name: str
    kind: str
    set: SetRef | None
    collection: CollectionRef | None
    price: int
    stock_limit: int | None
    stock_left: int | None
    sale_starts_at: datetime | None
    sale_ends_at: datetime | None


class CaseDropOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    item_def: ItemDefOut = Field(alias="def")
    weight: int
    chance: float
    chance_text: str


class CaseDetailOut(ShopCaseOut):
    on_sale_now: bool
    drops: list[CaseDropOut]


class CaseBuyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: ItemOut
    balance: int


class CaseOpenOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: ItemOut
    strip: list[int]
    win_index: int
    defs: dict[str, ItemDefOut]


class DailyRewardOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wins_today: int
    wins_required: int
    claimed_today: bool
    available: bool


class DailyRewardClaimOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: CaseRefOut
    item: ItemOut
    roll_id: int


class UpgradeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_ids: conlist(int, min_length=1, max_length=50)  # type: ignore[valid-type]
    target_def_id: int


class UpgradePreviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chance: float
    chance_text: str
    allowed: bool
    reason: str | None


class UpgradeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    success: bool
    chance: float
    chance_text: str
    roll_value: float
    roll_id: int
    burned_ids: list[int]
    item: ItemOut | None


# --- Роутер-входы -----------------------------------------------------------


class LoadoutPutIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    inventory_item_id: int | None


# --- Админка каталога (входы) ------------------------------------------------


class PieceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    side: Side
    piece_type: PieceType
    rarity: Rarity
    value: int = Field(ge=1, le=10_000_000)
    asset: SkinAsset
    is_upgrade_target: bool = True


class CollectionCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: SlugCode
    name: NameStr
    description: DescriptionStr
    pieces: list[PieceIn]

    @model_validator(mode="after")
    def check_pieces(self) -> "CollectionCreateIn":
        keys = [p.side + p.piece_type for p in self.pieces]
        if len(keys) != 12 or len(set(keys)) != 12:
            raise ValueError("Нужно ровно 12 фигур: по одной на каждую сторону и тип")
        return self


class CollectionPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NameStr | None = None
    description: DescriptionStr | None = None


class BoardCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: SlugCode
    name: NameStr
    rarity: Rarity
    value: int = Field(ge=1, le=10_000_000)
    asset: SkinAsset
    is_upgrade_target: bool = True


class ItemDefPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NameStr | None = None
    rarity: Rarity | None = None
    value: int | None = Field(default=None, ge=1, le=10_000_000)
    asset: SkinAsset | None = None
    is_upgrade_target: bool | None = None


class SetCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: SlugCode
    name: NameStr
    description: DescriptionStr


class SetPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NameStr | None = None
    description: DescriptionStr | None = None


class CaseCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: SlugCode
    name: NameStr
    price: int = Field(ge=1, le=10_000_000)
    sort: int = 0
    kind: CaseKind
    set_id: int | None = None
    collection_id: int | None = None
    stock_limit: int | None = Field(default=None, ge=1)
    sale_starts_at: datetime | None = None
    sale_ends_at: datetime | None = None

    @model_validator(mode="after")
    def check_refs_and_window(self) -> "CaseCreateIn":
        if self.kind == "set":
            if self.set_id is None or self.collection_id is not None:
                raise ValueError("Для kind='set' требуется set_id, а collection_id должен отсутствовать")
        elif self.kind == "collection":
            if self.collection_id is None or self.set_id is not None:
                raise ValueError("Для kind='collection' требуется collection_id, а set_id должен отсутствовать")
        elif self.set_id is not None or self.collection_id is not None:
            raise ValueError("Для kind='custom' нельзя указывать set_id и collection_id")
        if (
            self.sale_starts_at is not None
            and self.sale_ends_at is not None
            and self.sale_starts_at >= self.sale_ends_at
        ):
            raise ValueError("sale_starts_at должна быть раньше sale_ends_at")
        return self


class CasePatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NameStr | None = None
    price: int | None = Field(default=None, ge=1, le=10_000_000)
    sort: int | None = None
    stock_limit: int | None = Field(default=None, ge=1)
    sale_starts_at: datetime | None = None
    sale_ends_at: datetime | None = None


class DropIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_def_id: int
    weight: int = Field(ge=1)


class DropsIn(RootModel[list[DropIn]]):
    @model_validator(mode="after")
    def no_duplicates(self) -> "DropsIn":
        ids = [d.item_def_id for d in self.root]
        if len(set(ids)) != len(ids):
            raise ValueError("Повторяющиеся item_def_id в дропах")
        return self


class AutoDropsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    set_ids: conlist(int, max_length=20) = []  # type: ignore[valid-type]
    collection_ids: conlist(int, max_length=20) = []  # type: ignore[valid-type]

    @model_validator(mode="after")
    def no_duplicates(self) -> "AutoDropsIn":
        if len(set(self.set_ids)) != len(self.set_ids):
            raise ValueError("Повторяющиеся set_ids")
        if len(set(self.collection_ids)) != len(self.collection_ids):
            raise ValueError("Повторяющиеся collection_ids")
        return self


class DailyPoolEntryIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: int
    weight: int = Field(ge=1)


class DailyPoolIn(RootModel[list[DailyPoolEntryIn]]):
    @model_validator(mode="after")
    def no_duplicates(self) -> "DailyPoolIn":
        if len(self.root) > 50:
            raise ValueError("В пуле награды не может быть больше 50 кейсов")
        ids = [e.case_id for e in self.root]
        if len(set(ids)) != len(ids):
            raise ValueError("Повторяющиеся case_id в пуле награды")
        return self


class GrantItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_def_id: int | None = None
    case_id: int | None = None

    @model_validator(mode="after")
    def exactly_one(self) -> "GrantItemIn":
        if (self.item_def_id is None) == (self.case_id is None):
            raise ValueError("Нужно ровно одно: item_def_id или case_id")
        return self


# --- Админка каталога (выходы) ------------------------------------------------


class AdminSetOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    code: str
    name: str
    description: str
    status: str
    is_base: bool
    created_at: datetime
    released_at: datetime | None
    retired_at: datetime | None
    collections_count: int
    boards_count: int


class AdminSetCollectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    code: str
    name: str
    description: str
    items: list[ItemDefOut]


class AdminSetDetailOut(AdminSetOut):
    collections: list[AdminSetCollectionOut]
    boards: list[ItemDefOut]


class AdminDropOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_def_id: int
    weight: int


class AdminCaseOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    code: str
    name: str
    kind: str
    set: SetRef | None
    collection: CollectionRef | None
    price: int
    sort: int
    status: str
    stock_limit: int | None
    sold_count: int
    sale_starts_at: datetime | None
    sale_ends_at: datetime | None
    on_sale_now: bool
    drops: list[AdminDropOut]


class DailyPoolEntryOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case: CaseRefOut
    weight: int
