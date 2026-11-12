# Цель
Маркет: фильтр по стороне вместо вида. Список кейсов: подпись коллекций.

# Контекст
Прочитай: `docs/contracts-collections.md` (п. 6.1 `CaseOut`, 6.3 `/market`, п. 7), `frontend/js/market.js`, `frontend/js/cases.js`.

# Область
`frontend/js/market.js`, `frontend/js/cases.js`.

# Что сделать
- `market.js`: `kindSel` переименовать в `sideSel` = `mkSelect([['', 'Все'], ['w', 'Белые'], ['b', 'Чёрные']])` (везде, где использовался `kindSel`); в `loadFeed`: `if (sideSel.value) params.set('side', sideSel.value);`. Больше ничего не менять.
- `cases.js`: строку с `'Коллекция ' + c.collection.name` заменить на `h('p', { class: 'case-collection' }, collectionsLabel(c.collections))` и добавить функцию:
```js
function collectionsLabel(cols) {
  if (!Array.isArray(cols) || cols.length === 0) return '';
  if (cols.length === 1) return 'Коллекция ' + cols[0].name;
  return 'Смешанный: ' + cols.map((c) => c.name).join(', ');
}
```

# Готово, когда
`bash scripts/check_frontend.sh` печатает `frontend check: OK`; `grep -n "kind\|c.collection\b" frontend/js/market.js frontend/js/cases.js` не находит `kindSel`, `piece_skin`, `c.collection.name`.

# Правила фронта
- DOM только через `h()` / `textContent` из `frontend/js/dom.js`. Запрещено: `innerHTML`, `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval`, `setAttribute('style', …)`, `Math.random`, `localStorage`, `sessionStorage`, `document.cookie`, инлайн-стили/скрипты. Цвета — только `el.style.setProperty(...)`.
- Фронт ничего не вычисляет из игровой логики, только показывает ответы API.
- Тексты интерфейса — по-русски, дословно как в задаче.
