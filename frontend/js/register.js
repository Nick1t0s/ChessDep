import { api, safeNext, text } from './api.js';

const form = document.querySelector('#register-form');
const errorEl = document.querySelector('#error');

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  text(errorEl, '');
  const login = document.querySelector('#login').value;
  const email = document.querySelector('#email').value;
  const password = document.querySelector('#password').value;
  try {
    await api('POST', '/auth/register', { login, email, password });
    location.href = safeNext();
  } catch (e) {
    text(errorEl, e.message);
    errorEl.classList.add('show');
  }
});
