'use strict';
// Run in the head so the saved appearance is applied before the first paint.
(() => {
  const root = document.documentElement, key = 'archet.appearance';
  const palettes = {
    Connect:['#095570','#083c51','#f3f8fa'],
    California:['#a92d49','#491c2c','#faf0f2'],
    SRH:['#a06118','#503718','#fbf5ea'],
    ARM:['#176b56','#104735','#edf8f3'],
    ARBF:['#7646a5','#3d2652','#f5effa']
  };
  function apply(mode) {
    root.dataset.theme = mode === 'dark' ? 'dark' : 'light';
    document.querySelectorAll('[data-theme-toggle]').forEach(button => {
      const dark = root.dataset.theme === 'dark';
      button.textContent = dark ? 'Light mode' : 'Dark mode';
      button.setAttribute('aria-label', dark ? 'Switch to light mode' : 'Switch to dark mode');
      button.setAttribute('aria-pressed', String(dark));
    });
  }
  let initial = 'light';
  try { initial = localStorage.getItem(key) || initial; } catch (_) {}
  apply(initial);
  function dealer(name) {
    root.dataset.dealer = name || '';
    const values = palettes[name] || palettes.Connect;
    ['accent','dark','tint'].forEach((part, index) => root.style.setProperty('--dealer-' + part, values[index]));
  }
  window.archetAppearance = {dealer};
  window.addEventListener('storage', event => { if (event.key === key) apply(event.newValue); });
  document.addEventListener('DOMContentLoaded', () => {
    for (const selector of ['.topbar', '#login .login-card', '.sheet-format-bar', '#sheet-login-form', '.wf-rail-end']) {
      const host = document.querySelector(selector);
      if (!host) continue;
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'theme-toggle'; button.dataset.themeToggle = '';
      button.onclick = () => {
        const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
        apply(next);
        try { localStorage.setItem(key, next); } catch (_) {}
      };
      host.append(button);
    }
    apply(root.dataset.theme);
    const sheetDealer = document.getElementById('sheet-dealer');
    if (sheetDealer) {
      const sync = () => dealer(sheetDealer.value);
      sheetDealer.addEventListener('change', sync);
      new MutationObserver(sync).observe(sheetDealer, {childList:true});
      sync();
    }
  });
})();
