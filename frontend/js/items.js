import { h } from './dom.js';
import { glyph } from './pieces.js';
import { fmtCrystals } from './format.js';

export const RARITIES = ['common', 'uncommon', 'rare', 'epic', 'legendary', 'mythic'];
export const RARITY_RU = {
  common: 'Обычный', uncommon: 'Необычный', rare: 'Редкий',
  epic: 'Эпический', legendary: 'Легендарный', mythic: 'Мифический',
};
export const EXTERIOR_RU = {
  FN: 'Прямо с завода', MW: 'Немного поношенное', FT: 'После полевых испытаний',
  WW: 'Поношенное', BS: 'Закалённое в боях',
};
export const SLOT_RU = {
  P: 'Пешка', N: 'Конь', B: 'Слон', R: 'Ладья', Q: 'Ферзь', K: 'Король', board: 'Доска',
};

export function skinPreview(def) {
  if (def.kind === 'board_skin') {
    const grid = h('div', { class: 'skin-board' });
    for (let i = 0; i < 16; i++) {
      const cellClass = (Math.floor(i / 4) + i) % 2 === 1 ? 'cell dark' : 'cell light';
      grid.appendChild(h('span', { class: cellClass }));
    }
    grid.style.setProperty('--light', def.asset.light);
    grid.style.setProperty('--dark', def.asset.dark);
    return h('div', { class: 'skin-preview' }, grid);
  }
  const glyphSpan = h('span', { class: 'skin-glyph' }, glyph(def.piece_type, 'white'));
  glyphSpan.style.setProperty('--piece-color', def.asset.color);
  return h('div', { class: 'skin-preview' }, glyphSpan);
}

export function itemCard(def, opts = {}) {
  const classes = ['item-card', 'r-' + def.rarity];
  if (opts.selected === true) classes.push('selected');
  if (opts.onClick) classes.push('clickable');
  const root = h('div', { class: classes.join(' ') },
    skinPreview(def),
    h('div', { class: 'item-name' }, def.name),
    h('div', { class: 'item-meta' },
      h('span', { class: 'item-rarity' }, RARITY_RU[def.rarity]),
      h('span', { class: 'item-value mono' }, fmtCrystals(def.value))),
    opts.exterior ? h('div', { class: 'item-exterior' }, EXTERIOR_RU[opts.exterior] ?? opts.exterior) : null,
    opts.badge ? h('span', { class: 'item-badge' }, opts.badge) : null,
  );
  if (opts.onClick) {
    root.addEventListener('click', opts.onClick);
    root.setAttribute('role', 'button');
    root.setAttribute('tabindex', '0');
  }
  if (opts.extra) root.appendChild(opts.extra);
  return root;
}
