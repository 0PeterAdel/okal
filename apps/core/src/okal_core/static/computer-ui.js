"use strict";
/* Explicit owner scopes; no credentials or transcripts in browser storage. */
let computerPolicyRevision=0;
const computerPost=async(path,payload={})=>{
  const response=await fetch("/api/v1/actions/"+path,{method:"POST",credentials:"same-origin",
    cache:"no-store",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  if(!response.ok)throw new Error(response.status===403 ? "الصلاحية غير متاحة أو الخطة انتهت. راجع الإعدادات."
    : response.status===409 ? "الحالة اتغيّرت؛ حدّث الخطة قبل التنفيذ." : "تعذر الطلب؛ افحص الجاهزية والمدخلات.");
  return response.json();
};
function computerRootsFromText(value){
  return value.split("\n").map(v=>v.trim()).filter(Boolean).map(line=>{
    const match=/^(read|write) (\/.*)$/.exec(line);
    if(!match)throw new Error("كل سطر مجلد يبدأ بـ read أو write ثم مسار كامل.");
    return {root:match[2],write:match[1]==="write"};
  });
}
function clearComputerUI(){
  for(const id of ["computer-roots","computer-origins","computer-apps","computer-commands","computer-accounts"]){
    const node=document.getElementById(id);if(node)node.value="";
  }
  const form=document.getElementById("computer-policy-form");if(form)form.hidden=true;
  computerPolicyRevision=0;
}
function renderComputerRun(parent,id){
  const card=document.createElement("section");card.className="computer-run";
  card.setAttribute("aria-label","خطة وإيصالات التنفيذ");parent.append(card);
  let timer=null,starting=false,generation=0;
  const line=(tag,value)=>{const n=document.createElement(tag);n.textContent=value;card.append(n);return n;};
  const button=(label,action)=>{
    const n=line("button",label);n.type="button";
    n.addEventListener("click",async()=>{
      n.disabled=true;
      try{await action();await refresh();}catch(error){line("p",error.message);n.disabled=false;}
    });
  };
  async function refresh(){
    const active=++generation;
    if(timer){clearTimeout(timer);timer=null;}
    if(card.isConnected===false){if(timer)clearTimeout(timer);return;}
    try{
      const run=await computerPost("get",{run_id:id});
      if(card.isConnected===false || active!==generation)return;
      card.replaceChildren();line("strong","خطة التنفيذ وإيصالاتها / Action plan & receipts");
      line("p","الحالة / Status: "+run.status+" · "+run.steps.filter(s=>s.status==="verified").length+" خطوات متحققة من "+run.steps.length);
      for(let i=0;i<run.plan.steps.length;i++){
        const step=run.plan.steps[i],record=run.steps[i];
        line("h4",String(i+1)+". "+step.tool+" · "+record.status);
        if(run.status==="awaiting_approval"){
          const changes=run.preview[i]?.moves;
          if(changes)line("p",changes.slice(0,12).map(v=>v.source+" → "+v.destination).join("\n")+
            (changes.length>12 ? "\n… "+changes.length+" تغييرات؛ افتح التفاصيل لمراجعتها" : ""));
          else line("p",Object.entries(step.arguments).filter(([k])=>["path","source","destination","output","url","title","account"].includes(k))
            .map(([k,v])=>k+": "+v).join(" · "));
        }
        const details=document.createElement("details");const summary=document.createElement("summary");
        summary.textContent="التفاصيل والمصادر والتغييرات / Preview & evidence";details.append(summary);
        const pre=document.createElement("pre");pre.textContent=JSON.stringify({arguments:step.arguments,
          preview:run.preview[i],receipt:record.result,error:record.error},null,2);details.append(pre);card.append(details);
        if(record.result?.summary)line("p",record.result.summary);
      }
      if(run.status==="awaiting_approval")button("أوافق على هذه الخطة بالضبط / Execute exact plan",()=>
        computerPost("execute",{run_id:id,approval_digest:run.approval_digest}));
      if(run.status==="ready" && !starting){starting=true;await computerPost("execute",{run_id:id});}
      if(["awaiting_approval","ready","running"].includes(run.status)){
        button("إلغاء / Cancel",()=>computerPost("cancel",{run_id:id}));
        timer=setTimeout(refresh,1000);
      }else{
        button("تحديث الإيصال / Refresh",async()=>{});
        if(["failed","cancelled"].includes(run.status))
          button("استكمال الخطة / Resume",()=>computerPost("resume",{run_id:id,approval_digest:run.approval_digest}));
        if(["succeeded","needs_reconciliation","failed","cancelled"].includes(run.status))
          button("استرجاع التغييرات المدعومة / Recover",async()=>{
            if(!confirm("استرجاع التغييرات الموجودة في إيصالات هذه الخطة؟ لن يتم استبدال أي ملف اتغيّر."))return;
            await computerPost("recover",{run_id:id,approval_digest:run.approval_digest});
          });
      }
    }catch(error){if(card.isConnected!==false)line("p",error.message);}
  }
  refresh();
}
(function initComputerSettings(){
  const get=id=>document.getElementById(id);
  if(!get("computer-load"))return;
  get("computer-load").addEventListener("click",async()=>{
    try{
      const data=await computerPost("capabilities"),policy=data.policy.policy;
      computerPolicyRevision=data.policy.revision;
      get("computer-policy-form").hidden=false;
      get("computer-mode").value=policy.mode;
      get("computer-roots").value=policy.roots.map(g=>(g.write ? "write " : "read ")+g.root).join("\n");
      get("computer-origins").value=policy.browser_origins.join("\n");
      get("computer-accounts").value=(policy.accounts || []).join("\n");
      get("computer-apps").value=policy.applications.join("\n");
      get("computer-commands").value=JSON.stringify(policy.commands,null,2);
      get("computer-readiness").textContent=JSON.stringify(data.readiness);
      get("computer-tools").replaceChildren();
      for(const tool of data.tools){
        const label=document.createElement("label"),input=document.createElement("input");
        input.type="checkbox";input.value=tool.name;input.checked=policy.tools.includes(tool.name);
        label.append(input,document.createTextNode(tool.name+" · "+tool.risk+" — "+tool.description));
        get("computer-tools").append(label);
      }
      get("computer-status").textContent="لا يوجد تنفيذ قبل منح الأدوات والنطاقات. التغييرات المؤثرة تحتاج مراجعة كل خطة.";
    }catch(error){get("computer-status").textContent=error.message;}
  });
  get("computer-policy-form").addEventListener("submit",async event=>{
    event.preventDefault();
    const lines=id=>get(id).value.split("\n").map(v=>v.trim()).filter(Boolean);
    try{
      if(!confirm("حفظ صلاحيات الكمبيوتر بهذه الأدوات والمجلدات والمصادر؟ الخطط القديمة ستحتاج إعادة تخطيط."))return;
      const tools=[...get("computer-tools").querySelectorAll("input:checked")].map(n=>n.value);
      const data=await computerPost("policy",{revision:computerPolicyRevision,policy:{mode:get("computer-mode").value,
        tools,roots:computerRootsFromText(get("computer-roots").value),
        browser_origins:lines("computer-origins"),accounts:lines("computer-accounts"),applications:lines("computer-apps"),
        commands:JSON.parse(get("computer-commands").value)}});
      computerPolicyRevision=data.revision;get("computer-status").textContent="الصلاحيات اتحفظت. إلغاء علامة أداة أو مجلد وسيلة لسحب الصلاحية فورًا.";
    }catch(error){get("computer-status").textContent=error.message;}
  });
})();
