'use strict';
(() => {
  const el = id => document.getElementById('sales-' + id);
  const columns = [['dealer','Dealer'],['market','Market'],['store','Store'],['new_activation','New activation'],['upgrade','Upgrade'],['reactivation','Reactivation'],['bts','BTS'],['hsi','HSI'],['accessory','Accessory'],['apo','APO'],['total_boxes','Total boxes'],['qpay','QPay'],['qpay_conv','QPay conv']];
  const themes = {'': ['#095570','#f3f8fa','#083c51','#829aa5'],Connect:['#095570','#f3f8fa','#083c51','#829aa5'],California:['#a92d49','#faf0f2','#491c2c','#ecd8de'],SRH:['#a06118','#fbf5ea','#503718','#e8dcc9'],AMQ:['#365cad','#eef2fa','#20335b','#d6dfef'],ARM:['#176b56','#edf8f3','#104735','#cee7dc'],ARBF:['#7646a5','#f5effa','#3d2652','#e4d7ed']};
  let data = null, revision = 0, syncing = false, syncSequence = 0;
  const localToday = () => new Intl.DateTimeFormat('en-CA',{timeZone:'America/Chicago',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const dateLabel = day => new Date(day + 'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
  const text = (key,value) => value === null ? '—' : ['accessory','apo'].includes(key) ? '$' + Number(value || 0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}) : key === 'qpay_conv' ? Number(value || 0).toFixed(0) + '%' : String(value ?? '');
  function theme() {
    const values = themes[el('dealer').value] || themes[''];
    ['accent','tint','dark','border'].forEach((key,i) => document.documentElement.style.setProperty('--sales-' + key,values[i]));
  }
  function range() {
    const now = localToday(), period = el('period').value;
    if (period === 'custom') return [el('start').value,el('end').value];
    if (period === 'month') return [now.slice(0,8) + '01',now];
    if (period === 'yesterday') { const day = new Date(now + 'T12:00:00Z'); day.setUTCDate(day.getUTCDate()-1); const value = day.toISOString().slice(0,10); return [value,value]; }
    return [now,now];
  }
  function params() {
    const [start,end] = range();
    return new URLSearchParams({start,end,dealer:el('dealer').value,market:el('market').value,store:el('store').value});
  }
  function options(id,values,first) {
    const select = el(id), before = select.value;
    select.replaceChildren(new Option(first,''),...values.map(v => new Option(v.name || v,v.id || v)));
    if ([...select.options].some(o => o.value === before)) select.value = before;
  }
  function message(value) { el('message').textContent = value; el('message').hidden = !value; }
  function cellClass(key,value) {
    if (value === null) return '';
    if (key === 'total_boxes') return 'metric-boxes';
    return '';
  }
  function render(result) {
    options('dealer',result.dealers.map(d => d.name),'All Dealers');
    options('market',result.markets,'All Markets'); options('store',result.stores,'All Stores');
    theme();
    const label = result.start === result.end ? dateLabel(result.start) : dateLabel(result.start) + ' – ' + dateLabel(result.end);
    el('period-label').textContent = (el('dealer').value || 'All dealers') + ' / ' + label;
    el('range-badge').textContent = label; el('count').textContent = result.rows.length + ' STORES';
    el('updated').textContent = result.updated_at ? new Date(result.updated_at).toLocaleString('en-US',{timeZone:'America/Chicago',month:'short',day:'numeric',year:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'}) : 'Awaiting first import';
    const c = result.coverage, incomplete = c.complete < c.expected;
    document.querySelector('.sales-freshness').classList.toggle('incomplete',incomplete || c.retained>0);
    el('coverage').textContent = incomplete ? `Import in progress or incomplete: ${c.complete} of ${c.expected} account-days loaded.` : `${c.complete} of ${c.expected} account-days loaded.`;
    el('stale-note').textContent = c.retained ? '† Some stores were omitted by the latest source export; their last saved values are shown.' : '';
    if (c.errors.length) message('Refresh failed for ' + c.errors.join(', ') + '. Saved data remains available; the next scheduled run retries.');
    const table = el('table');
    table.caption.textContent = reportTitle(result);
    el('empty').textContent = result.calling_tree && !result.calling_tree.active ? 'Upload a Calling Tree to choose the stores shown here.' : 'No Calling Tree stores match this selection.';
    if (result.calling_tree?.unmatched) message(result.calling_tree.unmatched + ' Calling Tree Store IDs have not appeared in RT-POS yet. Their sales are unavailable.');
    table.tHead.innerHTML = '<tr>' + columns.map(([,label])=>'<th scope="col">'+label+'</th>').join('') + '</tr>';
    table.tBodies[0].innerHTML = result.rows.map(r => '<tr>' + columns.map(([k])=>'<td class="'+cellClass(k,r[k])+'">'+(k==='dealer'?'<span class="sales-dealer-chip">':'')+escapeHTML(text(k,r[k]))+(k==='dealer'?'</span>':'')+(k==='store'&&(r.stale||r.incomplete)?'<span class="sales-stale-mark" title="Values may be incomplete; a source report is unavailable or retained">†</span>':'')+'</td>').join('')+'</tr>').join('');
    [...table.tBodies[0].rows].forEach((row,index) => {
      for (const [key,col] of [['apo',9],['qpay_conv',12]]) {
        row.cells[col].style.backgroundColor = result.metric_fills?.[index]?.[key] || '';
      }
    });
    table.tFoot.innerHTML = '<tr><td colspan="3">TOTAL</td>' + columns.slice(3).map(([k])=>'<td>'+escapeHTML(text(k,result.totals[k]))+'</td>').join('') + '</tr>';
    el('empty').hidden = result.rows.length>0; el('copy').disabled = !result.rows.length; el('excel').disabled = !result.rows.length;
    el('sync').hidden = currentUser?.role !== 'admin';
  }
  async function load() {
    const id = ++revision; theme(); message('');
    el('copy').disabled = true; el('excel').disabled = true;
    el('coverage').textContent = 'Loading saved sales…';
    try {
      const result = await api('sales?' + params());
      if (id !== revision || !currentUser) return;
      data = result; render(result);
    } catch (error) { if (id===revision) { data=null; el('table').tBodies[0].replaceChildren(); el('table').tFoot.replaceChildren(); el('coverage').textContent='Unable to load this selection.'; message(error.message); } }
  }
  function reportTitle(result, location=el('market').value || el('dealer').value || 'ALL DEALERS') {
    const period=result.start===result.end?dateLabel(result.start):dateLabel(result.start)+' – '+dateLabel(result.end);
    return ('SALES UPDATE • '+location+' • '+period).toUpperCase();
  }
  function snapshot() {
    return window.salesSnapshot.render(data, {dealer: el('dealer').value, market: el('market').value});
  }
  el('copy').onclick = async () => {
    if (!data) return; const button=el('copy');button.disabled=true;
    try {
      const canvas=snapshot(),blobPromise=new Promise(resolve=>canvas.toBlob(resolve,'image/png'));
      if (navigator.clipboard?.write && window.ClipboardItem) {
        try { await navigator.clipboard.write([new ClipboardItem({'image/png':blobPromise})]);message('Snapshot copied without the Dealer column.');return; } catch { /* Some browsers deny image clipboard access. */ }
      }
      const blob=await blobPromise;if(!blob)throw new Error('Could not generate snapshot. Try a smaller selection.');
      const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download='sales-snapshot.png';link.click();setTimeout(()=>URL.revokeObjectURL(link.href),1000);message('Clipboard unavailable. Your snapshot was downloaded without the Dealer column.');
    } catch(error){message(error.message);}finally{button.disabled=false;}
  };
  el('excel').onclick = () => { if(data)window.location.assign('/api/internal/sales/export?'+params()); };
  el('dealer').onchange=()=>{el('market').value='';el('store').value='';theme();load();};
  el('market').onchange=()=>{el('store').value='';load();};el('store').onchange=load;
  el('period').onchange=()=>{el('custom').hidden=el('period').value!=='custom';if(el('period').value!=='custom')load();};
  el('apply').onclick=()=>{if(!el('start').value||!el('end').value){message('Choose both dates.');return;}load();};el('reload').onclick=load;
  el('sync').onclick=async()=>{
    if(syncing || currentUser?.role !== 'admin')return;
    const id=++syncSequence, isCurrent=()=>id===syncSequence && !!currentUser;
    syncing=true;el('sync').disabled=true;el('sync').textContent='Syncing…';
    message("Downloading today's sales and retrying pending imports…");
    try {
      const result=await syncSalesSources(message,isCurrent);
      if(!result || !isCurrent())return;
      await load();
      if(isCurrent())message(sourceSyncMessage(result));
    } catch(error){if(isCurrent())message(error.message);}
    finally{if(id===syncSequence){syncing=false;el('sync').disabled=false;el('sync').textContent='Sync sources';}}
  };
  for(const id of ['start','end']){el(id).value=localToday();el(id).max=localToday();}
  window.salesDashboard={load,clear(){revision++;syncSequence++;syncing=false;el('sync').disabled=false;el('sync').textContent='Sync sources';data=null;document.body.classList.remove('sales-mode');el('table').tBodies[0].replaceChildren();el('table').tFoot.replaceChildren();},snapshot};
  setInterval(()=>{if(currentUser && page==='sales' && !syncing && !document.hidden)load();},60000);
})();
