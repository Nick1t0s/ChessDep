from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel, conlist, constr
from pydantic import model_validator

from app.chess_engine import format_chance

Rarity = Literal["common", "uncommon", "rare", "epic", "legendary", "mythic"]
PieceType = Literal["P", "N", "B", "R", "Q", "K"]
Slot = Literal["P", "N", "B", "R", "Q", "K", "board"]

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


class BoardAsset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["stub"]
    light: HexColor
    dark: HexColor


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
    kind: str
    piece_type: PieceType | None
    rarity: str
    value: int
    asset: PieceAsset | BoardAsset
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

    P: ItemOut | None
    N: ItemOut | None
    B: ItemOut | None
    R: ItemOut | None
    Q: ItemOut | None
    K: ItemOut | None
    board: ItemOut | None


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
    collection: CollectionRef


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


class CollectionCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: SlugCode
    name: NameStr
    description: DescriptionStr


class CollectionPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NameStr | None = None
    description: DescriptionStr | None = None


class ItemDefCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: SlugCode
    name: NameStr
    kind: Literal["piece_skin", "board_skin"]
    piece_type: PieceType | None = None
    rarity: Rarity
    value: int = Field(ge=1, le=10_000_000)
    asset: PieceAsset | BoardAsset
    is_upgrade_target: bool = True

    @model_validator(mode="after")
    def check_kind(self) -> "ItemDefCreateIn":
        if self.kind == "piece_skin":
            if self.piece_type is None:
                raise ValueError("Для piece_skin обязателен piece_type")
            if not isinstance(self.asset, PieceAsset):
                raise ValueError("Для piece_skin нужен asset вида PieceAsset")
        else:
            if self.piece_type is not None:
                raise ValueError("Для board_skin piece_type не указывается")
            if not isinstance(self.asset, BoardAsset):
                raise ValueError("Для board_skin нужен asset вида BoardAsset")
        return self


class ItemDefPatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NameStr | None = None
    kind: Literal["piece_skin", "board_skin"] | None = None
    piece_type: PieceType | None = None
    rarity: Rarity | None = None
    value: int | None = Field(default=None, ge=1, le=10_000_000)
    asset: PieceAsset | BoardAsset | None = None
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
    is_active: bool | None = None
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

    kind: Literal["piece_skin", "board_skin"] | None = None


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
    cases_count: int


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
    collection: CollectionRef
    is_active: bool
    sort: int
    drops: list[AdminDropOut]


class AdminCollectionDetailOut(AdminCollectionOut):
    items: list[ItemDefOut]
    cases: list[AdminCaseOut]
