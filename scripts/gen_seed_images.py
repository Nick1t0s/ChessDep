"""Генерирует PNG-заглушки сида в backend/app/seed_images/ (docs/contracts-skins.md §5). Запуск руками, результат коммитится."""
import os

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SEED_IMAGES_DIR = os.path.join("backend", "app", "seed_images")

SEED_IMAGE_NAMES = (
    "base-wp", "base-wn", "base-wb", "base-wr", "base-wq", "base-wk",
    "base-bp", "base-bn", "base-bb", "base-br", "base-bq", "base-bk",
    "base-board",
    "genesis-wp", "genesis-wn", "genesis-wb", "genesis-wr", "genesis-wq", "genesis-wk",
    "genesis-bp", "genesis-bn", "genesis-bb", "genesis-br", "genesis-bq", "genesis-bk",
    "genesis-board-paper", "genesis-board-albion",
)

GLYPHS = {"p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚"}

PIECE_COLORS = {
    ("base", "w"): "#f4f6ff",
    ("base", "b"): "#ff5470",
    ("genesis", "w"): "#ffffff",
    ("genesis", "b"): "#ffc93c",
}

BOARDS = {
    "base-board": ("#454f77", "#262e4d", "#1a2038"),
    "genesis-board-paper": ("#ffffff", "#e5e5e5", "#b8b8b8"),
    "genesis-board-albion": ("#ffffff", "#c9d1e0", "#8a93a8"),
}


def gen_piece(name: str) -> Image.Image:
    prefix, side, piece_type = name[:-3], name[-2], name[-1]
    img = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 104)
    draw.text(
        (64, 68), GLYPHS[piece_type], font=font,
        fill=PIECE_COLORS[(prefix, side)], anchor="mm",
        stroke_width=3, stroke_fill="#000000",
    )
    return img


def gen_board(name: str) -> Image.Image:
    light, dark, frame = BOARDS[name]
    img = Image.new("RGB", (1088, 1088), frame)
    draw = ImageDraw.Draw(img)
    for row in range(8):
        for col in range(8):
            x, y = 32 + col * 128, 32 + row * 128
            fill = light if (row + col) % 2 == 0 else dark
            draw.rectangle([x, y, x + 127, y + 127], fill=fill)
    return img


def main() -> None:
    os.makedirs(SEED_IMAGES_DIR, exist_ok=True)
    for name in SEED_IMAGE_NAMES:
        img = gen_board(name) if "board" in name else gen_piece(name)
        path = os.path.join(SEED_IMAGES_DIR, f"{name}.png")
        img.save(path, format="PNG", optimize=True)
        print(name)


if __name__ == "__main__":
    main()
