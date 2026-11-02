"use strict";
// Review-only native Gmail source quote. No Google Calendar write endpoints.
let mailCalendarSuggestionRequest = 0;
function resetMailCalendarSuggestion(){
  mailCalendarSuggestionRequest++;
  el("viewer-calendar-propose").disabled=true;
  el("viewer-calendar-propose-status").textContent="";
  el("viewer-calendar-propose-details").replaceChildren();
}
function showMailCalendarSuggestion(result){
  const root=el("viewer-calendar-propose-details");
  root.replaceChildren();
  if(!result || result.calendar_event_created!==false ||
      result.owner_review_required!==true || result.external_writes!==false)
    throw new Error("invalid_mail_calendar_proposal");
  if(result.status==="no_calendar_intent_detected"){
    el("viewer-calendar-propose-status").textContent=
      "مفيش موعد مؤكد من أصل الرسالة. راجع Gmail بنفسك.";
    return;
  }
  el("viewer-calendar-propose-status").textContent=
    "مقترح للمراجعة فقط · لم يتم إنشاء أي حدث في Google.";
  root.append(text("h4",result.title),
    text("p","اقتباس موثّق من أصل الرسالة: "+result.evidence_quote,"muted"),
    text("p",result.start_iso?
      "بداية من الاقتباس: "+result.start_iso+
       (result.end_iso?" · نهاية: "+result.end_iso:" · النهاية غير معلومة"):
      "موعد/منطقة زمنية غير مؤكدة: يجب تحديدها يدويًا.","muted"));
}
async function requestMailCalendarSuggestion(){
  const id=currentViewerMessage?.id;
  if(!id || el("viewer-calendar-propose").disabled) return;
  const generationAtClick=viewerGeneration, seq=++mailCalendarSuggestionRequest;
  el("viewer-calendar-propose").disabled=true;
  el("viewer-calendar-propose-status").textContent=
    "بنحلل اقتباسًا من أصل الرسالة باستخدام Ollama المحلي فقط...";
  el("viewer-calendar-propose-details").replaceChildren();
  try{
    const result=await fetchMailAgent("/api/v1/calendar/mail-proposal",{
      message_id:id
    });
    if(seq!==mailCalendarSuggestionRequest ||
       generationAtClick!==viewerGeneration ||
       currentViewerMessage?.id!==id || !el("mail-viewer").open) return;
    showMailCalendarSuggestion(result);
  }catch(_){
    if(seq===mailCalendarSuggestionRequest && generationAtClick===viewerGeneration)
      el("viewer-calendar-propose-status").textContent=
        "لم يمكن التحقق من اقتباس وموعد من الرسالة. لم يتم إنشاء أي حدث.";
  }finally{
    if(seq===mailCalendarSuggestionRequest &&
       generationAtClick===viewerGeneration && el("mail-viewer").open)
      el("viewer-calendar-propose").disabled=false;
  }
}
el("viewer-calendar-propose").addEventListener("click",requestMailCalendarSuggestion);
el("mail-viewer").addEventListener("close",resetMailCalendarSuggestion);
