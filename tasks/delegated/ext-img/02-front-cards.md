# ТЗ ext-img-front: карточки экземпляров показывают картинку своего качества

Рабочая папка: /home/nik/PycharmProjects/.oc-wt/ChessDep/ext-img/front (ветка ext-img-front).
НИКОГДА не заходи в /home/nik/PycharmProjects/ChessDep и не переключай там ветки.
Контракт: docs/contracts-skins.md §8. Сервер отдаёт у экземпляра поле `image` (sha256 или null). Меняй ТОЛЬКО перечисленное.
Правила фронта: DOM только через h()/textContent, без innerHTML.

## 1. frontend/js/items.js
- `skinPreview(def)` → `skinPreview(def, image = null)`. Первая строка тела:
  `const url = image ? skinUrl({ type: 'png', image }) : skinUrl(def.asset);` Остальное без изменений.
- `itemCard`: вызов `skinPreview(def)` заменить на `skinPreview(def, opts.image ?? null)`.
- `invItemCard`: в объекте для itemCard после `exterior: item.exterior,` добавить `image: item.image,`.

## 2. Передать image там, где передаётся exterior экземпляра
- frontend/js/market.js: оба вызова `itemCard(l.item.def, { exterior: l.item.exterior, ...` — после строки `exterior: l.item.exterior,` добавить `image: l.item.image,`.
- frontend/js/upgrade.js: в `renderInventory` после `exterior: item.exterior,` добавить `image: item.image,`; в модалке успеха `itemCard(res.item.def, { exterior: res.item.exterior })` → `itemCard(res.item.def, { exterior: res.item.exterior, image: res.item.image })`.
- frontend/js/case.js: `itemCard(res.item.def, { exterior: res.item.exterior })` → `itemCard(res.item.def, { exterior: res.item.exterior, image: res.item.image })`.
Другие вызовы itemCard/skinPreview (дропы, лента, цели апгрейда, market-item.js, admin/) НЕ трогать.

## Проверка
`bash scripts/check_frontend.sh` — без ошибок. `git diff` содержит только описанные строки. Затем `git add -A && git commit -m "Фронт: картинка экземпляра по качеству в карточках"`.

## Если что-то не сходится
Остановись, опиши проблему в отчёте. В отчёте — вывод check_frontend.sh и `git diff --stat`.
