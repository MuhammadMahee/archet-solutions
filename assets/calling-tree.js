'use strict';
(() => {
  const el=id=>document.getElementById('tree-'+id);
  let active=[],preview=null,version=null,sequence=0;
  const message=text=>{el('message').textContent=text;el('message').hidden=!text;};
  function draw(){
    const rows=preview?preview.rows:active;
    const selected=el('dealer').value,query=el('search').value.toLowerCase();
    const filtered=rows.filter(r=>(!selected||r.dealer===selected)&&(!query||[r.dealer,r.store_id,r.store,r.market,r.dm,r.address].join(' ').toLowerCase().includes(query)));
    el('table').tBodies[0].innerHTML=filtered.map(r=>'<tr>'+[r.dealer,r.market,r.store_id,r.store,r.carrier,r.dm,r.state,r.dealer_code,r.door_code,r.sap_id,r.address,r.zip_code].map(v=>'<td>'+escapeHTML(v)+'</td>').join('')+'<td><span class="tree-match '+(r.matched?'matched':'unmatched')+'">'+(r.matched?'Matched':'Not yet found')+'</span></td></tr>').join('');
    el('empty').hidden=filtered.length>0;
    el('empty').textContent=rows.length?'No stores match your filters.':'No Calling Tree uploaded yet. An administrator can upload one above.';
    el('title').textContent=preview?'Workbook preview':'Active Calling Tree';
    el('active-summary').textContent=preview?`${filtered.length} of ${rows.length} stores · ${preview.filename} · ${preview.worksheet}`:version?`${filtered.length} of ${rows.length} stores · ${version.filename} · Updated ${new Date(version.activated_at).toLocaleString()}`:'Upload a Calling Tree to choose the stores shown in sales.';
  }
  function filters(){const selected=el('dealer').value;el('dealer').replaceChildren(new Option('All Dealers',''),...([...new Set((preview?preview.rows:active).map(r=>r.dealer))].sort().map(v=>new Option(v,v))));el('dealer').value=[...el('dealer').options].some(o=>o.value===selected)?selected:'';draw();}
  async function load(){
    const id=++sequence;el('upload').hidden=currentUser?.role!=='admin';message('');
    const result=await api('calling-tree');if(id!==sequence||!currentUser)return;
    active=result.rows;version=result.active;filters();
  }
  el('dealer').onchange=draw;el('search').oninput=draw;
  el('file').onchange=()=>{preview=null;el('preview').hidden=true;filters();message('');};
  el('form').onsubmit=async event=>{
    event.preventDefault();const file=el('file').files[0];if(!file)return;
    preview=null;el('preview').hidden=true;filters();
    if(!file.name.toLowerCase().endsWith('.xlsx')||file.size>2*1024*1024){message('Choose an .xlsx workbook smaller than 2 MB.');return;}
    const id=++sequence;el('preview-button').disabled=true;message('Reading and checking the workbook…');
    try{
      const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(new Error('The file could not be read.'));reader.readAsDataURL(file);});
      const result=await api('calling-tree/preview','POST',{filename:file.name,content,worksheet:el('sheet').value.trim()});
      if(id!==sequence||!currentUser)return;
      preview=result;el('preview').hidden=false;
      el('preview-summary').textContent=Object.entries(preview.counts).map(([dealer,count])=>`${dealer}: ${count}`).join(' · ')+` — ${preview.rows.length} stores total.`;
      el('preview-matches').textContent=preview.unmatched?`${preview.unmatched} Store IDs have not appeared in RT-POS yet. They remain in the list and show unavailable sales until matched.`:'Every Store ID matches saved RT-POS data.';
      el('dealer').value='';el('search').value='';filters();message('Preview ready. The active Calling Tree is unchanged until you apply this workbook.');
    }catch(error){message(error.message);}finally{el('preview-button').disabled=false;}
  };
  el('discard').onclick=()=>{preview=null;el('preview').hidden=true;filters();message('Preview discarded. The active Calling Tree is unchanged.');};
  el('activate').onclick=async()=>{
    if(!preview)return;el('activate').disabled=true;el('discard').disabled=true;
    try{const result=await api('calling-tree/activate','POST',{preview_id:preview.preview_id});preview=null;el('preview').hidden=true;el('form').reset();await load();message(result.message);}
    catch(error){message(error.message);}finally{el('activate').disabled=false;el('discard').disabled=false;}
  };
  window.callingTree={load,clear(){sequence++;active=[];preview=null;version=null;el('table').tBodies[0].replaceChildren();el('preview').hidden=true;el('form').reset();el('dealer').replaceChildren(new Option('All Dealers',''));el('search').value='';}};
})();
