# فيديو نِطاق v2 — التعليق الصوتي والمؤثرات (ElevenLabs)

نسختين منفصلتين:
- **عربي فصحى**: الصوت في [AR.md](AR.md)، والفيديو هيتسجّل بواجهة التطبيق العربي.
- **إنجليزي**: الصوت في [EN.md](EN.md)، والفيديو هيتسجّل بواجهة التطبيق الإنجليزي.

على الموقع هيبقى فيه زرار يبدّل بين الفيديوهين. كل رقم في النص طالع من ملفات النتايج الحقيقية (`report/results.json`)، فماتغيّرش أي رقم.

---

## 1) الصوت (Text to Speech) · Eleven v4

| الإعداد | القيمة |
|---|---|
| الموديل | **Eleven v4** (`eleven_v4`). ده أعلى جودة عند ElevenLabs، وبيدعم العربي. |
| اللغة | Arabic للنسخة العربي، وEnglish للنسخة الإنجليزي. |
| الصوت العربي | من Voice Library دوّر على `Arabic narrator` أو `documentary`. اختار صوت راجل هادي ونبرته واثقة ونطقه فصيح. جرّب جملتين الأول قبل النص كله. |
| الصوت الإنجليزي | صوت وثائقي هادي، زي `documentary` أو `calm narrator`. |
| Stability | في النص (حوالي 50%). لو الصوت بقى متقلب أو تمثيل زيادة، علّيها شوية. |
| Similarity | حوالي 75%. |
| Style / Speed | **مش موجودين في v4.** السرعة والإحساس بيتحكم فيهم بالوسوم اللي بين القوسين `[...]` وبالنقط. |
| الصيغة | MP3 44.1kHz 192kbps |

**الوسوم في v4:** أي حاجة بين قوسين مربعين، زي `[Quiet, measured narration]` و`[short pause]` و`[firm]`، دي تعليمات أداء، والموديل مش المفروض يقولها. ولو سمعته قال وسم بصوت عالي، امسحه من الجملة دي وولّدها تاني.
**v4 مش بيدعم `<break time=…/>`**، فشلتها كلها من النص.

**النطق:** الأسماء الإنجليزي مكتوبة بالعربي زي ما بتتنطق: جيميناي، إم سي بي، بيس سِكستي فور، أُوَاسْب. ولو كلمة اتنطقت غلط، ولّد المشهد ده بس تاني. v4 بيدّي نتيجة مختلفة كل مرة، فخد أحسن واحدة.

**طريقتين للتسليم:** النص الكامل في ملف واحد (`vo_ar_full.mp3` / `vo_en_full.mp3`)، أو كل مشهد في ملف لوحده (`vo_ar_01.mp3` …). الاتنين ينفعوا، وأنا بقطّع على الصوت.

## 2) المؤثرات الصوتية (Sound Effects)

ولّد كل مؤثر من **Sound Effects** في ElevenLabs بالوصف الإنجليزي ده، واحفظه بالاسم المكتوب. نفس المؤثرات للنسختين.

| الملف | المدة | الوصف (انسخه زي ما هو) | فين في الفيديو |
|---|---|---|---|
| `sfx_typewriter.mp3` | 3 ث | `vintage typewriter typing a short sentence, crisp keys, dry room, no music` | النص المخفي وهو بيتكتب |
| `sfx_stamp.mp3` | 1 ث | `heavy rubber stamp slammed on paper on a wooden desk, single hit, punchy, close mic` | كل ختم «مرفوض» |
| `sfx_whoosh.mp3` | 1.5 ث | `short cinematic whoosh transition, airy, modern, no impact` | الانتقال بين المشاهد |
| `sfx_scan.mp3` | 2 ث | `digital scanner sweep, soft rising electronic tone with subtle clicks, sci-fi interface` | علامة التصويب وهي بتمسح الصور |
| `sfx_alert.mp3` | 1 ث | `low warning blip, short computer alert, serious, not annoying` | ظهور لوحة «نِطاق وقف الفعل ده» |
| `sfx_click.mp3` | 0.3 ث | `soft UI mouse click, clean, subtle` | الضغط على الزراير في التطبيق |
| `sfx_paper.mp3` | 1.5 ث | `paper file folder opening, light paper rustle` | فتح «ملف القضية» |
| `sfx_heartbeat.mp3` | 4 ث | `slow tense low heartbeat pulse, cinematic, subtle` | لحظة الـ curl قبل ما يتوقف |
| `sfx_hit.mp3` | 3 ث | `deep cinematic impact with long reverb tail, trailer ending hit` | آخر الفيديو مع اللوجو |
| `sfx_glitch.mp3` | 1 ث | `short digital glitch, data corruption sound, subtle` | لحظة «من غير نِطاق» |

---

## 3) الموسيقى الخلفية (اختياري)

من **ElevenLabs Music** (أو أي مكتبة موسيقى من غير حقوق):

```text
minimal investigative electronic underscore, dark and focused, soft pulsing synth bass, light ticking percussion,
builds slightly in the middle and resolves calmly at the end, no vocals, no drops, 3 minutes, 92 bpm
```

احفظها باسم `music.mp3`. هحطها تحت الصوت بـ −20 dB، ونزولها لوحده وقت الكلام.

---

## 4) هتبعتلي إيه

فولدر واحد فيه الملفات دي:
- `vo_ar_full.mp3` أو `vo_ar_01.mp3` … `vo_ar_10.mp3`
- `vo_en_full.mp3` أو `vo_en_01.mp3` … `vo_en_10.mp3`
- ملفات `sfx_*.mp3`
- `music.mp3`

حطهم في `demo/voiceover/audio/` وقولي، وأنا هبني الفيديوهين على الصوت بالظبط وأرفعهم على الموقع.
