'use strict';
(() => {
  const root=document.createElement('div');root.className='sh-root';
  root.innerHTML=`<div class="sh-hero"><div><div class="sh-eyebrow">STORE OPERATIONS</div><h1 id="sh-title">Store Opening / Closing</h1><p id="sh-subtitle"></p></div><button class="sh-link" id="sh-switch" type="button"></button></div>
    <div class="sh-filters"><label>Dealer<select id="sh-dealer"><option value="">All dealers</option></select></label><label>Market<select id="sh-market"><option value="">All markets</option></select></label><label>Store<select id="sh-store"><option value="">All stores</option></select></label><label>Report period<button id="sh-date" class="sh-button sh-date-trigger" type="button" aria-haspopup="dialog">Today <span>▦</span></button></label><div class="sh-actions"><button id="sh-reload" class="sh-button" type="button">Reload</button><button id="sh-copy" class="sh-button" type="button">Copy Snapshot</button><button id="sh-excel" class="sh-button sh-primary" type="button">Download Excel</button></div></div>
    <div class="sh-summary"><div class="sh-stat"><span>Employee rows</span><b id="sh-total">—</b><small id="sh-store-count">In the selected period</small></div><div class="sh-stat sh-late"><span>Late openings</span><b id="sh-late">—</b><small>1+ minute after opening</small></div><div class="sh-stat sh-pending"><span>Pending reviews</span><b id="sh-pending">—</b><small>Camera or schedule needed</small></div><div class="sh-stat"><span>Employee chargebacks</span><b id="sh-chargebacks">—</b><small>Automatic and manually entered amounts</small></div></div>
    <div class="sh-note" id="sh-note">Hours follow the workbook’s Monday–Friday, Saturday, or Sunday schedule for each report date. You can override hours for an individual date; clear an override and save to restore workbook hours. Stores without a matching schedule stay unset. Missing camera times stay <strong>Pending camera review</strong>.</div>
    <div class="sh-tools"><label class="sh-search-label"><span>⌕</span><input id="sh-search" type="search" placeholder="Search employees or stores" aria-label="Search employees or stores"></label><div class="sh-actions"><button class="sh-button" id="sh-manage" type="button" hidden>↑ Upload schedules</button><button class="sh-button sh-primary" id="sh-add" type="button">＋ Add employee</button></div></div>
    <section class="sh-upload" id="sh-upload" hidden aria-label="Upload store schedules"><div class="sh-upload-head"><div><div class="sh-eyebrow">STORE DIRECTORY & HOURS</div><h2>Keep every store up to date</h2><p>Upload your MON TO SAT and SUN workbook to add dealers, stores, and weekly hours. Existing stores and camera reviews are kept.</p></div><button class="sh-button" type="button" id="sh-upload-close" aria-label="Close schedule upload">×</button></div><div class="sh-upload-select"><label for="sh-file">Schedule workbook (.xlsx, up to 2 MB)</label><input id="sh-file" type="file" accept=".xlsx"><span id="sh-upload-status" role="status"></span></div><div id="sh-upload-preview" hidden><div class="sh-upload-confirm"><strong id="sh-upload-count"></strong><button id="sh-upload-apply" type="button" class="sh-button sh-primary">Apply workbook</button></div><p id="sh-upload-corrections"></p><div class="sh-upload-scroll"><table class="sh-table" id="sh-upload-table"><thead><tr><th>Change</th><th>Dealer</th><th>Market</th><th>Store</th><th>Monday–Friday</th><th>Saturday</th><th>Sunday</th></tr></thead><tbody></tbody></table></div></div></section>
    <div class="sh-toolbar"><span id="sh-coverage" role="status">Loading time punches…</span><div class="sh-actions"><strong id="sh-unsaved"></strong><button class="sh-button" id="sh-discard" type="button" hidden>Discard changes</button><button class="sh-button" id="sh-save-all" type="button" hidden>Save changes</button><button class="sh-button" id="sh-sync" type="button" hidden>↻ Sync sources</button></div></div>
    <div id="sh-message" class="sh-message" role="status" hidden></div><div class="sh-table-wrap"><table class="sh-table" id="sh-table"><thead></thead><tbody></tbody></table><div class="sh-empty" id="sh-empty" hidden>No stores in this selection. Adjust the filters or upload a schedule workbook to add stores.</div></div>
    <div class="sh-page-controls"><button class="sh-button" id="sh-prev" type="button">← Previous</button><span id="sh-page-label"></span><button class="sh-button" id="sh-next" type="button">Next →</button></div>
    <p class="sh-footnote">Each employee has a separate daily row. Repeated shifts use that employee’s earliest RT clock-in and latest RT clock-out. Times use the store’s local clock.<br>Automatic rules (unless manually overridden): late ≥1 minute after opening; early ≥1 minute before closing. Connect chargebacks apply per employee: Houston / Reno ≥5 minutes late; Dallas ≥10 minutes late → −$10.<br>Snapshots and Excel include every saved employee row matching your filters. Amber cells need review. Stores without an RT-POS source support manual entries.</p>`;
  $('page-storehours').append(root);
  const sheetLink=document.createElement('a');sheetLink.href='/spreadsheet';sheetLink.className='sh-button';sheetLink.textContent='Open spreadsheet ↗';root.querySelector('.sh-hero').append(sheetLink);
  const el=id=>$('sh-'+id),{columns,text,tone}=window.storeHoursSnapshot;
  const fields=['opening_time','closing_time','camera_in','camera_out'];
  let sheet,historyPanel;
  let data=null,mode='storehours',sequence=0,syncSequence=0,syncing=false,saving=false,pageIndex=0;
  let currentDay=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Chicago',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  let start=currentDay,end=currentDay,earliest=currentDay.slice(0,8)+'01',preset='Today';
  const drafts=new Map(),key=row=>JSON.stringify([row.source_date||row.date,row.dealer,row.store_id,row.employee_key||'']);
  const dayDate=s=>new Date(s+'T12:00:00'),iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const shift=(s,n)=>{const d=dayDate(s);d.setDate(d.getDate()+n);return iso(d);};
  const dateLabel=s=>dayDate(s).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});
  function message(value='',error=false){el('message').textContent=value;el('message').hidden=!value;el('message').classList.toggle('is-error',error);}
  function params(){return new URLSearchParams({start,end,dealer:el('dealer').value,market:el('market').value,store:el('store').value,search:el('search').value.trim()});}
  function options(id,values,placeholder){const select=el(id),selected=select.value;select.replaceChildren(new Option(placeholder,''));values.forEach(v=>select.add(new Option(typeof v==='string'?v:v.name,typeof v==='string'?v:v.id)));select.value=selected;}
  function evaluate(row){
    const sec=v=>v?v.split(':').reduce((sum,v,i)=>sum+Number(v)*[3600,60,1][i],0):null;
    const [opening,closing,cin,cout]=fields.map(k=>sec(row[k]));
    const out={store_status:cin===null?'Pending camera review':'Open',opening_status:'Pending camera review',closing_status:'Pending camera review',chargeback:null};
    if(cin!==null){if(opening===null)out.opening_status='Schedule required';else{const delay=cin-opening;out.opening_status=delay>=60?'Late':'On Time';const threshold={HOUSTON:5,RENO:5,DALLAS:10}[row.market.trim().toUpperCase()];out.chargeback=row.dealer==='Connect'&&threshold&&delay>=threshold*60?-10:0;}}
    if(cout!==null){if(closing===null)out.closing_status='Schedule required';else{let close=closing,actual=cout;if(opening!==null&&close<=opening){close+=86400;if(actual<opening)actual+=86400;}out.closing_status=close-actual>=60?'Early':'On Time';}}
    return out;
  }
  function refreshDraft(draft,saved){
    const overrides=draft.cell_overrides||{};
    for(const [field] of columns)if(!fields.includes(field))draft[field]=Object.hasOwn(overrides,field)?overrides[field]:(saved.source_values&&Object.hasOwn(saved.source_values,field)?saved.source_values[field]:saved[field]);
    draft.source_date=saved.source_date||saved.date;
    const preview={...draft};['opening_time','closing_time'].forEach(field=>{if(!preview[field])preview[field]=saved['scheduled_'+field]||null;});
    Object.assign(draft,evaluate(preview));Object.assign(draft,overrides);return draft;
  }
  function updateDirty(){el('unsaved').textContent=drafts.size?`${drafts.size} unsaved review${drafts.size===1?'':'s'}`:'';el('save-all').hidden=mode!=='storehours'||!drafts.size;el('save-all').disabled=saving;el('discard').hidden=mode!=='storehours'||!drafts.size;el('discard').disabled=saving;}
  function render(){
    if(!data)return;
    const editing=mode==='storehours',rows=data.rows;
    el('store-count').textContent=new Set(rows.map(r=>r.dealer+':'+r.store_id)).size+' stores in this selection';
    el('total').textContent=rows.length;el('late').textContent=rows.filter(r=>r.opening_status==='Late').length;
    el('pending').textContent=rows.filter(r=>['Pending camera review','Schedule required'].includes(r.opening_status)).length;
    const charge=rows.reduce((s,r)=>s+(r.chargeback||0),0);el('chargebacks').textContent=text('chargeback',charge).replace('-',String.fromCharCode(8722));
    el('table').querySelector('thead').innerHTML='<tr>'+columns.map(([k,h])=>`<th scope="col"${k==='store_status'?' title="Camera evidence that the store opened"':k==='opening_status'?' title="Opening punctuality against the scheduled time"':''}>${escapeHTML(h)}</th>`).join('')+(editing?'<th scope="col">Review</th>':'')+'</tr>';
    const body=el('table').querySelector('tbody');body.replaceChildren();
    pageIndex=Math.min(pageIndex,Math.max(0,Math.ceil(rows.length/100)-1));
    rows.slice(pageIndex*100,(pageIndex+1)*100).forEach(saved=>{
      const row=editing?(drafts.get(key(saved))||saved):saved,tr=document.createElement('tr');tr.dataset.rowKey=key(saved);tr.classList.toggle('sh-dirty',drafts.has(key(saved))&&editing);
      columns.forEach(([k,heading])=>{
        const td=document.createElement('td');td.dataset.column=k;
        if(editing&&fields.includes(k)){
          const input=document.createElement('input');input.type='time';input.step='1';input.value=row[k]||'';input.setAttribute('aria-label',`${heading} — ${row.store} — ${row.date}`);
          if(k==='opening_time'||k==='closing_time')input.title=row['scheduled_'+k]?`${row.schedule_period} workbook hours: ${text(k,row['scheduled_'+k])}. Clear and save to restore this time.`:'No matching workbook schedule. Enter a time for this date.';
          input.oninput=()=>{sheet?.resetHistory();const draft={...(drafts.get(key(saved))||saved),[k]:input.value||null};refreshDraft(draft,saved);drafts.set(key(saved),draft);tr.classList.add('sh-dirty');tr.querySelector('button').disabled=saving;['store_status','opening_status','closing_status','chargeback'].forEach(col=>{const cell=tr.querySelector(`[data-column="${col}"]`);cell.textContent=text(col,draft[col]);cell.className='sh-'+tone(col,draft[col]);});updateDirty();};td.append(input);
        }else{td.textContent=text(k,row[k]);const state=tone(k,row[k]);if(state)td.className='sh-'+state;}
        if(['rt_clockin','rt_clockout'].includes(k)&&saved.source_status!=='complete')td.title=saved.source_status==='manual_only'?'This store has no connected RT-POS source. Add employees manually.':'Source not fully synced. This value may be missing or from an earlier sync.';
        if(k==='store'){td.title=row.dealer+' · '+row.store_id;const tag=document.createElement('small');tag.className='sh-dealer-tag';tag.textContent=row.dealer;td.append(tag);}
        if(Object.hasOwn(row.cell_overrides||{},k)){td.classList.add('sh-cell-corrected');td.title='Saved correction. F8 then U restores the source/default value. Source date: '+(row.source_date||row.date);}
        if(k==='employee'&&row.manual){const tag=document.createElement('small');tag.className='sh-manual-tag';tag.textContent='Manual';td.append(tag);}
        tr.append(td);
      });
      if(editing){const td=document.createElement('td'),button=document.createElement('button');button.type='button';button.className='sh-row-save';button.textContent='Save';button.disabled=!drafts.has(key(saved))||saving;button.setAttribute('aria-label','Save '+row.store+' '+row.date);button.onclick=()=>save([key(saved)]);td.append(button);tr.append(td);}
      body.append(tr);
    });
    el('empty').hidden=!!rows.length;el('table').hidden=!rows.length;
    el('page-label').textContent=rows.length?`${pageIndex*100+1}–${Math.min((pageIndex+1)*100,rows.length)} of ${rows.length} records`:'0 records';
    el('prev').disabled=pageIndex===0;el('next').disabled=(pageIndex+1)*100>=rows.length;
    const coverage=data.coverage;el('coverage').textContent=`${coverage.complete}/${coverage.expected} source days synced${data.manual_store_count?' · '+data.manual_store_count+' stores with manual entries':''}${data.updated_at?' · Updated '+new Date(data.updated_at).toLocaleString():''}${coverage.complete<coverage.expected?' · Incomplete source data':''}`;
    el('copy').disabled=el('excel').disabled=!rows.length;updateDirty();sheet?.refresh();
  }
  function updateMode(){
    const editing=mode==='storehours';$('page-'+mode).append(root);
    el('title').textContent=editing?'Store Opening / Closing Form':'Store Opening / Closing Report';
    el('subtitle').textContent=editing?'Edit any cell, review camera observations, and save corrections.':'Opening punctuality, closing checks, and assessed chargebacks.';
    el('switch').textContent=editing?'View report →':'← Edit report cells';
    el('note').hidden=!editing;el('copy').hidden=el('excel').hidden=editing;
    el('sync').hidden=currentUser?.role!=='admin';
    el('manage').hidden=currentUser?.role!=='admin';el('add').hidden=!editing;
    el('date').replaceChildren(document.createTextNode(preset==='Custom'?`${dateLabel(start)} – ${dateLabel(end)}`:preset));
    const icon=document.createElement('span');icon.textContent='▦';el('date').append(icon);
  }
  async function load(name){
    if(typeof name==='string')mode=name;
    updateMode();historyPanel?.clear();sheet?.reset();const id=++sequence;data=null;el('table').querySelector('tbody').replaceChildren();el('copy').disabled=el('excel').disabled=true;el('coverage').textContent='Loading time punches…';
    try{const result=await api('store-hours?'+params());if(id!==sequence||!currentUser)return;data=result;currentDay=result.today;earliest=result.earliest;options('dealer',result.dealers,'All dealers');options('market',result.markets,'All markets');options('store',result.stores,'All stores');render();}
    catch(error){if(id===sequence){el('coverage').textContent='Report could not be loaded.';message(error.message,true);}}
  }
  async function save(keys){
    if(saving)return;const refocus=el('table').contains(document.activeElement);sheet?.resetHistory();saving=true;const userId=currentUser?.id;render();if(refocus)sheet?.focus();
    try{for(const k of keys){const draft=drafts.get(k);if(!draft)continue;const sent={...draft};const result=await api('store-hours/review','POST',sent);if(!currentUser||currentUser.id!==userId)return;const row=data?.rows.find(r=>key(r)===k);if(row)Object.assign(row,sent,{revision:result.revision});if(drafts.get(k)===draft)drafts.delete(k);else if(drafts.has(k))drafts.get(k).revision=result.revision;}await load();if(currentUser?.id===userId)message('Camera review saved. All cell corrections are included in the report and exports.');}
    catch(error){if(currentUser?.id===userId)message(error.message,true);}
    finally{saving=false;if(currentUser?.id===userId){const restore=refocus&&(document.activeElement===document.body||el('table').contains(document.activeElement));render();if(restore)sheet?.focus();}}
  }
  el('save-all').onclick=()=>save([...drafts.keys()]);
  el('discard').onclick=()=>{drafts.clear();message('Unsaved changes discarded.');load();};
  el('switch').onclick=()=>showPage(mode==='storehours'?'storehoursreport':'storehours');
  el('reload').onclick=()=>load();
  let searchTimer;el('search').oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{pageIndex=0;load();},300);};
  el('dealer').onchange=()=>{el('market').value='';el('store').value='';pageIndex=0;load();};
  el('market').onchange=()=>{el('store').value='';pageIndex=0;load();};el('store').onchange=()=>{pageIndex=0;load();};
  el('prev').onclick=()=>{pageIndex--;render();};el('next').onclick=()=>{pageIndex++;render();};
  el('excel').onclick=()=>{if(data)location.assign('/api/internal/store-hours/export?'+params());};
  const snapshot=()=>window.storeHoursSnapshot.render(data,{dealer:el('dealer').value,market:el('market').value});
  el('copy').onclick=async()=>{
    if(!data)return;el('copy').disabled=true;
    try{const canvas=snapshot(),blob=new Promise((resolve,reject)=>canvas.toBlob(b=>b?resolve(b):reject(new Error('Snapshot could not be generated. Choose fewer rows.')),'image/png'));
      if(navigator.clipboard?.write&&window.ClipboardItem){try{await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);message('Snapshot copied. Paste it into your update.');return;}catch{/* Download when image clipboard is unavailable. */}}
      const url=URL.createObjectURL(await blob),a=document.createElement('a');a.href=url;a.download=`store-opening-closing-${start}-${end}.png`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);message('Clipboard unavailable. The snapshot was downloaded.');
    }catch(error){message(error.message,true);}finally{el('copy').disabled=false;}
  };
  el('sync').onclick=async()=>{
    if(syncing||currentUser?.role!=='admin')return;const id=++syncSequence;syncing=true;el('sync').disabled=true;el('sync').textContent='Syncing…';let continuation=false;
    try{let result;do{message('Fetching RT-POS time punches. Existing camera reviews are preserved.');result=await api('store-hours/refresh','POST',continuation?{continue:true}:{});if(id!==syncSequence||!currentUser)return;continuation=true;if(result.pending)message(`${result.pending} source days remain. Fetching the next batch…`);}while(result.status!=='busy'&&result.pending&&(result.workers||[]).some(w=>w.completed));
      await load();if(id!==syncSequence||!currentUser)return;
      message(result.status==='busy'?'Another time-punch sync is running. Reload after it finishes.':result.remaining?`${result.remaining} source days could not be fetched. Saved data was kept; click Sync sources to retry. ${[...new Set((result.workers||[]).map(w=>w.error).filter(Boolean))].join(', ')}`:'Time punches synced, including the last extracted date.',!!result.remaining);
    }catch(error){if(id===syncSequence)message(error.message,true);}finally{if(id===syncSequence){syncing=false;el('sync').disabled=false;el('sync').textContent='Sync sources';}}
  };

  const employeeDialog=document.createElement('dialog');employeeDialog.className='sh-editor-dialog';employeeDialog.id='sh-employee-dialog';employeeDialog.setAttribute('aria-labelledby','sh-employee-heading');
  employeeDialog.innerHTML=`<form id="sh-employee-form"><div class="sh-upload-head"><div><div class="sh-eyebrow">MANUAL ENTRY</div><h2 id="sh-employee-heading">Add an employee row</h2></div><button id="sh-employee-close" class="sh-button" type="button" aria-label="Close add employee">×</button></div><p>Add someone missing from the timesheet. Their RT punches will stay empty until they appear in a future sync.</p><label>Store<select id="sh-employee-store" required></select></label><div class="sh-editor-fields"><label>Report date<input id="sh-employee-date" type="date" required></label><label>Employee name<input id="sh-employee-name" autocomplete="off" maxlength="160" placeholder="First and last name" required></label></div><p id="sh-employee-error" class="sh-form-error" role="alert" hidden></p><div class="sh-editor-footer"><button id="sh-employee-cancel" class="sh-button" type="button">Cancel</button><button id="sh-employee-submit" class="sh-button sh-primary" type="submit">Add employee</button></div></form>`;
  document.body.append(employeeDialog);
  el('add').onclick=()=>{
    if(!data?.directory?.length){message('Load the store directory before adding an employee.',true);return;}
    const select=el('employee-store');select.replaceChildren();data.directory.forEach(s=>select.add(new Option(`${s.dealer} · ${s.market} · ${s.store}`,JSON.stringify([s.dealer,s.store_id]))));
    const selected=data.directory.find(s=>s.dealer+':'+s.store_id===el('store').value)||data.directory.find(s=>s.dealer===el('dealer').value);
    if(selected)select.value=JSON.stringify([selected.dealer,selected.store_id]);select.dispatchEvent(new Event('picker-sync'));
    el('employee-date').max=currentDay;el('employee-date').value=end;el('employee-name').value='';el('employee-error').hidden=true;employeeDialog.showModal();el('employee-name').focus();
  };
  el('employee-close').onclick=el('employee-cancel').onclick=()=>employeeDialog.close();
  el('employee-form').onsubmit=async event=>{
    event.preventDefault();const userId=currentUser?.id,[dealer,store_id]=JSON.parse(el('employee-store').value),day=el('employee-date').value;
    el('employee-submit').disabled=true;el('employee-error').hidden=true;
    try{await api('store-hours/employees','POST',{dealer,store_id,date:day,employee:el('employee-name').value});if(currentUser?.id!==userId)return;employeeDialog.close();start=end=day;preset=dateLabel(day);el('search').value='';el('dealer').value=dealer;el('market').value='';el('store').replaceChildren(new Option('Selected store',dealer+':'+store_id));el('store').value=dealer+':'+store_id;pageIndex=0;await load();message('Employee added. Edit their report cells and save the review.');}
    catch(error){if(currentUser?.id===userId){el('employee-error').textContent=error.message;el('employee-error').hidden=false;}}
    finally{el('employee-submit').disabled=false;}
  };
  let uploadSequence=0,uploadPreview=null;
  el('manage').onclick=()=>{el('upload').hidden=!el('upload').hidden;};el('upload-close').onclick=()=>{el('upload').hidden=true;};
  el('file').onchange=async()=>{
    const file=el('file').files[0],id=++uploadSequence;uploadPreview=null;el('upload-preview').hidden=true;
    if(!file)return;
    if(file.size>2*1024*1024||!file.name.toLowerCase().endsWith('.xlsx')){el('upload-status').textContent='Choose an .xlsx workbook smaller than 2 MB.';return;}
    el('upload-status').textContent='Reading workbook and matching stores…';
    try{const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Could not read the file.'));reader.readAsDataURL(file);});
      const result=await api('store-hours/schedules/preview','POST',{filename:file.name,content});if(id!==uploadSequence||!currentUser)return;
      uploadPreview=result.preview_id;el('upload-status').textContent=file.name;el('upload-count').textContent=`${result.added} new ${result.added===1?'store':'stores'} · ${result.updated} existing ${result.updated===1?'store':'stores'} updated`;
      el('upload-corrections').textContent=result.corrected?`${result.corrected} Connect opening times corrected from 10:00 PM to the confirmed 10:00 AM schedule.`:'All omitted stores and saved camera reviews will be retained.';
      const body=el('upload-table').querySelector('tbody');body.replaceChildren();result.rows.forEach(row=>{const tr=document.createElement('tr');[row.action,row.dealer,row.market,row.store,...['weekday','saturday','sunday'].map(p=>`${text('opening_time',row.schedules[p].opening_time)} – ${text('closing_time',row.schedules[p].closing_time)}`)].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td);});body.append(tr);});el('upload-preview').hidden=false;
    }catch(error){if(id===uploadSequence)el('upload-status').textContent=error.message;}
  };
  el('upload-apply').onclick=async()=>{
    if(!uploadPreview)return;const id=uploadSequence;el('upload-apply').disabled=true;
    try{const result=await api('store-hours/schedules/apply','POST',{preview_id:uploadPreview});if(id!==uploadSequence||!currentUser)return;uploadPreview=null;el('upload-preview').hidden=true;el('file').value='';el('upload-status').textContent=`Saved schedules for ${result.count} stores.`;await load();message('Workbook applied. Dealers, stores, and schedules are up to date.');}
    catch(error){if(id===uploadSequence)el('upload-status').textContent=error.message;}
    finally{el('upload-apply').disabled=false;}
  };

  // Two-stage range selector: preset cards followed by one From/To calendar.
  const dialog=document.createElement('dialog');dialog.className='sh-date-dialog';dialog.id='sh-date-dialog';dialog.setAttribute('aria-label','Choose report date range');
  dialog.innerHTML=`<div class="sh-date-head"><button id="sh-date-back" class="sh-date-icon" aria-label="Back to date presets" type="button" hidden>←</button><div><small id="sh-date-eyebrow">STORE OPENING / CLOSING PERIOD</small><strong id="sh-date-heading">Choose a date range</strong></div><button id="sh-date-close" class="sh-date-icon" aria-label="Close date picker" type="button">×</button></div><div id="sh-presets" class="sh-presets"></div><div id="sh-custom" hidden><div class="sh-range-fields"><button id="sh-from" class="sh-range-field" type="button"><small>FROM</small><strong></strong></button><span>→</span><button id="sh-to" class="sh-range-field" type="button"><small>TO</small><strong></strong></button></div><div class="sh-calendar"><div class="sh-month-head"><button id="sh-month-prev" class="sh-date-icon" aria-label="Previous month" type="button">‹</button><strong id="sh-month-label"></strong><button id="sh-month-next" class="sh-date-icon" aria-label="Next month" type="button">›</button></div><div id="sh-calendar-grid" class="sh-calendar-grid"></div></div><p id="sh-date-error" class="sh-date-error" role="status" hidden></p><div class="sh-date-footer"><button id="sh-date-clear" class="sh-button" type="button">Clear</button><button id="sh-date-apply" class="sh-button sh-primary" type="button">Apply Range</button></div></div>`;
  document.body.append(dialog);let draftStart='',draftEnd='',selecting='from',month=dayDate(start);
  function closeDate(){dialog.close();el('date').focus();}
  function applyRange(a,b,label){start=a;end=b;preset=label;pageIndex=0;closeDate();load();}
  function drawPresets(){
    el('presets').hidden=false;el('custom').hidden=true;el('date-back').hidden=true;el('date-heading').textContent='Choose a date range';
    const d=dayDate(currentDay),monday=shift(currentDay,-((d.getDay()+6)%7)),monthStart=currentDay.slice(0,8)+'01',lastEnd=shift(monthStart,-1),lastStart=lastEnd.slice(0,8)+'01';
    const presets=[[`Since ${dateLabel(earliest)}`,'All available dates',earliest,currentDay],['Today','Current day',currentDay,currentDay],['Yesterday','Previous day',shift(currentDay,-1),shift(currentDay,-1)],['This Week','Monday through today',monday,currentDay],['Last Week','Previous Monday to Sunday',shift(monday,-7),shift(monday,-1)],['This Month','Month to date',monthStart,currentDay],['Last Month','Previous calendar month',lastStart,lastEnd]];
    el('presets').replaceChildren();presets.forEach(([label,sub,a,b])=>{const button=document.createElement('button');button.type='button';button.className='sh-preset'+(a===start&&b===end?' is-selected':'');button.innerHTML=`<strong>${escapeHTML(label)}</strong><small>${escapeHTML(sub)}</small><span>→</span>`;button.onclick=()=>applyRange(a,b,label);el('presets').append(button);});
    const custom=document.createElement('button');custom.type='button';custom.className='sh-preset sh-custom';custom.id='sh-custom-trigger';custom.innerHTML='<strong>⇄ &nbsp; Custom Date Range</strong><small>Select From and To on one calendar</small><span>→</span>';custom.onclick=()=>{draftStart=start;draftEnd=end;selecting='from';month=dayDate(start);month.setDate(1);el('presets').hidden=true;el('custom').hidden=false;el('date-back').hidden=false;el('date-heading').textContent='Select From and To';drawCalendar();el('from').focus();};el('presets').append(custom);
  }
  function drawCalendar(){
    el('from').querySelector('strong').textContent=draftStart?dateLabel(draftStart):'Select date';el('to').querySelector('strong').textContent=draftEnd?dateLabel(draftEnd):'Select date';
    el('from').classList.toggle('active',selecting==='from');el('to').classList.toggle('active',selecting==='to');
    el('month-label').textContent=month.toLocaleDateString('en-US',{month:'long',year:'numeric'});
    el('month-next').disabled=month.getFullYear()===dayDate(currentDay).getFullYear()&&month.getMonth()>=dayDate(currentDay).getMonth();
    const grid=el('calendar-grid');grid.replaceChildren();['SUN','MON','TUE','WED','THU','FRI','SAT'].forEach(day=>{const label=document.createElement('span');label.className='sh-weekday';label.textContent=day;grid.append(label);});
    for(let n=0;n<month.getDay();n++)grid.append(document.createElement('span'));
    const count=new Date(month.getFullYear(),month.getMonth()+1,0).getDate();
    for(let n=1;n<=count;n++){
      const value=iso(new Date(month.getFullYear(),month.getMonth(),n,12)),button=document.createElement('button');button.type='button';button.className='sh-day';button.textContent=n;button.disabled=value>currentDay;button.setAttribute('aria-label',dateLabel(value));button.setAttribute('aria-pressed',String(value===draftStart||value===draftEnd));button.classList.toggle('in-range',!!draftStart&&!!draftEnd&&value>=draftStart&&value<=draftEnd);button.classList.toggle('is-end',value===draftStart||value===draftEnd);
      button.onclick=()=>{if(selecting==='from'){draftStart=value;if(draftEnd&&draftEnd<value)draftEnd='';selecting='to';}else{if(draftStart&&value<draftStart){draftEnd=draftStart;draftStart=value;}else draftEnd=value;}el('date-error').hidden=true;drawCalendar();};grid.append(button);
    }
  }
  el('date').onclick=()=>{drawPresets();dialog.showModal();};el('date-close').onclick=closeDate;el('date-back').onclick=drawPresets;
  el('from').onclick=()=>{selecting='from';drawCalendar();};el('to').onclick=()=>{selecting='to';drawCalendar();};
  el('month-prev').onclick=()=>{month.setMonth(month.getMonth()-1);drawCalendar();};el('month-next').onclick=()=>{month.setMonth(month.getMonth()+1);drawCalendar();};
  el('date-clear').onclick=()=>{draftStart=draftEnd='';selecting='from';drawCalendar();};
  el('date-apply').onclick=()=>{if(!draftStart||!draftEnd){el('date-error').textContent='Select both From and To dates.';el('date-error').hidden=false;return;}applyRange(draftStart,draftEnd,'Custom');};
  dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)closeDate();}});
  function clear(){historyPanel?.clear();sheet?.reset();sequence++;syncSequence++;uploadSequence++;uploadPreview=null;clearTimeout(searchTimer);employeeDialog.close();el('employee-form').reset();el('employee-store').replaceChildren();el('upload').hidden=true;el('upload-preview').hidden=true;el('upload-table').querySelector('tbody').replaceChildren();el('file').value='';el('upload-status').textContent='';el('search').value='';syncing=saving=false;data=null;drafts.clear();dialog.close();el('table').querySelector('tbody').replaceChildren();['dealer','market','store'].forEach(id=>options(id,[],`All ${id==='store'?'stores':id==='market'?'markets':'dealers'}`));el('sync').disabled=false;el('sync').textContent='↻ Sync sources';start=end=currentDay;preset='Today';pageIndex=0;message();['total','late','pending','chargebacks'].forEach(id=>el(id).textContent='—');updateDirty();}
  historyPanel=window.createStoreHoursHistory({root,params,request:api});
  sheet=window.createStoreHoursGrid({
    root,table:el('table'),columns,fields,text,key,message,
    rows:()=>data?data.rows.slice(pageIndex*100,(pageIndex+1)*100).map(r=>mode==='storehours'?(drafts.get(key(r))||r):r):[],
    editing:()=>mode==='storehours',busy:()=>saving,user:()=>currentUser?.id||'',today:()=>currentDay,
    manual:(r,c)=>fields.includes(columns[c][0])||Object.hasOwn((drafts.get(key(data.rows[pageIndex*100+r]))||data.rows[pageIndex*100+r]).cell_overrides||{},columns[c][0]),
    apply(changes){
      const visible=data.rows.slice(pageIndex*100,(pageIndex+1)*100);
      for(const {r,c,value,reset} of changes){const saved=visible[r],id=key(saved),field=columns[c][0];
        const previous=drafts.get(id)||saved,draft={...previous,cell_overrides:{...(previous.cell_overrides||{})}};
        if(fields.includes(field))draft[field]=reset?null:value;
        else if(reset)delete draft.cell_overrides[field];else draft.cell_overrides[field]=value;
        refreshDraft(draft,saved);drafts.set(id,draft);
      }
      render();
    },
    save:()=>save([...drafts.keys()]),find:()=>el('search').focus(),
    download:()=>{if(data)location.assign('/api/internal/store-hours/export?'+params());},
    add:()=>el('add').click()
  });
  window.storeHoursDashboard={load,clear,snapshot,evaluate};
})();
