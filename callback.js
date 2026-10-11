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
    status.textContent = 'Autorisation reçue. Copiez cette URL dans la commande finish sur votre VPS. Ne la partagez pas dans un chat.';
  } else {
    output.hidden = true;
    status.textContent = 'Aucune autorisation utilisable reçue. Relancez la connexion depuis votre VPS.';
  }
  document.getElementById('clear').addEventListener('click', () => {
    output.value = ''; output.hidden = true;
    status.textContent = 'Informations effacées de la page. Vous pouvez fermer cet onglet.';
  });
});
