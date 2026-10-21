import { api, text } from './api.js';

const loginEl = document.querySelector('#login');
const roleEl = document.querySelector('#role');
const balanceEl = document.querySelector('#balance');
const adminLink = document.querySelector('#admin-link');
const bonusBtn = document.querySelector('#daily-bonus');
const logoutBtn = document.querySelector('#logout');
const errorEl = document.querySelector('#error');

function showError(message) {
  text(errorEl, message);
  errorEl.classList.add('show');
}

const me = await api('GET', '/me');
text(loginEl, me.login);
text(roleEl, me.role === 'admin' ? 'админ' : 'игрок');
text(balanceEl, me.balance);
if (me.role === 'admin') {
  adminLink.hidden = false;
}

bonusBtn.disabled = me.daily_bonus_available_at !== null;
bonusBtn.addEventListener('click', async () => {
  try {
    const out = await api('POST', '/me/daily-bonus');
    text(balanceEl, out.balance);
    bonusBtn.disabled = true;
  } catch (e) {
    showError(e.message);
  }
});

logoutBtn.addEventListener('click', async () => {
  try {
    await api('POST', '/auth/logout');
  } finally {
    location.href = '/login.html';
  }
});
