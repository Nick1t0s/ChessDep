# ТЗ ext-req-admin: обязательные картинки всех качеств в админке

Рабочая папка: /home/nik/PycharmProjects/.oc-wt/ChessDep/ext-req/admin (ветка ext-req-admin).
НИКОГДА не заходи в /home/nik/PycharmProjects/ChessDep и не переключай там ветки.
Контракт: docs/contracts-skins.md §8. Меняй ТОЛЬКО frontend/js/admin/catalog.js.
Правила фронта: DOM только через h()/textContent/appendChild, без innerHTML и инлайн-стилей.

## 1. imagePicker
Вернуть прежнюю сигнатуру `imagePicker(kind, initialImage)`: удалить параметр `clearable` и весь блок `if (clearable) {...}` с кнопкой «Убрать».

## 2. Новые функции (сразу после imagePicker)
```js
// Пять обязательных картинок качеств; initial — asset.exteriors или null.
function exteriorPickers(kind, initial) {
  const pickers = {};
  for (const ext of EXTERIORS) pickers[ext] = imagePicker(kind, initial?.[ext] ?? null);
  return pickers;
}

// asset из основной картинки и картинок всех качеств; null, если чего-то не хватает.
function buildAsset(picker, extPickers) {
  if (picker.image === null) return null;
  const exteriors = {};
  for (const ext of EXTERIORS) {
    if (extPickers[ext].image === null) return null;
    exteriors[ext] = extPickers[ext].image;
  }
  return { type: 'png', image: picker.image, exteriors };
}
```

## 3. Создание коллекции
- `makePiecesRow`: после `const picker = imagePicker('piece', null);` добавить `const extPickers = exteriorPickers('piece', null);`; в `tr` после `h('td', {}, picker.el),` добавить `...EXTERIORS.map((ext) => h('td', {}, extPickers[ext].el)),`; вернуть `{ slot, tr, rarSel, valIn, picker, extPickers, upIn }`.
- В thead формы после `h('th', {}, 'Картинка 128×128'),` добавить `...EXTERIORS.map((ext) => h('th', {}, EXTERIOR_RU[ext])),`.
- В submit: заменить условие `row.picker.image === null` на `buildAsset(row.picker, row.extPickers) === null`; текст тоста: `'Строка «' + SLOT_RU[row.slot] + '»: проверьте ценность и загрузите все картинки'`; `asset: buildAsset(row.picker, row.extPickers),`.

## 4. Создание доски (createBoardForm)
- После `const picker = imagePicker('board', null);` — `const extPickers = exteriorPickers('board', null);`.
- В форме после `field('Картинка 1088×1088', picker.el),` — `...EXTERIORS.map((ext) => field('Картинка: ' + EXTERIOR_RU[ext], extPickers[ext].el)),`.
- В submit: проверку `if (picker.image === null) {...}` заменить на `const asset = buildAsset(picker, extPickers); if (asset === null) { toast('Загрузите основную картинку и картинки всех качеств', 'error'); return; }`; в теле запроса `asset,`.

## 5. Окно «Изменить скин» (openEditModal / saveItemDef)
- Цикл создания extPickers заменить на `const extPickers = exteriorPickers(def.kind, def.asset.exteriors);`.
- В onClick «Сохранить» после проверки value добавить:
  `const asset = buildAsset(picker, extPickers); if (asset === null) { toast('Загрузите основную картинку и картинки всех качеств', 'error'); return false; }`
  и вызывать `saveItemDef(d, def, { name, value, upIn, rarSel, asset })`.
- `saveItemDef(d, def, { name, value, upIn, rarSel, asset })`: удалить сборку exteriors внутри, в body `asset,`.

## Проверка
`bash scripts/check_frontend.sh` — OK. `grep -n "clearable\|Убрать" frontend/js/admin/catalog.js` — пусто. Затем `git add -A && git commit -m "Админка: обязательные картинки всех качеств"`.

## Если что-то не сходится
Остановись, опиши в отчёте. В отчёте — вывод check_frontend.sh и `git diff --stat`.
