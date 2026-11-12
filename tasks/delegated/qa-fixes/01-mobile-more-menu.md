# 01 — Мобильное меню «Ещё» в нижнем таб-баре

Рабочая копия: /home/nik/PycharmProjects/.oc-wt/ChessDep/qa-fixes/more-menu (ветка `qa-mobile-more-menu`).
Работать ТОЛЬКО в ней. В /home/nik/PycharmProjects/ChessDep ничего не трогать и не переключать ветки.

## Проблема
На ширине ≤ 640px верхняя навигация скрыта, а в нижнем таб-баре 5 пунктов. Разделы «Смотреть», «Апгрейд»,
«Лидеры», «Подарки» и кнопка «Выйти» недоступны. Решение: последний пункт таб-бара — кнопка «Ещё»,
она открывает всплывающее меню над таб-баром.

## Меняешь ровно два файла

### 1. frontend/js/layout.js
a) Массив `TABBAR` заменить на (убран «Профиль»):
```js
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
```
b) Обработчик кнопки «Выйти» вынести в функцию модуля (в конец файла, рядом с `loadGiftBadge`):
```js
async function logout() {
  try {
    await api('POST', '/auth/logout');
  } finally {
    location.href = '/login.html';
  }
}
```
и в `initLayout` заменить существующий `out.addEventListener('click', async () => { ... });` на `out.addEventListener('click', logout);`.

c) Блок создания таб-бара (`if (auth !== 'none') { const tabbar = ...; document.body.appendChild(tabbar); }`) заменить на:
```js
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
```
Больше в layout.js ничего не менять.

### 2. frontend/css/layout.css
Сразу после правила `.tabbar a.active { color: var(--gold); }` вставить дословно:
```css
.tabbar-more-btn {
  flex: 1;
  display: grid;
  place-items: center;
  min-height: 52px;
  padding: 0;
  border: none;
  background: none;
  color: var(--muted);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.tabbar-more-btn.active { color: var(--gold); }

/* Меню «Ещё»: над таб-баром, только на мобильной ширине */
.tabbar-menu {
  position: fixed;
  right: 8px;
  bottom: calc(60px + env(safe-area-inset-bottom));
  z-index: 61;
  display: flex;
  flex-direction: column;
  min-width: 190px;
  padding: 6px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, .5);
}

.tabbar-menu[hidden] { display: none; }

.tabbar-menu a,
.tabbar-menu-logout {
  display: block;
  min-height: 44px;
  padding: 12px 14px;
  border: none;
  border-radius: 8px;
  background: none;
  color: var(--text);
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}

.tabbar-menu a.active { color: var(--gold); }
.tabbar-menu-logout { color: var(--red); border-top: 1px solid var(--line); border-radius: 0 0 8px 8px; }
```
И внутрь существующего `@media (max-width: 640px) { ... }` ничего не добавлять. После этого блока `@media` добавить:
```css
@media (min-width: 641px) {
  .tabbar-menu { display: none; }
}
```

## Проверка
1. `cd /home/nik/PycharmProjects/.oc-wt/ChessDep/qa-fixes/more-menu && bash scripts/check_frontend.sh` → `frontend check: OK`.
2. `git diff --stat` → изменены ровно `frontend/js/layout.js` и `frontend/css/layout.css`.
3. Закоммитить в ветку `qa-mobile-more-menu` сообщением `Фронт: меню «Ещё» в мобильном таб-баре`.
Браузерную проверку не делай: живой стек смотрит в основную копию, не в твою.

## Если что-то не сходится
Если фрагмент для замены не найден дословно или check_frontend падает не из-за твоих строк — остановись,
ничего не придумывай, опиши проблему в финальном ответе.
