'use strict';
(() => {
  let shownVersion = null, checking = false;
  const reload = performance.getEntriesByType('navigation')[0]?.type === 'reload';
  function show(user, freshLogin = false) {
    const version = user.id + ':' + user.rest_version;
    if (shownVersion === version && !$('account-rest').hidden) return;
    let seen = false;
    try { seen = sessionStorage.getItem('archet.rest.seen') === version; sessionStorage.setItem('archet.rest.seen', version); } catch (_) {}
    shownVersion = version;
    window.salesDashboard?.clear(); window.callingTree?.clear(); window.quotaDashboard?.clear();
    document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
    quotes = []; users = []; editingUser = editingQuote = null; offset = 0;
    ['recent-quotes','quote-list','user-list','quote-details','quote-message'].forEach(id => $(id).replaceChildren());
    ['password-form','user-form','quote-form'].forEach(id => $(id).reset());
    currentUser = user; page = 'rest';
    $('workspace').hidden = true; $('workspace').inert = true; $('boot').hidden = true; $('login').hidden = true;
    $('login-password').value = '';
    const reloaded = reload && seen && !freshLogin;
    $('rest-emoji').textContent = reloaded ? '🍆' : '🖕🏻';
    $('rest-message').textContent = reloaded ? 'Chal Bey Dalley' : "Now it's time to have Tui wich Lund " + user.username;
    $('account-rest').hidden = false;
  }
  function hide() {
    shownVersion = null; $('account-rest').hidden = true; $('workspace').inert = false;
    $('rest-emoji').textContent = ''; $('rest-message').textContent = '';
  }
  async function check() {
    if (!currentUser || checking || document.hidden) return;
    checking = true;
    try {
      const previous = currentUser.id;
      const result = await api('me');
      if (!currentUser || currentUser.id !== previous) return;
      if (result.user.rest_mode) show(result.user);
      else if (currentUser.rest_mode) enterWorkspace(result.user);
    } catch (_) { /* API handles revoked sessions. Retry temporary connection failures. */ }
    finally { checking = false; }
  }
  $('rest-logout').onclick = async () => {
    $('rest-logout').disabled = true;
    try { await api('logout','POST',{}); signedOut(); }
    catch (_) { $('rest-message').textContent = 'Unable to sign out. Please try again.'; }
    finally { $('rest-logout').disabled = false; }
  };
  document.addEventListener('click', async event => {
    const button = event.target.closest('[data-rest-user]');
    if (!button || !currentUser?.is_owner || currentUser.username !== 'Mahee' || currentUser.rest_mode) return;
    const target = users.find(user => user.id === button.dataset.restUser);
    if (!target) return;
    button.disabled = true;
    try {
      await api('users/' + target.id + '/rest','PATCH',{rest_mode:!target.rest_mode});
      await loadUsers(); notice(target.username + (target.rest_mode ? ' is back to work.' : ' is now on rest.'));
    } catch (error) { notice(error.message,true); }
    finally { button.disabled = false; }
  });
  setInterval(check,5000);
  document.addEventListener('visibilitychange',check);
  window.addEventListener('focus',check);
  window.accountRest = {show,hide};
})();
