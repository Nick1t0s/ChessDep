const ATTR_KEYS = new Set([
  'class',
  'id',
  'type',
  'disabled',
  'title',
  'href',
  'value',
  'name',
  'role',
  'tabindex',
  'for',
  'required',
  'readonly',
  'maxlength',
  'minlength',
  'autocomplete',
  'placeholder',
  'hidden',
  'min',
  'max',
  'step',
  'rows',
  'checked',
]);

export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') {
      const cls = (Array.isArray(value) ? value : [value]).filter(Boolean).join(' ');
      if (cls) el.className = cls;
    } else if (key === 'href') {
      setHref(el, value);
    } else if (key === 'disabled') {
      if (value) el.disabled = true;
    } else if (key === 'value') {
      if (el.tagName === 'INPUT' || el.tagName === 'SELECT' || el.tagName === 'TEXTAREA') {
        el.value = value;
      } else {
        el.setAttribute(key, String(value));
      }
    } else if (key.startsWith('on') && /^on[A-Za-z]+$/.test(key)) {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (ATTR_KEYS.has(key) || key.startsWith('aria-') || key.startsWith('data-')) {
      el.setAttribute(key, String(value));
    } else {
      throw new Error('h(): неизвестный атрибут ' + key);
    }
  }
  appendChildren(el, children);
  return el;
}

function setHref(el, value) {
  if (typeof value !== 'string') throw new Error('h(): href должен быть строкой');
  const ok = (value.startsWith('/') && !value.startsWith('//')) || value.startsWith('#');
  if (!ok) throw new Error('h(): href разрешён только относительный');
  el.setAttribute('href', value);
}

function appendChildren(el, children) {
  for (const child of children) appendChild(el, child);
}

function appendChild(el, child) {
  if (child === null || child === undefined || child === false) return;
  if (typeof child === 'string' || typeof child === 'number') {
    el.appendChild(document.createTextNode(String(child)));
  } else if (child instanceof Node) {
    el.appendChild(child);
  } else if (Array.isArray(child)) {
    appendChildren(el, child);
  } else {
    throw new Error('h(): неизвестный тип ребёнка');
  }
}

export function clear(el) {
  while (el.firstChild) el.firstChild.remove();
}

export function $(selector, root = document) {
  return root.querySelector(selector);
}
