# T4. Новое колесо апгрейда (фронт)

Worktree: /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t4
Файлы: только `frontend/js/upgrade.js` и `frontend/css/upgrade.css`.

Вид как у «апгрейдера» CS-сайтов: кольцо со шкалой рисок снаружи, тёмный диск в центре с процентом и подписью «низкий/средний/высокий шанс», дуга шанса (оранжево-золотая) по центру СНИЗУ, белая стрелка крутится по кругу и останавливается на броске.

## 1. `frontend/css/upgrade.css`
- В первой строке `.upg-layout { ... grid-template-columns: 1fr 300px 1fr; ...}` заменить `300px` на `340px`.
- Удалить правила `.wheel-wrap`, `.wheel` (2 строки), `.wheel-pointer` (2 строки) и `.upg-chance`.
- Вместо них (там же, перед `.upg-reason`) вставить:
```css
.gauge { position: relative; width: 260px; height: 260px; margin: 18px auto 8px; }
.gauge-ticks { position: absolute; inset: -16px; border-radius: 50%;
  background: repeating-conic-gradient(rgba(255, 255, 255, .35) 0deg .8deg, transparent .8deg 7.5deg);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 8px), #000 calc(100% - 7px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 8px), #000 calc(100% - 7px)); }
.gauge-arc { --half: 0deg; position: absolute; inset: 0; border-radius: 50%;
  background: conic-gradient(from calc(180deg - var(--half)),
    #ff7a1a 0deg, #ffd23c calc(var(--half) * .6), #fff6d8 var(--half), #ffd23c calc(var(--half) * 1.4),
    #ff7a1a calc(var(--half) * 2), rgba(255, 255, 255, .07) calc(var(--half) * 2) 360deg);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 20px), #000 calc(100% - 19px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 20px), #000 calc(100% - 19px));
  filter: drop-shadow(0 0 10px rgba(255, 170, 40, .45)); }
.gauge-inner { position: absolute; inset: 30px; border-radius: 50%; display: grid; place-content: center; gap: 2px;
  text-align: center; background: radial-gradient(circle at 50% 30%, #2b3144, #141925 70%);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, .06), inset 0 0 40px rgba(0, 0, 0, .7), 0 0 0 6px rgba(0, 0, 0, .25); }
.gauge-inner::before { content: ''; position: absolute; inset: 8px; border-radius: 50%; pointer-events: none;
  background: repeating-conic-gradient(rgba(255, 255, 255, .10) 0deg 7deg, transparent 7deg 10deg);
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 9px), #000 calc(100% - 8px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 9px), #000 calc(100% - 8px)); }
.gauge-chance { position: relative; font-size: 34px; font-weight: 800; color: var(--text);
  text-shadow: 0 0 18px rgba(255, 210, 60, .35); }
.gauge-level { position: relative; min-height: 16px; font-size: 13px; color: var(--gold); }
.gauge-arrow { position: absolute; inset: -10px; pointer-events: none; transform: rotate(180deg); }
.gauge-needle { position: absolute; left: 50%; top: 0; width: 0; height: 0; margin-left: -8px;
  border-left: 8px solid transparent; border-right: 8px solid transparent; border-top: 26px solid #fff;
  filter: drop-shadow(0 0 6px rgba(255, 255, 255, .9)); }
```

## 2. `frontend/js/upgrade.js`
1. Добавить импорт после `import { itemCard } from './items.js';`:
   `import { playSound } from './sound.js';` (модуль уже есть: `playSound(name, volume = 0.6)`, имена `'tick'`, `'win'`, `'fail'`).
2. `let rotation = 0;` → `let rotation = 180; // стрелка в покое — внизу, в центре дуги`
3. Заменить блок создания `wheel`, `chanceEl` и `centerCard` (строки от `const wheel = ...` до закрывающей `);` у `centerCard`, `reasonEl` и `goBtn` оставить как есть) на:
```js
const arrow = h('div', { class: 'gauge-arrow' }, h('div', { class: 'gauge-needle' }));
const gaugeArc = h('div', { class: 'gauge-arc' });
const chanceEl = h('div', { class: 'gauge-chance mono' }, '—');
const levelEl = h('div', { class: 'gauge-level' }, '');
const gauge = h('div', { class: 'gauge' },
  h('div', { class: 'gauge-ticks' }),
  gaugeArc,
  h('div', { class: 'gauge-inner' }, chanceEl, levelEl),
  arrow,
);
const reasonEl = h('p', { class: 'upg-reason' }, '');
const goBtn = h('button', { type: 'button', class: 'btn btn-gold btn-block', disabled: true }, 'Апгрейд');
const centerCard = h('div', { class: 'card upg-center' }, gauge, reasonEl, goBtn);
```
4. Перед `function resetPreview()` добавить:
```js
function chanceLevel(chance) {
  if (chance < 0.3) return 'низкий шанс';
  if (chance < 0.6) return 'средний шанс';
  return 'высокий шанс';
}
```
5. В `resetPreview` строку `wheel.style.setProperty('--win', '0deg');` заменить на `gaugeArc.style.setProperty('--half', '0deg');` и после `chanceEl.textContent = '—';` добавить `levelEl.textContent = '';`.
6. В `refreshPreview` строку `wheel.style.setProperty('--win', (p.chance * 360) + 'deg');` заменить на `gaugeArc.style.setProperty('--half', (p.chance * 180) + 'deg');`, а после `chanceEl.textContent = p.chance_text;` добавить `levelEl.textContent = chanceLevel(p.chance);`.
7. В `waitSpin` оба `wheel.` заменить на `arrow.`.
8. После `waitSpin` добавить функцию:
```js
// Щелчок каждые 15° поворота стрелки, но не чаще раза в 45 мс.
function tickWhileSpinning() {
  let last = null;
  let unwrapped = 0;
  let lastTickAt = 0;
  let raf = 0;
  const step = () => {
    const t = getComputedStyle(arrow).transform;
    if (t !== 'none') {
      const m = new DOMMatrix(t);
      const angle = Math.atan2(m.b, m.a) * 180 / Math.PI;
      if (last !== null) {
        let d = angle - last;
        if (d < -180) d += 360;
        if (d > 180) d -= 360;
        const before = Math.floor(unwrapped / 15);
        unwrapped += d;
        const now = performance.now();
        if (Math.floor(unwrapped / 15) !== before && now - lastTickAt > 45) {
          lastTickAt = now;
          playSound('tick', 0.35);
        }
      }
      last = angle;
    }
    raf = requestAnimationFrame(step);
  };
  raf = requestAnimationFrame(step);
  return () => cancelAnimationFrame(raf);
}
```
9. В обработчике `goBtn` заменить 5 строк от `const base = Math.ceil(rotation / 360) * 360 + 1800;` до `await waitSpin();` включительно на:
```js
  // Дуга шанса — по центру снизу: [180° − chance·180°, 180° + chance·180°).
  // Успех ⇔ roll_value < chance, поэтому стрелка встаёт в 180° − chance·180° + roll·360°.
  const stop = 180 - res.chance * 180 + res.roll_value * 360;
  rotation = Math.ceil(rotation / 360) * 360 + 1800 + stop;
  const stopTicks = tickWhileSpinning();
  arrow.style.setProperty('transition', 'transform 4s cubic-bezier(.15,.85,.25,1)');
  arrow.style.setProperty('transform', 'rotate(' + rotation + 'deg)');
  await waitSpin();
  stopTicks();
  playSound(res.success ? 'win' : 'fail');
```
10. Убедиться, что в файле не осталось ни одного упоминания `wheel` (кроме слов в комментариях — их тоже не должно быть).

## Проверка
`cd /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t4 && bash scripts/check_frontend.sh && grep -n "wheel" frontend/js/upgrade.js frontend/css/upgrade.css` — первая команда «frontend check: OK», grep ничего не выводит.
