# Цель
Превью скина на карточках (`skinPreview` в `frontend/js/items.js`) показывает PNG-картинку вместо глифа/сетки цветов.

# Контекст
Прочитай: `docs/contracts-skins.md` §3, §7, `frontend/js/pieces.js` (функция `skinUrl(asset)`), `frontend/js/items.js`, `frontend/css/items.css`.
`def.asset` теперь всегда `{type: "png", image: "<sha256>"}`. `skinPreview(def)` должна использовать ТОЛЬКО `def.kind` и `def.asset` (админка вызывает её с объектом `{kind, asset}`).
У `h()` нет атрибутов `src`/`alt` — их задают свойствами элемента.

# Область
Только `frontend/js/items.js` и `frontend/css/items.css`.

# Правки items.js
1. `import { glyph } from './pieces.js';` → `import { skinUrl } from './pieces.js';`
2. Функцию `skinPreview` заменить целиком на:
```js
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
```

# Правки items.css
Удалить 5 строк — правила `.skin-glyph`, `.skin-board` (две строки), `.skin-board .cell.light`, `.skin-board .cell.dark` — и на их место вставить:
```css
.skin-img { width: 72px; height: 72px; object-fit: contain; filter: drop-shadow(0 2px 4px rgba(0, 0, 0, .5)); }
.skin-img-board { width: 76px; height: 76px; border-radius: 4px; filter: none; }
```

# Готово, когда
`bash scripts/check_frontend.sh` → `frontend check: OK`; `grep -rn "skin-glyph\|skin-board\|glyph" frontend/js/items.js frontend/css/items.css` пусто; `git diff --stat` — два файла.

# Нельзя
Трогать другие файлы и функции. Если что-то не сходится — остановиться и описать в SUMMARY.
