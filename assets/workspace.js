'use strict';
(() => {
  const workspace = document.getElementById('workspace');
  const sidebar = document.getElementById('workspace-sidebar');
  const toggle = document.getElementById('sidebar-toggle');
  const backdrop = document.getElementById('sidebar-backdrop');
  const mobile = matchMedia('(max-width:720px)');
  let saved = false;
  try { saved = localStorage.getItem('archet.sidebar.hidden') === 'true'; } catch (_) {}
  function collapse(hidden, persist = false) {
    workspace.classList.toggle('sidebar-collapsed', hidden);
    sidebar.inert = hidden;
    toggle.setAttribute('aria-expanded', String(!hidden));
    toggle.setAttribute('aria-label', hidden ? 'Show sidebar' : 'Hide sidebar');
    backdrop.hidden = hidden || !mobile.matches;
    if (persist && !mobile.matches) {
      saved = hidden;
      try { localStorage.setItem('archet.sidebar.hidden', String(hidden)); } catch (_) {}
    }
  }
  toggle.onclick = () => {
    const hidden = !workspace.classList.contains('sidebar-collapsed');
    collapse(hidden, true);
    if (!hidden && mobile.matches) document.getElementById('sidebar-close').focus();
  };
  const closeSidebar = () => { collapse(true, true); toggle.focus(); };
  document.getElementById('sidebar-close').onclick = closeSidebar;
  backdrop.onclick = closeSidebar;
  sidebar.addEventListener('click', event => {
    if (mobile.matches && event.target.closest('[data-page],#logout')) collapse(true);
  });
  sidebar.addEventListener('keydown', event => {
    if (!mobile.matches) return;
    if (event.key === 'Escape') { event.preventDefault(); closeSidebar(); }
    if (event.key === 'Tab') {
      const buttons = [...sidebar.querySelectorAll('button')].filter(button => button.getClientRects().length);
      if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons.at(-1).focus(); }
      else if (!event.shiftKey && document.activeElement === buttons.at(-1)) { event.preventDefault(); buttons[0].focus(); }
    }
  });
  mobile.addEventListener('change', () => collapse(mobile.matches || saved));
  collapse(mobile.matches || saved);

  let opened = null;
  function closePicker(restore = false) {
    if (!opened) return;
    const previous = opened;
    opened = null;
    previous.menu.hidden = true;
    previous.trigger.setAttribute('aria-expanded', 'false');
    if (restore) previous.trigger.focus();
  }
  function positionPicker() {
    if (!opened) return;
    const rect = opened.trigger.getBoundingClientRect();
    const width = Math.min(Math.max(rect.width, 175), innerWidth - 16);
    const below = innerHeight - rect.bottom - 12, above = rect.top - 12;
    const upwards = below < 190 && above > below;
    opened.menu.style.width = width + 'px';
    opened.menu.style.left = Math.max(8, Math.min(rect.left, innerWidth - width - 8)) + 'px';
    opened.menu.style.maxHeight = Math.max(100, Math.min(300, upwards ? above : below)) + 'px';
    opened.menu.style.top = upwards ? 'auto' : rect.bottom + 6 + 'px';
    opened.menu.style.bottom = upwards ? innerHeight - rect.top + 6 + 'px' : 'auto';
  }
  for (const id of ['sales-dealer','sales-market','sales-store','sales-period','tree-dealer','quota-month','quota-dealer','quota-market','quota-store']) {
    const select = document.getElementById(id);
    const label = select.parentElement.firstChild.textContent.trim();
    const trigger = document.createElement('button');
    trigger.type = 'button'; trigger.className = 'picker-trigger'; trigger.id = id + '-trigger';
    trigger.setAttribute('aria-haspopup', 'dialog'); trigger.setAttribute('aria-expanded', 'false');
    const value = document.createElement('span'); value.className = 'picker-value'; trigger.append(value);
    select.classList.add('picker-native'); select.tabIndex = -1; select.setAttribute('aria-hidden', 'true');
    select.after(trigger);
    const menu = document.createElement('div'); menu.className = 'picker-menu'; menu.hidden = true;
    menu.id = id + '-menu'; menu.setAttribute('role', 'dialog'); menu.setAttribute('aria-label', label + ' options');
    trigger.setAttribute('aria-controls', menu.id);
    const searchWrap = document.createElement('div'); searchWrap.className = 'picker-search-wrap';
    const icon = document.createElement('span'); icon.className = 'picker-search-icon'; icon.textContent = '⌕'; icon.setAttribute('aria-hidden','true');
    const search = document.createElement('input'); search.className = 'picker-search'; search.type = 'search';
    search.placeholder = 'Search ' + label.toLowerCase(); search.setAttribute('aria-label', 'Search ' + label.toLowerCase());
    search.setAttribute('role','combobox'); search.setAttribute('aria-expanded','true'); search.setAttribute('aria-autocomplete','list');
    const list = document.createElement('div'); list.className = 'picker-list'; list.id = id + '-options'; list.setAttribute('role','listbox'); list.setAttribute('aria-label',label);
    search.setAttribute('aria-controls',list.id);
    searchWrap.append(icon, search); menu.append(searchWrap, list); document.body.append(menu);
    const picker = {trigger, menu};
    let options = [], active = 0;
    function highlight() {
      [...list.children].forEach((item,index) => item.classList.toggle('is-active', index === active && options.length > 0));
      if (options.length) search.setAttribute('aria-activedescendant', list.children[active].id);
      else search.removeAttribute('aria-activedescendant');
    }
    function choose(index) {
      if (!options[index]) return;
      select.value = options[index].value;
      closePicker(true);
      select.dispatchEvent(new Event('change', {bubbles:true}));
      sync();
    }
    function draw() {
      const query = search.value.trim().toLowerCase();
      options = [...select.options].filter(option => !option.disabled && option.text.toLowerCase().includes(query));
      active = Math.max(0, options.findIndex(option => option.value === select.value));
      list.replaceChildren();
      options.forEach((option,index) => {
        const item = document.createElement('div'); item.className = 'picker-option'; item.id = id + '-option-' + index;
        item.setAttribute('role','option'); item.setAttribute('aria-selected',String(option.value === select.value)); item.textContent = option.text;
        item.onmousedown = event => event.preventDefault(); item.onclick = () => choose(index); list.append(item);
      });
      if (!options.length) { const empty = document.createElement('div'); empty.className = 'picker-empty'; empty.textContent = 'No matches'; empty.setAttribute('role','status'); list.append(empty); }
      highlight();
    }
    function sync() {
      value.textContent = select.selectedOptions[0]?.text || label;
      trigger.setAttribute('aria-label', label + ': ' + value.textContent);
      trigger.disabled = select.disabled;
      if (opened === picker) draw();
    }
    function open() {
      closePicker(); opened = picker; menu.hidden = false; trigger.setAttribute('aria-expanded','true');
      search.value = ''; draw(); positionPicker(); search.focus();
    }
    trigger.onclick = () => opened === picker ? closePicker() : open();
    trigger.onkeydown = event => { if (['ArrowDown','ArrowUp'].includes(event.key)) { event.preventDefault(); open(); } };
    search.oninput = draw;
    search.onkeydown = event => {
      if (event.key === 'Escape') { event.preventDefault(); closePicker(true); }
      else if (event.key === 'Tab') { closePicker(true); }
      else if (event.key === 'Enter') { event.preventDefault(); choose(active); }
      else if (['ArrowDown','ArrowUp','Home','End'].includes(event.key) && options.length) {
        event.preventDefault();
        active = event.key === 'Home' ? 0 : event.key === 'End' ? options.length - 1 : (active + (event.key === 'ArrowDown' ? 1 : -1) + options.length) % options.length;
        highlight(); list.children[active].scrollIntoView({block:'nearest'});
      }
    };
    select.addEventListener('change', sync);
    select.addEventListener('picker-sync', sync);
    new MutationObserver(sync).observe(select, {childList:true,subtree:true,attributes:true});
    sync();
  }
  document.addEventListener('pointerdown', event => { if (opened && !opened.menu.contains(event.target) && !opened.trigger.contains(event.target)) closePicker(); });
  document.addEventListener('click', event => { if (event.target.closest('[data-page],#logout')) closePicker(); });
  window.addEventListener('resize', positionPicker);
  window.addEventListener('scroll', event => { if (opened && !opened.menu.contains(event.target)) positionPicker(); }, true);
  new MutationObserver(() => { if (workspace.hidden) { closePicker(); if (mobile.matches) collapse(true); } }).observe(workspace, {attributes:true,attributeFilter:['hidden']});
})();
