# task-003b — исправления по ревью task-003

Правила те же: делаешь ровно это, ничего сверх; существующие тесты не удалять и не ослаблять; при сомнении — вопрос.

---

## 1. КРИТИЧНО: партия из матчмейкинга не получает дедлайн

**Воспроизведение (на живом стеке):** двое встают в очередь, worker создаёт партию. `ZSCORE clock:deadlines <game_id>` → `nil`. Дедлайн появляется только после первого хода. Если никто не сходит, партия никогда не аннулируется: оба игрока навсегда остаются с `ALREADY_IN_GAME`, так как новую партию начать нельзя.

**Причина:** `matchmaking._match_pair` коммитит транзакцию через `async with db.begin()`, но не вызывает `run_after_commit(db)`. Хук `schedule_deadline` из `create_game` так и не выполняется. В task-003 (п. 5.2) вызов прописан явно.

**Исправление:** в `_match_pair` после выхода из `async with db.begin():` (то есть после коммита), внутри `async with SessionLocal() as db:`, вызвать `await run_after_commit(db)`.

**Тесты (в `tests/test_matchmaking.py`):**
- `test_matched_game_has_deadline`: alice и bob в очередь, `tick` → `ZSCORE clock:deadlines <game_id>` == `to_ms(games.abort_deadline)`.
- `test_matched_game_aborts_without_moves` (фикстура `frozen`): очередь, `tick`, `frozen.advance(31)`, `tick_clocks(clock.now())` → партия `aborted` / `abort_no_first_move`; у обоих `/me/active-game` → `null`.

## 2. Одна сбойная партия блокирует все флаги

`tick_clocks` обрабатывает партии в цикле без `try/except`. Если `_process_deadline` падает на одной партии (например, `GAME_NOT_FOUND`: id в ZSET есть, а партии в БД нет), исключение выходит из `tick_clocks`. Эта партия остаётся в ZSET с самым маленьким score, поэтому на каждом тике она первая и снова роняет весь батч. Флаги остальных партий не ставятся никогда.

**Исправление** в `app/worker.py`:
- в `tick_clocks` каждый `_process_deadline` обернуть в `try/except Exception`, при ошибке `logger.exception("deadline processing failed for %s", raw_id)` и продолжать цикл;
- в `_process_deadline`: если `lock_game` бросил `AppError` с кодом `GAME_NOT_FOUND` → `ZREM` этого id и выйти без ошибки;
- некорректный uuid в ZSET (`ValueError` из `uuid.UUID`) → тоже `ZREM` и выйти.

**Тест** `test_tick_clocks_skips_broken_entries` (в `tests/test_clock_worker.py`, фикстура `frozen`): партия после двух ходов; в ZSET вручную добавить `str(uuid.uuid4())` со score 0 и `"not-a-uuid"` со score 0; `frozen.advance(181)`, `tick_clocks` → реальная партия `finished` / `timeout`; оба мусорных id удалены из ZSET.

## 3. Игрок может навсегда «зависнуть» в очереди

Сценарий: worker сделал `LPOP` двоих, затем `create_game` упал с любым исключением, кроме `ALREADY_IN_GAME` (ошибка БД, перезапуск worker посреди пары). Оба игрока пропали из LIST, но их ключ `mm:user:{id}` жив, и поллинг `/matchmaking/status` продлевает его каждую секунду. Статус показывает `queued` вечно, повторный `enqueue` только продлевает TTL и не возвращает игрока в LIST. Партия не найдётся никогда.

**Исправление:**
1. `_match_pair`: на любое исключение, кроме обработанного `ALREADY_IN_GAME`, вернуть обоих в начало очереди с сохранением порядка (`LPUSH b`, затем `LPUSH a`) и пробросить исключение дальше (worker его залогирует).
2. `enqueue`: если `mm:user:{id}` уже есть, продлить TTL **и** проверить `await redis_client.lpos(queue_key, str(user.id))`; если `None` → `RPUSH`. Так повторное нажатие «Играть» чинит любой рассинхрон.
3. `status`: если `mm:user` есть, но `lpos` вернул `None` → так же `RPUSH` (самовосстановление при поллинге).

**Тесты (в `tests/test_matchmaking.py`):**
- `test_requeue_when_missing_from_list`: alice в очереди; вручную `LREM` её из LIST (ключ `mm:user` остаётся); `GET /matchmaking/status` → `queued` и `LLEN == 1`; ещё раз `LREM`; `POST /matchmaking/queue` → `LLEN == 1`.
- `test_match_failure_requeues_both`: alice и bob в очереди; `monkeypatch.setattr(matchmaking, "create_game", <async-функция, бросающая RuntimeError>)`; `tick` → `RuntimeError` (через `pytest.raises`); после этого `LRANGE` == `[alice_id, bob_id]` в исходном порядке.

---

## Проверка (приложить вывод)
```bash
make test        # 100 старых + 6 новых, все зелёные
```
В конце — список изменённых файлов и вопросы, если были.
