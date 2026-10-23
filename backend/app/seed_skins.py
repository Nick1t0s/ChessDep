"""PNG-заглушки сида: файлы app/seed_images/<name>.png (генерирует scripts/gen_seed_images.py).

Используют seed_data.py (id картинок в asset), миграция 0008, tests/conftest.py (строки skin_images),
seed_asset — asset скинов сида и тестов.
"""
import hashlib
from functools import cache
from pathlib import Path

from app.schemas.items import EXTERIORS

SEED_IMAGES_DIR = Path(__file__).parent / "seed_images"

# Те же слоты, что seed_data.CANONICAL_SLOTS (импорт оттуда дал бы цикл: seed_data импортирует этот модуль).
_SLOTS: tuple[str, ...] = tuple(s + p for s in ("w", "b") for p in ("P", "N", "B", "R", "Q", "K"))

SEED_IMAGE_NAMES: tuple[str, ...] = (
    *(f"base-{slot.lower()}" for slot in _SLOTS),
    "base-board",
    *(f"genesis-{slot.lower()}" for slot in _SLOTS),
    "genesis-board-paper",
    "genesis-board-albion",
)


def _kind(name: str) -> str:
    return "board" if "board" in name else "piece"


@cache
def _read(name: str) -> bytes:
    return (SEED_IMAGES_DIR / f"{name}.png").read_bytes()


@cache
def seed_image_id(name: str) -> str:
    return hashlib.sha256(_read(name)).hexdigest()


def seed_image_rows() -> list[dict]:
    return [
        {"id": seed_image_id(name), "kind": _kind(name), "data": _read(name)}
        for name in SEED_IMAGE_NAMES
    ]


def seed_asset(name: str) -> dict:
    """asset скина сида: картинка name основной и во всех качествах."""
    image = seed_image_id(name)
    return {"type": "png", "image": image, "exteriors": {ext: image for ext in EXTERIORS}}
