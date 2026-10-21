(function () {
  var params = new URLSearchParams(location.search);
  var tab = params.get('tab') || 'login';
  var next = params.get('next') || 'index.html';
  var err = params.get('err');

  document.addEventListener('DOMContentLoaded', function () {
    var tabs = document.querySelectorAll('.auth-tabs button');

    function showTab(name) {
      tabs.forEach(function (b) {
        b.classList.toggle('on', b.dataset.tab === name);
      });
      document.getElementById('form-login').classList.toggle('show', name === 'login');
      document.getElementById('form-register').classList.toggle('show', name === 'register');
    }

    tabs.forEach(function (b) {
      b.addEventListener('click', function () { showTab(b.dataset.tab); });
    });

    if (err) {
      var boxE = document.getElementById('err-login');
      boxE.classList.add('show');
      boxE.textContent = err;
    }
    showTab(tab === 'register' ? 'register' : 'login');
    bindLogin();
    bindRegister();
  });

  function fieldMsg(input, msg) {
    var f = input.closest('.field');
    var m = f.querySelector('.msg');
    if (m) m.textContent = msg || '';
    f.classList.toggle('err', !!msg);
  }

  function bindLogin() {
    var form = document.getElementById('form-login');
    var name = document.getElementById('li-name');
    var pass = document.getElementById('li-pass');
    var errBox = document.getElementById('err-login');

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      errBox.classList.remove('show');
      if (!name.value.trim()) { fieldMsg(name, 'Введи логин'); return; }
      fieldMsg(name, '');
      if (!pass.value) { fieldMsg(pass, 'Введите пароль'); return; }
      fieldMsg(pass, '');
      var res = CD.login(name.value.trim(), pass.value);
      if (res) {
        errBox.textContent = res;
        errBox.classList.add('show');
      } else {
        CD.toast('С возвращением, ' + name.value.trim() + '!', 'success');
        location.href = next;
      }
    });
  }

  function bindRegister() {
    var form = document.getElementById('form-register');
    var name = document.getElementById('rg-name');
    var email = document.getElementById('rg-email');
    var pass = document.getElementById('rg-pass');
    var pass2 = document.getElementById('rg-pass2');
    var terms = document.getElementById('rg-terms');
    var errBox = document.getElementById('rg-err');

    form.addEventListener('submit', function (e) {
      e.preventDefault();
      errBox.classList.remove('show');
      var ok = true;

      if (name.value.trim().length < 3) { fieldMsg(name, 'Минимум 3 символа'); ok = false; }
      else if (name.value.trim().length > 16) { fieldMsg(name, 'Максимум 16 символов'); ok = false; }
      else if (!/^[A-Za-z0-9_-]+$/u.test(name.value.trim())) { fieldMsg(name, 'Только латиница, цифры, _ и -'); ok = false; }
      else fieldMsg(name, '');

      var em = email.value.trim().toLowerCase();
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(em)) { fieldMsg(email, 'Введи корректный email'); ok = false; }
      else fieldMsg(email, '');

      if (pass.value.length < 6) { fieldMsg(pass, 'Минимум 6 символов'); ok = false; }
      else fieldMsg(pass, '');

      if (pass2.value !== pass.value) { fieldMsg(pass2, 'Пароли не совпадают'); ok = false; }
      else fieldMsg(pass2, '');

      if (!terms.checked) {
        errBox.textContent = 'Нужно согласиться с правилами и условиями';
        errBox.classList.add('show');
        ok = false;
      }
      if (!ok) return;

      var res = CD.register(name.value.trim(), em, pass.value);
      if (res) {
        errBox.textContent = res;
        errBox.classList.add('show');
        return;
      }
      var first = document.querySelector('.auth-note.is-first');
      if (first && CD.isAdmin()) {
        first.classList.add('show');
        first.textContent = 'Аккаунт создан. Это первый аккаунт, поэтому роль назначена админская.';
      }
      CD.toast('Аккаунт ' + name.value.trim() + ' создан', 'success');
      location.href = next;
    });
  }
})();
