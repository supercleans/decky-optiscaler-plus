"""What a game needs besides OptiScaler, read out of its wiki entry.

Some games are on the compatibility list as working, but only with something
else in place first: a mod OptiScaler hooks into (a Luma build, a DLSS mod,
SekiroTSR), a file copied into the game folder, Engine.ini lines, an
anti-cheat switched off. The list says so in prose, and an install that skips
it loads OptiScaler and changes nothing on screen. None of these can be
installed from here, so they are found and *said*, with the wiki's own
sentence beside each, rather than acted on.

REFramework and PDPerfPlugin are not here: the plugin installs or asks for
them as steps of their own. Nor are the launch arguments the wiki names
(-dx12 and the like): the plan already puts them in the launch options.
"""

import re

from .constants import WIKI_HTML_BASE

# What is looked for: (key, kind, name, pattern, link). The name is what the
# checklist calls it; the link is where to get it when the sentence has none.
KNOWN = (
    # Not "check the Luma UE table": that is where Engine.ini lines are listed.
    ("luma", "mod", "Luma 모드", r"\bLuma\b(?!\s+UE\s+table)",
     "https://github.com/Filoppi/Luma-Framework/releases"),
    ("dlss-mod", "mod", "DLSS 모드", r"\bDLSS mod\b", None),
    ("sekirotsr", "mod", "SekiroTSR 모드", r"\bSekiroTSR\b", None),
    ("erss-fg", "mod", "ERSS-FG 모드", r"\bERSS[- ]?FG\b", None),
    ("nukems", "mod", "Nukem's dlssg-to-fsr3", r"\bNukem",
     f"{WIKI_HTML_BASE}/Nukem's-dlssg%E2%80%90to%E2%80%90fsr3"),
    ("special-k", "mod", "Special K", r"\bSpecial ?K\b", None),
    ("uasi", "mod", "Ultimate ASI Loader", r"Ultimate[- ]ASI[- ]Loader|\bUASI\b",
     "https://github.com/ThirteenAG/Ultimate-ASI-Loader/releases"),
    ("nvngx-dlss", "file", "nvngx_dlss.dll 복사", r"nvngx_dlss\.dll", None),
    ("engine-ini", "config", "Engine.ini 수정",
     r"Engine\.ini|\bUE5? tweaks?\b|Unreal-Engine-Tweaks|\bengine tweaks?\b",
     f"{WIKI_HTML_BASE}/Unreal-Engine-Tweaks"),
    ("anti-cheat", "game", "안티치트 끄기",
     r"disabl\w*\s+(?:the\s+)?(?:BattlEye|EAC|Easy ?Anti-?Cheat|anti-?cheat)|without EAC", None),
    ("beta-branch", "game", "Steam 베타 브랜치", r"\bbeta branch\b", None),
)
# "Requires the X mod", "use Y mod": anything named a mod that is not known
# above. REFramework is a step of its own; the rest are names of known ones.
GENERIC_MOD = re.compile(
    r"\b(?i:requires?|need(?:s|ed)?|use|using|install(?:ing)?|with)\s+(?i:the\s+|a\s+)?"
    r"((?:[A-Z0-9][\w'.\-]*\s+){1,3}?)mod\b")
NOT_GENERIC = re.compile(r"^(?:REFramework|PDUpscaler|PDPerf|OptiPatcher|Luma|DLSS|SekiroTSR|ERSS|"
                         r"Nukem|Special ?K|SPT|Singleplayer)\b[\w'.\- ]*$|^DLSS$", re.I)

# A sentence that requires something, and one that only offers it. A hedge
# wins: "might require" is a suggestion, and saying "필수" about it would be a
# lie the user acts on.
REQUIRED_RE = re.compile(r"\b(?:requires?|required|must|needs?|only (?:works )?with|as (?:a )?basis|"
                         r"copy|paste)\b", re.I)
HEDGED_RE = re.compile(r"\b(?:might|may|if|could|can be|for less|optional(?:ly)?|try)\b", re.I)

# The fields a requirement is read from, most specific first. "Upscaler
# Inputs" is where an entry writes "DLSS with Luma Framework".
FIELDS = ("Upscaler Inputs", "Notes", "Known Issues", "Settings")
# Where an entry starts describing another way to set the game up; what is
# needed for that way is not needed for this one.
ALT_METHOD_RE = re.compile(r"\b(?:alternat(?:e|ive)\s+method|method\s*[2-9])\b", re.I)
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)|(https?://[^\s\[\]]+)(?:\[([^\]]*)\])?")


def _plain(text):
    """Wiki markup down to words, links kept as ``label (target)``."""
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r"\1 (\2)", text or "")
    text = re.sub(r"(https?://[^\s\[\]]+)\[([^\]]*)\]", r"\2 (\1)", text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    # Emphasis markers, but not the underscore inside a name like nvngx_dlss.dll.
    text = re.sub(r"[*`]+|(?<!\w)_+|_+(?!\w)", "", text)
    return text.replace("’", "'").replace("–", "-").replace("—", "-")


def _sentences(text):
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(\[])|\s+-{3,}\s+|\s\*+\s", text)
    return [p.strip(" -") for p in parts if p and p.strip(" -")]


def _link(raw_sentence):
    """The first link in a sentence, made absolute."""
    found = LINK_RE.search(raw_sentence)
    if not found:
        return None
    target = found.group(2) or found.group(3)
    if target.startswith("http"):
        return target
    if target.startswith("#"):
        return None
    return f"{WIKI_HTML_BASE}/{target}"


def _texts(recommendation):
    """(origin, raw text) for every field worth reading, this method only."""
    detail = recommendation.get("detail") or {}
    out = []
    for label in FIELDS:
        value = (detail.get(label) or "").strip()
        if value and value not in ("-", "N/A"):
            out.append((f"wiki entry, “{label}”", value))
    if recommendation.get("notes"):
        out.append(("compatibility list notes", recommendation["notes"]))
    cut = []
    for origin, text in out:
        stop = ALT_METHOD_RE.search(text)
        cut.append((origin, text[:stop.start()] if stop else text))
    return cut


#: The list's two mod tables say what every game in them needs once, in the
#: table's introduction, and nothing in a row repeats it.
TABLE_REQUIREMENTS = {
    "luma-ue": {
        "key": "luma", "kind": "mod", "name": "Luma UE 모드",
        "detail": "OptiScaler 위키의 “Luma Unreal Engine” 표에 있는 게임입니다. Luma Framework의 "
                  "Unreal Engine 모드가 게임의 TAA를 DLSS로 바꿔야 OptiScaler가 동작합니다. 지금은 "
                  "DX11이 필요하고, 게임마다 Engine.ini 명령이나 게임 안 안티에일리어싱 설정이 더 필요할 수 "
                  "있습니다.",
        "link": f"{WIKI_HTML_BASE}/Luma-Unreal-Engine-Luma-UE",
    },
    "mods": {
        "key": "upscaler-mod", "kind": "mod", "name": "업스케일러 모드",
        "detail": "OptiScaler 위키의 “Upscaler mods support” 표에 있는 게임입니다. 게임 자체에는 "
                  "업스케일러가 없어서, 서드파티 모드가 DLSS·FSR·XeSS를 추가해야 OptiScaler가 동작합니다. "
                  "어떤 모드인지와 권장 설치 방법은 위키 항목에 있습니다.",
        "link": None,
    },
}
#: What already names the mod a "mods" table game uses, so the generic one is not added too.
SPECIFIC_MODS = {"luma", "dlss-mod", "sekirotsr", "erss-fg"}


def mine(recommendation):
    """Everything this entry says the game needs besides OptiScaler.

    ``[{key, kind, name, required, detail, source, link}]``, one per thing,
    most firmly stated first. ``kind`` is mod, file, config or game;
    ``required`` is false where the entry only suggests it.
    """
    if not recommendation:
        return []
    found = {}
    table = TABLE_REQUIREMENTS.get(recommendation.get("table") or "")
    if table:
        found[table["key"]] = {
            **table,
            "required": True,
            "source": "compatibility list table",
            "link": table["link"] or recommendation.get("wiki_url"),
        }
    for origin, raw in _texts(recommendation):
        for raw_sentence in _sentences(raw):
            sentence = _plain(raw_sentence)
            # Not inside a web address ("…/Luma-Framework/wiki"): that names a
            # site, not a requirement. A wiki page name ("Unreal-Engine-Tweaks")
            # is kept, since it is often the only word saying what the link is.
            words = re.sub(r"https?://\S+", "", sentence)
            # A mod named in full ("FF7 Remake Luma mod") first, under the key of
            # the known one it is a build of, so it is said once, by its name.
            hits = {}
            for match in GENERIC_MOD.finditer(words):
                label = match.group(1).strip()
                if NOT_GENERIC.search(label):
                    continue
                known = next((entry for entry in KNOWN if re.search(entry[3], label, re.I)), None)
                key = known[0] if known else f"mod:{label.lower()}"
                hits[key] = (key, "mod", f"{label} 모드", known[4] if known else None)
            for key, kind, name, pattern, link in KNOWN:
                if key not in hits and re.search(pattern, words, re.I):
                    hits[key] = (key, kind, name, link)
            hits = list(hits.values())
            if not hits:
                continue
            required = ((origin.endswith("“Upscaler Inputs”") or bool(REQUIRED_RE.search(sentence)))
                        and not HEDGED_RE.search(sentence))
            for key, kind, name, link in hits:
                item = found.get(key)
                if item and (item["required"] or not required):
                    continue
                found[key] = {
                    "key": key,
                    "kind": kind,
                    "name": name,
                    "required": required,
                    "detail": sentence[:300],
                    "source": origin,
                    "link": _link(raw_sentence) or link,
                }
    # The table's "some upscaler mod" is not worth saying when the entry names
    # the mod, or when that mod is REFramework, which the plugin installs.
    named = SPECIFIC_MODS & set(found) or any(key.startswith("mod:") for key in found)
    via_ref = any(re.search(r"REFramework", text, re.I) for _, text in _texts(recommendation))
    if "upscaler-mod" in found and (named or via_ref):
        del found["upscaler-mod"]
    return sorted(found.values(), key=lambda item: not item["required"])


def required_names(entry):
    """What a list row says its game cannot go without, by name."""
    return [item["name"] for item in mine(entry or {}) if item["required"]]
