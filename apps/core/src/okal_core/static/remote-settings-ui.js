"use strict";
// Only the local https://okal page can request the remote systemd transition.
// Control keys are never stored in localStorage, cookies, or URL parameters.
async function loadRemoteSettings() {
  const status=document.getElementById("remote-status");
  const start=document.getElementById("remote-enable");
  const stop=document.getElementById("remote-disable");
  const link=document.getElementById("remote-url");
  const noUrl=document.getElementById("remote-no-url");
  start.disabled=true;
  stop.disabled=true;
  try {
    const response=await fetch("/api/v1/remote/status", {
      credentials:"same-origin",cache:"no-store",
      headers:token?{Authorization:"Bearer "+token}:{}
    });
    if(!response.ok) throw Error("status_unavailable");
    const data=await response.json();
    status.textContent=data.tunnel_running
      ? "التونل يعمل محليًا · لا يُعتبر الوصول العام مؤكدًا"
      : data.configured
      ? "الوصول الخارجي متوقف · الإعداد محفوظ"
      : "غير مهيأ · أنشئ Cloudflare Named Tunnel وAccess أولًا";
    link.hidden=true;
    noUrl.hidden=false;
    if(typeof data.external_url_if_configured==="string") {
      const address=new URL(data.external_url_if_configured);
      if(address.protocol==="https:" && address.username==="" &&
         address.password==="" && address.pathname==="/" &&
         !address.search && !address.hash) {
        link.textContent=address.href;
        link.href=address.href;
        link.hidden=false;
        noUrl.hidden=true;
      }
    }
    const local=location.origin==="https://okal";
    const ready=local && data.owner_control_key_issued;
    start.disabled=!ready || !data.configured || data.tunnel_running;
    stop.disabled=!ready || !data.tunnel_running;
  } catch (_) {
    status.textContent="تعذّر فحص حالة Cloudflare؛ لا نفترض الاتصال.";
  }
}
async function setRemoteMode(action) {
  const feedback=document.getElementById("remote-feedback");
  const input=document.getElementById("remote-control-key");
  const confirm=document.getElementById("remote-confirm-policy");
  if(location.origin!=="https://okal") {
    feedback.textContent="التحكم متاح من https://okal فقط.";
    return;
  }
  if(!input.value) {
    feedback.textContent="أدخل مفتاح المالك الذي أُنشئ محليًا في Terminal.";
    return;
  }
  if(action==="on" && !confirm.checked) {
    feedback.textContent="أكد إعداد Cloudflare Access لحسابك فقط.";
    return;
  }
  const key=input.value;
  input.value="";
  const start=document.getElementById("remote-enable");
  const stop=document.getElementById("remote-disable");
  start.disabled=true;
  stop.disabled=true;
  feedback.textContent="جارٍ إرسال طلب "+(action==="on"?"التشغيل":"الإيقاف")+"...";
  try {
    const response=await fetch("/api/v1/remote/switch", {
      method:"POST",credentials:"same-origin",cache:"no-store",
      headers:{"Content-Type":"application/json",
        ...(token?{Authorization:"Bearer "+token}:{})},
      body:JSON.stringify({action,control_key:key,
        confirm_access_policy:action==="on" && confirm.checked})
    });
    if(!response.ok) {
      const payload=await response.json().catch(()=>({}));
      const codes={
        remote_owner_control_key_required:"مفتاح التحكم غير صالح أو منتهي. أنشئ مفتاحًا جديدًا.",
        remote_not_configured:"أكمل إعداد Cloudflare Tunnel وAccess أولًا.",
        cloudflare_access_policy_confirmation_required:"يجب تأكيد سياسة Cloudflare Access.",
        remote_action_launch_failed:"تعذّر تشغيل خدمة systemd؛ تحقق من الـ Terminal.",
        remote_owner_local_https_only:"التحكم متاح من https://okal فقط."
      };
      throw Error(codes[payload.detail]||"رفض الخادم تنفيذ الطلب.");
    }
    feedback.textContent="قُبل الطلب محليًا؛ النتيجة لم تتأكد بعد. تحقق من الحالة.";
    await new Promise(resolve=>setTimeout(resolve,1800));
    await loadRemoteSettings();
  } catch (error) {
    feedback.textContent=String(error.message||"النتيجة غير مؤكدة")+" تأكد من حالة النظام قبل إعادة الطلب.";
    await loadRemoteSettings();
  }
}
document.getElementById("remote-enable").addEventListener("click",()=>setRemoteMode("on"));
document.getElementById("remote-disable").addEventListener("click",()=>setRemoteMode("off"));
document.getElementById("remote-refresh").addEventListener("click",loadRemoteSettings);
window.addEventListener("DOMContentLoaded",loadRemoteSettings);
