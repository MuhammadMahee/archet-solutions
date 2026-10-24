'use strict';
(() => {
  const $=id=>document.getElementById(id),root=$('sheet-app'),table=$('sh-table');
  const base=window.storeHoursSnapshot,columns=base.columns.map(c=>[...c]),fields=['opening_time','closing_time','camera_in','camera_out'];
  const key=r=>JSON.stringify([r.dealer,r.store_id,r.source_date||r.date,r.employee_key||'']);
  let user=null,data=null,rows=[],grid,historyPanel,saving=false,page=0,loading=false,filterRules={},sort={},popup=null;
  const drafts=new Map(),today=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Chicago',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  let start=today,end=today;
  $('sheet-from').value=start;$('sheet-to').value=end;$('sheet-from').max=$('sheet-to').max=today;
  const current=r=>drafts.get(key(r))||r,visible=()=>rows.slice(page*100,(page+1)*100).map(current);
  function message(text='',error=false){$('sheet-message').textContent=text;$('sheet-message').hidden=!text;$('sheet-message').classList.toggle('is-error',error);}
  async function api(path,method='GET',body){
    const response=await fetch('/api/internal/'+path,{method,headers:method==='GET'?{}:{'Content-Type':'application/json','X-Archet-Request':'1'},body:body===undefined?undefined:JSON.stringify(body)});
    let result;try{result=await response.json();}catch{throw new Error('The service could not respond. Please try again.');}
    if(!response.ok){if(response.status===401&&user){user=null;root.hidden=true;$('sheet-login').hidden=false;drafts.clear();grid.reset();historyPanel.clear();}throw new Error(result.message||'The request could not be completed.');}return result;
  }
  function params(withFilters=true){const p=new URLSearchParams({start,end,dealer:$('sheet-dealer').value,market:$('sheet-market').value,store:$('sheet-store').value});if(withFilters){p.set('filters',JSON.stringify(filterRules));p.set('sort',JSON.stringify(sort));p.set('search',$('sheet-search').value.trim());}return p;}
  const rawText=value=>value==null?'':String(value);
  function formatted(field,value,format={}){
    const type=format.number_format||data?.column_formats?.[field]||'auto',s=rawText(value);
    if(!s)return field.startsWith('custom_')?'':base.text(field,value);
    if(type==='text')return s;
    if(['number','currency','percent'].includes(type)){
      const stripped=s.replaceAll('$','').replaceAll(',','').replace(/%$/,'');let n=Number(stripped);if(s.endsWith('%'))n/=100;
      if(stripped.trim()&&Number.isFinite(n))return new Intl.NumberFormat('en-US',type==='currency'?{style:'currency',currency:'USD'}:type==='percent'?{style:'percent',minimumFractionDigits:2,maximumFractionDigits:2}:{minimumFractionDigits:2,maximumFractionDigits:2}).format(n);
    }
    if(type==='date'&&/^\d{4}-\d{2}-\d{2}(T.*)?$/.test(s)){const date=new Date(s.slice(0,10)+'T12:00:00');if(!isNaN(date))return date.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'});}
    if(type==='time'&&/^(\d{4}-\d{2}-\d{2}T)?\d{2}:\d{2}(:\d{2})?$/.test(s))return base.text('camera_in',s);
    return field.startsWith('custom_')?s:base.text(field,value);
  }
  function evaluate(row){
    const sec=v=>v?v.split(':').reduce((s,v,i)=>s+Number(v)*[3600,60,1][i],0):null;
    const [opening,closing,cin,cout]=fields.map(k=>sec(row[k]));
    const out={store_status:cin===null?'Pending camera review':'Open',opening_status:'Pending camera review',closing_status:'Pending camera review',chargeback:null};
    if(cin!==null){if(opening===null)out.opening_status='Schedule required';else{const delay=cin-opening;out.opening_status=delay>=60?'Late':'On Time';const threshold={HOUSTON:5,RENO:5,DALLAS:10}[row.market.trim().toUpperCase()];out.chargeback=row.dealer==='Connect'&&threshold&&delay>=threshold*60?-10:0;}}
    if(cout!==null){if(closing===null)out.closing_status='Schedule required';else{let close=closing,actual=cout;if(opening!==null&&close<=opening){close+=86400;if(actual<opening)actual+=86400;}out.closing_status=close-actual>=60?'Early':'On Time';}}
    return out;
  }
  function refreshDraft(row,saved){
    for(const [field] of base.columns)if(!fields.includes(field))row[field]=Object.hasOwn(row.cell_overrides,field)?row.cell_overrides[field]:(Object.hasOwn(saved.source_values||{},field)?saved.source_values[field]:saved[field]);
    const preview={...row};for(const field of ['opening_time','closing_time'])if(!preview[field])preview[field]=saved['scheduled_'+field]||null;
    Object.assign(row,evaluate(preview),row.cell_overrides);
    for(const [field] of columns)if(field.startsWith('custom_'))row[field]=row.custom_cells[field]??null;
  }
  function dirty(){
    $('sheet-save').disabled=saving||loading||!drafts.size;
    $('sheet-save-state').textContent=saving?'Saving…':loading?'Loading…':drafts.size?`${drafts.size} unsaved row${drafts.size===1?'':'s'}`:'All changes saved';
  }
  function options(id,values,label){const el=$(id),selected=el.value;el.replaceChildren(new Option(label,''));for(const v of values)el.add(new Option(typeof v==='string'?v:v.name,typeof v==='string'?v:v.id));el.value=selected;}
  function applyFilters(){
    const search=$('sheet-search').value.trim().toLowerCase();
    rows=(data?.rows||[]).filter(original=>{const row=current(original);return (!search||columns.some(([k])=>rawText(row[k]).toLowerCase().includes(search)))&&Object.entries(filterRules).every(([k,rule])=>rawText(row[k]).toLowerCase().includes((rule.contains||'').toLowerCase())&&(!rule.values||rule.values.includes(rawText(row[k]))));});
    if(sort.key){const value=r=>current(r)[sort.key],number=v=>Number(rawText(v).replaceAll('$','').replaceAll(',',''));
      rows.sort((a,b)=>{const av=value(a),bv=value(b);if(av==null||av==='')return bv==null||bv===''?0:1;if(bv==null||bv==='')return -1;const an=number(av),bn=number(bv),comparison=Number.isFinite(an)&&Number.isFinite(bn)?an-bn:rawText(av).localeCompare(rawText(bv),undefined,{numeric:true,sensitivity:'base'});return sort.direction==='desc'?-comparison:comparison;});}
    page=0;render();
  }
  function cellStyle(td,fmt){
    if('bold' in fmt)td.style.fontWeight=fmt.bold?'700':'400';if('italic' in fmt)td.style.fontStyle=fmt.italic?'italic':'normal';if('underline' in fmt)td.style.textDecoration=fmt.underline?'underline':'none';
    if(fmt.color)td.style.color=fmt.color;if(fmt.background)td.style.backgroundColor=fmt.background;if(fmt.align)td.style.textAlign=fmt.align;
    if(fmt.font_size)td.style.fontSize=fmt.font_size+'pt';if(fmt.wrap){td.style.whiteSpace='pre-wrap';td.style.overflowWrap='anywhere';}
  }
  function render(){
    const header=document.createElement('tr'),corner=document.createElement('th');corner.innerHTML='<button title="Select current page" aria-label="Select current page">▦</button>';corner.firstChild.onclick=()=>grid.command('all');header.append(corner);
    columns.forEach(([field,label])=>{const th=document.createElement('th');th.style.width=(['store','employee'].includes(field)?210:['store_status','opening_status','closing_status'].includes(field)?190:field==='date'?135:155)+'px';const wrapper=document.createElement('div');wrapper.className='sheet-column-label';const name=document.createElement('span');name.textContent=label;const filter=document.createElement('button');filter.textContent=sort.key===field?(sort.direction==='asc'?'↑':'↓'):'▾';filter.title='Filter and manage '+label;filter.setAttribute('aria-label','Filter '+label+' column '+field);filter.classList.toggle('is-filtered',!!filterRules[field]);filter.onclick=e=>{e.stopPropagation();columnMenu(field);};wrapper.append(name,filter);th.append(wrapper);header.append(th);});
    table.tHead.replaceChildren(header);table.tBodies[0].replaceChildren();page=Math.min(page,Math.max(0,Math.ceil(rows.length/100)-1));
    for(const [i,row] of visible().entries()){
      const tr=document.createElement('tr'),number=document.createElement('th');number.scope='row';number.textContent=page*100+i+1;number.dataset.sheetRow=i;tr.append(number);
      for(const [field] of columns){const td=document.createElement('td'),fmt=row.cell_formats?.[field]||{};td.textContent=formatted(field,row[field],fmt);td.dataset.column=field;const tone=base.tone(field,row[field]);if(tone)td.classList.add('sh-'+tone);if(Object.hasOwn(row.cell_overrides||{},field))td.classList.add('sh-cell-corrected');cellStyle(td,fmt);tr.append(td);}table.tBodies[0].append(tr);
    }
    $('sheet-empty').hidden=!!rows.length;$('sheet-row-count').textContent=`${rows.length.toLocaleString()} row${rows.length===1?'':'s'}${Object.keys(filterRules).length?' · '+Object.keys(filterRules).length+' column filters':''}`;
    $('sheet-period').textContent=start===end?start:`${start} – ${end}`;$('sheet-page').textContent=rows.length?`${page*100+1}–${Math.min(rows.length,(page+1)*100)}`:'0';$('sheet-prev').disabled=page===0;$('sheet-next').disabled=(page+1)*100>=rows.length;dirty();grid?.refresh();
  }
  async function load(){
    if(loading||saving)return;if(drafts.size){message('Save or discard your changes before loading a different period.',true);return;}
    loading=true;dirty();message();grid.reset();
    try{const result=await api('store-hours/sheet?'+params(false));if(!user)return;data=result;columns.splice(0,columns.length,...data.columns);for(const field of Object.keys(filterRules))if(!columns.some(c=>c[0]===field))delete filterRules[field];if(!columns.some(c=>c[0]===sort.key))sort={};options('sheet-dealer',data.dealers,'All dealers');options('sheet-market',data.markets,'All markets');options('sheet-store',data.stores,'All stores');applyFilters();}catch(error){message(error.message,true);}finally{loading=false;dirty();}
  }
  async function save(){
    if(saving||loading||!drafts.size)return;saving=true;dirty();grid.resetHistory();
    try{for(const [id,row] of [...drafts]){const result=await api('store-hours/review','POST',row);const saved=data.rows.find(r=>key(r)===id);Object.assign(saved,row,{revision:result.revision});drafts.delete(id);}saving=false;await load();message('All changes saved, including cell formats. Version history keeps every save.');}catch(error){message(error.message,true);}finally{saving=false;dirty();}
  }
  function selectionChanged({active,cells,address}){
    const row=visible()[active.r],field=columns[active.c]?.[0],fmt=row?.cell_formats?.[field]||{};
    if(document.activeElement!==$('sheet-value'))$('sheet-value').value=rawText(row?.[field]);$('sheet-value-label').textContent=columns[active.c]?.[1]||'';
    $('sheet-selection-status').textContent=cells.length>1?`${cells.length} cells selected`:address;
    document.querySelectorAll('[data-format]').forEach(button=>button.setAttribute('aria-pressed',String(!!fmt[button.dataset.format])));
    $('sheet-number-format').value=fmt.number_format||data?.column_formats?.[field]||'auto';$('sheet-font-size').value=fmt.font_size||10;$('sheet-align').value=fmt.align||'left';$('sheet-text-color').value=fmt.color||'#202124';$('sheet-fill-color').value=fmt.background||'#ffffff';
  }
  grid=window.createStoreHoursGrid({root,table,columns,fields,gutter:true,text:(k,v)=>formatted(k,v),key,message,rows:visible,editing:()=>true,busy:()=>saving||loading,user:()=>user?.id||'',today:()=>data?.today||today,
    manual:(r,c)=>{const row=visible()[r],field=columns[c][0];return fields.includes(field)||Object.hasOwn(field.startsWith('custom_')?row.custom_cells||{}:row.cell_overrides||{},field);},
    cellFormat:(r,c)=>({...visible()[r]?.cell_formats?.[columns[c][0]]}),onSelection:selectionChanged,
    apply(changes){const shown=rows.slice(page*100,(page+1)*100);for(const change of changes){const {r,c,value,reset,kind}=change,saved=shown[r],previous=current(saved),field=columns[c][0],row={...previous,cell_overrides:{...previous.cell_overrides},custom_cells:{...previous.custom_cells},cell_formats:{...previous.cell_formats}};
      if(kind==='format'){if(Object.keys(value).length)row.cell_formats[field]=value;else delete row.cell_formats[field];}
      else if(field.startsWith('custom_')){if(reset)delete row.custom_cells[field];else row.custom_cells[field]=value;}
      else if(fields.includes(field))row[field]=reset?null:value;
      else if(reset)delete row.cell_overrides[field];else row.cell_overrides[field]=value;
      refreshDraft(row,saved);drafts.set(key(saved),row);}render();},save,find:()=>{setFiltersVisible(true);$('sheet-search').focus();},download:download,add:addRow});
  $('sheet-address-slot').append(root.querySelector('.sh-address-label'));
  historyPanel=window.createStoreHoursHistory({root,params:()=>params(false),request:api,columnLabels:()=>Object.fromEntries([...base.columns,...(data?.sheet?.columns||[]).map(c=>[c.id,c.name])])});
  function setFiltersVisible(visible){$('sheet-filters').hidden=!visible;$('sheet-filter-toggle').setAttribute('aria-pressed',String(visible));}
  function openDialog(title){closeMenu();$('sheet-dialog-title').textContent=title;$('sheet-dialog-content').replaceChildren();if(!$('sheet-dialog').open)$('sheet-dialog').showModal();return $('sheet-dialog-content');}
  $('sheet-dialog-close').onclick=()=>$('sheet-dialog').close();
  function button(label,action,parent,cls=''){const b=document.createElement('button');b.type='button';b.textContent=label;b.className=cls;b.onclick=action;parent.append(b);return b;}
  function inputLabel(text,parent,type='text',value=''){const label=document.createElement('label');label.textContent=text;const input=document.createElement('input');input.type=type;input.value=value;label.append(input);parent.append(label);return input;}
  function selectLabel(text,parent,options,value){const label=document.createElement('label');label.textContent=text;const select=document.createElement('select');for(const [v,t] of options)select.add(new Option(t,v));select.value=value||options[0][0];label.append(select);parent.append(label);return select;}
  function paragraph(text,parent){const p=document.createElement('p');p.textContent=text;parent.append(p);return p;}
  async function mutateColumn(payload){if(drafts.size){throw new Error('Save or discard cell edits before changing columns.');}const config=await api('store-hours/sheet/columns','POST',{...payload,revision:data.sheet.revision});data.sheet=config;await load();}
  function columnDialog(action,id){
    if(!data)return;const column=data.sheet.columns.find(c=>c.id===id),content=openDialog(action==='add'?'Add a custom column':action==='rename'?'Rename column':'Remove custom column');
    let name,format;if(action!=='delete'){name=inputLabel('Column name',content,'text',column?.name||'');name.maxLength=60;format=selectLabel('Default cell format',content,[['text','Plain text'],['auto','Automatic'],['number','Number'],['currency','Currency'],['percent','Percent'],['date','Date'],['time','Time']],column?.format||'text');}
    else paragraph(`Remove “${column.name}” from the shared sheet? Its saved values and version history are retained. Default report columns cannot be removed.`,content);
    const error=paragraph('',content);error.className='sheet-dialog-error';const actions=document.createElement('div');actions.className='sheet-dialog-actions';content.append(actions);button('Cancel',()=>$('sheet-dialog').close(),actions);
    const submit=button(action==='delete'?'Remove column':'Save column',async()=>{submit.disabled=true;try{await mutateColumn({action,id,name:name?.value,format:format?.value});$('sheet-dialog').close();message(action==='delete'?'Custom column removed. Saved history and values are retained.':'Column saved.');}catch(e){error.textContent=e.message;}finally{submit.disabled=false;}},actions,'sheet-primary');name?.focus();
  }
  function columnMenu(field){
    const label=columns.find(c=>c[0]===field)[1],rule=filterRules[field]||{},content=openDialog(label+' · column filter');
    const actions=document.createElement('div');actions.className='sheet-inline-actions';content.append(actions);
    for(const [direction,label] of [['asc','Sort A → Z / smallest'],['desc','Sort Z → A / largest']])button(label,()=>{sort={key:field,direction};$('sheet-dialog').close();applyFilters();},actions);
    const contains=inputLabel('Text contains',content,'text',rule.contains||'');contains.placeholder='Filter the entire selected period';
    const allValues=[...new Set((data.rows||[]).map(r=>rawText(current(r)[field])))].sort((a,b)=>a.localeCompare(b)),chosen=new Set(rule.values||allValues);
    const controls=document.createElement('div');controls.className='sheet-inline-actions';content.append(controls);const valueSearch=inputLabel('Find a value',content);const list=document.createElement('div');list.className='sheet-filter-values';content.append(list);
    function drawValues(){list.replaceChildren();const found=allValues.filter(v=>v.toLowerCase().includes(valueSearch.value.toLowerCase())).slice(0,200);for(const value of found){const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.checked=chosen.has(value);check.onchange=()=>check.checked?chosen.add(value):chosen.delete(value);const text=document.createElement('span');text.textContent=value===''?'(Blank)':formatted(field,value);label.append(check,text);list.append(label);}if(allValues.length>200)paragraph('Showing up to 200 matching values. Search to find more, or use Text contains.',list);}
    button('Select all',()=>{allValues.forEach(v=>chosen.add(v));drawValues();},controls);button('Clear selection',()=>{chosen.clear();drawValues();},controls);valueSearch.oninput=drawValues;drawValues();
    const footer=document.createElement('div');footer.className='sheet-dialog-actions';content.append(footer);button('Remove filter',()=>{delete filterRules[field];$('sheet-dialog').close();applyFilters();},footer);
    button('Apply filter',()=>{const next={};if(contains.value)next.contains=contains.value;if(chosen.size!==allValues.length){if(chosen.size>500){message('Use Text contains to filter more than 500 individual values.',true);return;}next.values=[...chosen];}if(Object.keys(next).length)filterRules[field]=next;else delete filterRules[field];$('sheet-dialog').close();applyFilters();},footer,'sheet-primary');
    const custom=field.startsWith('custom_');paragraph(custom?'Custom column · shared with everyone using this report.':'Default column · protected from deletion.',content);
    const manage=document.createElement('div');manage.className='sheet-inline-actions';content.append(manage);button('Rename column',()=>columnDialog('rename',field),manage).disabled=!custom;button('Delete column',()=>columnDialog('delete',field),manage).disabled=!custom;
  }
  function addRow(){
    if(!data)return;const content=openDialog('Add employee row'),stores=data.directory.map(s=>[JSON.stringify([s.dealer,s.store_id]),`${s.dealer} · ${s.market} · ${s.store}`]),store=selectLabel('Store',content,stores),date=inputLabel('Date',content,'date',end),name=inputLabel('Employee name',content);date.max=data.today;name.maxLength=160;
    const error=paragraph('',content);error.className='sheet-dialog-error';const footer=document.createElement('div');footer.className='sheet-dialog-actions';content.append(footer);const submit=button('Add row',async()=>{if(drafts.size){error.textContent='Save or discard your cell edits first.';return;}submit.disabled=true;try{const [dealer,store_id]=JSON.parse(store.value);await api('store-hours/employees','POST',{dealer,store_id,date:date.value,employee:name.value});start=end=date.value;$('sheet-from').value=start;$('sheet-to').value=end;$('sheet-dealer').value='';$('sheet-market').value='';$('sheet-store').value='';$('sheet-search').value='';filterRules={};sort={};$('sheet-dialog').close();await load();message('Employee added. Enter their times and save.');}catch(e){error.textContent=e.message;}finally{submit.disabled=false;}},footer,'sheet-primary');name.focus();
  }
  function download(){if(drafts.size){message('Save changes before downloading the sheet.',true);return;}if(data)location.assign('/api/internal/store-hours/sheet/export?'+params());}
  async function copySnapshot(){if(!data)return;if(drafts.size){message('Save changes before copying a snapshot.',true);return;}try{const canvas=base.render({...data,rows:rows.map(current)},{dealer:$('sheet-dealer').value,market:$('sheet-market').value}),blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);message('Snapshot copied.');}catch(e){message(e.message||'Could not copy the snapshot.',true);}}
  async function sync(){if(drafts.size){message('Save your edits before syncing sources.',true);return;}if(user?.role!=='admin')return;loading=true;dirty();try{let result,continuation=false;do{message('Syncing source time punches…');result=await api('store-hours/refresh','POST',continuation?{continue:true}:{});continuation=true;}while(result.status!=='busy'&&result.pending&&result.workers?.some(w=>w.completed));loading=false;await load();message(result.remaining?'Some source days could not be fetched. Saved data was kept.':'Source sync completed. Your saved corrections and formats are preserved.',!!result.remaining);}catch(e){message(e.message,true);}finally{loading=false;dirty();}}
  function closeMenu(){popup?.remove();popup=null;document.querySelectorAll('#sheet-menu button').forEach(b=>b.setAttribute('aria-expanded','false'));}
  const menus={
    File:[['Save changes',save,'Ctrl+S'],['Download Excel',download],['Copy snapshot',copySnapshot],['Reload saved sheet',load],['Back to portal',()=>location.assign('/internal#storehours')]],
    Edit:[['Undo',()=>grid.command('undo'),'Ctrl+Z'],['Redo',()=>grid.command('redo'),'Ctrl+Y'],['Copy',()=>grid.command('copy'),'Ctrl+C'],['Paste',()=>grid.command('paste'),'Ctrl+V'],['Fill down',()=>grid.command('down'),'Ctrl+D'],['Fill right',()=>grid.command('right'),'Ctrl+R'],['Use source/default',()=>grid.command('reset'),'F8 → U'],['Discard unsaved edits',()=>{drafts.clear();load();}]],
    View:[['Report filters',()=>setFiltersVisible($('sheet-filters').hidden)],['Version history',()=>historyPanel.open()],['Go to cell / range',()=>grid.command('goto'),'Ctrl+G']],
    Insert:[['Custom column',()=>columnDialog('add')],['Employee row',addRow]],
    Format:[['Bold',()=>toggleFormat('bold')],['Italic',()=>toggleFormat('italic')],['Underline',()=>toggleFormat('underline')],['Wrap text',()=>toggleFormat('wrap')],['Clear formatting',()=>grid.format(null)]],
    Data:[['Filter selected column',()=>columnMenu(columns[grid.selection().active.c][0])],['Clear all column filters',()=>{filterRules={};sort={};applyFilters();}],['Sync RT-POS sources',sync,'Admin'],['Upload store schedules',()=>location.assign('/internal#storehours')]],
    Help:[['Spreadsheet tutorial',()=>grid.command('tutorial'),'F1'],['Keyboard commands',()=>grid.command('commands'),'F8'],['Custom columns & formatting',()=>{const content=openDialog('Working with your spreadsheet');paragraph('Use + Column to add a shared custom column. Each column heading opens filters, sorting, rename, and delete. Default report columns cannot be deleted. Removed custom columns and their saved values remain in version history.',content);paragraph('Select cells or a range, then choose bold, colors, alignment, wrapping, font size, or number formats. Formatting changes display only; the cell-value bar always shows the underlying value. Custom cell values are plain data; formulas are not evaluated.',content);paragraph('Filters apply to all loaded rows in your selected period. Editing and formatting apply to the current page of up to 100 rows. Save changes before exporting, syncing, or changing the period. Column changes save immediately for everyone. Excel includes all filtered rows and active custom columns with their saved formats.',content);}]]
  };
  for(const [name,items] of Object.entries(menus)){const trigger=button(name,e=>{const was=trigger.getAttribute('aria-expanded')==='true';closeMenu();if(was)return;trigger.setAttribute('aria-expanded','true');popup=document.createElement('div');popup.className='sheet-menu-popup';popup.setAttribute('role','menu');for(const [label,action,shortcut] of items){const b=button(label,()=>{closeMenu();action();},popup);b.setAttribute('role','menuitem');if(shortcut){const small=document.createElement('small');small.textContent=shortcut;b.append(small);}if(label==='Sync RT-POS sources')b.disabled=user?.role!=='admin';}document.body.append(popup);const box=trigger.getBoundingClientRect();popup.style.left=Math.min(box.left,innerWidth-popup.offsetWidth-8)+'px';popup.style.top=box.bottom+3+'px';popup.querySelector('button')?.focus();},$('sheet-menu'));trigger.setAttribute('aria-haspopup','menu');trigger.setAttribute('aria-expanded','false');}
  document.addEventListener('pointerdown',e=>{if(popup&&!popup.contains(e.target)&&!$('sheet-menu').contains(e.target))closeMenu();});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenu();if(popup&&['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();const buttons=[...popup.querySelectorAll('button:not(:disabled)')],i=buttons.indexOf(document.activeElement);buttons[(i+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();}});
  function toggleFormat(field){const {active}=grid.selection(),fmt=visible()[active.r]?.cell_formats?.[columns[active.c][0]]||{};grid.format({[field]:!fmt[field]});}
  root.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&!e.altKey&&!e.shiftKey&&e.target.closest('td[data-grid-row]')&&!e.target.closest('input')){const format={b:'bold',i:'italic',u:'underline'}[e.key.toLowerCase()];if(format){e.preventDefault();e.stopPropagation();toggleFormat(format);}}},true);
  document.querySelectorAll('[data-format]').forEach(b=>b.onclick=()=>toggleFormat(b.dataset.format));document.querySelectorAll('[data-command]').forEach(b=>b.onclick=()=>grid.command(b.dataset.command));
  $('sheet-number-format').onchange=e=>grid.format({number_format:e.target.value});$('sheet-font-size').onchange=e=>grid.format({font_size:Number(e.target.value)});$('sheet-align').onchange=e=>grid.format({align:e.target.value});$('sheet-text-color').onchange=e=>grid.format({color:e.target.value});$('sheet-fill-color').onchange=e=>grid.format({background:e.target.value});$('sheet-clear-format').onclick=()=>grid.format(null);
  $('sheet-zoom').onchange=e=>table.style.zoom=Number(e.target.value.replace('%',''))/100;$('sheet-add-column').onclick=()=>columnDialog('add');$('sheet-add-row').onclick=addRow;$('sheet-save').onclick=save;$('sheet-filter-toggle').onclick=()=>setFiltersVisible($('sheet-filters').hidden);
  $('sheet-value').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();grid.setValue(e.target.value);grid.focus();}if(e.key==='Escape'){e.preventDefault();grid.focus();}};
  $('sheet-clear-filters').onclick=()=>{filterRules={};sort={};$('sheet-search').value='';applyFilters();};$('sheet-search').oninput=applyFilters;
  $('sheet-dealer').onchange=()=>{$('sheet-market').value='';$('sheet-store').value='';load();};$('sheet-market').onchange=()=>{$('sheet-store').value='';load();};$('sheet-store').onchange=load;
  $('sheet-apply-period').onclick=()=>{if(drafts.size){message('Save or discard your edits before changing the period.',true);return;}const from=$('sheet-from').value,to=$('sheet-to').value;if(!from||!to||from>to||to>today){message('Choose a valid period ending today or earlier.',true);return;}start=from;end=to;load();};
  $('sheet-today').onclick=()=>{$('sheet-from').value=today;$('sheet-to').value=today;$('sheet-apply-period').click();};$('sheet-month').onclick=()=>{$('sheet-from').value=today.slice(0,8)+'01';$('sheet-to').value=today;$('sheet-apply-period').click();};
  $('sheet-prev').onclick=()=>{page--;render();};$('sheet-next').onclick=()=>{page++;render();};
  async function enter(person){user=person;if(user.rest_mode){location.assign('/internal');return;}$('sheet-login').hidden=true;root.hidden=false;$('sheet-account').textContent=(person.display_name||person.username||'U').slice(0,1).toUpperCase();await load();}
  $('sheet-account').onclick=async()=>{if(drafts.size){message('Save or discard your edits before signing out.',true);return;}await api('logout','POST',{});location.reload();};
  $('sheet-login-form').onsubmit=async e=>{e.preventDefault();const submit=e.target.querySelector('button[type=submit]');submit.disabled=true;try{const result=await api('login','POST',{username:$('sheet-username').value.trim(),password:$('sheet-password').value});$('sheet-password').value='';await enter(result.user);}catch(error){$('sheet-login-error').textContent=error.message;}finally{submit.disabled=false;}};
  window.addEventListener('beforeunload',e=>{if(drafts.size){e.preventDefault();e.returnValue='';}});
  api('me').then(result=>enter(result.user)).catch(()=>{$('sheet-login').hidden=false;});
})();
