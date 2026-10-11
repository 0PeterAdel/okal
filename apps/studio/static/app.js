"use strict";

const SCHEMA = "okal.studio.canvas.v1";
const csrf = document.querySelector('meta[name="okal-csrf"]').content;
const content = document.getElementById("canvasContent");
const source = document.getElementById("canvasSource");
const footnote = document.getElementById("canvasFootnote");
const list = document.getElementById("conversationList");
const input = document.getElementById("promptInput");
const orb = document.getElementById("orbField");
const phaseLabel = document.getElementById("phaseLabel");
const mic = document.getElementById("micButton");
const orbAction = document.getElementById("orbAction");
const connection = document.getElementById("connectionLabel");
const toast = document.getElementById("toast");
const demos = {
  chart: {
    schema_version: SCHEMA, kind: "chart", title: "الأفكار بتوضح لما نشوفها.",
    subtitle: "مثال لشكل مخطط يقدر Okal يعرضه لما توصله بيانات فعلية.",
    source: "معاينة تصميمية", unit: "%",
    series: [{label:"بحث",value:74},{label:"كود",value:52},{label:"تعلم",value:91},
             {label:"مهام",value:66},{label:"إبداع",value:83}]
  },
  gallery: {
    schema_version: SCHEMA, kind: "gallery", title: "الصورة جزء من الحوار.",
    subtitle: "مساحة لعرض صور أو نتائج بصرية داخل نفس المحادثة.",
    source: "رسوم توضيحية أصلية", images: [
      {src:"/assets/noor.svg",alt:"تشكيل ضوئي هادئ",caption:"ضوء الفكرة"},
      {src:"/assets/terrain.svg",alt:"طبقات منظر تجريدي",caption:"مسارات جديدة"},
      {src:"/assets/atlas.svg",alt:"شبكة مدارية مجردة",caption:"زاوية أوسع"}
    ]
  },
  steps: {
    schema_version: SCHEMA, kind: "steps", title: "من الفكرة للخطوة الجاية.",
    subtitle: "مثال لخطة مرئية. التنفيذ الفعلي يحتاج وكيلًا موصولًا وسياسة واضحة.",
    source: "معاينة تصميمية", steps: [
      {title:"نفهم المطلوب",detail:"نحدد الهدف والقيود والنتيجة التي يمكن التحقق منها.",state:"done"},
      {title:"نرتّب الخيارات",detail:"نجمع المسارات الممكنة ونقارن الجهد والفائدة.",state:"active"},
      {title:"نراجع قبل التنفيذ",detail:"أي إجراء مؤثر ينتظر موافقتك الصريحة.",state:"waiting"},
      {title:"نُظهر الدليل",detail:"النتيجة ترتبط بمصدرها وحالة التحقق منها.",state:"waiting"}
    ]
  }
};

let currentView = "home";
let preview = null;
let liveCanvas = null;
let sessionCanvas = null;
let liveSignature = "";
let dismissedCanvas = false;
let voice = {available:false, phase:"idle", text:"", session_id:""};
let awaitingReply = false;
let lastCompletedSession = "";
let toastTimer = null;
let displayName = "بيتر";
const activity = [];

function node(tag, className, text) {
  const item = document.createElement(tag);
  if (className) item.className = className;
  if (text !== undefined) item.textContent = String(text);
  return item;
}
function append(parent, ...children) { children.forEach(child => parent.appendChild(child)); return parent; }
function setCanvasMeta(status, note) { source.textContent = status; footnote.textContent = note; }
function heading(target, eyebrow, title, subtitle) {
  append(target, node("div","panel-eyebrow",eyebrow), node("h3","panel-title",title),
         node("p","panel-subtitle",subtitle));
}
function note(target, text) { target.appendChild(node("div","panel-note",text)); }

function renderCanvas(data, isPreview) {
  content.replaceChildren();
  const pane = node("div", data.kind + "-panel");
  heading(pane, isPreview ? "DESIGN PREVIEW / EXAMPLE" : "OKAL CANVAS / LIVE",
          data.title, data.subtitle);
  if (data.kind === "text") {
    pane.appendChild(node("div","text-body",data.body || ""));
    if (data.highlights && data.highlights.length) {
      const ul = node("ul","highlight-list");
      data.highlights.forEach(item => append(ul, append(node("li"),node("span","",item))));
      pane.appendChild(ul);
    }
  } else if (data.kind === "chart") {
    const bars = node("div","chart-bars");
    (data.series || []).forEach(point => {
      const col = node("div","chart-column");
      const value = Number(point.value);
      const bar = node("div","bar");
      bar.style.height = Math.max(3, Math.min(100, value)) + "%";
      append(col, node("div","bar-value",value + (data.unit || "")), bar,
             node("div","bar-label",point.label));
      bars.appendChild(col);
    });
    append(pane,bars,node("div","chart-spacer"));
  } else if (data.kind === "gallery") {
    const gallery = node("div","gallery-grid");
    (data.images || []).forEach(image => {
      const figure = node("figure","gallery-card");
      const img = node("img");
      img.src = image.src;
      img.alt = image.alt || "";
      img.loading = "lazy";
      append(figure,img,node("figcaption","",image.caption || ""));
      gallery.appendChild(figure);
    });
    pane.appendChild(gallery);
  } else if (data.kind === "steps") {
    (data.steps || []).forEach((step, index) => {
      const row = node("div","step-row " + step.state);
      append(row,node("span","step-index",String(index + 1).padStart(2,"0")),
             append(node("div"),node("h4","",step.title),node("p","",step.detail)));
      pane.appendChild(row);
    });
  }
  note(pane, isPreview ? "المحتوى توضيحي — ليس نتيجة مهمة فعلية." :
       "وصل المحتوى من ملف العرض المحلي. المصدر: " + (data.source || "غير مذكور"));
  content.appendChild(pane);
  setCanvasMeta(isPreview ? "معاينة" : "محتوى محلي", isPreview ? "مثال تصميمي" : (data.source || "مصدر غير مذكور"));
}

function renderHome() {
  content.replaceChildren();
  const art = node("div","empty-art");
  const orbit = node("div","empty-orbit");
  append(orbit,node("span"),node("span"),node("span"));
  append(art,orbit,node("span","empty-marker","READY FOR WHAT'S NEXT"));
  append(content,art,node("h3",""));
  const title = content.querySelector("h3");
  append(title,document.createTextNode("المساحة دي بتتشكّل"),node("br"),node("i","","حسب اللي تحتاجه."));
  content.appendChild(node("p","","كلام، صورة، مخطط، أو خطوات واضحة — اختار معاينة تحت أو ابدأ بطلبك."));
  setCanvasMeta("معاينة","المعاينات أمثلة تصميمية");
}
function renderActivity() {
  content.replaceChildren();
  const pane = node("div","steps-panel");
  heading(pane,"SESSION ACTIVITY","خطوة بخطوة، قدامك.","اللي حصل في هذه النافذة فقط؛ لا توجد مهام منفّذة مخفية.");
  const rows = activity.slice(-6).reverse();
  if (!rows.length) pane.appendChild(node("p","panel-subtitle","لسه ما فيش نشاط هنا. جرّب معاينة أو اسأل Okal."));
  rows.forEach((entry, i) => {
    const row = node("div","step-row " + (i === 0 ? "active" : "done"));
    append(row,node("span","step-index",entry.time),
           append(node("div"),node("h4","",entry.title),node("p","",entry.detail)));
    pane.appendChild(row);
  });
  note(pane,"سجل هذه النافذة مؤقت؛ ليس سجل تنفيذ موثّق.");
  content.appendChild(pane);
  setCanvasMeta("النشاط","جلسة المتصفح الحالية");
}
function renderAgents() {
  content.replaceChildren();
  const pane = node("div","steps-panel");
  heading(pane,"SPECIALIST SPACE","كل فكرة، مع الشخص المناسب.","أماكن مخصصة للوكلاء. ربط المهام والأذونات لم يكتمل بعد.");
  [["بحث وابتكار","تقصّي المصادر وتحليل الأفكار"],["برمجة","فهم الكود والتغيير المنضبط"],
   ["محتوى اجتماعي","صياغة ومراجعة قبل النشر"],["أعمال حرة","فرص وعروض تتطلب مراجعتك"]]
    .forEach(pair => {
      const card = node("div","agent-card");
      append(card,append(node("div"),node("strong","",pair[0]),node("small","",pair[1])),
             node("span","","بانتظار الربط"));
      pane.appendChild(card);
    });
  note(pane,"عرض تعريفي فقط؛ لا توجد صلاحيات تنفيذ من هذه الشاشة.");
  content.appendChild(pane);
  setCanvasMeta("الوكلاء","عرض تعريفي");
}
function renderSettings() {
  content.replaceChildren();
  const pane = node("div","steps-panel");
  heading(pane,"YOUR SPACE / SETTINGS","خليها شبهك.","إعدادات هذه الواجهة محفوظة داخل متصفحك فقط.");
  const themeRow = node("div","setting-row");
  const swatches = node("div","theme-buttons");
  [["mint","#a8eee0"],["lilac","#c5bbf5"],["amber","#f0d5a1"]].forEach(pair => {
    const button = node("button");
    button.type = "button"; button.style.background = pair[1]; button.dataset.theme = pair[0];
    button.setAttribute("aria-label","لون " + pair[0]);
    button.title = pair[0];
    button.addEventListener("click",() => applyTheme(pair[0]));
    swatches.appendChild(button);
  });
  append(themeRow,append(node("div"),node("span","","لون الإضاءة"),node("small","","اختيار بصري؛ لا يغير أداء النموذج")),swatches);
  const nameRow = node("div","setting-row");
  const nameInput = node("input","name-input");
  nameInput.type = "text";
  nameInput.maxLength = 24;
  nameInput.value = displayName;
  nameInput.setAttribute("aria-label","الاسم المفضل");
  nameInput.addEventListener("change",() => {
    displayName = nameInput.value.trim().slice(0,24) || "صديقي";
    try { localStorage.setItem("okal-name",displayName); } catch (_) { /* visual preference only */ }
    updateClock();
  });
  append(nameRow,append(node("div"),node("span","","أناديك بإيه؟"),node("small","","بيتخزن في متصفحك بس")),nameInput);
  const motionRow = node("div","setting-row");
  const motion = node("button","toggle-button",document.body.classList.contains("reduce-motion") ? "تشغيل" : "إيقاف");
  motion.type = "button";
  motion.addEventListener("click",() => {
    const reduced = document.body.classList.toggle("reduce-motion");
    localStorage.setItem("okal-motion",reduced ? "off" : "on");
    motion.textContent = reduced ? "تشغيل" : "إيقاف";
  });
  append(motionRow,append(node("div"),node("span","","الحركة الهادئة"),node("small","","تقليل حركة العناصر المتوهجة")),motion);
  append(pane,nameRow,themeRow,motionRow);
  note(pane,"الاتصال بخدمة الصوت على جهازك فقط. لا توجد خدمات سحابية في هذه الشاشة.");
  content.appendChild(pane);
  setCanvasMeta("تخصيص","داخل المتصفح");
  markTheme();
}
function addActivity(title, detail) {
  const time = new Intl.DateTimeFormat("ar-EG",{hour:"2-digit",minute:"2-digit"}).format(new Date());
  activity.push({time,title,detail});
  if (activity.length > 30) activity.shift();
  if (currentView === "activity") renderActivity();
}
function setView(view) {
  currentView = view;
  document.querySelectorAll("[data-view]").forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle("selected",active);
    if (active) button.setAttribute("aria-current","page");
    else button.removeAttribute("aria-current");
  });
  if (view === "activity") renderActivity();
  else if (view === "agents") renderAgents();
  else if (view === "settings") renderSettings();
  else if (dismissedCanvas) renderHome();
  else if (preview) renderCanvas(preview,true);
  else if (sessionCanvas) renderCanvas(sessionCanvas,false);
  else if (liveCanvas) renderCanvas(liveCanvas,false);
  else renderHome();
}
function showDemo(kind) {
  preview = demos[kind];
  dismissedCanvas = false;
  setView("canvas");
  addActivity("معاينة " + (kind === "chart" ? "مخطط" : kind === "gallery" ? "صور" : "خطة"),
              "عرض توضيحي، لا توجد بيانات أو مهمة حقيقية.");
}
function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"),3500);
}
function addMessage(kind,text) {
  const empty = document.getElementById("conversationEmpty");
  if (empty) empty.remove();
  const message = node("div","message " + kind,text);
  list.appendChild(message);
  list.scrollTop = list.scrollHeight;
}
function voiceCanvas(title,body,sourceName) {
  return {schema_version:SCHEMA,kind:"text",title,subtitle:"من خدمة Okal الصوتية على جهازك.",
          source:sourceName,body,highlights:[]};
}
function labelFor(phase, available) {
  if (!available) return "واجهة جاهزة · خدمة الصوت غير متصلة";
  return ({
    idle:"جاهز لما تكون جاهز", listening:"بسمعك... اضغط تاني لما تخلص",
    transcribing:"بحوّل كلامك لنص", reviewing:"راجع الكلام قبل المتابعة",
    routing:"بفهم طلبك", speaking:"برد عليك دلوقتي",
    blocked:"الطلب محتاج توضيح", error:"في مشكلة في الصوت"
  })[phase] || "جاهز لما تكون جاهز";
}
function updateVoice(next) {
  voice = next;
  const phase = next.phase || "idle";
  orb.dataset.phase = phase;
  phaseLabel.textContent = labelFor(phase,next.available);
  connection.classList.toggle("offline",!next.available);
  connection.lastChild.textContent = next.available ? " خدمة الصوت متصلة" : " خدمة الصوت غير متصلة";
  mic.classList.toggle("active",phase === "listening");
  mic.setAttribute("aria-label",phase === "listening" ? "أنهِ التسجيل" :
                   phase === "idle" ? "ابدأ التحدث" : "إلغاء جلسة الصوت");
  mic.title = mic.getAttribute("aria-label");
  orbAction.setAttribute("aria-label",mic.getAttribute("aria-label"));
  orbAction.title = mic.title;
  if (awaitingReply && phase === "idle" && next.session_id &&
      next.session_id !== lastCompletedSession && next.text &&
      !next.text.startsWith("Cancelled")) {
    addMessage("okal",next.text);
    addActivity("رد صوتي",next.text.slice(0,120));
    sessionCanvas = voiceCanvas("ردّ Okal",next.text,"خدمة الصوت المحلية");
    preview = null;
    dismissedCanvas = false;
    setView("canvas");
    lastCompletedSession = next.session_id;
    awaitingReply = false;
  }
  if (awaitingReply && (phase === "error" || phase === "blocked")) {
    addMessage("system",next.text || "تعذر إتمام جلسة الصوت.");
    sessionCanvas = voiceCanvas(phase === "blocked" ? "الطلب متوقف" : "مشكلة في الصوت",
                                next.text || "تعذر إتمام جلسة الصوت.","حالة خدمة الصوت");
    preview = null;
    dismissedCanvas = false;
    setView("canvas");
    awaitingReply = false;
  }
}
async function poll() {
  try {
    const response = await fetch("/api/state",{cache:"no-store"});
    if (!response.ok) throw new Error("status");
    const state = await response.json();
    updateVoice(state.voice);
    const signature = JSON.stringify(state.canvas);
    if (signature !== liveSignature) {
      liveSignature = signature;
      liveCanvas = state.canvas;
      if (liveCanvas) {
        preview = null;
        sessionCanvas = null;
        dismissedCanvas = false;
        if (currentView === "home" || currentView === "canvas") setView("canvas");
      } else if (currentView === "home" || currentView === "canvas") setView(currentView);
    }
  } catch (_) {
    updateVoice({available:false,phase:"idle",text:"",session_id:""});
  }
}
async function sendVoice(command,text) {
  const response = await fetch("/api/voice",{
    method:"POST",
    headers:{"Content-Type":"application/json","X-Okal-CSRF":csrf},
    body:JSON.stringify({command,text})
  });
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.error || "خدمة الصوت غير متاحة");
  await poll();
  return result;
}
async function sendPrompt() {
  const text = input.value.trim();
  if (!text) return;
  if (!voice.available) { showToast("شغّل خدمة صوت Okal أولاً؛ النص محفوظ في الخانة."); return; }
  try {
    document.getElementById("sendButton").disabled = true;
    lastCompletedSession = voice.session_id || "";
    awaitingReply = true;
    preview = null;
    sessionCanvas = voiceCanvas("طلبك قدامي",text,"طلب مكتوب · بانتظار الرد");
    dismissedCanvas = false;
    setView("canvas");
    await sendVoice("ask",text);
    addMessage("user",text);
    addActivity("طلب مكتوب",text.slice(0,120));
    input.value = "";
    input.style.height = "";
  } catch (error) {
    awaitingReply = false;
    sessionCanvas = voiceCanvas("تعذر إرسال الطلب",error.message,"خدمة الصوت غير متاحة");
    setView("canvas");
    showToast(error.message);
  }
  finally { document.getElementById("sendButton").disabled = false; }
}
async function toggleMic() {
  if (!voice.available) { showToast("خدمة الصوت غير متصلة. شغّل okal-voice.service أولاً."); return; }
  const previousPhase = voice.phase;
  const command = ["idle","listening"].includes(previousPhase) ? "toggle" : "cancel";
  try {
    if (previousPhase === "idle") lastCompletedSession = voice.session_id || "";
    if (previousPhase === "listening") awaitingReply = true;
    await sendVoice(command,"");
    if (command === "toggle") {
      addActivity(previousPhase === "listening" ? "تسجيل صوتي" : "بدء الاستماع",
                  "تعمل خدمة Okal الصوتية على جهازك.");
    } else { awaitingReply = false; addActivity("إلغاء","تم طلب إلغاء جلسة الصوت."); }
  } catch (error) { awaitingReply = false; showToast(error.message); }
}
function markTheme() {
  const theme = localStorage.getItem("okal-theme") || "mint";
  document.querySelectorAll("[data-theme]").forEach(button =>
    button.classList.toggle("selected",button.dataset.theme === theme));
}
function applyTheme(theme) {
  const choices = {
    mint:["#a8eee0","#d2fff4","111,227,207"],
    lilac:["#c5bbf5","#eae4ff","181,164,242"],
    amber:["#f0d5a1","#fff0d1","240,204,151"]
  };
  const selected = choices[theme] || choices.mint;
  document.documentElement.style.setProperty("--mint",selected[0]);
  document.documentElement.style.setProperty("--mint-bright",selected[1]);
  orb.style.setProperty("--orb-color",selected[2]);
  localStorage.setItem("okal-theme",theme);
  markTheme();
}
function updateClock() {
  document.getElementById("clock").textContent =
    new Intl.DateTimeFormat("ar-EG",{hour:"2-digit",minute:"2-digit"}).format(new Date());
  const hour = new Date().getHours();
  document.getElementById("timeGreeting").textContent =
    (hour < 12 ? "صباح الخير" : hour < 17 ? "نهارك جميل" : "مساء الخير") + "، " + displayName;
}

document.querySelectorAll("[data-view]").forEach(button =>
  button.addEventListener("click",() => setView(button.dataset.view)));
document.querySelectorAll("[data-demo]").forEach(button =>
  button.addEventListener("click",() => showDemo(button.dataset.demo)));
document.getElementById("resetCanvas").addEventListener("click",() => {
  preview = null; sessionCanvas = null; dismissedCanvas = true; setView("home");
});
document.getElementById("clearChat").addEventListener("click",() => {
  list.replaceChildren(node("div","conversation-empty","المحادثة الظاهرة اتْمسحت من النافذة دي."));
});
document.getElementById("sendButton").addEventListener("click",sendPrompt);
mic.addEventListener("click",toggleMic);
orbAction.addEventListener("click",toggleMic);
input.addEventListener("keydown",event => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault(); sendPrompt();
  }
});
input.addEventListener("input",() => {
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight,100) + "px";
});
try {
  displayName = localStorage.getItem("okal-name") || displayName;
  if (localStorage.getItem("okal-motion") === "off") document.body.classList.add("reduce-motion");
  applyTheme(localStorage.getItem("okal-theme") || "mint");
} catch (_) { /* Storage may be disabled; the default remains usable. */ }
updateClock();
setInterval(updateClock,30000);
poll();
setInterval(poll,1000);
