# رفع موقع نِطاق على Cloudflare Pages بدومينك

الموقع ملفات ثابتة (HTML وCSS وJS وفيديو). مش محتاج سيرفر ولا قاعدة بيانات. اللي بيترفع:
- الموقع بالعربي على `/`، وبالإنجليزي على `/en/`.
- تطبيق الفحص على `/app/`.
- فيديو العرض على `/assets/film/nitaq-demo.mp4`، وحجمه حوالي 12 ميجا. Cloudflare بيقبل لحد 25 ميجا للملف الواحد.
- ملف `_headers` فيه إعدادات أمان وكاش.

الأوامر شغالة على Linux وmacOS وWindows. محتاج **Python 3.11+** و**Node.js** (عشان `npx wrangler`).

---

## 1) سجّل دخول Cloudflare (مرة واحدة)
```bash
npx wrangler login
```
هيفتح المتصفح على حسابك في Cloudflare، ودوس «Allow». اتأكد إنك داخل:
```bash
npx wrangler whoami
```

## 2) ابني وارفع (كل مرة تعدّل الموقع)
من فولدر المشروع:
```bash
python3 tools/site/deploy.py
```
على ويندوز: `py tools/site/deploy.py`

الأمر ده بيعمل كذا حاجة ورا بعض:
1. بيبني الموقع في `dist/site`، ومعاه التطبيق والفيديو.
2. بيعمل مشروع Pages اسمه `nitaq`، لو مش موجود.
3. بيرفع الموقع ويطبعلك رابط. الرابط الأساسي للمشروع ده هو **https://nitaq-f0z.pages.dev**، لأن `nitaq.pages.dev` كان محجوز، فـ Cloudflare زوّد حروف في الآخر.

> عايز تبني بس من غير رفع؟ `python3 tools/site/deploy.py --build-only`. وبعدها ممكن ترفع فولدر `dist/site` بإيدك من لوحة Cloudflare: Workers & Pages ← Create ← Pages ← Upload assets.

## 3) اتأكد إن الموقع شغال
افتح **https://nitaq-f0z.pages.dev** وجرّب الحاجات دي:
- اللوحة اللي فوق: دوس على أي صورة أو غيّر اللغة، والختم الأحمر يفضل نازل على نفس الفعل.
- قسم «الفيلم»: الفيديو بيشتغل، والفصول بتنقلك للدقيقة الصح.
- زرار «English» فوق.

## 4) الدومين بتاعك (مرة واحدة)

> **الحالة دلوقتي:** الموقع شغال على **https://byhamo.bond** (اتربط في 24 نوفمبر 2026).
>
> **ليه طلع Error 522 في الأول؟** اتعمل سجل CNAME بيشاور على `nitaq-f0z.pages.dev` من صفحة الـ DNS، بس الدومين ماكانش متضاف لمشروع Pages نفسه. فـ Cloudflare مكانش عارف يعرض أنهي موقع. الحل دايمًا إنك تضيف الدومين من **Custom domains** جوه المشروع، أو من API الـ Pages كده:
> `POST /accounts/<account>/pages/projects/nitaq/domains  {"name": "byhamo.bond"}`
الدومين بتاعك أصلًا على Cloudflare، فالـ DNS بيتظبط لوحده:
1. افتح **dash.cloudflare.com** ← **Workers & Pages** ← مشروع **nitaq**.
2. افتح تبويب **Custom domains** ← **Set up a custom domain**.
3. اكتب الدومين الرئيسي، مثلًا `example.com`، ودوس **Continue** وبعدها **Activate domain**.
4. Cloudflare هيضيف سجل DNS لوحده، من نوع CNAME للدومين الرئيسي، بيشاور على `nitaq-f0z.pages.dev`. لو الدومين عليه سجل قديم (A أو CNAME لمشروع تاني)، هيطلب منك تمسحه الأول.
5. استنى لحد ما الحالة تبقى **Active**. ده بياخد من دقيقة لربع ساعة، وشهادة HTTPS بتطلع لوحدها.

**عايز `www` كمان؟** كرر نفس الخطوات بـ `www.example.com`. أو اعمل تحويل من `www` للدومين الرئيسي: من صفحة الدومين ← **Rules** ← **Redirect Rules** ← قالب «Redirect from WWW to root».

## 5) ربط MCP من الموقع (قسم «اربط الـ AI»)
الموقع بيكلّم نِطاق Gateway اللي شغال على جهازك من المتصفح مباشرة. عشان الـ Gateway يقبل الموقع، شغّله باسم الدومين بتاعك:
```bash
nitaq gateway --allow-origin https://example.com
```
بعد كده افتح قسم «اربط الـ AI بتاعك» في الموقع، والصق رابط الـ MCP اللي الـ Gateway طبعه، ودوس «اختبر الاتصال».

- `--allow-origin` بيفتح مسار الـ MCP للموقع ده بس. لوحة الموافقات بتفضل شغالة على جهازك بس.
- **كروم هيسألك** «byhamo.bond عايز يوصل لأجهزة وتطبيقات على جهازك/شبكتك المحلية». دوس **Allow**، لأن الـ Gateway شغال على `127.0.0.1`. لو رفضت بالغلط: دوس على أيقونة القفل جنب العنوان ← Site settings ← Local network access ← Allow، وبعدها اعمل ريفريش.
- لو شايف في الـ Console خطأ عن `static.cloudflareinsights.com`: ده سكريبت إحصائيات Cloudflare بيحطه لوحده، وسياسة الأمان بتاعة الموقع بتمنعه. يعني مفيش تتبع. ولو عايز تشيل الرسالة، اقفل Web Analytics للموقع من لوحة Cloudflare.
- الرابط فيه سر. الموقع مش بيحفظه، ومش بيبعته لأي حد غير الـ Gateway بتاعك.

## 6) كود QR للمعرض
الـ QR جاهز: [`demo/Nitaq_Site_QR.png`](../demo/Nitaq_Site_QR.png) بيفتح https://byhamo.bond/. لو الدومين اتغير، اعمله تاني بـ `qrencode`:
```bash
qrencode -l M -s 16 -m 3 -o demo/Nitaq_Site_QR.png "https://byhamo.bond/"
```
لو مش متثبت عندك: على Arch `sudo pacman -S qrencode`، وعلى Ubuntu `sudo apt install qrencode`، وعلى macOS `brew install qrencode`.

---

### لو حاجة وقفت
- **`wrangler could not list projects`**: شغّل `npx wrangler login` تاني.
- **الفيديو بيستنى ثانية قبل ما ينط للفصل**: Cloudflare Pages (وكمان `python -m http.server`) مش بيبعت الفيديو على أجزاء (Range)، فالصفحة بتستنى لحد ما الجزء ده يتحمّل وبعدين تنقلك. الفيديو 12 ميجا بس، فده بياخد ثواني.
- **«origin not allowed» في قسم الربط**: الـ Gateway شغال من غير `--allow-origin`، أو الدومين اللي كاتبه مختلف (اتأكد من `https` ومن `www`).
