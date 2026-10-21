(function () {
  function el(id) { return document.getElementById(id); }

  document.addEventListener('DOMContentLoaded', function () {
    if (!CD.state || !CD.isAdmin()) return;
    renderStats();
    renderUsers();
    renderLogs();
    initCfg();
    initSkinsCfg();
    el('usr-search').addEventListener('input', function () { renderUsers(); });
  });

  function renderStats() {
    var list = CD.userList();
    var totalBalance = list.reduce(function (s, u) { return s + u.balance; }, 0);
    var totalPieces = list.reduce(function (s, u) { return s + u.pieces.length; }, 0);
    var totalSpins = list.reduce(function (s, u) { return s + ((u.stats || {}).spins || 0); }, 0);
    el('ad-users').textContent = list.length;
    el('ad-pieces').textContent = totalPieces;
    el('ad-balance').textContent = CD.fmt(totalBalance);
    el('ad-spins').textContent = totalSpins;
  }

  function renderUsers() {
    var list = CD.userList();
    var q = el('usr-search').value.trim().toLowerCase();
    if (q) {
      list = list.filter(function (u) {
        return u.name.toLowerCase().indexOf(q) !== -1 || (u.email || '').toLowerCase().indexOf(q) !== -1;
      });
    }
    var body = el('users-table').querySelector('tbody');
    body.innerHTML = '';
    if (list.length === 0) {
      var emptyTr = document.createElement('tr');
      emptyTr.innerHTML = '<td colspan="6" style="text-align:center;color:var(--dim)">Никого не найдено</td>';
      body.appendChild(emptyTr);
      return;
    }
    list.sort(function (a, b) { return b.created - a.created; });
    list.forEach(function (u) {
      var tr = document.createElement('tr');
      var av = u.name.charAt(0).toUpperCase();
      var roleBadge = u.role === 'admin' ? '<span class="role-badge admin">ADMIN</span>' : '<span class="role-badge user">USER</span>';
      var banBadge = u.banned ? '<span class="role-badge banned">BAN</span>' : '';
      var btns = document.createElement('div');
      btns.className = 'row-actions';
      btns.innerHTML =
        '<button class="rbtn" data-act="plus" data-key="' + u.key + '">+100 ◈</button>' +
        '<button class="rbtn" data-act="minus" data-key="' + u.key + '">−100 ◈</button>' +
        '<button class="rbtn danger' + (u.banned ? ' ' : '') + '" data-act="ban" data-key="' + u.key + '">' + (u.banned ? 'Разбан' : 'Бан') + '</button>' +
        '<button class="rbtn" data-act="role" data-key="' + u.key + '">' + (u.role === 'admin' ? 'Демо-админ' : 'Сделать админом') + '</button>' +
        '<button class="rbtn" data-act="reset" data-key="' + u.key + '">Сброс склада</button>' +
        '<button class="rbtn danger" data-act="del" data-key="' + u.key + '">Удалить</button>';
      var tdAct = document.createElement('td');
      tdAct.appendChild(btns);
      tr.innerHTML =
        '<td><div class="profile-top"><div class="avatar" style="width:34px;height:34px;font-size:14px;border-radius:10px">' + av + '</div>' +
        '<div><div class="u-name">' + u.name + '</div><div style="color:var(--dim);font-size:11.5px;font-family:var(--mono)">' + (u.email || '') + '</div></div></div></td>' +
        '<td>' + roleBadge + banBadge + '</td>' +
        '<td class="mono">' + CD.fmt(u.balance) + ' ◈</td>' +
        '<td class="mono">' + u.pieces.length + ' шт · ' + CD.fmt(u.pieces.reduce(function (s, c) { return s + CD.PIECES[c].val; }, 0)) + ' ◈</td>' +
        '<td class="mono" style="color:var(--dim)">' + new Date(u.created).toLocaleDateString('ru-RU') + '</td>';
      tr.appendChild(tdAct);
      body.appendChild(tr);
    });
    body.querySelectorAll('button.rbtn').forEach(function (b) {
      b.addEventListener('click', onAction);
    });
  }

  function onAction(e) {
    var key = e.currentTarget.dataset.key;
    var act = e.currentTarget.dataset.act;
    var match = CD.userList().filter(function (u) { return u.key === key; })[0];
    if (!match) return;

    switch (act) {
      case 'plus':
        CD.patchUserBalance(key, 100);
        CD.toast('+' + 100 + ' ◈ игроку ' + match.name, 'success');
        log('admin', { t: 'ad', note: '+100 ◈ → ' + match.name });
        afterChange();
        break;
      case 'minus':
        CD.patchUserBalance(key, -100);
        CD.toast('−' + 100 + ' ◈ у ' + match.name, 'fail');
        log('admin', { t: 'ad', note: '−100 ◈ ← ' + match.name });
        afterChange();
        break;
      case 'ban':
        CD.patchUser(key, { banned: !match.banned });
        CD.toast(match.banned ? 'Бан снят: ' + match.name : 'Забанил: ' + match.name, match.banned ? 'success' : 'fail');
        log('admin', { t: 'ad', note: (match.banned ? 'Разбан ' : 'Бан ') + match.name });
        afterChange();
        break;
      case 'role':
        var role = match.role === 'admin' ? 'user' : 'admin';
        if (confirm('Сделать роль "' + role + '" для ' + match.name + '?')) {
          CD.patchUser(key, { role: role });
          CD.toast('Роль ' + match.name + ' теперь: ' + role, 'info');
          log('admin', { t: 'ad', note: 'Роль ' + match.name + ' → ' + role });
          afterChange();
        }
        break;
      case 'reset':
        if (confirm('Обнулить склад ' + match.name + '?')) {
          CD.patchUser(key, { pieces: [] });
          CD.toast('Склад ' + match.name + ' сброшен', 'info');
          log('admin', { t: 'ad', note: 'Склад сброшен: ' + match.name });
          afterChange();
        }
        break;
      case 'del':
        if (match.key === CD.user) { CD.toast('Сам себя не удалишь)', 'fail'); return; }
        if (confirm('Удалить аккаунт ' + match.name + ' навсегда?')) {
          CD.removeUser(key);
          CD.toast('Аккаунт ' + match.name + ' удалён', 'fail');
          log('admin', { t: 'ad', note: 'Аккаунт удалён: ' + match.name });
          afterChange();
        }
        break;
    }
  }

  function afterChange() {
    renderStats();
    renderUsers();
  }

  function initCfg() {
    var c = CD.config();
    el('cf-start').value = c.startingBalance;
    el('cf-case').value = c.caseCost;
    el('cf-fee').value = c.upgradeFeePct;
    el('btn-cfg').addEventListener('click', function () {
      var s0 = Math.max(0, parseInt(el('cf-start').value || '0', 10));
      var cost = Math.max(0, parseInt(el('cf-case').value || '0', 10));
      var fee = Math.min(50, Math.max(0, parseInt(el('cf-fee').value || '10', 10)));
      if (isNaN(s0) || isNaN(cost) || isNaN(fee)) {
        CD.toast('Введи нормальные числа', 'fail');
        return;
      }
      CD.saveConfig({ startingBalance: s0, caseCost: cost, upgradeFeePct: fee });
      CD.toast('Конфиг сохранён', 'success');
      el('cfg-note').textContent = 'Старт баланс новых юзеров: ' + s0 + ' ◈ · кейс: ' + cost + ' ◈ · комиссия: ' + fee + '%';
    });
  }

  function initSkinsCfg() {
    var c = CD.config();
    el('cf-skin-cost').value = c.skinCaseCost;
    el('cf-slot-cost').value = c.slotCost;
    el('cf-skin-weights').value = JSON.stringify(c.skinWeights || {});
    el('btn-cfg-skins').addEventListener('click', function () {
      var w;
      try {
        w = JSON.parse(el('cf-skin-weights').value);
      } catch (e) {
        CD.toast('Веса редкостей — некорректный JSON', 'fail');
        return;
      }
      var skinCost = Math.max(0, parseInt(el('cf-skin-cost').value || '0', 10) || 0);
      var slotCost = Math.max(0, parseInt(el('cf-slot-cost').value || '0', 10) || 0);
      CD.saveConfig({ skinCaseCost: skinCost, slotCost: slotCost, skinWeights: w });
      CD.toast('Скин-конфиг сохранён', 'success');
      el('cfg-note').textContent = 'Скин-кейс: ' + skinCost + ' ◈ · слот: ' + slotCost + ' ◈';
    });
  }

  function renderLogs() {
    var box = el('logs-list');
    box.innerHTML = '';
    var list = [];
    CD.userList().forEach(function (u) {
      (u.hist || []).forEach(function (h) {
        list.push(Object.assign({ user: u.name }, h));
      });
    });
    list.sort(function (a, b) { return b.time - a.time; });
    if (list.length === 0) {
      box.innerHTML = '<div class="hist-empty">Лог пуст. Пусть играют.</div>';
      return;
    }
    list.slice(0, 30).forEach(function (row) {
      var d = document.createElement('div');
      d.className = 'hist-row';
      d.innerHTML =
        '<span class="tag ' + (row.tag || '') + '">' + logTag(row.t) + '</span>' +
        '<span style="color:var(--muted)">@' + row.user + '</span>' +
        '<span>' + row.note + '</span>' +
        '<time>' + new Date(row.time).toLocaleString('ru-RU') + '</time>';
      box.appendChild(d);
    });
  }

  function logTag(t) {
    switch (t) {
      case 'upgrade': return 'апгрейд';
      case 'case': return 'кейс';
      case 'board': return 'доска';
      case 'sell': return 'продажа';
      case 'fee': return 'комиссия';
      case 'ad': return 'админ';
      default: return 'инфо';
    }
  }

  function log(user, entry) {
    var users = CD.usersAll();
    if (!users[user]) return;
    users[user].hist = users[user].hist || [];
    users[user].hist.unshift(Object.assign(Object.assign({}, entry), { time: Date.now() }));
    users[user].hist = users[user].hist.slice(0, 60);
    CD.save();
  }
})();
