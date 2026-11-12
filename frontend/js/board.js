import { h, clear } from './dom.js';
import { pieceNode, boardUrl } from './pieces.js';
import { PIECE_NAME_RU } from './format.js';

const FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'];
const RANKS = ['1', '2', '3', '4', '5', '6', '7', '8'];
const DRAG_THRESHOLD = 6;

// Порядок клеток a1..h8: индекс = номер файла + номер вертикали * 8.
export function squareIndex(square) {
  return FILES.indexOf(square[0]) + (Number(square[1]) - 1) * 8;
}

function squareName(index) {
  return FILES[index % 8] + RANKS[Math.floor(index / 8)];
}

const STATUS_CLASSES = ['sel', 'hint', 'cap', 'last', 'last-dep', 'check', 'dep-pick'];

export function createBoard(
  container,
  { orientation = 'white', onSquareClick, canDrag, onDragStart, onPieceDrop } = {}
) {
  container.classList.add('board-holder');
  while (container.firstChild) container.firstChild.remove();

  const board = h('div', { class: 'board' });
  const ranksCol = h('div', { class: 'ranks' });
  const filesRow = h('div', { class: 'files' });
  const zone = h('div', { class: 'board-zone' }, ranksCol, board, filesRow);
  container.appendChild(zone);

  let currentOrientation = orientation === 'black' ? 'black' : 'white';
  let lastState = null;
  const occupied = new Map();

  // Состояние перетаскивания (drag-and-drop)
  let currentPointerId = null;
  let currentSourceSquare = null;
  let currentSourceBtn = null;
  let startX = 0;
  let startY = 0;
  let dragActive = false;
  let suppressClick = false;
  let suppressTimer = null;
  let dragGhost = null;
  let currentHoverSquare = null;

  function suppressNextClick() {
    suppressClick = true;
    if (suppressTimer !== null) {
      clearTimeout(suppressTimer);
    }
    suppressTimer = setTimeout(() => {
      suppressClick = false;
      suppressTimer = null;
    }, 100);
  }

  function cleanupDrag(opts = {}) {
    const { suppress = false } = opts;
    if (suppress || dragActive) {
      suppressNextClick();
    }

    const btnToRelease = currentSourceBtn;
    const pointerIdToRelease = currentPointerId;
    const hoverSquareToClean = currentHoverSquare;

    // Сбрасываем поля до releasePointerCapture во избежание реентрантности из lostpointercapture
    currentPointerId = null;
    currentSourceSquare = null;
    currentSourceBtn = null;
    dragActive = false;
    currentHoverSquare = null;

    if (hoverSquareToClean !== null) {
      const prevEl = squareEl(hoverSquareToClean);
      if (prevEl) prevEl.classList.remove('drag-over');
    }
    if (btnToRelease !== null) {
      btnToRelease.classList.remove('dragging-source');
    }
    if (dragGhost !== null) {
      if (dragGhost.parentNode) {
        dragGhost.remove();
      }
      dragGhost = null;
    }

    window.removeEventListener('pointermove', onPointerMove);
    window.removeEventListener('pointerup', onPointerUp);
    window.removeEventListener('pointercancel', onPointerCancel);

    if (btnToRelease !== null && pointerIdToRelease !== null) {
      try {
        if (btnToRelease.hasPointerCapture(pointerIdToRelease)) {
          btnToRelease.releasePointerCapture(pointerIdToRelease);
        }
      } catch {}
    }
  }

  function startDragVisuals(sourceSquare, sourceBtn, x, y) {
    sourceBtn.classList.add('dragging-source');

    let sourceGlyph = null;
    for (const child of sourceBtn.children) {
      if (child.classList.contains('glyph') || child.classList.contains('piece-img')) {
        sourceGlyph = child;
        break;
      }
    }
    if (!sourceGlyph) return;

    dragGhost = h('div', { class: 'drag-ghost' });
    if (sourceBtn.classList.contains('side-white')) {
      dragGhost.classList.add('side-white');
    } else if (sourceBtn.classList.contains('side-black')) {
      dragGhost.classList.add('side-black');
    }

    let ghostChild;
    if (sourceGlyph.tagName === 'IMG' || sourceGlyph.classList.contains('piece-img')) {
      ghostChild = sourceGlyph.cloneNode(true);
      ghostChild.draggable = false;
      ghostChild.alt = '';
    } else {
      ghostChild = h('span', { class: 'glyph' });
      ghostChild.textContent = sourceGlyph.textContent;
      const pieceColorVal = sourceGlyph.style.getPropertyValue('--piece-color');
      if (pieceColorVal) {
        ghostChild.style.setProperty('--piece-color', pieceColorVal);
      }
    }
    dragGhost.appendChild(ghostChild);

    const rect = sourceBtn.getBoundingClientRect();
    if (rect.width > 0 && rect.height > 0) {
      dragGhost.style.width = rect.width + 'px';
      dragGhost.style.height = rect.height + 'px';
    }
    try {
      const comp = window.getComputedStyle(sourceBtn);
      if (comp && comp.fontSize) {
        dragGhost.style.fontSize = comp.fontSize;
      }
    } catch {}

    dragGhost.style.left = x + 'px';
    dragGhost.style.top = y + 'px';

    document.body.appendChild(dragGhost);
  }

  function getSquareAtPoint(x, y) {
    if (typeof document !== 'undefined' && typeof document.elementFromPoint === 'function') {
      const el = document.elementFromPoint(x, y);
      if (el) {
        const sq = el.closest ? el.closest('.sq') : null;
        if (sq && board.contains(sq)) {
          return sq.getAttribute('data-square') ?? null;
        }
      }
    }
    return getSquareByCoordinates(x, y);
  }

  function getSquareByCoordinates(x, y) {
    const rect = board.getBoundingClientRect();
    if (x < rect.left || x > rect.right || y < rect.top || y > rect.bottom) {
      return null;
    }
    const col = Math.floor((x - rect.left) / (rect.width / 8));
    const row = Math.floor((y - rect.top) / (rect.height / 8));
    if (col < 0 || col > 7 || row < 0 || row > 7) return null;

    const rank = currentOrientation === 'white' ? 8 - row : row + 1;
    const fileIdx = currentOrientation === 'white' ? col : 7 - col;
    return FILES[fileIdx] + RANKS[rank - 1];
  }

  function updateHoverTarget(x, y) {
    const target = getSquareAtPoint(x, y);
    if (target !== currentHoverSquare) {
      if (currentHoverSquare !== null) {
        const prevEl = squareEl(currentHoverSquare);
        if (prevEl) prevEl.classList.remove('drag-over');
      }
      currentHoverSquare = target;
      if (currentHoverSquare !== null) {
        const nextEl = squareEl(currentHoverSquare);
        if (nextEl) nextEl.classList.add('drag-over');
      }
    }
  }

  function onPointerMove(e) {
    if (currentPointerId === null || e.pointerId !== currentPointerId) return;

    if (!dragActive) {
      const dist = Math.hypot(e.clientX - startX, e.clientY - startY);
      if (dist < DRAG_THRESHOLD) return;

      dragActive = true;
      startDragVisuals(currentSourceSquare, currentSourceBtn, e.clientX, e.clientY);
      if (typeof onDragStart === 'function') {
        try {
          onDragStart(currentSourceSquare);
        } catch (err) {
          console.error(err);
        }
      }
    }

    if (dragActive) {
      if (dragGhost) {
        dragGhost.style.left = e.clientX + 'px';
        dragGhost.style.top = e.clientY + 'px';
      }
      updateHoverTarget(e.clientX, e.clientY);
    }
  }

  function onPointerUp(e) {
    if (currentPointerId === null || e.pointerId !== currentPointerId) return;

    const wasDragActive = dragActive;
    const source = currentSourceSquare;

    if (wasDragActive) {
      const targetSquare = getSquareAtPoint(e.clientX, e.clientY);

      cleanupDrag({ suppress: true });

      if (targetSquare !== null && targetSquare !== source) {
        if (typeof onPieceDrop === 'function') {
          try {
            onPieceDrop(source, targetSquare);
          } catch (err) {
            console.error(err);
          }
        }
      }
    } else {
      cleanupDrag({ suppress: false });
    }
  }

  function onPointerCancel(e) {
    if (currentPointerId !== null && e.pointerId === currentPointerId) {
      cleanupDrag({ suppress: true });
    }
  }

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

    btn.addEventListener('pointerdown', (e) => {
      if (e.button !== 0) return;
      if (currentPointerId !== null || e.isPrimary === false) return;
      if (typeof canDrag !== 'function') return;

      const cell = occupied.get(name);
      if (!cell) return;
      try {
        if (!canDrag(name)) return;
      } catch {
        return;
      }

      cleanupDrag();

      currentPointerId = e.pointerId;
      currentSourceSquare = name;
      currentSourceBtn = btn;
      startX = e.clientX;
      startY = e.clientY;
      dragActive = false;

      try {
        btn.setPointerCapture(e.pointerId);
      } catch {}

      window.addEventListener('pointermove', onPointerMove);
      window.addEventListener('pointerup', onPointerUp);
      window.addEventListener('pointercancel', onPointerCancel);
    });

    btn.addEventListener('lostpointercapture', (e) => {
      if (currentPointerId !== null && e.pointerId === currentPointerId) {
        cleanupDrag({ suppress: true });
      }
    });

    btn.addEventListener('click', (e) => {
      if (suppressClick) {
        suppressClick = false;
        if (suppressTimer !== null) {
          clearTimeout(suppressTimer);
          suppressTimer = null;
        }
        e.preventDefault();
        e.stopPropagation();
        return;
      }
      try {
        if (typeof onSquareClick === 'function') {
          onSquareClick(name);
        }
      } catch (err) {
        console.error(err);
      }
    });

    byIndex[i] = btn;
  }

  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && (dragActive || currentPointerId !== null)) {
      cleanupDrag({ suppress: true });
    }
  });

  window.addEventListener('blur', () => {
    if (dragActive || currentPointerId !== null) {
      cleanupDrag({ suppress: true });
    }
  });

  setOrientation(currentOrientation);

  function setOrientation(color) {
    cleanupDrag({ suppress: currentPointerId !== null });
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

  // Узел фигуры с ключом: render не пересоздаёт его, если фигура и картинка не менялись.
  function makePiece(piece, color, loadout) {
    const node = pieceNode(loadout, piece, color, 'glyph');
    node.dataset.key = piece + '|' + color + '|' + (node.tagName === 'IMG' ? node.src : '');
    return node;
  }

  function pieceElement(piece, color) {
    return makePiece(piece, color, lastState?.players?.[color]?.loadout);
  }

  function setGlyph(btn, name, piece, color, loadout) {
    let current = null;
    for (const child of btn.children) {
      if (child.classList.contains('glyph')) {
        current = child;
        break;
      }
    }
    if (piece === null) {
      if (current !== null) current.remove();
      btn.classList.remove('side-white', 'side-black');
      btn.setAttribute('aria-label', name + ', пусто');
      return;
    }
    const fresh = makePiece(piece, color, loadout);
    if (current === null) {
      btn.appendChild(fresh);
    } else if (current.dataset.key !== fresh.dataset.key) {
      current.replaceWith(fresh);
    }
    btn.classList.toggle('side-white', color === 'white');
    btn.classList.toggle('side-black', color === 'black');
    btn.setAttribute(
      'aria-label',
      name + ', ' + (color === 'white' ? 'белый' : 'чёрный') + ' ' + (PIECE_NAME_RU[piece] ?? '').toLowerCase()
    );
  }

  function isSamePosition(prev, next) {
    if (!prev || !next) return false;
    if (prev === next) return true;
    if (typeof prev.version === 'number' && typeof next.version === 'number') {
      if (prev.version !== next.version) return false;
    }
    const bPrev = prev.board;
    const bNext = next.board;
    if (bPrev === bNext) return true;
    if (!Array.isArray(bPrev) || !Array.isArray(bNext)) return false;
    if (bPrev.length !== bNext.length) return false;
    for (let i = 0; i < bPrev.length; i += 1) {
      const pA = bPrev[i];
      const pB = bNext[i];
      if (!pA || !pB) return false;
      if (pA.square !== pB.square || pA.piece !== pB.piece || pA.color !== pB.color) {
        return false;
      }
    }
    return true;
  }

  function render(state, opts = {}) {
    if ((dragActive || currentPointerId !== null) && !isSamePosition(lastState, state)) {
      cleanupDrag({ suppress: true });
    }
    lastState = state;

    const { selected = null, hints = [], captures = [], depPickable = [] } = opts;
    // Доска рисуется скином смотрящего (зритель — доска белых).
    lastState = state;
    const url = boardUrl(state?.players?.[state?.you]?.loadout ?? state?.players?.white?.loadout);
    zone.classList.toggle('skinned', url !== null);
    if (url !== null) board.style.setProperty('--board-image', 'url("' + url + '")');
    else board.style.removeProperty('--board-image');

    occupied.clear();
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

      let isDraggable = false;
      if (typeof canDrag === 'function' && cell !== null) {
        try {
          isDraggable = Boolean(canDrag(name));
        } catch {
          isDraggable = false;
        }
      }
      btn.classList.toggle('draggable', isDraggable);

      if (dragActive && currentSourceSquare === name) {
        btn.classList.add('dragging-source');
      }
      if (dragActive && currentHoverSquare === name) {
        btn.classList.add('drag-over');
      }
    }
  }

  return { render, squareEl, setOrientation, pieceElement, element: board, orientation: () => currentOrientation };
}
