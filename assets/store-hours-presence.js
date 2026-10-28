'use strict';
window.createStoreHoursPresence=function(api){
  const {root,table,columns}=api,wrap=table.parentElement,clientId=crypto.randomUUID();
  const palette=['#1967d2','#b3261e','#9334e6','#b06000','#007b83','#b01276','#596b15','#68452d','#3949ab','#8f3d00','#00695c','#713c86'];
  let sequence=0,peers=[],colors=new Map(),lastUpdate=0,frame=0;
  const outlines=new Map(),rangeOutlines=new Map(),bar=document.createElement('div');bar.className='sheet-presence';bar.id='sheet-presence';bar.setAttribute('aria-label','People using this spreadsheet');bar.hidden=true;
  root.querySelector('.sheet-header').after(bar);
  const identity=row=>JSON.stringify([row.dealer,row.store_id,row.source_date||row.date,row.employee_key||'']);
  const rowIdentity=row=>({dealer:row.dealer,store_id:row.store_id,source_date:row.source_date||row.date,employee_key:row.employee_key||''});
  function capture(active=true){
    const state=api.selection(),rows=api.rows(),position=state?.active,row=position&&rows[position.r],column=position&&columns[position.c]?.[0];
    const selection=row&&column?{...rowIdentity(row),column}:null;
    if(active&&selection&&state.cells.length>1)selection.range={rows:rows.map(rowIdentity),columns:columns.map(c=>c[0]),areas:state.ranges.map(b=>[b.top,b.left,b.bottom,b.right])};
    return {client_id:clientId,sequence:++sequence,active,selection:active?selection:null,editing:!!(active&&selection&&api.editing())};
  }
  function removeOutlines(){for(const group of [outlines,rangeOutlines]){for(const outline of group.values())outline.remove();group.clear();}}
  function clear(){peers=[];bar.hidden=true;bar.replaceChildren();removeOutlines();}
  function update(next){
    peers=next||[];lastUpdate=performance.now();
    const people=new Map();for(const peer of peers){const entry=people.get(peer.user_id)||{...peer,tabs:0};entry.tabs++;people.set(peer.user_id,entry);}
    colors=new Map();const used=new Set();
    for(const id of [...people.keys()].sort()){
      let hash=0;for(const ch of id)hash=(hash*31+ch.charCodeAt(0))>>>0;
      let index=hash%palette.length;while(used.has(index))index++;
      used.add(index);colors.set(id,palette[index]||`hsl(${(index*137.508)%360} 65% 35%)`);
    }
    bar.replaceChildren();bar.hidden=!api.user();
    const title=document.createElement('span');title.className='sheet-presence-title';title.textContent=`People here (${people.size})`;bar.append(title);
    const mahee=person=>(person.username||person.name).trim().toLowerCase()==='mahee';
    for(const person of [...people.values()].sort((a,b)=>Number(mahee(a))-Number(mahee(b))||a.name.localeCompare(b.name)||a.user_id.localeCompare(b.user_id))){
      const chip=document.createElement('span');chip.className='sheet-person';chip.dataset.userId=person.user_id;chip.style.setProperty('--person-color',colors.get(person.user_id));
      const initial=document.createElement('span');initial.className='sheet-person-initial';initial.textContent=person.name.trim().slice(0,1).toUpperCase();initial.setAttribute('aria-hidden','true');
      const name=document.createElement('span');name.textContent=person.name+(person.user_id===api.user()?.id?' (you)':'');
      chip.title=person.name+(person.tabs>1?` - ${person.tabs} open tabs`:'');chip.append(initial,name);bar.append(chip);
    }
    render();
  }
  // Project identities into this viewer's filtered/sorted rows, then combine adjacent
  // cells into rectangles. Hidden or reordered rows never highlight unrelated cells.
  function rangeBoxes(range,shown){
    if(!range)return [];
    const rows=range.rows.map(row=>shown.get(identity(row))),cols=range.columns.map(key=>columns.findIndex(c=>c[0]===key)),points=new Map();
    for(const [top,left,bottom,right] of range.areas)for(let r=top;r<=bottom;r++){
      const local=rows[r];if(local===undefined)continue;
      const selected=points.get(local)||new Set();points.set(local,selected);
      for(let c=left;c<=right;c++)if(cols[c]>=0)selected.add(cols[c]);
    }
    const boxes=[],previous=new Map();
    for(const [r,selected] of [...points].sort((a,b)=>a[0]-b[0])){
      const sorted=[...selected].sort((a,b)=>a-b);
      for(let i=0;i<sorted.length;i++){
        const left=sorted[i];let right=left;while(sorted[i+1]===right+1)right=sorted[++i];
        const key=`${left}:${right}`,prior=previous.get(key);
        if(prior&&prior.bottom===r-1)prior.bottom=r;
        else{const box={top:r,bottom:r,left,right};boxes.push(box);previous.set(key,box);}
      }
    }
    return boxes;
  }
  function draw(){
    frame=0;if(!api.user()){clear();return;}
    const shown=new Map(api.rows().map((row,index)=>[identity(row),index])),kept=new Set(),keptRanges=new Set(),occupants=new Map(),viewport=wrap.getBoundingClientRect();
    for(const peer of peers){
      if(peer.client_id===clientId||!peer.selection)continue;
      for(const [index,box] of rangeBoxes(peer.selection.range,shown).entries()){
        const first=table.tBodies[0]?.rows[box.top]?.cells[box.left+1],last=table.tBodies[0]?.rows[box.bottom]?.cells[box.right+1];if(!first||!last)continue;
        const key=`${peer.client_id}:${index}`;keptRanges.add(key);let outline=rangeOutlines.get(key);
        if(!outline){outline=document.createElement('div');outline.className='sheet-peer-range';outline.dataset.clientId=peer.client_id;wrap.append(outline);rangeOutlines.set(key,outline);}
        const rect=first.getBoundingClientRect(),end=last.getBoundingClientRect();outline.style.setProperty('--person-color',colors.get(peer.user_id));
        outline.dataset.peerRange=`${first.dataset.address}:${last.dataset.address}`;outline.setAttribute('aria-label',`${peer.name} selected ${outline.dataset.peerRange}`);
        Object.assign(outline.style,{left:(rect.left-viewport.left+wrap.scrollLeft-wrap.clientLeft)+'px',top:(rect.top-viewport.top+wrap.scrollTop-wrap.clientTop)+'px',width:(end.right-rect.left)+'px',height:(end.bottom-rect.top)+'px'});
      }
      const r=shown.get(identity(peer.selection)),c=columns.findIndex(column=>column[0]===peer.selection.column),cell=r===undefined?null:table.tBodies[0]?.rows[r]?.cells[c+1];
      if(c<0||!cell)continue;
      const key=peer.client_id;kept.add(key);let outline=outlines.get(key);
      if(!outline){
        outline=document.createElement('div');outline.className='sheet-peer-selection';outline.dataset.clientId=key;
        const label=document.createElement('span');label.className='sheet-peer-label';label.tabIndex=0;
        const initial=document.createElement('span'),dots=document.createElement('span'),name=document.createElement('span');
        initial.className='sheet-peer-initial';dots.className='sheet-peer-dots';dots.textContent='...';name.className='sheet-peer-name';
        label.append(initial,dots,name);outline.append(label);wrap.append(outline);outlines.set(key,outline);
      }
      const label=outline.firstChild,[initial,marker,name]=label.children,caption=peer.name+(peer.user_id===api.user()?.id?' (other tab)':'');
      if(name.textContent!==caption){name.textContent=caption;initial.textContent=Array.from(peer.name.trim())[0]?.toUpperCase()||'?';label.style.setProperty('--peer-name-width',name.scrollWidth+'px');}
      initial.hidden=peer.editing;marker.hidden=!peer.editing;outline.dataset.editing=String(peer.editing);outline.dataset.peerAddress=cell.dataset.address||'';
      label.setAttribute('aria-label',`${caption}${peer.editing?' is editing':''}`);
      outline.setAttribute('aria-label',`${caption} ${peer.editing?'editing':'viewing'} ${columns[c][1]}`);
      const rect=cell.getBoundingClientRect(),position=`${r}:${c}`,depth=occupants.get(position)||0;occupants.set(position,depth+1);
      const inset=(depth%4)*2;outline.style.setProperty('--person-color',colors.get(peer.user_id));
      Object.assign(outline.style,{left:(rect.left-viewport.left+wrap.scrollLeft-wrap.clientLeft+inset)+'px',top:(rect.top-viewport.top+wrap.scrollTop-wrap.clientTop+inset)+'px',width:Math.max(0,rect.width-inset*2)+'px',height:Math.max(0,rect.height-inset*2)+'px'});
      label.style.top=(depth*16)+'px';
    }
    for(const [id,outline] of outlines)if(!kept.has(id)){outline.remove();outlines.delete(id);}
    for(const [id,outline] of rangeOutlines)if(!keptRanges.has(id)){outline.remove();rangeOutlines.delete(id);}
  }
  function render(){if(!frame)frame=requestAnimationFrame(draw);}
  function leave(){
    if(!api.user())return;
    fetch('/api/internal/store-hours/sheet/presence',{method:'POST',keepalive:true,headers:{'Content-Type':'application/json','X-Archet-Request':'1'},body:JSON.stringify(capture(false))}).catch(()=>{});clear();
  }
  wrap.addEventListener('scroll',render,{passive:true});window.addEventListener('resize',render);
  const observer=new ResizeObserver(render);observer.observe(table);observer.observe(wrap);
  setInterval(()=>{if(lastUpdate&&performance.now()-lastUpdate>15000)clear();},1000);
  window.addEventListener('pagehide',leave);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)leave();});
  return {capture,update,render,clear};
};
