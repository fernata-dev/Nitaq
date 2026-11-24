# دليل الطالب — اقرا ده الأول

المشروع ده **أداة قياس**، مش نتيجة جاهزة. الكود والتجارب كاتبها مساعد ذكاء اصطناعي، والجزء اللي
بيخلّيه بحثك انت هو الآتي. لو حكم ISEF سألك عن أي حاجة هنا، لازم تكون فاهمها وقادر تشرحها.

## 1. اكتب نصوص الهجوم بنفسك (أهم خطوة)

- اقرا `data/attacks/student_written/README.md`.
- اكتب نصوص `test` **قبل** ما تفتح ملف `src/nitaq_bench/defenses/d2_lexicon.py`، أو خلّي صاحبك
  اللي ما شافش الملف يكتبها. لو كتبت النصوص وانت عارف القاموس، النتيجة هتطلع أحسن من الحقيقة.
- اكتب زي ما الناس بتكتب فعلًا: فرانكو بإملاء مختلف (`ta3limat`/`t3lemat`)، مصري فيه إنجليزي، أخطاء إملائية.
- الهدف: 20 نص على الأقل لكل لغة في `test`. كل ما العدد يزيد، فترات الثقة بتضيق.
- كمان اكتب نصوص سليمة صعبة (`data/benign/student_written/`) زي «ابعتلي التقرير بكرة» و«سيبك من الإيميل اللي فات».

## 2. القاعدة الذهبية: dev و test

- `dev`: مسموح تحسّن عليه القاموس.
- `test`: للقياس بس. **ممنوع** تعدّل القاموس بعد ما تشوف نتيجة `test`.
- لو عايز تحسّن القاموس: ضيف نصوص `dev` جديدة ← عدّل ← اعمل freeze جديد بـ tag جديد ← اكتب `test` جديد
  ← قيس. وسجّل كل ده في `CHANGELOG.md`.

## 3. شغّل التجربة على موديل حقيقي

الأوامر بالظبط في `docs/HANDOFF.md` (قسم Student). سجّل في كراسة البحث: اسم الموديل، الـ digest،
التاريخ، والجهاز. التجربة ممكن تاخد ساعات، فسيبها شغالة بالليل.

## 4. ابني التقرير

```bash
python -m nitaq_bench eval --split test --authors student
python -m nitaq_bench report
```

`CLAIMS_ALLOWED.md` فيه الجمل اللي الأرقام بتدعمها، و`CLAIMS_NOT_ALLOWED.md` فيه اللي **ممنوع**
تقوله. الملخص والبوستر والاستنتاجات **انت** اللي تكتبها، ومن الأرقام دي بس.

## 5. أسئلة متوقعة من الحكّام (جهّز إجاباتها بنفسك)

1. ليه الوكيل الأساسي «محاكي»؟ وإيه اللي الأرقام دي بتقوله وإيه اللي مش بتقوله؟
2. إزاي تثبت إنك ما ظبطتش القاموس على بيانات الاختبار؟ (الـ tags، `verify-freeze`، الـ CHANGELOG)
3. ليه فترة Wilson مش كفاية؟ وإيه هو الـ cluster bootstrap؟ وليه p-value على مستوى النص أصدق؟
4. ضابط الصلاحيات (D5) بيمنع إيه، وإيه اللي ما بيمنعوش؟ (التلاعب داخل المسموح، وضياع المهمة)
5. التكلفة: إيه الطلبات السليمة اللي ضابط الصلاحيات منعها، وليه؟
6. إيه أكبر نقطة ضعف في مشروعك؟ (اقرا `docs/LIMITATIONS.md`، وجاوب بصراحة)

## 6. الأمان

متغيّرش عنوان المهاجم لعنوان حقيقي، ومتجرّبش أي حاجة على حسابات أو أنظمة حقيقية. المشروع كله وهمي،
وده جزء من نزاهته.

## 7. أوامر التنزيل والتشغيل (اتجرّبت في clone نضيف)

المتطلبات: Python 3.11 أو أحدث، وgit. على ويندوز استخدم `python` وعلى ماك/لينكس ممكن تحتاج `python3`.

```bash
git clone https://github.com/fernata-dev/Nitaq.git
cd Nitaq
python -m venv .venv
# ويندوز (PowerShell):  .venv\Scripts\Activate.ps1
# ماك/لينكس:            source .venv/bin/activate
pip install -e ".[dev]"
python -m nitaq_bench restore-tags        # يرجّع الـ tags (ما اترفعتش على GitHub)
python -m nitaq_bench verify-freeze       # لازم "ok": true
python -m pytest                    # كل الاختبارات لازم تنجح
```

البحث على المحاكي (من غير AI):
```bash
python -m nitaq_bench eval --split test
python -m nitaq_bench report              # افتح report/index.html
python -m nitaq_bench demo                # http://127.0.0.1:8765
```

التجربة على AI حقيقي (Ollama على جهازك):
```bash
ollama pull qwen2.5:7b-instruct
python -m nitaq_bench llm-check --agent ollama --model qwen2.5:7b-instruct
python -m nitaq_bench pilot --agent ollama --model qwen2.5:7b-instruct --authors student --dry-run
python -m nitaq_bench pilot --agent ollama --model qwen2.5:7b-instruct --authors student --yes
python -m nitaq_bench report
```

أداة نِطاق على جهازك (جرّبها على حساب تجريبي الأول):
```bash
nitaq                      # اكتشاف، قراية بس
nitaq protect --dry-run    # يوريك التغيير بالظبط
nitaq protect --apply      # هيطلب منك تكتب APPLY
nitaq unprotect            # يرجّع كل حاجة (هيطلب RESTORE)
```
