import { api } from './api.js';
import { h } from './dom.js';

const SECTIONS = [
  ['Играть', '/index.html', 'play'],
  ['Смотреть', '/live.html', 'live'],
  ['Магазин', '/cases.html', 'cases'],
  ['Инвентарь', '/inventory.html', 'inventory'],
  ['Апгрейд', '/upgrade.html', 'upgrade'],
  ['Маркет', '/market.html', 'market'],
  ['Лидеры', '/leaderboard.html', 'leaderboard'],
];

const TABBAR = [
  ['Играть', '/index.html', 'play'],
  ['Магазин', '/cases.html', 'cases'],
  ['Инвентарь', '/inventory.html', 'inventory'],
  ['Маркет', '/market.html', 'market'],
];

const MORE = [
  ['Смотреть', '/live.html', 'live'],
  ['Апгрейд', '/upgrade.html', 'upgrade'],
  ['Лидеры', '/leaderboard.html', 'leaderboard'],
  ['Подарки', '/gifts.html', 'gifts'],
  ['Профиль', '/profile.html', 'profile'],
];

let balanceEl = null;

export async function initLayout({ auth = 'required', active = '' } = {}) {
  let me = null;
  if (auth === 'required') {
    me = await api('GET', '/me');
  } else if (auth === 'optional') {
    try {
      me = await api('GET', '/me', undefined, { redirectOn401: false });
    } catch {
      me = null;
    }
  }

  const header = h('header', { class: 'topbar' });
  header.appendChild(h('a', { class: 'logo', href: '/index.html' }, 'ChessDep'));

  if (auth !== 'none') {
    const nav = h('nav', { class: 'topnav' });
    for (const [label, href, key] of SECTIONS) {
      nav.appendChild(h('a', { href, class: key === active ? 'active' : '' }, label));
    }
    header.appendChild(nav);

    const right = h('div', { class: 'topbar-right' });
    if (me !== null) {
      balanceEl = h('span', { class: 'balance pill' }, h('b', { id: 'balance-num' }, fmtBalance(me.balance)));
      right.appendChild(balanceEl);
      right.appendChild(h('a', { class: 'pill gift-badge', href: '/gifts.html', hidden: true }, 'Подарки'));
      right.appendChild(h('a', { class: 'pill login-link', href: '/profile.html' }, me.login));
      if (me.role === 'admin') {
        right.appendChild(h('a', { class: 'pill', href: '/admin.html' }, 'Админка'));
      }
      const out = h('button', { type: 'button', class: 'btn btn-ghost btn-sm btn-logout' }, 'Выйти');
      out.addEventListener('click', logout);
      right.appendChild(out);
      loadGiftBadge();
    } else {
      right.appendChild(h('a', { class: 'pill', href: '/login.html' }, 'Войти'));
    }
    header.appendChild(right);
  }

  document.body.prepend(header);

  if (auth !== 'none') {
    const tabbar = h('nav', { class: 'tabbar' });
    for (const [label, href, key] of TABBAR) {
      tabbar.appendChild(h('a', { href, class: key === active ? 'active' : '' }, label));
    }
    const inMore = MORE.some(([, , key]) => key === active);
    const moreBtn = h('button', { type: 'button', class: ['tabbar-more-btn', inMore ? 'active' : ''] }, 'Ещё');
    moreBtn.setAttribute('aria-expanded', 'false');
    const moreMenu = h('nav', { class: 'tabbar-menu', hidden: true });
    for (const [label, href, key] of MORE) {
      moreMenu.appendChild(h('a', { href, class: key === active ? 'active' : '' }, label));
    }
    if (me !== null) {
      const menuOut = h('button', { type: 'button', class: 'tabbar-menu-logout' }, 'Выйти');
      menuOut.addEventListener('click', logout);
      moreMenu.appendChild(menuOut);
    }
    moreBtn.addEventListener('click', () => {
      moreMenu.hidden = !moreMenu.hidden;
      moreBtn.setAttribute('aria-expanded', String(!moreMenu.hidden));
    });
    tabbar.appendChild(moreBtn);
    document.body.appendChild(moreMenu);
    document.body.appendChild(tabbar);
  }

  return me;
}

export function setBalance(n) {
  if (balanceEl === null) return;
  const num = balanceEl.querySelector('#balance-num');
  if (num) num.textContent = fmtBalance(n);
}

function fmtBalance(n) {
  return Number(n).toLocaleString('ru-RU') + ' ◈';
}

async function loadGiftBadge() {
  try {
    const out = await api('GET', '/me/gifts/unseen-count', undefined, { redirectOn401: false });
    const badge = document.querySelector('.gift-badge');
    if (out && out.count > 0 && badge) {
      badge.hidden = false;
      badge.textContent = 'Подарки · ' + out.count;
    }
  } catch {
    /* бейдж не критичен */
  }
}

async function logout() {
  try {
    await api('POST', '/auth/logout');
  } finally {
    location.href = '/login.html';
  }
}
