# T2. Часы не идут во время депа (бэкенд)

Worktree: /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t2

Анимация депа на фронте идёт ~2.6 с. Сервер должен «подарить» депающему эти секунды: после депа его часы стоят 3 с.

## 1. `backend/app/services/game_clock.py`
- После импортов добавить константу:
  ```python
  # После депа часы депающего стоят столько, сколько идёт анимация на фронте (+ запас).
  DEP_CLOCK_PAUSE_MS = 3000
  ```
- В `remaining_ms` строку `return max(0, ms - elapsed)` заменить на:
  ```python
          # turn_started_at может быть в будущем — пауза после депа.
          return max(0, ms - max(0, elapsed))
  ```

## 2. `backend/app/services/games.py`, функция `do_dep`
- В импорт `from app.services.game_clock import ...` добавить `DEP_CLOCK_PAUSE_MS` (по алфавиту, первым).
- Прямо ПЕРЕД строкой `schedule_deadline(db, game)` внутри `do_dep` (это та, что идёт после блока `if outcome is not None:`) вставить:
  ```python
      if game.status == "active":
          pause = timedelta(milliseconds=DEP_CLOCK_PAUSE_MS)
          if game.clock_running:
              left = remaining_ms(game, color, now)
              if color == "white":
                  game.white_ms = left
              else:
                  game.black_ms = left
              game.turn_started_at = now + pause
          elif game.abort_deadline is not None:
              game.abort_deadline = game.abort_deadline + pause
  ```
  `timedelta` в файле уже импортирован (проверь; если нет — добавь в импорт `from datetime import ...`).

## 3. Новый файл `backend/tests/test_dep_clock_pause.py`
Образец работы с партиями и депом — `backend/tests/test_games.py` и `backend/tests/test_history.py:78`. Фикстуры `alice`, `bob`, `rng`, `frozen` и хелпер `start_game` — из `backend/tests/conftest.py` (alice всегда белые).

```python
import uuid
from datetime import timedelta

from app.db import SessionLocal
from app.models import Game
from tests.conftest import start_game


async def _state(client, game_id: str) -> dict:
    resp = await client.get(f"/api/v1/games/{game_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_dep_pauses_running_clock(alice, bob, rng, frozen) -> None:
    game_id = await start_game(alice, bob, rng)
    resp = await alice.post(f"/api/v1/games/{game_id}/move", json={"uci": "e2e4"})
    assert resp.status_code == 200, resp.text
    resp = await bob.post(f"/api/v1/games/{game_id}/move", json={"uci": "e7e5"})
    assert resp.status_code == 200, resp.text
    frozen.advance(5)
    before = (await _state(alice, game_id))["clocks"]["white_ms"]
    rng.values = [0.0]
    resp = await alice.post(f"/api/v1/games/{game_id}/dep", json={"square": "b1", "target": "Q"})
    assert resp.status_code == 200, resp.text
    frozen.advance(2)
    assert (await _state(alice, game_id))["clocks"]["white_ms"] == before
    frozen.advance(2)
    assert (await _state(alice, game_id))["clocks"]["white_ms"] == before - 1000


async def test_dep_extends_abort_deadline(alice, bob, rng, frozen) -> None:
    game_id = await start_game(alice, bob, rng)
    async with SessionLocal() as db:
        before = (await db.get(Game, uuid.UUID(game_id))).abort_deadline
    rng.values = [0.0]
    resp = await alice.post(f"/api/v1/games/{game_id}/dep", json={"square": "b1", "target": "Q"})
    assert resp.status_code == 200, resp.text
    async with SessionLocal() as db:
        after = (await db.get(Game, uuid.UUID(game_id))).abort_deadline
    assert after == before + timedelta(milliseconds=3000)
```
Если формат запросов `/move` или `/dep` в тестах отличается (смотри test_games.py) — приведи к нему, логику проверок не меняй.

## Проверка
`cd /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t2 && bash scripts/test_isolated.sh tests/test_dep_clock_pause.py tests/test_games.py tests/test_game_clock.py tests/test_clock_worker.py` — всё зелёное.
