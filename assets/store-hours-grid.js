'use strict';
// A bounded spreadsheet editor over the existing review drafts and save API.
window.createStoreHoursGrid = function(api) {
  const {root,table,columns,fields}=api, offset=api.gutter?1:0;let width=columns.length;
  let selectionKind='cells';
  let painted=new Map(),paintedActive=null,clipboardRange=null,finishEditor=null;
  let anchor={r:0,c:0},active={r:0,c:0},signature='',editor=null,dragging=false,undo=[],redo=[],generation=0,extraRanges=[];
  const letter=c=>{let label='';for(c++;c;c=Math.floor((c-1)/26))label=String.fromCharCode(65+(c-1)%26)+label;return label;}, address=p=>letter(p.c)+(p.r+1);
  const columnIndex=s=>[...s].reduce((n,c)=>n*26+c.charCodeAt(0)-64,0)-1;
  const writable=c=>api.editing()&&!!columns[c];
  const timeColumns=[...fields,'rt_clockin','rt_clockout'];
  const cell=(r,c)=>table.tBodies[0]?.rows[r]?.cells[c+offset];
  const value=(r,c)=>api.rows()[r]?.[columns[c][0]]??null;
  const scrollWrap=table.parentElement,reducedMotion=window.matchMedia('(prefers-reduced-motion: reduce)');
  let horizontalScroll=null,scrollFrame=0;
  function stopScroll(){cancelAnimationFrame(scrollFrame);scrollFrame=0;horizontalScroll=null;}
  function scrollHorizontally(left){
    left=Math.max(0,Math.min(left,scrollWrap.scrollWidth-scrollWrap.clientWidth));
    if(!api.animateSelection||reducedMotion.matches){stopScroll();scrollWrap.scrollLeft=left;return;}
    if(horizontalScroll&&Math.abs(horizontalScroll.left-left)<1)return;
    stopScroll();const from=scrollWrap.scrollLeft;if(Math.abs(from-left)<1)return;
    // Give newly revealed columns a visible glide; longer jumps get a little more time.
    const motion={from,left,started:performance.now(),duration:320+Math.min(120,Math.abs(left-from)*.08)};horizontalScroll=motion;
    function tick(now){
      if(horizontalScroll!==motion)return;
      const progress=Math.min(1,(now-motion.started)/motion.duration),eased=Math.sin(progress*Math.PI/2);
      scrollWrap.scrollLeft=motion.from+(motion.left-motion.from)*eased;
      if(progress<1)scrollFrame=requestAnimationFrame(tick);else stopScroll();
    }
    scrollFrame=requestAnimationFrame(tick);
  }
  function revealColumn(target){
    const viewport=scrollWrap.getBoundingClientRect(),rect=target.getBoundingClientRect(),gutter=offset?table.tHead.rows[0].cells[0].getBoundingClientRect().width:0;
    const space=scrollWrap.clientWidth-gutter,padding=api.animateSelection?Math.max(0,Math.min(32,(space-rect.width)/2)):0;
    let left=scrollWrap.scrollLeft;
    if(rect.left<viewport.left+gutter||rect.width>scrollWrap.clientWidth-gutter)left+=rect.left-viewport.left-gutter;
    else if(rect.right>viewport.left+scrollWrap.clientWidth)left+=rect.right-viewport.left-scrollWrap.clientWidth+padding;
    if(rect.left<viewport.left+gutter&&rect.width<=space)left-=padding;
    scrollHorizontally(left);
  }
  // A manual scroll or click takes control immediately; keyboard moves retarget one animation.
  scrollWrap.addEventListener('wheel',stopScroll,{passive:true});
  scrollWrap.addEventListener('touchstart',stopScroll,{passive:true});
  scrollWrap.addEventListener('pointerdown',stopScroll,true);
  reducedMotion.addEventListener('change',()=>{if(reducedMotion.matches&&horizontalScroll){const left=horizontalScroll.left;stopScroll();scrollWrap.scrollLeft=left;}});
  const selectionOutline=document.createElement('div');selectionOutline.className='sh-selection-outline';selectionOutline.hidden=true;selectionOutline.setAttribute('aria-hidden','true');
  if(api.animateSelection){table.classList.add('sh-animated-selection');table.parentElement.append(selectionOutline);}
  function drawSelection(){
    if(!api.animateSelection)return;
    const target=cell(active.r,active.c);
    if(!target||editor||!signature){selectionOutline.hidden=true;return;}
    const wrap=table.parentElement,rect=target.getBoundingClientRect(),viewport=wrap.getBoundingClientRect(),initial=selectionOutline.hidden;
    if(initial)selectionOutline.style.transition='none';
    Object.assign(selectionOutline.style,{transform:`translate3d(${rect.left-viewport.left+wrap.scrollLeft-wrap.clientLeft}px,${rect.top-viewport.top+wrap.scrollTop-wrap.clientTop}px,0)`,width:rect.width+'px',height:rect.height+'px'});
    selectionOutline.hidden=false;
    if(initial){selectionOutline.getBoundingClientRect();selectionOutline.style.transition='';}
  }
  const clipOutline=document.createElement('div');clipOutline.className='sh-clipboard-outline';clipOutline.hidden=true;clipOutline.setAttribute('aria-hidden','true');table.parentElement.append(clipOutline);
  function clearClipboard(){clipboardRange=null;clipOutline.hidden=true;}
  function drawClipboard(){
    if(!clipboardRange){clipOutline.hidden=true;return;}const b=clipboardRange.bounds,first=cell(b.top,b.left),last=cell(b.bottom,b.right);if(!first||!last){clearClipboard();return;}const wrap=table.parentElement,a=first.getBoundingClientRect(),z=last.getBoundingClientRect(),w=wrap.getBoundingClientRect();Object.assign(clipOutline.style,{left:(a.left-w.left+wrap.scrollLeft-wrap.clientLeft)+'px',top:(a.top-w.top+wrap.scrollTop-wrap.clientTop)+'px',width:(z.right-a.left)+'px',height:(z.bottom-a.top)+'px'});clipOutline.dataset.operation=clipboardRange.cut?'cut':'copy';clipOutline.hidden=false;
  }
  const bounds=()=>({top:Math.min(anchor.r,active.r),bottom:Math.max(anchor.r,active.r),left:Math.min(anchor.c,active.c),right:Math.max(anchor.c,active.c)});
  const ranges=()=>[...new Map([...extraRanges,bounds()].map(b=>[JSON.stringify(b),{...b}])).values()];
  const rangeLabel=b=>address({r:b.top,c:b.left})+(b.top===b.bottom&&b.left===b.right?'':':'+address({r:b.bottom,c:b.right}));
  const singleRange=()=>{if(!extraRanges.length)return true;notice('Choose one continuous range for copy, cut, paste, or flash fill. Separate ranges support edits, clear, and fills.',true);return false;};
  const toolbar=document.createElement('div');toolbar.className='sh-sheet-tools';
  toolbar.innerHTML=`<label class="sh-address-label">Range<input id="sh-grid-address" aria-label="Cell or range" value="A1" placeholder="G1:G10" spellcheck="false"></label><span id="sh-grid-status" role="status" aria-live="polite">Select a cell to begin</span><div class="sh-sheet-buttons"><button type="button" data-grid="undo" title="Undo (Ctrl+Z)">↶ Undo</button><button type="button" data-grid="redo" title="Redo (Ctrl+Y)">↷ Redo</button><button type="button" data-grid="down" title="Fill down (Ctrl+D)">↓ Fill down</button><button type="button" data-grid="right" title="Fill right (Ctrl+R)">→ Fill right</button><button type="button" data-grid="flash" title="Flash fill preview (Ctrl+E)">Flash fill</button><button type="button" data-grid="commands">Commands <kbd>F8</kbd></button><button type="button" data-grid="tutorial">Tutorial</button></div>`;
  table.parentElement.before(toolbar);
  const welcome=document.createElement('div');welcome.className='sh-sheet-welcome';welcome.hidden=true;
  welcome.innerHTML='<span><strong>New to this sheet?</strong> Learn cell navigation, paste, fills, and saving in five quick steps.</span><button type="button" data-grid="tutorial">Start tutorial</button><button type="button" id="sh-grid-dismiss" aria-label="Dismiss tutorial introduction">×</button>';
  toolbar.before(welcome);
  const rangeInput=toolbar.querySelector('input'),status=toolbar.querySelector('[role=status]');
  const editButton=document.createElement('button');editButton.type='button';editButton.dataset.grid='edit';editButton.textContent='Edit cell';editButton.title='Edit selected cell (F2)';toolbar.querySelector('.sh-sheet-buttons').prepend(editButton);
  const seenKey=()=>`archet.store-hours.sheet-tutorial.v1.${api.user()}`;
  const markSeen=()=>{try{localStorage.setItem(seenKey(),'seen');}catch{}welcome.hidden=true;};
  welcome.querySelector('#sh-grid-dismiss').onclick=markSeen;
  const dialog=document.createElement('dialog');dialog.id='sh-grid-dialog';dialog.className='sh-grid-dialog';
  dialog.setAttribute('aria-labelledby','sh-grid-dialog-title');
  dialog.innerHTML='<div class="sh-grid-dialog-head"><h2 id="sh-grid-dialog-title"></h2><button type="button" id="sh-grid-dialog-close" aria-label="Close spreadsheet help">×</button></div><div id="sh-grid-dialog-content"></div>';
  document.body.append(dialog);
  const title=dialog.querySelector('h2'),content=dialog.querySelector('#sh-grid-dialog-content');
  let dialogMode='',tutorialStep=0;
  dialog.querySelector('#sh-grid-dialog-close').onclick=()=>dialog.close();
  dialog.addEventListener('close',()=>{if(dialog.open)return;dialogMode='';if(root.getClientRects().length&&(document.activeElement===document.body||dialog.contains(document.activeElement)))cell(active.r,active.c)?.focus({preventScroll:true});});
  function openDialog(name,heading){cancelEdit();dialogMode=name;title.textContent=heading;content.replaceChildren();if(!dialog.open)dialog.showModal();}
  function notice(text,error=false){api.message(text,error);}
  function clamp(p){return {r:Math.max(0,Math.min(p.r,api.rows().length-1)),c:Math.max(0,Math.min(p.c,width-1))};}
  function paint(focus=false){
    const rows=api.rows(),boxes=ranges(),points=rows.length?selected():[],next=new Map();
    for(const point of points){const td=cell(point.r,point.c);if(td)next.set(td,point);}
    for(const td of painted.keys())if(!next.has(td)&&td.isConnected){td.classList.remove('sh-cell-selected','sh-range-top','sh-range-bottom','sh-range-left','sh-range-right');td.setAttribute('aria-selected','false');}
    for(const [td,{r,c}] of next){if(!painted.has(td)){td.classList.add('sh-cell-selected');td.setAttribute('aria-selected','true');}
      for(const [side,edge] of [['top','top'],['bottom','bottom'],['left','left'],['right','right']]){
        const border=boxes.some(b=>r>=b.top&&r<=b.bottom&&c>=b.left&&c<=b.right&&(side==='top'||side==='bottom'?r===b[edge]:c===b[edge]));
        td.classList.toggle('sh-range-'+side,border);
      }
    }
    const target=rows.length?cell(active.r,active.c):null;
    if(paintedActive!==target){if(paintedActive?.isConnected){paintedActive.classList.remove('sh-cell-active');paintedActive.tabIndex=-1;}if(target){target.classList.add('sh-cell-active');target.tabIndex=0;}}
    painted=next;paintedActive=target;
    if(api.animateSelection)table.dataset.singleSelection=String(points.length===1);
    if(offset){[...table.tHead.rows[0].cells].forEach((th,c)=>th.classList.toggle('sh-heading-selected',boxes.some(b=>c-offset>=b.left&&c-offset<=b.right)));[...table.tBodies[0].rows].forEach((tr,r)=>tr.cells[0].classList.toggle('sh-heading-selected',boxes.some(b=>r>=b.top&&r<=b.bottom)));}
    rangeInput.value=rows.length?boxes.map(rangeLabel).join(', '):'';
    status.textContent=rows.length?`${points.length} cell(s) in ${boxes.length} range(s) / ${columns[active.c][1]} / ${writable(active.c)?'Editable':'Read only'} / Current page`:'No cells in this selection';
    toolbar.querySelector('[data-grid=undo]').disabled=!undo.length||api.busy()||!api.editing();
    toolbar.querySelector('[data-grid=redo]').disabled=!redo.length||api.busy()||!api.editing();
    ['down','right','flash'].forEach(id=>toolbar.querySelector(`[data-grid=${id}]`).disabled=!api.editing()||api.busy()||!rows.length);
    editButton.disabled=!rows.length||!writable(active.c)||api.busy();
    api.onSelection?.({active:{...active},cells:points,address:rangeInput.value});
    if(focus&&target){target.focus({preventScroll:true});const wrap=table.parentElement,viewport=wrap.getBoundingClientRect(),rect=target.getBoundingClientRect(),header=table.tHead.getBoundingClientRect().height;
      if(rect.top<viewport.top+header)wrap.scrollTop-=viewport.top+header-rect.top;
      else if(rect.bottom>viewport.top+wrap.clientHeight)wrap.scrollTop+=rect.bottom-viewport.top-wrap.clientHeight;
      revealColumn(target);
    }
    drawClipboard();drawSelection();
  }
  function select(r,c,extend=false,add=false,focus=true){if(!api.rows().length)return;selectionKind='cells';if(add&&extraRanges.length<49)extraRanges.push(bounds());else if(!extend)extraRanges=[];active=clamp({r,c});if(!extend||add)anchor={...active};paint(focus);}
  function resetHistory(){undo=[];redo=[];toolbar.querySelector('[data-grid=undo]').disabled=true;toolbar.querySelector('[data-grid=redo]').disabled=true;}
  function reset(){selectionKind='cells';stopScroll();clearClipboard();selectionOutline.hidden=true;rangeInput.disabled=true;generation++;cancelEdit();if(dialog.open)dialog.close();content.replaceChildren();title.textContent='';resetHistory();signature='';extraRanges=[];anchor=active={r:0,c:0};welcome.hidden=true;}
  function refresh(){
    width=columns.length;const rows=api.rows();rangeInput.disabled=!rows.length;const next=JSON.stringify([api.editing(),columns.map(c=>c[0]),rows.map(api.key)]);
    if(next!==signature){selectionKind='cells';stopScroll();clearClipboard();selectionOutline.hidden=true;generation++;cancelEdit();resetHistory();extraRanges=[];anchor={r:0,c:0};active={...anchor};signature=next;}
    table.setAttribute('role','grid');table.setAttribute('aria-label','Opening and closing spreadsheet');table.setAttribute('aria-multiselectable','true');
    table.setAttribute('aria-rowcount',String(rows.length+1));table.setAttribute('aria-colcount',String(width));
    [...table.tHead.rows[0].cells].forEach((th,index)=>{const c=index-offset;if(c<0||c>=width)return;th.setAttribute('role','columnheader');const tag=document.createElement('span');tag.className='sh-column-letter';tag.textContent=letter(c);th.querySelector('.sh-column-letter')?.remove();th.prepend(tag);});
    [...table.tBodies[0].rows].forEach((tr,r)=>{tr.setAttribute('role','row');tr.setAttribute('aria-rowindex',String(r+2));tr.querySelector('.sh-row-number')?.remove();
      for(let c=0;c<width;c++){const td=tr.cells[c+offset];td.setAttribute('role','gridcell');td.dataset.gridRow=r;td.dataset.gridCol=c;td.dataset.address=letter(c)+(r+1);td.setAttribute('aria-colindex',String(c+1));td.setAttribute('aria-readonly',String(!writable(c)));
        td.classList.remove('sh-cell-selected','sh-cell-active','sh-range-top','sh-range-bottom','sh-range-left','sh-range-right');td.tabIndex=-1;td.setAttribute('aria-selected','false');if(c===0&&!offset){const number=document.createElement('span');number.className='sh-row-number';number.textContent=r+1;td.prepend(number);}
        td.querySelectorAll('input').forEach(input=>{input.tabIndex=-1;input.setAttribute('aria-label',`${address({r,c})} ${columns[c][1]} — ${rows[r].employee} — ${rows[r].store}`);});
      }
    });
    try{welcome.hidden=!rows.length||localStorage.getItem(seenKey())==='seen';}catch{welcome.hidden=!rows.length;}
    painted=new Map();paintedActive=null;active=clamp(active);anchor=clamp(anchor);paint();
  }
  function parseTime(raw){
    const s=String(raw??'').trim();if(['','-','—'].includes(s))return null;
    const match=s.match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(AM|PM)?$/i);
    if(!match)throw new Error('Use a time such as 9:02 AM, 14:30, or 09:02:00. Formulas are not supported.');
    let h=Number(match[1]);const m=Number(match[2]),sec=Number(match[3]||0),period=match[4]?.toUpperCase();
    if(m>59||sec>59||(period?(h<1||h>12):h>23))throw new Error('Enter a valid time between 00:00:00 and 23:59:59.');
    if(period)h=h%12+(period==='PM'?12:0);
    return [h,m,sec].map(n=>String(n).padStart(2,'0')).join(':');
  }
  function parseCell(r,c,raw){
    const field=columns[c][0],s=String(raw??'').trim();
    if(field.startsWith('custom_')){const value=String(raw??'');if(value.length>1000||/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(value))throw new Error('Custom cells accept text up to 1,000 characters.');return value;}
    if(timeColumns.includes(field)){if(/^No Clock (In|Out)$/i.test(s))return null;return parseTime(s.includes('T')?s.split('T')[1]:s);}
    if(field==='date'){
      let match=s.match(/^(\d{4})-(\d{2})-(\d{2})$/),y,m,d;
      if(match)[,y,m,d]=match;else if((match=s.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/)))[,m,d,y]=match;
      else if((match=s.match(/^([A-Za-z]{3}) (\d{1,2}), (\d{4})$/))){y=match[3];m=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'].findIndex(x=>x.toLowerCase()===match[1].toLowerCase())+1;d=match[2];}
      const day=new Date(Date.UTC(Number(y),Number(m)-1,Number(d)));
      if(!y||day.getUTCFullYear()!==Number(y)||day.getUTCMonth()+1!==Number(m)||day.getUTCDate()!==Number(d)||day.toISOString().slice(0,10)>api.today())throw new Error('Use a valid date ending today or earlier: YYYY-MM-DD or MM/DD/YYYY.');
      return day.toISOString().slice(0,10);
    }
    if(field==='chargeback'){
      if(!s||s.toLowerCase()==='pending')return null;
      const cleaned=s.replaceAll('$','').replaceAll(',','');
      if(!/^-?\d+(?:\.\d{1,2})?$/.test(cleaned)||Math.abs(Number(cleaned))>1000000)throw new Error('Use a chargeback amount with up to two decimals (maximum 1,000,000).');
      return Number(cleaned);
    }
    if(s.length>160||/[\x00-\x1f]/.test(s))throw new Error('Use plain text up to 160 characters.');
    return s;
  }
  function commit(changes,label){
    if(api.busy()){notice('Wait for the current save to finish.',true);return false;}
    if(!api.editing()){notice('Open the form to edit report cells.',true);return false;}
    const rows=api.rows();
    if(changes.some(x=>x.r<0||x.r>=rows.length||!writable(x.c))){notice('This range is not editable in the report view.',true);return false;}
    try{changes=changes.map(x=>x.reset||x.kind==='format'?x:{...x,value:parseCell(x.r,x.c,x.value)});}catch(error){notice('Nothing changed. '+error.message,true);return false;}
    const items=[...new Map(changes.map(x=>[`${x.r}:${x.c}`,x])).values()].map(x=>({...x,before:x.kind==='format'?api.cellFormat(x.r,x.c):value(x.r,x.c),beforeManual:api.manual(x.r,x.c)})).filter(x=>JSON.stringify(x.before)!==JSON.stringify(x.value)||(x.reset&&x.beforeManual));
    if(!items.length){notice('No values changed.');return true;}
    if(clipboardRange?.cut&&items.some(x=>clipboardRange.items.some(y=>x.r===y.r&&x.c===y.c)))clearClipboard();
    undo.push(items);if(undo.length>100)undo.shift();redo=[];api.apply(items);paint(true);notice(`${label}: ${items.length} cell(s) updated. ${api.autosave?'Autosave will save your changes.':'Review the changes, then Save changes.'}`);return true;
  }
  function history(back){
    if(api.busy()||!api.editing())return;clearClipboard();const from=back?undo:redo,to=back?redo:undo,items=from.pop();if(!items)return;
    to.push(items);api.apply(items.map(x=>({...x,value:back?x.before:x.value,reset:back?!x.beforeManual:x.reset})));paint(true);notice((back?'Last sheet edit undone. ':'Sheet edit restored. ')+(api.autosave?'Autosave will save this change.':'Save to persist this change.'));
  }
  function structuralSelection(){const boxes=ranges(),allRows=boxes.every(b=>b.left===0&&b.right===width-1),allColumns=boxes.every(b=>b.top===0&&b.bottom===api.rows().length-1);return allRows&&allColumns?(selectionKind==='rows'||selectionKind==='columns'?selectionKind:'all'):allRows?'rows':allColumns?'columns':'cells';}
  function selected(){const out=new Map();for(const b of ranges())for(let r=b.top;r<=b.bottom;r++)for(let c=b.left;c<=b.right;c++)out.set(`${r}:${c}`,{r,c});return [...out.values()];}
  function borders(mode,line){
    const points=selected(),included=new Set(points.map(p=>`${p.r}:${p.c}`));
    const changes=points.map(p=>{const format=api.cellFormat(p.r,p.c),borders={...format.borders};
      for(const [side,dr,dc] of [['top',-1,0],['bottom',1,0],['left',0,-1],['right',0,1]]){
        const inside=included.has(`${p.r+dr}:${p.c+dc}`);
        if(mode==='all'||mode==='none'||(mode==='outer'&&!inside)||(mode==='inner'&&inside)||(mode==='horizontal'&&!dc)||(mode==='vertical'&&!dr)||(mode===side&&!inside))borders[side]={...line,style:mode==='none'?'none':line.style};
      }
      return {...p,kind:'format',value:{...format,borders}};
    });commit(changes,'Borders');
  }
  function clearCells(){commit(selected().filter(x=>writable(x.c)).map(x=>({...x,value:columns[x.c][0]==='date'?value(x.r,x.c):null,reset:columns[x.c][0]==='date'})),'Clear');}
  function fill(direction){
    const changes=[];
    for(const b of ranges()){
    if(direction==='down'){
      if(b.top===b.bottom){if(!b.top){notice('Select multiple rows, or a cell below the source row.',true);return;}b.top--;}
      for(let c=b.left;c<=b.right;c++)if(writable(c))for(let r=b.top+1;r<=b.bottom;r++)changes.push({r,c,value:value(b.top,c)});
    }else{
      if(b.left===b.right){if(!b.left){notice('Select multiple columns, or a cell to the right of the source.',true);return;}b.left--;}
      if(!writable(b.left)){notice('Open the form to fill cells.',true);return;}
      for(let r=b.top;r<=b.bottom;r++)for(let c=b.left+1;c<=b.right;c++)if(writable(c))changes.push({r,c,value:value(r,b.left)});
    }
    }
    if(!changes.length){notice('Select editable cells to fill.',true);return;}commit(changes,direction==='down'?'Fill down':'Fill right');
  }
  function cancelEdit(){const input=editor;editor=null;finishEditor=null;input?.remove();}
  function beginEdit(initial){
    if(!writable(active.c)||api.busy()){notice('This cell is read only in the report view. Open the form to edit it.',true);return;}
    cancelEdit();const pos={...active},td=cell(pos.r,pos.c);if(!td)return;
    const input=document.createElement('input');input.type='text';input.className='sh-cell-editor';input.setAttribute('aria-label','Edit '+address(pos));const field=columns[pos.c][0],original=value(pos.r,pos.c);input.value=initial??(timeColumns.includes(field)&&typeof original==='string'&&original.includes('T')?original.split('T')[1]:original)??'';input.placeholder=timeColumns.includes(field)?'9:02 AM':field==='date'?'YYYY-MM-DD':'Enter value';input.spellcheck=false;editor=input;td.append(input);input.focus({preventScroll:true});if(initial===undefined)input.select();
    let closing=false;
    const finish=(all=false)=>{if(closing||editor!==input)return true;let changes;try{changes=(all?selected().filter(x=>writable(x.c)):[pos]).map(x=>({...x,value:parseCell(x.r,x.c,input.value)}));}catch(e){notice(e.message,true);input.setAttribute('aria-invalid','true');return false;}closing=true;cancelEdit();commit(changes,'Edit');drawSelection();return true;};
    finishEditor=finish;
    input.onkeydown=e=>{e.stopPropagation();const ctrl=e.ctrlKey||e.metaKey,k=e.key.toLowerCase();if(e.key==='Escape'){e.preventDefault();closing=true;cancelEdit();paint(true);}else if(e.key==='Enter'||e.key==='Tab'){e.preventDefault();if(finish(ctrl&&e.key==='Enter')&&!ctrl)move(e.key,e.shiftKey,false);}else if((ctrl&&['s','d','r','e','g','f'].includes(k))||['F8','F1'].includes(e.key)){e.preventDefault();if(finish())command(e.key==='F8'?'commands':e.key==='F1'?'tutorial':({s:'save',d:'down',r:'right',e:'flash',g:'goto',f:'find'})[k]);}};
    input.onblur=()=>{if(!finish()&&editor===input)input.focus();};
    drawSelection();
  }
  function move(key,shift,extend){
    let {r,c}=active;if(key==='ArrowLeft')c--;if(key==='ArrowRight')c++;if(key==='ArrowUp')r--;if(key==='ArrowDown')r++;
    if(key==='Enter')r+=shift?-1:1;
    if(key==='Tab'){if((shift&&r===0&&c===0)||(!shift&&r===api.rows().length-1&&c===width-1)){toolbar.querySelector('[data-grid=commands]').focus();return;}c+=shift?-1:1;if(c>=width){c=0;r++;}if(c<0){c=width-1;r--;}}
    select(r,c,extend);
  }
  const quote=s=>/[\t\n\r"]/.test(s)?'"'+s.replaceAll('"','""')+'"':s;
  function copyText(){const b=bounds(),lines=[];for(let r=b.top;r<=b.bottom;r++){const cells=[];for(let c=b.left;c<=b.right;c++){const v=value(r,c);cells.push(quote(v===null?'':fields.includes(columns[c][0])?String(v):api.text(columns[c][0],v)));}lines.push(cells.join('\t'));}return lines.join('\r\n');}
  function matrix(raw){
    if(raw.length>200000)throw new Error('Paste up to 100 rows on the current page.');
    const rows=[[]];let field='',quoted=false;
    for(let i=0;i<raw.length;i++){const char=raw[i];if(char==='"'){if(quoted&&raw[i+1]==='"'){field+='"';i++;}else if(quoted||!field)quoted=!quoted;else field+=char;}
      else if(!quoted&&(char==='\t'||char==='\n'||char==='\r')){rows.at(-1).push(field);field='';if(char!=='\t'){if(char==='\r'&&raw[i+1]==='\n')i++;rows.push([]);}}else field+=char;}
    if(quoted)throw new Error('The copied cells contain an unfinished quoted value.');rows.at(-1).push(field);
    if(rows.length>1&&rows.at(-1).length===1&&rows.at(-1)[0]==='')rows.pop();
    if(rows.length>100||rows.some(r=>r.length!==rows[0].length)||rows[0].length>width)throw new Error(`Paste a rectangular range of up to 100 rows and ${width} columns.`);return rows;
  }
  function paste(raw){
    if(!singleRange())return;
    try{const grid=matrix(raw),b=bounds(),height=grid.length,w=grid[0].length,selectedHeight=b.bottom-b.top+1,selectedWidth=b.right-b.left+1;
      const repeat=selectedHeight>=height&&selectedWidth>=w&&selectedHeight%height===0&&selectedWidth%w===0;
      const nr=repeat?selectedHeight:height,nc=repeat?selectedWidth:w,changes=[];
      if(b.top+nr>api.rows().length||b.left+nc>width)throw new Error('The paste would extend past this page. Choose a smaller range or the next page.');
      for(let r=0;r<nr;r++)for(let c=0;c<nc;c++){if(!writable(b.left+c))throw new Error(`${address({r:b.top+r,c:b.left+c})} is read only in the report view. Open the form to paste.`);changes.push({r:b.top+r,c:b.left+c,value:parseCell(b.top+r,b.left+c,grid[r%height][c%w])});}
      const moving=clipboardRange?.cut&&api.moveOnPaste&&clipboardRange.raw===raw?clipboardRange:null;
      if(moving){const targets=new Set(changes.map(x=>`${x.r}:${x.c}`));for(const x of moving.items)if(!targets.has(`${x.r}:${x.c}`))changes.unshift({...x,value:columns[x.c][0]==='date'?value(x.r,x.c):null,reset:columns[x.c][0]==='date'});}
      if(commit(changes,moving?'Move cells':'Paste')){anchor={r:b.top,c:b.left};active={r:b.top+nr-1,c:b.left+nc-1};if(moving)clearClipboard();paint(true);}
    }catch(e){notice('Nothing pasted. '+e.message,true);}
  }
  function markClipboard(cut,raw,box=bounds(),items=selected()){
    clipboardRange={cut,raw,bounds:{...box},items:items.map(x=>({...x}))};drawClipboard();
    if(cut&&!api.moveOnPaste){commit(items.map(x=>({...x,value:columns[x.c][0]==='date'?value(x.r,x.c):null,reset:columns[x.c][0]==='date'})),'Cut');clipboardRange={cut,raw,bounds:{...box},items:items.map(x=>({...x}))};drawClipboard();}
    notice(cut&&api.moveOnPaste?'Cut selected. Choose a destination and paste to move cells. Escape cancels.':'Selected cells '+(cut?'cut':'copied')+'. Escape clears the copy outline.');
  }
  async function clipboard(cut=false){
    if(!api.rows().length||!singleRange())return;if(cut&&selected().some(x=>!writable(x.c))){notice('Open the form to cut cells.',true);return;}
    const version=generation,items=selected(),box={...bounds()},raw=copyText();try{await navigator.clipboard.writeText(raw);if(version===generation)markClipboard(cut,raw,box,items);}catch{notice('Clipboard access is unavailable. Focus the selected cells and press Ctrl+C or Ctrl+X.',true);}
  }
  async function pasteClipboard(){const version=generation;try{const raw=await navigator.clipboard.readText();if(version===generation)paste(raw);}catch{notice('Focus an editable cell and press Ctrl+V to paste.',true);}}
  function flash(){
    if(!singleRange())return;
    const b=bounds();if(b.left!==b.right||(!writable(b.left)||!timeColumns.includes(columns[b.left][0]))||b.bottom-b.top<2){notice('Flash fill: select at least three cells in one time column. Enter the first two examples, leaving later cells blank.',true);return;}
    const seconds=v=>v===null?null:v.split('T').at(-1).split(':').map(Number).reduce((sum,n,i)=>sum+n*[3600,60,1][i],0);
    const first=seconds(value(b.top,b.left)),second=seconds(value(b.top+1,b.left));if(first===null||second===null){notice('Enter two time examples at the top of the selected range first.',true);return;}
    const changes=[];for(let r=b.top+2;r<=b.bottom;r++)if(value(r,b.left)===null){const total=((first+(second-first)*(r-b.top))%86400+86400)%86400;changes.push({r,c:b.left,value:[Math.floor(total/3600),Math.floor(total%3600/60),total%60].map(v=>String(v).padStart(2,'0')).join(':')});}
    if(!changes.length){notice('There are no blank cells after the two examples. Existing values are kept.',true);return;}
    openDialog('flash','Preview flash fill');const intro=document.createElement('p');intro.textContent=`The first two examples imply a ${second-first} second interval. ${changes.length} blank cell(s) will be filled. Check each proposed time against your records.`;content.append(intro);
    const list=document.createElement('div');list.className='sh-flash-preview';changes.forEach(x=>{const p=document.createElement('p');p.textContent=`${address(x)} · ${api.rows()[x.r].employee} · ${api.rows()[x.r].store} → ${api.text(columns[x.c][0],x.value)}`;list.append(p);});content.append(list);
    const button=document.createElement('button');button.type='button';button.className='sh-button sh-primary';button.id='sh-flash-apply';button.textContent='Apply suggested times';const version=generation;button.onclick=()=>{dialog.close();if(version===generation)commit(changes,'Flash fill');};content.append(button);
  }
  const commands=[
    ['D','Fill down','Ctrl+D','down'],['R','Fill right','Ctrl+R','right'],['E','Flash fill preview','Ctrl+E','flash'],
    ['C','Copy selected cells','Ctrl+C','copy'],['X','Cut selected cells','Ctrl+X','cut'],['V','Paste cells','Ctrl+V','paste'],
    ['Z','Undo sheet edit','Ctrl+Z','undo'],['Y','Redo sheet edit','Ctrl+Y / Ctrl+Shift+Z','redo'],['B','Clear selected cells','Delete','clear'],
    ['S','Save changes','Ctrl+S','save'],['F','Find employee or store','Ctrl+F','find'],['G','Go to cell or range','Ctrl+G','goto'],
    ['U','Use source/default','Remove selected corrections','reset'],['A','Select this page','Ctrl+A','all'],['I','Add employee','Form only','add'],['O','Download saved Excel','Filtered saved rows','download'],['T','Tutorial & shortcut guide','F1','tutorial']
  ];
  function command(name){
    const actions={down:()=>fill('down'),right:()=>fill('right'),flash,copy:()=>clipboard(),cut:()=>clipboard(true),paste:pasteClipboard,undo:()=>history(true),redo:()=>history(false),clear:clearCells,
      reset:()=>commit(selected().filter(x=>writable(x.c)).map(x=>({...x,value:null,reset:true})),'Use source/default'),edit:()=>beginEdit(),save:()=>{if(api.editing())api.save();else notice('Open the form to save edits.');},find:api.find,goto:()=>{rangeInput.focus();rangeInput.select();},all:()=>{selectionKind='all';extraRanges=[];anchor={r:0,c:0};active={r:api.rows().length-1,c:width-1};paint(true);},add:()=>{if(api.editing())api.add();else notice('Open the form to add an employee.');},download:api.download,commands:showCommands,tutorial:()=>tutorial(0)};
    if(!api.rows().length&&!['commands','tutorial','find','add'].includes(name))return;
    actions[name]?.();
  }
  function showCommands(){openDialog('commands','Spreadsheet commands');const p=document.createElement('p');p.textContent='F8 replaces Alt here. Press a letter below, or click a command. Shortcuts act only while the sheet has focus; your browser shortcuts work elsewhere.';content.append(p);
    const list=document.createElement('div');list.className='sh-command-list';commands.forEach(([key,label,shortcut,name])=>{const button=document.createElement('button');button.type='button';const k=document.createElement('kbd');k.textContent=key;const span=document.createElement('span');span.textContent=label;const small=document.createElement('small');small.textContent=shortcut;button.append(k,span,small);button.onclick=()=>{dialog.close();command(name);};list.append(button);});content.append(list);list.querySelector('button').focus();}
  dialog.addEventListener('keydown',e=>{if(dialogMode==='commands'&&!e.ctrlKey&&!e.metaKey&&!e.altKey){const match=commands.find(x=>x[0]===e.key.toUpperCase());if(match){e.preventDefault();dialog.close();command(match[3]);}}});
  const lessons=[
    ['Choose your rows','Filter by dealer, store, and date first. Each employee has an independent row. Selections and bulk edits cover the current page (up to 100 rows). Exports include all filtered saved rows.','Click a cell, then use arrows. Shift+arrows or drag selects a rectangle. Hold Shift while clicking, dragging, or using arrows to extend a range. Ctrl/Command+click or drag adds a separate range. Ctrl+Space selects entire columns; Shift+Space selects entire rows on this page. The Range box accepts G1:G10, K1:K10.'],
    ['Edit any report cell','All default and custom data columns are editable on the form and dedicated spreadsheet. Enter dates, names, statuses, times, or chargeback amounts. The report view displays saved values.','Press F2, double-click, start typing, or use Edit cell (also on phones). Enter 9:02 AM or 14:30:00. Enter commits and moves down; Tab moves right; Escape cancels. Ctrl+Enter applies the typed value to selected cells of compatible types. Clearing a schedule restores workbook hours after saving.'],
    ['Copy and paste','Use Ctrl+C / Ctrl+V for rectangular cells from Excel, Google Sheets, or this sheet. A single copied value fills the selected range. Paste is validated as a whole: an invalid time, incompatible value or page overflow rejects the entire paste.','Ctrl+X marks cells to move when pasted inside the dedicated sheet; Escape cancels the move. A dashed green outline marks copied or cut cells. Delete clears cells; clearing a date restores its source date. Ctrl+Z undoes an edit; Ctrl+Y or Ctrl+Shift+Z redoes it. Corrections to names and RT punches survive syncs. F8 then U restores selected cells to source/default values. Manually entered statuses and chargebacks stay fixed until you reset them.'],
    ['Fill and preview patterns','Select a range and press Ctrl+D to repeat its top row downward, or Ctrl+R to repeat its leftmost value rightward. On one cell, these copy from directly above or left.','For flash fill, enter two time examples and select them plus blank cells below in the same column. Ctrl+E previews the repeated or evenly spaced time pattern. It fills blanks only after you apply the preview. Verify camera times against your observations.'],
    ['Save your work','The dedicated spreadsheet autosaves after you finish an edit; check the AutoSave status before closing. Ctrl+S saves immediately. Undo covers the last 100 operations; reload, filter, and page changes reset it. A page refresh or sign-out discards unsaved drafts. Version history permanently records saved changes; undo never removes a saved version.','F8 opens the command menu instead of Excel’s Alt ribbon. For example, F8 then D fills down; F8 then S saves. Use Tutorial or F1 to reopen this guide. On Mac, Command can replace Ctrl.']
  ];
  function tutorial(step){tutorialStep=step;openDialog('tutorial',`Quick start · ${step+1} of ${lessons.length}`);const [heading,body,detail]=lessons[step];const h=document.createElement('h3');h.textContent=heading;content.append(h);for(const text of [body,detail]){const p=document.createElement('p');p.textContent=text;content.append(p);}
    if(step===4){const list=document.createElement('dl');list.className='sh-shortcut-guide';[['Arrows / Shift+arrows','Move / extend selection'],['Tab / Shift+Tab','Next / previous cell'],['Enter / Shift+Enter','Move down / up'],['Home / End','First / last column'],['Ctrl+Home / Ctrl+End','First / last cell on this page'],['Ctrl+arrows','Jump to page edges; add Shift to extend'],['Shift+Space','Select entire row(s)'],['Ctrl+Space','Select entire column(s) on this page'],['Page Up / Page Down','Move ten rows'],['Ctrl+A','Select current page'],['Ctrl+G','Go to cell or range'],['Ctrl+F','Search employees and stores'],['F2 / Escape','Edit / cancel'],...(api.animateSelection?[['Ctrl++ / Ctrl+=','Add an employee when whole rows are selected; otherwise add a custom column'],['Ctrl+-','Remove selected whole rows or the active custom column; default columns are protected']]:[]),...commands.slice(0,10).map(x=>[x[2],x[1]])].forEach(([key,description])=>{const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=description;list.append(dt,dd);});content.append(list);}
    const footer=document.createElement('div');footer.className='sh-tutorial-footer';const back=document.createElement('button');back.type='button';back.className='sh-button';back.textContent='Back';back.disabled=!step;back.onclick=()=>tutorial(step-1);const next=document.createElement('button');next.type='button';next.className='sh-button sh-primary';next.id='sh-tutorial-next';next.textContent=step===4?'Start working':'Next';next.onclick=()=>{if(step===4){markSeen();dialog.close();}else tutorial(step+1);};footer.append(back,next);content.append(footer);next.focus();
  }
  root.addEventListener('click',e=>{const button=e.target.closest('[data-grid]');if(button)command(button.dataset.grid);});
  rangeInput.addEventListener('keydown',e=>{if(e.key!=='Enter')return;e.preventDefault();const parts=rangeInput.value.trim().toUpperCase().split(',');if(parts.length>50){notice('Select up to 50 separate ranges.',true);return;}const parsed=[];
    for(const part of parts){const match=part.trim().match(/^([A-Z]{1,3})([1-9]\d*)(?::([A-Z]{1,3})([1-9]\d*))?$/);if(!match){notice('Enter ranges such as G1:G10, K1:K10.',true);return;}const a={r:Number(match[2])-1,c:columnIndex(match[1])},b={r:Number(match[4]||match[2])-1,c:columnIndex(match[3]||match[1])};if(Math.max(a.c,b.c)>=width||Math.max(a.r,b.r)>=api.rows().length){notice('That cell is outside this page.',true);return;}parsed.push({a,b});}
    selectionKind='cells';extraRanges=parsed.slice(0,-1).map(({a,b})=>({top:Math.min(a.r,b.r),bottom:Math.max(a.r,b.r),left:Math.min(a.c,b.c),right:Math.max(a.c,b.c)}));anchor=parsed.at(-1).a;active=parsed.at(-1).b;paint(true);});
  table.addEventListener('pointerdown',e=>{const gutter=e.target.closest('[data-sheet-row]');if(gutter){e.preventDefault();if((e.ctrlKey||e.metaKey)&&!e.shiftKey&&extraRanges.length<49)extraRanges.push(bounds());else if(!e.shiftKey)extraRanges=[];selectionKind='rows';anchor={r:e.shiftKey?anchor.r:Number(gutter.dataset.sheetRow),c:0};active={r:Number(gutter.dataset.sheetRow),c:width-1};paint(true);return;}const td=e.target.closest('td[data-grid-row]');if(!td||e.button!==0||e.target===editor||editor)return;e.preventDefault();const add=(e.ctrlKey||e.metaKey)&&!e.shiftKey;
    if(e.target.closest('.sh-row-number')){selectionKind='rows';if(add&&extraRanges.length<49)extraRanges.push(bounds());else if(!e.shiftKey)extraRanges=[];anchor={r:e.shiftKey?anchor.r:Number(td.dataset.gridRow),c:0};active={r:Number(td.dataset.gridRow),c:width-1};paint(true);return;}
    select(Number(td.dataset.gridRow),Number(td.dataset.gridCol),e.shiftKey,add);dragging=e.pointerType!=='touch';});
  table.tHead.addEventListener('click',e=>{const th=e.target.closest('th');if(!th||e.target.closest('button')||th.cellIndex<offset||th.cellIndex-offset>=width||!api.rows().length)return;if((e.ctrlKey||e.metaKey)&&!e.shiftKey&&extraRanges.length<49)extraRanges.push(bounds());else if(!e.shiftKey)extraRanges=[];selectionKind='columns';anchor={r:0,c:e.shiftKey?anchor.c:th.cellIndex-offset};active={r:api.rows().length-1,c:th.cellIndex-offset};paint(true);});
  table.addEventListener('pointerover',e=>{if(!dragging||!(e.buttons&1))return;const td=e.target.closest('td[data-grid-row]');if(td)select(Number(td.dataset.gridRow),Number(td.dataset.gridCol),true);});
  document.addEventListener('pointerup',()=>{dragging=false;});
  table.addEventListener('dblclick',e=>{if(e.target.closest('td[data-grid-row]'))beginEdit();});
  table.addEventListener('copy',e=>{if(editor||!api.rows().length)return;e.preventDefault();if(!singleRange())return;const raw=copyText();e.clipboardData.setData('text/plain',raw);markClipboard(false,raw);});
  table.addEventListener('cut',e=>{if(editor||!api.rows().length)return;e.preventDefault();if(!singleRange())return;if(selected().some(x=>!writable(x.c))){notice('Open the form to cut cells.',true);return;}const raw=copyText();e.clipboardData.setData('text/plain',raw);markClipboard(true,raw);});
  table.addEventListener('paste',e=>{if(editor)return;e.preventDefault();paste(e.clipboardData.getData('text/plain'));});
  table.addEventListener('keydown',e=>{
    if(editor||e.target.closest('button')||!api.rows().length)return;const ctrl=e.ctrlKey||e.metaKey,k=e.key.toLowerCase();
    if(ctrl&&['c','x','v'].includes(k))return;
    if(e.key==='F8'||e.key==='F1'){e.preventDefault();command(e.key==='F8'?'commands':'tutorial');return;}
    if(ctrl&&['d','r','e','z','y','a','s','f','g'].includes(k)){e.preventDefault();command(({d:'down',r:'right',e:'flash',z:e.shiftKey?'redo':'undo',y:'redo',a:'all',s:'save',f:'find',g:'goto'})[k]);return;}
    if((e.key===' '||e.code==='Space')&&(ctrl||e.shiftKey)){e.preventDefault();selectionKind=ctrl?'columns':'rows';const b=bounds();if(ctrl){extraRanges=extraRanges.map(x=>({...x,top:0,bottom:api.rows().length-1}));anchor={r:0,c:b.left};active={r:api.rows().length-1,c:b.right};}else{extraRanges=extraRanges.map(x=>({...x,left:0,right:width-1}));anchor={r:b.top,c:0};active={r:b.bottom,c:width-1};}paint(true);return;}
    if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Tab','Enter'].includes(e.key)){e.preventDefault();if(ctrl){select(e.key==='ArrowUp'?0:e.key==='ArrowDown'?api.rows().length-1:active.r,e.key==='ArrowLeft'?0:e.key==='ArrowRight'?width-1:active.c,e.shiftKey);}else move(e.key,e.shiftKey,e.shiftKey&&e.key.startsWith('Arrow'));return;}
    if(['Home','End','PageUp','PageDown'].includes(e.key)){e.preventDefault();select(e.key==='PageUp'?active.r-10:e.key==='PageDown'?active.r+10:ctrl?(e.key==='Home'?0:api.rows().length-1):active.r,e.key==='Home'?0:e.key==='End'?width-1:active.c,e.shiftKey);return;}
    if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();clearCells();return;}
    if(e.key==='Escape'){e.preventDefault();selectionKind='cells';clearClipboard();extraRanges=[];anchor={...active};paint(true);return;}
    if(e.key==='F2'){e.preventDefault();beginEdit();return;}
    if(e.key.length===1&&!ctrl&&!e.altKey){e.preventDefault();beginEdit(e.key);}
  });
  const layoutChanged=()=>{if(horizontalScroll){const target=cell(active.r,active.c);if(target)revealColumn(target);else stopScroll();}drawClipboard();drawSelection();};
  window.addEventListener('resize',layoutChanged);
  if(api.animateSelection){const observer=new ResizeObserver(layoutChanged);observer.observe(table);observer.observe(table.parentElement);}
  return {refresh,reset,resetHistory,borders,layout:layoutChanged,selectCell:(r,c)=>select(r,c),restoreCell:(r,c)=>select(r,c,false,false,false),isSelecting:()=>dragging,isEditing:()=>!!editor,finishEditing:()=>!editor||finishEditor?.(),command,selection:()=>({active:{...active},cells:selected(),kind:structuralSelection()}),setValue:(value,position=active)=>commit([{...position,value}],'Edit'),format:delta=>commit(selected().map(x=>({...x,kind:'format',value:delta===null?{}:{...api.cellFormat(x.r,x.c),...delta}})),'Format'),focus:()=>{if(root.getClientRects().length)paint(true);}};
};
