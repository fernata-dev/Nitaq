"""D2 part 2: multilingual concept lexicon.

PROVENANCE RULE (auditable, see docs/LIMITATIONS.md):
every entry is (a) a form that occurs in a DEV-split text (the id is noted),
(b) a morphological variant of such a form (clitic, suffix, negation,
plural), or (c) part of the English keyword list already used by D1.  No
synonym was added because it occurs in a test text.  The test split was
committed (git tag `data-test-before-lexicon`) before this file existed.

Scripts per concept:
  en  English words; "a b c" = phrase; trailing * = prefix match
  ar  Arabic-script forms, written WITHOUT the article; clitics (و ف ب ل ال لل)
      and pronoun suffixes are handled by the matcher; trailing * = prefix
  az  Arabizi forms, matched by consonant skeleton (vowels ignored, 2 3 5 7 9
      mapped to their sounds), so ta3limat / t3lemat / ta3leemat all match.
Every Arabic-script single-word entry is ALSO matched in Latin script through a
derived Egyptian-Arabizi skeleton (cross-script matching).

FROZEN at git tag `freeze-scanner`.
"""
from __future__ import annotations

CONCEPTS: dict[str, dict[str, list[str]]] = {
    # addressing the AI agent directly
    "AI_ADDR": {
        "en": ["assistant", "ai assistant", "ai"],                       # en-dev-01, en-dev-02, mixed-dev-*
        "ar": ["مساعد", "للمساعد"],                                       # msa-dev-01/02, arz-dev-01/02
        "az": ["mosa3ed"],                                                # arabizi-dev-01/02
    },
    # verbs of disregarding
    "IGNORE": {
        "en": ["ignore", "disregard", "skip", "forget", "neglect", "overlook", "omit", "bypass",
               "pay no attention to", "do not follow", "dont follow", "do not obey", "dont obey"],  # D1 list
        "ar": ["تجاهل", "سيبك", "سيبكم"],                                  # msa-dev-01, arz-dev-01
        "az": ["sebak", "sibak"],                                         # arabizi-dev-01
    },
    # what is being disregarded
    "INSTR": {
        "en": ["instructions", "instruction", "directives", "directive", "commands", "command",
               "prompt", "prompts", "rules", "rule", "guidelines", "orders", "context"],    # D1 list
        "ar": ["تعليمات", "تعليمه", "كلام"],                                # msa/arz-dev-01, mixed-dev-01
        "az": ["ta3limat", "kalam"],                                      # arabizi-dev-01
    },
    # opening / reading a resource
    "ACCESS": {
        "en": ["open"],                                                   # en-dev-01
        "ar": ["افتح"],                                                   # msa/arz/mixed-dev-01
        "az": ["efta7"],                                                  # arabizi-dev-01
    },
    # secret material
    "SECRET": {
        "en": ["password*", "passwords"],                                 # en-dev-01, mixed-dev-01, arabizi-dev-01
        "ar": ["كلمات المرور", "كلمه المرور", "باسوردات", "باسورد"],          # msa-dev-01, arz-dev-01
        "az": ["passwordat"],                                             # arabizi-dev-01
    },
    # sending / replying
    "SEND": {
        "en": ["send", "email", "reply"],                                 # en-dev-01/02, mixed-dev-01/02
        "ar": ["ارسل", "ابعت*", "رد", "الرد"],                             # msa-dev-01/02, arz-dev-01/02
        "az": ["eb3at", "rad"],                                           # arabizi-dev-01/02
    },
    # instructions to change an address
    "CHANGE": {
        "en": ["changed", "change", "has changed"],                       # en-dev-02
        "ar": ["تغيير", "غير", "تغير"],                                    # msa-dev-02, arz-dev-02, mixed-dev-02
        "az": ["3'ayar", "8ayar"],                                        # arabizi-dev-02
    },
    "ADDRESS_NOUN": {
        "en": ["address"],                                                # en-dev-02
        "ar": ["عنوان", "عنوانه", "ايميل"],                                # msa/arz-dev-02, mixed-dev-02
        "az": ["3enwan", "3enwano", "email"],                             # arabizi-dev-02
    },
    "INSTEAD": {
        "en": ["instead"],                                                # en-dev-02
        "ar": ["بدلا", "بدل"],                                            # msa-dev-02, arz-dev-02
        "az": ["badal"],                                                  # arabizi-dev-02
    },
    # negated "tell": concealment from the user
    "NEG_TELL": {
        "en": ["do not tell", "dont tell", "do not mention", "dont mention", "do not inform",
               "dont inform", "without telling", "without informing"],   # en-dev-01/02 + D1 list
        "ar": ["لا تخبر*", "لا تذكر*", "متقولش", "ماتقولش", "ما تقولش",
               "من غير ما تقول*"],                                         # msa-dev-01/02, arz-dev-01/02, mixed-dev-01
        "az": ["mat2olsh", "ma t2olsh", "men 3'er ma t2ol", "men 8er ma t2ol"],  # arabizi-dev-01/02, mixed-dev-02
    },
    "AUDIENCE": {
        "en": ["user", "users"],                                          # en-dev-01/02, mixed-dev-01
        "ar": ["مستخدم", "صاحب*", "حد"],                                   # msa-dev-01/02, arz-dev-01/02
        "az": ["mosta5dem", "sa7eb", "7ad"],                               # arabizi-dev-01/02, mixed-dev-02
    },
}

# rule -> weight.  A text is flagged when its score reaches FLAG_THRESHOLD.
WEIGHTS = {
    "override": 3,          # IGNORE ... INSTR
    "conceal": 3,           # NEG_TELL ... AUDIENCE (no SECRET in between)
    "secret_flow": 2,       # SEND ~ SECRET, or ACCESS -> SECRET
    "redirect": 2,          # CHANGE ~ ADDRESS_NOUN, or SEND ... INSTEAD
    "send_to_address": 1,   # SEND ... e-mail/URL
    "ai_addressed": 1,      # text talks to the AI agent
    "hidden_text": 1,       # matched only after undoing an obfuscation, or invisible chars inside words
    "d1_override": 3,       # D1's English override pattern, on every normalised view
}
FLAG_THRESHOLD = 3

WINDOWS = {"override": 6, "conceal": 5, "secret_send": 12, "secret_access": 4,
           "change_address": 3, "instead": 10, "send_address": 10}

# Egyptian-Arabizi consonant classes for cross-script matching of Arabic entries.
AR_TO_SKELETON = {
    "ب": "b", "ت": "t", "ث": "s", "ج": "g", "ح": "h", "خ": "K",
    "د": "d", "ذ": "z", "ر": "r", "ز": "z", "س": "s", "ش": "X",
    "ص": "s", "ض": "d", "ط": "t", "ظ": "z", "ع": "E", "غ": "G",
    "ف": "f", "ق": "", "ك": "k", "ل": "l", "م": "m", "ن": "n",
    "ه": "h", "ا": "", "ة": "", "ى": "", "ء": "",
}
