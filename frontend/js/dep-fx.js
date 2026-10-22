import { h } from './dom.js';
import { PIECE_NAME_RU } from './format.js';
import { glyph } from './pieces.js';

const CURSOR_MS = 1800;
const CURSOR_FALLBACK_MS = 2000;
const FX_MS = 800;

function fmtChance(chance, chanceText) {
  if (typeof chanceText === 'string') return chanceText.replace('%', ' %');
  return (chance * 100).toFixed(2) + ' %';
}

function transitionDone(el, fallbackMs) {
  return new Promise((resolve) => {
    let finished = false;
    const done = () => {
      if (finished) return;
      finished = true;
      el.removeEventListener('transitionend', done);
      clearTimeout(timer);
      resolve();
    };
    const timer = setTimeout(done, fallbackMs);
    el.addEventListener('transitionend', done);
  });
}

export async function playDep(boardApi, event, { mine }) {
  const board = boardApi?.element;
  if (!board) return;

  const chanceLabel = fmtChance(event.chance, event.chance_text);
  const title = (PIECE_NAME_RU[event.from] ?? event.from) + ' → ' + (PIECE_NAME_RU[event.to] ?? event.to)
    + ' · ' + chanceLabel;

  const titleEl = h('div', { class: 'dep-title' }, title);
  const subtitleEl = mine ? null : h('div', { class: 'dep-sub' }, 'Соперник депает…');
  const zoneWin = h('div', { class: 'zone-win' });
  zoneWin.style.setProperty('width', String(event.chance * 100) + '%');
  const cursor = h('div', { class: 'dep-cursor' });
  const track = h('div', { class: 'dep-track' }, zoneWin, cursor);
  const percents = h('div', { class: 'dep-percents' }, h('span', {}, '0%'), h('span', {}, '100%'));
  const card = h('div', { class: 'dep-bar card' }, titleEl, subtitleEl, track, percents);
  // Плашка встаёт в ту половину доски, где нет депаемой фигуры, —
  // иначе у перевёрнутой доски она закрывает превращение/сгорание.
  const sqEl = boardApi.squareEl(event.square);
  const inTopHalf = sqEl !== null && sqEl.offsetTop < board.clientHeight / 2;
  const overlay = h('div', { class: ['dep-overlay', inTopHalf && 'at-bottom'] }, card);
  board.appendChild(overlay);

  // Курсор едет слева направо и останавливается ровно на броске:
  // win-зона — [0, chance), успех ⇔ roll_value < chance.
  cursor.style.setProperty('left', '0%');
  void cursor.offsetWidth;
  cursor.style.setProperty('transition', 'left ' + CURSOR_MS + 'ms cubic-bezier(.15,.85,.25,1)');
  cursor.style.setProperty('left', String(event.roll_value * 100) + '%');
  await transitionDone(cursor, CURSOR_FALLBACK_MS);

  if (sqEl && event.square) {
    const side = sqEl.classList.contains('side-white') ? 'white' : 'black';
    let glyphEl = null;
    for (const child of sqEl.children) {
      if (child.classList.contains('glyph')) {
        glyphEl = child;
        break;
      }
    }
    let ring = null;
    if (glyphEl !== null) glyphEl.classList.remove('newpop', 'crack', 'burn-out');
    if (event.success && glyphEl !== null) {
      glyphEl.textContent = glyph(event.to, side);
      glyphEl.classList.add('newpop');
      ring = h('span', { class: 'dep-ring burst' });
      sqEl.appendChild(ring);
    } else if (!event.success && glyphEl !== null) {
      glyphEl.classList.add('crack');
      setTimeout(() => {
        glyphEl.classList.add('burn-out');
      }, 500);
    }
  }
  await new Promise((resolve) => setTimeout(resolve, FX_MS));

  if (sqEl) {
    const staleRing = sqEl.querySelector('.dep-ring');
    if (staleRing) staleRing.remove();
  }
  overlay.remove();
}
