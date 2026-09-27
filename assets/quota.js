'use strict';
(() => {
  const el = id => document.getElementById('quota-' + id);
  const colors = {Connect:'#095570',California:'#a92d49',SRH:'#a06118',AMQ:'#365cad',ARM:'#176b56',ARBF:'#7646a5'};
  const dealers = Object.keys(colors);
  let data = null, sequence = 0, previewSequence = 0, pending = null;
  const message = text => { el('message').textContent = text; el('message').hidden = !text; };
  const monthLabel = value => new Date(value + '-01T12:00:00').toLocaleDateString('en-US',{month:'long',year:'numeric'});
  function options(id, items, empty, selected = el(id).value) {
    el(id).replaceChildren(...(empty ? [new Option(empty,'')] : []), ...items.map(i => typeof i === 'string' ? new Option(i,i) : new Option(i.name,i.id)));
    el(id).value = [...el(id).options].some(o => o.value === selected) ? selected : (empty ? '' : el(id).options[0]?.value || '');
    el(id).dispatchEvent(new Event('picker-sync'));
  }
  function theme() {
    const color = colors[el('dealer').value] || colors.Connect;
    const channels = color.match(/[0-9a-f]{2}/gi).map(x => parseInt(x,16));
    const mix = (target,amount) => '#' + channels.map(c => Math.round(c + (target-c)*amount).toString(16).padStart(2,'0')).join('');
    for (const [key,value] of Object.entries({accent:color,dark:mix(0,.47),tint:mix(255,.95),border:mix(255,.72)})) document.documentElement.style.setProperty('--sales-' + key,value);
  }
  function query() {
    const params = new URLSearchParams();
    for (const key of ['month','dealer','market','store']) if (el(key).value) params.set(key,el(key).value);
    return params.toString();
  }
  const growthColor = value => value == null ? null : Number(value)>=1 ? '#86efac' : Number(value)>=.75 ? '#bef264' : Number(value)>=.5 ? '#fde047' : Number(value)>=.25 ? '#fdba74' : '#fca5a5';
  function format(value, kind) {
    if (value == null) return '\u2014';
    if (kind === 'text') return String(value);
    if (value === '') return '';
    const number = Number(value), negative = number < 0;
    let text = Math.abs(number * (kind === 'percent' ? 100 : 1)).toLocaleString('en-US', {minimumFractionDigits:kind==='number'?0:2,maximumFractionDigits:2});
    if (kind === 'money') text = '$' + text;
    if (kind === 'percent') text += '%';
    return negative ? '(' + text + ')' : text;
  }
  function cell(row, col, total = false) {
    const value = row[col.key] ?? (col.kind === 'text' ? '' : null);
    let text = escapeHTML(format(value,col.kind));
    if (col.key === 'rank' && total) text = '';
    if (col.key === 'store' && row.incomplete) text += '<span class="quota-provisional" title="Partial or stale saved actuals">*</span>';
    const fill = !total && col.kind === 'percent' ? growthColor(value) : null;
    if (fill) text = `<span class="quota-growth" style="--growth-color:${fill}"><i style="width:${Math.min(100,Math.max(0,Number(value)*100))}%"></i><span>${text}</span></span>`;
    return `<td class="${col.kind==='text'?'quota-text ':''}${col.key==='store'?'quota-store':''}"${fill?` style="background:${fill}55"`:''}>${text}</td>`;
  }
  function draw() {
    theme();
    el('dealer').dispatchEvent(new Event('picker-sync'));
    el('tables').innerHTML = data.count ? data.tables.map(table => `<article class="quota-card" id="quota-card-${table.id}"><div class="quota-card-head"><div><h2>${escapeHTML(table.title)}</h2><small>${escapeHTML(monthLabel(data.month))} &middot; ${data.count} stores</small></div><button type="button" data-quota-copy="${table.id}">Copy Snapshot</button></div>${data.incomplete?'<div class="quota-partial">* Provisional: some saved actuals are incomplete or stale. Totals include available data.</div>':''}<div class="quota-scroll"><table aria-label="${escapeHTML(table.title)}"><thead><tr>${table.columns.map(c=>'<th scope="col">'+escapeHTML(c.label)+'</th>').join('')}</tr></thead><tbody>${table.rows.map(row=>'<tr>'+table.columns.map(col=>cell(row,col)).join('')+'</tr>').join('')}</tbody><tfoot><tr>${table.columns.map(col=>cell(table.total,col,true)).join('')}</tr></tfoot></table></div></article>`).join('') : '';
    el('count').textContent = data.count + ' STORES';
    el('month-label').textContent = monthLabel(data.month);
    el('days').textContent = `${data.elapsed} of ${data.days} days elapsed`;
    el('empty').hidden = data.count > 0;
    el('empty').textContent = !data.calling_tree_active ? 'Upload a Calling Tree first, then upload monthly goals for its stores.' : data.uploads.length ? 'No goals match these filters and the active Calling Tree.' : 'No goals uploaded for this month. An administrator can upload a Goals workbook above.';
    el('upload-info').textContent = data.uploads.map(u=>`${u.dealer}: ${u.filename} (${u.row_count} stores)`).join(' \u00b7 ');
    el('coverage').textContent = data.incomplete ? `${data.incomplete} stores have incomplete or stale saved actuals. Rankings and projections are provisional.` : data.count ? (data.elapsed ? 'Saved sales through '+(data.month < data.today.slice(0,7) ? data.month+'-'+data.days : data.today)+'.' : 'This month has not started yet.') : 'Upload monthly goals to begin.';
    if (data.updated_at) el('coverage').textContent += ' Oldest source refresh: '+new Date(data.updated_at).toLocaleString()+'.';
    el('excel').disabled = !data.count;
  }
  async function load() {
    const id = ++sequence; data = null;
    el('upload').hidden = currentUser?.role !== 'admin';
    el('tables').replaceChildren(); el('empty').hidden = true; el('excel').disabled = true;
    el('coverage').textContent = 'Loading monthly goals\u2026'; message(''); theme();
    try {
      const result = await api('quota?' + query());
      if (id !== sequence || !currentUser) return;
      data = result;
      options('month',data.months.map(m=>({id:m,name:monthLabel(m)})),null,data.month);
      options('market',data.markets,'All Markets');
      options('store',data.stores.map(s=>({id:s.id,name:el('dealer').value?s.name:`${s.name} (${s.dealer})`})),'All Stores');
      if (!el('upload-month').value) el('upload-month').value = data.today.slice(0,7);
      draw();
    } catch (error) { if (id === sequence) { el('coverage').textContent = 'Quota report could not be loaded.'; message(error.message); } }
  }
  for (const key of ['month','dealer','market','store']) el(key).onchange = () => {
    if (key==='dealer'||key==='month') el('market').value = '';
    if (key!=='store') el('store').value = '';
    load();
  };
  el('reload').onclick = load;
  async function download(path, fallback) {
    const response = await fetch('/api/internal/' + path,{credentials:'same-origin'});
    if (!response.ok) {
      const result = await response.json().catch(()=>({}));
      if (response.status===401) signedOut('Your session has ended. Please sign in again.');
      throw new Error(result.message || 'The file could not be downloaded.');
    }
    saveBlob(await response.blob(), fallback);
  }
  function saveBlob(blob, name) {
    const link = document.createElement('a'), url = URL.createObjectURL(blob);
    link.href = url; link.download = name; document.body.append(link); link.click(); link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),10000);
  }
  el('excel').onclick = async () => { try { await download('quota/excel?'+query(),'Quota-Update-'+data.month+'.xlsx'); } catch (error) { message(error.message); } };
  el('template').onclick = async () => { try { await download('quota/template?dealer='+encodeURIComponent(el('upload-dealer').value),'Quota-Goals-'+el('upload-dealer').value+'.xlsx'); } catch (error) { message(error.message); } };
  options('dealer',dealers,'All Dealers'); options('upload-dealer',dealers,null,'California');
  function discard() { previewSequence++; pending = null; el('preview').hidden = true; el('preview-table').tBodies[0].replaceChildren(); }
  el('discard').onclick = discard;
  el('form').addEventListener('change',discard);
  function uploadBusy(value) { for (const input of el('form').elements) input.disabled = value; el('save').disabled = value; el('discard').disabled = value; }
  el('form').onsubmit = async event => {
    event.preventDefault(); discard();
    const file = el('file').files[0];
    if (!file || file.size>2*1024*1024 || !/\.xls[mx]$/i.test(file.name)) { message('Choose an .xlsx or .xlsm workbook smaller than 2 MB.'); return; }
    const id = previewSequence;
    uploadBusy(true); message('Checking goals against your Calling Tree\u2026');
    try {
      const content = await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('The workbook could not be read.'));reader.readAsDataURL(file);});
      const payload = {dealer:el('upload-dealer').value,month:el('upload-month').value,filename:file.name,content};
      const result = await api('quota/upload','POST',payload);
      if (id!==previewSequence || !currentUser) return;
      pending = {...payload,roster_version:result.roster_version};
      el('preview-summary').textContent = result.message;
      const previewColumns = [['market','Market'],['store','Store'],['voice_goal','Voice'],['bts_goal','BTS'],['hsi_goal','HSI/HINT'],...(payload.dealer==='ARBF'?[]:[['accessory_goal','Acc']]),['mim_goal','MIM']];
      el('preview-table').tHead.innerHTML = '<tr>'+previewColumns.map(([,label])=>'<th>'+label+'</th>').join('')+'</tr>';
      el('preview-table').tBodies[0].innerHTML = result.rows.map(r=>'<tr>'+previewColumns.map(([k])=>'<td>'+escapeHTML(format(r[k],k==='market'||k==='store'?'text':k==='accessory_goal'?'money':'number'))+'</td>').join('')+'</tr>').join('');
      el('preview').hidden=false;message('Preview ready. Review the goals, then apply them.');
    } catch (error) { if (id===previewSequence) message(error.message); }
    finally { uploadBusy(false); }
  };
  el('save').onclick = async () => {
    if (!pending) return;
    const payload = {...pending,apply:true}, id = previewSequence; uploadBusy(true);
    try {
      const result = await api('quota/upload','POST',payload);
      if (id!==previewSequence || !currentUser) return;
      options('month',[payload.month],null,payload.month); el('dealer').value=payload.dealer; el('market').value='';el('store').value='';
      discard();el('file').value='';await load();message(result.message);
    } catch (error) { if (id===previewSequence) message(error.message); }
    finally { uploadBusy(false); }
  };
  function snapshot(table) {
    if (table.rows.length > 350) throw new Error('Choose a dealer or market with 350 stores or fewer for a readable snapshot. Excel includes every row.');
    const cols = table.columns.filter(c=>c.key!=='dealer');
    const width=1920, margin=12, titleHeight=76, rowHeight=38, footer=36;
    const canvas=document.createElement('canvas');canvas.width=width;canvas.height=margin*2+titleHeight+(table.rows.length+2)*rowHeight+footer;
    const ctx=canvas.getContext('2d'); const accent=colors[el('dealer').value]||colors.Connect;
    const weights=cols.map(c=>c.key==='store'?2.8:c.key==='rank'?.65:c.kind==='text'?1.1:1.15);
    const sum=weights.reduce((a,b)=>a+b,0), widths=weights.map(w=>(width-2*margin)*w/sum);
    ctx.fillStyle='#f0f6fa';ctx.fillRect(0,0,canvas.width,canvas.height);
    const header=ctx.createLinearGradient(0,0,width,0);header.addColorStop(0,'#062d40');header.addColorStop(.7,accent);header.addColorStop(1,'#062d40');
    ctx.fillStyle=header;ctx.fillRect(margin,margin,width-2*margin,titleHeight-8);
    ctx.fillStyle='#fff';ctx.textAlign='left';ctx.textBaseline='middle';ctx.font='800 25px Arial';
    const title=table.title+' \u00b7 '+(el('market').value||el('dealer').value||'ALL DEALERS').toUpperCase()+' \u00b7 '+monthLabel(data.month).toUpperCase();
    ctx.fillText(title,margin+20,margin+24,width-2*margin-40);
    ctx.font='600 13px Arial';ctx.fillText(`${table.rows.length} STORES  /  ${data.incomplete?'PROVISIONAL - PARTIAL SAVED ACTUALS':'MONTHLY GOALS & SAVED ACTUALS'}`,margin+20,margin+49);
    let font=17;
    const rows=[...table.rows,table.total];
    for (;;) {
      ctx.font=`700 ${font}px Arial`;
      const fits=cols.every((col,i)=>ctx.measureText(col.label.toUpperCase()).width<=widths[i]-14&&rows.every(r=>ctx.measureText(format(r[col.key]??(col.kind==='text'?'':null),col.kind)).width<=widths[i]-14));
      if(fits||font<=10)break;font--;
    }
    function drawRow(row,index,kind) {
      let x=margin;const y=margin+titleHeight+index*rowHeight;
      cols.forEach((col,i)=>{
        const w=widths[i], dark=kind!=='body', fill=dark?accent:col.kind==='percent'?(growthColor(row[col.key])||'#fff'):index%2?'#ffffff':'#edf5f9';
        ctx.shadowColor='#082d4560';ctx.shadowBlur=2;ctx.shadowOffsetX=1;ctx.shadowOffsetY=2;
        ctx.fillStyle=fill;ctx.fillRect(x+2,y+2,w-4,rowHeight-4);
        ctx.shadowColor='transparent';ctx.shadowBlur=ctx.shadowOffsetX=ctx.shadowOffsetY=0;
        const shine=ctx.createLinearGradient(0,y,0,y+rowHeight);shine.addColorStop(0,'#ffffff60');shine.addColorStop(.45,'#ffffff00');shine.addColorStop(1,'#00000008');ctx.fillStyle=shine;ctx.fillRect(x+2,y+2,w-4,rowHeight-4);
        ctx.strokeStyle=dark?'#ffffff40':'#7b98a850';ctx.strokeRect(x+2.5,y+2.5,w-5,rowHeight-5);
        ctx.fillStyle=dark?'#fff':'#123b4f';ctx.font=`700 ${font}px Arial`;ctx.textAlign=col.key==='store'?'left':'center';
        let text=kind==='head'?col.label.toUpperCase():format(row[col.key]??(col.kind==='text'?'':null),col.kind);
        if(kind==='total'&&col.key==='rank')text='';
        ctx.fillText(text,col.key==='store'?x+9:x+w/2,y+rowHeight/2,w-14);x+=w;
      });
    }
    drawRow({},0,'head');table.rows.forEach((r,i)=>drawRow(r,i+1,'body'));drawRow(table.total,table.rows.length+1,'total');
    ctx.font='600 12px Arial';ctx.textAlign='left';ctx.fillStyle='#59768b';ctx.fillText('ARCHET  /  QUOTA UPDATE'+(data.incomplete?'  /  PROVISIONAL TOTALS':''),margin+5,canvas.height-17);
    ctx.textAlign='right';ctx.fillText('GROWTH: RED <25%  \u00b7  ORANGE 25%  \u00b7  YELLOW 50%  \u00b7  LIME 75%  \u00b7  GREEN 100%+',width-margin-5,canvas.height-17);
    return new Promise((resolve,reject)=>canvas.toBlob(blob=>blob?resolve(blob):reject(new Error('Snapshot could not be created.')),'image/png'));
  }
  el('tables').onclick = async event => {
    const button=event.target.closest('[data-quota-copy]');if(!button||!data)return;
    const table=data.tables.find(t=>t.id===button.dataset.quotaCopy);button.disabled=true;
    try {
      const blob=snapshot(table);let copied=false;
      if(navigator.clipboard?.write&&window.ClipboardItem)try{await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);copied=true;}catch(_){}
      if(copied)message(table.title+' snapshot copied.');else{saveBlob(await blob,'Quota-'+table.id+'-'+data.month+'.png');message('Snapshot downloaded. Clipboard access is unavailable.');}
    } catch(error){message(error.message);}finally{button.disabled=false;}
  };
  window.quotaDashboard={load,clear(){sequence++;discard();data=null;el('tables').replaceChildren();el('upload').hidden=true;el('form').reset();el('upload-info').textContent='';options('month',[],null);el('dealer').value='';options('market',[],'All Markets');options('store',[],'All Stores');}};
})();
