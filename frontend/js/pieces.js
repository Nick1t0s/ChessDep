const WHITE = { K: '♔', Q: '♕', R: '♖', B: '♗', N: '♘', P: '♙' };
const BLACK = { K: '♚', Q: '♛', R: '♜', B: '♝', N: '♞', P: '♟' };

export const DEFAULT_PIECE_COLOR = { white: '#f4f6ff', black: '#ff5470' };
export const DEFAULT_BOARD = { light: '#454f77', dark: '#262e4d' };

export function glyph(piece, color) {
  const glyphs = color === 'black' ? BLACK : WHITE;
  return (glyphs[piece] ?? '') + '\uFE0E';
}

export function pieceColor(loadout, piece, color) {
  const asset = loadout?.[piece]?.asset;
  return asset != null && asset.type === 'stub'
    ? asset.color
    : DEFAULT_PIECE_COLOR[color];
}

export function boardColors(loadout) {
  const asset = loadout?.board?.asset;
  if (asset != null && asset.type === 'stub') {
    return { light: asset.light, dark: asset.dark };
  }
  return { ...DEFAULT_BOARD };
}
