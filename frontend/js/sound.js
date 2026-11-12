// Звуки интерфейса: файлы в /sounds/ (CC0, Kenney.nl — см. docs/ARCHITECTURE.md §12.2).
// Чтобы заменить звук, достаточно положить новый mp3 под тем же именем.
const FILES = {
  move: 'move.mp3',
  capture: 'capture.mp3',
  'dep-success': 'dep-success.mp3',
  'dep-fail': 'dep-fail.mp3',
  tick: 'tick.mp3',
  win: 'win.mp3',
  fail: 'fail.mp3',
  sale: 'sale.mp3',
};

const cache = new Map();

export function playSound(name, volume = 0.6) {
  const file = FILES[name];
  if (file === undefined) return;
  let base = cache.get(name);
  if (base === undefined) {
    base = new Audio('/sounds/' + file);
    base.preload = 'auto';
    cache.set(name, base);
  }
  // Клон — чтобы частые звуки (тики ленты) накладывались, а не обрывали друг друга.
  const audio = base.cloneNode();
  audio.volume = volume;
  // Браузер может запретить звук до первого клика по странице — это не ошибка.
  audio.play().catch(() => {});
}
