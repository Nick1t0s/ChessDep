# T5. Звук ленты при открытии кейса (фронт)

Worktree: /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t5
Файл: только `frontend/js/case.js`.

1. После `import { itemCard } from './items.js';` добавить `import { playSound } from './sound.js';` (модуль уже есть: `playSound(name, volume = 0.6)`).
2. В функции `playStrip` сразу после строки
   `track.style.setProperty('transform', 'translateX(' + String(-offset) + 'px)');`
   вставить:
```js
  // Щелчок, когда под маркер приезжает новая ячейка (ячейка с зазором — 132 px), как в CS.
  const half = windowEl.clientWidth / 2;
  let lastCell = null;
  let raf = 0;
  const step = () => {
    const t = getComputedStyle(track).transform;
    if (t !== 'none') {
      const cell = Math.floor((half - new DOMMatrix(t).m41) / 132);
      if (lastCell !== null && cell !== lastCell) playSound('tick', 0.5);
      lastCell = cell;
    }
    raf = requestAnimationFrame(step);
  };
  raf = requestAnimationFrame(step);
```
3. В той же функции внутри `finish` после строки `done = true;` добавить `cancelAnimationFrame(raf);`.
4. В функции `openItemCase` сразу после `await playStrip(windowEl, track, res);` добавить `playSound('win');`.

## Проверка
`cd /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t5 && bash scripts/check_frontend.sh` → «frontend check: OK».
