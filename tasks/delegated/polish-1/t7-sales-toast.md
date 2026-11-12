# T7. Тосты о продажах на маркете (фронт)

Worktree: /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t7
Файл: только `frontend/js/layout.js`.

Контракт API (делается параллельно, на него не смотри): `GET /api/v1/me/sales/unseen` → `{"sales": [{"listing_id": int, "name": str, "price": int, "payout": int, "buyer_login": str, "closed_at": str}], "balance": int}`; возвращённые продажи сервер сам помечает увиденными. Тосты (`toast.js`) уже показываются справа сверху.

1. После строки `import { h } from './dom.js';` добавить:
```js
import { toast } from './toast.js';
import { playSound } from './sound.js';
```
2. В `initLayout` сразу после строки `      loadGiftBadge();` добавить:
```js
      pollSales();
      setInterval(pollSales, 15000);
```
3. Сразу после функции `loadGiftBadge` (перед `async function logout`) добавить:
```js
// Уведомления о продажах на маркете: тост справа сверху, звук, свежий баланс.
async function pollSales() {
  if (document.hidden) return;
  try {
    const out = await api('GET', '/me/sales/unseen', undefined, { redirectOn401: false });
    if (!out || !Array.isArray(out.sales) || out.sales.length === 0) return;
    for (const sale of out.sales) {
      toast('Продано: ' + sale.name + ' за ' + fmtBalance(sale.price) + ' · вам +' + fmtBalance(sale.payout), 'success');
    }
    playSound('sale');
    setBalance(out.balance);
  } catch {
    /* уведомления не критичны */
  }
}
```

## Проверка
`cd /home/nik/PycharmProjects/.oc-wt/ChessDep/polish1/t7 && bash scripts/check_frontend.sh` → «frontend check: OK».
