import { h } from './dom.js';
import { skinUrl } from './pieces.js';
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
  wP: 'Белая пешка', wN: 'Белый конь', wB: 'Белый слон', wR: 'Белая ладья', wQ: 'Белый ферзь', wK: 'Белый король',
  bP: 'Чёрная пешка', bN: 'Чёрный конь', bB: 'Чёрный слон', bR: 'Чёрная ладья', bQ: 'Чёрный ферзь', bK: 'Чёрный король',
  board: 'Доска',
};
export const WHITE_SLOTS = ['wP', 'wN', 'wB', 'wR', 'wQ', 'wK'];
export const BLACK_SLOTS = ['bP', 'bN', 'bB', 'bR', 'bQ', 'bK'];
export const LOADOUT_SLOTS = [...WHITE_SLOTS, ...BLACK_SLOTS, 'board'];
export const SIDE_RU = { w: 'Белые', b: 'Чёрные' };
export const CASE_KIND_RU = { set: 'Набор', collection: 'Коллекция', custom: 'Особый' };

function setLine(def) {
  if (!def.set) return null;
  return def.collection ? def.set.name + ' · ' + def.collection.name : def.set.name;
}

export function skinPreview(def) {
  const url = skinUrl(def.asset);
  if (url === null) return h('div', { class: 'skin-preview' });
  const img = h('img', { class: def.kind === 'board' ? 'skin-img skin-img-board' : 'skin-img' });
  img.alt = '';
  img.draggable = false;
  img.loading = 'lazy';
  img.src = url;
  return h('div', { class: 'skin-preview' }, img);
}

export function casePreview(caseRef) {
  return h('div', { class: 'skin-preview case-preview' }, h('span', { class: 'case-glyph' }, '▣'));
}

export function itemCard(def, opts = {}) {
  const classes = ['item-card', 'r-' + def.rarity];
  if (opts.selected === true) classes.push('selected');
  if (opts.onClick) classes.push('clickable');
  const root = h('div', { class: classes.join(' ') },
    skinPreview(def),
    h('div', { class: 'item-name' }, def.name),
    setLine(def) ? h('div', { class: 'item-set' }, setLine(def)) : null,
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

export function invItemCard(item, opts = {}) {
  if (item.kind === 'case') {
    const card = h('div', { class: 'item-card r-case' + (opts.onClick ? ' clickable' : '') },
      casePreview(item.case),
      h('div', { class: 'item-name' }, item.case.name),
      h('div', { class: 'item-meta' }, h('span', { class: 'item-rarity' }, 'Кейс')),
      opts.badge ? h('span', { class: 'item-badge' }, opts.badge) : null,
    );
    if (opts.onClick) {
      card.addEventListener('click', opts.onClick);
      card.setAttribute('role', 'button');
      card.setAttribute('tabindex', '0');
    }
    if (opts.extra) card.appendChild(opts.extra);
    return card;
  }
  return itemCard(item.def, {
    ...opts,
    exterior: item.exterior,
    badge: opts.badge ?? (item.bound ? 'Базовый' : null),
  });
}
