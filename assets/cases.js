'use strict';
(() => {
  const el = name => document.getElementById('case-' + name);
  const esc = escapeHTML;
  const day = () => new Intl.DateTimeFormat('en-CA', {timeZone:'America/Chicago', year:'numeric', month:'2-digit', day:'2-digit'}).format(new Date());
  const dateText = value => new Date(value.slice(0,10) + 'T12:00:00').toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});
  const statusText = status => ({pending:'Pending',approved:'Approved',not_approved:'Not Approved'}[status] || status);
  const badge = status => '<span class="case-status case-status-' + esc(status) + '">' + esc(statusText(status)) + '</span>';
  let epoch=0, listSequence=0, reportSequence=0, detailSequence=0, timer=null, draftId=null, sending=false;
  let directory=[], selected={to:[],cc:[]}, pictures=[], detail=null;
  let locations=[], editLocations=[];
  let editing=null, editUsers=[], editSelected={to:[],cc:[]}, editPictures=[], removedPictures=new Set(), savingEdit=false, editSequence=0;
  const offsets={cases:0,inbox:0,'case-report':0}, more={};
  const admin=()=>currentUser?.role==='admin';
  const error=err=>notice(err.message,true);
  const actionButtons = r => '<div class="case-review-actions">'+(r.can_edit?'<button class="subtle" data-case-edit="'+r.id+'">Edit</button><button class="subtle danger" data-case-delete="'+r.id+'" data-revision="'+r.revision+'">Delete</button>':'')+(admin()?'<button class="case-approve" data-case-review="'+r.id+'" data-revision="'+r.revision+'" data-status="approved" '+(r.status==='approved'?'disabled':'')+'>Approved</button><button class="subtle" data-case-review="'+r.id+'" data-revision="'+r.revision+'" data-status="not_approved" '+(r.status==='not_approved'?'disabled':'')+'>Not Approved</button>':'')+'</div>';

  function pager(name, prefix) {
    el(prefix+'prev').disabled=offsets[name]===0;
    el(prefix+'next').disabled=!more[name];
    el(prefix+'page-number').textContent='Page '+(Math.floor(offsets[name]/50)+1);
  }
  async function unread() {
    const version=epoch;
    if(!currentUser||currentUser.rest_mode||currentUser.must_change_password||!canOpen('inbox'))return;
    try {
      const result=await api('cases/unread');
      if(version!==epoch||!currentUser)return;
      el('unread').textContent=String(result.count);el('unread').hidden=!result.count;
      el('unread').setAttribute('aria-label',result.count+' unread cases');
    } catch (_) { /* The next poll retries; api handles session expiry. */ }
  }
  function start() {
    clearInterval(timer);unread();
    timer=setInterval(()=>{
      if(document.hidden||!currentUser||currentUser.rest_mode)return;
      unread();
      if(page==='inbox'&&!el('detail-dialog').open&&!el('compose-dialog').open&&!el('edit-dialog').open)loadList('inbox').catch(error);
    },30000);
  }
  async function loadList(name) {
    const sequence=++listSequence, version=epoch, inbox=name==='inbox';
    el('scope-label').hidden=!admin();
    const folder=inbox?'inbox':admin()?el('scope').value:'sent';
    const target=el(inbox?'inbox':'history');
    const result=await api('cases?'+new URLSearchParams({folder,offset:offsets[name],status:inbox?'':el('status').value}));
    if(version!==epoch||sequence!==listSequence||!currentUser||page!==name)return;
    const rows=result.cases;
    more[name]=result.has_more;
    if(!rows.length)target.innerHTML='<div class="case-empty"><span aria-hidden="true">✉</span><h3>'+(inbox?'Your inbox is clear':'No cases here yet')+'</h3><p>'+(inbox?'Cases sent to you or copied to you will appear here.':'Select + Drop cases to draft your first case, or adjust the status filter.')+'</p></div>';
    else target.innerHTML='<div class="table-wrap"><table class="case-list-table"><thead><tr><th>Case / employee</th><th>From</th><th>Violation date</th><th>Case type</th><th>Status</th>'+'<th>Actions</th>'+'</tr></thead><tbody>'+rows.map(r=>'<tr class="'+(r.unread?'case-is-unread':'')+'"><td><button class="case-subject-button" data-case-open="'+r.id+'">'+(r.unread?'<span class="case-dot" aria-label="Unread"></span>':'')+esc(r.subject)+'</button><small>'+esc(r.employee_name)+' · '+esc(r.employee_ntid)+(r.attachment_count?' · '+r.attachment_count+' picture'+(r.attachment_count===1?'':'s'):'')+'</small>'+(r.store_name?'<small>'+esc(r.dealer)+' / '+esc(r.store_name)+'</small>':'')+'</td><td>'+esc(r.sender_name)+'</td><td>'+esc(dateText(r.violation_date))+'</td><td>'+esc(r.case_type)+'</td><td>'+badge(r.status)+'</td>'+'<td>'+actionButtons(r)+'</td>'+'</tr>').join('')+'</tbody></table></div>';
    pager(name,inbox?'inbox-':'');
  }
  async function loadReport() {
    if(!admin())return;
    if(!el('report-start').value){el('report-start').value=day().slice(0,7)+'-01';el('report-end').value=day();}
    const start=el('report-start').value,end=el('report-end').value;
    if(!start||!end||start>end)throw new Error('Select a valid date range.');
    const sequence=++reportSequence,version=epoch;
    const result=await api('cases/report?'+new URLSearchParams({start,end,offset:offsets['case-report']}));
    if(sequence!==reportSequence||version!==epoch||!currentUser||page!=='case-report')return;
    const approved=result.ranking.reduce((sum,r)=>sum+Number(r.approved),0);
    el('report-summary').innerHTML=[['Cases submitted',result.total],['Submitting users',result.ranking.length],['Approved',approved]].map(([label,value])=>'<div class="panel"><span>'+label+'</span><strong>'+value+'</strong></div>').join('');
    el('ranking').innerHTML=result.ranking.length?'<ol class="case-ranking">'+result.ranking.map(r=>'<li><span><strong>'+esc(r.user_name)+'</strong><small>'+esc(r.username)+' · '+r.approved+' approved · '+r.pending+' pending · '+r.not_approved+' not approved</small></span><b>'+r.submitted+'<small>submitted</small></b></li>').join('')+'</ol>':'<p class="muted">No submissions in this date range.</p>';
    el('report-table').innerHTML='<div class="table-wrap"><table><thead><tr><th>Date</th><th>User</th><th>Employee NTID</th><th>Employee Name</th><th>Case Type</th></tr></thead><tbody>'+result.rows.map(r=>'<tr><td><button class="case-subject-button" data-case-open="'+r.id+'">'+esc(dateText(r.date))+'</button></td><td>'+esc(r.user)+'</td><td>'+esc(r.employee_ntid)+'</td><td>'+esc(r.employee_name)+'</td><td>'+esc(r.case_type)+'</td></tr>').join('')+'</tbody></table></div>'+(!result.rows.length?'<div class="empty">No cases in this date range.</div>':'');
    more['case-report']=result.has_more;pager('case-report','report-');
  }
  async function load(name) {
    document.querySelectorAll('[data-case-compose]').forEach(button=>button.hidden=!canOpen('cases'));
    if(name==='case-report')await loadReport();else await loadList(name);
    await unread();
  }
  function recipientOptions() {
    for(const kind of ['to','cc']) {
      const used=new Set([...selected.to,...selected.cc]);
      el(kind).replaceChildren(new Option('Choose a recipient…',''),...directory.filter(u=>!used.has(u.id)).map(u=>new Option((u.display_name||u.username)+' ('+u.username+')',u.id)));
      el(kind+'-chips').innerHTML=selected[kind].map(id=>{
        const user=directory.find(u=>u.id===id);
        return '<button type="button" class="case-chip" data-recipient-kind="'+kind+'" data-recipient-id="'+id+'" aria-label="Remove '+esc(user?.display_name||user?.username)+'">'+esc(user?.display_name||user?.username)+' <span aria-hidden="true">×</span></button>';
      }).join('');
    }
  }
  for(const kind of ['to','cc'])el(kind).onchange=()=>{
    if(el(kind).value)selected[kind].push(el(kind).value);
    recipientOptions();
  };
  el('type').onchange=()=>{const custom=el('type').value==='Custom';el('custom-label').hidden=!custom;el('custom').required=custom;};
  function storeOptions(prefix, rows, selectedStore='') {
    const dealer=el(prefix+'dealer').value;
    const matches=rows.filter(s=>s.dealer===dealer);
    el(prefix+'store').replaceChildren(new Option('Select a store…',''),...matches.map(s=>{
      const duplicate=matches.filter(other=>other.store_name===s.store_name).length>1;
      return new Option(s.store_name+(duplicate&&s.market?' — '+s.market:''),s.store_id);
    }));
    el(prefix+'store').disabled=!dealer;
    el(prefix+'store').value=selectedStore;
    if(prefix)el(prefix+'store').required=!!dealer;
  }
  function locationOptions(prefix, rows, dealer='', sid='') {
    el(prefix+'dealer').replaceChildren(new Option(prefix?'Not specified (existing case)':'Select a dealer…',''),
      ...[...new Set(rows.map(s=>s.dealer))].sort().map(name=>new Option(name,name)));
    el(prefix+'dealer').value=dealer;
    storeOptions(prefix,rows,sid);
  }
  el('dealer').onchange=()=>storeOptions('',locations);
  el('edit-dealer').onchange=()=>storeOptions('edit-',editLocations);
  async function compose() {
    if(sending||!canOpen('cases'))return;
    const version=epoch;
    try {
      const result=await api('cases/recipients');
      if(version!==epoch||!currentUser)return;
      directory=result.users;locations=result.stores;
      const previousDealer=draftId?el('dealer').value:'',previousStore=draftId?el('store').value:'';
      if(!draftId){
        el('compose-form').reset();selected={to:[],cc:[]};pictures=[];
        draftId=crypto.randomUUID();
        el('date').value=day();el('date').max=day();
        el('type').replaceChildren(new Option('Select a case type…',''),...result.case_types.map(t=>new Option(t,t)));
        el('custom-label').hidden=true;el('custom').required=false;drawPictures();
      }
      locationOptions('',locations,previousDealer,previousStore);
      recipientOptions();el('compose-error').textContent='';el('compose-dialog').showModal();
    }catch(err){error(err);}
  }
  function drawPictures() {
    el('draft-pictures').innerHTML=pictures.map((file,i)=>'<div class="case-picture-chip"><span>'+esc(file.name)+' <small>'+Math.ceil(file.size/1024)+' KB</small></span><button type="button" class="subtle" data-remove-picture="'+i+'" aria-label="Remove '+esc(file.name)+'">×</button></div>').join('');
  }
  el('pictures').onchange=()=>{
    const next=[...pictures,...el('pictures').files];el('pictures').value='';
    if(next.length>5||next.reduce((sum,f)=>sum+f.size,0)>2*1024*1024){el('compose-error').textContent='Attach up to 5 pictures totaling 2 MB.';return;}
    if(next.some(f=>!['image/jpeg','image/png','image/webp'].includes(f.type))){el('compose-error').textContent='Choose JPG, PNG, or WebP pictures.';return;}
    pictures=next;el('compose-error').textContent='';drawPictures();
  };
  const encode=file=>new Promise((resolve,reject)=>{const reader=new FileReader();reader.onerror=()=>reject(new Error('Unable to read '+file.name));reader.onload=()=>resolve({filename:file.name,content:String(reader.result).split(',')[1]});reader.readAsDataURL(file);});
  el('compose-form').onsubmit=async event=>{
    event.preventDefault();if(sending)return;
    if(!selected.to.length){el('compose-error').textContent='Select at least one To recipient.';el('to').focus();return;}
    sending=true;el('send').disabled=true;el('send').textContent='Sending…';el('compose-error').textContent='';
    const version=epoch;
    try {
      const payload={request_id:draftId,dealer:el('dealer').value,store_id:el('store').value,violation_date:el('date').value,case_type:el('type').value,custom_type:el('custom').value,employee_ntid:el('ntid').value,employee_name:el('employee').value,subject:el('subject').value,body:el('body').value,to:[...selected.to],cc:[...selected.cc],attachments:await Promise.all(pictures.map(encode))};
      if(version!==epoch||!currentUser)return;
      const result=await api('cases','POST',payload);
      if(version!==epoch||!currentUser)return;
      draftId=null;pictures=[];selected={to:[],cc:[]};el('compose-form').reset();el('compose-dialog').close();
      notice(result.message);
      if(['cases','inbox','case-report'].includes(page))await load(page).catch(()=>notice(result.message+' Refresh to update the list.'));
      await unread();
    }catch(err){if(version===epoch)el('compose-error').textContent=err.message;}
    finally{if(version===epoch){sending=false;el('send').disabled=false;el('send').textContent='Send case →';}}
  };
  async function openCase(id) {
    const sequence=++detailSequence,version=epoch;
    try {
      const data=await api('cases/'+id);
      if(sequence!==detailSequence||version!==epoch||!currentUser)return;
      detail=data.case;
      el('detail-subject').textContent=detail.subject;el('detail-error').textContent='';
      const recipients=kind=>data.recipients.filter(r=>r.kind===kind).map(r=>r.recipient_name).join(', ')||'—';
      const fields=[['From',detail.sender_name],['To',recipients('to')],['CC',recipients('cc')],['Sent',new Date(detail.submitted_at).toLocaleString()],['Violation date',dateText(detail.violation_date)],['Employee',detail.employee_name+' · '+detail.employee_ntid],['Case type',detail.case_type],['Dealer',detail.dealer||'Not specified'],['Store Name',detail.store_name||'Not specified']];
      el('detail-content').innerHTML='<div class="case-detail-status">'+badge(detail.status)+'</div><dl class="case-details">'+fields.map(([label,value])=>'<div><dt>'+label+'</dt><dd>'+esc(value)+'</dd></div>').join('')+'</dl><div class="case-message-body">'+esc(detail.body)+'</div>'+(data.attachments.length?'<h3>Pictures</h3><div class="case-photos">'+data.attachments.map(a=>{const url='/api/internal/cases/'+id+'/attachments/'+a.id;return '<a href="'+url+'?download=1"><img loading="lazy" src="'+url+'" alt="'+esc(a.filename)+'"><span>'+esc(a.filename)+'</span></a>';}).join('')+'</div>':'')+actionButtons(detail)+(data.reviews.length?'<div class="case-review-history"><h3>Review history</h3>'+data.reviews.map(r=>'<p>'+esc(r.reviewer)+' · '+esc(statusText(r.status))+' · '+esc(new Date(r.reviewed_at).toLocaleString())+'</p>').join('')+'</div>':'');
      if(data.edits?.length) {
        const labels={dealer:'Dealer',store_id:'Store',store_name:'Store Name',to:'To',cc:'CC',sender:'Sender',pictures:'Pictures',violation_date:'Violation date',employee_ntid:'Employee NTID',employee_name:'Employee name',case_type:'Case type',subject:'Subject',body:'Body'};
        el('detail-content').insertAdjacentHTML('beforeend','<div class="case-review-history"><h3>Edit history</h3>'+data.edits.map(e=>'<p>'+esc(e.editor)+' · '+esc(e.changed_fields.map(k=>labels[k]||k).join(', '))+' · '+esc(new Date(e.edited_at).toLocaleString())+'</p>').join('')+'</div>');
      }
      if(!el('detail-dialog').open)el('detail-dialog').showModal();
      await api('cases/'+id+'/read','POST',{});await unread();
      if(['cases','inbox'].includes(page))await loadList(page);
    }catch(err){error(err);}
  }
  async function review(button) {
    const id=button.dataset.caseReview;button.disabled=true;
    const version=epoch;
    try {
      const result=await api('cases/'+id+'/review','PATCH',{status:button.dataset.status,revision:Number(button.dataset.revision)});
      if(version!==epoch||!currentUser)return;
      if(el('detail-dialog').open&&detail?.id===id)await openCase(id);
      if(['cases','inbox','case-report'].includes(page))await load(page);
      notice(result.message);
    }catch(err){if(version===epoch){if(el('detail-dialog').open)el('detail-error').textContent=err.message;else error(err);}}
    finally{button.disabled=false;}
  }
  function editRecipients() {
    const used=new Set([...editSelected.to,...editSelected.cc]);
    for(const kind of ['to','cc']) {
      el('edit-'+kind).replaceChildren(new Option('Choose a recipient…',''),...editUsers.filter(u=>!u.retainedOnly&&!used.has(u.id)).map(u=>new Option((u.display_name||u.username)+' ('+u.username+')',u.id)));
      el('edit-'+kind+'-chips').innerHTML=editSelected[kind].map(id=>{
        const user=editUsers.find(u=>u.id===id);
        return '<button type="button" class="case-chip" data-edit-recipient-kind="'+kind+'" data-edit-recipient-id="'+id+'" aria-label="Remove '+esc(user?.display_name||user?.username)+'">'+esc(user?.display_name||user?.username)+' ×</button>';
      }).join('');
    }
  }
  for(const kind of ['to','cc'])el('edit-'+kind).onchange=()=>{if(el('edit-'+kind).value)editSelected[kind].push(el('edit-'+kind).value);editRecipients();};
  el('edit-type').onchange=()=>{const custom=el('edit-type').value==='Custom';el('edit-custom-label').hidden=!custom;el('edit-custom').required=custom;};
  function editPictureList() {
    el('edit-picture-list').innerHTML=(editing?.attachments||[]).filter(a=>!removedPictures.has(a.id)).map(a=>'<div class="case-picture-chip"><span>'+esc(a.filename)+'</span><button type="button" class="subtle" data-edit-remove-existing="'+a.id+'" aria-label="Remove '+esc(a.filename)+'">×</button></div>').join('')+editPictures.map((a,i)=>'<div class="case-picture-chip"><span>'+esc(a.name)+' (new)</span><button type="button" class="subtle" data-edit-remove-new="'+i+'" aria-label="Remove '+esc(a.name)+'">×</button></div>').join('');
  }
  async function editCase(id) {
    if(savingEdit)return;
    const version=epoch,sequence=++editSequence;
    try {
      const [data,options]=await Promise.all([api('cases/'+id),api('cases/recipients')]);
      if(version!==epoch||sequence!==editSequence||!currentUser)return;
      if(!data.case.can_edit)throw new Error('Only admins and the current sender can edit this case.');
      editing=data;editUsers=options.users;editPictures=[];removedPictures=new Set();
      editSelected={to:data.recipients.filter(r=>r.kind==='to').map(r=>r.user_id),cc:data.recipients.filter(r=>r.kind==='cc').map(r=>r.user_id)};
      for(const recipient of data.recipients)if(!editUsers.some(u=>u.id===recipient.user_id))editUsers.push({id:recipient.user_id,display_name:recipient.recipient_name,username:'Unavailable account',retainedOnly:true});
      el('edit-form').reset();el('edit-error').textContent='';
      el('edit-fields').hidden=!admin();el('edit-fields').disabled=!admin();
      el('edit-permissions').textContent=admin()?'You can edit case details, pictures, sender, To, and CC.':'You can edit only To and CC on your own case.';
      editRecipients();
      if(admin()) {
        const row=data.case;
        editLocations=[...options.stores];
        if(row.dealer&&!editLocations.some(s=>s.dealer===row.dealer&&s.store_id===row.store_id))
          editLocations.push({dealer:row.dealer,store_id:row.store_id,store_name:row.store_name+' (previous selection)',market:''});
        locationOptions('edit-',editLocations,row.dealer,row.store_id);
        el('edit-dealer').required=!!row.dealer;
        el('edit-sender').replaceChildren(...editUsers.filter(u=>!u.retainedOnly).map(u=>new Option((u.display_name||u.username)+' ('+u.username+')',u.id)));
        if(![...el('edit-sender').options].some(o=>o.value===row.sender_id))el('edit-sender').add(new Option(row.sender_name+' (current sender)',row.sender_id));
        el('edit-sender').value=row.sender_id;
        el('edit-date').value=row.violation_date;el('edit-date').max=day();
        el('edit-type').replaceChildren(...options.case_types.map(t=>new Option(t,t)));
        const custom=!options.case_types.includes(row.case_type)||row.case_type==='Custom';
        el('edit-type').value=custom?'Custom':row.case_type;el('edit-custom').value=custom?row.case_type:'';el('edit-type').onchange();
        el('edit-ntid').value=row.employee_ntid;el('edit-employee').value=row.employee_name;
        el('edit-subject').value=row.subject;el('edit-body').value=row.body;editPictureList();
      }
      el('detail-dialog').close();el('edit-dialog').showModal();
    }catch(err){error(err);}
  }
  el('edit-pictures').onchange=()=>{
    const next=[...editPictures,...el('edit-pictures').files];el('edit-pictures').value='';
    const retained=editing.attachments.filter(a=>!removedPictures.has(a.id));
    if(next.length+retained.length>5||next.reduce((s,f)=>s+f.size,0)+retained.reduce((s,f)=>s+f.size,0)>2*1024*1024){el('edit-error').textContent='Attach up to 5 pictures totaling 2 MB, including existing pictures.';return;}
    if(next.some(f=>!['image/jpeg','image/png','image/webp'].includes(f.type))){el('edit-error').textContent='Choose JPG, PNG, or WebP pictures.';return;}
    editPictures=next;el('edit-error').textContent='';editPictureList();
  };
  el('edit-form').onsubmit=async event=>{
    event.preventDefault();if(savingEdit||!editing)return;
    if(!editSelected.to.length){el('edit-error').textContent='Select at least one To recipient.';return;}
    savingEdit=true;el('edit-save').disabled=true;el('edit-error').textContent='';
    const version=epoch,id=editing.case.id;
    try {
      const payload={revision:editing.case.revision,to:[...editSelected.to],cc:[...editSelected.cc]};
      if(admin())Object.assign(payload,{sender_id:el('edit-sender').value,dealer:el('edit-dealer').value,store_id:el('edit-store').value,violation_date:el('edit-date').value,case_type:el('edit-type').value,custom_type:el('edit-custom').value,employee_ntid:el('edit-ntid').value,employee_name:el('edit-employee').value,subject:el('edit-subject').value,body:el('edit-body').value,remove_attachments:[...removedPictures],attachments:await Promise.all(editPictures.map(encode))});
      if(version!==epoch||!currentUser)return;
      const result=await api('cases/'+id,'PATCH',payload);
      if(version!==epoch||!currentUser)return;
      el('edit-dialog').close();editing=null;
      if(['cases','inbox','case-report'].includes(page))await load(page).catch(()=>{});
      await openCase(id);notice(result.message);
    }catch(err){if(version===epoch)el('edit-error').textContent=err.message;}
    finally{if(version===epoch){savingEdit=false;el('edit-save').disabled=false;}}
  };
  async function deleteCase(button) {
    if(!confirm('Delete this case? It will be removed from case history, recipient inboxes, and reports.'))return;
    button.disabled=true;const version=epoch,id=button.dataset.caseDelete;
    try {
      const result=await api('cases/'+id,'DELETE',{revision:Number(button.dataset.revision)});
      if(version!==epoch||!currentUser)return;
      if(detail?.id===id){el('detail-dialog').close();el('detail-content').replaceChildren();el('detail-subject').textContent='';detail=null;}
      if(editing?.case.id===id){el('edit-dialog').close();el('edit-form').reset();editing=null;}
      if(['cases','inbox','case-report'].includes(page))await load(page).catch(()=>{});
      await unread();notice(result.message);
    }catch(err){if(version===epoch){if(el('detail-dialog').open)el('detail-error').textContent=err.message;else error(err);}}
    finally{button.disabled=false;}
  }
  document.addEventListener('click',event=>{
    if(event.target.closest('[data-case-compose]'))compose();
    const open=event.target.closest('[data-case-open]');if(open)openCase(open.dataset.caseOpen);
    const button=event.target.closest('[data-case-review]');if(button)review(button);
    const edit=event.target.closest('[data-case-edit]');if(edit)editCase(edit.dataset.caseEdit);
    const deletion=event.target.closest('[data-case-delete]');if(deletion)deleteCase(deletion);
    const editChip=event.target.closest('[data-edit-recipient-id]');if(editChip){editSelected[editChip.dataset.editRecipientKind]=editSelected[editChip.dataset.editRecipientKind].filter(id=>id!==editChip.dataset.editRecipientId);editRecipients();}
    const oldPicture=event.target.closest('[data-edit-remove-existing]');if(oldPicture){removedPictures.add(oldPicture.dataset.editRemoveExisting);editPictureList();}
    const newPicture=event.target.closest('[data-edit-remove-new]');if(newPicture){editPictures.splice(Number(newPicture.dataset.editRemoveNew),1);editPictureList();}
    const chip=event.target.closest('[data-recipient-id]');if(chip){selected[chip.dataset.recipientKind]=selected[chip.dataset.recipientKind].filter(id=>id!==chip.dataset.recipientId);recipientOptions();}
    const picture=event.target.closest('[data-remove-picture]');if(picture){pictures.splice(Number(picture.dataset.removePicture),1);drawPictures();}
  });
  for(const [name,prefix] of [['cases',''],['inbox','inbox-'],['case-report','report-']]){
    el(prefix+'prev').onclick=()=>{offsets[name]=Math.max(0,offsets[name]-50);load(name).catch(error);};
    el(prefix+'next').onclick=()=>{if(more[name]){offsets[name]+=50;load(name).catch(error);}};
  }
  for(const name of ['scope','status'])el(name).onchange=()=>{offsets.cases=0;loadList('cases').catch(error);};
  el('refresh').onclick=()=>load('cases').catch(error);
  el('inbox-refresh').onclick=()=>load('inbox').catch(error);
  el('report-filter').onsubmit=event=>{event.preventDefault();offsets['case-report']=0;loadReport().catch(error);};
  function clear() {
    epoch++;listSequence++;reportSequence++;detailSequence++;clearInterval(timer);timer=null;
    editSequence++;editing=null;editUsers=[];editSelected={to:[],cc:[]};editPictures=[];removedPictures=new Set();savingEdit=false;
    el('edit-form').reset();el('edit-fields').disabled=false;el('edit-error').textContent='';el('edit-save').disabled=false;
    ['edit-to','edit-cc','edit-to-chips','edit-cc-chips','edit-sender','edit-picture-list'].forEach(name=>el(name).replaceChildren());el('edit-dialog').close();
    draftId=null;detail=null;directory=[];locations=[];editLocations=[];selected={to:[],cc:[]};pictures=[];sending=false;
    ['dealer','store','edit-dealer','edit-store'].forEach(name=>el(name).replaceChildren());
    Object.keys(offsets).forEach(key=>offsets[key]=0);
    ['history','inbox','report-summary','ranking','report-table','detail-content','detail-subject','to-chips','cc-chips','draft-pictures'].forEach(name=>el(name).replaceChildren());
    el('compose-form').reset();el('report-filter').reset();el('compose-error').textContent='';el('detail-error').textContent='';
    el('to').replaceChildren();el('cc').replaceChildren();el('unread').hidden=true;el('unread').textContent='';el('send').disabled=false;el('send').textContent='Send case →';
    el('compose-dialog').close();el('detail-dialog').close();
  }
  window.casesDashboard={load,start,clear};
})();
