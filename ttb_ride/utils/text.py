import re
from difflib import SequenceMatcher
from typing import Optional, Tuple, Dict

# redact base64 and inline data URLs from LLM context
DATA_URL_MD_RE = re.compile(r"!\[[^\]]*\]\(data:image\/[^;]+;base64,[^)]+\)")
BASE64_LONG_RE = re.compile(r"[A-Za-z0-9\/+]{800,}={0,2}")

MAX_CONTEXT_MSGS = 12
MAX_CONTEXT_CHARS = 12000

TITLE_STOPWORDS_EN = {"mr","mr.","mrs","mrs.","ms","ms.","miss","miss.","mister"}
TITLE_STOPWORDS_TH = {"นาย","นาง","น.ส.","นส.","คุณ","ด.ช.","ด.ญ.","เด็กชาย","เด็กหญิง","คุณนาย"}

def sanitize_for_llm(text: str) -> str:
    if not text: return ""
    text = DATA_URL_MD_RE.sub("[image omitted]", text)
    text = BASE64_LONG_RE.sub("[omitted]", text)
    if len(text) > 2000:
        text = text[:2000] + " …"
    return text

def thai_id_checksum_ok(nid: str) -> bool:
    digits = re.sub(r"\D", "", nid or "")
    if len(digits) != 13 or not digits.isdigit():
        return False
    s = sum(int(digits[i]) * (13 - i) for i in range(12))
    check = (11 - (s % 11)) % 10
    return check == int(digits[-1])

def strip_titles_and_punct(s: str) -> str:
    if not s: return ""
    s = s.lower()
    s = re.sub(r"[^0-9a-zA-Zก-๙]+", " ", s)
    tokens = [t for t in s.split() if t not in TITLE_STOPWORDS_EN and t not in TITLE_STOPWORDS_TH]
    return " ".join(tokens)

def normalize_name(s: Optional[str]) -> str:
    if not s: return ""
    s = strip_titles_and_punct(s)
    return re.sub(r"\s+", " ", s).strip()

def relaxed_name_match(a: str, b: str, threshold: float = 0.50) -> Tuple[bool, float, Dict[str, float]]:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return False, 0.0, {"ratio": 0.0, "token_overlap": 0.0, "last_same": 0.0}
    ratio = SequenceMatcher(None, na, nb).ratio()
    ta, tb = set(na.split()), set(nb.split())
    token_overlap = len(ta & tb) / max(1, len(ta | tb))
    last_same = 1.0 if (na.split()[-1] == nb.split()[-1]) else 0.0
    score = max(ratio, token_overlap, last_same)
    return (score >= threshold), round(score, 3), {
        "ratio": round(ratio, 3),
        "token_overlap": round(token_overlap, 3),
        "last_same": last_same
    }

def mask_nid(nid: str) -> str:
    digits = re.sub(r"\D", "", nid or "")
    if len(digits) != 13: return nid or ""
    return f"{digits[0]} {digits[1:5]} **** {digits[9:11]} {digits[11:13]}"
