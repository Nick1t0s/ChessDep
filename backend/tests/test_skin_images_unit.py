import io

import pytest
from PIL import Image

from app.core.errors import AppError
from app.services.skin_images import (
    MAX_UPLOAD_BYTES,
    BAD_BOARD_SIZE,
    BAD_PIECE_SIZE,
    NOT_PNG,
    NOT_TRANSPARENT,
    TOO_BIG,
    normalize_png,
)


def _png(size, mode="RGBA", color=(0, 0, 0, 0)):
    buf = io.BytesIO()
    Image.new(mode, size, color).save(buf, format="PNG")
    return buf.getvalue()


def _expect(exc, message, const):
    assert exc.value.code == "SKIN_IMAGE_INVALID"
    assert exc.value.message == message
    assert exc.value is const


def test_piece_ok():
    buf = io.BytesIO()
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    img.putpixel((64, 64), (255, 0, 0, 255))
    img.save(buf, format="PNG")
    out = normalize_png("piece", buf.getvalue())
    res = Image.open(io.BytesIO(out))
    assert res.size == (128, 128)
    assert res.mode == "RGBA"


def test_board_ok():
    out = normalize_png("board", _png((1088, 1088), "RGB", (10, 20, 30)))
    res = Image.open(io.BytesIO(out))
    assert res.size == (1088, 1088)


def test_not_png():
    with pytest.raises(AppError) as exc:
        normalize_png("piece", b"hello")
    _expect(exc, "Нужен файл PNG", NOT_PNG)

    with pytest.raises(AppError) as exc:
        normalize_png("piece", b"")
    _expect(exc, "Нужен файл PNG", NOT_PNG)

    buf = io.BytesIO()
    Image.new("RGB", (128, 128)).save(buf, format="JPEG")
    with pytest.raises(AppError) as exc:
        normalize_png("piece", buf.getvalue())
    _expect(exc, "Нужен файл PNG", NOT_PNG)


def test_too_big():
    with pytest.raises(AppError) as exc:
        normalize_png("piece", b"0" * (MAX_UPLOAD_BYTES + 1))
    _expect(exc, "Файл больше 8 МБ", TOO_BIG)


def test_bad_sizes():
    with pytest.raises(AppError) as exc:
        normalize_png("piece", _png((64, 64)))
    _expect(exc, "Фигура должна быть PNG 128×128", BAD_PIECE_SIZE)

    with pytest.raises(AppError) as exc:
        normalize_png("board", _png((1024, 1024)))
    _expect(exc, "Доска должна быть PNG 1088×1088", BAD_BOARD_SIZE)


def test_piece_opaque_background():
    with pytest.raises(AppError) as exc:
        normalize_png("piece", _png((128, 128), "RGB", (10, 20, 30)))
    _expect(exc, "У фигуры должен быть прозрачный фон", NOT_TRANSPARENT)
