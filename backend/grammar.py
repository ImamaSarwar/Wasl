"""
Turns the technical morphology codes stored in words.pos_tag / words.grammar (e.g. "PERF,3MS,form 6")
into plain-English descriptions for the hover card. No database access; pure functions, easy to test.

describe(pos_tag, grammar) -> {"kind": "Verb", "hint": None, "details": [{"label": "Tense", "value": "..."}, ...]}

The raw codes are NOT replaced in the database (the RAG code and the verification log still use them);
this module only adds a human-readable layer on top.
"""

# Who does the action / who is meant: code -> (plain wording, technical wording)
PERSON = {
    "1S": ("I", "1st person, singular"),
    "1P": ("we", "1st person, plural"),
    "2MS": ("you (one man)", "2nd person, masculine, singular"),
    "2FS": ("you (one woman)", "2nd person, feminine, singular"),
    "2D": ("you two", "2nd person, dual"),
    "2MP": ("you (a group)", "2nd person, masculine, plural"),
    "2FP": ("you (a group of women)", "2nd person, feminine, plural"),
    "3MS": ("he / it", "3rd person, masculine, singular"),
    "3FS": ("she / it", "3rd person, feminine, singular"),
    "3D": ("they two", "3rd person, dual"),
    "3MP": ("they (a group)", "3rd person, masculine, plural"),
    "3FP": ("they (a group of women)", "3rd person, feminine, plural"),
}

TENSE = {
    "PERF": "Past (māḍī): it already happened",
    "IMPF": "Present / future (muḍāriʿ): happening now or still to come",
    "IMPV": "Command (amr): telling someone to do it",
}

# Derived verb patterns. Form I is the basic verb, so it is not shown. Wording is deliberately hedged
# ("typically") because each pattern has several uses.
VERB_FORM = {
    "2": "Form II: typically an intensified or 'causing' version of the basic verb",
    "3": "Form III: typically doing the action to or with someone",
    "4": "Form IV: typically 'making it happen' (causing the action)",
    "5": "Form V: typically the action happening to oneself",
    "6": "Form VI: typically a mutual or shared action",
    "7": "Form VII: typically the action 'just happens' (passive-like)",
    "8": "Form VIII: typically doing the action for or to oneself",
    "9": "Form IX: typically becoming a colour or a defect",
    "10": "Form X: typically asking for, seeking or considering",
}

GENDER_NUMBER = {
    "M": "masculine", "F": "feminine",
    "MS": "masculine, singular", "FS": "feminine, singular",
    "MP": "masculine, plural", "FP": "feminine, plural",
    "MD": "masculine, dual", "FD": "feminine, dual", "D": "dual",
}

CASE = {
    "NOM": "Subject form (nominative): usually the one doing or being described",
    "ACC": "Object form (accusative): usually the thing acted on, or extra detail",
    "GEN": "'Of' / after-a-preposition form (genitive)",
}

# Word kinds for words tagged N, in priority order: (code, label, hint)
NOUN_KINDS = [
    ("PRON", "Pronoun", "he, she, you, we, they..."),
    ("REL", "Relative pronoun", "who / which / that"),
    ("DEM", "Pointing word", "this / that"),
    ("INTG", "Question word", "who? what? how? when?"),
    ("PN", "Proper name", None),
    ("T", "Time word", "when / at the time of"),
    ("LOC", "Place word", "where / above / before / with"),
    ("ACT_PCPL", "Doer noun (active participle)", "someone or something that does the action"),
    ("PASS_PCPL", "Receiver noun (passive participle)", "someone or something the action is done to"),
    ("VN", "Verbal noun", "the action itself, named as a thing"),
    ("ADJ", "Describing word (adjective)", None),
]

# Small words tagged P: code -> (label, hint). Empty code = plain preposition.
PARTICLE_KINDS = {
    "": ("Preposition / small word", "in, on, from, to, with..."),
    "NEG": ("Negation", "not / no"),
    "CONJ": ("Conjunction", "and / then / or"),
    "COND": ("Conditional word", "if"),
    "ACC": ("Emphasis particle", "indeed (inna and its family)"),
    "CERT": ("Certainty particle", "indeed / certainly (qad)"),
    "RES": ("Exception word", "except / only"),
    "SUB": ("Linking word", "that / so that"),
    "INTG": ("Question particle", "is it...? / do...?"),
    "ANS": ("Answer particle", "yes / indeed"),
    "SUR": ("Surprise particle", "suddenly / behold"),
    "RET": ("Retraction particle", "rather / nay"),
    "EMPH": ("Emphasis particle", "indeed / surely"),
    "FUT": ("Future particle", "will"),
    "VOC": ("Calling particle", "O ..."),
    "PRP": ("Purpose particle", "in order to"),
    "CAUS": ("Reason particle", "because"),
    "CIRC": ("Circumstantial particle", "while / as"),
    "RSLT": ("Result particle", "then / so"),
    "PREV": ("Preventive particle", None),
    "SUP": ("Supplemental particle", None),
    "REM": ("Resumption particle", "and / now"),
    "COM": ("Companion particle", "with"),
    "EXH": ("Encouragement particle", "why not...?"),
    "EXL": ("Explanation particle", "that is to say"),
    "EXP": ("Exception particle", "except"),
    "PRO": ("Prohibition particle", "do not"),
    "AMD": ("Amendment particle", "but rather"),
    "AVR": ("Warning particle", "lest"),
    "EQ": ("Equalization particle", "whether... or"),
    "INC": ("Beginning particle", None),
    "IMPN": ("Command particle", None),
    "INL": ("Letter group", "disconnected letters"),
}


def _split(grammar):
    """'PERF,3MS,form 6' -> (set of codes, verb form as str or None)"""
    codes, vform = set(), None
    for part in (grammar or "").split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("form "):
            vform = part[5:].strip()
        else:
            codes.add(part)
    return codes, vform


def _person(codes):
    for c in PERSON:
        if c in codes:
            plain, tech = PERSON[c]
            return f"{plain} ({tech})"
    return None


def _gender_number(codes):
    # Prefer the most specific code (e.g. MS over M).
    for c in ("MS", "FS", "MP", "FP", "MD", "FD", "D", "M", "F"):
        if c in codes:
            return GENDER_NUMBER[c]
    return None


def describe(pos_tag, grammar):
    codes, vform = _split(grammar)
    details = []

    def add(label, value):
        if value:
            details.append({"label": label, "value": value})

    # ---- verbs ----
    if pos_tag == "V":
        for c in ("PERF", "IMPF", "IMPV"):
            if c in codes:
                add("Tense", TENSE[c])
        add("Who", _person(codes))
        if "PASS" in codes:
            add("Voice", "Passive: the action is done to the subject")
        if vform and vform != "1":
            add("Pattern", VERB_FORM.get(vform, f"Form {vform}"))
        return {"kind": "Verb", "hint": "an action word", "details": details}

    # ---- small words ----
    if pos_tag == "P":
        key = next((c for c in codes if c in PARTICLE_KINDS and c != ""), "")
        label, hint = PARTICLE_KINDS.get(key, ("Particle", None))
        if key == "" and codes:  # unknown code: never hide it
            add("Code", ", ".join(sorted(codes)))
        return {"kind": label, "hint": hint, "details": details}

    # ---- nouns and everything noun-like ----
    kind, hint = "Noun", "a person, place or thing"
    for code, label, h in NOUN_KINDS:
        if code in codes:
            kind, hint = label, h
            break
    if "PRON" in codes:
        add("Who", _person(codes))
    else:
        add("Gender / number", _gender_number(codes))
        if "REL" not in codes and "DEM" not in codes:
            if "INDEF" in codes:
                add("Definiteness", "Indefinite: 'a' or 'an'")
            for c in ("NOM", "ACC", "GEN"):
                if c in codes:
                    add("Role in sentence", CASE[c])
        if "ACT_PCPL" in codes and "ADJ" in codes:
            add("Also used as", "a describing word (adjective)")
    return {"kind": kind, "hint": hint, "details": details}
