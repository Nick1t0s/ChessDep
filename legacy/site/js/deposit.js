(function () {
  var amount = 500;

  function el(id) { return document.getElementById(id); }

  document.addEventListener('DOMContentLoaded', function () {
    if (!CD.state) return;
    var presets = document.querySelectorAll('.preset');
    presets.forEach(function (b) {
      b.addEventListener('click', function () {
        amount = parseInt(b.dataset.sum, 10);
        presets.forEach(function (x) { x.classList.toggle('on', x === b); });
        el('dp-amount').value = amount;
      });
    });
    el('dp-amount').addEventListener('input', function () {
      amount = parseInt(el('dp-amount').value || '0', 10) || 0;
      presets.forEach(function (x) {
        x.classList.toggle('on', parseInt(x.dataset.sum, 10) === amount);
      });
    });
    document.querySelectorAll('.method').forEach(function (m) {
      m.addEventListener('click', function () {
        document.querySelectorAll('.method').forEach(function (x) {
          x.classList.toggle('on', x === m);
        });
      });
    });
    el('btn-deposit').addEventListener('click', deposit);
    el('btn-promo').addEventListener('click', promo);
  });

  function deposit() {
    if (!amount || amount < 10) {
      CD.toast('Минимум для пополнения — 10 ◈', 'fail');
      return;
    }
    CD.addBalance(amount);
    CD.pushHist({ t: 'deposit', tag: 'gold', note: 'Пополнение +' + amount + ' ◈ (демо)' });
    CD.toast('Начислено +' + amount + ' ◈', 'success');
    el('dp-amount').value = '';
    amount = 0;
    document.querySelectorAll('.preset').forEach(function (x) { x.classList.remove('on'); });
  }

  function promo() {
    var code = el('dp-promo').value.trim().toUpperCase();
    if (!code) {
      CD.toast('Введи промокод', 'fail');
      return;
    }
    if (code === 'LUDO') {
      if (CD.state.promoLUDO) {
        CD.toast('Промокод LUDO уже активирован на этом акке', 'fail');
        return;
      }
      CD.patchUser(CD.user, { promoLUDO: true });
      CD.addBalance(200);
      CD.pushHist({ t: 'deposit', tag: 'gold', note: 'Промокод LUDO: +200 ◈' });
      CD.toast('LUDO принят: +200 ◈', 'success');
      el('dp-promo').value = '';
      return;
    }
    CD.toast('Такого промокода нет. Подсказка: LUDO', 'fail');
  }
})();
