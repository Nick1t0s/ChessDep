# T6. Звуки ходов и депа, часы стоят во время анимации депа (фронт)

Worktree: /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t6
Файлы: только `frontend/js/game.js` и `frontend/js/dep-fx.js`.
Модуль `frontend/js/sound.js` уже есть: `playSound(name, volume = 0.6)`; имена `'move'`, `'capture'`, `'dep-success'`, `'dep-fail'`.

## 1. `frontend/js/dep-fx.js`
- После `import { PIECE_NAME_RU } from './format.js';` добавить `import { playSound } from './sound.js';`.
- Сразу после строки `await transitionDone(cursor, CURSOR_FALLBACK_MS);` добавить:
  `playSound(event.success ? 'dep-success' : 'dep-fail');`

## 2. `frontend/js/game.js`
- Добавить импорт после строки `import { playDep } from './dep-fx.js';`: `import { playSound } from './sound.js';`
- В `applyState` сразу после строки `const versionGrew = prevState !== null;` вставить:
```js
    // Звук хода: ply растёт только от ходов (деп, ничья, чат его не меняют).
    if (prevState !== null && state.ply > prevState.ply && state.last_action?.kind === 'move') {
      playSound(state.last_action.san?.includes('x') ? 'capture' : 'move');
    }
```
- В `clockTick` сразу после строки `if (state === null) return;` вставить:
```js
    // Во время анимации депа часы стоят: сервер даёт депающему паузу (DEP_CLOCK_PAUSE_MS).
    if (fxRunning) return;
```

## Проверка
`cd /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t6 && bash scripts/check_frontend.sh` → «frontend check: OK».
