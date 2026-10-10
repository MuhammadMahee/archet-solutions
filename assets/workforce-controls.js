'use strict';
window.createWorkforceControls = function(host) {
  const el = id => document.getElementById('wf-' + id), esc = escapeHTML;
  let state = null, filter = 'all', reply = null, selected = new Set(), selecting = false, epoch = 0;
  const menu = document.createElement('div'); menu.className = 'wf-context-menu'; menu.hidden = true; menu.setAttribute('role','menu'); document.body.append(menu);
  const panel = document.createElement('dialog'); panel.className = 'wf-dialog wf-info-panel'; panel.id = 'wf-group-info'; document.body.append(panel);
  const modal = document.createElement('dialog'); modal.className = 'wf-dialog wf-control-dialog'; modal.id = 'wf-control-dialog'; document.body.append(modal);
  const memoryPanel=document.createElement('dialog');memoryPanel.className='wf-dialog wf-memory-panel';memoryPanel.id='wf-memory-panel';document.body.append(memoryPanel);
  const memoryButton=document.createElement('button');memoryButton.type='button';memoryButton.className='subtle';memoryButton.id='wf-memory';memoryButton.textContent='Memory';memoryButton.setAttribute('aria-label','AI memory');document.querySelector('.wf-hero-actions').prepend(memoryButton);
  const toolbar = document.createElement('div'); toolbar.className = 'wf-inbox-filters';
  toolbar.innerHTML = '<div class="wf-filter-tabs" aria-label="Conversation filters"><button type="button" data-filter="all" aria-pressed="true">All</button><button type="button" data-filter="unread" aria-pressed="false">Unread</button><button type="button" data-filter="favorites" aria-pressed="false">Favorites</button></div><select aria-label="Filter conversations"><option value="all">All chats</option><option value="unread">Unread</option><option value="favorites">Favorites</option><option value="archived">Archived</option></select>';
  el('chats').before(toolbar);
  const setFilter=value=>{filter=value;toolbar.querySelectorAll('[data-filter]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.filter===value)));host.renderChats();};
  toolbar.querySelector('select').onchange = e => setFilter(e.target.value);
  toolbar.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>setFilter(b.dataset.filter));
  const more = document.createElement('button'); more.type='button'; more.className='wf-square'; more.textContent='⋮'; more.id='wf-chat-menu'; more.setAttribute('aria-label','Chat options');
  document.querySelector('.wf-chat-head').append(more);
  const replyBar=document.createElement('div'); replyBar.className='wf-reply-bar'; replyBar.hidden=true; el('input').before(replyBar);
  const selectionBar=document.createElement('div'); selectionBar.className='wf-selection-bar'; selectionBar.hidden=true; el('log').before(selectionBar);
  const run = fn => async (...args) => { const ticket=epoch; try {await fn(...args);} catch(e) {if(ticket===epoch && currentUser)host.error(e.message);} };
  async function call(...args){const ticket=epoch;const result=await api(...args);if(ticket!==epoch||!currentUser||currentUser.rest_mode)throw new Error('The conversation changed.');return result;}
  const endpoint = chat => 'workforce/conversations/'+chat;
  const current = () => host.state();
  const button = (label, action, danger=false) => ({label,action,danger});
  // One stroke-based icon family keeps chat, menus and group settings consistent.
  function icon(name){
    const paths={
      info:'<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
      person:'<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2m3-13v6m-3-3h6"/>',
      search:'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
      reply:'<path d="m9 5-6 6 6 6m-6-6h10a7 7 0 0 1 7 7"/>',
      copy:'<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/>',
      smile:'<circle cx="12" cy="12" r="9"/><path d="M8 14s1 3 4 3 4-3 4-3M8 8v2m8-2v2"/>',
      forward:'<path d="m15 5 6 6-6 6m6-6H11a7 7 0 0 0-7 7"/>',
      download:'<path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/>',
      exit:'<path d="M10 3H4v18h6m-1-9h12m-5-5 5 5-5 5"/>',
      trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
      pin:'<path d="m8 3 8 0-1 7 4 4v2H5v-2l4-4-1-7m4 13v6"/>',
      star:'<path d="m12 3 2.8 5.8 6.4.9-4.6 4.5 1.1 6.4-5.7-3-5.7 3 1.1-6.4-4.6-4.5 6.4-.9Z"/>',
      heart:'<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
      archive:'<path d="M4 8v13h16V8M9 12h6"/><rect x="3" y="3" width="18" height="5" rx="1"/>',
      bell:'<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9m-9 12h6"/>',
      theme:'<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18Z"/>',
      link:'<path d="m10 13 4-4m-5 7-2 2a4 4 0 0 1-6-6l4-4a4 4 0 0 1 6 0m2 2 2-2a4 4 0 0 1 6 6l-4 4a4 4 0 0 1-6 0" transform="translate(1 -1)"/>',
      edit:'<path d="m15 4 5 5M4 20l5-1L21 7a3.5 3.5 0 0 0-5-5L4 14Z"/>',
      image:'<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1"/><path d="m3 17 6-6 4 4 3-3 5 5"/>',
      clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
      list:'<path d="M9 5h12M9 12h12M9 19h12M3 5h1M3 12h1M3 19h1"/>',
      check:'<path d="m4 12 5 5L20 6"/>',
      close:'<path d="m6 6 12 12M6 18 18 6"/>',
      flag:'<path d="M5 22V3c5-4 9 4 14 0v11c-5 4-9-4-14 0"/>',
      more:'<circle cx="12" cy="5" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="12" cy="19" r="1"/>',
      camera:'<path d="m8 5 2-3h4l2 3h5v16H3V5Z"/><circle cx="12" cy="13" r="4"/>',
      chat:'<path d="M21 11a9 9 0 0 1-9 9H3l2-5a9 9 0 1 1 16-4Z"/>'
    };
    return '<svg class="wf-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+(paths[name]||paths.chat)+'</svg>';
  }
  function labelButton(node,label){
    const rules=[[/info/i,'info'],[/member|similar group/i,'person'],[/search/i,'search'],[/reply/i,'reply'],[/copy/i,'copy'],[/react/i,'smile'],[/forward/i,'forward'],[/download|export/i,'download'],[/exit/i,'exit'],[/delete|clear/i,'trash'],[/pin/i,'pin'],[/star/i,'star'],[/favorites/i,'heart'],[/archive/i,'archive'],[/notification/i,'bell'],[/theme/i,'theme'],[/link|invite/i,'link'],[/edit/i,'edit'],[/media/i,'image'],[/disappearing/i,'clock'],[/list/i,'list'],[/read|select/i,'check'],[/close/i,'close'],[/report/i,'flag']];
    node.innerHTML=icon(rules.find(([pattern])=>pattern.test(label))?.[1])+'<span>'+esc(label)+'</span>';node.setAttribute('aria-label',label);
  }
  more.innerHTML=icon('more');
  document.querySelectorAll('.wf-search>span,.wf-chat-tools label>span').forEach(node=>node.innerHTML=icon('search'));
  const attach=document.querySelector('.wf-image-button');attach.innerHTML=icon('image');attach.title='Attach screenshots';
  el('new').innerHTML=icon('edit');el('new').title='New conversation';
  el('send').innerHTML='<span>Send</span>'+icon('forward');
  function hideMenu(){menu.hidden=true;menu.replaceChildren();}
  document.addEventListener('pointerdown',e=>{if(!menu.contains(e.target))hideMenu();});
  document.addEventListener('keydown',e=>{if(e.key==='Escape')hideMenu();});
  function showMenu(items, anchor, event) {
    hideMenu();
    menu.classList.toggle('wf-reaction-menu',items.every(item=>!/[A-Za-z]/.test(item.label)));
    for(const item of items){const b=document.createElement('button');b.type='button';b.role='menuitem';labelButton(b,item.label);if(item.danger)b.className='danger';if(['Archive chat','Unarchive chat','Export chat','Delete for me','Clear chat'].includes(item.label))b.classList.add('wf-menu-divider');b.onclick=run(async()=>{hideMenu();await item.action();});menu.append(b);}
    const rect=anchor.getBoundingClientRect();menu.hidden=false;
    menu.style.left=Math.max(8,Math.min(event?.clientX??rect.right-menu.offsetWidth,innerWidth-menu.offsetWidth-8))+'px';
    menu.style.top=Math.max(8,Math.min(event?.clientY??rect.bottom,innerHeight-menu.offsetHeight-8))+'px';
    menu.querySelector('button')?.focus();
    menu.onkeydown=e=>{if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();const buttons=[...menu.querySelectorAll('button')],i=buttons.indexOf(document.activeElement);buttons[(i+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length].focus();}};
  }
  function shell(node,title,html){node.innerHTML='<div class="wf-close-row"><h2>'+esc(title)+'</h2><button type="button" class="close" aria-label="Close '+esc(title)+'">×</button></div>'+html;node.querySelector('.close').onclick=()=>node.close();if(!node.open)node.showModal();}
  function form(title,label,value,save,{options=null,help='',confirm=false}={}) {
    const input=options?'<select name="value">'+options.map(([v,l])=>'<option value="'+esc(v)+'" '+(String(v)===String(value)?'selected':'')+'>'+esc(l)+'</option>').join('')+'</select>':'<textarea name="value" maxlength="1000" rows="3">'+esc(value||'')+'</textarea>';
    shell(modal,title,'<form><label>'+esc(label)+(confirm?'':input)+'</label><p>'+esc(help)+'</p><p class="error" role="alert"></p><button class="primary" type="submit">'+(confirm?'Confirm':'Save')+'</button></form>');
    modal.querySelector('form').onsubmit=async e=>{e.preventDefault();const ticket=epoch,b=e.submitter;b.disabled=true;try{await save(confirm?true:e.target.elements.value.value);if(ticket===epoch)modal.close();}catch(error){if(ticket===epoch)modal.querySelector('.error').textContent=error.message;}finally{b.disabled=false;}};
  }
  async function memory(){
    const data=await call('workforce/memory');
    shell(memoryPanel,'AI memory','<p>Useful context that stays with your AI team, even when you clear a chat or start a new one.</p><label class="wf-memory-toggle"><input type="checkbox" id="wf-memory-auto" '+(data.enabled?'checked':'')+'> Let Manager remember useful details automatically</label><p class="wf-memory-help">Personal notes follow you into chats only when everyone there was in the original audience. Notes you add here are private to chats with just you and AI. Company notes are shared with all employees. Past chats are not imported automatically.</p><div class="wf-memory-tools"><input type="search" id="wf-memory-search" placeholder="Find a memory" aria-label="Find a memory"><button type="button" id="wf-memory-add">Add note</button></div><div id="wf-memory-notes"></div>');
    const render=()=>{
      const q=memoryPanel.querySelector('#wf-memory-search').value.toLowerCase();
      const rows=data.memories.filter(m=>(m.topic+' '+m.content).toLowerCase().includes(q));
      memoryPanel.querySelector('#wf-memory-notes').innerHTML=rows.map(m=>'<article class="wf-memory-note"><div class="wf-memory-note-head"><strong>'+esc(m.topic)+'</strong><span>'+esc(m.scope==='company'?'Company':'Personal')+'</span></div><p>'+esc(m.content)+'</p><small>'+esc(new Date(m.updated_at).toLocaleDateString())+(m.scope==='personal'?' &middot; '+m.audience_count+' original recipient'+(m.audience_count===1?'':'s'):' &middot; Shared with all employees')+'</small>'+(m.can_edit?'<div class="wf-memory-note-actions"><button data-edit-memory="'+esc(m.id)+'">Edit</button><button class="danger" data-forget-memory="'+esc(m.id)+'">Forget</button></div>':'')+'</article>').join('')||'<p class="wf-memory-empty">'+(q?'No matching notes.':'No memories saved yet. Tell Manager something useful to remember, or add your first note.')+'</p>';
    };
    memoryPanel.querySelector('#wf-memory-search').oninput=render;render();
    memoryPanel.querySelector('#wf-memory-auto').onchange=run(async e=>{const b=e.target;b.disabled=true;try{await call('workforce/memory/settings','PATCH',{enabled:b.checked});}catch(error){b.checked=!b.checked;throw error;}finally{b.disabled=false;}});
    const edit=note=>{
      shell(modal,note?'Edit memory':'Add memory','<form><label>Title<input name="topic" maxlength="80" required value="'+esc(note?.topic||'')+'"></label><label>What should the AI remember?<textarea name="content" maxlength="600" rows="4" required>'+esc(note?.content||'')+'</textarea></label><label>Visibility<select name="scope"><option value="personal">Personal</option>'+(data.can_share?'<option value="company">Company — all employees</option>':'')+'</select></label><p>Company notes are included in other employees’ AI chats. Don’t save passwords or confidential identifiers.</p><p class="error" role="alert"></p><button type="submit" class="primary">Save note</button></form>');
      modal.querySelector('[name=scope]').value=note?.scope||'personal';
      modal.querySelector('form').onsubmit=async e=>{e.preventDefault();const ticket=epoch,b=e.submitter;b.disabled=true;try{const f=e.target.elements;await call('workforce/memory'+(note?'/'+note.id:''),note?'PATCH':'POST',{topic:f.topic.value,content:f.content.value,scope:f.scope.value});modal.close();await memory();}catch(error){if(ticket===epoch)modal.querySelector('.error').textContent=error.message;}finally{b.disabled=false;}};
    };
    memoryPanel.querySelector('#wf-memory-add').onclick=()=>edit(null);
    memoryPanel.querySelector('#wf-memory-notes').onclick=e=>{const editButton=e.target.closest('[data-edit-memory]'),forget=e.target.closest('[data-forget-memory]');if(editButton)edit(data.memories.find(m=>m.id===editButton.dataset.editMemory));if(forget){const note=data.memories.find(m=>m.id===forget.dataset.forgetMemory);form('Forget memory','Forget “'+note.topic+'”?',null,async()=>{await call('workforce/memory/'+note.id,'DELETE');await memory();},{confirm:true,help:'This removes the durable note from future AI context. Existing chat messages are unchanged.'});}};
  }
  memoryButton.onclick=run(memory);
  async function prefs(chat,values){await call(endpoint(chat)+'/preferences','PATCH',values);await host.refresh();}
  function mute(chat){form('Notification settings','Mute in-app unread and mention badges',0,value=>prefs(chat,{muted_until:value==='0'?0:Date.now()/1000+Number(value)}),{options:[['0','Unmute'],['28800','8 hours'],['604800','1 week'],['31536000','1 year']],help:'Unread messages remain in the chat. Browser push and calls are not connected.'});}
  function theme(chat){form('Chat theme','Choose your theme',state?.preferences.theme||'default',value=>prefs(chat,{theme:value}),{options:[['default','Archet dark'],['forest','Forest'],['midnight','Midnight blue'],['plum','Plum']]});}
  function list(chat){form('Add to list','List name (leave blank to remove)',current().chats.find(c=>c.id===chat)?.preferences?.list_name||'',value=>prefs(chat,{list_name:value.trim()}),{help:'Lists organize your chats and stay private to your account.'});}
  function report(chat,seq=null){form(seq?'Report message':'Report group','Reason','',async reason=>{await call(seq?'workforce/messages/'+seq+'/report':endpoint(chat)+'/actions/report','POST',{reason});host.error('Report saved for portal administrators to review.');});}
  function searchMessages(){form('Search chat','Search all visible messages','',async value=>{modal.close();setTimeout(()=>run(()=>library('search',value))(),0);});}
  async function library(kind,query=''){const chat=current().active;if(!chat)return;const ticket=epoch;const data=await call(endpoint(chat)+'/library?kind='+kind+'&q='+encodeURIComponent(query));if(ticket!==epoch||current().active!==chat)return;
    const names={media:'Media and reports',links:'Links',starred:'Starred messages',pinned:'Pinned messages',search:'Search results'};
    shell(modal,names[kind],'<div class="wf-library">'+(data.messages.map(m=>'<article><strong>'+esc(m.sender_name)+'</strong><p>'+esc(m.content)+'</p>'+m.images.map(i=>'<a href="/api/internal/workforce/images/'+esc(i.id)+'" target="_blank" rel="noopener"><img alt="'+esc(i.name)+'" src="/api/internal/workforce/images/'+esc(i.id)+'"></a>').join('')+(m.report_ready?'<button data-library-report="'+esc(m.task_id)+'">Open sales snapshot</button> <a href="/api/internal/workforce/tasks/'+esc(m.task_id)+'/report.csv" download>Download sales report</a>':'')+'</article>').join('')||'<p>No matching messages.</p>')+'</div><p>Showing up to 200 recent matches.</p>');
    if(kind==='links')for(const article of modal.querySelectorAll('.wf-library article')){
      for(const match of article.querySelector('p').textContent.matchAll(/https?:\/\/[^\s<>"']+/g)){
        const a=document.createElement('a');a.textContent=match[0];a.href=match[0];a.target='_blank';a.rel='noopener noreferrer';a.style.display='block';article.append(a);
      }
    }
    modal.querySelectorAll('[data-library-report]').forEach(b=>b.onclick=run(async()=>{
      const report=await call('workforce/tasks/'+b.dataset.libraryReport+'/snapshot');
      const src=window.salesSnapshot.render(report,report.filters).toDataURL('image/png');
      shell(modal,'Sales snapshot','<img style="max-width:100%" alt="Sales Update snapshot" src="'+src+'"><a download="sales-snapshot.png" href="'+src+'">Download snapshot</a>');
    }));
  }
  async function addMember(chat){const ticket=epoch,data=await call(endpoint(chat)+'/people');if(ticket!==epoch)return;const joined=new Set(current().participants.map(p=>p.id));const options=data.people.filter(p=>!joined.has(p.id)).map(p=>[p.id,p.display_name]);if(!options.length){host.error('All available employees are already members.');return;}
    form('Add member','Employee',options[0][0],async user_id=>{await call(endpoint(chat)+'/members','POST',{action:'add',user_id});await host.refresh();if(panel.open)await info();},{options});}
  async function invite(chat){const ticket=epoch;const result=await call(endpoint(chat)+'/actions/invite','POST',{});if(ticket!==epoch)return;const link=location.origin+'/ai-workforce#invite='+result.token;
    shell(modal,'Invite to group','<p>Only signed-in portal employees can join. This link expires in 7 days. Creating a new link revokes the previous link.</p><input aria-label="Group invite link" readonly value="'+esc(link)+'"><button id="wf-copy-invite">Copy invite link</button><button id="wf-revoke-invite">Revoke link</button>');
    document.getElementById('wf-copy-invite').onclick=run(async()=>{await navigator.clipboard.writeText(link);document.getElementById('wf-copy-invite').textContent='Copied';});
    document.getElementById('wf-revoke-invite').onclick=run(async()=>{await call(endpoint(chat)+'/actions/revoke-invite','POST',{});modal.close();});
  }
  function groupActions(chat) {
    const c=current().chats.find(c=>c.id===chat),p=c?.preferences||{},active=chat===current().active;
    const items=[button(p.archived?'Unarchive chat':'Archive chat',()=>prefs(chat,{archived:!p.archived})),button('Mute notifications',()=>mute(chat)),button(p.pinned?'Unpin chat':'Pin chat',()=>prefs(chat,{pinned:!p.pinned})),button('Mark as read',()=>prefs(chat,{read_seq:c?.last_seq||0,unread:0})),button('Mark as unread',()=>prefs(chat,{unread:1})),button(p.favorite?'Remove from Favorites':'Add to Favorites',()=>prefs(chat,{favorite:!p.favorite})),button('Add to list',()=>list(chat))];
    if(active)items.unshift(button('Group info',info),button('Search',searchMessages),button('Select messages',()=>{selecting=true;host.renderMessages();selectionUI();}),button('Starred messages',()=>library('starred')),button('Pinned messages',()=>library('pinned')),button('Chat theme',()=>theme(chat)));
    if(active&&state?.can_manage)items.unshift(button('Add member',()=>addMember(chat)),button('Disappearing messages',()=>form('Disappearing messages','New messages expire after',state.profile.disappearing,async value=>{await call(endpoint(chat)+'/profile','PATCH',{disappearing:Number(value)});await host.refresh();},{options:[['0','Off'],['86400','24 hours'],['604800','7 days'],['7776000','90 days']],help:'Applies to new messages. Expired messages and attachments become unavailable; downloaded or forwarded copies can remain.'})));
    items.push(button('Export chat',()=>{location.href='/api/internal/'+endpoint(chat)+'/export';}),button('Close chat',()=>host.close()),button('Clear chat',()=>form('Clear chat','Clear the current history for your account?',null,async()=>{await call(endpoint(chat)+'/actions/clear','POST',{});await host.refresh();},{confirm:true,help:'Other members keep their messages. New messages will still appear.'}),true),button('Exit group',()=>form('Exit group','Leave this group?',null,async()=>{await call(endpoint(chat)+'/actions/exit','POST',{});panel.close();if(active)host.close();await host.refresh();},{confirm:true,help:'You lose access to its messages and images. A remaining member becomes creator if you are leaving as creator.'}),true),button('Report group',()=>report(chat),true));
    return items;
  }
  async function info(){const chat=current().active;if(!chat)return;const ticket=epoch;const data=await call(endpoint(chat));if(ticket!==epoch||current().active!==chat)return;state=data;
    const names=data.participants,creator=names.find(p=>p.id===data.profile.original_creator)?.name||'Former member';
    shell(panel,'Group info',
      '<div class="wf-group-identity"><button id="wf-group-avatar" aria-label="Change group photo">'+(data.profile.has_avatar?'<img src="/api/internal/'+endpoint(chat)+'/avatar?v='+esc(data.revision)+'" alt="Group photo">':icon('camera'))+'</button><div class="wf-group-title"><h2>'+esc(data.conversation.title)+'</h2><span id="wf-edit-title"></span></div><p>'+names.length+' members &middot; '+names.filter(p=>p.kind==='ai').length+' AI teammates</p></div>'+
      '<div class="wf-group-quick"></div><section class="wf-info-section"><div class="wf-section-title"><h3>About this group</h3><span id="wf-edit-description"></span></div><p class="wf-description">'+esc(data.profile.description||'Add a description to give your team a little context.')+'</p></section>'+
      '<section class="wf-info-section"><div class="wf-section-title"><h3>Members</h3><span class="wf-member-count">'+names.length+'</span></div><input id="wf-member-search" placeholder="Find a member" aria-label="Search group members"><div id="wf-member-list"></div><div class="wf-group-actions" data-section="members"></div></section>'+
      '<section class="wf-info-section"><h3>Shared in this chat</h3><div class="wf-group-actions" data-section="shared"></div></section><section class="wf-info-section"><h3>Preferences</h3><div class="wf-group-actions" data-section="preferences"></div></section><section class="wf-info-section"><h3>Manage group</h3><div class="wf-group-actions" data-section="manage"></div></section><p class="wf-created">Created by '+esc(creator)+'<br>'+esc(new Date(data.conversation.created_at).toLocaleDateString(undefined,{month:'long',day:'numeric',year:'numeric'}))+'</p>');
    const actions=[button('Search messages',searchMessages),button('Media and reports',()=>library('media')),button('Links',()=>library('links')),button('Starred messages',()=>library('starred')),button('Notification settings',()=>mute(chat)),button('Chat theme',()=>theme(chat)),button('Add member tag',()=>form('My member tag','Tag',data.preferences.member_tag,async value=>{await prefs(chat,{member_tag:value});await info();})),button('See member changes',async()=>{const result=await call(endpoint(chat)+'/events');shell(modal,'Member changes',result.events.map(e=>'<p><strong>'+esc(e.event.replaceAll('.',' '))+'</strong> · '+esc(new Date(e.created_at).toLocaleString())+'<br>'+esc(JSON.parse(e.details).name||'')+'</p>').join('')||'<p>No changes recorded yet.</p>');})];
    if(currentUser.role==='admin')actions.push(button('Reported items',async()=>{const result=await call('workforce/reports');shell(modal,'Reported items',result.reports.map(r=>'<article><p>'+esc(r.reason)+'</p><small>'+esc(new Date(r.created_at).toLocaleString())+'</small></article>').join('')||'<p>No reports.</p>');}));
    if(data.can_manage)actions.unshift(button('Edit group name',()=>form('Group name','Name',data.conversation.title,async title=>{await call(endpoint(chat)+'/profile','PATCH',{title});await host.refresh();await info();})),button('Edit description',()=>form('Group description','Description',data.profile.description,async description=>{await call(endpoint(chat)+'/profile','PATCH',{description});await info();})),button('Add member',()=>addMember(chat)),button('Invite to group via link',()=>invite(chat)),button('Create a similar group',()=>form('Create a similar group','New group name',data.conversation.title+' copy',async title=>{const result=await call(endpoint(chat)+'/actions/similar','POST',{title});panel.close();await host.refresh();await host.select(result.id);},{help:'Starts a new conversation with the same people. History is not copied; you can add or remove members afterward.'})));
    actions.push(...groupActions(chat).filter(a=>['Add to Favorites','Remove from Favorites','Add to list','Export chat','Clear chat','Exit group','Report group'].includes(a.label)));
    const quick={'Search messages':'Search','Media and reports':'Media','Add member':'Add','Invite to group via link':'Invite'};
    for(const a of actions){
      const b=document.createElement('button');b.type='button';labelButton(b,a.label);b.onclick=run(a.action);
      if(a.danger)b.classList.add('danger');
      let box;
      if(a.label==='Edit group name'||a.label==='Edit description'){
        box=panel.querySelector(a.label==='Edit group name'?'#wf-edit-title':'#wf-edit-description');b.classList.add('wf-edit-icon');b.title=a.label;
      }else if(quick[a.label]){
        box=panel.querySelector('.wf-group-quick');b.querySelector('span').textContent=quick[a.label];
      }else{
        const section=['Links','Starred messages'].includes(a.label)?'shared':/member/i.test(a.label)?'members':/notification|theme|Favorites|list/i.test(a.label)?'preferences':'manage';
        box=panel.querySelector('[data-section="'+section+'"]');
      }
      box.append(b);
    }
    const renderMembers=()=>{const q=document.getElementById('wf-member-search').value.toLowerCase();document.getElementById('wf-member-list').innerHTML=names.filter(p=>p.name.toLowerCase().includes(q)).map(p=>{const tag=data.member_preferences.find(t=>t.user_id===p.id)?.member_tag;return '<div class="wf-member"><span class="wf-chat-avatar">'+esc(p.name.slice(0,2))+'</span><div><strong>'+esc(p.id===currentUser.id?'You':p.name)+'</strong><small>'+esc(p.kind==='ai'?'AI teammate':[(p.id===data.conversation.creator_id?'Group creator':p.is_admin?'Group admin':'Member'),tag].filter(Boolean).join(' / '))+'</small></div>'+(data.can_manage&&p.kind==='human'&&p.id!==data.conversation.creator_id?'<button data-remove-member="'+esc(p.id)+'" aria-label="Remove '+esc(p.name)+'">Remove</button>':'')+'</div>';}).join('');};
    document.getElementById('wf-member-search').oninput=renderMembers;renderMembers();
    document.getElementById('wf-member-list').onclick=e=>{const b=e.target.closest('[data-remove-member]');if(b)form('Remove member','Remove this person from the group?',null,async()=>{await call(endpoint(chat)+'/members','POST',{action:'remove',user_id:b.dataset.removeMember});await host.refresh();await info();},{confirm:true});};
    document.getElementById('wf-group-avatar').onclick=()=>{if(!data.can_manage)return;const input=document.createElement('input');input.type='file';input.accept='image/png,image/jpeg,image/webp';input.onchange=run(async()=>{const file=input.files[0];if(!file)return;if(file.size>10*1024*1024)throw Error('Choose a photo under 10 MB.');const bitmap=await createImageBitmap(file),canvas=document.createElement('canvas');canvas.width=256;canvas.height=256;canvas.getContext('2d').drawImage(bitmap,0,0,256,256);bitmap.close();await call(endpoint(chat)+'/profile','PATCH',{avatar:{data:canvas.toDataURL('image/png').split(',')[1]}});await info();});input.click();};
  }
  function setReply(m){reply=m;replyBar.hidden=false;replyBar.innerHTML='<strong>Reply to '+esc(m.sender_name)+'</strong><span>'+esc(m.content.slice(0,150))+'</span><button type="button" aria-label="Cancel reply">×</button>';replyBar.querySelector('button').onclick=()=>clearReply();el('input').focus();}
  function clearReply(){reply=null;replyBar.hidden=true;replyBar.replaceChildren();}
  // Wrap null handling so cancel and switching conversations share one path.
  const replyTo=m=>m?setReply(m):clearReply();
  replyBar.addEventListener('click',e=>{if(e.target.closest('button'))clearReply();});
  async function forwardMessages(items){const options=current().chats.map(c=>[c.id,c.title]);form('Forward messages','Destination',options[0]?.[0],async conversation_id=>{for(const m of items){
      await call('workforce/messages/'+m.seq+'/forward','POST',{conversation_id,request_id:crypto.randomUUID()});
    }await host.refresh();},{options});}
  function messageActions(m){const chat=current().active;
    const actions=[button('Message info',async()=>{const data=await call('workforce/messages/'+m.seq+'/info');shell(modal,'Message info','<p>Sent by '+esc(data.sender_name)+' · '+esc(new Date(data.sent_at).toLocaleString())+'</p><h3>Read by</h3><p>'+esc(data.read_by.map(id=>current().participants.find(p=>p.id===id)?.name||'Member').join(', ')||'No read receipts yet.')+'</p>');}),button('Reply',()=>replyTo(m)),button('Copy',()=>navigator.clipboard.writeText(m.content)),button('React',()=>showMenu(['👍','❤️','😂','😮','😢','🙏','✅','🎉','👀','🔥'].map(emoji=>button(emoji,async()=>{await call('workforce/messages/'+m.seq+'/react','POST',{emoji});await host.refresh();})),document.querySelector('[data-seq="'+m.seq+'"]'))),button('Forward',()=>forwardMessages([m])),button(m.starred?'Unstar':'Star',async()=>{await call('workforce/messages/'+m.seq+'/star','POST',{});await host.refresh();})];
    if(state?.can_manage)actions.push(button(m.details?.pinned?'Unpin':'Pin',async()=>{await call('workforce/messages/'+m.seq+'/pin','POST',{});await host.refresh();}));
    if(m.images?.length||m.report_ready)actions.push(button('Download',()=>{const picture=m.report_ready?document.querySelector('[data-snapshot="'+m.task_id+'"] img'):null;if(m.report_ready&&!picture){host.error('The snapshot is still loading. Try again in a moment.');return;}const a=document.createElement('a');a.href=picture?.src||'/api/internal/workforce/images/'+m.images[0].id;a.download=m.report_ready?'sales-snapshot.png':'chat-image.png';a.click();}));
    if(m.kind==='human'&&m.sender_id!==currentUser.id)actions.push(button('Reply privately',()=>form('Private reply','Start a private conversation with '+m.sender_name+'?',null,async()=>{const result=await call('workforce/direct','POST',{user_id:m.sender_id});await host.refresh();await host.select(result.id);el('invoke').checked=false;el('input').value='Regarding your message: '+m.content.slice(0,500)+'\n\n';el('input').focus();},{confirm:true}))); 
    if(m.kind==='human'&&m.sender_id!==currentUser.id)actions.push(button('Message '+m.sender_name,async()=>{const result=await call('workforce/direct','POST',{user_id:m.sender_id});await host.refresh();await host.select(result.id);el('invoke').checked=false;el('input').focus();}));
    actions.push(button('Delete for me',()=>form('Delete for me','Hide this message from your account?',null,async()=>{await call('workforce/messages/'+m.seq+'/hide','POST',{});await host.refresh();},{confirm:true}),true));
    if(m.sender_id===currentUser.id||state?.can_manage)actions.push(button('Delete for everyone',()=>form('Delete for everyone','Delete this message and its attachments for all group members?',null,async()=>{await call('workforce/messages/'+m.seq+'/delete','POST',{});await host.refresh();},{confirm:true,help:'This also cancels an active assignment attached to the message.'}),true));
    actions.push(button('Report',()=>report(chat,m.seq),true));return actions;
  }
  function selectionUI(){selectionBar.hidden=!selecting;selectionBar.innerHTML='<span>'+selected.size+' selected</span><button data-bulk="forward">Forward</button><button data-bulk="star">Star</button><button data-bulk="hide">Delete for me</button><button data-bulk="cancel">Cancel</button>';}
  selectionBar.onclick=run(async e=>{const action=e.target.dataset.bulk;if(!action)return;if(action==='cancel'){selecting=false;selected.clear();selectionUI();host.renderMessages();return;}const items=current().messages.filter(m=>selected.has(m.seq));if(!items.length)return;if(action==='forward'){await forwardMessages(items);return;}form('Selected messages',action==='hide'?'Hide the selected messages for your account?':'Star the selected messages?',null,async()=>{for(const m of items)if(action!=='star'||!m.starred)await call('workforce/messages/'+m.seq+'/'+action,'POST',{});selected.clear();selecting=false;selectionUI();await host.refresh();},{confirm:true});});
  el('chats').addEventListener('click',e=>{const b=e.target.closest('[data-chat-options]');if(b){e.stopPropagation();showMenu(groupActions(b.dataset.chatOptions),b);}});
  el('chats').addEventListener('contextmenu',e=>{const b=e.target.closest('[data-chat]');if(b){e.preventDefault();showMenu(groupActions(b.dataset.chat),b,e);}});
  more.onclick=()=>{if(current().active)showMenu(groupActions(current().active),more);};
  const heading=document.querySelector('.wf-chat-heading');heading.tabIndex=0;heading.role='button';heading.setAttribute('aria-label','Group info');heading.onclick=run(info);heading.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();run(info)();}};
  el('messages').addEventListener('contextmenu',e=>{const article=e.target.closest('[data-seq]');if(article){e.preventDefault();const m=current().messages.find(m=>m.seq===Number(article.dataset.seq));if(m)showMenu(messageActions(m),article,e);}});
  el('messages').addEventListener('click',e=>{const b=e.target.closest('[data-message-options]');if(b){const m=current().messages.find(m=>m.seq===Number(b.dataset.messageOptions));if(m)showMenu(messageActions(m),b);}const check=e.target.closest('[data-select-message]');if(check){const seq=Number(check.dataset.selectMessage);check.checked?selected.add(seq):selected.delete(seq);selectionUI();}});
  return {
    filter(chats){const lists=[...new Set(chats.map(c=>c.preferences?.list_name).filter(Boolean))];const select=toolbar.querySelector('select');for(const old of select.querySelectorAll('[data-list]'))old.remove();lists.forEach(name=>{const o=new Option(name,'list:'+name);o.dataset.list='1';select.add(o);});select.value=filter;
      return chats.filter(c=>filter==='archived'?c.preferences?.archived:!c.preferences?.archived&&(filter==='all'||filter==='favorites'&&c.preferences?.favorite||filter==='unread'&&(c.preferences?.unread||(c.last_seq||0)>(c.preferences?.read_seq||0))||filter.startsWith('list:')&&c.preferences?.list_name===filter.slice(5)));},
    chatBadge(c){return (c.preferences?.pinned?'📌 ':'')+(c.preferences?.favorite?'☆ ':'')+(c.preferences?.muted_until>Date.now()/1000?'🔕 ':'');},
    beforeMessage(m){return (selecting?'<input type="checkbox" data-select-message="'+m.seq+'" aria-label="Select message" '+(selected.has(m.seq)?'checked':'')+'>':'')+(m.details?.forwarded?'<small class="wf-forwarded">Forwarded</small>':'')+(m.reply?'<blockquote class="wf-quoted"><strong>'+esc(m.reply.sender_name)+'</strong><br>'+esc(m.reply.content)+'</blockquote>':'');},
    afterMessage(m){const counts={};(m.reactions||[]).forEach(r=>counts[r.emoji]=(counts[r.emoji]||0)+1);return '<div class="wf-message-meta">'+(m.starred?'★ ':'')+(m.details?.pinned?'📌 ':'')+Object.entries(counts).map(([emoji,n])=>'<span>'+esc(emoji)+' '+n+'</span>').join('')+'<button type="button" data-message-options="'+m.seq+'" aria-label="Message options">⌄</button></div>';},
    onState(data){const changed=state?.conversation?.id===data.conversation.id&&state.revision!==data.revision;state=data;const avatar=document.querySelector('.wf-chat-head>.wf-chat-avatar');const src=data.profile.has_avatar?'/api/internal/'+endpoint(data.conversation.id)+'/avatar?v='+data.revision:null;if(src){if(avatar.querySelector('img')?.getAttribute('src')!==src)avatar.innerHTML='<img alt="Group photo" src="'+esc(src)+'">';}else avatar.textContent='A\u2197';el('active').dataset.theme=data.preferences.theme;const latest=data.messages.at(-1)?.seq||0;if(latest>data.preferences.read_seq&&!document.hidden)call(endpoint(data.conversation.id)+'/preferences','PATCH',{read_seq:latest,unread:0}).catch(()=>{});return changed;},
    replySeq(){return reply?.seq||null;},sent(){clearReply();},
    reset(){epoch++;hideMenu();state=null;clearReply();selecting=false;selected.clear();selectionUI();panel.close();modal.close();memoryPanel.close();panel.replaceChildren();modal.replaceChildren();memoryPanel.replaceChildren();},
    async loaded(){const match=location.hash.match(/^#invite=([A-Za-z0-9_-]+)$/);if(match){history.replaceState(null,'',location.pathname);form('Join group','Join the group from this invitation?',null,async()=>{const result=await call('workforce/invites/join','POST',{token:match[1]});await host.refresh();await host.select(result.id);},{confirm:true,help:'You must be signed in to the portal. Existing group history becomes visible after joining.'});}}
  };
};
