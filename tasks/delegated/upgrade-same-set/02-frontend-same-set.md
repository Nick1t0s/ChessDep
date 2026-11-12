# Цель
На странице апгрейда (`frontend/js/upgrade.js`) разрешить выбирать входы и цель только из одного набора.

# Контекст
Сервер теперь требует: все входные предметы и цель — из одного набора, иначе причина `UPGRADE_SET_MISMATCH`.
У предмета инвентаря набор: `item.def.set.code` (строка). У цели: `def.set.code`.
Прочитай `frontend/js/upgrade.js` целиком. Правила фронта: DOM только через `h()`/`textContent`, никакого `innerHTML`.

# Область
Только `frontend/js/upgrade.js`. Другие файлы не трогать.

# Контракт — ровно 4 правки
1. В объект `REASON_RU` добавить строку после `UPGRADE_TARGET_NOT_AVAILABLE`:
   `  UPGRADE_SET_MISMATCH: 'Апгрейд возможен только внутри одного набора',`

2. После функции `sumValue()` добавить функцию:
```js
function selectedSetCode() {
  for (const id of selected) {
    const item = items.find((it) => it.id === id);
    if (item) return item.def.set.code;
  }
  return null;
}
```

3. В `renderTargets()` сразу после строки `const sum = sumValue();` добавить
   `  const setCode = selectedSetCode();`
   а внутри цикла `for (const def of targets) {` первой строкой добавить
   `    if (setCode !== null && def.set.code !== setCode) continue;`

4. В `toggleItem(id)` в ветке `else` (добавление) перед `selected.add(id);` (после проверки на 10) вставить:
```js
    const item = items.find((it) => it.id === id);
    const setCode = selectedSetCode();
    if (item && setCode !== null && item.def.set.code !== setCode) {
      toast('Апгрейд возможен только внутри одного набора', 'error');
      return;
    }
```
   И после строки `if (selected.size === 0) target = null;` добавить:
```js
  if (target !== null && selected.size > 0 && target.set.code !== selectedSetCode()) target = null;
```

# Готово, когда
`bash scripts/check_frontend.sh` проходит без ошибок. `git diff` показывает изменения только в `frontend/js/upgrade.js`, только 4 описанные правки.

# Нельзя
Менять что-либо ещё в файле, переименовывать, переформатировать. Если что-то не сходится с описанием — остановиться и описать в SUMMARY.
