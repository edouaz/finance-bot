'use strict';
// Capture once, then remove secrets from the address bar before any user interaction.
const original = window.location.href;
const params = new URLSearchParams(window.location.search);
window.history.replaceState(null, '', window.location.pathname);
window.addEventListener('DOMContentLoaded', () => {
  const output = document.getElementById('callback');
  const status = document.getElementById('status');
  if (params.has('code') && params.has('state')) {
    output.value = original;
    status.textContent = 'Authorization received. Copy this URL into the finish command on your server. Do not share it in a chat.';
  } else {
    output.hidden = true;
    status.textContent = 'No usable authorization received. Restart the connection from your server.';
  }
  document.getElementById('clear').addEventListener('click', () => {
    output.value = ''; output.hidden = true;
    status.textContent = 'Information cleared from the page. You can close this tab.';
  });
});
