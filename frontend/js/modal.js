let overlay = null;
let modal = null;
let active = null;

function ensure() {
  if (overlay !== null) return;
  overlay = document.createElement('div');
  overlay.className = 'overlay';
  modal = document.createElement('div');
  modal.className = 'modal';
  overlay.appendChild(modal);
  overlay.addEventListener('click', (e) => {
    if (active && active.dismissible && (e.target === overlay || e.target.closest('[data-modal-cancel]'))) {
      close();
    }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && active && active.dismissible) close();
  });
  document.body.appendChild(overlay);
}

export function openModal({ title, titleAnim = 'pop', body, actions, dismissible = true }) {
  ensure();
  if (active !== null) active = null;
  active = { dismissible };

  while (modal.firstChild) modal.firstChild.remove();
  modal.className = 'modal' + (titleAnim === 'shake' ? ' shake' : '');

  const titleEl = document.createElement('h2');
  titleEl.className = 'm-title' + (titleAnim === 'shake' ? ' anim-shake' : titleAnim === 'pop' ? ' anim-pop' : '');
  titleEl.textContent = title ?? '';
  modal.appendChild(titleEl);

  if (body) modal.appendChild(body);

  if (actions && actions.length) {
    const row = document.createElement('div');
    row.className = 'm-btnrow';
    for (const action of actions) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-' + (action.kind || 'ghost');
      btn.textContent = action.label;
      btn.addEventListener('click', () => {
        const proceed = action.onClick ? action.onClick() : undefined;
        if (proceed !== false) close();
      });
      row.appendChild(btn);
    }
    modal.appendChild(row);
  }

  if (dismissible) {
    const xBtn = document.createElement('button');
    xBtn.type = 'button';
    xBtn.className = 'm-x';
    xBtn.textContent = '✕';
    xBtn.setAttribute('data-modal-cancel', '');
    xBtn.title = 'Закрыть';
    modal.appendChild(xBtn);
  }

  overlay.classList.add('open');
  const first = modal.querySelector('button');
  if (first) first.focus();
  return close;
}

export function close() {
  if (overlay === null) return;
  overlay.classList.remove('open');
  active = null;
}

export function confirmModal(title, text, okLabel, kind = 'gold') {
  const body = document.createElement('p');
  body.className = 'm-text';
  body.textContent = text;
  return new Promise((resolve) => {
    openModal({
      title,
      titleAnim: 'none',
      body,
      dismissible: true,
      actions: [
        { label: 'Отмена', kind: 'ghost', onClick: () => resolve(false) },
        { label: okLabel, kind, onClick: () => resolve(true) },
      ],
    });
  });
}
