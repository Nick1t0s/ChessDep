# Цель
Написать скрипт `scripts/gen_seed_images.py`, запустить его и закоммитить 27 PNG-заглушек в `backend/app/seed_images/`.

# Контекст
Прочитай `docs/contracts-skins.md` (§1, §5) и `backend/app/seed_skins.py` (там список имён `SEED_IMAGE_NAMES`, 27 штук).
Pillow стоит в системном python3 (`python3 -c "import PIL"`). Шрифт: `/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf`.

# Область
Создать: `scripts/gen_seed_images.py` и папку `backend/app/seed_images/` с 27 файлами `<name>.png`. Больше ничего не трогать.

# Контракт скрипта
- Запуск: `python3 scripts/gen_seed_images.py` из корня репозитория; пишет файлы в `backend/app/seed_images/` (создаёт папку `os.makedirs(..., exist_ok=True)`), печатает имя каждого файла.
- Импортировать `SEED_IMAGE_NAMES` нельзя (там нужен пакет app) — список имён построй в скрипте сам, в том же порядке:
  `base-wp base-wn base-wb base-wr base-wq base-wk base-bp base-bn base-bb base-br base-bq base-bk base-board genesis-wp … genesis-bk genesis-board-paper genesis-board-albion`.
- **Фигура** (имя без `board`): `Image.new("RGBA", (128, 128), (0, 0, 0, 0))`. Глиф берётся из ЗАЛИТЫХ символов для обеих сторон: `{"p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚"}` по последней букве имени. Шрифт `ImageFont.truetype(FONT, 104)`. Рисовать `draw.text((64, 68), ch, font=font, fill=COLOR, anchor="mm", stroke_width=3, stroke_fill="#000000")`.
  Цвета COLOR: `base` + `w` → `#f4f6ff`, `base` + `b` → `#ff5470`, `genesis` + `w` → `#ffffff`, `genesis` + `b` → `#ffc93c` (сторона — предпоследняя буква имени).
- **Доска** (имя содержит `board`): `Image.new("RGB", (1088, 1088), FRAME)`, затем 64 клетки прямоугольниками `draw.rectangle([x, y, x + 127, y + 127], fill=...)`, где `x = 32 + col * 128`, `y = 32 + row * 128`, `row, col` в 0..7; клетка светлая, если `(row + col) % 2 == 0`, иначе тёмная.
  Цвета (light, dark, FRAME): `base-board` → `#454f77`, `#262e4d`, `#1a2038`; `genesis-board-paper` → `#ffffff`, `#e5e5e5`, `#b8b8b8`; `genesis-board-albion` → `#ffffff`, `#c9d1e0`, `#8a93a8`.
- Сохранять `img.save(path, format="PNG", optimize=True)`.
- В начале файла docstring: `"""Генерирует PNG-заглушки сида в backend/app/seed_images/ (docs/contracts-skins.md §5). Запуск руками, результат коммитится."""`

# Готово, когда
Команда печатает `27 ok`:
```
python3 scripts/gen_seed_images.py && python3 -c "
from PIL import Image; import glob
fs=sorted(glob.glob('backend/app/seed_images/*.png')); assert len(fs)==27, len(fs)
for f in fs:
    im=Image.open(f)
    if 'board' in f: assert im.size==(1088,1088), f
    else:
        assert im.size==(128,128), f; im=im.convert('RGBA')
        assert all(im.getpixel(p)[3]==0 for p in [(0,0),(127,0),(0,127),(127,127)]), f
print(len(fs),'ok')"
```
PNG-файлы и скрипт закоммичены.

# Нельзя
Трогать другие файлы, ставить пакеты, менять размеры/цвета. Если шрифта нет или что-то не сходится — остановиться и описать в SUMMARY.
