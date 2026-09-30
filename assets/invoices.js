'use strict';
(() => {
  const money = cents => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD'}).format(cents / 100);
  const label = month => new Date(month + '-01T12:00:00').toLocaleDateString('en-US', {month:'long', year:'numeric'});
  const allowed = () => currentUser?.is_owner === true && currentUser.username.toLowerCase() === 'mahee' && !currentUser.rest_mode;
  const printSheet = document.createElement('article'); printSheet.id = 'invoice-print'; document.body.append(printSheet);
  let loadedMonth = '', revision = null, dirty = false, busy = false, generation = 0, suggestions = [], suggested = false;
  const localMonth = () => new Intl.DateTimeFormat('en-CA', {timeZone:'America/Chicago',year:'numeric',month:'2-digit'}).formatToParts(new Date()).filter(p => p.type !== 'literal').reduce((o,p) => ({...o,[p.type]:p.value}), {});
  function defaultMonth() { const d = localMonth(); return d.year + '-' + d.month; }
  function nextMonth(month) { const [y,m] = month.split('-').map(Number); return `${y + (m === 12 ? 1 : 0)}-${String(m % 12 + 1).padStart(2,'0')}`; }
  function message(value = '', error = false) { $('invoice-message').textContent = value; $('invoice-message').hidden = !value; $('invoice-message').classList.toggle('is-error',error); }
  function lock(value) {
    busy = value; $('invoice-fields').disabled = value || !loadedMonth;
    ['invoice-save','invoice-print-button','invoice-reload','invoice-month'].forEach(id => $(id).disabled = value);
    $('invoice-save').disabled = value || !loadedMonth;
    $('invoice-print-button').disabled = value || !loadedMonth;
  }
  function cents(value) {
    if (!/^\d{1,9}(\.\d{1,2})?$/.test(value)) return null;
    const [whole, fraction = ''] = value.split('.'); return Number(whole) * 100 + Number(fraction.padEnd(2,'0'));
  }
  function rowValues(tr) {
    const get = field => tr.querySelector(`[data-field="${field}"]`).value;
    return {dealer:get('dealer').trim(),market:get('market').trim(),amount_cents:cents(get('amount')),advance_cents:cents(get('advance')),remark:get('remark').trim()};
  }
  function rows() { return [...$('invoice-rows').children].map(rowValues); }
  function refresh() {
    let total = 0, advance = 0, invalid = false;
    [...$('invoice-rows').children].forEach(tr => {
      const r = rowValues(tr), valid = r.amount_cents !== null && r.advance_cents !== null;
      invalid ||= !valid; total += r.amount_cents ?? 0; advance += r.advance_cents ?? 0;
      tr.querySelector('output').textContent = valid ? money(r.amount_cents-r.advance_cents) : '—';
      tr.querySelector('output').classList.toggle('is-credit', valid && r.advance_cents > r.amount_cents);
    });
    const count = $('invoice-rows').children.length;
    $('invoice-total').textContent = invalid ? '—' : money(total); $('invoice-advance').textContent = invalid ? '—' : money(advance);
    $('invoice-balance').textContent = invalid ? '—' : money(total - advance);
    $('invoice-market-count').textContent = `${count} ${count === 1 ? 'market' : 'markets'}`;
    $('invoice-empty').hidden = count > 0; $('invoice-add').disabled = count >= 100;
    if (loadedMonth) {
      $('invoice-period').textContent = label(loadedMonth) + ' · Amounts and payments by market';
      $('invoice-due').textContent = 'For ' + label(nextMonth(loadedMonth)) + (total < advance ? ' · Credit balance' : '');
    }
    if (dirty) $('invoice-state').textContent = 'Unsaved changes';
  }
  function markDirty() { dirty = true; message(); refresh(); }
  function addRow(row = {dealer:'',market:'',amount_cents:0,advance_cents:0,remark:''}, focus = false) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td data-label="Dealer / Market"><input data-field="dealer" aria-label="Dealer" list="invoice-dealers" placeholder="Dealer" maxlength="100" required><input data-field="market" aria-label="Market" list="invoice-markets" placeholder="Market name" maxlength="100" required></td>
      <td data-label="Amount"><div class="inv-money-input"><span>$</span><input data-field="amount" aria-label="Amount in USD" inputmode="decimal" pattern="[0-9]{1,9}([.][0-9]{1,2})?" title="Enter an amount with up to two decimal places" required></div></td>
      <td data-label="Advance paid"><div class="inv-money-input"><span>$</span><input data-field="advance" aria-label="Advance paid in USD" inputmode="decimal" pattern="[0-9]{1,9}([.][0-9]{1,2})?" title="Enter an amount with up to two decimal places" required></div></td>
      <td data-label="Next month balance"><output aria-label="Next month balance"></output></td>
      <td data-label="Remark"><textarea data-field="remark" aria-label="Remark" placeholder="Add a note…" maxlength="500" rows="2"></textarea></td>
      <td class="inv-remove-cell"><button type="button" class="inv-remove" aria-label="Remove market">×</button></td>`;
    for (const [key,value] of Object.entries({dealer:row.dealer,market:row.market,amount:(row.amount_cents/100).toFixed(2),advance:(row.advance_cents/100).toFixed(2),remark:row.remark})) tr.querySelector(`[data-field="${key}"]`).value = value;
    tr.querySelector('.inv-remove').onclick = () => { tr.remove(); markDirty(); $('invoice-add').focus(); };
    tr.querySelector('[data-field="dealer"]').addEventListener('input', () => marketOptions(tr));
    tr.querySelector('[data-field="market"]').addEventListener('focus', () => marketOptions(tr));
    $('invoice-rows').append(tr); if (focus) tr.querySelector('input').focus();
  }
  function marketOptions(tr) {
    const dealer = tr.querySelector('[data-field="dealer"]').value.trim().toLowerCase();
    options('invoice-markets',suggestions.filter(r => !dealer || r.dealer.toLowerCase() === dealer).map(r => r.market));
  }
  function options(id, values) { $(id).replaceChildren(...[...new Set(values)].sort().map(value => { const option = document.createElement('option'); option.value = value; return option; })); }
  async function loadSuggestions(token) {
    if (suggested) return;
    try {
      const result = await api('calling-tree');
      if (token !== generation || !allowed()) return;
      suggestions = result.rows; suggested = true; options('invoice-dealers',suggestions.map(r => r.dealer));
    } catch (_) { /* Manual dealer and market entry remains available. */ }
  }
  async function load(force = false) {
    if (!allowed() || busy) return;
    if (!force && loadedMonth) return;
    const month = $('invoice-month').value || defaultMonth();
    if (!/^20\d{2}-(0[1-9]|1[0-2])$/.test(month)) { $('invoice-month').value = loadedMonth || defaultMonth(); return; }
    const token = ++generation; lock(true); message(); $('invoice-state').textContent = 'Loading invoice…';
    try {
      const result = await api('invoices/' + month);
      if (token !== generation || !allowed()) return;
      loadedMonth = month; revision = result.invoice.revision; dirty = false; $('invoice-month').value = month;
      $('invoice-rows').replaceChildren(); result.invoice.rows.forEach(r => addRow(r));
      $('invoice-state').textContent = revision ? 'All changes saved' : 'New monthly invoice';
      $('invoice-updated').textContent = result.invoice.updated_at ? 'Saved ' + new Date(result.invoice.updated_at).toLocaleString() : 'Ready for your first market';
      refresh(); void loadSuggestions(token);
    } catch (error) {
      if (token !== generation || !allowed()) return;
      $('invoice-month').value = loadedMonth || month;
      $('invoice-state').textContent = dirty ? 'Unsaved changes' : 'Could not load invoice'; message(error.message,true);
    } finally { if (token === generation) lock(false); }
  }
  async function save() {
    if (!allowed() || busy || !loadedMonth || !$('invoice-form').reportValidity()) return false;
    const data = rows();
    const keys = data.map(r => JSON.stringify([r.dealer.toLowerCase(),r.market.toLowerCase()]));
    if (new Set(keys).size !== keys.length) { message('Each dealer and market can appear only once per month.',true); return false; }
    if (data.some(r => !r.dealer || !r.market)) { message('Enter a dealer and market for every row.',true); return false; }
    const token = generation; lock(true); message(); $('invoice-state').textContent = 'Saving…';
    try {
      const result = await api('invoices/' + loadedMonth, 'PUT', {revision,rows:data});
      if (token !== generation || !allowed()) return false;
      revision = result.invoice.revision; dirty = false; $('invoice-state').textContent = 'All changes saved';
      $('invoice-updated').textContent = 'Saved ' + new Date(result.invoice.updated_at).toLocaleString(); return true;
    } catch (error) {
      if (token === generation && allowed()) { message(error.message,true); $('invoice-state').textContent = 'Changes not saved'; }
      return false;
    } finally { if (token === generation) lock(false); }
  }
  function preparePrint() {
    printSheet.replaceChildren(); document.body.classList.remove('invoices-print-ready');
    if (!allowed() || page !== 'invoices' || !loadedMonth) return;
    const data = rows(), valid = data.every(r => r.amount_cents !== null && r.advance_cents !== null);
    const sum = field => data.reduce((s,r) => s + (r[field] ?? 0),0);
    const total = sum('amount_cents'), advance = sum('advance_cents');
    printSheet.innerHTML = `<header class="inv-print-head"><div><div class="inv-print-brand">ARCHET<span> / SOLUTIONS</span></div><p>MONTHLY MARKET INVOICE</p></div><div><strong>INVOICE</strong><span>INV-${escapeHTML(loadedMonth.replace('-',''))}</span></div></header>
      <div class="inv-print-period"><div><small>INVOICE PERIOD</small><h1>${escapeHTML(label(loadedMonth))}</h1></div><div><small>BALANCE FOR</small><strong>${escapeHTML(label(nextMonth(loadedMonth)))}</strong><span>Currency: USD</span></div></div>
      ${dirty || !revision || !valid ? '<p class="inv-print-draft">DRAFT · Unsaved invoice</p>' : ''}
      <table><colgroup><col style="width:26%"><col style="width:16%"><col style="width:16%"><col style="width:17%"><col style="width:25%"></colgroup><thead><tr><th>Dealer / Market</th><th>Amount</th><th>Advance paid</th><th>Next month<br>balance</th><th>Remark</th></tr></thead><tbody>${data.map(r => `<tr><td><strong>${escapeHTML(r.market)}</strong><small>${escapeHTML(r.dealer)}</small></td><td>${r.amount_cents === null ? '—' : money(r.amount_cents)}</td><td>${r.advance_cents === null ? '—' : money(r.advance_cents)}</td><td><strong>${r.amount_cents === null || r.advance_cents === null ? '—' : money(r.amount_cents-r.advance_cents)}</strong></td><td class="inv-print-remark">${escapeHTML(r.remark) || '—'}</td></tr>`).join('')}</tbody></table>
      <div class="inv-print-totals"><div><span>Total amount</span><strong>${valid ? money(total) : '—'}</strong></div><div><span>Advance already paid</span><strong>${valid ? money(advance) : '—'}</strong></div><div class="inv-print-balance"><span>Next month balance</span><strong>${valid ? money(total-advance) : '—'}</strong></div><small>For ${escapeHTML(label(nextMonth(loadedMonth)))}${total < advance ? ' · Credit balance' : ''}</small></div>
      <footer>ARCHET SOLUTIONS <span>Balance = amount − advance paid. Negative balances represent credit.</span></footer>`;
    document.body.classList.add('invoices-print-ready');
  }
  function clear() {
    generation++; loadedMonth = ''; revision = null; dirty = false; busy = false; suggestions = []; suggested = false;
    $('invoice-rows').replaceChildren(); $('invoice-month').value = ''; $('invoices-nav').hidden = true;
    $('page-invoices').hidden = true; $('invoice-dealers').replaceChildren(); $('invoice-markets').replaceChildren();
    $('invoice-period').textContent = ''; $('invoice-updated').textContent = ''; $('invoice-due').textContent = '';
    printSheet.replaceChildren(); document.body.classList.remove('invoices-print-ready'); message(); refresh(); lock(false);
  }
  $('invoice-form').addEventListener('input',markDirty);
  $('invoice-form').onsubmit = event => { event.preventDefault(); void save(); };
  $('invoice-add').onclick = () => { if ($('invoice-rows').children.length < 100) { addRow(undefined,true); markDirty(); } };
  $('invoice-save').onclick = () => void save();
  $('invoice-reload').onclick = () => { if (!dirty || confirm('Discard unsaved changes and reload this month?')) void load(true); };
  $('invoice-month').onchange = () => {
    if (dirty && !confirm('Discard unsaved changes and open another month?')) { $('invoice-month').value = loadedMonth; return; }
    void load(true);
  };
  $('invoice-print-button').onclick = async () => {
    if (!$('invoice-rows').children.length) { message('Add a market before printing.',true); return; }
    if (!(await save())) return;
    if (!allowed() || page !== 'invoices') return;
    preparePrint(); window.print();
  };
  window.addEventListener('beforeprint',preparePrint);
  window.addEventListener('afterprint',() => { printSheet.replaceChildren(); document.body.classList.remove('invoices-print-ready'); });
  window.addEventListener('beforeunload',event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  window.invoiceDashboard = {allowed,load,clear};
})();
