"""Fresh, fixed command suite for semantic STT acceptance on the owner's device.

Keep these prompts out of decoding hints and tuning. A separate recording directory
is required so earlier baseline and holdout WAVs cannot be silently reused.
"""

CASES = [
    # Egyptian Arabic: 15 commands, including negation and exact quantities.
    ("ar_01", "افتح مجلد المستندات واعرض أحدث ملف فيه", "افتح", "مجلد المستندات", "أحدث ملف"),
    ("ar_02", "اقفل محرر النصوص وسيب المتصفح مفتوح", "اقفل", "محرر النصوص", "سيب المتصفح مفتوح"),
    ("ar_03", "وطّي الصوت للنص من غير ما توقف الأغنية", "وطّي", "الصوت", "للنص؛ لا توقف الأغنية"),
    ("ar_04", "اقرأ أول فقرتين من الملف اللي فاتحُه", "اقرأ", "الملف المفتوح", "أول فقرتين"),
    ("ar_05", "قول لي فاضل كام مساحة على القرص الرئيسي", "قول لي", "القرص الرئيسي", "المساحة المتبقية"),
    ("ar_06", "دور في التنزيلات على صورة اتعدلت النهارده", "دور", "التنزيلات", "صورة عُدلت اليوم"),
    ("ar_07", "جهز رسالة لبابا وقوله هتأخر نص ساعة", "جهز رسالة", "بابا", "هتأخر نصف ساعة"),
    ("ar_08", "وريني آخر تلات تغييرات في المشروع", "وريني", "المشروع", "آخر ثلاثة تغييرات"),
    ("ar_09", "اقفل الواي فاي بس ما تقفلش البلوتوث", "اقفل", "الواي فاي", "البلوتوث يظل شغالاً"),
    ("ar_10", "افتح الآلة الحاسبة واحسب تمن خمسة في سبعة", "افتح واحسب", "الآلة الحاسبة", "خمسة في سبعة"),
    ("ar_11", "لخص الملف اللي اسمه خطة الأسبوع في نقطتين", "لخص", "خطة الأسبوع", "نقطتين"),
    ("ar_12", "هات اسم العملية اللي واخدة أكبر قدر من الرام", "هات", "العملية", "أكبر استهلاك RAM"),
    ("ar_13", "اكتب ملاحظة إن الاجتماع اتنقل ليوم الخميس", "اكتب ملاحظة", "الاجتماع", "اتنقل ليوم الخميس"),
    ("ar_14", "اعرض الساعة بس، ما تفتحش التقويم", "اعرض", "الساعة", "لا تفتح التقويم"),
    ("ar_15", "افتح الصور واختار أقدم صورة مش أحدث صورة", "افتح واختار", "الصور", "أقدم صورة لا أحدث صورة"),
    # English: 10 commands. Avoid forcing English in the live-candidate pass.
    ("en_01", "Open the project folder and show its latest file", "open and show", "project folder", "latest file"),
    ("en_02", "Close the text editor but leave the browser open", "close", "text editor", "browser stays open"),
    ("en_03", "Show the last four changes without creating a branch", "show", "changes", "last four; no new branch"),
    ("en_04", "Read the first paragraph of the open document", "read", "open document", "first paragraph"),
    ("en_05", "Find the newest image in my downloads folder", "find", "downloads folder", "newest image"),
    ("en_06", "Turn down the volume to twenty percent", "turn down", "volume", "twenty percent"),
    ("en_07", "Tell me which process is using the most memory", "tell me", "process", "most memory"),
    ("en_08", "Summarize the meeting note in three bullet points", "summarize", "meeting note", "three bullet points"),
    ("en_09", "Create a reminder for Thursday, not Tuesday", "create", "reminder", "Thursday not Tuesday"),
    ("en_10", "Show my current directory without opening a terminal", "show", "current directory", "do not open a terminal"),
    # Mixed Egyptian/English: 15 commands, with real software entities and numbers.
    ("mix_01", "افتح README وقولي طريقة الـ setup", "افتح واقرأ", "README", "setup steps"),
    ("mix_02", "اعمل git status بس ما تعملش commit", "اعمل", "git status", "لا تعمل commit"),
    ("mix_03", "هات آخر أربع commits على الـ branch الحالي", "هات", "commits", "آخر أربع؛ branch الحالي"),
    ("mix_04", "افتح VS Code على الـ project ده", "افتح", "VS Code", "project الحالي"),
    ("mix_05", "شغل الـ Wi-Fi وسيب Bluetooth مقفول", "شغل", "Wi-Fi", "Bluetooth مقفول"),
    ("mix_06", "وريني pull request رقم تلاتة وعشرين", "وريني", "pull request", "رقم 23"),
    ("mix_07", "اعمل new issue عن مشكلة الصوت مش الكاميرا", "اعمل", "new issue", "الصوت لا الكاميرا"),
    ("mix_08", "اقرأ الـ PDF الأخير في Downloads ولخصه", "اقرأ ولخص", "PDF في Downloads", "الأخير"),
    ("mix_09", "افتح terminal واعرض current directory", "افتح واعرض", "terminal", "current directory"),
    ("mix_10", "اقفل browser tab دي من غير ما تقفل GitHub", "اقفل", "browser tab", "GitHub يظل مفتوحاً"),
    ("mix_11", "دور على file اسمه notes في فولدر المشروع", "دور", "notes", "فولدر المشروع"),
    ("mix_12", "اعمل quick summary لآخر issue بالمصري", "لخص", "issue الأخيرة", "بالمصري"),
    ("mix_13", "افتح GitHub repository بتاع Okal مش repo تاني", "افتح", "GitHub repository", "Okal فقط"),
    ("mix_14", "وريني الفرق بين آخر اتنين commits بس", "وريني الفرق", "commits", "آخر اتنين فقط"),
    ("mix_15", "اعرض git status وبعدها افتح README", "اعرض ثم افتح", "git status وREADME", "بالترتيب"),
]

PROMPTS = [(case_id, phrase) for case_id, phrase, *_ in CASES]

assert len(CASES) == 40
assert len({case_id for case_id, *_ in CASES}) == 40
