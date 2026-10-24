'use strict';
// A bounded spreadsheet editor over the existing review drafts and save API.
window.createStoreHoursGrid = function(api) {
  const {root,table,columns,fields}=api, offset=api.gutter?1:0;let width=columns.length;
  let anchor={r:0,c:0},active={r:0,c:0},signature='',editor=null,dragging=false,undo=[],redo=[],generation=0,extraRanges=[];
  const letter=c=>{let label='';for(c++;c;c=Math.floor((c-1)/26))label=String.fromCharCode(65+(c-1)%26)+label;return label;}, address=p=>letter(p.c)+(p.r+1);
  const columnIndex=s=>[...s].reduce((n,c)=>n*26+c.charCodeAt(0)-64,0)-1;
  const writable=c=>api.editing()&&!!columns[c];
  const timeColumns=[...fields,'rt_clockin','rt_clockout'];
  const cell=(r,c)=>table.tBodies[0]?.rows[r]?.cells[c+offset];
  const value=(r,c)=>api.rows()[r]?.[columns[c][0]]??null;
  const bounds=()=>({top:Math.min(anchor.r,active.r),bottom:Math.max(anchor.r,active.r),left:Math.min(anchor.c,active.c),right:Math.max(anchor.c,active.c)});
  const ranges=()=>[...extraRanges,bounds()].map(b=>({...b}));
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
    const rows=api.rows(),boxes=ranges();
    for(let r=0;r<table.tBodies[0]?.rows.length;r++)for(let c=0;c<width;c++){
      const td=cell(r,c),selected=boxes.some(b=>r>=b.top&&r<=b.bottom&&c>=b.left&&c<=b.right);
      td.classList.toggle('sh-cell-selected',selected);td.classList.toggle('sh-cell-active',r===active.r&&c===active.c);
      td.setAttribute('aria-selected',String(selected));td.tabIndex=r===active.r&&c===active.c?0:-1;
    }
    rangeInput.value=rows.length?boxes.map(rangeLabel).join(', '):'';
    status.textContent=rows.length?`${selected().length} cell(s) in ${boxes.length} range(s) · ${columns[active.c][1]} · ${writable(active.c)?'Editable':'Read only'} · Current page`:'No cells in this selection';
    toolbar.querySelector('[data-grid=undo]').disabled=!undo.length||api.busy()||!api.editing();
    toolbar.querySelector('[data-grid=redo]').disabled=!redo.length||api.busy()||!api.editing();
    ['down','right','flash'].forEach(id=>toolbar.querySelector(`[data-grid=${id}]`).disabled=!api.editing()||api.busy()||!rows.length);
    editButton.disabled=!rows.length||!writable(active.c)||api.busy();
    api.onSelection?.({active:{...active},cells:selected(),address:rangeInput.value});
    if(focus&&rows.length){const target=cell(active.r,active.c);target?.focus({preventScroll:true});target?.scrollIntoView({block:'nearest',inline:'nearest'});
      const wrap=table.parentElement;if(active.c<3)wrap.scrollLeft=0;else{const edge=wrap.getBoundingClientRect().left+(cell(active.r,2)?.offsetWidth||0)+2,hidden=edge-target.getBoundingClientRect().left;if(hidden>0)wrap.scrollLeft-=hidden;}
    }
  }
  function select(r,c,extend=false,add=false){if(!api.rows().length)return;if(add&&extraRanges.length<49)extraRanges.push(bounds());else if(!extend)extraRanges=[];active=clamp({r,c});if(!extend||add)anchor={...active};paint(true);}
  function resetHistory(){undo=[];redo=[];toolbar.querySelector('[data-grid=undo]').disabled=true;toolbar.querySelector('[data-grid=redo]').disabled=true;}
  function reset(){rangeInput.disabled=true;generation++;cancelEdit();if(dialog.open)dialog.close();content.replaceChildren();title.textContent='';resetHistory();signature='';extraRanges=[];anchor=active={r:0,c:0};welcome.hidden=true;}
  function refresh(){
    width=columns.length;const rows=api.rows();rangeInput.disabled=!rows.length;const next=JSON.stringify([api.editing(),columns.map(c=>c[0]),rows.map(api.key)]);
    if(next!==signature){generation++;cancelEdit();resetHistory();extraRanges=[];anchor={r:0,c:0};active={...anchor};signature=next;}
    table.setAttribute('role','grid');table.setAttribute('aria-label','Opening and closing spreadsheet');table.setAttribute('aria-multiselectable','true');
    table.setAttribute('aria-rowcount',String(rows.length+1));table.setAttribute('aria-colcount',String(width));
    [...table.tHead.rows[0].cells].forEach((th,index)=>{const c=index-offset;if(c<0||c>=width)return;th.setAttribute('role','columnheader');const tag=document.createElement('span');tag.className='sh-column-letter';tag.textContent=letter(c);th.prepend(tag);});
    [...table.tBodies[0].rows].forEach((tr,r)=>{tr.setAttribute('role','row');tr.setAttribute('aria-rowindex',String(r+2));
      for(let c=0;c<width;c++){const td=tr.cells[c+offset];td.setAttribute('role','gridcell');td.dataset.gridRow=r;td.dataset.gridCol=c;td.dataset.address=letter(c)+(r+1);td.setAttribute('aria-colindex',String(c+1));td.setAttribute('aria-readonly',String(!writable(c)));
        if(c===0&&!offset){const number=document.createElement('span');number.className='sh-row-number';number.textContent=r+1;td.prepend(number);}
        td.querySelectorAll('input').forEach(input=>{input.tabIndex=-1;input.setAttribute('aria-label',`${address({r,c})} ${columns[c][1]} — ${rows[r].employee} — ${rows[r].store}`);});
      }
    });
    try{welcome.hidden=!rows.length||localStorage.getItem(seenKey())==='seen';}catch{welcome.hidden=!rows.length;}
    active=clamp(active);anchor=clamp(anchor);paint();
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
    undo.push(items);if(undo.length>100)undo.shift();redo=[];api.apply(items);paint(true);notice(`${label}: ${items.length} cell(s) updated. Review the changes, then Save changes.`);return true;
  }
  function history(back){
    if(api.busy()||!api.editing())return;const from=back?undo:redo,to=back?redo:undo,items=from.pop();if(!items)return;
    to.push(items);api.apply(items.map(x=>({...x,value:back?x.before:x.value,reset:back?!x.beforeManual:x.reset})));paint(true);notice(back?'Last sheet edit undone. Save to persist this change.':'Sheet edit restored. Save to persist this change.');
  }
  function selected(){const out=new Map();for(const b of ranges())for(let r=b.top;r<=b.bottom;r++)for(let c=b.left;c<=b.right;c++)out.set(`${r}:${c}`,{r,c});return [...out.values()];}
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
  function cancelEdit(){const input=editor;editor=null;input?.remove();}
  function beginEdit(initial){
    if(!writable(active.c)||api.busy()){notice('This cell is read only in the report view. Open the form to edit it.',true);return;}
    cancelEdit();const pos={...active},td=cell(pos.r,pos.c);if(!td)return;
    const input=document.createElement('input');input.type='text';input.className='sh-cell-editor';input.setAttribute('aria-label','Edit '+address(pos));const field=columns[pos.c][0],original=value(pos.r,pos.c);input.value=initial??(timeColumns.includes(field)&&typeof original==='string'&&original.includes('T')?original.split('T')[1]:original)??'';input.placeholder=timeColumns.includes(field)?'9:02 AM':field==='date'?'YYYY-MM-DD':'Enter value';input.spellcheck=false;editor=input;td.append(input);input.focus();if(initial===undefined)input.select();
    let closing=false;
    const finish=(all=false)=>{if(closing||editor!==input)return true;let changes;try{changes=(all?selected().filter(x=>writable(x.c)):[pos]).map(x=>({...x,value:parseCell(x.r,x.c,input.value)}));}catch(e){notice(e.message,true);input.setAttribute('aria-invalid','true');return false;}closing=true;cancelEdit();commit(changes,'Edit');return true;};
    input.onkeydown=e=>{e.stopPropagation();const ctrl=e.ctrlKey||e.metaKey,k=e.key.toLowerCase();if(e.key==='Escape'){e.preventDefault();closing=true;cancelEdit();paint(true);}else if(e.key==='Enter'||e.key==='Tab'){e.preventDefault();if(finish(ctrl&&e.key==='Enter')&&!ctrl)move(e.key,e.shiftKey,false);}else if((ctrl&&['s','d','r','e','g','f'].includes(k))||['F8','F1'].includes(e.key)){e.preventDefault();if(finish())command(e.key==='F8'?'commands':e.key==='F1'?'tutorial':({s:'save',d:'down',r:'right',e:'flash',g:'goto',f:'find'})[k]);}};
    input.onblur=()=>{if(!finish()&&editor===input)input.focus();};
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
    if(rows.length>100||rows.some(r=>r.length!==rows[0].length)||rows[0].length>width)throw new Error('Paste a rectangular range of up to 100 rows and 14 columns.');return rows;
  }
  function paste(raw){
    if(!singleRange())return;
    try{const grid=matrix(raw),b=bounds(),height=grid.length,w=grid[0].length,selectedHeight=b.bottom-b.top+1,selectedWidth=b.right-b.left+1;
      const repeat=selectedHeight>=height&&selectedWidth>=w&&selectedHeight%height===0&&selectedWidth%w===0;
      const nr=repeat?selectedHeight:height,nc=repeat?selectedWidth:w,changes=[];
      if(b.top+nr>api.rows().length||b.left+nc>width)throw new Error('The paste would extend past this page. Choose a smaller range or the next page.');
      for(let r=0;r<nr;r++)for(let c=0;c<nc;c++){if(!writable(b.left+c))throw new Error(`${address({r:b.top+r,c:b.left+c})} is read only in the report view. Open the form to paste.`);changes.push({r:b.top+r,c:b.left+c,value:parseCell(b.top+r,b.left+c,grid[r%height][c%w])});}
      if(commit(changes,'Paste')){anchor={r:b.top,c:b.left};active={r:b.top+nr-1,c:b.left+nc-1};paint(true);}
    }catch(e){notice('Nothing pasted. '+e.message,true);}
  }
  async function clipboard(cut=false){
    if(!api.rows().length||!singleRange())return;if(cut&&selected().some(x=>!writable(x.c))){notice('Open the form to cut cells.',true);return;}
    const version=generation,items=selected();try{await navigator.clipboard.writeText(copyText());if(version!==generation)return;if(cut)commit(items.map(x=>({...x,value:null})),'Cut');else notice('Selected cells copied. Paste into Excel, Google Sheets, or another range.');}catch{notice('Clipboard access is unavailable. Focus the selected cells and press Ctrl+C or Ctrl+X.',true);}
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
      reset:()=>commit(selected().filter(x=>writable(x.c)).map(x=>({...x,value:null,reset:true})),'Use source/default'),edit:()=>beginEdit(),save:()=>{if(api.editing())api.save();else notice('Open the form to save edits.');},find:api.find,goto:()=>{rangeInput.focus();rangeInput.select();},all:()=>{extraRanges=[];anchor={r:0,c:0};active={r:api.rows().length-1,c:width-1};paint(true);},add:()=>{if(api.editing())api.add();else notice('Open the form to add an employee.');},download:api.download,commands:showCommands,tutorial:()=>tutorial(0)};
    if(!api.rows().length&&!['commands','tutorial','find','add'].includes(name))return;
    actions[name]?.();
  }
  function showCommands(){openDialog('commands','Spreadsheet commands');const p=document.createElement('p');p.textContent='F8 replaces Alt here. Press a letter below, or click a command. Shortcuts act only while the sheet has focus; your browser shortcuts work elsewhere.';content.append(p);
    const list=document.createElement('div');list.className='sh-command-list';commands.forEach(([key,label,shortcut,name])=>{const button=document.createElement('button');button.type='button';const k=document.createElement('kbd');k.textContent=key;const span=document.createElement('span');span.textContent=label;const small=document.createElement('small');small.textContent=shortcut;button.append(k,span,small);button.onclick=()=>{dialog.close();command(name);};list.append(button);});content.append(list);list.querySelector('button').focus();}
  dialog.addEventListener('keydown',e=>{if(dialogMode==='commands'&&!e.ctrlKey&&!e.metaKey&&!e.altKey){const match=commands.find(x=>x[0]===e.key.toUpperCase());if(match){e.preventDefault();dialog.close();command(match[3]);}}});
  const lessons=[
    ['Choose your rows','Filter by dealer, store, and date first. Each employee has an independent row. Selections and bulk edits cover the current page (up to 100 rows). Exports include all filtered saved rows.','Click a cell, then use arrows. Shift+arrows or drag selects a rectangle. Hold Shift while clicking, dragging, or using arrows to extend a range. Ctrl/Command+click or drag adds a separate range. Both Ctrl+Space and Shift+Space select columns on this page. The Range box accepts G1:G10, K1:K10.'],
    ['Edit any report cell','All default and custom data columns are editable on the form and dedicated spreadsheet. Enter dates, names, statuses, times, or chargeback amounts. The report view displays saved values.','Press F2, double-click, start typing, or use Edit cell (also on phones). Enter 9:02 AM or 14:30:00. Enter commits and moves down; Tab moves right; Escape cancels. Ctrl+Enter applies the typed value to selected cells of compatible types. Clearing a schedule restores workbook hours after saving.'],
    ['Copy and paste','Use Ctrl+C / Ctrl+V for rectangular cells from Excel, Google Sheets, or this sheet. A single copied value fills the selected range. Paste is validated as a whole: an invalid time, incompatible value or page overflow rejects the entire paste.','Ctrl+X cuts selected cells. Delete clears cells; clearing a date restores its source date. Ctrl+Z undoes an edit; Ctrl+Y or Ctrl+Shift+Z redoes it. Corrections to names and RT punches survive syncs. F8 then U restores selected cells to source/default values. Manually entered statuses and chargebacks stay fixed until you reset them.'],
    ['Fill and preview patterns','Select a range and press Ctrl+D to repeat its top row downward, or Ctrl+R to repeat its leftmost value rightward. On one cell, these copy from directly above or left.','For flash fill, enter two time examples and select them plus blank cells below in the same column. Ctrl+E previews the repeated or evenly spaced time pattern. It fills blanks only after you apply the preview. Verify camera times against your observations.'],
    ['Save your work','Edits remain drafts until Save changes or Ctrl+S succeeds. Undo covers the last 100 sheet operations and resets when you save, reload, change filters, or change pages. A page refresh or sign-out discards unsaved drafts. Version history permanently records saved changes; undo never removes a saved version.','F8 opens the command menu instead of Excel’s Alt ribbon. For example, F8 then D fills down; F8 then S saves. Use Tutorial or F1 to reopen this guide. On Mac, Command can replace Ctrl.']
  ];
  function tutorial(step){tutorialStep=step;openDialog('tutorial',`Quick start · ${step+1} of ${lessons.length}`);const [heading,body,detail]=lessons[step];const h=document.createElement('h3');h.textContent=heading;content.append(h);for(const text of [body,detail]){const p=document.createElement('p');p.textContent=text;content.append(p);}
    if(step===4){const list=document.createElement('dl');list.className='sh-shortcut-guide';[['Arrows / Shift+arrows','Move / extend selection'],['Tab / Shift+Tab','Next / previous cell'],['Enter / Shift+Enter','Move down / up'],['Home / End','First / last column'],['Ctrl+Home / Ctrl+End','First / last cell on this page'],['Ctrl+arrows','Jump to page edges; add Shift to extend'],['Shift+Space / Ctrl+Space','Select entire column(s) on this page'],['Page Up / Page Down','Move ten rows'],['Ctrl+A','Select current page'],['Ctrl+G','Go to cell or range'],['Ctrl+F','Search employees and stores'],['F2 / Escape','Edit / cancel'],...commands.slice(0,10).map(x=>[x[2],x[1]])].forEach(([key,description])=>{const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=description;list.append(dt,dd);});content.append(list);}
    const footer=document.createElement('div');footer.className='sh-tutorial-footer';const back=document.createElement('button');back.type='button';back.className='sh-button';back.textContent='Back';back.disabled=!step;back.onclick=()=>tutorial(step-1);const next=document.createElement('button');next.type='button';next.className='sh-button sh-primary';next.id='sh-tutorial-next';next.textContent=step===4?'Start working':'Next';next.onclick=()=>{if(step===4){markSeen();dialog.close();}else tutorial(step+1);};footer.append(back,next);content.append(footer);next.focus();
  }
  root.addEventListener('click',e=>{const button=e.target.closest('[data-grid]');if(button)command(button.dataset.grid);});
  rangeInput.addEventListener('keydown',e=>{if(e.key!=='Enter')return;e.preventDefault();const parts=rangeInput.value.trim().toUpperCase().split(',');if(parts.length>50){notice('Select up to 50 separate ranges.',true);return;}const parsed=[];
    for(const part of parts){const match=part.trim().match(/^([A-Z]{1,3})([1-9]\d*)(?::([A-Z]{1,3})([1-9]\d*))?$/);if(!match){notice('Enter ranges such as G1:G10, K1:K10.',true);return;}const a={r:Number(match[2])-1,c:columnIndex(match[1])},b={r:Number(match[4]||match[2])-1,c:columnIndex(match[3]||match[1])};if(Math.max(a.c,b.c)>=width||Math.max(a.r,b.r)>=api.rows().length){notice('That cell is outside this page.',true);return;}parsed.push({a,b});}
    extraRanges=parsed.slice(0,-1).map(({a,b})=>({top:Math.min(a.r,b.r),bottom:Math.max(a.r,b.r),left:Math.min(a.c,b.c),right:Math.max(a.c,b.c)}));anchor=parsed.at(-1).a;active=parsed.at(-1).b;paint(true);});
  table.addEventListener('pointerdown',e=>{const gutter=e.target.closest('[data-sheet-row]');if(gutter){e.preventDefault();extraRanges=[];anchor={r:Number(gutter.dataset.sheetRow),c:0};active={r:anchor.r,c:width-1};paint(true);return;}const td=e.target.closest('td[data-grid-row]');if(!td||e.button!==0||e.target===editor||editor)return;e.preventDefault();const add=(e.ctrlKey||e.metaKey)&&!e.shiftKey;
    if(e.target.closest('.sh-row-number')){if(add&&extraRanges.length<49)extraRanges.push(bounds());else if(!e.shiftKey)extraRanges=[];anchor={r:e.shiftKey?anchor.r:Number(td.dataset.gridRow),c:0};active={r:Number(td.dataset.gridRow),c:width-1};paint(true);return;}
    select(Number(td.dataset.gridRow),Number(td.dataset.gridCol),e.shiftKey,add);dragging=e.pointerType!=='touch';});
  table.tHead.addEventListener('click',e=>{const th=e.target.closest('th');if(!th||e.target.closest('button')||th.cellIndex<offset||th.cellIndex-offset>=width||!api.rows().length)return;if((e.ctrlKey||e.metaKey)&&!e.shiftKey&&extraRanges.length<49)extraRanges.push(bounds());else if(!e.shiftKey)extraRanges=[];anchor={r:0,c:e.shiftKey?anchor.c:th.cellIndex-offset};active={r:api.rows().length-1,c:th.cellIndex-offset};paint(true);});
  table.addEventListener('pointerover',e=>{if(!dragging||!(e.buttons&1))return;const td=e.target.closest('td[data-grid-row]');if(td)select(Number(td.dataset.gridRow),Number(td.dataset.gridCol),true);});
  document.addEventListener('pointerup',()=>{dragging=false;});
  table.addEventListener('dblclick',e=>{if(e.target.closest('td[data-grid-row]'))beginEdit();});
  table.addEventListener('copy',e=>{if(editor||!api.rows().length)return;e.preventDefault();if(!singleRange())return;e.clipboardData.setData('text/plain',copyText());notice('Selected cells copied.');});
  table.addEventListener('cut',e=>{if(editor||!api.rows().length)return;e.preventDefault();if(!singleRange())return;if(selected().some(x=>!writable(x.c))){notice('Open the form to cut cells.',true);return;}e.clipboardData.setData('text/plain',copyText());clearCells();});
  table.addEventListener('paste',e=>{if(editor)return;e.preventDefault();paste(e.clipboardData.getData('text/plain'));});
  table.addEventListener('keydown',e=>{
    if(editor||e.target.closest('button')||!api.rows().length)return;const ctrl=e.ctrlKey||e.metaKey,k=e.key.toLowerCase();
    if(ctrl&&['c','x','v'].includes(k))return;
    if(e.key==='F8'||e.key==='F1'){e.preventDefault();command(e.key==='F8'?'commands':'tutorial');return;}
    if(ctrl&&['d','r','e','z','y','a','s','f','g'].includes(k)){e.preventDefault();command(({d:'down',r:'right',e:'flash',z:e.shiftKey?'redo':'undo',y:'redo',a:'all',s:'save',f:'find',g:'goto'})[k]);return;}
    if((e.key===' '||e.code==='Space')&&(ctrl||e.shiftKey)){e.preventDefault();const b=bounds();extraRanges=extraRanges.map(x=>({...x,top:0,bottom:api.rows().length-1}));anchor={r:0,c:b.left};active={r:api.rows().length-1,c:b.right};paint(true);return;}
    if(['ArrowLeft','ArrowRight','ArrowUp','ArrowDown','Tab','Enter'].includes(e.key)){e.preventDefault();if(ctrl){select(e.key==='ArrowUp'?0:e.key==='ArrowDown'?api.rows().length-1:active.r,e.key==='ArrowLeft'?0:e.key==='ArrowRight'?width-1:active.c,e.shiftKey);}else move(e.key,e.shiftKey,e.shiftKey&&e.key.startsWith('Arrow'));return;}
    if(['Home','End','PageUp','PageDown'].includes(e.key)){e.preventDefault();select(e.key==='PageUp'?active.r-10:e.key==='PageDown'?active.r+10:ctrl?(e.key==='Home'?0:api.rows().length-1):active.r,e.key==='Home'?0:e.key==='End'?width-1:active.c,e.shiftKey);return;}
    if(e.key==='Delete'||e.key==='Backspace'){e.preventDefault();clearCells();return;}
    if(e.key==='Escape'){e.preventDefault();extraRanges=[];anchor={...active};paint(true);return;}
    if(e.key==='F2'){e.preventDefault();beginEdit();return;}
    if(e.key.length===1&&!ctrl&&!e.altKey){e.preventDefault();beginEdit(e.key);}
  });
  return {refresh,reset,resetHistory,command,selection:()=>({active:{...active},cells:selected()}),setValue:value=>commit([{...active,value}],'Edit'),format:delta=>commit(selected().map(x=>({...x,kind:'format',value:delta===null?{}:{...api.cellFormat(x.r,x.c),...delta}})),'Format'),focus:()=>{if(root.getClientRects().length)paint(true);}};
};
