'use strict';
(() => {
  const $=id=>document.getElementById(id),root=$('sheet-app'),table=$('sh-table');
  const base=window.storeHoursSnapshot,columns=base.columns.map(c=>[...c]),fields=['opening_time','closing_time','camera_in','camera_out'];
  const key=r=>JSON.stringify([r.dealer,r.store_id,r.source_date||r.date,r.employee_key||'']);
  let user=null,data=null,rows=[],grid,historyPanel,saving=false,page=0,loading=false,filterRules={},sort={},popup=null;
  let autosaveTimer=null,saveFlight=null,saveFailed=false;
  let viewEpoch=0,liveBusy=false,liveDue=0,liveFailures=0,presence;
  const conflicts=new Map(),liveStatus=document.createElement('span');liveStatus.id='sheet-live-state';liveStatus.className='sheet-live-state';liveStatus.textContent='Connecting...';liveStatus.setAttribute('role','status');$('sheet-save-state').after(liveStatus);
  const resolveButton=document.createElement('button');resolveButton.id='sheet-resolve-conflict';resolveButton.textContent='Resolve conflict';resolveButton.hidden=true;resolveButton.onclick=resolveConflict;liveStatus.after(resolveButton);
  const drafts=new Map();let today=new Intl.DateTimeFormat('en-CA',{timeZone:'America/Chicago',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  const initialPeriod=new URLSearchParams(location.search);
  let start=initialPeriod.get('start')||today,end=initialPeriod.get('end')||today;
  if(!/^\d{4}-\d{2}-\d{2}$/.test(start)||!/^\d{4}-\d{2}-\d{2}$/.test(end)||start>end||end>today)start=end=today;
  $('sheet-from').value=start;$('sheet-to').value=end;$('sheet-from').max=$('sheet-to').max=today;
  const current=r=>drafts.get(key(r))||r,visible=()=>rows.slice(page*100,(page+1)*100).map(current);
  function message(text='',error=false){$('sheet-message').textContent=text;$('sheet-message').hidden=!text;$('sheet-message').classList.toggle('is-error',error);}
  async function api(path,method='GET',body,signal){
    const response=await fetch('/api/internal/'+path,{method,signal,headers:method==='GET'?{}:{'Content-Type':'application/json','X-Archet-Request':'1'},body:body===undefined?undefined:JSON.stringify(body)});
    let result;try{result=await response.json();}catch{throw new Error('The service could not respond. Please try again.');}
    if(!response.ok){if(result.code==='password_change_required'){root.hidden=true;drafts.clear();clearTimeout(autosaveTimer);presence?.clear();location.replace('/internal');throw new Error(result.message);}if(response.status===401&&user){user=null;root.hidden=true;$('sheet-login').hidden=false;drafts.clear();clearTimeout(autosaveTimer);grid.reset();historyPanel.clear();presence?.clear();$('sheet-dialog').close();closeMenu();}const error=new Error(result.message||'The request could not be completed.');error.status=response.status;throw error;}return result;
  }
  function params(withFilters=true){const p=new URLSearchParams({start,end,dealer:$('sheet-dealer').value,market:$('sheet-market').value,store:$('sheet-store').value});if(withFilters){p.set('filters',JSON.stringify(filterRules));p.set('sort',JSON.stringify(sort));p.set('search',$('sheet-search').value.trim());}return p;}
  const rawText=value=>value==null?'':String(value);
  function formatted(field,value,format={}){
    if(field==='employee')return rawText(value).toUpperCase();
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
  const equal=(a,b)=>a===b||!!(a&&b&&typeof a==='object'&&typeof b==='object'&&Array.isArray(a)===Array.isArray(b)&&Object.keys(a).length===Object.keys(b).length&&Object.keys(a).every(k=>Object.hasOwn(b,k)&&equal(a[k],b[k])));
  function mergeDraft(baseline,local,remote,preferRemote=false){
    const merged={...remote,cell_overrides:{...remote.cell_overrides},custom_cells:{...remote.custom_cells},cell_formats:{...remote.cell_formats}},changed=[];
    function merge(group,field,before,mine,theirs){
      if(equal(before,mine))return;
      const conflict=!equal(before,theirs)&&!equal(mine,theirs);
      if(conflict)changed.push({group,field,mine,theirs});
      if(conflict&&preferRemote)return;
      if(group==='time')merged[field]=local[field];
      else if(mine===undefined)delete merged[group][field];else merged[group][field]=mine;
    }
    for(const field of fields){
      const scheduled=['opening_time','closing_time'].includes(field),before=scheduled&&!baseline.schedule_overrides?.[field]?null:baseline[field];
      const mine=scheduled&&local[field]===baseline[field]&&!baseline.schedule_overrides?.[field]?null:local[field];
      const theirs=scheduled&&!remote.schedule_overrides?.[field]?null:remote[field];
      merge('time',field,before,mine,theirs);
    }
    for(const group of ['cell_overrides','custom_cells','cell_formats'])for(const field of new Set([...Object.keys(baseline[group]||{}),...Object.keys(local[group]||{})]))merge(group,field,baseline[group]?.[field],local[group]?.[field],remote[group]?.[field]);
    refreshDraft(merged,remote);return {row:merged,conflicts:changed};
  }
  async function rebaseDraft(id){
    const fresh=await api('store-hours/sheet?'+params(false));if(!user)return false;
    const baseline=data.rows.find(r=>key(r)===id),local=drafts.get(id),remote=fresh.rows.find(r=>key(r)===id);
    if(!remote)throw new Error('This row was removed or moved outside your filters. Copy your unsaved values, then use Edit > Discard unsaved edits to reload.');
    const activeFields=new Set(fresh.columns.map(c=>c[0]));
    for(const group of ['custom_cells','cell_formats'])for(const field of new Set([...Object.keys(local[group]||{}),...Object.keys(baseline[group]||{})]))if(!activeFields.has(field)&&!equal(local[group]?.[field],baseline[group]?.[field]))throw new Error('A column you edited was removed. Copy your unsaved values, then use Edit > Discard unsaved edits to reload.');
    const merged=mergeDraft(baseline,local,remote);
    if(merged.conflicts.length){conflicts.set(id,{remote});dirty();throw new Error('Someone edited the same cell. Choose Resolve conflict to review both values.');}
    Object.assign(baseline,remote);drafts.set(id,merged.row);grid.resetHistory();return true;
  }
  function resolveConflict(){
    if(!grid.finishEditing()||!conflicts.size)return;
    const [id,{remote}]=conflicts.entries().next().value,baseline=data.rows.find(r=>key(r)===id),local=drafts.get(id),merged=mergeDraft(baseline,local,remote);
    const content=openDialog('Review conflicting edits');paragraph(`${local.date} | ${local.store} | ${formatted('employee',local.employee)}`,content);
    paragraph('Both people edited the same cell. Other changes will be combined automatically. Choose which conflicting values to keep.',content);
    for(const change of merged.conflicts){const label=columns.find(c=>c[0]===change.field)?.[1]||change.field,format=v=>change.group==='cell_formats'?JSON.stringify(v||{}):v===undefined?'Source/default':formatted(change.field,v);paragraph(`${label}${change.group==='cell_formats'?' formatting':''}: Your value: ${format(change.mine)} | Latest saved value: ${format(change.theirs)}`,content);}
    const footer=document.createElement('div');footer.className='sheet-dialog-actions';content.append(footer);button('Cancel',()=>$('sheet-dialog').close(),footer);
    const choose=async preferRemote=>{const rebased=mergeDraft(baseline,drafts.get(id),remote,preferRemote);Object.assign(baseline,remote);drafts.set(id,rebased.row);conflicts.delete(id);grid.resetHistory();$('sheet-dialog').close();render();await save();};
    button('Use latest values',()=>choose(true),footer);button('Keep my values',()=>choose(false),footer,'sheet-primary');
  }
  function liveBlocked(){return loading||saving||drafts.size||grid.isEditing()||document.activeElement===$('sheet-value')||document.querySelector('dialog[open]')||popup||grid.isSelecting();}
  async function pollLive(){
    if(!user||!data||document.hidden||liveBusy||performance.now()<liveDue)return;
    if(!navigator.onLine){liveStatus.textContent='Offline - reconnecting';return;}
    liveBusy=true;const epoch=viewEpoch,query=params(false).toString(),userId=user.id;
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),30000);
    const valid=()=>user?.id===userId&&viewEpoch===epoch&&query===params(false).toString()&&!document.hidden;
    try{
      const update=await api('store-hours/sheet/presence','POST',presence.capture(),controller.signal);if(user?.id===userId&&!document.hidden)presence.update(update.peers);if(!valid())return;
      liveFailures=0;liveDue=0;
      if(update.revision===data.live_revision){liveStatus.textContent='Live';return;}
      if(liveBlocked()){liveStatus.textContent='Updates waiting';return;}
      const fresh=await api('store-hours/sheet?'+query,'GET',undefined,controller.signal);if(!valid()||liveBlocked())return;
      if(equal({...data,live_revision:null},{...fresh,live_revision:null})){data.live_revision=fresh.live_revision;liveStatus.textContent='Live';return;}
      const position=grid.selection().active,selected=visible()[position.r],selectedKey=selected&&key(selected),field=columns[position.c]?.[0],wrap=table.parentElement,left=wrap.scrollLeft,top=wrap.scrollTop,focused=table.contains(document.activeElement);
      const oldShape=JSON.stringify([columns.map(c=>c[0]),visible().map(key)]);
      data=fresh;today=fresh.today||today;columns.splice(0,columns.length,...fresh.columns);
      for(const name of Object.keys(filterRules))if(!columns.some(c=>c[0]===name))delete filterRules[name];if(!columns.some(c=>c[0]===sort.key))sort={};
      options('sheet-dealer',data.dealers,'All dealers');options('sheet-market',data.markets,'All markets');options('sheet-store',data.stores,'All stores');
      applyFilters({preservePage:true,refresh:false});const index=rows.findIndex(r=>key(r)===selectedKey);if(index>=0)page=Math.floor(index/100);
      grid.resetHistory();render();
      if(oldShape!==JSON.stringify([columns.map(c=>c[0]),visible().map(key)]))grid.restoreCell(index>=0?index%100:position.r,Math.max(0,columns.findIndex(c=>c[0]===field)));
      wrap.scrollLeft=left;wrap.scrollTop=top;if(focused)table.querySelector('.sh-cell-active')?.focus({preventScroll:true});
      liveStatus.textContent='Live';
    }catch(error){if(valid()){liveFailures++;liveDue=performance.now()+Math.min(30000,1000*2**Math.min(liveFailures,5));liveStatus.textContent='Reconnecting...';}}
    finally{clearTimeout(timeout);liveBusy=false;}
  }
  setInterval(pollLive,1000);
  for(const event of ['online','visibilitychange'])window.addEventListener(event,()=>{liveDue=0;pollLive();});
  function dirty(){
    if(!drafts.size)conflicts.clear();resolveButton.hidden=!conflicts.size;
    $('sheet-save').disabled=saving||loading||!drafts.size;
    $('sheet-save-state').textContent=loading?'Loading...':saving?'Saving...':saveFailed?'Not saved - retry':drafts.size?'Waiting to autosave...':'All changes saved';
    $('sheet-save-state').classList.toggle('is-error',saveFailed);
  }
  function scheduleAutosave(){
    clearTimeout(autosaveTimer);if(conflicts.size){dirty();return;}saveFailed=false;dirty();
    autosaveTimer=setTimeout(()=>{if(grid.isEditing()||document.activeElement===$('sheet-value')){scheduleAutosave();return;}save({quiet:true});},500);
  }
  function rememberPeriod(){
    $('sheet-from').value=start;$('sheet-to').value=end;$('sheet-from').max=$('sheet-to').max=today;
    $('sheet-period-button').textContent=start===end?start:`${start} to ${end}`;
    const url=new URL(location.href);url.searchParams.set('start',start);url.searchParams.set('end',end);window.history.replaceState(null,'',url);
  }
  function options(id,values,label){const el=$(id),selected=el.value;el.replaceChildren(new Option(label,''));for(const v of values)el.add(new Option(typeof v==='string'?v:v.name,typeof v==='string'?v:v.id));el.value=selected;}
  function applyFilters({preservePage=false,refresh=true}={}){
    const search=$('sheet-search').value.trim().toLowerCase();
    rows=(data?.rows||[]).filter(original=>{const row=current(original);return (!search||columns.some(([k])=>rawText(row[k]).toLowerCase().includes(search)))&&Object.entries(filterRules).every(([k,rule])=>rawText(row[k]).toLowerCase().includes((rule.contains||'').toLowerCase())&&(!rule.values||rule.values.includes(rawText(row[k]))));});
    if(sort.key){const value=r=>current(r)[sort.key],number=v=>Number(rawText(v).replaceAll('$','').replaceAll(',',''));
      rows.sort((a,b)=>{const av=value(a),bv=value(b);if(av==null||av==='')return bv==null||bv===''?0:1;if(bv==null||bv==='')return -1;const an=number(av),bn=number(bv),comparison=Number.isFinite(an)&&Number.isFinite(bn)?an-bn:rawText(av).localeCompare(rawText(bv),undefined,{numeric:true,sensitivity:'base'});return sort.direction==='desc'?-comparison:comparison;});}
    if(!preservePage)page=0;if(refresh)render();
  }
  function cellStyle(td,fmt){
    if(fmt.font_family)td.style.fontFamily=`"${fmt.font_family}", Arial, sans-serif`;
    for(const [side,border] of Object.entries(fmt.borders||{})){const style=border.style;td.style['border'+side[0].toUpperCase()+side.slice(1)]=style==='none'?'none':`${{thin:1,medium:2,thick:3,double:3,dashed:1,dotted:1}[style]}px ${['dashed','dotted','double'].includes(style)?style:'solid'} ${border.color}`;}
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
    viewEpoch++;
    if(loading)return false;if(!await save({quiet:true}))return false;
    loading=true;dirty();message();grid.reset();
    try{const result=await api('store-hours/sheet?'+params(false));if(!user)return false;data=result;today=result.today||today;rememberPeriod();columns.splice(0,columns.length,...data.columns);for(const field of Object.keys(filterRules))if(!columns.some(c=>c[0]===field))delete filterRules[field];if(!columns.some(c=>c[0]===sort.key))sort={};options('sheet-dealer',data.dealers,'All dealers');options('sheet-market',data.markets,'All markets');options('sheet-store',data.stores,'All stores');applyFilters();return true;}catch(error){message(error.message,true);return false;}finally{loading=false;dirty();}
  }
  function save({quiet=false}={}){
    if(!quiet&&!grid.finishEditing())return Promise.resolve(false);
    clearTimeout(autosaveTimer);
    if(saveFlight)return saveFlight;
    if(!drafts.size){conflicts.clear();return Promise.resolve(true);}
    if(conflicts.size)return Promise.resolve(false);
    if(loading)return Promise.resolve(false);
    viewEpoch++;saving=true;saveFailed=false;dirty();
    saveFlight=(async()=>{
      try{
        let rebases=0;while(drafts.size){
          const [id,sent]=drafts.entries().next().value;
          let result;try{result=await api('store-hours/review','POST',{...sent,include_row:true});}
          catch(error){if(error.status===409&&rebases++<3){if(await rebaseDraft(id))continue;return false;}throw error;}
          if(!user)return false;
          const saved=data.rows.find(r=>key(r)===id),canonical=result.row||{...sent,revision:result.revision};
          for(const [field] of columns)if(field.startsWith('custom_'))canonical[field]=canonical.custom_cells?.[field]??null;
          Object.assign(saved,canonical);
          const latest=drafts.get(id);
          if(latest===sent)drafts.delete(id);
          else if(latest){
            const merged={...latest,revision:result.revision,source_values:canonical.source_values,scheduled_opening_time:canonical.scheduled_opening_time,scheduled_closing_time:canonical.scheduled_closing_time,schedule_period:canonical.schedule_period};
            for(const field of fields)if(latest[field]===sent[field])merged[field]=canonical[field];
            refreshDraft(merged,saved);drafts.set(id,merged);
          }
        }
        if(!grid.isEditing()){const refocus=table.contains(document.activeElement);render();if(refocus)grid.focus();}
        if(!quiet)message('All changes saved. Version history keeps every autosave.');
        return true;
      }catch(error){saveFailed=true;message('Autosave could not finish. Your edits are still here. '+error.message,true);return false;}
      finally{saving=false;saveFlight=null;dirty();}
    })();
    return saveFlight;
  }
  function selectionChanged({active,cells,address}){
    presence?.render();
    const row=visible()[active.r],field=columns[active.c]?.[0],fmt=row?.cell_formats?.[field]||{};
    if(document.activeElement!==$('sheet-value'))$('sheet-value').value=rawText(row?.[field]);$('sheet-value-label').textContent=columns[active.c]?.[1]||'';
    $('sheet-selection-status').textContent=cells.length>1?`${cells.length} cells selected`:address;
    document.querySelectorAll('[data-format]').forEach(button=>button.setAttribute('aria-pressed',String(!!fmt[button.dataset.format])));
    $('sheet-font-family').value=fmt.font_family||'Calibri';
    $('sheet-number-format').value=fmt.number_format||data?.column_formats?.[field]||'auto';$('sheet-font-size').value=fmt.font_size||10;$('sheet-align').value=fmt.align||'left';$('sheet-text-color').value=fmt.color||'#202124';$('sheet-fill-color').value=fmt.background||'#ffffff';
  }
  grid=window.createStoreHoursGrid({root,table,columns,fields,gutter:true,autosave:true,moveOnPaste:true,animateSelection:true,text:(k,v)=>formatted(k,v),key,message,rows:visible,editing:()=>true,busy:()=>loading,user:()=>user?.id||'',today:()=>data?.today||today,
    manual:(r,c)=>{const row=visible()[r],field=columns[c][0];return fields.includes(field)||Object.hasOwn(field.startsWith('custom_')?row.custom_cells||{}:row.cell_overrides||{},field);},
    cellFormat:(r,c)=>({...visible()[r]?.cell_formats?.[columns[c][0]]}),onSelection:selectionChanged,
    apply(changes){const shown=rows.slice(page*100,(page+1)*100);for(const change of changes){const {r,c,value,reset,kind}=change,saved=shown[r],previous=current(saved),field=columns[c][0],row={...previous,cell_overrides:{...previous.cell_overrides},custom_cells:{...previous.custom_cells},cell_formats:{...previous.cell_formats}};
      if(kind==='format'){if(Object.keys(value).length)row.cell_formats[field]=value;else delete row.cell_formats[field];}
      else if(field.startsWith('custom_')){if(reset)delete row.custom_cells[field];else row.custom_cells[field]=value;}
      else if(fields.includes(field))row[field]=reset?null:value;
      else if(reset)delete row.cell_overrides[field];else row.cell_overrides[field]=value;
      refreshDraft(row,saved);drafts.set(key(saved),row);}render();scheduleAutosave();},save,find:()=>{setFiltersVisible(true);$('sheet-search').focus();},download:download,add:addRow});
  $('sheet-address-slot').append(root.querySelector('.sh-address-label'));
  historyPanel=window.createStoreHoursHistory({root,params:()=>params(false),request:api,columnLabels:()=>Object.fromEntries([...base.columns,...(data?.sheet?.columns||[]).map(c=>[c.id,c.name])])});
  presence=window.createStoreHoursPresence({root,table,columns,rows:visible,user:()=>user,selection:()=>grid.selection(),editing:()=>grid.isEditing()||document.activeElement===$('sheet-value')});
  function setFiltersVisible(visible){$('sheet-filters').hidden=!visible;$('sheet-filter-toggle').setAttribute('aria-pressed',String(visible));}
  function openDialog(title){closeMenu();$('sheet-dialog').classList.remove('sheet-wide');$('sheet-dialog-title').textContent=title;$('sheet-dialog-content').replaceChildren();if(!$('sheet-dialog').open)$('sheet-dialog').showModal();return $('sheet-dialog-content');}
  $('sheet-dialog-close').onclick=()=>$('sheet-dialog').close();
  function button(label,action,parent,cls=''){const b=document.createElement('button');b.type='button';b.textContent=label;b.className=cls;b.onclick=action;parent.append(b);return b;}
  function inputLabel(text,parent,type='text',value=''){const label=document.createElement('label');label.textContent=text;const input=document.createElement('input');input.type=type;input.value=value;label.append(input);parent.append(label);return input;}
  function selectLabel(text,parent,options,value){const label=document.createElement('label');label.textContent=text;const select=document.createElement('select');select.setAttribute('aria-label',text);for(const [v,t] of options)select.add(new Option(t,v));select.value=value||options[0][0];label.append(select);parent.append(label);return select;}
  function paragraph(text,parent){const p=document.createElement('p');p.textContent=text;parent.append(p);return p;}
  function borderDialog(){
    if(!rows.length||loading)return;
    const content=openDialog('Cell borders');
    const style=selectLabel('Line style',content,[['thin','Thin'],['medium','Medium'],['thick','Thick'],['dashed','Dashed'],['dotted','Dotted'],['double','Double']],'thin');
    const color=inputLabel('Border color',content,'color','#202124');
    paragraph('Apply borders to the selected cells. Outer and inner borders follow each selected range.',content);
    const choices=document.createElement('div');choices.className='sheet-border-choices';content.append(choices);
    for(const [mode,label] of [['all','All borders'],['outer','Outer borders'],['inner','Inner borders'],['horizontal','Horizontal borders'],['vertical','Vertical borders'],['top','Top border'],['bottom','Bottom border'],['left','Left border'],['right','Right border'],['none','No borders']])button(label,()=>{grid.borders(mode,{style:style.value,color:color.value});$('sheet-dialog').close();grid.focus();},choices);
  }
  function chooseDates({exporting=false}={}){
    const content=openDialog(exporting?'Download Excel':'Choose report dates'),limit=data?.today||today;
    const mode=selectLabel('Selection',content,[['day','Single day'],['range','Date range']],exporting?'range':start===end?'day':'range');
    const dates=document.createElement('div');dates.className='sheet-date-inputs';content.append(dates);
    const from=inputLabel('From date',dates,'date',start),to=inputLabel('To date',dates,'date',end);from.max=to.max=limit;
    let month=new Date(start.slice(0,7)+'-01T12:00:00'),pickingEnd=false;
    const iso=d=>`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    const header=document.createElement('div');header.className='sheet-calendar-heading';content.append(header);
    const prev=button('‹',()=>{month.setMonth(month.getMonth()-1);draw();},header);prev.setAttribute('aria-label','Previous calendar month');
    const title=document.createElement('strong');header.append(title);
    const next=button('›',()=>{month.setMonth(month.getMonth()+1);draw();},header);next.setAttribute('aria-label','Next calendar month');
    const calendar=document.createElement('div');calendar.className='sheet-calendar';content.append(calendar);
    function draw(){
      title.textContent=month.toLocaleDateString('en-US',{month:'long',year:'numeric'});next.disabled=iso(month).slice(0,7)>=limit.slice(0,7);to.disabled=mode.value==='day';calendar.replaceChildren();
      for(const day of ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']){const label=document.createElement('span');label.textContent=day;calendar.append(label);}
      for(let i=0;i<month.getDay();i++)calendar.append(document.createElement('span'));
      const count=new Date(month.getFullYear(),month.getMonth()+1,0).getDate();
      for(let n=1;n<=count;n++){
        const date=new Date(month.getFullYear(),month.getMonth(),n,12),value=iso(date);
        const day=button(String(n),()=>{if(mode.value==='day'){from.value=to.value=value;}else if(!pickingEnd){from.value=to.value=value;pickingEnd=true;}else{const first=from.value;from.value=value<first?value:first;to.value=value>first?value:first;pickingEnd=false;}draw();},calendar);
        day.disabled=value>limit;day.setAttribute('aria-label',date.toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}));day.setAttribute('aria-pressed',String(value===from.value||value===to.value));day.classList.toggle('in-range',value>=from.value&&value<=to.value);
      }
    }
    mode.onchange=()=>{pickingEnd=false;if(mode.value==='day')to.value=from.value;draw();};
    from.onchange=()=>{if(mode.value==='day')to.value=from.value;if(from.value)month=new Date(from.value.slice(0,7)+'-01T12:00:00');draw();};to.onchange=draw;
    const presets=document.createElement('div');presets.className='sheet-inline-actions';content.append(presets);
    const yesterday=new Date(limit+'T12:00:00');yesterday.setDate(yesterday.getDate()-1);
    for(const [label,a,b] of [['Today',limit,limit],['Yesterday',iso(yesterday),iso(yesterday)],['This month',limit.slice(0,8)+'01',limit]])button(label,()=>{from.value=a;to.value=b;mode.value=a===b?'day':'range';month=new Date(a.slice(0,7)+'-01T12:00:00');pickingEnd=false;draw();},presets);
    paragraph(exporting?'Choose the dates to include in Excel. Current dealer, market, store, and column filters apply. Your sheet dates stay unchanged; pending edits save before downloading.':'Choose an earlier day, or select a date range. Pending edits autosave before the period changes.',content);
    const error=paragraph('',content);error.className='sheet-dialog-error';error.setAttribute('role','alert');
    const actions=document.createElement('div');actions.className='sheet-dialog-actions';content.append(actions);button('Cancel',()=>$('sheet-dialog').close(),actions);
    const apply=button(exporting?'Download Excel':'Apply dates',async()=>{apply.disabled=true;error.textContent='';try{const a=from.value,b=mode.value==='day'?a:to.value;if(!validPeriod(a,b))throw new Error('Choose a valid period of up to 367 days ending today or earlier.');if(await (exporting?exportExcel(a,b):changePeriod(a,b)))$('sheet-dialog').close();else error.textContent='Resolve the unsaved changes or loading error before continuing.';}catch(e){error.textContent=e.message;}finally{apply.disabled=false;}},actions,'sheet-primary');apply.id='sheet-date-apply';draw();
  }
  async function mutateColumn(payload){if(!await save())throw new Error('Resolve the unsaved edits before changing columns.');const config=await api('store-hours/sheet/columns','POST',{...payload,revision:data.sheet.revision});data.sheet=config;await load();}
  function columnDialog(action,id){
    if(!data||loading)return;if(action==='delete'&&!columns.some(c=>c[0]===id&&id.startsWith('custom_'))){message('Default columns are protected. Select a custom column to delete.',true);return;}const position=grid.selection().active,column=data.sheet.columns.find(c=>c.id===id),content=openDialog(action==='add'?'Add a custom column':action==='rename'?'Rename column':'Remove custom column');
    let name,format;if(action!=='delete'){name=inputLabel('Column name',content,'text',column?.name||'');name.maxLength=60;format=selectLabel('Default cell format',content,[['text','Plain text'],['auto','Automatic'],['number','Number'],['currency','Currency'],['percent','Percent'],['date','Date'],['time','Time']],column?.format||'text');}
    else paragraph(`Remove “${column.name}” from the shared sheet? Its saved values and version history are retained. Default report columns cannot be removed.`,content);
    const error=paragraph('',content);error.className='sheet-dialog-error';const actions=document.createElement('div');actions.className='sheet-dialog-actions';content.append(actions);button('Cancel',()=>$('sheet-dialog').close(),actions);
    const submit=button(action==='delete'?'Remove column':'Save column',async()=>{submit.disabled=true;try{await mutateColumn({action,id,name:name?.value,format:format?.value});$('sheet-dialog').close();const selectedColumn=action==='add'?columns.findIndex(c=>c[1]===name.value.trim()):Math.min(position.c,columns.length-1);grid.selectCell(position.r,Math.max(0,selectedColumn));message(action==='delete'?'Custom column removed. Saved history and values are retained.':'Column saved.');}catch(e){error.textContent=e.message;}finally{submit.disabled=false;}},actions,'sheet-primary');name?.focus();
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
  const rowIdentity=row=>({dealer:row.dealer,store_id:row.store_id,date:row.date,source_date:row.source_date||row.date,employee_key:row.employee_key,revision:row.revision});
  async function changeRows(action,chosen){
    if(!await save())throw new Error('Resolve unsaved changes before changing rows.');
    const entries=chosen.map(row=>rowIdentity(data.rows.find(r=>key(r)===key(row))||row));
    await api('store-hours/rows','POST',{action,rows:entries});await load();
  }
  function removeRowsDialog(){
    if(!data||loading)return;const selection=grid.selection();
    if(selection.kind!=='rows'){message('Select entire rows using their row numbers or Shift+Space first.',true);return;}
    const shown=visible(),chosen=[...new Set(selection.cells.map(p=>p.r))].map(r=>shown[r]);
    const content=openDialog(`Remove ${chosen.length} row${chosen.length===1?'':'s'}`);
    paragraph('These rows will be removed from the sheet and reports. Their values and version history are retained. Use Edit > Restore removed rows to bring them back.',content);
    const list=document.createElement('ul');list.className='sheet-row-choices';for(const row of chosen){const item=document.createElement('li');item.textContent=`${row.date} | ${row.store} | ${formatted('employee',row.employee)}`;list.append(item);}content.append(list);
    const error=paragraph('',content);error.className='sheet-dialog-error';const footer=document.createElement('div');footer.className='sheet-dialog-actions';content.append(footer);button('Cancel',()=>$('sheet-dialog').close(),footer);
    const submit=button('Remove rows',async()=>{submit.disabled=true;try{await changeRows('remove',chosen);$('sheet-dialog').close();message('Rows removed. Restore them through Edit > Restore removed rows.');}catch(e){error.textContent=e.message;}finally{submit.disabled=false;}},footer,'sheet-primary');
  }
  async function restoreRowsDialog(){
    if(loading||!await save())return;await load();if(!user)return;
    const content=openDialog('Restore removed rows'),removed=data?.removed_rows||[],chosen=new Set();
    paragraph('Removed rows in the current date, dealer, market, and store filters. Restore up to 100 at a time.',content);
    const list=document.createElement('div');list.className='sheet-filter-values';content.append(list);
    if(!removed.length)paragraph('No removed rows in this period.',content);
    for(const row of removed){const label=document.createElement('label'),check=document.createElement('input');check.type='checkbox';check.onchange=()=>check.checked?chosen.add(row):chosen.delete(row);label.append(check,document.createTextNode(`${row.date} | ${row.store} | ${formatted('employee',row.employee)}`));list.append(label);}
    const error=paragraph('',content);error.className='sheet-dialog-error';const footer=document.createElement('div');footer.className='sheet-dialog-actions';content.append(footer);button('Cancel',()=>$('sheet-dialog').close(),footer);
    const submit=button('Restore rows',async()=>{if(!chosen.size||chosen.size>100){error.textContent='Select between 1 and 100 rows.';return;}submit.disabled=true;try{await changeRows('restore',[...chosen]);$('sheet-dialog').close();message('Rows restored with their saved values and formatting.');}catch(e){error.textContent=e.message;}finally{submit.disabled=false;}},footer,'sheet-primary');submit.disabled=!removed.length;
  }
  function addRow(context){
    if(!data)return;const content=openDialog('Add employee row'),stores=data.directory.map(s=>[JSON.stringify([s.dealer,s.store_id]),`${s.dealer} · ${s.market} · ${s.store}`]),store=selectLabel('Store',content,stores),date=inputLabel('Date',content,'date',context?.dealer?context.date:end),name=inputLabel('Employee name',content);date.max=data.today;name.maxLength=160;if(context?.dealer)store.value=JSON.stringify([context.dealer,context.store_id]);
    const error=paragraph('',content);error.className='sheet-dialog-error';const footer=document.createElement('div');footer.className='sheet-dialog-actions';content.append(footer);button('Cancel',()=>$('sheet-dialog').close(),footer);const submit=button('Add row',async()=>{submit.disabled=true;try{if(!await save())throw new Error('Resolve the unsaved edits before adding a row.');const [dealer,store_id]=JSON.parse(store.value);await api('store-hours/employees','POST',{dealer,store_id,date:date.value,employee:name.value});start=end=date.value;$('sheet-from').value=start;$('sheet-to').value=end;$('sheet-dealer').value='';$('sheet-market').value='';$('sheet-store').value='';$('sheet-search').value='';filterRules={};sort={};$('sheet-dialog').close();await load();message('Employee added. Enter their times and save.');}catch(e){error.textContent=e.message;}finally{submit.disabled=false;}},footer,'sheet-primary');name.focus();
  }
  async function uploadSchedules(){
    if(loading||!await save())return;
    const userId=user.id,content=openDialog('Upload store schedules');$('sheet-dialog').classList.add('sheet-wide');
    paragraph('Upload the Opening Timing workbook (.xlsx, up to 2 MB), including weekday/Saturday and Sunday sheets. Preview the stores and hours before applying.',content);
    const file=inputLabel('Schedule workbook',content,'file');file.accept='.xlsx';
    const status=paragraph('',content);status.setAttribute('role','status');
    const preview=document.createElement('div');preview.className='sheet-schedule-preview';content.append(preview);
    const footer=document.createElement('div');footer.className='sheet-dialog-actions';content.append(footer);
    const cancel=button('Cancel',()=>$('sheet-dialog').close(),footer);
    let previewId=null,sequence=0;
    const active=()=>user?.id===userId&&$('sheet-dialog').open&&file.isConnected;
    const apply=button('Apply schedules',async()=>{
      if(!previewId)return;apply.disabled=true;file.disabled=true;cancel.disabled=true;
      try{
        const result=await api('store-hours/schedules/apply','POST',{preview_id:previewId});previewId=null;
        if(user?.id!==userId)return;
        if(active())$('sheet-dialog').close();await load();message(`Schedules saved for ${result.count} ${result.count===1?'store':'stores'}.`);
      }catch(error){if(active()){status.textContent=error.message;status.className='sheet-dialog-error';}}
      finally{file.disabled=false;cancel.disabled=false;apply.disabled=!previewId;}
    },footer,'sheet-primary');apply.disabled=true;
    file.onchange=async()=>{
      const selected=file.files[0],requestId=++sequence;previewId=null;apply.disabled=true;preview.replaceChildren();status.className='';status.textContent='';
      if(!selected)return;
      if(selected.size>2*1024*1024||!selected.name.toLowerCase().endsWith('.xlsx')){status.textContent='Choose an .xlsx workbook no larger than 2 MB.';return;}
      status.textContent='Reading workbook and matching stores...';
      try{
        const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(new Error('Could not read the file.'));reader.readAsDataURL(selected);});
        if(!active()||requestId!==sequence)return;
        const result=await api('store-hours/schedules/preview','POST',{filename:selected.name,content:encoded});
        if(!active()||requestId!==sequence)return;
        previewId=result.preview_id;status.textContent=`${result.added} new ${result.added===1?'store':'stores'}, ${result.updated} existing ${result.updated===1?'store':'stores'} updated.`;
        paragraph(result.corrected?`${result.corrected} Connect opening times corrected from 10:00 PM to 10:00 AM. Omitted stores and saved reviews are retained.`:'Omitted stores and saved reviews are retained.',preview);
        const table=document.createElement('table'),head=table.createTHead().insertRow();table.setAttribute('aria-label','Schedule preview');
        for(const label of ['Action','Dealer','Market','Store','Monday-Friday','Saturday','Sunday']){const th=document.createElement('th');th.scope='col';th.textContent=label;head.append(th);}
        const body=table.createTBody();for(const row of result.rows){const tr=body.insertRow();for(const value of [row.action,row.dealer,row.market,row.store,...['weekday','saturday','sunday'].map(day=>`${base.text('opening_time',row.schedules[day].opening_time)} - ${base.text('closing_time',row.schedules[day].closing_time)}`)])tr.insertCell().textContent=value;}
        preview.append(table);apply.disabled=false;
      }catch(error){if(active()&&requestId===sequence){status.textContent=error.message;status.className='sheet-dialog-error';}}
    };
  }
  function download(){if(data&&!loading)chooseDates({exporting:true});}
  async function exportExcel(from,to){
    if(!await save())return false;
    const query=params();query.set('start',from);query.set('end',to);
    const response=await fetch('/api/internal/store-hours/sheet/export?'+query);
    if(!response.ok){const result=await response.json().catch(()=>({}));throw new Error(result.message||'Could not download Excel. Please try again.');}
    const url=URL.createObjectURL(await response.blob()),link=document.createElement('a');link.href=url;link.download=`opening-closing-sheet-${from}-${to}.xlsx`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);return true;
  }
  async function copySnapshot(){if(!data)return;if(!await save())return;try{const canvas=base.render({...data,rows:rows.map(current)},{dealer:$('sheet-dealer').value,market:$('sheet-market').value}),blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);message('Snapshot copied.');}catch(e){message(e.message||'Could not copy the snapshot.',true);}}
  async function sync(){if(!await save())return;loading=true;dirty();try{let result,continuation=false;do{message('Syncing source time punches…');result=await api('store-hours/refresh','POST',continuation?{continue:true}:{});continuation=true;}while(result.status!=='busy'&&result.pending&&result.workers?.some(w=>w.completed));loading=false;await load();message(result.remaining?'Some source days could not be fetched. Saved data was kept.':'Source sync completed. Your saved corrections and formats are preserved.',!!result.remaining);}catch(e){message(e.message,true);}finally{loading=false;dirty();}}
  function closeMenu(){popup?.remove();popup=null;document.querySelectorAll('#sheet-menu button').forEach(b=>b.setAttribute('aria-expanded','false'));}
  async function changePassword(){
    if(!await save())return;
    const content=openDialog('Change password'),form=document.createElement('form');content.append(form);
    const inputs={};
    for(const [key,title] of [['current','Current password'],['next','New password'],['confirm','Confirm new password']]){
      const label=document.createElement('label'),input=document.createElement('input');label.textContent=title;input.type='password';input.required=true;input.maxLength=128;input.autocomplete=key==='current'?'current-password':'new-password';if(key!=='current')input.minLength=8;label.append(input);form.append(label);inputs[key]=input;
    }
    const error=paragraph('',form);error.className='sheet-dialog-error';error.setAttribute('role','alert');
    const submit=document.createElement('button');submit.type='submit';submit.className='sheet-primary';submit.textContent='Update password';form.append(submit);
    form.onsubmit=async event=>{event.preventDefault();error.textContent='';if(inputs.next.value!==inputs.confirm.value){error.textContent='New passwords do not match.';return;}submit.disabled=true;
      try{await api('password','POST',{current_password:inputs.current.value,new_password:inputs.next.value});form.reset();user=null;presence.clear();location.assign('/internal#settings');}catch(e){error.textContent=e.message;}finally{submit.disabled=false;}
    };inputs.current.focus();
  }
  const menus={
    File:[['Save changes',save,'Ctrl+S'],['Download Excel',download],['Copy snapshot',copySnapshot],['Reload saved sheet',load],['Change password',changePassword],['Back to portal',()=>location.assign('/internal')]],
    Edit:[['Undo',()=>grid.command('undo'),'Ctrl+Z'],['Redo',()=>grid.command('redo'),'Ctrl+Y'],['Remove selected rows',removeRowsDialog],['Restore removed rows',restoreRowsDialog],['Delete selected column',()=>columnDialog('delete',columns[grid.selection().active.c]?.[0]),'Ctrl+-'],['Copy',()=>grid.command('copy'),'Ctrl+C'],['Paste',()=>grid.command('paste'),'Ctrl+V'],['Fill down',()=>grid.command('down'),'Ctrl+D'],['Fill right',()=>grid.command('right'),'Ctrl+R'],['Use source/default',()=>grid.command('reset'),'F8 → U'],['Discard unsaved edits',()=>{if(saving){message('Wait for the current save to finish.',true);return;}clearTimeout(autosaveTimer);drafts.clear();saveFailed=false;load();}]],
    View:[['Report filters',()=>setFiltersVisible($('sheet-filters').hidden)],['Version history',()=>historyPanel.open()],['Go to cell / range',()=>grid.command('goto'),'Ctrl+G']],
    Insert:[['Custom column',()=>columnDialog('add'),'Ctrl++'],['Employee row',addRow]],
    Format:[['Bold',()=>toggleFormat('bold')],['Italic',()=>toggleFormat('italic')],['Underline',()=>toggleFormat('underline')],['Wrap text',()=>toggleFormat('wrap')],['Borders',borderDialog],['Clear formatting',()=>grid.format(null)]],
    Data:[['Filter selected column',()=>columnMenu(columns[grid.selection().active.c][0])],['Clear all column filters',()=>{filterRules={};sort={};applyFilters();}],['Sync RT-POS sources',sync],['Upload store schedules',uploadSchedules]],
    Help:[['Spreadsheet tutorial',()=>grid.command('tutorial'),'F1'],['Keyboard commands',()=>grid.command('commands'),'F8'],['Custom columns & formatting',()=>{const content=openDialog('Working with your spreadsheet');paragraph('Use + Column to add a shared custom column. Each column heading opens filters, sorting, rename, and delete. Default report columns cannot be deleted. Removed custom columns and their saved values remain in version history.',content);paragraph('Select cells or a range, then choose a font family, bold, colors, alignment, wrapping, font size, borders, or number formats. Employee names display in uppercase, including clipboard copies and exports. Formatting changes display only; the cell-value bar always shows the underlying value. Custom cell values are plain data; formulas are not evaluated.',content);paragraph('People here shows who has this spreadsheet open. Each person has a matching colored cell outline and initial. Their selected ranges, including separate ranges and whole rows or columns, are highlighted in the same color. Hover over the initial or focus it with Tab to expand the full name; bold animated dots replace the initial while they edit that cell. Unfinished text stays private until saved. Indicators update every second and disappear after a disconnect.',content);paragraph('Live checks for saved changes every second. Incoming updates wait while you type or use a dialog. Different-cell edits merge automatically; Resolve conflict lets you choose between competing values for the same cell. Applying another person’s changes clears local undo history; your own autosaves preserve it.',content);paragraph('Filters apply to all loaded rows in your selected period. Editing and formatting apply to the current page of up to 100 rows. Edits autosave after you finish typing. Exports, syncs, and date changes wait for saving to finish. Column changes save immediately for everyone. Excel includes all filtered rows and active custom columns with their saved formats.',content);}]]
  };
  for(const [name,items] of Object.entries(menus)){const trigger=button(name,e=>{const was=trigger.getAttribute('aria-expanded')==='true';closeMenu();if(was)return;trigger.setAttribute('aria-expanded','true');popup=document.createElement('div');popup.className='sheet-menu-popup';popup.setAttribute('role','menu');for(const [label,action,shortcut] of items){const b=button(label,()=>{closeMenu();action();},popup);b.setAttribute('role','menuitem');if(shortcut){const small=document.createElement('small');small.textContent=shortcut;b.append(small);}}document.body.append(popup);const box=trigger.getBoundingClientRect();popup.style.left=Math.min(box.left,innerWidth-popup.offsetWidth-8)+'px';popup.style.top=box.bottom+3+'px';popup.querySelector('button')?.focus();},$('sheet-menu'));trigger.setAttribute('aria-haspopup','menu');trigger.setAttribute('aria-expanded','false');}
  document.addEventListener('pointerdown',e=>{if(popup&&!popup.contains(e.target)&&!$('sheet-menu').contains(e.target))closeMenu();});document.addEventListener('keydown',e=>{if(e.key==='Escape')closeMenu();if(popup&&['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();const buttons=[...popup.querySelectorAll('button:not(:disabled)')],i=buttons.indexOf(document.activeElement);buttons[(i+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length]?.focus();}});
  function toggleFormat(field){const {active}=grid.selection(),fmt=visible()[active.r]?.cell_formats?.[columns[active.c][0]]||{};grid.format({[field]:!fmt[field]});}
  root.addEventListener('keydown',e=>{
    if(!(e.ctrlKey||e.metaKey)||e.altKey||!e.target.closest('td[data-grid-row]')||e.target.closest('input,textarea,[contenteditable=true]'))return;
    const add=e.key==='+'||e.key==='='||e.code==='NumpadAdd',remove=e.key==='-'||e.code==='NumpadSubtract';
    if(!add&&!remove)return;e.preventDefault();e.stopPropagation();if(e.repeat||loading)return;
    const selection=grid.selection();if(selection.kind==='rows'){if(add)addRow(visible()[selection.active.r]);else removeRowsDialog();}
    else if(selection.kind==='all')message('Select row numbers or column headings to choose what to add or remove.',true);
    else columnDialog(add?'add':'delete',add?undefined:columns[selection.active.c]?.[0]);
  },true);
  root.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&!e.altKey&&!e.shiftKey&&e.target.closest('td[data-grid-row]')&&!e.target.closest('input')){const format={b:'bold',i:'italic',u:'underline'}[e.key.toLowerCase()];if(format){e.preventDefault();e.stopPropagation();toggleFormat(format);}}},true);
  document.querySelectorAll('[data-format]').forEach(b=>b.onclick=()=>toggleFormat(b.dataset.format));document.querySelectorAll('[data-command]').forEach(b=>b.onclick=()=>grid.command(b.dataset.command));
  $('sheet-font-family').onchange=e=>grid.format({font_family:e.target.value});$('sheet-borders').onclick=borderDialog;
  $('sheet-number-format').onchange=e=>grid.format({number_format:e.target.value});$('sheet-font-size').onchange=e=>grid.format({font_size:Number(e.target.value)});$('sheet-align').onchange=e=>grid.format({align:e.target.value});$('sheet-text-color').onchange=e=>grid.format({color:e.target.value});$('sheet-fill-color').onchange=e=>grid.format({background:e.target.value});$('sheet-clear-format').onclick=()=>grid.format(null);
  $('sheet-zoom').onchange=e=>{table.style.zoom=Number(e.target.value.replace('%',''))/100;grid.layout();};$('sheet-add-column').onclick=()=>columnDialog('add');$('sheet-add-row').onclick=addRow;$('sheet-save').onclick=save;$('sheet-filter-toggle').onclick=()=>setFiltersVisible($('sheet-filters').hidden);
  let formulaTarget=null;
  $('sheet-value').onfocus=()=>{const position=grid.selection().active,row=visible()[position.r];formulaTarget=row?{position,key:key(row)}:null;};
  function commitFormula(){const target=formulaTarget;formulaTarget=null;if(target&&visible()[target.position.r]&&key(visible()[target.position.r])===target.key)grid.setValue($('sheet-value').value,target.position);}
  $('sheet-value').onchange=commitFormula;
  $('sheet-value').onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();commitFormula();grid.focus();}if(e.key==='Escape'){e.preventDefault();formulaTarget=null;grid.focus();}};
  $('sheet-clear-filters').onclick=()=>{filterRules={};sort={};$('sheet-search').value='';applyFilters();};$('sheet-search').oninput=applyFilters;
  $('sheet-dealer').onchange=()=>{$('sheet-market').value='';$('sheet-store').value='';load();};$('sheet-market').onchange=()=>{$('sheet-store').value='';load();};$('sheet-store').onchange=load;
  function validPeriod(from,to){
    const limit=data?.today||today;
    return !!from&&!!to&&/^\d{4}-\d{2}-\d{2}$/.test(from)&&/^\d{4}-\d{2}-\d{2}$/.test(to)&&from<=to&&to<=limit&&Number.isFinite(Date.parse(from))&&Number.isFinite(Date.parse(to))&&(new Date(to)-new Date(from))/86400000<=366;
  }
  async function changePeriod(from,to){
    if(!validPeriod(from,to)){message('Choose a valid period of up to 367 days ending today or earlier.',true);return false;}
    if(!await save())return false;
    const previous=[start,end];start=from;end=to;rememberPeriod();const loaded=await load();if(!loaded){[start,end]=previous;rememberPeriod();grid.refresh();}return loaded;
  }
  $('sheet-apply-period').onclick=()=>changePeriod($('sheet-from').value,$('sheet-to').value);
  $('sheet-today').onclick=()=>changePeriod(today,today);
  $('sheet-month').onclick=()=>changePeriod(today.slice(0,8)+'01',today);
  $('sheet-period-button').onclick=chooseDates;
  $('sheet-prev').onclick=()=>{page--;render();};$('sheet-next').onclick=()=>{page++;render();};
  async function enter(person){user=person;if(user.must_change_password||user.rest_mode||(!person.is_owner&&person.page_access&&!person.page_access.includes('spreadsheet'))){user=null;location.replace('/internal#settings');return;}$('sheet-login').hidden=true;root.hidden=false;$('sheet-account').textContent=(person.display_name||person.username||'U').slice(0,1).toUpperCase();await load();}
  $('sheet-account').onclick=async()=>{if(!await save())return;await api('logout','POST',{});location.reload();};
  $('sheet-login-form').onsubmit=async e=>{e.preventDefault();const submit=e.target.querySelector('button[type=submit]');submit.disabled=true;try{const result=await api('login','POST',{username:$('sheet-username').value.trim(),password:$('sheet-password').value});$('sheet-password').value='';await enter(result.user);}catch(error){$('sheet-login-error').textContent=error.message;}finally{submit.disabled=false;}};
  window.addEventListener('beforeunload',e=>{if(drafts.size||grid.isEditing()){e.preventDefault();e.returnValue='';}});
  api('me').then(result=>enter(result.user)).catch(()=>{$('sheet-login').hidden=false;});
})();
