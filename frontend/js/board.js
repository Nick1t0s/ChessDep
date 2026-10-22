import { h, clear } from './dom.js';
import { glyph, pieceColor, boardColors } from './pieces.js';
import { PIECE_NAME_RU } from './format.js';

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
const RANKS = ['1', '2', '3', '4', '5', '6', '7', '8'];

// Порядок клеток a1..h8: индекс = номер файла + номер вертикали * 8.
export function squareIndex(square) {
  return FILES.indexOf(square[0]) + (Number(square[1]) - 1) * 8;
}

function squareName(index) {
  return FILES[index % 8] + RANKS[Math.floor(index / 8)];
}

const STATUS_CLASSES = ['sel', 'hint', 'cap', 'last', 'last-dep', 'check', 'dep-pick'];

export function createBoard(container, { orientation = 'white', onSquareClick } = {}) {
  container.classList.add('board-holder');
  while (container.firstChild) container.firstChild.remove();

  const board = h('div', { class: 'board' });
  const ranksCol = h('div', { class: 'ranks' });
  const filesRow = h('div', { class: 'files' });
  container.appendChild(h('div', { class: 'board-zone' }, ranksCol, board, filesRow));

  const byIndex = new Array(64);
  for (let i = 0; i < 64; i += 1) {
    const name = squareName(i);
    const light = (i % 8 + Math.floor(i / 8)) % 2 === 1;
    const btn = h('button', {
      type: 'button',
      class: ['sq', light ? 'light' : 'dark'],
      'data-square': name,
      tabindex: '-1',
    });
    btn.addEventListener('click', () => {
      try {
        onSquareClick(name);
      } catch (e) {
        console.error(e);
      }
    });
    byIndex[i] = btn;
  }

  let currentOrientation = orientation === 'black' ? 'black' : 'white';
  setOrientation(currentOrientation);

  function setOrientation(color) {
    currentOrientation = color === 'black' ? 'black' : 'white';
    clear(board);
    clear(ranksCol);
    clear(filesRow);
    // white: снизу слева a1 — верхний ряд 8-я горизонталь, слева файл a.
    // black: снизу слева h8 — верхний ряд 1-я горизонталь, слева файл h.
    for (let row = 0; row < 8; row += 1) {
      for (let col = 0; col < 8; col += 1) {
        const rank = currentOrientation === 'white' ? 8 - row : row + 1;
        const fileIdx = currentOrientation === 'white' ? col : 7 - col;
        board.appendChild(byIndex[fileIdx + (rank - 1) * 8]);
        if (col === 0) ranksCol.appendChild(h('span', {}, String(rank)));
      }
    }
    for (let col = 0; col < 8; col += 1) {
      const fileIdx = currentOrientation === 'white' ? col : 7 - col;
      filesRow.appendChild(h('span', {}, FILES[fileIdx]));
    }
  }

  function squareEl(name) {
    return byIndex[squareIndex(name)] ?? null;
  }

  function setGlyph(btn, name, piece, color, loadout) {
    let span = null;
    for (const child of btn.children) {
      if (child.classList.contains('glyph')) {
        span = child;
        break;
      }
    }
    if (piece === null) {
      if (span !== null) span.remove();
      btn.classList.remove('side-white', 'side-black');
      btn.setAttribute('aria-label', name + ', пусто');
      return;
    }
    if (span === null) {
      span = h('span', { class: ['glyph'] });
      btn.appendChild(span);
    }
    span.textContent = glyph(piece, color);
    btn.classList.toggle('side-white', color === 'white');
    btn.classList.toggle('side-black', color === 'black');
    span.style.setProperty('--piece-color', pieceColor(loadout, piece, color));
    btn.setAttribute(
      'aria-label',
      name + ', ' + (color === 'white' ? 'белый' : 'чёрный') + ' ' + (PIECE_NAME_RU[piece] ?? '').toLowerCase()
    );
  }

  function render(state, opts = {}) {
    const { selected = null, hints = [], captures = [], depPickable = [] } = opts;
    // Доска рисуется скином смотрящего.
    const colors = boardColors(state?.players?.[state?.you]?.loadout);
    board.style.setProperty('--light', colors.light);
    board.style.setProperty('--dark', colors.dark);

    const occupied = new Map();
    for (const cell of state?.board ?? []) {
      occupied.set(cell.square, cell);
    }

    const lastFrom = state?.last_action?.kind === 'move' ? state.last_action.uci.slice(0, 2) : null;
    const lastTo = state?.last_action?.kind === 'move' ? state.last_action.uci.slice(2, 4) : null;
    const lastDep = state?.last_action?.kind === 'dep' ? state.last_action.square : null;

    const hintSet = new Set(hints);
    const capSet = new Set(captures);
    const pickSet = new Set(depPickable);

    for (let i = 0; i < 64; i += 1) {
      const btn = byIndex[i];
      const name = squareName(i);
      const cell = occupied.get(name) ?? null;
      setGlyph(
        btn,
        name,
        cell?.piece ?? null,
        cell?.color ?? null,
        cell !== null ? state?.players?.[cell.color]?.loadout : null
      );
      btn.classList.remove(...STATUS_CLASSES);
      if (selected === name) btn.classList.add('sel');
      if (hintSet.has(name)) btn.classList.add('hint');
      if (capSet.has(name)) btn.classList.add('cap');
      if (lastFrom === name || lastTo === name) btn.classList.add('last');
      if (lastDep === name) btn.classList.add('last-dep');
      if (state?.check_square === name) btn.classList.add('check');
      if (pickSet.has(name)) btn.classList.add('dep-pick');
    }
  }

  return { render, squareEl, setOrientation, element: board, orientation: () => currentOrientation };
}
