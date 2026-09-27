'use strict';
(() => {
  const el = id => document.getElementById('sales-' + id);
  const columns = [['dealer','Dealer'],['market','Market'],['store','Store'],['new_activation','New activation'],['upgrade','Upgrade'],['reactivation','Reactivation'],['bts','BTS'],['hsi','HSI'],['accessory','Accessory'],['apo','APO'],['total_boxes','Total boxes'],['qpay','QPay'],['qpay_conv','QPay conv']];
  const themes = {'': ['#095570','#f3f8fa','#083c51','#829aa5'],Connect:['#095570','#f3f8fa','#083c51','#829aa5'],California:['#a92d49','#faf0f2','#491c2c','#ecd8de'],SRH:['#a06118','#fbf5ea','#503718','#e8dcc9'],AMQ:['#365cad','#eef2fa','#20335b','#d6dfef'],ARM:['#176b56','#edf8f3','#104735','#cee7dc'],ARBF:['#7646a5','#f5effa','#3d2652','#e4d7ed']};
  let data = null, revision = 0, syncing = false;
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
    el('updated').textContent = result.updated_at ? new Date(result.updated_at).toLocaleString('en-US',{timeZone:'America/Chicago',month:'short',day:'numeric',hour:'numeric',minute:'2-digit',timeZoneName:'short'}) : 'Awaiting first import';
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
  // Draw a crisp vector-style report, then copy it as a high-resolution PNG.
  function snapshot() {
    const cols=columns.filter(([key])=>key!=='dealer'),rows=data.rows;
    const widths=[142,401,241,145,208,80,75,167,126,192,99,172];
    const width=2112,pad=32,tableWidth=2048,tableY=164,rowHeight=52,headerHeight=54,totalHeight=60;
    const incomplete=data.coverage.complete<data.coverage.expected || rows.some(r=>r.incomplete||r.stale);
    const tableHeight=headerHeight+rows.length*rowHeight+totalHeight;
    const height=tableY+tableHeight+64+(incomplete?30:0);
    const scale=Math.min(2835/width,15000/height),canvas=document.createElement('canvas');
    canvas.width=Math.ceil(width*scale);canvas.height=Math.ceil(height*scale);
    const ctx=canvas.getContext('2d');ctx.scale(scale,scale);
    const colors=themes[el('dealer').value]||themes[''];
    const ink='#16354a',grid='#e0e8ef';
    // Fit the entire table once, so headings, values and totals share one size.
    let tableFont=22;
    ctx.font='700 22px Arial, sans-serif';
    cols.forEach(([key,heading],i)=>{
      const values=[heading.toUpperCase(),...rows.map(row=>text(key,row[key])+(key==='store'&&(row.stale||row.incomplete)?' †':''))];
      if(i>1)values.push(text(key,data.totals[key]));
      for(const value of values){const measured=ctx.measureText(value).width;if(measured)tableFont=Math.min(tableFont,22*(widths[i]-32)/measured);}
    });
    tableFont=Math.floor(tableFont*2)/2;
    function rounded(x,y,w,h,r,fill){ctx.beginPath();ctx.roundRect(x,y,w,h,r);ctx.fillStyle=fill;ctx.fill();}
    function raisedCell(x,y,w,h,fill,dark=false){
      ctx.save();
      ctx.shadowColor=dark?'#00000045':'#15334f30';
      ctx.shadowBlur=5*scale;ctx.shadowOffsetX=1*scale;ctx.shadowOffsetY=3*scale;
      ctx.fillStyle=fill;ctx.fillRect(x,y,w,h);
      ctx.restore();
      // A translucent top reflection leaves the base performance color visible.
      const shine=ctx.createLinearGradient(x,y+2,x,y+h*.46);
      shine.addColorStop(0,dark?'#ffffff4d':'#ffffff85');
      shine.addColorStop(.6,dark?'#ffffff18':'#ffffff30');
      shine.addColorStop(1,'#ffffff00');
      ctx.fillStyle=shine;ctx.fillRect(x+2,y+2,w-4,h*.46-2);
      // Beveled edges create depth without changing the performance fill color.
      const bevel=ctx.createLinearGradient(x,y,x,y+h);
      bevel.addColorStop(0,dark?'#ffffff55':'#ffffffee');
      bevel.addColorStop(.45,dark?'#ffffff10':'#ffffff40');
      bevel.addColorStop(1,dark?'#00000055':'#16354a30');
      ctx.strokeStyle=bevel;ctx.lineWidth=1.5;
      ctx.strokeRect(x+.75,y+.75,w-1.5,h-1.5);
    }
    function label(value,x,y,w,h,font=23,color=ink,align='center',weight=700,fit=true){
      ctx.save();ctx.beginPath();ctx.rect(x+8,y,w-16,h);ctx.clip();
      ctx.fillStyle=color;ctx.textAlign=align;ctx.textBaseline='middle';
      let size=font;ctx.font=weight+' '+size+'px Arial, sans-serif';
      while(fit&&ctx.measureText(value).width>w-28&&size>12){size--;ctx.font=weight+' '+size+'px Arial, sans-serif';}
      ctx.fillText(value,align==='left'?x+16:x+w/2,y+h/2);ctx.restore();
    }
    ctx.fillStyle='#f0f5f9';ctx.fillRect(0,0,width,height);
    // Flat geometric decoration stays away from the text and live figures.
    rounded(pad,24,tableWidth,116,20,colors[2]);
    ctx.save();ctx.beginPath();ctx.roundRect(pad,24,tableWidth,116,20);ctx.clip();
    ctx.fillStyle=colors[0];ctx.beginPath();ctx.moveTo(width-570,24);ctx.lineTo(width-400,140);ctx.lineTo(width,140);ctx.lineTo(width,24);ctx.closePath();ctx.fill();
    ctx.strokeStyle='#ffffff12';ctx.lineWidth=2;
    for(let n=0;n<4;n++){ctx.beginPath();ctx.moveTo(width-620+n*80,24);ctx.lineTo(width-450+n*80,140);ctx.stroke();}
    ctx.restore();
    label(reportTitle(data,el('market').value || 'ALL MARKETS'),pad+16,42,tableWidth-260,48,32,'#fff','left',800);
    label('STORE PERFORMANCE  /  '+(incomplete?'PARTIAL DATA':'SALES REPORT'),pad+16,90,tableWidth-260,26,14,'#d9e8f0','left',600);
    rounded(width-pad-190,53,160,56,12,'#ffffff18');
    label(rows.length+' STORES',width-pad-190,53,160,56,22,'#fff');
    rounded(pad,tableY,tableWidth,tableHeight,16,'#fff');
    ctx.save();ctx.beginPath();ctx.roundRect(pad,tableY,tableWidth,tableHeight,16);ctx.clip();
    function drawRow(values,y,kind){
      const head=kind==='head',total=kind==='total',h=total?totalHeight:rowHeight;
      ctx.fillStyle=head?colors[0]:total?colors[2]:kind%2?'#f7fafc':'#fff';
      ctx.fillRect(pad,y,tableWidth,head?headerHeight:h);
      let x=pad;
      cols.forEach(([key,heading],i)=>{
        if(total&&i===0){raisedCell(x+5,y+6,widths[0]+widths[1]-10,h-12,colors[2],true);label('TOTAL',x,y,widths[0]+widths[1],h,tableFont,'#fff','left',700,false);x+=widths[0];return;}
        if(total&&i===1){x+=widths[1];return;}
        const value=values[key];
        const fill=head?colors[0]:total?colors[2]:data.metric_fills?.[kind]?.[key] || (key==='total_boxes'&&value!==null?'#d9edf7':kind%2?'#f7fafc':'#fff');
        raisedCell(x+5,y+6,widths[i]-10,(head?headerHeight:h)-12,fill,head||total);
        const valueText=head?heading.toUpperCase():text(key,value)+(key==='store'&&(values.stale||values.incomplete)?' †':'');
        label(valueText,x,y,widths[i],head?headerHeight:h,tableFont,head||total?'#fff':key==='market'?colors[0]:ink,i===1&&!head?'left':'center',700,false);
        x+=widths[i];
      });
      if(!head&&!total&&(kind===0||rows[kind-1].market!==values.market)){ctx.fillStyle=colors[0];ctx.fillRect(pad,y,4,h);}
    }
    drawRow({},tableY,'head');rows.forEach((r,i)=>drawRow(r,tableY+headerHeight+i*rowHeight,i));
    drawRow(data.totals,tableY+headerHeight+rows.length*rowHeight,'total');
    ctx.restore();ctx.beginPath();ctx.roundRect(pad,tableY,tableWidth,tableHeight,16);ctx.strokeStyle=grid;ctx.lineWidth=1.5;ctx.stroke();
    const footerY=tableY+tableHeight+14;
    label('ARCHET  /  SALES UPDATE',pad,footerY,480,30,14,'#61798b','left',700);
    const legend=ctx.createLinearGradient(width-500,0,width-388,0);legend.addColorStop(0,'#e98181');legend.addColorStop(.5,'#eeee88');legend.addColorStop(1,'#80e77f');
    rounded(width-500,footerY+10,112,10,5,legend);
    label('APO / QPAY CONV  ·  LOW → HIGH',width-380,footerY,348,30,14,'#61798b','left',600);
    if(incomplete)label('† Partial or retained source data. Totals reflect available values.',pad,footerY+30,tableWidth,26,15,'#865c20','left',600);
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
