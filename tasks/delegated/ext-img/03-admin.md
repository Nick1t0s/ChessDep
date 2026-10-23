# ТЗ ext-img-admin: поля картинок по качеству в окне «Изменить скин»

Рабочая папка: /home/nik/PycharmProjects/.oc-wt/ChessDep/ext-img/admin (ветка ext-img-admin).
НИКОГДА не заходи в /home/nik/PycharmProjects/ChessDep и не переключай там ветки.
Контракт: docs/contracts-skins.md §8. Меняй ТОЛЬКО frontend/js/admin/catalog.js (и, если нужно, стиль в frontend/css — только добавить класс, см. ниже).
Правила фронта: DOM только через h()/textContent/appendChild, без innerHTML, без инлайн-стилей.

## 1. imagePicker с кнопкой «Убрать»
Сигнатура: `function imagePicker(kind, initialImage, clearable = false)`. Если `clearable` — после превью добавить кнопку
`h('button', { type: 'button', class: 'btn btn-ghost btn-sm' }, 'Убрать')`, по клику: `picker.image = null; input.value = ''; showPreview();`.
Кнопка входит в `picker.el` (третьим ребёнком `admin-skin-picker`). Вызовы без третьего аргумента ведут себя как раньше.

## 2. Импорт
Добавить `EXTERIOR_RU` в импорт из '../items.js'. Константа в файле: `const EXTERIORS = ['FN', 'MW', 'FT', 'WW', 'BS'];` (рядом с DEFAULT_RARITY).

## 3. openEditModal
- После `const picker = imagePicker(def.kind, def.asset.image);` добавить:
```js
const extPickers = {};
for (const ext of EXTERIORS) {
  extPickers[ext] = imagePicker(def.kind, def.asset.exteriors?.[ext] ?? null, true);
}
```
- В `body` сразу после поля основной картинки добавить пять полей:
  `...EXTERIORS.map((ext) => field('Картинка: ' + EXTERIOR_RU[ext], extPickers[ext].el)),`
  (field принимает label и input; если field требует, чтобы второй аргумент был input — у picker.el ему присваивается id, это ок, так уже делается для основной картинки).
- В `saveItemDef(d, def, {...})` передать `extPickers` и в нём собрать:
```js
const exteriors = {};
for (const ext of EXTERIORS) {
  if (extPickers[ext].image !== null) exteriors[ext] = extPickers[ext].image;
}
const asset = { type: 'png', image: picker.image };
if (Object.keys(exteriors).length > 0) asset.exteriors = exteriors;
```
  и отправлять `asset` вместо `{ type: 'png', image: picker.image }`.
Формы создания коллекции и доски НЕ трогать.

## Проверка
`bash scripts/check_frontend.sh` — без ошибок. Затем `git add -A && git commit -m "Админка: картинки скина по качеству"`.

## Если что-то не сходится
Остановись, опиши в отчёте. В отчёте — вывод check_frontend.sh и `git diff --stat`.
