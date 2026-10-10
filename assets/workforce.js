'use strict';
(() => {
  const el = name => document.getElementById('wf-' + name);
  const endpoint = 'workforce/';
  let generation = 0, selection = 0, active = null, chats = [], messages = [], tasks = [], status = null;
  let polling = false, ticks = 0, pendingSend = null, sending = false;
  let participants = [], canAddAgents = false, mentionOptions = [], mentionIndex = 0, mentionStart = -1;
  let attachedImages = [], processingImages = false;
  const reportSnapshots = new Map();
  let controls = null;
  const seen = new Map();
  const valid = token => token === generation && currentUser && !currentUser.rest_mode && page === 'workforce';
  const error = message => { el('error').textContent = message || ''; el('error').hidden = !message; };
  const uuid = () => crypto.randomUUID();
  function dialog(name, title, bodyHTML) {
    const node = document.createElement('dialog'); node.id = 'wf-' + name; node.className = 'wf-dialog';
    node.innerHTML = '<div class="wf-close-row"><h2>' + title + '</h2><button type="button" class="subtle close" aria-label="Close ' + title + '">×</button></div>' + bodyHTML;
    node.querySelector('.close').onclick = () => node.close(); document.body.append(node); return node;
  }
  const newDialog = dialog('new-dialog', 'Start a conversation', '<form id="wf-new-form"><p>Your AI Manager and Operations agent will join this conversation.</p><div class="field"><label for="wf-new-title">Conversation name</label><input id="wf-new-title" required maxlength="80" placeholder="Daily operations"></div><div class="field" id="wf-people-field" hidden><label for="wf-people">Add team members (optional)</label><select id="wf-people" multiple aria-describedby="wf-people-help"></select><p id="wf-people-help">Hold Ctrl or Command to select multiple people. Leave empty for a private AI chat.</p></div><p id="wf-new-error" class="error" role="alert"></p><div class="actions"><button type="submit" class="primary">Create conversation</button></div></form>');
  const directory = dialog('directory-dialog', 'Your AI employees', '<p>Add specialist bots to a group by asking @manager. Mention a joined bot to get its help.</p><div id="wf-employees"></div><p>Specialists advise and draft. Adding a bot does not connect private HR, finance or other business records.</p>');
  const settings = dialog('settings-dialog', 'Connection & models', '<div id="wf-connection" class="wf-connection"></div><form id="wf-model-form"><div class="field"><label for="wf-model">Default AI model</label><select id="wf-model"></select></div><p>Changes apply to new assignments. Current assignments keep their original model.</p><p id="wf-settings-error" class="error" role="alert"></p><button class="primary" type="submit" id="wf-model-save">Save model</button></form><p id="wf-worker-help">Start the AI worker on your company AI computer to process queued assignments.</p><div id="wf-integrations" class="wf-connection"></div>');
  const auditDialog = dialog('audit-dialog', 'Assignment activity', '<div id="wf-audit-content"></div>');
  const imageDialog = dialog('image-dialog', 'Chat image', '<img id="wf-full-image" alt="Chat attachment"><button type="button" id="wf-copy-snapshot" hidden>Copy Snapshot</button> <a id="wf-download-image" download>Download image</a><p id="wf-image-feedback" role="status"></p>');
  el('copy-snapshot').onclick = async () => {
    const button = el('copy-snapshot'); button.disabled = true;
    try {
      const bytes = Uint8Array.from(atob(el('full-image').src.split(',')[1]), c => c.charCodeAt(0));
      const blob = new Blob([bytes], {type:'image/png'});
      await navigator.clipboard.write([new ClipboardItem({'image/png': blob})]);
      el('image-feedback').textContent = 'Snapshot copied.';
    } catch { el('image-feedback').textContent = 'Clipboard unavailable. Use Download image to save the snapshot.'; }
    finally { button.disabled = false; }
  };

  function snapshotMarkup(message) {
    if (!message.report_ready) return imageMarkup(message.images);
    return '<button type="button" class="wf-chat-image wf-sales-snapshot" data-snapshot="' + escapeHTML(message.task_id) + '" aria-label="Open Sales Update Copy Snapshot"><span>Loading Sales Update snapshot…</span></button>';
  }
  async function loadSnapshots() {
    const token = generation, selected = selection;
    for (const button of el('messages').querySelectorAll('[data-snapshot]')) {
      const id = button.dataset.snapshot;
      try {
        if (!reportSnapshots.has(id)) reportSnapshots.set(id, api(endpoint + 'tasks/' + id + '/snapshot').then(report => {
          if (!valid(token) || selected !== selection) return null;
          return window.salesSnapshot.render(report, report.filters).toDataURL('image/png');
        }));
        const url = await reportSnapshots.get(id);
        if (!valid(token) || selected !== selection) return;
        if (!url || !button.isConnected) continue;
        const log = el('log'), atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 100;
        const image = document.createElement('img'), caption = document.createElement('small');
        image.alt = 'Sales Update Copy Snapshot'; image.src = url;
        image.onload = () => { if (atBottom && valid(token) && selected === selection) log.scrollTop = log.scrollHeight; };
        caption.textContent = 'Sales Update · Copy Snapshot';
        button.replaceChildren(image, caption);
      } catch {
        if (!valid(token) || selected !== selection) return;
        reportSnapshots.delete(id);
        button.textContent = 'Snapshot could not load. Click to retry.';
      }
    }
  }
  const imageInput = document.createElement('input'); imageInput.type = 'file'; imageInput.multiple = true;
  imageInput.accept = 'image/png,image/jpeg,image/webp'; imageInput.hidden = true; imageInput.id = 'wf-image-input';
  const imageButton = document.createElement('button'); imageButton.type = 'button'; imageButton.className = 'wf-image-button';
  imageButton.textContent = 'Attach'; imageButton.setAttribute('aria-label', 'Attach screenshots');
  const imagePreview = document.createElement('div'); imagePreview.id = 'wf-image-preview'; imagePreview.className = 'wf-image-preview'; imagePreview.hidden = true;
  el('composer').prepend(imageInput, imagePreview);
  el('composer').querySelector('.wf-composer-bottom').prepend(imageButton);
  el('input').required = false;
  function renderImagePreview() {
    imagePreview.hidden = !attachedImages.length;
    imagePreview.replaceChildren();
    attachedImages.forEach((attachment, index) => {
      const item = document.createElement('div'), image = document.createElement('img'), remove = document.createElement('button');
      image.src = attachment.preview; image.alt = 'Screenshot ready to send';
      remove.type = 'button'; remove.textContent = '×'; remove.setAttribute('aria-label', 'Remove screenshot ' + (index + 1));
      remove.onclick = () => { attachedImages.splice(index,1); renderImagePreview(); };
      item.append(image, remove); imagePreview.append(item);
    });
  }
  async function attachFiles(files) {
    if (processingImages) return;
    if (attachedImages.length + files.length > 2) return error('Attach up to two screenshots per message.');
    const chat = active, token = generation; processingImages = true; imageButton.disabled = true;
    try {
      for (const file of files) {
        if (!['image/png','image/jpeg','image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) throw new Error('Choose a PNG, JPEG or WebP image under 10 MB.');
        const bitmap = await createImageBitmap(file);
        if (!valid(token) || active !== chat) { bitmap.close(); return; }
        if (bitmap.width * bitmap.height > 20000000) { bitmap.close(); throw new Error('Use an image up to 20 megapixels.'); }
        const scale = Math.min(1, 1600 / Math.max(bitmap.width,bitmap.height));
        const canvas = document.createElement('canvas'); canvas.width = Math.max(1,Math.round(bitmap.width * scale)); canvas.height = Math.max(1,Math.round(bitmap.height * scale));
        const context = canvas.getContext('2d'); context.fillStyle = '#fff'; context.fillRect(0,0,canvas.width,canvas.height); context.drawImage(bitmap,0,0,canvas.width,canvas.height); bitmap.close();
        let preview = canvas.toDataURL('image/png');
        if (preview.length > 1300000) preview = canvas.toDataURL('image/jpeg', .82);
        if (preview.length > 1300000) throw new Error('This screenshot is too detailed. Crop it or use a smaller image.');
        attachedImages.push({data:preview.split(',')[1], preview}); renderImagePreview();
      }
      error('');
    } catch (e) { if (valid(token) && active === chat) error(e.message); }
    finally { processingImages = false; imageButton.disabled = false; imageInput.value = ''; }
  }
  imageButton.onclick = () => imageInput.click();
  imageInput.onchange = () => attachFiles([...imageInput.files]);
  el('input').addEventListener('paste', event => {
    const files = [...event.clipboardData.items].filter(i => i.kind === 'file' && i.type.startsWith('image/')).map(i => i.getAsFile());
    if (files.length) { event.preventDefault(); attachFiles(files); }
  });
  el('composer').addEventListener('dragover', event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); });
  el('composer').addEventListener('drop', event => { if (event.dataTransfer.files.length) { event.preventDefault(); attachFiles([...event.dataTransfer.files]); } });

  function imageMarkup(images) {
    return (images || []).map(image => '<button type="button" class="wf-chat-image" data-image="' + escapeHTML(image.id) + '" aria-label="Open ' + escapeHTML(image.name) + '"><img src="/api/internal/workforce/images/' + escapeHTML(image.id) + '" alt="' + escapeHTML(image.name) + '" loading="lazy"><small>' + escapeHTML(image.name) + '</small></button>').join('');
  }
  const mentionMenu = document.createElement('div');
  mentionMenu.id = 'wf-mention-menu'; mentionMenu.className = 'wf-mention-menu'; mentionMenu.hidden = true;
  mentionMenu.setAttribute('role', 'listbox'); mentionMenu.setAttribute('aria-label', 'Mention a teammate');
  el('composer').prepend(mentionMenu);
  el('input').setAttribute('aria-controls', mentionMenu.id);
  el('input').setAttribute('aria-autocomplete', 'list');
  const mentionButton = document.createElement('button');
  mentionButton.type = 'button'; mentionButton.className = 'wf-mention-button'; mentionButton.textContent = '@';
  mentionButton.setAttribute('aria-label', 'Mention a teammate');
  el('composer').querySelector('.wf-composer-bottom').prepend(mentionButton);

  function closeMentions() {
    mentionMenu.hidden = true; mentionOptions = []; mentionStart = -1;
    el('input').removeAttribute('aria-activedescendant');
  }
  function showMentions() {
    const input = el('input'), before = input.value.slice(0, input.selectionStart);
    const match = before.match(/(?:^|\s)@([a-zA-Z0-9_-]*)$/);
    if (!match || input.selectionStart !== input.selectionEnd) return closeMentions();
    mentionStart = before.lastIndexOf('@');
    const query = match[1].toLowerCase();
    const rank = p => p.handle.toLowerCase().startsWith(query) ? 0 : p.name.toLowerCase().startsWith(query) ? 1 : 2;
    mentionOptions = participants.filter(p => (p.handle + ' ' + p.name).toLowerCase().includes(query)).sort((a,b) => rank(a) - rank(b)).slice(0,12);
    mentionIndex = 0;
    if (!mentionOptions.length) return closeMentions();
    renderMentions();
  }
  function renderMentions() {
    mentionMenu.innerHTML = mentionOptions.map((p,i) => '<button type="button" role="option" id="wf-mention-option-' + i + '" data-mention-index="' + i + '" aria-selected="' + (i === mentionIndex) + '"><strong>' + escapeHTML(p.name) + '</strong><small>@' + escapeHTML(p.handle) + ' · ' + (p.kind === 'ai' ? 'AI bot' : 'Team member') + '</small></button>').join('');
    mentionMenu.hidden = false;
    el('input').setAttribute('aria-activedescendant', 'wf-mention-option-' + mentionIndex);
    document.getElementById('wf-mention-option-' + mentionIndex).scrollIntoView({block:'nearest'});
  }
  function chooseMention(index) {
    const person = mentionOptions[index], input = el('input');
    if (!person || mentionStart < 0) return;
    input.setRangeText('@' + person.handle + ' ', mentionStart, input.selectionStart, 'end');
    closeMentions(); input.focus();
  }
  mentionMenu.onmousedown = event => event.preventDefault();
  mentionMenu.onclick = event => { const option = event.target.closest('[data-mention-index]'); if (option) chooseMention(Number(option.dataset.mentionIndex)); };
  mentionButton.onclick = () => {
    const input = el('input'); input.focus();
    const prefix = input.selectionStart && !/\s/.test(input.value[input.selectionStart - 1]) ? ' @' : '@';
    input.setRangeText(prefix, input.selectionStart, input.selectionEnd, 'end'); showMentions();
  };
  el('input').addEventListener('input', showMentions);
  el('input').addEventListener('click', showMentions);
  document.addEventListener('click', event => { if (!el('composer').contains(event.target)) closeMentions(); });

  function messageMarkup(message) {
    const template = document.createElement('template'); template.innerHTML = markup(message.content);
    const handles = new Set(participants.filter(p => (message.mention_ids || []).includes(p.id)).map(p => p.handle.toLowerCase()));
    const walker = document.createTreeWalker(template.content, NodeFilter.SHOW_TEXT), nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      if (node.parentElement?.closest('code,pre')) return;
      const text = node.textContent, pattern = /(^|[^\w@])@([a-zA-Z0-9_-]+)(?![\w-])/g;
      const fragment = document.createDocumentFragment(); let end = 0, match;
      while ((match = pattern.exec(text))) {
        if (!handles.has(match[2].toLowerCase())) continue;
        const start = match.index + match[1].length;
        fragment.append(text.slice(end,start));
        const tag = document.createElement('span'); tag.className = 'wf-mention'; tag.textContent = '@' + match[2];
        fragment.append(tag); end = pattern.lastIndex;
      }
      if (end) { fragment.append(text.slice(end)); node.replaceWith(fragment); }
    });
    return template.innerHTML;
  }

  function worker(online) {
    el('worker').textContent = status?.execution === 'request' ? 'AI runs on Vercel' : online ? 'AI worker online' : 'AI worker offline - jobs stay queued';
    el('worker-dot').classList.toggle('online', online);
  }
  function renderChats() {
    const query = el('search').value.trim().toLowerCase();
    const filtered = (controls ? controls.filter(chats) : chats).filter(chat => (chat.title + ' ' + (chat.preview || '')).toLowerCase().includes(query));
    el('chat-count').textContent = chats.length + (chats.length === 1 ? ' conversation' : ' conversations');
    const html = filtered.length ? filtered.map(chat => '<div class="wf-chat-row"><button class="wf-chat ' + (active === chat.id ? 'selected' : '') + '" data-chat="' + escapeHTML(chat.id) + '" aria-pressed="' + (active === chat.id) + '"><span class="wf-chat-avatar">' + (chat.has_avatar ? '<img alt="" src="/api/internal/workforce/conversations/' + chat.id + '/avatar?v=' + chat.avatar_version + '">' : 'A↗') + '</span><span class="wf-chat-copy"><strong>' + escapeHTML((controls?.chatBadge(chat) || '') + chat.title) + '</strong><p>' + escapeHTML(chat.working ? 'AI assignment in progress…' : chat.preview || 'AI Manager & Operations') + '</p></span>' + (chat.preferences?.muted_until < Date.now()/1000 && chat.mention_seq > Math.max(seen.get(chat.id) || 0, chat.preferences?.read_seq || 0) && active !== chat.id ? '<span class="wf-ping" aria-label="You were mentioned">@</span>' : '') + (chat.preferences?.muted_until < Date.now()/1000 && (chat.preferences?.unread || chat.last_seq > Math.max(seen.get(chat.id) || 0,chat.preferences?.read_seq || 0)) && active !== chat.id ? '<span class="wf-chat-new" aria-label="Unread messages"></span>' : '') + '</button><button class="wf-chat-options" type="button" data-chat-options="' + escapeHTML(chat.id) + '" aria-label="Options for ' + escapeHTML(chat.title) + '">&#8964;</button></div>').join('') : '<div class="wf-empty-chat">' + (chats.length ? 'No matching conversations.' : 'Your next conversation starts here.<br>Use + to create a private chat or group.') + '</div>';
    if (el('chats').innerHTML !== html) el('chats').innerHTML = html;
  }
  function markup(text) {
    // Escape all model/user content first. Only small formatting primitives are supported.
    return escapeHTML(text).split(/(```[\s\S]*?```)/g).map(part => {
      if (part.startsWith('```')) return '<pre><code>' + part.slice(3, -3).replace(/^[a-zA-Z0-9_+-]+\n/, '') + '</code></pre>';
      return part.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>').replace(/`([^`\n]+)`/g, '<code>$1</code>');
    }).join('');
  }
  function sourceSummary(report) {
    if (!report) return '';
    const money = report.accessory_usd === null ? 'Unavailable' : new Intl.NumberFormat('en-US', {style:'currency', currency:'USD'}).format(Number(report.accessory_usd));
    const coverage = report.coverage;
    return '<div class="wf-source"><strong>SOURCE TOTALS &middot; ' + escapeHTML(report.start) + ' to ' + escapeHTML(report.end) + '</strong><span>' + escapeHTML(report.store_count) + ' matching stores &middot; ' + escapeHTML(report.total_boxes ?? 'Unavailable') + ' total boxes</span><span>' + escapeHTML(money) + ' in accessory sales</span><small>Import coverage: ' + escapeHTML(coverage.complete) + '/' + escapeHTML(coverage.expected) + ' source-days &middot; ' + escapeHTML(coverage.retained) + ' retained records. Missing source data may make totals incomplete.</small></div>';
  }
  function renderMessages(stick = false) {
    const log = el('log'), nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 90;
    const query = el('message-search').value.toLowerCase();
    const visible = messages.filter(m => (m.content + ' ' + m.sender_name).toLowerCase().includes(query));
    el('messages').innerHTML = visible.length ? '<div class="wf-date">' + escapeHTML(new Date(visible[0].created_at).toLocaleDateString(undefined, {weekday:'long',month:'long',day:'numeric'})) + '</div>' + visible.map(m => {
      const own = m.sender_id === currentUser.id, ai = m.kind === 'ai';
      const initials = ai ? (status?.employees?.find(a => a.id === m.sender_id)?.initials || 'AI') : m.sender_name.slice(0,2).toUpperCase();
      return '<article data-seq="' + m.seq + '" class="wf-message ' + (own ? 'own ' : '') + ((m.mention_ids || []).includes(currentUser.id) ? 'mentioned ' : '') + (m.sender_id === 'ai-operations' ? 'operations' : '') + '"><span class="wf-message-icon" aria-hidden="true">' + escapeHTML(initials) + '</span><div class="wf-bubble"><div class="wf-sender">' + escapeHTML(own ? 'You' : m.sender_name) + (ai ? '<span class="wf-ai-label">AI</span>' : '') + '</div>' + (controls?.beforeMessage(m) || '') + '<div class="wf-content">' + messageMarkup(m) + '</div>' + snapshotMarkup(m) + sourceSummary(m.report_summary) + (m.report_ready ? '<a class="wf-report" href="/api/internal/workforce/tasks/' + escapeHTML(m.task_id) + '/report.csv" download>&#8595; Download source report</a>' : '') + '<time class="wf-time" datetime="' + escapeHTML(m.created_at) + '" title="' + escapeHTML(new Date(m.created_at).toLocaleString()) + '">' + escapeHTML(new Date(m.created_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})) + '</time>' + (controls?.afterMessage(m) || '') + '</div></article>';
    }).join('') : '<div class="wf-empty-chat">' + (query ? 'No matching loaded messages.' : 'Your AI team is ready for an assignment.<button type="button" class="wf-suggestion" id="wf-example">Summarize yesterday’s saved sales for all stores.</button>') + '</div>';
    if (stick || nearBottom) log.scrollTop = log.scrollHeight;
    loadSnapshots();
  }
  function renderTasks() {
    el('tasks').innerHTML = tasks.filter(task => task.status !== 'completed').slice(0,10).map(task => {
      const own = task.creator_id === currentUser.id, running = ['pending','running'].includes(task.status);
      const retryable = ['failed','cancelled'].includes(task.status) && task.attempts < 3;
      return '<div class="wf-task" data-status="' + escapeHTML(task.status) + '"><span class="wf-task-status">' + escapeHTML(task.status) + '</span><div class="wf-task-info"><strong>' + escapeHTML(task.step) + '</strong>' + (task.error ? '<small>' + escapeHTML(task.error) + '</small>' : '') + '</div><div class="wf-task-actions">' + (task.has_report ? '<a href="/api/internal/workforce/tasks/' + task.id + '/report.csv" download>↓ Sales CSV</a>' : '') + (own && running ? '<button data-task="' + task.id + '" data-action="cancel">Cancel</button>' : '') + (own && task.status === 'pending' && status?.execution === 'request' ? '<button data-task="' + task.id + '" data-action="run">Start</button>' : '') + (own && retryable ? '<button data-task="' + task.id + '" data-action="retry">Retry</button>' : '') + '<button data-audit="' + task.id + '" aria-label="View assignment activity">Activity</button>' + (['failed','cancelled'].includes(task.status) ? '<button class="wf-dismiss" data-task="' + task.id + '" data-action="dismiss" aria-label="Dismiss ' + task.status + ' assignment" title="Dismiss assignment">&times;</button>' : '') + '</div></div>';
    }).join('');
  }
  async function refreshChats(token) {
    const data = await api(endpoint + 'conversations');
    if (!valid(token)) return;
    chats = data.conversations; worker(data.worker_online); renderChats();
  }
  async function refreshConversation(initial = false) {
    const chat = active, token = generation, selected = selection;
    if (!chat) return;
    const last = initial ? 0 : (messages.at(-1)?.seq || 0);
    let data;
    try { data = await api(endpoint + 'conversations/' + chat + (last ? '?after=' + last : '')); }
    catch(e) { if (e.message === 'Conversation not found.' && active === chat) closeChat(); throw e; }
    if (!valid(token) || active !== chat || selection !== selected) return;
    const changed = controls?.onState(data);
    if (changed && !initial) return refreshConversation(true);
    if (initial) messages = [];
    const known = new Set(messages.map(m => m.seq));
    const added = data.messages.filter(m => !known.has(m.seq));
    messages.push(...added); messages.sort((a,b) => a.seq - b.seq);
    const taskChanged = JSON.stringify(tasks) !== JSON.stringify(data.tasks);
    tasks = data.tasks;
    el('title').textContent = data.conversation.title;
    participants = data.participants || []; canAddAgents = data.can_add_agents;
    el('members').textContent = participants.map(p => p.kind === 'ai' ? '@' + p.handle : p.name).join(', ');
    if (initial) el('older').hidden = !data.has_older;
    seen.set(chat, messages.at(-1)?.seq || 0);
    if (initial || added.length) renderMessages(initial);
    if (initial || taskChanged) renderTasks();
    renderChats();
  }
  async function selectChat(id) {
    controls?.reset();
    reportSnapshots.clear();
    attachedImages = []; renderImagePreview();
    selection++; active = id; messages = []; tasks = []; pendingSend = null; participants = []; canAddAgents = false; closeMentions();
    el('input').value = ''; el('message-search').value = ''; el('older').hidden = true;
    el('welcome').hidden = true; el('active').hidden = false; el('layout').classList.add('chat-open');
    el('title').textContent = 'Opening conversation…'; el('members').textContent = '';
    el('messages').innerHTML = '<div class="wf-empty-chat">Loading messages…</div>'; el('tasks').replaceChildren();
    renderChats(); error('');
    try { await refreshConversation(true); } catch (e) { if (currentUser && active === id) error(e.message); }
  }
  async function load() {
    const token = ++generation; error(''); sending = false; el('send').disabled = false;
    try {
      const [info] = await Promise.all([api(endpoint + 'status'), refreshChats(token)]);
      if (!valid(token)) return;
      status = info; worker(info.worker_online); el('model-label').textContent = info.model + (info.provider === 'groq' ? ' - Groq' : info.provider === 'vercel' ? ' - Vercel AI Gateway' : ' - local model'); el('demo').hidden = !info.demo;
      if (info.error) error(info.error);
      if (active) await refreshConversation(true);
      await controls?.loaded();
    } catch (e) { if (valid(token)) error(e.message); }
  }
  function clear() {
    controls?.reset();
    reportSnapshots.clear();
    participants = []; canAddAgents = false; closeMentions(); attachedImages = []; renderImagePreview();
    el('full-image').removeAttribute('src');
    el('download-image').removeAttribute('href'); el('image-feedback').textContent = '';
    generation++; selection++; active = null; chats = []; messages = []; tasks = []; status = null; pendingSend = null; sending = false; seen.clear();
    el('chats').replaceChildren(); el('messages').replaceChildren(); el('tasks').replaceChildren();
    el('input').value = ''; el('search').value = ''; el('message-search').value = ''; el('new-form').reset(); el('people').replaceChildren();
    el('audit-content').replaceChildren(); el('employees').replaceChildren();
    el('active').hidden = true; el('welcome').hidden = false; el('demo').hidden = true; el('layout').classList.remove('chat-open');
    el('send').disabled = false; error('');
    [newDialog,directory,settings,auditDialog,imageDialog].forEach(d => { if (d.open) d.close(); });
  }
  async function newChat() {
    const token = generation;
    el('new-form').reset(); el('new-error').textContent = ''; el('people').replaceChildren();
    el('people-field').hidden = currentUser.role !== 'admin';
    newDialog.showModal(); el('new-title').focus();
    if (currentUser.role === 'admin') {
      try {
        const data = await api('users');
        if (!valid(token)) return;
        data.users.filter(u => u.id !== currentUser.id && u.active && !u.rest_mode).forEach(u => el('people').append(new Option(u.display_name, u.id)));
      } catch(e) { if (valid(token)) el('new-error').textContent = e.message; }
    }
  }
  el('new').onclick = newChat; el('start').onclick = newChat;
  el('new-form').onsubmit = event => { event.preventDefault(); const token = generation; submit(event.target, 'wf-new-error', async () => {
    const members = [...el('people').selectedOptions].map(o => o.value);
    const data = await api(endpoint + 'conversations', 'POST', {title:el('new-title').value,member_ids:members});
    if (!valid(token)) return;
    newDialog.close(); await refreshChats(token); if (valid(token)) await selectChat(data.id);
  }); };
  el('chats').onclick = event => { const button = event.target.closest('[data-chat]'); if (button) selectChat(button.dataset.chat); };
  el('search').oninput = renderChats;
  el('message-search').oninput = () => renderMessages();
  el('back').onclick = () => el('layout').classList.remove('chat-open');
  el('messages').onclick = event => {
    const snapshot = event.target.closest('[data-snapshot]');
    if (snapshot) {
      const image = snapshot.querySelector('img');
      if (!image) { loadSnapshots(); return; }
      el('full-image').src = image.src; el('download-image').href = image.src;
      el('download-image').download = 'sales-snapshot.png'; el('copy-snapshot').hidden = false;
      el('image-feedback').textContent = ''; imageDialog.showModal(); return;
    }
    const button = event.target.closest('[data-image]');
    if (button) {
      const url = '/api/internal/workforce/images/' + button.dataset.image;
      el('copy-snapshot').hidden = true; el('download-image').download = ''; el('image-feedback').textContent = '';
      el('full-image').src = url; el('download-image').href = url; imageDialog.showModal();
    }
    if (event.target.closest('#wf-example')) { el('input').value = 'Summarize yesterday saved sales for all stores.'; el('input').focus(); }
  };
  el('input').onkeydown = event => {
    if (event.isComposing) return;
    if (!mentionMenu.hidden) {
      if (event.key === 'Escape') { event.preventDefault(); closeMentions(); return; }
      if (['ArrowDown','ArrowUp'].includes(event.key)) {
        event.preventDefault(); mentionIndex = (mentionIndex + (event.key === 'ArrowDown' ? 1 : -1) + mentionOptions.length) % mentionOptions.length; renderMentions(); return;
      }
      if ((event.key === 'Enter' && !event.shiftKey) || event.key === 'Tab') { event.preventDefault(); chooseMention(mentionIndex); return; }
    }
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); el('composer').requestSubmit(); }
  };
  el('composer').onsubmit = async event => {
    event.preventDefault(); if (!active || sending || processingImages) return;
    const content = el('input').value.trim(), chat = active, token = generation, invoke = el('invoke').checked;
    if (!content && !attachedImages.length) return;
    const reply_seq = controls?.replySeq() || null;
    const images = attachedImages.map(i => ({data:i.data}));
    const imageKey = images.map(i => i.data).join('|');
    if (!pendingSend || pendingSend.chat !== chat || pendingSend.content !== content || pendingSend.invoke !== invoke || pendingSend.imageKey !== imageKey || pendingSend.reply_seq !== reply_seq) pendingSend = {chat,content,invoke,imageKey,reply_seq,id:uuid()};
    const outgoing = pendingSend;
    sending = true; el('send').disabled = true; error('');
    try {
      await api(endpoint + 'conversations/' + chat + '/messages', 'POST', {content,request_id:outgoing.id,invoke_agents:invoke,images,reply_seq});
      if (!valid(token) || active !== chat) return;
      if (el('input').value.trim() === content) el('input').value = '';
      pendingSend = null; closeMentions(); controls?.sent();
      if (attachedImages.map(i => i.data).join('|') === imageKey) { attachedImages = []; renderImagePreview(); }
      await refreshConversation(); await refreshChats(token); el('log').scrollTop = el('log').scrollHeight;
    } catch(e) { if (valid(token) && active === chat) error(e.message + ' Your message is kept here for retry.'); }
    finally { if (token === generation) { sending = false; el('send').disabled = false; } }
  };
  el('older').onclick = async () => {
    const chat = active, selected = selection, token = generation;
    el('older').disabled = true;
    try {
      const data = await api(endpoint + 'conversations/' + chat + '?before=' + messages[0].seq);
      if (!valid(token) || active !== chat || selected !== selection) return;
      const beforeHeight = el('log').scrollHeight, beforeTop = el('log').scrollTop;
      const known = new Set(messages.map(m => m.seq)); messages.unshift(...data.messages.filter(m => !known.has(m.seq)));
      el('older').hidden = !data.has_older; renderMessages(); el('log').scrollTop = beforeTop + el('log').scrollHeight - beforeHeight;
    } catch(e) { if (valid(token)) error(e.message); } finally { el('older').disabled = false; }
  };
  el('tasks').onclick = async event => {
    const button = event.target.closest('button'); if (!button) return;
    const token = generation;
    button.disabled = true;
    try {
      if (button.dataset.audit) {
        const data = await api(endpoint + 'tasks/' + button.dataset.audit + '/audit');
        if (!valid(token)) return;
        el('audit-content').innerHTML = data.events.map(item => '<div class="wf-employee"><div><h3>' + escapeHTML(item.event.replaceAll('.', ' · ')) + '</h3><p>' + escapeHTML(new Date(item.created_at).toLocaleString()) + '</p><p>' + escapeHTML(item.details === '{}' ? '' : item.details) + '</p></div></div>').join('');
        auditDialog.showModal();
      } else {
        await api(endpoint + 'tasks/' + button.dataset.task + '/' + button.dataset.action, 'POST', {});
        if (valid(token)) await refreshConversation();
      }
    } catch(e) { if (valid(token)) error(e.message); } finally { button.disabled = false; }
  };
  el('directory').onclick = () => {
    el('employees').innerHTML = (status?.employees || []).map(agent => {
      const joined = participants.some(p => p.id === agent.id);
      return '<div class="wf-employee"><div class="wf-chat-avatar">' + escapeHTML(agent.initials) + '</div><div><h3>' + escapeHTML(agent.name) + ' <span class="wf-ai-label">AI</span></h3><small>@' + escapeHTML(agent.handle) + ' ? ' + escapeHTML(agent.department) + '</small><p>' + escapeHTML(agent.description) + '</p>' + (active && !joined && canAddAgents ? '<button type="button" data-add-agent="' + escapeHTML(agent.id) + '">Ask Manager to add</button>' : joined ? '<small>In this group</small>' : '') + '</div></div>';
    }).join('') || '<p>Connect to the workforce server to see employees.</p>';
    directory.showModal();
  };
  el('employees').onclick = event => {
    const button = event.target.closest('[data-add-agent]');
    const agent = status?.employees?.find(a => a.id === button?.dataset.addAgent);
    if (!agent || !active) return;
    directory.close();
    el('input').value += (el('input').value ? '\n' : '') + '@manager Add ' + agent.name + ' to this group.';
    el('input').focus();
  };
  el('settings').onclick = async () => {
    const token = generation; el('settings-error').textContent = ''; el('connection').textContent = 'Checking connection…'; settings.showModal();
    el('model-save').hidden = currentUser.role !== 'admin'; el('model').disabled = currentUser.role !== 'admin';
    try {
      const info = await api(endpoint + 'status'); if (!valid(token)) return; status = info;
      el('connection').textContent = info.execution === 'request' ? (info.provider === 'groq' ? 'Groq: ' : 'Vercel AI Gateway: ') + (info.ai_configured ? 'Configured' : 'Needs setup') : 'Ollama: ' + (info.ollama_online ? 'Connected' : 'Unavailable') + ' - AI worker: ' + (info.worker_online ? 'Online' : 'Offline');
      el('worker-help').textContent = info.provider === 'groq' ? 'Assignments run on Vercel and are saved in Supabase. Prompts and selected sales summaries are sent to Groq. Stay on the Groq Free plan for free usage within its limits.' : info.provider === 'vercel' ? 'Assignments run on Vercel and are saved in Supabase. Prompts and selected sales summaries are sent to the hosted model. Usage draws from your Vercel AI Gateway credits.' : 'Start the AI worker on your company AI computer to process queued assignments.';
      el('model').replaceChildren(...info.models.map(model => new Option(model, model)));
      el('model').value = info.model; el('settings-error').textContent = info.error || '';
      el('integrations').innerHTML = info.integrations.map(item => '<div>' + escapeHTML(item.name) + ': <strong>' + (item.connected ? 'Configured' : 'Not connected') + '</strong></div>').join('');
    } catch(e) { if (valid(token)) el('settings-error').textContent = e.message; }
  };
  el('model-form').onsubmit = event => { event.preventDefault(); submit(event.target, 'wf-settings-error', async () => {
    const token = generation; await api(endpoint + 'settings', 'PATCH', {model:el('model').value});
    if (valid(token)) { settings.close(); await load(); }
  }); };
  setInterval(async () => {
    if (polling || document.hidden || !currentUser || currentUser.rest_mode || page !== 'workforce') return;
    polling = true; const token = generation;
    try { if (active) await refreshConversation(); if (++ticks % 5 === 0) await refreshChats(token); }
    catch(e) { if (valid(token)) error(e.message); }
    finally { polling = false; }
  }, 2000);
  function closeChat() {
    controls?.reset(); reportSnapshots.clear(); selection++; active=null; messages=[];tasks=[];
    if(imageDialog.open)imageDialog.close();el('full-image').removeAttribute('src');el('download-image').removeAttribute('href');
    participants=[];attachedImages=[];renderImagePreview();pendingSend=null;el('input').value='';
    el('messages').replaceChildren();el('tasks').replaceChildren();el('active').hidden=true;
    el('welcome').hidden=false;el('layout').classList.remove('chat-open');renderChats();
  }
  controls = window.createWorkforceControls({
    state:()=>({active,chats,messages,participants}),error,select:selectChat,close:closeChat,
    renderChats,renderMessages,refresh:async()=>{if(active)await refreshConversation(true);await refreshChats(generation);}
  });
  window.workforceDashboard = {load,clear};
})();
