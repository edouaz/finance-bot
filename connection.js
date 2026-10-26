'use strict';

const SERVER_KEY = 'finance-private-server-origin';

function serverOrigin(value) {
  if (typeof value !== 'string' || value !== value.trim()
      || !/^https:\/\/[^/?#\\\s]+\/?$/i.test(value)) {
    throw new Error('invalid_server_origin');
  }
  const url = new URL(value);
  if (url.protocol !== 'https:' || !url.hostname || url.username || url.password
      || url.pathname !== '/' || url.search || url.hash) {
    throw new Error('invalid_server_origin');
  }
  return url.origin;
}

function setupConnection(document, browser) {
  const input = document.getElementById('server');
  const status = document.getElementById('status');
  const open = document.getElementById('open');
  const forget = document.getElementById('forget');
  let storageUnavailable = false;

  function preview() {
    try {
      const origin = serverOrigin(input.value);
      status.textContent = `Destination: ${origin}/. Check that this server belongs to you.`;
      open.disabled = false;
    } catch {
      status.textContent = input.value
        ? 'Address rejected: use only an HTTPS origin, without credentials, a path, query parameters or a fragment.'
        : 'Enter the address of a server you control.';
      open.disabled = true;
    }
    if (storageUnavailable) status.textContent += ' Browser storage is blocked; you can still open your server.';
  }

  try {
    const saved = browser.localStorage.getItem(SERVER_KEY);
    if (saved !== null) {
      try {
        input.value = serverOrigin(saved);
      } catch {
        browser.localStorage.removeItem(SERVER_KEY);
      }
    }
  } catch {
    storageUnavailable = true;
  }
  preview();
  input.addEventListener('input', preview);
  open.addEventListener('click', () => {
    let origin;
    try {
      origin = serverOrigin(input.value);
    } catch {
      preview();
      return;
    }
    try {
      browser.localStorage.setItem(SERVER_KEY, origin);
    } catch {
      storageUnavailable = true;
      preview();
    }
    browser.location.assign(origin + '/');
  });
  forget.addEventListener('click', () => {
    let removed = true;
    try {
      browser.localStorage.removeItem(SERVER_KEY);
    } catch {
      storageUnavailable = true;
      removed = false;
    }
    input.value = '';
    preview();
    status.textContent = removed
      ? 'Address forgotten in this browser.'
      : 'Address cleared from the page. Browser storage removal is blocked; use your browser settings to clear this site’s data.';
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { serverOrigin, setupConnection, SERVER_KEY };
} else {
  setupConnection(document, window);
}
