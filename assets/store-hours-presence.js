'use strict';
window.createStoreHoursPresence=function(api){
  const {root,table,columns}=api,wrap=table.parentElement,clientId=crypto.randomUUID();
  const palette=['#1967d2','#b3261e','#9334e6','#b06000','#007b83','#b01276','#596b15','#68452d','#3949ab','#8f3d00','#00695c','#713c86'];
  let sequence=0,peers=[],colors=new Map(),lastUpdate=0,frame=0;
  const outlines=new Map(),bar=document.createElement('div');bar.className='sheet-presence';bar.id='sheet-presence';bar.setAttribute('aria-label','People using this spreadsheet');bar.hidden=true;
  root.querySelector('.sheet-header').after(bar);
  const identity=row=>JSON.stringify([row.dealer,row.store_id,row.source_date||row.date,row.employee_key||'']);
  function capture(active=true){
    const position=api.selection()?.active,row=position&&api.rows()[position.r],column=position&&columns[position.c]?.[0];
    const selection=row&&column?{dealer:row.dealer,store_id:row.store_id,source_date:row.source_date||row.date,employee_key:row.employee_key||'',column}:null;
    return {client_id:clientId,sequence:++sequence,active,selection:active?selection:null,editing:!!(active&&selection&&api.editing())};
  }
  function removeOutlines(){for(const outline of outlines.values())outline.remove();outlines.clear();}
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
    for(const person of people.values()){
      const chip=document.createElement('span');chip.className='sheet-person';chip.dataset.userId=person.user_id;chip.style.setProperty('--person-color',colors.get(person.user_id));
      const initial=document.createElement('span');initial.className='sheet-person-initial';initial.textContent=person.name.trim().slice(0,1).toUpperCase();initial.setAttribute('aria-hidden','true');
      const name=document.createElement('span');name.textContent=person.name+(person.user_id===api.user()?.id?' (you)':'');
      chip.title=person.name+(person.tabs>1?` - ${person.tabs} open tabs`:'');chip.append(initial,name);bar.append(chip);
    }
    render();
  }
  function draw(){
    frame=0;if(!api.user()){clear();return;}
    const shown=new Map(api.rows().map((row,index)=>[identity(row),index])),kept=new Set(),occupants=new Map(),viewport=wrap.getBoundingClientRect();
    for(const peer of peers){
      if(peer.client_id===clientId||!peer.selection)continue;
      const r=shown.get(identity(peer.selection)),c=columns.findIndex(column=>column[0]===peer.selection.column),cell=r===undefined?null:table.tBodies[0]?.rows[r]?.cells[c+1];
      if(c<0||!cell)continue;
      const key=peer.client_id;kept.add(key);let outline=outlines.get(key);
      if(!outline){outline=document.createElement('div');outline.className='sheet-peer-selection';outline.dataset.clientId=key;const label=document.createElement('span');label.className='sheet-peer-label';const name=document.createElement('span'),dots=document.createElement('span');dots.className='sheet-peer-dots';dots.textContent='...';label.append(name,dots);outline.append(label);wrap.append(outline);outlines.set(key,outline);}
      const label=outline.firstChild,marker=label.lastChild,caption=peer.name+(peer.user_id===api.user()?.id?' (other tab)':'');
      if(label.firstChild.textContent!==caption)label.firstChild.textContent=caption;
      marker.hidden=!peer.editing;outline.dataset.editing=String(peer.editing);outline.dataset.peerAddress=cell.dataset.address||'';
      outline.setAttribute('aria-label',`${caption} ${peer.editing?'editing':'viewing'} ${columns[c][1]}`);
      const rect=cell.getBoundingClientRect(),position=`${r}:${c}`,depth=occupants.get(position)||0;occupants.set(position,depth+1);
      const inset=(depth%4)*2;outline.style.setProperty('--person-color',colors.get(peer.user_id));
      Object.assign(outline.style,{left:(rect.left-viewport.left+wrap.scrollLeft-wrap.clientLeft+inset)+'px',top:(rect.top-viewport.top+wrap.scrollTop-wrap.clientTop+inset)+'px',width:Math.max(0,rect.width-inset*2)+'px',height:Math.max(0,rect.height-inset*2)+'px'});
      label.style.top=(depth*16)+'px';
    }
    for(const [id,outline] of outlines)if(!kept.has(id)){outline.remove();outlines.delete(id);}
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
