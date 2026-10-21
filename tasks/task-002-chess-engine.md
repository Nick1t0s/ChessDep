# task-002 — Шахматный движок с депами (чистый модуль)

Прочитай перед работой: `docs/TZ.md`, раздел 3 целиком.

## Правила для исполнителя
Те же, что в task-001. Отдельно для этой задачи:
1. Модуль `app/chess_engine/` **чистый**: никаких импортов `sqlalchemy`, `fastapi`, `redis`, `app.db`, `app.services`, `app.core`, никакого I/O, никакой случайности (`random`, `secrets`). Бросок `roll_value` приходит снаружи аргументом.
2. Функции **не мутируют** входной `chess.Board`: работают с копией `board.copy(stack=False)`.
3. На `board.move_stack` не полагаться никогда: состояние партии — только FEN.
4. Лимиты «1 деп за ход» и «10 за партию», часы, БД — **не** в этой задаче (это task-003). Здесь только правила позиции.
5. Все FEN в тестах ниже проверены на python-chess 1.11.1. Если ожидание в тесте не сходится, это баг в твоём коде, а не в FEN. Тесты и FEN не меняй; если уверен, что ошибка в задании, остановись и спроси.

---

## 1. Файлы

```
backend/app/chess_engine/__init__.py     # реэкспорт публичного API (всё из списка ниже)
backend/app/chess_engine/constants.py
backend/app/chess_engine/errors.py
backend/app/chess_engine/dep.py
backend/app/chess_engine/game.py
backend/tests/test_chess_engine.py
```

## 2. `constants.py`
```python
import chess

PIECE_VALUES: dict[int, int] = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9,
}
DEP_TARGETS: dict[int, tuple[int, ...]] = {
    chess.PAWN: (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN),
    chess.KNIGHT: (chess.ROOK, chess.QUEEN),
    chess.BISHOP: (chess.ROOK, chess.QUEEN),
    chess.ROOK: (chess.QUEEN,),
}
DEP_LIMIT_PER_GAME = 10
LETTER_TO_TYPE: dict[str, int] = {"P": chess.PAWN, "N": chess.KNIGHT, "B": chess.BISHOP,
                                  "R": chess.ROOK, "Q": chess.QUEEN, "K": chess.KING}
TYPE_TO_LETTER: dict[int, str] = {v: k for k, v in LETTER_TO_TYPE.items()}
COLOR_NAME: dict[bool, str] = {chess.WHITE: "white", chess.BLACK: "black"}
```

## 3. `errors.py`
```python
class EngineError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
```
Коды: `ILLEGAL_MOVE`, `DEP_INVALID_PIECE`, `DEP_INVALID_TARGET`, `WOULD_CHECK_OPPONENT`.

## 4. `dep.py`

```python
@dataclass(frozen=True)
class DepTarget:
    piece: str            # "N" | "B" | "R" | "Q"
    chance: float
    chance_text: str
    allowed: bool
    reason: str | None    # None | "WOULD_CHECK_OPPONENT"

@dataclass(frozen=True)
class DepPieceOption:
    square: str           # "c3"
    piece: str            # "P" | "N" | "B" | "R"
    targets: tuple[DepTarget, ...]

@dataclass(frozen=True)
class DepResolution:
    success: bool
    square: str
    from_piece: str
    to_piece: str
    chance: float
    chance_text: str
    roll_value: float
    board: chess.Board    # позиция после исхода; ход всё ещё за тем же игроком
```

Функции (сигнатуры ровно такие):

```python
def dep_chance(from_letter: str, to_letter: str, multiplier: float) -> float
```
`PIECE_VALUES[from] / PIECE_VALUES[to] * multiplier`, обрезать в `[0.0, 1.0]`. Пара не из `DEP_TARGETS` (или неизвестная буква) → `EngineError("DEP_INVALID_TARGET")`. Без округления.

```python
def format_chance(chance: float) -> str
```
`f"{chance * 100:.2f}%"`. Пример: `1/3` → `"33.33%"`, `0.6` → `"60.00%"`.

```python
def apply_dep_outcome(board: chess.Board, square: int, target: int | None) -> chess.Board
```
На копии доски:
1. запомнить цвет фигуры на `square`, снять её (`remove_piece_at`);
2. если `target is not None` — поставить `chess.Piece(target, color)` на ту же клетку;
3. `b.castling_rights = b.clean_castling_rights()`;
4. если `b.ep_square is not None and not b.has_legal_en_passant()` → `b.ep_square = None`;
5. `b.halfmove_clock = 0`;
6. `turn` и `fullmove_number` не трогать.

```python
def validate_dep(board: chess.Board, square_name: str, target_letter: str) -> tuple[int, int]
```
Возвращает `(square, target_type)` или бросает `EngineError`. Порядок проверок:
1. `square_name` не парсится (`chess.parse_square` → `ValueError`) → `DEP_INVALID_PIECE`;
2. на клетке нет фигуры, или она не цвета `board.turn`, или её тип не в `DEP_TARGETS` (король, ферзь) → `DEP_INVALID_PIECE`;
3. `target_letter` не в `LETTER_TO_TYPE` или тип не в `DEP_TARGETS[piece_type]` → `DEP_INVALID_TARGET`;
4. если `_gives_check(apply_dep_outcome(board, sq, target))` **или** `_gives_check(apply_dep_outcome(board, sq, None))` → `WOULD_CHECK_OPPONENT`.

Приватный хелпер:
```python
def _gives_check(b: chess.Board) -> bool:
    king = b.king(not b.turn)
    return king is not None and b.is_attacked_by(b.turn, king)
```

```python
def list_dep_options(board: chess.Board, multiplier: float) -> list[DepPieceOption]
```
Все фигуры цвета `board.turn` с типом из `DEP_TARGETS`. Сортировка по индексу клетки по возрастанию (a1=0 … h8=63). Цели — в порядке кортежа `DEP_TARGETS`. Для каждой цели `allowed`/`reason` — по шагу 4 `validate_dep`. Король и ферзи в список не попадают.

```python
def resolve_dep(board: chess.Board, square_name: str, target_letter: str,
                roll_value: float, multiplier: float) -> DepResolution
```
1. `if not 0.0 <= roll_value < 1.0: raise ValueError("roll_value out of range")`;
2. `validate_dep` (пробрасывает `EngineError`);
3. `chance = dep_chance(...)`; `success = roll_value < chance` (строго меньше);
4. `board = apply_dep_outcome(board, sq, target if success else None)`;
5. вернуть `DepResolution`.

## 5. `game.py`

```python
@dataclass(frozen=True)
class Outcome:
    result: str       # "white" | "black" | "draw"
    end_reason: str   # "checkmate" | "stalemate" | "insufficient_material" | "fifty_move" | "threefold"

@dataclass(frozen=True)
class MoveResult:
    board: chess.Board   # новая позиция, пустой move_stack
    uci: str
    san: str
    irreversible: bool   # board.is_irreversible(move), вычислить ДО хода
```

```python
def apply_move(board: chess.Board, uci: str) -> MoveResult
```
`chess.Move.from_uci` бросил `ValueError` или ход не в `board.legal_moves` → `EngineError("ILLEGAL_MOVE")`. `san = board.san(move)` и `irreversible` считать до хода. Затем копия, `push(move)`, вернуть `chess.Board(after.fen())` (чтобы стек был пустым).

```python
def game_outcome(board: chess.Board, repetition_count: int = 1) -> Outcome | None
```
Строго в этом порядке:
1. `board.is_checkmate()` → победитель — сторона, которая **не** ходит (`COLOR_NAME[not board.turn]`), `"checkmate"`;
2. `board.is_stalemate()` → `draw`, `"stalemate"`;
3. `board.is_insufficient_material()` → `draw`, `"insufficient_material"`;
4. `board.halfmove_clock >= 100` → `draw`, `"fifty_move"`;
5. `repetition_count >= 3` → `draw`, `"threefold"`;
6. иначе `None`.

Функция вызывается и после хода, и после депа. После депа ход за тем же игроком, поэтому мат означает мат ему самому: это ожидаемое поведение (TZ 3.5).

```python
def legal_moves_uci(board: chess.Board) -> list[str]           # отсортированный список uci
def board_squares(board: chess.Board) -> list[dict[str, str]]  # [{"square":"e1","piece":"K","color":"white"}], по индексу клетки
def position_key(board: chess.Board) -> str                    # " ".join(board.fen(en_passant="legal").split()[:4])
def can_win_on_time(board: chess.Board, color: str) -> bool    # not board.has_insufficient_material(<color>)
```
`color` в `can_win_on_time` — `"white"` или `"black"`, иначе `ValueError`.

## 6. Тесты `backend/tests/test_chess_engine.py`

Имена ровно такие. `sq = chess.parse_square`. Под «opts(fen)» понимается `{o.square: {t.piece: t.allowed for t in o.targets} for o in list_dep_options(chess.Board(fen), 1.0)}`.

### Шансы и пары
- `test_dep_chances_all_pairs` — все 9 пар при multiplier 1.0 (`pytest.approx`): P→N 1/3, P→B 1/3, P→R 0.2, P→Q 1/9, N→R 0.6, N→Q 1/3, B→R 0.6, B→Q 1/3, R→Q 5/9.
- `test_dep_chance_multiplier_and_clamp` — N→Q при 0.9 = 0.3; R→Q при 2.0 = 1.0 (обрезка); N→Q при 0.0 = 0.0.
- `test_dep_invalid_pairs` — N→B, B→N, Q→K, R→N, P→P, K→Q, "X"→"Q" → `EngineError` с кодом `DEP_INVALID_TARGET`.
- `test_format_chance` — `1/3` → `"33.33%"`, `0.6` → `"60.00%"`, `1/9` → `"11.11%"`, `1.0` → `"100.00%"`.

### Опции депа
- `test_options_start_position` — `chess.STARTING_FEN`: 14 фигур (8P, 2N, 2B, 2R), все цели `allowed=True`; у пешки цели `["N","B","R","Q"]`, у ладьи `["Q"]`; клеток `e1`, `d1` в списке нет.
- `test_options_black_to_move` — старт + `e2e4` (через `apply_move`): 14 фигур, все клетки на 7-й и 8-й горизонталях.
- `test_dep_forbidden_direct_check` — `"4k3/8/4P3/8/8/8/8/4K3 w - - 0 1"`: `opts["e6"] == {"N": True, "B": True, "R": False, "Q": False}`; у запрещённых `reason == "WOULD_CHECK_OPPONENT"`; `validate_dep(b, "e6", "Q")` → `EngineError("WOULD_CHECK_OPPONENT")`.
- `test_dep_forbidden_discovered_check_on_fail` — `"4k3/3N4/2B5/8/8/8/8/4K3 w - - 0 1"`: `opts["d7"] == {"R": False, "Q": False}` (при провале слон c6 вскрывает шах); `opts["c6"]` — все `True`.
- `test_dep_on_en_passant_position` — `"4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"`: `opts["e5"] == {"N": True, "B": True, "R": False, "Q": False}`.

### Ошибки валидации
- `test_validate_dep_invalid_piece` — на старте: `"e1"` (король), `"d1"` (ферзь), `"e7"` (чужая пешка), `"e4"` (пусто), `"z9"` (не клетка) → `DEP_INVALID_PIECE`.
- `test_validate_dep_invalid_target` — на старте: `("b1","B")`, `("b1","K")`, `("b1","x")`, `("a1","R")` → `DEP_INVALID_TARGET`.

### Применение исхода
- `test_dep_success_replaces_piece` — старт, `resolve_dep(b, "b1", "Q", roll_value=0.0, multiplier=1.0)`: `success`, на b1 белый ферзь, `board.turn == WHITE`, входная доска не изменилась (`b.fen() == chess.STARTING_FEN`).
- `test_dep_fail_removes_piece` — старт, `resolve_dep(b, "b1", "Q", 0.99, 1.0)`: `not success`, b1 пуста, входная доска не изменилась.
- `test_dep_roll_boundary` — `"4k3/8/8/8/8/8/P7/4K3 w - - 0 1"`, P→R (chance 0.2): `roll 0.19999` → успех; `roll 0.2` → провал; `roll 1.0` и `-0.01` → `ValueError`.
- `test_dep_allowed_self_discovered_check` — `"4r2k/8/8/8/8/8/4N3/4K3 w - - 0 1"`: `opts["e2"]` — все `True`; после провала (`roll 0.99`, цель `"Q"`): `board.is_check()`, легальные ходы есть, `game_outcome(board) is None`.
- `test_dep_allowed_while_in_check` — `"4k3/8/8/8/8/8/3N4/r3K3 w - - 0 1"` (белые под шахом): `opts["d2"]` — все `True`; после провала всё ещё шах и легальные ходы есть.
- `test_dep_fail_leads_to_selfmate` — `"k7/8/8/8/8/8/6PP/r2N3K w - - 0 1"`: `opts["d1"]` — все `True`; провал → `game_outcome == Outcome("black", "checkmate")`; успех в `"R"` (`roll 0.0`) → `game_outcome is None`.
- `test_dep_fail_leads_to_stalemate` — `"N7/8/8/8/8/7p/5k1P/7K w - - 0 1"`: провал коня a8 → `Outcome("draw", "stalemate")`; успех в `"Q"` → `None`.
- `test_dep_rook_clears_castling` — `"r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1"`: деп h1 (и успех, и провал) → `board.castling_xfen() == "Qkq"`; деп a1 (оба исхода) → `"Kkq"`. Та же позиция с `b` вместо `w`: деп a8 провал → `"KQk"`; деп h8 успех → `"KQq"`.
- `test_dep_clears_en_passant` — `"4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 2"`: до депа `has_legal_en_passant()`; после депа e5 в `"N"` (успех) и после провала → `board.ep_square is None`.
- `test_dep_resets_halfmove_clock` — `"4k3/8/8/8/8/8/P7/4K3 w - - 57 80"`, деп a2→R (любой исход) → `halfmove_clock == 0`, `fullmove_number == 80`.
- `test_dep_insufficient_material` — `"4k3/8/8/8/8/8/P7/4K3 w - - 0 1"`: провал → `Outcome("draw", "insufficient_material")`; успех в `"N"` → тоже `insufficient_material`; успех в `"R"` → `None`.
- `test_dep_probability` — позиция старта, N b1→Q. 10 000 вызовов `resolve_dep` с `roll_value` из `random.Random(42).random()`: доля успехов в `1/3 ± 0.02`. (Модуль `random` разрешён **только в тестах**.)

### Ходы и окончание партии
- `test_apply_move_ok_and_illegal` — старт: `apply_move(b, "e2e4")` → `san == "e4"`, `irreversible is True`, `board.move_stack == []`, входная доска не изменилась; `"e2e5"`, `"zzzz"`, `""` → `EngineError("ILLEGAL_MOVE")`.
- `test_apply_move_promotion` — `"8/P7/8/8/8/8/8/k6K w - - 0 1"`: `"a7a8q"` → на a8 белый ферзь; `"a7a8"` (без фигуры) → `ILLEGAL_MOVE`.
- `test_fools_mate` — старт, ходы `f2f3 e7e5 g2g4 d8h4` через `apply_move` → `game_outcome == Outcome("black", "checkmate")`.
- `test_fifty_move_rule` — `"4k3/8/8/8/8/8/R7/4K3 w - - 99 120"` → `None`; то же с `100` → `Outcome("draw", "fifty_move")`.
- `test_threefold` — старт: `game_outcome(b, 2) is None`, `game_outcome(b, 3) == Outcome("draw", "threefold")`.
- `test_position_key` — ключи `"4k3/8/8/8/8/8/R7/4K3 w - - 5 10"` и `"… w - - 9 30"` равны; ключи `"4k3/8/8/8/3P4/8/8/4K3 b - d3 0 1"` и `"… b - - 0 1"` равны (нелегальное взятие на проходе игнорируется).
- `test_can_win_on_time` — `"4k3/8/8/8/8/8/8/N3K3 w - - 0 1"`: обе стороны `False`; `"4k3/8/8/8/8/8/R7/4K3 w - - 0 1"`: white `True`, black `False`; `"purple"` → `ValueError`.
- `test_board_squares` — старт: 32 элемента, первый `{"square": "a1", "piece": "R", "color": "white"}`, последний `{"square": "h8", "piece": "R", "color": "black"}`.
- `test_legal_moves_uci` — старт: 20 ходов, список отсортирован, содержит `"g1f3"`.

### Чистота модуля
- `test_engine_is_pure` — прочитать исходники всех файлов `app/chess_engine/*.py`; ни один не содержит подстрок `import random`, `import secrets`, `sqlalchemy`, `fastapi`, `redis`, `from app.db`, `from app.services`, `from app.core`.

## 7. Проверка (приложить вывод)
```bash
make test     # все тесты зелёные: 28 старых + новые
```
В конце ответа: список созданных файлов, отступления (или «отступлений нет») и вопросы.
