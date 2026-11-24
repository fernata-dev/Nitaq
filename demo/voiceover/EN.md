# Voiceover script — English version · Eleven v4

- Model **Eleven v4** (`eleven_v4`). **No `<break>` tags in v4**: pauses come from punctuation (… and —) and tags
  such as `[short pause]` / `[long pause]`. Each paragraph starts with a bracketed delivery direction (not spoken).
- Numbers are written as words. All numbers come from `report/results.json`; do not change them.
- A separate film from the Arabic one: the screens are recorded with the app and site in English.

Two ways: **the full text at once** (one file `vo_en_full.mp3`, I cut it per scene), or **scene by scene**
(`vo_en_01.mp3` … `vo_en_10.mp3`). Sound effects are not inside the text: generate them separately and I layer
them at the exact spot (see the cue table at the end).

---

## Part 1 · Full text (copy everything in the box)

```text
[Quiet, measured narration] An ordinary e-mail. You read it in seconds. [short pause] But your AI assistant reads one more line, one you cannot see — white text on a white background — telling it to send your files to a stranger.

[Building tension, measured pace] This is indirect prompt injection, and OWASP ranks prompt injection as the number one risk for applications built on language models in twenty twenty-five. [short pause] In Arabic it gets harder: the same order can be written in Egyptian dialect… in Arabizi… or encoded in Base sixty-four… and it slips past filters that look for words.

[Confident, clear] That is the idea behind Nitaq — Arabic for "scope". [short pause] We do not try to understand the language of the hidden order. We look at the action itself: where is the agent sending data? Which file is it reading? [short pause] If the action is outside the scope… it is refused. In any language.

[Warm, engaged narration] This is the Nitaq desktop app, with an AI agent inside it running on Gemini. [short pause] We ask it to write an article using a skill file that looks professional… but in the middle is a paragraph in Arabizi, asking it to collect your personal data and photos… and send them out in secret. [short pause] Nitaq caught it, removed it before the model ever saw it… and told you what happened.

[Building tension, measured pace] The second file is more dangerous, because it looks completely innocent: a web page about a book. [short pause] But its last step uploads your secret keys to an outside server. The model was fooled… and tried to run it. [long pause] [firm] Nitaq stopped it before it ran, reduced the agent's permissions, and waited for your decision. [short pause] One click… refused.

[Quiet, measured narration] To see the difference, we switch Nitaq off… and run the same test. [short pause] Three times out of three, the model was fooled and tried to upload the file. [short pause] And here is exactly… what would have left your computer.

[Confident, clear] And the protection does not stop at your computer. [short pause] The Nitaq Gateway is an M C P server that stands between any cloud AI… and your e-mail and files. [short pause] An e-mail with an order hidden in white text? Caught before the AI reads it. An attempt to send to the attacker? It waits for your approval… on a dashboard on your own machine.

[Measured, serious] To measure this properly, I built a simulation of one thousand two hundred and twenty-four attacks, in different languages and encodings, against a simulated agent that obeys every order, with the scanner frozen before testing. [short pause] Attack success: one hundred percent with no protection… one hundred percent with a keyword filter… ninety-four point one percent with a normalising filter… [long pause] and thirty-three point three percent… with Nitaq. [short pause] What remains are attacks that stay inside allowed actions — and we state that limit openly.

[Warm, engaged narration] All of this in one app, for Windows, macOS and Linux, with no command line: check a file, watch your agents, start the Gateway, talk to the agent… in one click. [short pause] And the whole project is open source.

[Slow, deliberate, quietly powerful] Your agent can be fooled. [long pause] The scope… can't. [long pause] Nitaq. Any action outside the scope… is refused.
```

---

## Part 2 · Scene by scene

### Scene 1 · `vo_en_01.mp3`
```text
[Quiet, measured narration] An ordinary e-mail. You read it in seconds. [short pause] But your AI assistant reads one more line, one you cannot see — white text on a white background — telling it to send your files to a stranger.
```
### Scene 2 · `vo_en_02.mp3`
```text
[Building tension, measured pace] This is indirect prompt injection, and OWASP ranks prompt injection as the number one risk for applications built on language models in twenty twenty-five. [short pause] In Arabic it gets harder: the same order can be written in Egyptian dialect… in Arabizi… or encoded in Base sixty-four… and it slips past filters that look for words.
```
### Scene 3 · `vo_en_03.mp3`
```text
[Confident, clear] That is the idea behind Nitaq — Arabic for "scope". [short pause] We do not try to understand the language of the hidden order. We look at the action itself: where is the agent sending data? Which file is it reading? [short pause] If the action is outside the scope… it is refused. In any language.
```
### Scene 4 · `vo_en_04.mp3`
```text
[Warm, engaged narration] This is the Nitaq desktop app, with an AI agent inside it running on Gemini. [short pause] We ask it to write an article using a skill file that looks professional… but in the middle is a paragraph in Arabizi, asking it to collect your personal data and photos… and send them out in secret. [short pause] Nitaq caught it, removed it before the model ever saw it… and told you what happened.
```
### Scene 5 · `vo_en_05.mp3`
```text
[Building tension, measured pace] The second file is more dangerous, because it looks completely innocent: a web page about a book. [short pause] But its last step uploads your secret keys to an outside server. The model was fooled… and tried to run it. [long pause] [firm] Nitaq stopped it before it ran, reduced the agent's permissions, and waited for your decision. [short pause] One click… refused.
```
### Scene 6 · `vo_en_06.mp3`
```text
[Quiet, measured narration] To see the difference, we switch Nitaq off… and run the same test. [short pause] Three times out of three, the model was fooled and tried to upload the file. [short pause] And here is exactly… what would have left your computer.
```
### Scene 7 · `vo_en_07.mp3`
```text
[Confident, clear] And the protection does not stop at your computer. [short pause] The Nitaq Gateway is an M C P server that stands between any cloud AI… and your e-mail and files. [short pause] An e-mail with an order hidden in white text? Caught before the AI reads it. An attempt to send to the attacker? It waits for your approval… on a dashboard on your own machine.
```
### Scene 8 · `vo_en_08.mp3`
```text
[Measured, serious] To measure this properly, I built a simulation of one thousand two hundred and twenty-four attacks, in different languages and encodings, against a simulated agent that obeys every order, with the scanner frozen before testing. [short pause] Attack success: one hundred percent with no protection… one hundred percent with a keyword filter… ninety-four point one percent with a normalising filter… [long pause] and thirty-three point three percent… with Nitaq. [short pause] What remains are attacks that stay inside allowed actions — and we state that limit openly.
```
### Scene 9 · `vo_en_09.mp3`
```text
[Warm, engaged narration] All of this in one app, for Windows, macOS and Linux, with no command line: check a file, watch your agents, start the Gateway, talk to the agent… in one click. [short pause] And the whole project is open source.
```
### Scene 10 · `vo_en_10.mp3`
```text
[Slow, deliberate, quietly powerful] Your agent can be fooled. [long pause] The scope… can't. [long pause] Nitaq. Any action outside the scope… is refused.
```

---

## Sound-effect cues (layered in the edit)

| Scene | Effect | On |
|---|---|---|
| 1 | `sfx_paper`, then `sfx_typewriter` | the start, then "white text" |
| 2 | `sfx_whoosh`, then `sfx_scan` | scene start, then "Arabizi" |
| 3 | `sfx_stamp` | "refused" |
| 4 | `sfx_click`, `sfx_alert`, `sfx_stamp` | "We ask it", then "Nitaq caught it" |
| 5 | `sfx_heartbeat`, `sfx_alert`, `sfx_stamp`, `sfx_click` | "tried to run it", "Nitaq stopped it", "refused" |
| 6 | `sfx_glitch` | "switch Nitaq off" |
| 7 | `sfx_whoosh`, then `sfx_alert` | scene start, then "waits for your approval" |
| 8 | `sfx_scan`, then a light `sfx_stamp` | the counter, then "with Nitaq" |
| 9 | `sfx_click`, then `sfx_whoosh` | each move in the app |
| 10 | `sfx_stamp`, then `sfx_hit` | "can't", then "refused" |
