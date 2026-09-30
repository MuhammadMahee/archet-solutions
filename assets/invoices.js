'use strict';
(() => {
  const money = cents => new Intl.NumberFormat('en-US', {style:'currency', currency:'USD'}).format(cents / 100);
  const label = month => new Date(month + '-01T12:00:00').toLocaleDateString('en-US', {month:'long', year:'numeric'});
  const allowed = () => currentUser?.is_owner === true && currentUser.username.toLowerCase() === 'mahee' && !currentUser.rest_mode;
  const printSheet = document.createElement('article'); printSheet.id = 'invoice-print'; document.body.append(printSheet);
  // Warm the print logo so native Ctrl+P also has the brand asset ready.
  const printLogo = new Image(); printLogo.src = '/archet-logo.png';
  let loadedMonth = '', revision = null, dirty = false, busy = false, generation = 0, suggestions = [], suggested = false;
  let invoiceId = '', listGeneration = 0, listOffset = 0, listMore = false, searchTimer;
  const localMonth = () => new Intl.DateTimeFormat('en-CA', {timeZone:'America/Chicago',year:'numeric',month:'2-digit'}).formatToParts(new Date()).filter(p => p.type !== 'literal').reduce((o,p) => ({...o,[p.type]:p.value}), {});
  function defaultMonth() { const d = localMonth(); return d.year + '-' + d.month; }
  function monthDays(month = loadedMonth) { const [year,number] = month.split('-').map(Number); return new Date(Date.UTC(year,number,0)).getUTCDate(); }
  function message(value = '', error = false) { $('invoice-message').textContent = value; $('invoice-message').hidden = !value; $('invoice-message').classList.toggle('is-error',error); }
  function lock(value) {
    busy = value; $('invoice-fields').disabled = value || !loadedMonth;
    ['invoice-save','invoice-print-button','invoice-reload','invoice-month','invoice-name','invoice-new'].forEach(id => $(id).disabled = value);
    $('invoice-save').disabled = value || !loadedMonth;
    $('invoice-print-button').disabled = value || !loadedMonth;
  }
  function cents(value, maxDigits = 9) {
    if (!(new RegExp('^\\d{1,' + maxDigits + '}(\\.\\d{1,2})?$')).test(value)) return null;
    const [whole, fraction = ''] = value.split('.'); return Number(whole) * 100 + Number(fraction.padEnd(2,'0'));
  }
  function rowValues(tr) {
    const get = field => tr.querySelector(`[data-field="${field}"]`).value;
    const count = Number(get('store_count'));
    const days = get('days_worked') === '' ? NaN : Number(get('days_worked'));
    return {dealer:get('dealer').trim(),market:get('market').trim(),store_count:Number.isInteger(count) && count >= 1 && count <= 10000 ? count : null,days_worked:Number.isInteger(days) && days >= 0 && days <= monthDays() ? days : null,amount_cents:cents(get('amount')),remark:get('remark').trim()};
  }
  // Integer arithmetic rounds once per market, half up, matching the server.
  const subtotal = row => Math.floor((2 * row.store_count * row.amount_cents * row.days_worked + monthDays()) / (2 * monthDays()));
  const validRow = row => row.store_count !== null && row.days_worked !== null && row.amount_cents !== null && row.store_count * row.amount_cents <= 99999999999;
  const invoiceAdvance = () => cents($('invoice-payment-advance').value,11);
  function rows() { return [...$('invoice-rows').children].map(rowValues); }
  function refresh() {
    let total = 0, advance = invoiceAdvance(), invalid = false;
    [...$('invoice-rows').children].forEach(tr => {
      const r = rowValues(tr), valid = validRow(r);
      invalid ||= !valid; total += valid ? subtotal(r) : 0;
      tr.querySelector('output').textContent = valid ? money(subtotal(r)) : '—';
    });
    const count = $('invoice-rows').children.length;
    $('invoice-total').textContent = $('invoice-summary-potential').textContent = invalid ? '—' : money(total);
    $('invoice-advance').textContent = advance === null ? '—' : money(advance);
    $('invoice-balance').textContent = $('invoice-summary-payable').textContent = invalid || advance === null ? '—' : money(total - advance);
    $('invoice-market-count').textContent = `${count} ${count === 1 ? 'market' : 'markets'}`;
    $('invoice-empty').hidden = count > 0; $('invoice-add').disabled = count >= 100;
    if (loadedMonth) {
      $('invoice-period').textContent = label(loadedMonth) + ' · ' + monthDays() + ' calendar days · Monthly rate per store';
      $('invoice-due').textContent = !invalid && advance !== null && total < advance ? 'Credit balance after advance' : 'Potential pay less advance';
    }
    if (dirty) $('invoice-state').textContent = 'Unsaved changes';
  }
  function markDirty() { dirty = true; message(); refresh(); }
  function addRow(row = {dealer:'',market:'',store_count:1,amount_cents:0,remark:''}, focus = false) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td data-label="Dealer / Market"><input data-field="dealer" aria-label="Dealer" list="invoice-dealers" placeholder="Dealer" maxlength="100" required><input data-field="market" aria-label="Market" list="invoice-markets" placeholder="Market name" maxlength="100" required></td>
      <td data-label="Store count"><input data-field="store_count" aria-label="Store count" type="number" inputmode="numeric" min="1" max="10000" step="1" required></td>
      <td data-label="Monthly / store"><div class="inv-money-input"><span>$</span><input data-field="amount" aria-label="Monthly amount per store in USD" inputmode="decimal" pattern="[0-9]{1,9}([.][0-9]{1,2})?" title="Enter the full-month rate per store" required></div></td>
      <td data-label="Days worked"><div class="inv-days-input"><input data-field="days_worked" aria-label="Days worked" type="number" inputmode="numeric" min="0" max="${monthDays()}" step="1" required><span class="inv-days-denominator">/ ${monthDays()}</span></div></td>
      <td data-label="Potential pay"><output aria-label="Potential pay"></output></td>
      <td data-label="Remark"><textarea data-field="remark" aria-label="Remark" placeholder="Add a note…" maxlength="500" rows="2"></textarea></td>
      <td class="inv-remove-cell"><button type="button" class="inv-remove" aria-label="Remove market">×</button></td>`;
    for (const [key,value] of Object.entries({dealer:row.dealer,market:row.market,store_count:row.store_count ?? 1,days_worked:row.days_worked ?? monthDays(),amount:(row.amount_cents/100).toFixed(2),remark:row.remark})) tr.querySelector(`[data-field="${key}"]`).value = value;
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
  function rememberInvoice(id = '') {
    const url = new URL(location.href);
    if (id) url.searchParams.set('invoice',id); else url.searchParams.delete('invoice');
    history.replaceState(null,'',url);
  }
  function newInvoice() {
    generation++; invoiceId = crypto.randomUUID(); loadedMonth = defaultMonth(); revision = null; dirty = false;
    $('invoice-name').value = ''; $('invoice-month').value = loadedMonth; $('invoice-rows').replaceChildren();
    $('invoice-payment-advance').value = '0.00'; $('invoice-payment-remark').value = '';
    $('invoice-state').textContent = 'New invoice'; $('invoice-updated').textContent = 'Name your invoice, then save it to the database';
    rememberInvoice(); message(); refresh(); lock(false); void loadSuggestions(generation);
  }
  async function load(force = false) {
    if (!allowed() || busy || (!force && loadedMonth)) return;
    void loadLibrary();
    const id = force ? (revision ? invoiceId : '') : new URL(location.href).searchParams.get('invoice');
    if (id) await openInvoice(id); else newInvoice();
  }
  async function openInvoice(id) {
    if (!allowed() || busy) return;
    const token = ++generation; lock(true); message(); $('invoice-state').textContent = 'Loading invoice…';
    try {
      const result = await api('invoices/' + encodeURIComponent(id));
      if (token !== generation || !allowed()) return;
      invoiceId = result.invoice.id; loadedMonth = result.invoice.month; revision = result.invoice.revision; dirty = false;
      $('invoice-month').value = loadedMonth; $('invoice-name').value = result.invoice.name;
      $('invoice-payment-advance').value = (result.invoice.advance_cents / 100).toFixed(2);
      $('invoice-payment-remark').value = result.invoice.remark || '';
      $('invoice-rows').replaceChildren(); result.invoice.rows.forEach(r => addRow(r));
      $('invoice-state').textContent = 'All changes saved';
      $('invoice-updated').textContent = result.invoice.updated_at ? 'Saved ' + new Date(result.invoice.updated_at).toLocaleString() : 'Ready for your first market';
      rememberInvoice(invoiceId); refresh(); void loadSuggestions(token);
    } catch (error) {
      if (token !== generation || !allowed()) return;
      $('invoice-state').textContent = dirty ? 'Unsaved changes' : 'Could not load invoice'; message(error.message,true);
    } finally { if (token === generation) lock(false); }
  }
  async function loadLibrary() {
    if (!allowed()) return;
    const token = ++listGeneration;
    const params = new URLSearchParams({q:$('invoice-search').value.trim(),month:$('invoice-filter-month').value,offset:String(listOffset)});
    $('invoice-library-message').textContent = 'Loading saved invoices…';
    $('invoice-library-prev').disabled = true; $('invoice-library-next').disabled = true;
    try {
      const result = await api('invoices?' + params);
      if (token !== listGeneration || !allowed()) return;
      listMore = result.has_more;
      $('invoice-saved-list').innerHTML = result.invoices.map(item => `<div class="inv-saved-item"><div><strong>${escapeHTML(item.name)}</strong><small>${escapeHTML(label(item.month))} · Saved ${escapeHTML(new Date(item.updated_at).toLocaleString())}</small></div><button type="button" data-invoice-open="${escapeHTML(item.id)}">Open →</button></div>`).join('');
      $('invoice-library-message').textContent = result.invoices.length ? '' : params.get('q') || params.get('month') ? 'No saved invoices match these filters.' : 'No invoices saved yet. Name your first invoice and click Save changes.';
      $('invoice-library-page').textContent = 'Page ' + (listOffset / 20 + 1);
      $('invoice-library-prev').disabled = listOffset === 0; $('invoice-library-next').disabled = !listMore;
    } catch (error) {
      if (token !== listGeneration || !allowed()) return;
      $('invoice-saved-list').replaceChildren(); $('invoice-library-message').textContent = error.message;
    }
  }
  async function save() {
    if (!allowed() || busy || !loadedMonth || !$('invoice-form').reportValidity()) return false;
    if (!$('invoice-name').reportValidity() || !$('invoice-month').reportValidity()) return false;
    const name = $('invoice-name').value.trim();
    if (!name) { message('Give this invoice a name before saving.',true); $('invoice-name').focus(); return false; }
    const data = rows();
    if (!data.every(validRow) || invoiceAdvance() === null) { message('Enter valid counts, days worked, and amounts. Days worked cannot exceed the days in this month; stores × monthly rate must be below 1 billion USD per market.',true); return false; }
    const keys = data.map(r => JSON.stringify([r.dealer.toLowerCase(),r.market.toLowerCase()]));
    if (new Set(keys).size !== keys.length) { message('Each dealer and market can appear only once per invoice.',true); return false; }
    if (data.some(r => !r.dealer || !r.market)) { message('Enter a dealer and market for every row.',true); return false; }
    const token = generation; lock(true); message(); $('invoice-state').textContent = 'Saving…';
    try {
      const result = await api('invoices/' + invoiceId, 'PUT', {name,month:loadedMonth,revision,rows:data,advance_cents:invoiceAdvance(),remark:$('invoice-payment-remark').value.trim()});
      if (token !== generation || !allowed()) return false;
      revision = result.invoice.revision; dirty = false; $('invoice-state').textContent = 'All changes saved';
      $('invoice-name').value = result.invoice.name;
      rememberInvoice(invoiceId); listOffset = 0; void loadLibrary();
      $('invoice-updated').textContent = 'Saved to database · ' + new Date(result.invoice.updated_at).toLocaleString(); return true;
    } catch (error) {
      if (token === generation && allowed()) { message(error.message,true); $('invoice-state').textContent = 'Changes not saved'; }
      return false;
    } finally { if (token === generation) lock(false); }
  }
  function preparePrint() {
    printSheet.replaceChildren(); document.body.classList.remove('invoices-print-ready');
    if (!allowed() || page !== 'invoices' || !loadedMonth) return;
    const data = rows(), valid = data.every(validRow) && invoiceAdvance() !== null;
    const total = data.reduce((s,r) => s + subtotal(r),0), advance = invoiceAdvance();
    printSheet.innerHTML = `<header class="inv-print-head"><div class="inv-print-identity"><img src="/archet-logo.png" alt="Archet Solutions Private Limited" width="160" height="108"><div class="inv-print-brand">Archet Solutions<span>Private Limited</span></div></div><div class="inv-print-title"><small>MONTHLY MARKET STATEMENT</small><strong>Invoice<span>.</span></strong><span class="inv-print-number">INV-${escapeHTML(loadedMonth.replace('-',''))}-${escapeHTML(invoiceId.slice(0,8).toUpperCase())}</span></div></header>
      <h2 class="inv-print-name">${escapeHTML($('invoice-name').value.trim() || 'Untitled invoice')}</h2>
      <div class="inv-print-period"><div><small>INVOICE PERIOD</small><h1>${escapeHTML(label(loadedMonth))}</h1></div></div>
      <div class="inv-print-section"><h2>Market breakdown</h2><span>${data.length} ${data.length === 1 ? 'MARKET' : 'MARKETS'} / USD</span></div>
      ${dirty || !revision || !valid ? '<p class="inv-print-draft">DRAFT · Unsaved invoice</p>' : ''}
      <table><colgroup><col style="width:21%"><col style="width:8%"><col style="width:16%"><col style="width:16%"><col style="width:18%"><col style="width:21%"></colgroup><thead><tr><th>Dealer / Market</th><th>Stores</th><th>Monthly /<br>store</th><th>Days<br>worked</th><th>Potential<br>pay</th><th>Remark</th></tr></thead><tbody>${data.map(r => `<tr><td><strong>${escapeHTML(r.market)}</strong><small>${escapeHTML(r.dealer)}</small></td><td>${r.store_count ?? '—'}</td><td>${r.amount_cents === null ? '—' : money(r.amount_cents)}</td><td>${r.days_worked ?? '—'} / ${monthDays()}</td><td><strong>${!validRow(r) ? '—' : money(subtotal(r))}</strong></td><td class="inv-print-remark">${escapeHTML(r.remark) || '—'}</td></tr>`).join('')}</tbody></table>
      <div class="inv-print-payment"><div class="inv-print-payment-remark"><h3>Invoice remark</h3><p>${escapeHTML($('invoice-payment-remark').value.trim()) || '—'}</p><small></small></div><div class="inv-print-totals"><div><span>Total potential pay</span><strong>${valid ? money(total) : '—'}</strong></div><div><span>Advance already paid</span><strong>${valid ? money(advance) : '—'}</strong></div><div class="inv-print-balance"><span>Total payable</span><strong>${valid ? money(total-advance) : '—'}</strong></div></div></div>
      <section class="inv-bank-details" aria-label="Bank details">${$('invoice-bank-details').innerHTML}</section>
      <footer><div><strong>Archet Solutions Private Limited</strong><span>Precision in every detail.</span></div><p>This is automated generated invoice</p></footer>`;
    document.body.classList.add('invoices-print-ready');
  }
  function clear() {
    generation++; loadedMonth = ''; revision = null; dirty = false; busy = false; suggestions = []; suggested = false;
    invoiceId = ''; listGeneration++; listOffset = 0; listMore = false; clearTimeout(searchTimer);
    ['invoice-name','invoice-search','invoice-filter-month'].forEach(id => $(id).value = '');
    $('invoice-payment-advance').value = '0.00'; $('invoice-payment-remark').value = '';
    ['invoice-saved-list','invoice-library-message','invoice-library-page'].forEach(id => $(id).replaceChildren());
    $('invoice-rows').replaceChildren(); $('invoice-month').value = ''; $('invoices-nav').hidden = true;
    $('page-invoices').hidden = true; $('invoice-dealers').replaceChildren(); $('invoice-markets').replaceChildren();
    $('invoice-period').textContent = ''; $('invoice-updated').textContent = ''; $('invoice-due').textContent = '';
    printSheet.replaceChildren(); document.body.classList.remove('invoices-print-ready', 'invoices-mode'); message(); refresh(); lock(false);
  }
  $('invoice-form').addEventListener('input',markDirty);
  $('invoice-form').onsubmit = event => { event.preventDefault(); void save(); };
  $('invoice-add').onclick = () => { if ($('invoice-rows').children.length < 100) { addRow(undefined,true); markDirty(); } };
  $('invoice-save').onclick = () => void save();
  $('invoice-reload').onclick = () => { if (!dirty || confirm('Discard unsaved changes and reload this invoice?')) void load(true); };
  $('invoice-month').onchange = () => {
    if (!$('invoice-month').validity.valid || !$('invoice-month').value) { $('invoice-month').value = loadedMonth; return; }
    const previousDays = monthDays();
    loadedMonth = $('invoice-month').value;
    $('invoice-rows').querySelectorAll('[data-field="days_worked"]').forEach(input => {
      if (Number(input.value) === previousDays) input.value = monthDays();
      input.max = monthDays();
      input.nextElementSibling.textContent = '/ ' + monthDays();
    });
    markDirty();
  };
  $('invoice-name').addEventListener('input',markDirty);
  $('invoice-new').onclick = () => { if (!busy && (!dirty || confirm('Discard unsaved changes and start a new invoice?'))) { newInvoice(); $('invoice-name').focus(); } };
  $('invoice-saved-list').onclick = event => {
    const button = event.target.closest('[data-invoice-open]');
    if (button && !busy && (!dirty || confirm('Discard unsaved changes and open this invoice?'))) void openInvoice(button.dataset.invoiceOpen);
  };
  function filterLibrary() {
    listGeneration++; listOffset = 0; clearTimeout(searchTimer);
    searchTimer = setTimeout(() => void loadLibrary(),250);
  }
  $('invoice-search').addEventListener('input',filterLibrary);
  $('invoice-filter-month').addEventListener('change',filterLibrary);
  $('invoice-library-refresh').onclick = () => { listOffset = 0; void loadLibrary(); };
  $('invoice-library-prev').onclick = () => { listOffset = Math.max(0,listOffset - 20); void loadLibrary(); };
  $('invoice-library-next').onclick = () => { if (listMore) { listOffset += 20; void loadLibrary(); } };
  $('invoice-print-button').onclick = async () => {
    if (!$('invoice-rows').children.length) { message('Add a market before printing.',true); return; }
    if (!(await save())) return;
    if (!allowed() || page !== 'invoices') return;
    try {
      await Promise.all([document.fonts.ready, printLogo.decode()]);
    } catch (_) { message('The invoice logo could not load. Reload the page before printing.',true); return; }
    if (!allowed() || page !== 'invoices') return;
    preparePrint(); window.print();
  };
  window.addEventListener('beforeprint',preparePrint);
  window.addEventListener('afterprint',() => { printSheet.replaceChildren(); document.body.classList.remove('invoices-print-ready'); });
  window.addEventListener('beforeunload',event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
  window.invoiceDashboard = {allowed,load,clear};
})();
