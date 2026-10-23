import { h } from './dom.js';

const WHITE = { K: '♔', Q: '♕', R: '♖', B: '♗', N: '♘', P: '♙' };
const BLACK = { K: '♚', Q: '♛', R: '♜', B: '♝', N: '♞', P: '♟' };

// Запасной вид, если у снапшота нет слота (docs/contracts-skins.md §7).
export const DEFAULT_PIECE_COLOR = { white: '#f4f6ff', black: '#ff5470' };
export const DEFAULT_BOARD = { light: '#454f77', dark: '#262e4d' };

export const PIECE_PX = 128;
export const BOARD_PX = 1088;
export const BOARD_FRAME_PX = 32;

export function glyph(piece, color) {
  const glyphs = color === 'black' ? BLACK : WHITE;
  return (glyphs[piece] ?? '') + '︎';
}

export function skinUrl(asset) {
  return asset != null && asset.type === 'png' ? '/api/v1/skins/' + asset.image + '.png' : null;
}

// Картинка скина фигуры; без картинки — глиф цвета по умолчанию.
export function pieceNode(loadout, piece, color, extraClass = '') {
  const url = skinUrl(loadout?.[piece]?.asset);
  if (url !== null) {
    const img = h('img', { class: ['piece-img', extraClass] });
    img.alt = '';
    img.draggable = false;
    img.src = url;
    return img;
  }
  const span = h('span', { class: [extraClass] }, glyph(piece, color));
  span.style.setProperty('--piece-color', DEFAULT_PIECE_COLOR[color]);
  return span;
}

export function boardUrl(loadout) {
  return skinUrl(loadout?.board?.asset);
}
