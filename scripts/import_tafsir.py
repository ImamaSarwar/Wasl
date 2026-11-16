"""
Reads the tafsir files in data/raw/tafsir/ and fills `tafsir_sources` and `tafsir`. Called by build_db.py.

The Ibn Kathir file is keyed "surah:ayah", but commentary is GROUPED: the first ayah of a group holds the text
and lists the whole group in `ayah_keys`; the other ayahs of the group are just a pointer to that first ayah
(e.g. "67:3" -> "67:1"). So one text covers several ayahs; the app says so instead of pretending otherwise.

The text is HTML. It is sanitized HERE, once, with a strict allow-list (the front end then inserts it as HTML):
only simple text tags, and only `class` / `lang` attributes. Scripts, styles, links, images, event handlers
and every unknown tag are removed.
"""
import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

ALLOWED_TAGS = {"p", "span", "br", "b", "strong", "i", "em", "u", "sup", "sub", "ul", "ol", "li",
                "blockquote", "h1", "h2", "h3", "h4", "h5", "h6"}
VOID_TAGS = {"br"}
DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "template", "noscript"}
CLASS_OK = re.compile(r"^[A-Za-z0-9 _-]{1,60}$")
LANG_OK = re.compile(r"^[A-Za-z-]{1,10}$")


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT:
            self.skip += 1
            return
        if self.skip or tag not in ALLOWED_TAGS:
            return
        keep = []
        for k, v in attrs:
            v = v or ""
            if k == "class" and CLASS_OK.match(v):
                keep.append(f'class="{html.escape(v.strip(), quote=True)}"')
            elif k == "lang" and LANG_OK.match(v):
                keep.append(f'lang="{v}"')
        self.out.append(f"<{tag}{' ' + ' '.join(keep) if keep else ''}>")
        if tag not in VOID_TAGS:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        if tag in self.stack:                       # close any tags left open inside it first
            while self.stack:
                t = self.stack.pop()
                self.out.append(f"</{t}>")
                if t == tag:
                    break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))

    def close_all(self):
        while self.stack:
            self.out.append(f"</{self.stack.pop()}>")


def sanitize(raw_html):
    p = _Sanitizer()
    p.feed(raw_html or "")
    p.close()
    p.close_all()
    return "".join(p.out)


def read_tafsir_groups(path, surah, n_ayahs):
    """-> [(group_start, group_end, html)] covering every ayah of the surah exactly once."""
    data = json.load(open(path, encoding="utf-8"))
    groups = []
    for key, val in data.items():
        s, a = key.split(":")
        if int(s) != surah or not isinstance(val, dict):
            continue                                 # pointer entries (plain strings) are implied by ayah_keys
        keys = val.get("ayah_keys") or [key]
        ayahs = sorted(int(k.split(":")[1]) for k in keys if int(k.split(":")[0]) == surah)
        groups.append((ayahs[0], ayahs[-1], ayahs, val["text"]))
    groups.sort()
    covered = [a for _s, _e, ayahs, _t in groups for a in ayahs]
    if sorted(covered) != list(range(1, n_ayahs + 1)):
        raise ValueError(f"tafsir groups do not cover ayahs 1-{n_ayahs} exactly once: {covered}")
    for s, e, ayahs, _t in groups:
        if ayahs != list(range(s, e + 1)):
            raise ValueError(f"tafsir group {s}-{e} is not a continuous range")
    return [(s, e, sanitize(t)) for s, e, _a, t in groups]


def import_all(db, raw_dir, surah, n_ayahs):
    raw_dir = Path(raw_dir)
    files = sorted(raw_dir.glob("*.json")) if raw_dir.exists() else []
    if not files:
        print(f"  tafsir: skipped (no files in {raw_dir})")
        return []
    names = {"en-tafsir-ibn-kathir": "Tafsir Ibn Kathir (English)"}
    done = []
    for order, path in enumerate(files):
        sid = path.stem
        name = names.get(sid, sid.replace("-", " ").title())
        try:
            groups = read_tafsir_groups(path, surah, n_ayahs)
        except Exception as e:
            print(f"  tafsir: SKIPPED {path.name}: {e}")
            continue
        db.execute("INSERT INTO tafsir_sources VALUES (?,?,?)", (sid, name, order))
        for s, e, h in groups:
            db.execute("INSERT INTO tafsir VALUES (?,?,?,?)", (sid, s, e, h))
        done.append(sid)
        print(f"  tafsir: {name}: {len(groups)} commentary groups covering ayahs 1-{n_ayahs}")
    return done
