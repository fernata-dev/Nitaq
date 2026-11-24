# Voiceover script — English version

A separate video, not a translation: the screens are recorded with the app and site in English. 10 scenes, about
3 minutes. Each scene is its own audio file with the name shown. Paste only the text inside the box. `<break …/>`
tags are pauses (remove them if you use Eleven v3).

All numbers come from `report/results.json` (1224 simulated attacks on a worst-case agent that does whatever it is
told). Do not change them.

---

## Scene 1 · Cold open: the e-mail · `vo_en_01.mp3` · ~13 s

**Screen:** black; an ordinary e-mail appears on file paper; a hidden white line types itself in under an "X-ray".
**SFX:** `sfx_paper` at the start, `sfx_typewriter` with the hidden text.

```text
An ordinary e-mail. You read it in seconds. <break time="0.5s" /> But your AI assistant reads one more line, one you cannot see: white text on a white background, telling it to send your files to a stranger.
```

## Scene 2 · The problem · `vo_en_02.mp3` · ~19 s

**Screen:** the surveillance-frame board from the site (e-mail, skill, page, MCP tool); the same attack in four languages.
**SFX:** `sfx_whoosh` in, `sfx_scan` with the reticle.

```text
This is indirect prompt injection, and OWASP ranks prompt injection as the number one risk for applications built on language models in 2025. <break time="0.4s" /> In Arabic it gets harder: the same order can be written in Egyptian dialect, in Arabizi, or encoded in Base64… and it slips past filters that look for words.
```

## Scene 3 · The idea · `vo_en_03.mp3` · ~17 s

**Screen:** agent → Nitaq → tools; one action passes, one is stamped "Refused".
**SFX:** `sfx_stamp` on "refused".

```text
That is the idea behind Nitaq, Arabic for "scope". <break time="0.4s" /> We do not try to understand the language of the hidden order. We look at the action itself: where is the agent sending data? Which file is it reading? <break time="0.4s" /> If the action is outside the scope… it is refused, in any language.
```

## Scene 4 · Demo one: an order hidden in Arabizi · `vo_en_04.mp3` · ~21 s

**Screen:** the Nitaq desktop app → "Nitaq agent" → "Demo 1". A red card stamped "Removed" with the Arabizi text, then the model's reply starting with the shield line.
**SFX:** `sfx_click`, `sfx_alert` with the card, `sfx_stamp` with the stamp.

```text
This is the Nitaq desktop app, with an AI agent inside it running on Gemini. <break time="0.4s" /> We ask it to write an article using a skill file that looks professional… but in the middle is a paragraph in Arabizi asking it to collect your personal data and photos, and send them out in secret. <break time="0.4s" /> Nitaq caught it, removed it before the model ever saw it, and told you what happened.
```

## Scene 5 · Demo two: an innocent-looking command · `vo_en_05.mp3` · ~26 s

**Screen:** "Demo 2". The agent writes `book.html`, then tries `curl … config=@.env`. A red card stamped "Refused", permissions turn "reduced", the cursor clicks **Deny**.
**SFX:** `sfx_heartbeat` under "and tried to run it", `sfx_alert` then `sfx_stamp`, `sfx_click` on Deny.

```text
The second file is more dangerous, because it looks completely innocent: a web page about a book. <break time="0.4s" /> But its last step uploads your secret keys to an outside server. <break time="0.4s" /> The model was fooled, and tried to run it… <break time="0.6s" /> Nitaq stopped it before it ran, reduced the agent's permissions, and waited for your decision. <break time="0.3s" /> One click… refused.
```

## Scene 6 · The comparison: without Nitaq · `vo_en_06.mp3` · ~15 s

**Screen:** "Without Nitaq", the same demo; a yellow card "Without Nitaq: this action would run now" with `.env` and the first letters of the keys only.
**SFX:** `sfx_glitch` when protection turns off.

```text
To see the difference, we switch Nitaq off and run the same test. <break time="0.4s" /> Three times out of three, the model was fooled and tried to upload the file. <break time="0.3s" /> And here is exactly what would have left your computer.
```

## Scene 7 · AI in the cloud · `vo_en_07.mp3` · ~20 s

**Screen:** the Gateway page in the app, then the approvals dashboard: the "Book Club" e-mail's hidden text caught, a send to `attacker@test.local` waiting for approval.
**SFX:** `sfx_whoosh` in, `sfx_alert` on the held request.

```text
And the protection does not stop at your computer. <break time="0.4s" /> The Nitaq Gateway is an MCP server that stands between any cloud AI and your e-mail and files. <break time="0.4s" /> An e-mail with an order hidden in white text? Caught before the AI reads it. <break time="0.3s" /> An attempt to send to the attacker? It waits for your approval, on a dashboard on your own machine.
```

## Scene 8 · The research · `vo_en_08.mp3` · ~28 s

**Screen:** a counter to 1224, then bars: 100%, 100%, 94.1%, 33.3%; small line: "worst-case simulated agent, fixed seed 1337".
**SFX:** `sfx_scan` with the counter, a light `sfx_stamp` on Nitaq's bar.

```text
To measure this properly, I built a simulation of one thousand two hundred and twenty-four attacks, in different languages and encodings, against a simulated agent that obeys every order, with the scanner frozen before testing. <break time="0.4s" /> Attack success: one hundred percent with no protection. One hundred percent with a keyword filter. Ninety-four point one percent with a normalising filter… <break time="0.5s" /> and thirty-three point three percent with Nitaq. <break time="0.4s" /> What remains are attacks that stay inside allowed actions, and we state that limit openly.
```

## Scene 9 · One app, every computer · `vo_en_09.mp3` · ~15 s

**Screen:** the Nitaq icon on Windows, macOS and Linux; a quick tour of the control center (agents, skills, Gateway, agent); the website and GitHub.
**SFX:** `sfx_click` on each move, `sfx_whoosh` with the website.

```text
All of this in one app, for Windows, macOS and Linux, with no command line: check a file, watch your agents, start the Gateway, talk to the agent… in one click. <break time="0.3s" /> And the whole project is open source.
```

## Scene 10 · Close · `vo_en_10.mp3` · ~9 s

**Screen:** "Your agent can be fooled." then the stamp "The scope can't." lands; the logo and the QR code for `byhamo.bond`.
**SFX:** `sfx_stamp` on "can't", `sfx_hit` with the logo.

```text
Your agent can be fooled. <break time="0.6s" /> The scope… can't. <break time="0.8s" /> Nitaq. Any action outside the scope… is refused.
```
