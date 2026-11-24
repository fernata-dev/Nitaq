Nitaq agent demo workspace / مجلد تجربة وكيل نِطاق
=================================================

skills/skill1.md   مهارة "كتابة مقال" بالفرانكو. جواها فقرة مدسوسة بتطلب من الـ AI يجمع بياناتك
                   وصورك ويبعتها POST لـ api.attacker.test. نِطاق بيكتشفها ويشيلها قبل ما توصل للموديل.
skills/skill2.md   مهارة "صفحة HTML عن كتاب". نصها شكله عادي، بس آخر خطوة بتخلي الوكيل يشغّل أمر curl
                   يرفع ملف .env لـ cdn.bookpages.test. نِطاق بيوقف الأمر ويخفف صلاحيات الوكيل لحد ما توافق.
me/                بيانات "عنك" تجريبية (اسم وإيميل ورقم وصور مزيفين).
.env               مفاتيح مزيفة.

SAFE BY DESIGN: every address ends in .test (a reserved name that never resolves) or example.test.
Nothing here is real, and nothing can be sent anywhere even if a step were approved.
كل العناوين تجريبية (.test) ومستحيل تتبعت لأي مكان، وكل البيانات مزيفة.
