'use strict';
window.createStoreHoursHistory=function({root,params,request}){
  const button=document.createElement('button');button.type='button';button.id='sh-history';button.className='sh-button';button.textContent='Version history';
  root.querySelector('.sh-tools .sh-actions').prepend(button);
  const dialog=document.createElement('dialog');dialog.id='sh-history-dialog';dialog.className='sh-grid-dialog sh-history-dialog';dialog.setAttribute('aria-labelledby','sh-history-title');
  dialog.innerHTML='<div class="sh-grid-dialog-head"><h2 id="sh-history-title">Version history</h2><button type="button" id="sh-history-close" aria-label="Close version history">×</button></div><p>Saved changes matching your report filters. Recurring schedule changes apply across dates. Versions are append-only; portal users and administrators cannot edit or delete them.</p><p id="sh-history-start"></p><div id="sh-history-status" role="status"></div><div id="sh-history-list"></div><button type="button" id="sh-history-more" class="sh-button" hidden>Load older versions</button>';
  document.body.append(dialog);
  const get=id=>dialog.querySelector('#sh-history-'+id),list=get('list'),status=get('status');
  let generation=0,cursor=null,query=null,busy=false;
  const labels={review:'Employee review',legacy_review:'Store review',employee:'Employee entry',schedule:'Store schedule',source:'RT-POS punches'};
  const time=value=>value??'Not entered';
  const prettyDate=value=>value?new Intl.DateTimeFormat(undefined,{dateStyle:'medium',timeStyle:'short'}).format(new Date(value)):'—';
  function values(kind,data){
    if(!data)return {};
    if(kind==='review'||kind==='legacy_review'){
      const out={'Opening time override':data.opening_time??'Workbook default','Camera in':time(data.camera_in),
        'Closing time override':data.closing_time??'Workbook default','Camera out':time(data.camera_out),'Review revision':String(data.revision)};
      for(const [key,label] of [['date','Date'],['market','Market'],['store','Store'],['employee','Employee'],['store_status','Store opening status'],['rt_clockin','RT clock-in'],['opening_status','Opening punctuality'],['rt_clockout','RT clock-out'],['closing_status','Closing status'],['chargeback','Chargeback']])
        out[label+' correction']=Object.hasOwn(data.cell_overrides||{},key)?String(data.cell_overrides[key]??'Blank / pending'):'Source / automatic';
      return out;
    }
    if(kind==='employee')return {'Employee':data.employee};
    if(kind==='source')return {'RT-POS punches':data.punches.length?data.punches.map(p=>`${p.employee}: ${p.clock_in??'No Clock In'} → ${p.clock_out??'No Clock Out'}`).join('\n'):'No punches'};
    const out={'Company':data.company,'Store':data.store,'Market':data.market,'Carrier':data.carrier};
    for(const [period,label] of [['weekday','Monday–Friday'],['saturday','Saturday'],['sunday','Sunday']]){
      const hours=data.schedules?.[period]||{};out[label+' opening']=time(hours.opening_time);out[label+' closing']=time(hours.closing_time);
    }return out;
  }
  function draw(version){
    const details=document.createElement('details');details.className='sh-version';const summary=document.createElement('summary');
    const heading=document.createElement('strong');heading.textContent=`#${version.id} · ${labels[version.kind]||version.kind}${version.operation==='BASELINE'?' · Initial snapshot':version.operation==='DELETE'?' · Removed from current data':''}`;
    const identity=document.createElement('span');identity.textContent=`${version.dealer} · ${version.store} · ${version.report_date||'Recurring hours'}${version.employee&&version.employee!=='-'?' · '+version.employee:''}`;
    const author=document.createElement('small');author.textContent=`${prettyDate(version.recorded_at)} · ${version.actor_name}`;summary.append(heading,identity,author);details.append(summary);
    const before=values(version.kind,version.before_data),after=values(version.kind,version.after_data);
    const table=document.createElement('table');table.className='sh-version-values';const head=document.createElement('thead'),tr=document.createElement('tr');
    ['Field','Before','After'].forEach(label=>{const th=document.createElement('th');th.textContent=label;tr.append(th);});head.append(tr);table.append(head);const body=document.createElement('tbody');
    for(const field of new Set([...Object.keys(before),...Object.keys(after)])){if(before[field]===after[field])continue;const row=document.createElement('tr');[field,before[field]??'—',after[field]??'—'].forEach(text=>{const td=document.createElement('td');td.textContent=text;row.append(td);});body.append(row);}
    if(!body.children.length){const row=document.createElement('tr'),td=document.createElement('td');td.colSpan=3;td.textContent='Saved without a change to the displayed fields.';row.append(td);body.append(row);}
    table.append(body);const scroll=document.createElement('div');scroll.className='sh-version-scroll';scroll.append(table);details.append(scroll);list.append(details);
  }
  async function load(){
    if(busy)return;busy=true;get('more').disabled=true;status.textContent='Loading saved versions…';const id=generation;
    const search=new URLSearchParams(query);if(cursor)search.set('before',cursor);
    try{const result=await request('store-hours/history?'+search);if(id!==generation)return;
      result.versions.forEach(draw);cursor=result.next_cursor;get('more').hidden=!cursor;
      get('start').textContent=result.tracking_started?`Tracking started ${prettyDate(result.tracking_started)}. Initial snapshots preserve the data that existed then; earlier overwritten edits cannot be recovered.`:'';
      status.textContent=list.children.length?`${list.children.length} saved versions shown. Expand one to compare values.`:'No saved versions match these filters.';
    }catch(error){if(id===generation){status.textContent=error.message;get('more').hidden=false;get('more').textContent='Retry loading versions';}}
    finally{if(id===generation){busy=false;get('more').disabled=false;}}
  }
  function clear(){generation++;busy=false;cursor=null;query=null;if(dialog.open)dialog.close();list.replaceChildren();status.textContent='';get('start').textContent='';get('more').hidden=true;}
  function open(){clear();query=params().toString();get('more').textContent='Load older versions';dialog.showModal();load();}
  button.onclick=open;get('close').onclick=()=>dialog.close();get('more').onclick=load;
  dialog.addEventListener('close',()=>{generation++;busy=false;});
  return {open,clear};
};
