"use strict";
// Model output fills editable inputs only. It never previews/saves a plan.
async function suggestDayPlanAi() {
  const button=el("day-plan-ai-suggest");
  button.disabled=true;
  const generationAtCall=generation;
  const taskIds=dayPlanRows.filter(row=>row.selected.checked).map(row=>row.id);
  const feedback=el("day-plan-ai-feedback");
  try {
    if (!calendarSnapshot) throw Error("افتح تقويم اليوم أولًا.");
    if (!taskIds.length) throw Error("اختار المهام اللي عايز تقديرها أولًا.");
    invalidateDayPlanApproval();
    feedback.textContent="Ollama بيقدّر المدد والأولويات محليًا. لم يتم تغيير أي مهمة.";
    const data=await taskPost("/api/v1/calendar/day-plan/ai-suggest",{
      task_ids:taskIds
    });
    if (generationAtCall!==generation || !calendarSnapshot) return;
    const current=dayPlanRows.filter(row=>row.selected.checked).map(row=>row.id);
    if (current.join(",")!==taskIds.join(",")) {
      feedback.textContent="اتغير اختيار المهام؛ كرر الاقتراح.";
      return;
    }
    if (!Array.isArray(data.suggestions) ||
        data.review_required!==true || data.estimates_confirmed!==false)
      throw Error("invalid_recommendations");
    const allowed=new Set([15,30,45,60,90,120,180,240]);
    const priorities=new Set(["high","normal","low"]);
    if (data.suggestions.length!==taskIds.length ||
        new Set(data.suggestions.map(x=>x.task_id)).size!==taskIds.length)
      throw Error("invalid_recommendations");
    for (const row of data.suggestions) {
      if (!taskIds.includes(row.task_id) ||
          !allowed.has(row.minutes) || !priorities.has(row.priority))
        throw Error("invalid_recommendations");
    }
    for (const suggestion of data.suggestions) {
      const row=dayPlanRows.find(item=>item.id===suggestion.task_id);
      row.minutes.value=String(suggestion.minutes);
      row.priority.value=suggestion.priority;
    }
    feedback.textContent="دي تقديرات Ollama، مش قرار نهائي. راجع وعدّل المدة والأولوية، ثم اضغط «اقترح خطة اليوم» بنفسك.";
  } catch (_) {
    if (generationAtCall===generation)
      feedback.textContent="تعذر الحصول على تقديرات موثوقة من Ollama. حدّد المدة والأولوية يدويًا.";
  } finally {button.disabled=false;}
}
el("day-plan-ai-suggest").addEventListener("click",suggestDayPlanAi);
