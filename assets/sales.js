'use strict';
(() => {
  const el = id => document.getElementById('sales-' + id);
  const columns = [['dealer','Dealer'],['market','Market'],['store','Store'],['new_activation','New activation'],['upgrade','Upgrade'],['reactivation','Reactivation'],['bts','BTS'],['hsi','HSI'],['accessory','Accessory'],['apo','APO'],['total_boxes','Total boxes'],['qpay','QPay'],['qpay_conv','QPay conv']];
  const themes = {'': ['#176b56','#eff6f3','#193d33','#d8e5df'],Connect:['#176b56','#eff6f3','#193d33','#d8e5df'],California:['#a92d49','#faf0f2','#491c2c','#ecd8de'],SRH:['#a06118','#fbf5ea','#503718','#e8dcc9'],ARM:['#365cad','#eef2fa','#20335b','#d6dfef'],ARBF:['#7646a5','#f5effa','#3d2652','#e4d7ed']};
  let data = null, revision = 0, syncing = false;
  const localToday = () => new Intl.DateTimeFormat('en-CA',{timeZone:'America/Chicago',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const dateLabel = day => new Date(day + 'T12:00:00').toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
  const text = (key,value) => ['accessory','apo'].includes(key) ? '$' + Number(value || 0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2}) : key === 'qpay_conv' ? Number(value || 0).toFixed(0) + '%' : String(value ?? '');
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
    if (key === 'total_boxes') return 'metric-boxes';
    if (key === 'qpay_conv') return Number(value)>=100 ? 'metric-good' : Number(value)>=50 ? 'metric-mid' : 'metric-low';
    if (key === 'apo') return Number(value)>=20 ? 'metric-good' : Number(value)>=10 ? 'metric-mid' : 'metric-low';
    return '';
  }
  function render(result) {
    options('dealer',result.dealers.map(d => d.name),'All Dealers');
    options('market',result.markets,'All Markets'); options('store',result.stores,'All Stores');
    theme();
    const label = result.start === result.end ? dateLabel(result.start) : dateLabel(result.start) + ' – ' + dateLabel(result.end);
    el('period-label').textContent = (el('dealer').value || 'All dealers') + ' / ' + label;
    el('range-badge').textContent = label; el('count').textContent = result.rows.length + ' STORES';
    el('updated').textContent = result.updated_at ? new Date(result.updated_at).toLocaleString('en-US',{timeZone:'America/Chicago',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'}) : 'Awaiting first import';
    const c = result.coverage, incomplete = c.complete < c.expected;
    document.querySelector('.sales-freshness').classList.toggle('incomplete',incomplete || c.retained>0);
    el('coverage').textContent = incomplete ? `Import in progress or incomplete: ${c.complete} of ${c.expected} account-days loaded.` : `${c.complete} of ${c.expected} account-days loaded.`;
    el('stale-note').textContent = c.retained ? '† Some stores were omitted by the latest source export; their last saved values are shown.' : '';
    if (c.errors.length) message('Refresh failed for ' + c.errors.join(', ') + '. Saved data remains available; the next scheduled run retries.');
    const table = el('table');
    table.tHead.innerHTML = '<tr>' + columns.map(([,label])=>'<th scope="col">'+label+'</th>').join('') + '</tr>';
    table.tBodies[0].innerHTML = result.rows.map(r => '<tr>' + columns.map(([k])=>'<td class="'+cellClass(k,r[k])+'">'+(k==='dealer'?'<span class="sales-dealer-chip">':'')+escapeHTML(text(k,r[k]))+(k==='dealer'?'</span>':'')+(k==='store'&&r.stale?'<span class="sales-stale-mark" title="Last saved values; source refresh is incomplete">†</span>':'')+'</td>').join('')+'</tr>').join('');
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
  // Canvas generates a PNG of the filtered report. Dealer is deliberately absent.
  function snapshot() {
    const cols = columns.filter(([key])=>key !== 'dealer'), rows = data.rows;
    const widths = cols.map(([key,label]) => {
      const longest = Math.max(label.length,...rows.map(r=>text(key,r[key]).length));
      return key==='store' ? Math.min(370,Math.max(190,longest*7+22)) : key==='market' ? Math.min(185,Math.max(105,longest*7+18)) : Math.max(75,label.length*7+16);
    });
    const width=widths.reduce((a,b)=>a+b,0), height=112+(rows.length+2)*29+35;
    const scale=Math.min(2,16000/height); const canvas=document.createElement('canvas');canvas.width=Math.ceil(width*scale);canvas.height=Math.ceil(height*scale);
    const ctx=canvas.getContext('2d');ctx.scale(scale,scale); const colors=themes[el('dealer').value]||themes[''];
    ctx.fillStyle='#fff';ctx.fillRect(0,0,width,height);ctx.fillStyle=colors[2];ctx.fillRect(0,0,width,77);
    ctx.fillStyle='#fff';ctx.font='bold 24px Georgia';ctx.fillText('SALES UPDATE',20,31);
    ctx.font='12px Arial';ctx.fillText(el('period-label').textContent,20,56);
    ctx.fillStyle='#617269';ctx.font='11px Arial';ctx.fillText(el('coverage').textContent,15,99);
    function drawRow(values,y,kind) {
      let x=0;ctx.textBaseline='middle';
      cols.forEach(([key,label],i)=>{
        const value=values[key],cls=cellClass(key,value);
        ctx.fillStyle=kind==='head'?colors[0]:kind==='total'?colors[2]:cls==='metric-good'?'#bbe2bb':cls==='metric-mid'?'#eee5b7':cls==='metric-low'?'#f0cccc':cls==='metric-boxes'?'#e5f0e7':kind%2?colors[1]:'#fff';
        ctx.fillRect(x,y,widths[i],29);ctx.strokeStyle=colors[3];ctx.strokeRect(x,y,widths[i],29);
        ctx.fillStyle=kind==='head'||kind==='total'?'#fff':'#243d30';ctx.font=(kind==='head'||kind==='total'?'bold ':'')+(kind==='head'?'10':'11')+'px Arial';
        ctx.save();ctx.beginPath();ctx.rect(x+4,y,widths[i]-8,29);ctx.clip();
        const labelText=kind==='head'?label.toUpperCase():text(key,value);
        ctx.textAlign=i<2?'left':'center';ctx.fillText(labelText,i<2?x+9:x+widths[i]/2,y+15);ctx.restore();x+=widths[i];
      });
    }
    drawRow({},112,'head');rows.forEach((r,i)=>drawRow(r,141+i*29,i));drawRow({market:'TOTAL',store:'',...data.totals},141+rows.length*29,'total');
    ctx.textAlign='left';ctx.textBaseline='alphabetic';ctx.fillStyle='#687b70';ctx.font='10px Arial';ctx.fillText('Archet Solutions · '+(data.coverage.retained?'Includes last saved values for omitted stores. ':'')+'Refreshed: '+el('updated').textContent,15,height-12);
    return canvas;
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
    if(syncing)return;syncing=true;el('sync').disabled=true;el('sync').textContent='Syncing…';
    try{const result=await api('sales/refresh','POST',{});await load();message(result.status==='busy'?'Another refresh is already running.':result.remaining?`${result.remaining} account-days remain. Scheduled workers will continue the import.`:'Sources are up to date.');}catch(error){message(error.message);}finally{syncing=false;el('sync').disabled=false;el('sync').textContent='Sync sources';}
  };
  for(const id of ['start','end']){el(id).value=localToday();el(id).max=localToday();}
  window.salesDashboard={load,clear(){revision++;data=null;document.body.classList.remove('sales-mode');el('table').tBodies[0].replaceChildren();el('table').tFoot.replaceChildren();},snapshot};
  setInterval(()=>{if(currentUser && page==='sales' && !syncing && !document.hidden)load();},60000);
})();
