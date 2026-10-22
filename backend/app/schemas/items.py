from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, conlist, constr
from pydantic import model_validator

from app.chess_engine import format_chance

Rarity = Literal["common", "uncommon", "rare", "epic", "legendary", "mythic"]
PieceType = Literal["P", "N", "B", "R", "Q", "K"]
Side = Literal["w", "b"]
Slot = Literal["wP", "wN", "wB", "wR", "wQ", "wK", "bP", "bN", "bB", "bR", "bQ", "bK"]

HexColor = constr(pattern=r"^#[0-9a-fA-F]{6}$")
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


class PieceAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["stub"]
    color: HexColor


# --- Выходные схемы ---------------------------------------------------------


class CollectionRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str


class ItemDefOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    code: str
    name: str
    side: Side
    piece_type: PieceType
    rarity: str
    value: int
    asset: PieceAsset
    collection: CollectionRef


class ItemOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: int
    item_def: ItemDefOut = Field(alias="def")
    wear: float
    exterior: str
    status: str
    equipped_slot: Slot | None
    source: str
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


class PublicCollectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    description: str
    status: str
    released_at: datetime | None
    items_count: int


class CollectionDetailOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    name: str
    description: str
    status: str
    released_at: datetime | None
    items: list[ItemDefOut]


class CaseOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    code: str
    name: str
    price: int
    collections: list[CollectionRef]


class CaseDropOut(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    item_def: ItemDefOut = Field(alias="def")
    weight: int
    chance: float
    chance_text: str


class CaseDetailOut(CaseOut):
    drops: list[CaseDropOut]


class CaseOpenOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item: ItemOut
    strip: list[int]
    win_index: int
    defs: dict[str, ItemDefOut]
    balance: int


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
    asset: PieceAsset
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


class ItemDefPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NameStr | None = None
    rarity: Rarity | None = None
    value: int | None = Field(default=None, ge=1, le=10_000_000)
    asset: PieceAsset | None = None
    is_upgrade_target: bool | None = None


class CaseCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: SlugCode
    name: NameStr
    price: int = Field(ge=1, le=10_000_000)
    sort: int = 0


class CasePatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NameStr | None = None
    price: int | None = Field(default=None, ge=1, le=10_000_000)
    sort: int | None = None


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

    collection_ids: conlist(int, min_length=1, max_length=20)  # type: ignore[valid-type]

    @model_validator(mode="after")
    def no_duplicates(self) -> "AutoDropsIn":
        if len(set(self.collection_ids)) != len(self.collection_ids):
            raise ValueError("Повторяющиеся collection_ids")
        return self


class GrantItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_def_id: int


# --- Админка каталога (выходы) -----------------------------------------------


class AdminCollectionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    code: str
    name: str
    description: str
    status: str
    created_at: datetime
    released_at: datetime | None
    retired_at: datetime | None
    items_count: int


class AdminDropOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_def_id: int
    weight: int


class AdminCaseOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    code: str
    name: str
    price: int
    status: str
    sort: int
    collections: list[CollectionRef]
    drops: list[AdminDropOut]


class AdminCollectionDetailOut(AdminCollectionOut):
    items: list[ItemDefOut]
