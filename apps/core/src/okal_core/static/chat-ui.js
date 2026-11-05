"use strict";
/* OKAL chat-first surface. Never stores message text in browser storage. */
let chatSequence = 0;
let chatAbort = null;
let chatTurns = [];
let chatPending = false;
let chatConversation = null;
let chatRetry = null;
let chatReady = false;
let chatLoadLibrary = null;
let chatResetMemoryEditor = null;
function ensureChatLibrary() {
  if (!chatReady && chatLoadLibrary) return chatLoadLibrary();
}


/* Displays the exact saved daily brief already fetched by the dashboard.
 * Does not claim live Google/Gmail status and never displays made-up activity.
 */
function renderChatDailySummary(data) {
  const target = document.getElementById("chat-daily-points");
  const caveat = document.getElementById("chat-source-caveat");
  if (!target || !caveat) return;
  target.replaceChildren();
  const items = Array.isArray(data?.brief_points)
    ? data.brief_points.filter(v => typeof v === "string" && v.trim()).slice(0,4)
    : [];
  for (const value of items.length ? items : ["مفيش موجز محلي متاح حاليًا."]) {
    const item = document.createElement("li");
    item.textContent = value; // Cached labels and model output stay text.
    target.append(item);
  }
  caveat.textContent = data?.mail_sync_stale
    ? "Gmail: التحديث غير مؤكد؛ تفاصيل اليوم من النسخ المحفوظة فقط."
    : "البيانات المحفوظة قد تكون ناقصة؛ ما تعتمدش عليها كدليل إن التقويم فاضي.";
}
function updateChatSessionCount() {
  const marker = document.getElementById("chat-memory-count");
  if (marker) marker.textContent = String(chatTurns.length) + " رسائل";
}


function clearChatUI() {
  if (typeof clearComputerUI === "function") clearComputerUI();
  chatSequence += 1;
  if (chatAbort) chatAbort.abort();
  chatAbort = null;
  chatTurns = [];
  chatPending = false;
  chatConversation = null;
  chatRetry = null;
  chatReady = false;
  if (chatResetMemoryEditor) chatResetMemoryEditor();
  for (const id of ["chat-conversations","chat-memory-list","chat-memory-source-list",
    "chat-memory-lifecycle-list","chat-archive-results","chat-conversation-state","chat-vault-preview-text"]) {
    document.getElementById(id)?.replaceChildren();
  }
  for (const id of ["chat-memory-key","chat-memory-value","chat-project-name","chat-project-description",
    "chat-archive-query","chat-memory-project"]) {
    const node = document.getElementById(id); if (node) node.value = "";
  }
  const retry = document.getElementById("chat-retry"); if (retry) retry.hidden = true;
  updateChatSessionCount();
  const log = document.getElementById("chat-messages");
  if (log) log.replaceChildren();
  const prompt = document.getElementById("chat-input");
  if (prompt) prompt.value = "";
  const send = document.getElementById("chat-send");
  if (send) send.disabled = false;
  const greeting = document.getElementById("chat-greeting");
  if (greeting) greeting.hidden = false;
  const status = document.getElementById("chat-status");
  if (status) status.textContent = "";
}

(function initChatHome() {
  const get = id => document.getElementById(id);
  const log = get("chat-messages");
  const entry = get("chat-input");
  const send = get("chat-send");
  const status = get("chat-status");
  if (!log || !entry || !send || !status) return;

  function bubble(role, content) {
    const box = document.createElement("article");
    box.className = "chat-bubble";
    box.setAttribute("data-role", role);
    const label = document.createElement("span");
    label.className = "chat-bubble-role";
    label.textContent = role === "user" ? "أنت" : "OKAL · local";
    const text = document.createElement("div");
    text.dir = "auto";
    text.className = "chat-message-content";
    if (role === "assistant" && typeof renderOKALMarkdown === "function") {
      renderOKALMarkdown(text, content);
    } else {
      text.textContent = content;
    }
    box.append(label, text);
    log.append(box);
    get("chat-greeting").hidden = true;
    log.scrollTop = log.scrollHeight;
    return box;
  }

  function cairoISO(localValue) {
    // datetime-local has no zone. Resolve explicitly in Africa/Cairo instead
    // of assuming the browser's timezone (especially remote owner devices).
    if (!/^\d{4}-\d\d-\d\dT\d\d:\d\d$/.test(localValue))
      throw new Error("اختر تاريخ ووقت صالحين.");
    const naive = Date.parse(localValue + ":00Z");
    if (!Number.isFinite(naive)) throw new Error("وقت غير صالح.");
    const formatter = new Intl.DateTimeFormat("en-GB", {
      timeZone:"Africa/Cairo", year:"numeric",month:"2-digit",
      day:"2-digit",hour:"2-digit",minute:"2-digit",hourCycle:"h23",
    });
    const matches = [];
    for (const hours of [2,3]) {
      const stamp = naive - hours * 3600000;
      const parts = Object.fromEntries(formatter.formatToParts(new Date(stamp))
        .map(p => [p.type,p.value]));
      const rendered = parts.year + "-" + parts.month + "-" + parts.day +
        "T" + parts.hour + ":" + parts.minute;
      if (rendered === localValue) matches.push(stamp);
    }
    if (matches.length !== 1) throw new Error(
      "الوقت غير واضح بسبب تغيير التوقيت الصيفي؛ اختار وقت تاني من التقويم.");
    return new Date(matches[0]).toISOString();
  }

  function proposalForm(proposal, parent) {
    if (proposal.kind !== "event" || proposal.destination !== "okal_local_only"
        || !proposal.requires_confirmation) return;
    const form = document.createElement("form");
    form.className = "chat-proposal";
    const head = document.createElement("strong");
    head.textContent = "مراجعة موعد · غير محفوظ حتى الآن";
    const fields = {};
    for (const [name,label,value,type] of [
      ["title","اسم الموعد",proposal.title,"text"],
      ["start","البداية · بتوقيت القاهرة",proposal.start.slice(0,16),"datetime-local"],
      ["end","النهاية · بتوقيت القاهرة",proposal.end.slice(0,16),"datetime-local"]
    ]) {
      const wrapper = document.createElement("label");
      wrapper.textContent = label;
      const input = document.createElement("input");
      input.type = type;
      input.name = name;
      input.value = value;
      input.required = true;
      if (name === "title") input.maxLength = 250;
      wrapper.append(input);
      fields[name] = input;
      form.append(wrapper);
    }
    const action = document.createElement("button");
    action.type = "submit";
    action.textContent = "أؤكد — احفظ في تقويم OKAL المحلي";
    const note = document.createElement("p");
    note.className = "chat-save-note";
    note.textContent = "تقدر تعدّل التفاصيل قبل التأكيد. لن يُنشأ موعد في Google Calendar.";
    const feedback = document.createElement("p");
    feedback.setAttribute("role","status");
    feedback.className = "chat-save-note";
    // Insert heading before editable fields.
    form.prepend(head);
    form.append(note, action, feedback);
    let id = null; // Stable across uncertain retries; local Calendar is idempotent.
    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (action.disabled) return;
      let start, end;
      try {
        start = cairoISO(fields.start.value);
        end = cairoISO(fields.end.value);
        if (Date.parse(end) <= Date.parse(start)) throw new Error(
          "النهاية لازم تكون بعد البداية.");
      } catch (error) {
        feedback.textContent = error.message || "راجع الموعد والوقت.";
        return; // Client validation is safely retryable; no write attempted.
      }
      action.disabled = true;
      feedback.textContent = "براجع الوقت وبحفظ الموعد محليًا...";
      try {
        if (!id) id = crypto.randomUUID().replaceAll("-", "");
        const response = await fetch("/api/v1/calendar/local/save", {
          method:"POST",credentials:"same-origin",cache:"no-store",
          headers:{"Content-Type":"application/json"},
          body:JSON.stringify({
            id,revision:0,kind:"event",title:fields.title.value,
            notes:"Owner-confirmed from OKAL chat",
            start,end,target_date:null,reminder_minutes:null
          }),
        });
        if (!response.ok) throw new Error(response.status === 409
          ? "الطلب اتغيّر بعد محاولة سابقة. راجع التقويم قبل إعادة الحفظ."
          : "تعذر تأكيد الحفظ؛ افحص التقويم قبل تكرار المحاولة.");
        const saved = await response.json();
        if (saved.id !== id || (saved.revision !== 1 && !saved.replayed))
          throw new Error("نتيجة الحفظ غير مؤكدة، راجع التقويم.");
        feedback.textContent = "اتحفظ الموعد في تقويم OKAL المحلي فقط.";
        action.textContent = "تم الحفظ محليًا";
        for (const input of Object.values(fields)) input.disabled = true;
        if (typeof load === "function") await load(true);
      } catch (error) {
        feedback.textContent = error.message || "تعذر الحفظ. راجع التقويم أولًا.";
        // Do not retry a potentially ambiguous write with a different payload.
        // A same-ID exact replay can only be safely inspected through Calendar.
        action.disabled = true;
      }
    });
    parent.append(form);
  }

  const post = async (path, payload={}) => {
    const response = await fetch("/api/v1/chat/" + path, {
      method:"POST",credentials:"same-origin",cache:"no-store",
      headers:{"Content-Type":"application/json"},body:JSON.stringify(payload),
      signal:chatAbort?.signal,
    });
    if (!response.ok) {
      const error = new Error(response.status === 401 || response.status === 403
        ? "افتح جلسة OKAL المحمية الأول."
        : response.status === 409 ? "الموديل مشغول أو حالة الطلب اتغيّرت. حدّث السجل قبل المحاولة."
        : response.status === 422 ? "راجع البيانات؛ لا تحفظ كلمات السر أو مفاتيح الدخول."
        : "تعذر قراءة أو حفظ الحالة المحلية.");
      error.status = response.status; throw error;
    }
    return response.json();
  };
  let older = null, moreConversations = null, memoryRevision = 0;
  let editingProject = null, associationRevision = 0, browseOffset = null, archiveBefore = null, vaultPreview = null;
  let projectRecords=[], projectEdit=null, projectVaultPreview=null;
  const selectedProject = () => get("chat-memory-project").value || null;
  const labels = {remembered:"Remembered · من كلامك", current:"Remembered · الحالي",
    inferred:"Inferred · مستنتج", unverified:"Unverified · غير مؤكد",
    superseded:"Superseded · اتغير", deleted:"Deleted · محذوف"};
  function rememberSelection(id) {
    // Only an identifier goes in browser history; all text stays server-side.
    if (typeof window !== "undefined") window.history.replaceState({okalConversation:id}, "");
  }
  function resetMemoryEditor() {
    memoryRevision = 0;
    editingProject = null; vaultPreview = null;
    projectEdit=null;projectVaultPreview=null;projectRecords=[];
    get("chat-project-name").value="";get("chat-project-description").value="";
    get("chat-vault-project-import").hidden=true;get("chat-vault-project-text").replaceChildren();
    get("chat-memory-key").value = ""; get("chat-memory-key").disabled = false;
    get("chat-memory-value").value = "";
    get("chat-memory-scope").disabled = false;
    get("chat-memory-days").value = "0";
    get("chat-vault-import").hidden = true;
    for(const id of ["chat-memory-source-list","chat-memory-lifecycle-list","chat-archive-results","chat-vault-preview-text"])
      get(id).replaceChildren();
    get("chat-vault-memory").value="";
  }
  chatResetMemoryEditor = resetMemoryEditor;
  async function refreshMemories() {
    const seq=chatSequence;
    const data = await post("memories", {conversation_id:chatConversation,project_id:selectedProject()});
    if (seq !== chatSequence) return;
    get("chat-memory-list").replaceChildren();
    for (const item of data.items) {
      const row = document.createElement("article");
      const value = document.createElement("p");
      value.textContent = item.key + ": " + item.content;
      const source = document.createElement("small");
      source.textContent = item.kind + " · " + item.source + " · v" + item.revision +
        " · " + (item.expires_at ? new Date(item.expires_at * 1000).toLocaleDateString() : "لحد ما تنساها") +
        " · " + (labels[item.assertion] || labels.remembered) +
        " · " + (item.scope === "owner" ? "كل المحادثات" : item.project_id ? "المشروع" : "المحادثة فقط");
      const edit = document.createElement("button"); edit.type="button"; edit.textContent="تعديل";
      edit.addEventListener("click", () => {
        memoryRevision = item.revision;
        editingProject = item.project_id || null;
        get("chat-memory-key").value = item.key; get("chat-memory-key").disabled = true;
        get("chat-memory-value").value = item.content;
        get("chat-memory-kind").value = item.kind;
        get("chat-memory-scope").value = item.scope === "owner" ? "owner" : item.project_id ? "project" : "conversation";
        get("chat-memory-days").value = item.expires_at ? String(Math.max(1,Math.ceil((item.expires_at*1000-Date.now())/86400000))) : "0";
        get("chat-memory-scope").disabled = true;
        get("chat-memory-value").focus();
      });
      const forget = document.createElement("button"); forget.type="button"; forget.textContent="نسيان";
      forget.addEventListener("click", () => guarded(async () => {
        if (!confirm("نسيان المعلومة وحذف نصها وإبطال الردود المعتمدة عليها؟ باقي كلامك هيفضل محفوظ.")) return;
        await post("memory-delete", {memory_id:item.id}); resetMemoryEditor();
        chatSequence+=1;if(chatAbort)chatAbort.abort();chatAbort=null;chatPending=false;send.disabled=false;chatRetry=null;
        await refreshMemories(); if (chatConversation) await resume(chatConversation); await library();
      }));
      const sources = document.createElement("button"); sources.type="button"; sources.textContent="المصدر والإصدارات";
      sources.addEventListener("click",()=>guarded(()=>showSources(item.id)));
      row.append(value, source, edit, forget, sources); get("chat-memory-list").append(row);
    }
  }
  async function showSources(id) {
    const seq=chatSequence, data=await post("memory-versions",{memory_id:id});
    if(seq!==chatSequence)return;
    const target=get("chat-memory-source-list"); target.replaceChildren();
    vaultPreview=null;get("chat-vault-import").hidden=true;
    get("chat-vault-memory").value=id;
    for(const item of data.items) {
      const p=document.createElement("p"); p.dir="auto";
      p.textContent=(labels[item.status] || item.status)+" · v"+item.revision+" · "+
        (item.snapshot?.content || "النص محذوف / Content deleted"); target.append(p);
    }
    for(const item of data.sources || []) {
      const p=document.createElement("p"); p.dir="auto"; p.textContent="من رسالتك: "+item.quote;
      const open=document.createElement("button");open.type="button";open.textContent="افتح محادثة المصدر";
      open.addEventListener("click",()=>guarded(async()=>{await resume(item.conversation_id);get("chat-memory-manager").open=false;}));
      target.append(p,open);
    }
    get("chat-memory-sources").open=true;
  }
  async function memoryDashboard() {
    const seq=chatSequence;
    const [health,projects,state]=await Promise.all([post("memory-health"),post("projects"),
      chatConversation ? post("conversation-state",{conversation_id:chatConversation}) : Promise.resolve(null)]);
    if(seq!==chatSequence)return;
    const count = value => Object.entries(value || {}).map(([k,v])=>k+": "+v).join(" · ") || "0";
    get("chat-memory-health").textContent=(health.configured ? "تعلم محلي · "+health.worker : "محرك التعلم غير مهيأ؛ السجل والذاكرة اليدوية متاحين")+
      " | التعلم: "+count(health.jobs)+" | الفهرسة: "+count(health.index)+" | الخزنة: "+count(health.vault);
    get("chat-memory-health").textContent+=" | ملاحظات المشروعات: "+count(health.project_vault);
    projectRecords=projects.items;
    const project=get("chat-memory-project"), prior=project.value || state?.project_id || "";
    project.replaceChildren();
    const empty=document.createElement("option");empty.value="";empty.textContent="بدون مشروع";project.append(empty);
    for(const item of projects.items) {
      const option=document.createElement("option");option.value=item.id;option.textContent=item.name;project.append(option);
    }
    project.value=projects.items.some(p=>p.id===prior) ? prior : "";
    associationRevision=state?.revision || 0;
    get("chat-conversation-state").textContent=state ? (Object.values(state.state || {}).map(v=>v.quote).join(" · ") || "لسه مفيش نقطة تقدم محفوظة للمحادثة دي.") : "ابدأ أو افتح محادثة لعرض تقدمها.";
    await refreshMemories();
  }
  async function browseMemories(append=false) {
    const seq=chatSequence,data=await post("memory-browse",{status:get("chat-memory-lifecycle").value || "current",offset:append ? browseOffset : 0});
    if(seq!==chatSequence)return;
    const target=get("chat-memory-lifecycle-list");if(!append)target.replaceChildren();
    for(const item of data.items) {
      const record=item.snapshot || item, p=document.createElement("p");p.dir="auto";
      p.textContent=(labels[item.status] || item.status)+" · "+(record.content || "النص محذوف")+" · v"+item.revision;
      const open=document.createElement("button");open.type="button";open.textContent="المصدر والإصدارات";
      open.addEventListener("click",()=>guarded(()=>showSources(item.memory_id || item.id)));target.append(p,open);
    }
    if(!data.items.length&&!append)target.textContent="لا توجد معلومات بالحالة دي / No entries";
    browseOffset=data.next_offset;get("chat-memory-browse-more").hidden=browseOffset===null;
  }
  async function archiveSearch(append=false) {
    const scope=get("chat-archive-scope").value;
    if(scope==="conversation"&&!chatConversation)throw new Error("افتح محادثة الأول.");
    if(scope==="project"&&!selectedProject())throw new Error("اختار مشروع الأول.");
    const seq=chatSequence,data=await post("memory-search",{query:get("chat-archive-query").value,
      conversation_id:scope==="conversation" ? chatConversation : null,
      project_id:scope==="project" ? selectedProject() : null,before:append ? archiveBefore : null});
    if(seq!==chatSequence)return;
    const target=get("chat-archive-results");if(!append)target.replaceChildren();
    for(const item of data.items) {
      const article=document.createElement("article"),p=document.createElement("p");p.dir="auto";
      p.textContent=item.title+" · "+new Date(item.created_at*1000).toLocaleString()+"\n"+item.owner_excerpt;
      const assistant=document.createElement("p");assistant.dir="auto";
      assistant.textContent=item.assistant_excerpt ? "رد سابق غير متحقق: "+item.assistant_excerpt : "";
      const open=document.createElement("button");open.type="button";open.textContent="افتح المحادثة";
      open.addEventListener("click",()=>guarded(async()=>{await resume(item.conversation_id);get("chat-memory-manager").open=false;}));
      article.append(p,assistant,open);target.append(article);
    }
    if(!data.items.length&&!append)target.textContent="مش لاقي نص مطابق في السجل / No matching history";
    archiveBefore=data.next_before;get("chat-archive-more").hidden=archiveBefore===null;
  }
  async function library(append=false) {
    const seq = chatSequence;
    const data = await post("conversations", {before:append ? moreConversations : null});
    if (seq !== chatSequence) return;
    const select = get("chat-conversations");
    if (!append) {
      select.replaceChildren(); const blank=document.createElement("option");
      blank.value=""; blank.textContent="اختر محادثة محفوظة"; select.append(blank);
    }
    for (const item of data.items) {
      const option = document.createElement("option"); option.value=item.id;
      option.textContent=item.title; select.append(option);
    }
    moreConversations=data.next_before; get("chat-history-more").hidden=!moreConversations;
    select.value=chatConversation || "";
    return data;
  }
  function displayTurns(data, prepend=false) {
    const previous = prepend ? [...log.children] : [];
    if (!prepend) {chatTurns=[]; chatRetry=null;}
    log.replaceChildren();
    for (const turn of data.turns) {
      bubble("user",turn.message); chatTurns.push({role:"user",content:turn.message});
      if (turn.response) {
        const box=bubble("assistant",turn.response.answer);
        chatTurns.push({role:"assistant",content:turn.response.answer});
        if (turn.response.action_run && typeof renderComputerRun === "function")
          renderComputerRun(box,turn.response.action_run);
        // Old appointment proposals are historical, never new save buttons.
        if (turn.response.context_sources?.length) {
          const note=document.createElement("small");
          note.textContent="ذاكرة محفوظة: " + turn.response.context_sources.map(s=>s.id.slice(0,8)).join(", ");
          box.append(note);
          for(const source of turn.response.context_sources.slice(0,8)) {
            const open=document.createElement("button");open.type="button";open.textContent="مصدر الذاكرة · "+source.id.slice(0,8);
            open.addEventListener("click",()=>guarded(async()=>{
              get("chat-memory-manager").open=true;await showSources(source.id);
            }));box.append(open);
          }
        }
        for(const source of (turn.response.archive_sources || []).slice(0,3)) {
          const open=document.createElement("button");open.type="button";open.textContent="محادثة سابقة · المصدر";
          open.addEventListener("click",()=>guarded(()=>resume(source.conversation_id)));box.append(open);
        }
      }
      if (!prepend && turn === data.turns.at(-1) && turn.status !== "complete" && turn.message !== "[forgotten]") {
        chatRetry={conversation_id:chatConversation,request_id:turn.request_id,message:turn.message,retry:true};
      }
    }
    log.append(...previous);
    older=data.next_before; get("chat-older").hidden=!older;
    get("chat-retry").hidden=!chatRetry;
    get("chat-greeting").hidden=log.children.length>0;
    updateChatSessionCount();
  }
  async function resume(id, prepend=false, keepSequence=false) {
    if (chatPending) return;
    if (!id) return;
    const seq=keepSequence ? chatSequence : ++chatSequence;
    if(!prepend && chatConversation!==id) {
      resetMemoryEditor();get("chat-memory-project").value="";
    }
    chatConversation=id;
    const data=await post("get", {conversation_id:id,before:prepend ? older : null});
    if (seq !== chatSequence) return;
    displayTurns(data,prepend); rememberSelection(id);
    status.textContent="محادثة محفوظة محليًا · " + (data.turns.at(-1)?.status === "running"
      ? "الطلب لسه بيتعالج؛ حدّث السجل لمتابعته." : "جاهزة للاستكمال");
    get("chat-conversations").value=id;
    await guarded(memoryDashboard);
  }
  async function guarded(operation) {
    try {await operation();} catch(error) {status.textContent=error.message || "تعذر الطلب المحلي.";}
  }
  chatLoadLibrary = async () => {
    if (chatPending) return;
    await guarded(async () => {
      const data=await library(); if (!data) return;
      const id=typeof window !== "undefined" ? window.history.state?.okalConversation : null;
      if (id && data.items.some(v=>v.id===id)) await resume(id);
      else if (!chatReady && data.items.length) await resume(data.items[0].id);
      const settings=await post("settings"); get("chat-retention").value=settings.retention_days;
      await refreshMemories(); chatReady=true;
    });
  };
  async function sendMessage(value, retry=null) {
    const message=String(value || "").trim();
    if (!message || chatPending || message.length>900) return;
    chatPending=true; send.disabled=true;
    const seq=++chatSequence; chatAbort=new AbortController();
    status.textContent="OKAL بيحفظ الطلب وبيحلّله محليًا...";
    try {
      if (!chatConversation) {
        const created=await post("create");
        if (seq!==chatSequence) return;
        chatConversation=created.id; rememberSelection(created.id);
      }
      const payload=retry || {conversation_id:chatConversation,
        request_id:crypto.randomUUID().replaceAll("-", ""),message,retry:false};
      chatRetry=payload; get("chat-retry").hidden=true;
      entry.value="";
      const data=await post("turn",payload);
      if (seq!==chatSequence) return;
      chatPending=false;
      await resume(chatConversation,false,true);
      if (seq!==chatSequence) return;
      if (data.proposal) {
        const box=log.children[log.children.length-1];
        if (box) proposalForm(data.proposal,box);
      }
      status.textContent=data.mode === "action_plan" ? "خطة أدوات محلية؛ راجع الحالة والإيصالات في الرسالة"
        : data.mode === "pinned_local_ollama"
        ? "Ollama المحلي · المحادثة محفوظة" + (data.history_limited ? " · السياق مختصر" : "")
        : data.mode === "owner_memory" ? "تمت معالجة طلب الذاكرة محليًا"
        : "Ollama غير متاح أو مشغول · رد محدود من البيانات المحفوظة؛ تقدر تعيد المحاولة";
      await library();
    } catch(error) {
      if (seq===chatSequence && error.name!=="AbortError") {
        status.textContent=error.message + " الطلب ممكن يكون محفوظ؛ إعادة المحاولة تستخدم نفس المعرّف.";
        get("chat-retry").hidden=!chatRetry;
      }
    } finally {
      if (seq===chatSequence) {chatPending=false; send.disabled=false; chatAbort=null; entry.focus();}
    }
  }
  get("chat-retry").addEventListener("click",()=>{
    if(chatRetry) sendMessage(chatRetry.message,{...chatRetry,retry:true});
  });
  get("chat-conversations").addEventListener("change",()=>guarded(()=>resume(get("chat-conversations").value)));
  get("chat-history-refresh").addEventListener("click",()=>guarded(async()=>{
    await library(); if(chatConversation) await resume(chatConversation); else await refreshMemories();
  }));
  get("chat-history-more").addEventListener("click",()=>guarded(()=>library(true)));
  get("chat-older").addEventListener("click",()=>guarded(()=>resume(chatConversation,true)));
  get("chat-delete").addEventListener("click",()=>guarded(async()=>{
    if(!chatConversation || !confirm("حذف المحادثة والذاكرة المرتبطة بها؟")) return;
    const id=chatConversation; clearChatUI(); rememberSelection(null);
    await post("delete",{conversation_id:id}); await library(); await refreshMemories();
  }));
  get("chat-retention-save").addEventListener("click",()=>guarded(async()=>{
    if(Number(get("chat-retention").value)>0 && !confirm("تطبيق المدة وحذف المحادثات الأقدم منها؟")) return;
    await post("settings",{days:Number(get("chat-retention").value)});
    clearChatUI(); rememberSelection(null); await chatLoadLibrary();
  }));
  get("chat-memory-reset").addEventListener("click",resetMemoryEditor);
  get("chat-memory-form").addEventListener("submit",event=>{
    event.preventDefault(); guarded(async()=>{
      if(get("chat-memory-scope").value==="conversation" && !chatConversation)
        throw new Error("ابدأ محادثة الأول.");
      const scope=get("chat-memory-scope").value;
      if(scope==="project" && !(editingProject || selectedProject()))throw new Error("اختار مشروع الأول.");
      await post("memory-save",{key:get("chat-memory-key").value,content:get("chat-memory-value").value,
        kind:get("chat-memory-kind").value,revision:memoryRevision,
        conversation_id:scope==="conversation" ? chatConversation : null,
        project_id:scope==="project" ? (editingProject || selectedProject()) : null,
        days:Number(get("chat-memory-days").value)});
      resetMemoryEditor(); await refreshMemories();
      if(chatConversation) await resume(chatConversation);
      await library();
      status.textContent="المعلومة محفوظة بطلبك؛ تقدر تعدّلها أو تنساها.";
    });
  });
  get("chat-memory-manager").addEventListener("toggle",()=>{
    if(get("chat-memory-manager").open)guarded(memoryDashboard);
  });
  get("chat-memory-health-refresh").addEventListener("click",()=>guarded(memoryDashboard));
  get("chat-memory-project").addEventListener("change",()=>guarded(refreshMemories));
  get("chat-memory-browse").addEventListener("click",()=>guarded(()=>browseMemories()));
  get("chat-memory-browse-more").addEventListener("click",()=>guarded(()=>browseMemories(true)));
  get("chat-memory-retry").addEventListener("click",()=>guarded(async()=>{
    await post("memory-retry");await memoryDashboard();
  }));
  get("chat-memory-backfill").addEventListener("click",()=>guarded(async()=>{
    await post("memory-backfill");await memoryDashboard();
    status.textContent="تمت جدولة دفعة من السجل المحلي؛ التقدم ظاهر في حالة التعلم.";
  }));
  get("chat-memory-rebuild").addEventListener("click",()=>guarded(async()=>{
    await post("memory-rebuild");await memoryDashboard();
    status.textContent="تمت جدولة إعادة بناء الفهرس؛ السجل الأصلي محفوظ.";
  }));
  get("chat-project-form").addEventListener("submit",event=>{
    event.preventDefault();guarded(async()=>{
      const result=await post("project-save",{name:get("chat-project-name").value,description:get("chat-project-description").value,
        project_id:projectEdit?.id || null,revision:projectEdit?.revision || 0});
      projectEdit=null;
      get("chat-project-name").value="";get("chat-project-description").value="";
      await memoryDashboard();get("chat-memory-project").value=result.id;await refreshMemories();
    });
  });
  get("chat-project-edit").addEventListener("click",()=>guarded(async()=>{
    projectEdit=projectRecords.find(p=>p.id===selectedProject()) || null;
    if(!projectEdit)throw new Error("اختار مشروع الأول.");
    get("chat-project-name").value=projectEdit.name;get("chat-project-description").value=projectEdit.description;
    get("chat-project-name").focus();
  }));
  get("chat-project-new").addEventListener("click",()=>{
    projectEdit=null;get("chat-project-name").value="";get("chat-project-description").value="";
  });
  get("chat-project-associate").addEventListener("click",()=>guarded(async()=>{
    if(!chatConversation)throw new Error("ابدأ أو افتح محادثة الأول.");
    await post("project-associate",{conversation_id:chatConversation,project_id:selectedProject(),revision:associationRevision});
    await memoryDashboard();status.textContent="تم تحديث ارتباط المشروع بطلبك؛ مفيش تنفيذ أدوات تلقائي.";
  }));
  get("chat-archive-form").addEventListener("submit",event=>{event.preventDefault();guarded(()=>archiveSearch());});
  get("chat-archive-more").addEventListener("click",()=>guarded(()=>archiveSearch(true)));
  get("chat-vault-memory").addEventListener("input",()=>{vaultPreview=null;get("chat-vault-import").hidden=true;});
  get("chat-vault-preview").addEventListener("click",()=>guarded(async()=>{
    const seq=chatSequence,preview=await post("vault-preview",{memory_id:get("chat-vault-memory").value});
    if(seq!==chatSequence)return;
    vaultPreview=preview;get("chat-vault-preview-text").textContent=preview.content;
    get("chat-vault-import").hidden=!preview.changed;
  }));
  get("chat-vault-import").addEventListener("click",()=>guarded(async()=>{
    if(!vaultPreview || !confirm("اعتماد النص الظاهر كتعديل منك على المعلومة؟"))return;
    await post("vault-import",{memory_id:vaultPreview.memory_id,revision:vaultPreview.revision});
    resetMemoryEditor();await memoryDashboard();
  }));
  get("chat-vault-project-preview").addEventListener("click",()=>guarded(async()=>{
    if(!selectedProject())throw new Error("اختار مشروع الأول.");
    const seq=chatSequence,preview=await post("vault-project-preview",{project_id:selectedProject()});
    if(seq!==chatSequence)return;
    projectVaultPreview=preview;get("chat-vault-project-text").textContent=preview.content;
    get("chat-vault-project-import").hidden=!preview.changed;
  }));
  get("chat-vault-project-import").addEventListener("click",()=>guarded(async()=>{
    if(!projectVaultPreview || !confirm("اعتماد وصف المشروع الظاهر كتعديل منك؟"))return;
    await post("vault-project-import",{project_id:projectVaultPreview.project_id,revision:projectVaultPreview.revision});
    resetMemoryEditor();await memoryDashboard();
  }));

  get("chat-form").addEventListener("submit", event => {
    event.preventDefault();
    sendMessage(entry.value);
  });
  entry.addEventListener("keydown", event => {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      sendMessage(entry.value);
    }
  });
  get("chat-new").addEventListener("click", () => {
    clearChatUI();
    resetMemoryEditor();
    rememberSelection(null);
    guarded(async()=>{await library(); await refreshMemories(); chatReady=true;});
    entry.focus();
  });
  for (const button of document.querySelectorAll("[data-chat-prompt]")) {
    button.addEventListener("click",() => sendMessage(button.getAttribute("data-chat-prompt")));
  }
})();
