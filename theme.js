(() => {
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let preference;
  try {
    const saved = window.localStorage.getItem('finance-theme');
    if (saved === 'light' || saved === 'dark') preference = saved;
  } catch { /* Storage can be disabled; the switch still works for this page. */ }

  const root = document.documentElement;
  root.dataset.theme = preference || (system.matches ? 'dark' : 'light');

  document.addEventListener('DOMContentLoaded', () => {
    const button = document.getElementById('theme-toggle');
    if (!button) return;
    const update = () => {
      const dark = root.dataset.theme === 'dark';
      const label = dark ? 'Switch to light theme' : 'Switch to dark theme';
      button.setAttribute('aria-pressed', String(dark));
      button.setAttribute('aria-label', label);
      button.setAttribute('title', label);
    };
    update();
    button.addEventListener('click', () => {
      preference = root.dataset.theme === 'dark' ? 'light' : 'dark';
      root.dataset.theme = preference;
      try { window.localStorage.setItem('finance-theme', preference); } catch { /* Optional persistence. */ }
      update();
    });
    system.addEventListener('change', () => {
      if (!preference) {
        root.dataset.theme = system.matches ? 'dark' : 'light';
        update();
      }
    });
  });
})();
