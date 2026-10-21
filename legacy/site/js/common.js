(function () {
  var KEY_USERS = 'chessdep_users_v1';
  var KEY_SESSION = 'chessdep_session_v1';
  var KEY_CONFIG = 'chessdep_config_v1';

  var DEFAULT_CONFIG = {
    startingBalance: 500,
    caseCost: 200,
    upgradeFeePct: 0,
    skinCaseCost: 350,
    slotCost: 50,
    skinWeights: { common: 50, uncommon: 26, rare: 14, epic: 6.5, legendary: 2.5, mythic: 1 }
  };

  var PIECES = {
    pawn:   { code: 'pawn',   name: 'Пешка',    glyph: '\u265F\uFE0E', val: 10,  rarity: 'common' },
    knight: { code: 'knight', name: 'Конь',     glyph: '\u265E\uFE0E', val: 30,  rarity: 'uncommon' },
    bishop: { code: 'bishop', name: 'Слон',     glyph: '\u265D\uFE0E', val: 30,  rarity: 'uncommon' },
    rook:   { code: 'rook',   name: 'Ладья',    glyph: '\u265C\uFE0E', val: 60,  rarity: 'rare' },
    queen:  { code: 'queen',  name: 'Ферзь',    glyph: '\u265B\uFE0E', val: 120, rarity: 'epic' },
    queen2: { code: 'queen2', name: 'Ферзь ×2', glyph: '\u265B\uFE0E', val: 240, rarity: 'mythic', duo: true },
    king:   { code: 'king',   name: 'Король',   glyph: '\u265A\uFE0E', val: 400, rarity: 'legendary' }
  };

  var SKINS = {
    'pawn-chalk':     { code: 'pawn-chalk',     name: 'Меловая',               piece: 'pawn',   rarity: 'common',    val: 5 },
    'pawn-asphalt':   { code: 'pawn-asphalt',   name: 'Асфальтовая',           piece: 'pawn',   rarity: 'common',    val: 6 },
    'pawn-legend':    { code: 'pawn-legend',    name: 'Пешка-легенда',         piece: 'pawn',   rarity: 'rare',      val: 25 },
    'pawn-gold':      { code: 'pawn-gold',      name: 'Золотая фишка',         piece: 'pawn',   rarity: 'epic',      val: 60 },
    'knight-steel':   { code: 'knight-steel',   name: 'Стальной скакун',       piece: 'knight', rarity: 'uncommon',  val: 40 },
    'knight-blue':    { code: 'knight-blue',    name: 'Синий дьявол',          piece: 'knight', rarity: 'rare',      val: 90 },
    'knight-chrome':  { code: 'knight-chrome',  name: 'Хромовый жеребец',      piece: 'knight', rarity: 'epic',      val: 160 },
    'knight-plasma':  { code: 'knight-plasma',  name: 'Плазменный скакун',     piece: 'knight', rarity: 'legendary', val: 320 },
    'bishop-ivory':   { code: 'bishop-ivory',   name: 'Слоновая кость',        piece: 'bishop', rarity: 'uncommon',  val: 40 },
    'bishop-magma':   { code: 'bishop-magma',   name: 'Магма',                 piece: 'bishop', rarity: 'epic',      val: 160 },
    'rook-brick':     { code: 'rook-brick',     name: 'Кирпичная ладья',       piece: 'rook',   rarity: 'common',    val: 12 },
    'rook-concrete':  { code: 'rook-concrete',  name: 'Бетонная башня',        piece: 'rook',   rarity: 'uncommon',  val: 70 },
    'rook-titan':     { code: 'rook-titan',     name: 'Титановая башня',       piece: 'rook',   rarity: 'rare',      val: 140 },
    'rook-ice':       { code: 'rook-ice',       name: 'Ледяная цитадель',      piece: 'rook',   rarity: 'epic',      val: 240 },
    'queen-crimson':  { code: 'queen-crimson',  name: 'Кровавая леди',         piece: 'queen',  rarity: 'rare',      val: 180 },
    'queen-amethyst': { code: 'queen-amethyst', name: 'Аметистовая',           piece: 'queen',  rarity: 'epic',      val: 360 },
    'queen-jade':     { code: 'queen-jade',     name: 'Нефритовая императрица', piece: 'queen', rarity: 'legendary', val: 520 },
    'queen-void':     { code: 'queen-void',     name: 'Королева пустоты',      piece: 'queen',  rarity: 'mythic',    val: 900 },
    'king-chrome':    { code: 'king-chrome',    name: 'Хромированный',         piece: 'king',   rarity: 'legendary', val: 900 },
    'king-pharaoh':   { code: 'king-pharaoh',   name: 'Чёрный фараон',         piece: 'king',   rarity: 'mythic',    val: 1500 }
  };

  var RCOL = {
    common: '#9aa4b2', uncommon: '#38e8ff', rare: '#8b5cf6',
    epic: '#ffc93c', legendary: '#ff7847', mythic: '#ff5470'
  };

  function read(k) {
    try { var s = JSON.parse(localStorage.getItem(k)); return s == null ? null : s; }
    catch (e) { return null; }
  }
  function write(k, v) {
    try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {}
  }

  var config = Object.assign({}, DEFAULT_CONFIG, read(KEY_CONFIG) || {});
  var users = read(KEY_USERS) || {};

  function hydrate(u) {
    if (!u.skins) u.skins = {};
    if (!u.slots) u.slots = {};
    if (!u.stats) u.stats = { spins: 0, upgradeWins: 0, upgradeLosses: 0, cases: 0, placements: 0 };
    if (!u.hist) u.hist = [];
    if (typeof u.boostUsed !== 'boolean') u.boostUsed = false;
  }
  Object.keys(users).forEach(function (k) { hydrate(users[k]); });

  function defaultUser(name, email, pass) {
    return {
      name: name, email: email, pass: pass,
      role: 'user', banned: false,
      balance: config.startingBalance,
      pieces: ['pawn', 'pawn', 'pawn', 'knight', 'knight', 'bishop', 'rook', 'rook', 'queen'],
      skins: {},
      slots: {},
      created: Date.now(),
      boostUsed: false,
      stats: { spins: 0, upgradeWins: 0, upgradeLosses: 0, cases: 0, placements: 0 },
      hist: []
    };
  }

  var current = read(KEY_SESSION);
  if (current && !users[current]) current = null;
  var state = current ? users[current] : null;
  if (state && state.banned) { current = null; state = null; }

  function persist() { write(KEY_USERS, users); }
  function save() { persist(); }

  function findKey(name) {
    var k = Object.keys(users).filter(function (x) {
      return x.toLowerCase() === String(name).toLowerCase();
    });
    return k.length ? k[0] : null;
  }

  function emailKey(email) {
    var k = Object.keys(users).filter(function (x) {
      return (users[x].email || '').toLowerCase() === String(email).toLowerCase();
    });
    return k.length ? k[0] : null;
  }

  function fmt(n) { return n.toLocaleString('ru-RU'); }

  function refresh() {
    document.querySelectorAll('[data-balance]').forEach(function (el) {
      el.textContent = fmt(state ? state.balance : 0);
    });
  }

  function renderNav() {
    var box = document.getElementById('nav-right');
    if (!box) return;
    if (state) {
      var initial = state.name.charAt(0).toUpperCase();
      box.innerHTML =
        '<a class="btn btn-ghost btn-sm" href="profile.html">' + state.name + '</a>' +
        '<a class="btn btn-gold btn-sm" href="deposit.html" title="Пополнить">+ ◈</a>' +
        '<div class="balance"><span class="coin">◈</span><b data-balance>0</b></div>' +
        '<button class="user-chip" id="btn-logout" title="Выйти"><span class="av">' + initial + '</span><span class="nm">' + state.name + '</span>' +
        (state.role === 'admin' ? '<span class="role-badge admin">ADMIN</span>' : '') +
        '<span class="x">✕</span></button>';
      box.querySelector('#btn-logout').addEventListener('click', function () {
        if (confirm('Выйти из аккаунта?')) CD.logout();
      });
    } else {
      box.innerHTML =
        '<a class="btn btn-ghost btn-sm" href="auth.html?tab=login">Войти</a>' +
        '<a class="btn btn-violet btn-sm" href="auth.html?tab=register">Регистрация</a>';
    }
    refresh();
  }

  window.CD = {
    PIECES: PIECES,
    SKINS: SKINS,
    RCOL: RCOL,
    get state() { return state; },
    get user() { return current; },
    fmt: fmt,
    save: save,
    refresh: refresh,
    config: function () { return config; },
    saveConfig: function (patch) {
      config = Object.assign({}, config, patch);
      write(KEY_CONFIG, config);
    },
    addBalance: function (v) {
      if (!state) return false;
      state.balance += v; save(); refresh();
      return true;
    },
    spend: function (v) {
      if (!state || state.balance < v) return false;
      state.balance -= v; save(); refresh();
      return true;
    },
    addPiece: function (code) { if (!state) return; state.pieces.push(code); save(); },
    takeFirst: function (code) {
      if (!state) return false;
      var i = state.pieces.indexOf(code);
      if (i === -1) return false;
      state.pieces.splice(i, 1); save();
      return true;
    },
    count: function (code) {
      if (!state) return 0;
      return state.pieces.filter(function (c) { return c === code; }).length;
    },
    uniqueCodes: function () {
      if (!state) return [];
      var seen = {}, out = [];
      state.pieces.forEach(function (c) { if (!seen[c]) { seen[c] = 1; out.push(c); } });
      return out;
    },
    totalValue: function () {
      if (!state) return 0;
      return state.pieces.reduce(function (s, c) {
        return s + ((PIECES[c] || {}).val || 0);
      }, 0);
    },
    addSkin: function (code) {
      if (!state || !SKINS[code]) return;
      state.skins[code] = (state.skins[code] || 0) + 1;
      save();
    },
    takeSkin: function (code) {
      if (!state || !state.skins[code]) return false;
      state.skins[code]--;
      if (state.skins[code] <= 0) {
        delete state.skins[code];
        Object.keys(state.slots).forEach(function (p) {
          if (state.slots[p] === code) state.slots[p] = null;
        });
      }
      save();
      return true;
    },
    skinCount: function (code) {
      if (!state) return 0;
      return state.skins[code] || 0;
    },
    ownedSkins: function () {
      if (!state) return [];
      return Object.keys(state.skins).filter(function (c) { return state.skins[c] > 0; });
    },
    equip: function (pieceType, code) {
      if (!state) return false;
      if (code) {
        var sk = SKINS[code];
        if (!sk || sk.piece !== pieceType) return false;
        if (CD.skinCount(code) < 1) return false;
        Object.keys(state.slots).forEach(function (p) {
          if (state.slots[p] === code) state.slots[p] = null;
        });
        state.slots[pieceType] = code;
      } else {
        state.slots[pieceType] = null;
      }
      save();
      return true;
    },
    skinOf: function (pieceType) {
      if (!state) return null;
      var code = state.slots[pieceType];
      return code && SKINS[code] ? SKINS[code] : null;
    },
    skinColorFor: function (pieceType) {
      var sk = CD.skinOf(pieceType);
      return sk ? RCOL[sk.rarity] : null;
    },
    addStat: function (k, delta) {
      if (!state) return;
      state.stats[k] = (state.stats[k] || 0) + (delta == null ? 1 : delta);
      save();
    },
    pushHist: function (entry) {
      if (!state) return;
      state.hist = state.hist || [];
      entry.t = entry.t || '';
      entry.time = Date.now();
      state.hist.unshift(entry);
      state.hist = state.hist.slice(0, 60);
      save();
    },
    hist: function () { return state ? (state.hist || []) : []; },

    register: function (name, email, pass) {
      if (findKey(name)) return 'Этот логин уже занят';
      if (emailKey(email)) return 'Этот email уже привязан к аккаунту';
      var first = Object.keys(users).length === 0;
      users[name] = defaultUser(name, email, pass);
      if (first) users[name].role = 'admin';
      persist();
      current = name;
      state = users[name];
      write(KEY_SESSION, current);
      renderNav();
      return null;
    },
    login: function (name, pass) {
      var k = findKey(name);
      if (!k) return 'Аккаунт с таким логином не найден';
      var u = users[k];
      if (u.pass !== pass) return 'Неверный пароль';
      if (u.banned) return 'Аккаунт заблокирован администрацией';
      current = k; state = u;
      write(KEY_SESSION, current);
      renderNav();
      return null;
    },
    logout: function () {
      current = null; state = null;
      write(KEY_SESSION, null);
      location.href = 'auth.html';
    },
    changePass: function (oldPass, newPass) {
      if (!state) return 'Нужно войти';
      if (state.pass !== oldPass) return 'Текущий пароль неверен';
      state.pass = newPass; save();
      return null;
    },
    usersAll: function () { return users; },
    userList: function () {
      return Object.keys(users).map(function (k) {
        return Object.assign({ key: k }, users[k]);
      });
    },
    patchUser: function (name, patch) {
      if (!users[name]) return false;
      Object.assign(users[name], patch);
      if (current === name) state = users[name];
      persist();
      return true;
    },
    patchUserBalance: function (name, delta) {
      if (!users[name]) return false;
      users[name].balance = Math.max(0, users[name].balance + delta);
      if (current === name) state = users[name];
      persist();
      return true;
    },
    removeUser: function (name) {
      if (!users[name] || current === name) return false;
      delete users[name];
      persist();
      return true;
    },
    isAdmin: function () { return !!state && state.role === 'admin'; },

    toast: function (msg, type) {
      var box = document.getElementById('toasts');
      if (!box) return;
      var t = document.createElement('div');
      t.className = 'toast ' + (type || 'info');
      t.textContent = msg;
      box.appendChild(t);
      setTimeout(function () {
        t.style.opacity = '0';
        t.style.transform = 'translateX(16px)';
      }, 2900);
      setTimeout(function () { t.remove(); }, 3300);
    }
  };

  function guard() {
    var mode = document.body.getAttribute('data-auth') || 'optional';
    var u = current ? users[current] : null;

    if (mode === 'required' && !u) {
      location.replace('auth.html?next=' + encodeURIComponent(location.pathname.split('/').pop()));
      return;
    }
    if (mode === 'admin') {
      if (!u) {
        location.replace('auth.html?next=admin.html&err=' + encodeURIComponent('Войди, чтобы попасть в админку'));
        return;
      }
      if (u.role !== 'admin') {
        location.replace('profile.html?err=' + encodeURIComponent('Доступ только для админов'));
        return;
      }
    }
    if (u && u.banned && mode !== 'optional') {
      location.replace('auth.html?err=' + encodeURIComponent('Аккаунт заблокирован'));
      return;
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    guard();
    renderNav();
  });
})();
