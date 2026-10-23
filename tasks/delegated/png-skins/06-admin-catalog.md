# Цель
В админке каталога (`frontend/js/admin/catalog.js`) вместо полей цвета — загрузка PNG-картинок скинов.

# Контекст
Прочитай: `docs/contracts-skins.md` (§1, §3, §4, §7), `frontend/js/api.js` (готовая `apiUpload(path, file)` → JSON `{image, kind, url}`), `frontend/js/admin/catalog.js` целиком.
`skinPreview(def)` из `items.js` рисует картинку по `def.kind` и `def.asset` (`{type: 'png', image}`) — её параллельно переделывает другой исполнитель, просто вызывай.
У `h()` нет атрибута `accept` — задать свойством: `input.accept = 'image/png'`.
Правила фронта: DOM только через `h()`/`textContent`, без `innerHTML`.

# Область
Только `frontend/js/admin/catalog.js` и `frontend/css/admin.css`.

# Правки catalog.js
1. Импорт `import { api } from '../api.js';` → `import { api, apiUpload } from '../api.js';`
2. Удалить константы `DEFAULT_COLOR` и `COLOR_RE`.
3. После функции `field(...)` добавить:
```js
// Поле PNG скина: файл сразу грузится на сервер, picker.image — id картинки или null.
function imagePicker(kind, initialImage) {
  const picker = { image: initialImage, el: null };
  const preview = h('span', { class: 'admin-skin-preview' });
  const input = h('input', { type: 'file' });
  input.accept = 'image/png';
  function showPreview() {
    clear(preview);
    if (picker.image !== null) preview.appendChild(skinPreview({ kind, asset: { type: 'png', image: picker.image } }));
  }
  input.addEventListener('change', async () => {
    const file = input.files?.[0];
    if (!file) return;
    try {
      const res = await apiUpload('/admin/skin-images?kind=' + kind, file);
      picker.image = res.image;
      showPreview();
    } catch (err) {
      input.value = '';
      toast(err.message, 'error');
    }
  });
  showPreview();
  picker.el = h('div', { class: 'admin-skin-picker' }, input, preview);
  return picker;
}
```
4. `createCollectionForm`: заголовок колонки `h('th', {}, 'Цвет')` → `h('th', {}, 'Картинка 128×128')`. В обработчике submit условие
`if (!Number.isInteger(value) || value < 1 || !COLOR_RE.test(row.colorIn.value.trim())) {` → `if (!Number.isInteger(value) || value < 1 || row.picker.image === null) {`,
текст тоста → `'Строка «' + SLOT_RU[row.slot] + '»: проверьте ценность и загрузите картинку'`,
`asset: { type: 'stub', color: row.colorIn.value.trim() },` → `asset: { type: 'png', image: row.picker.image },`.
5. `makePiecesRow`: строку `const colorIn = h('input', …DEFAULT_COLOR[side] });` → `const picker = imagePicker('piece', null);`; `h('td', {}, colorIn),` → `h('td', {}, picker.el),`; `return { slot, tr, rarSel, valIn, colorIn, upIn };` → `return { slot, tr, rarSel, valIn, picker, upIn };`. Если переменная `side` после этого не используется — удалить строку `const side = slot[0];`.
6. `createBoardForm`: строки `lightIn`/`darkIn` → `const picker = imagePicker('board', null);`; два поля `field('Светлые клетки', lightIn), field('Тёмные клетки', darkIn),` → `field('Картинка 1088×1088', picker.el),`. В submit удалить `const light = …`, `const dark = …` и проверку `COLOR_RE` с тостом «Проверьте цвета клеток»; вместо неё:
```js
    if (picker.image === null) {
      toast('Загрузите картинку доски', 'error');
      return;
    }
```
`asset: { type: 'stub', light, dark },` → `asset: { type: 'png', image: picker.image },`.
7. `openEditModal`: блок `const assetInputs = {}; if (isBoard) {…} else {…}` → `const picker = imagePicker(def.kind, def.asset.image);`. Две строки полей `isBoard ? field('Светлые клетки'…` и `isBoard ? field('Тёмные клетки'…` → одна: `field(isBoard ? 'Картинка 1088×1088' : 'Картинка 128×128', picker.el),`. В onClick удалить блок `if (isBoard) { if (!COLOR_RE.test(…)) {…} }`. Вызов → `await saveItemDef(d, def, { name, value, upIn, rarSel, picker });`.
8. `saveItemDef(d, def, { name, value, upIn, rarSel, picker })`: значение `asset:` → `asset: { type: 'png', image: picker.image },`.

# Правки admin.css (в конец файла)
```css
.admin-skin-picker { display: flex; align-items: center; gap: 8px; }
.admin-skin-picker .skin-preview { height: 48px; }
.admin-skin-picker .skin-img { width: 44px; height: 44px; }
```

# Готово, когда
`bash scripts/check_frontend.sh` → OK; `grep -n "stub\|COLOR_RE\|DEFAULT_COLOR\|colorIn\|lightIn\|darkIn\|assetInputs" frontend/js/admin/catalog.js` пусто; `git diff --stat` — два файла.

# Нельзя
Трогать другие файлы и прочий код. Если что-то не сходится — остановиться и описать в SUMMARY.
