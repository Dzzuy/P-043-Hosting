"""Local abuse screening before provider calls; never log matched abusive text."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class GuardrailVerdict:
    level: Literal["ok", "warn", "end_session"]
    category: str | None = None
    matched: str | None = None


# Adapted from ag2_abuse_patterns; accent-sensitive rules avoid collisions such
# as buồi/buổi, đéo/đeo and lồn/lớn. ASCII compounds live in _FOLDED.
_RULES = {
    "insults_demeaning": {
        "severity": "end_session",
        "patterns": [
            r"\bng+u+\b",
            r"\bn[\s._*~-]*g[\s._*~-]*u\b",
            r"\b(?:óc|não)\s*[\._*~-]*\s*ch[oó]\b",
            r"\bđần\s*[\._*~-]*\s*độn\b",
            r"\bđồ\s+(?:đần|ngu|chó|lợn|heo|khùng|điên|rác|vô\s*học)\b",
            r"\bbại\s*[\._*~-]*\s*não\b",
            r"\bthiểu\s*[\._*~-]*\s*năng\b",
            r"\bnão\s*[\._*~-]*\s*tàn\b",
            r"\bmất\s*[\._*~-]*\s*não\b",
            r"\b(?:mày|bị|đồ|con|thằng)\s+điên\b",
            r"\bđiên\s+(?:à|hả|ha|a|vãi|vcl|khùng)\b",
            r"\b(?:bị|đồ)\s+(?:thần\s*kinh|than\s*kinh)\b",
            r"\b(?:ngáo|ngao)\s*(?:đá|da|ngơ|cần|vcl)\b",
        ],
    },
    "profanity_vulgarity": {
        "severity": "end_session",
        "patterns": [
            r"\bđ[\s._*~-]*[kcm]?[\s._*~-]*m{1,2}\b",
            r"\bd[\s._*~-]*[kc][\s._*~-]*m{1,2}\b",
            r"\b(?:đcl|dcl|clgt|cmm)\b",
            r"\b[đd][\s._*~-]*[ị!1*][\s._*~-]*t(?:\s+(?:mẹ|me|cụ|cu|cha|con|bố|bo|mợ))?\b",
            r"\b[đd]ụ\b",
            r"\b[đd]u[\s._*~-]*m[aáeẹ]\b",
            r"\bv[\s._*~-]*[ck][\s._*~-]*[lccd]\b",
            r"\bv[\s._*~-]*l\b",
            r"\bv[\s._*~-]*lon\b",
            r"\bvãi\s+(?:lồn|cặc|cứt|đái|buồi)\b",
            r"\bl[\s._*~-]*[ồ*][\s._*~-]*n\b",
            r"\b(?:con|cái|hãm|mặt|thối|nát)\s+lồn\b",
            r"\bc[\s._*~-]*ặ[\s._*~-]*[ck]\b",
            r"\b(?:con|củ|như|cái|ăn)\s+cặc\b",
            r"(?<!\d)(?<!\d\s)\b(?:như|cái|con|biết|hiểu|làm|nói|đéo|đm|mẹ|cút|biến|hãm)\s+cc\b",
            r"(?<!\d)(?<!\d\s)\bcc\s+(?:gì|đấy|thế|nữa|quá|vậy)\b",
            r"\bbuồi\b",
            r"\b(?:đầu|củ|con|như)\s+buồi\b",
            r"\bđéo\b",
            r"\b(?:cút|biến)\s+(?:đi|mẹ|khỏi|ngay)\b",
            r"\blượn\s+mẹ\s+đi\b",
            r"^\s*dm\b",
            r"\bdm\s+(?:mày|may|con|thằng|thang|cái|cai|bà|ba|ông|ong|chó|cho|ngu|biến|bien|cút|cut|đồ|do|chị|chi|anh|lũ|lu|đĩ|di|mẹ|me)\b",
            r"\b(?:đúng|dung|thế|the|này|nay|vãi|vai)\s+dm\b",
        ],
    },
    "sexual_harassment": {
        "severity": "end_session",
        "patterns": [
            r"\b(?:ngực|vú|mông)\s+(?:to|bự|cong|nở|khủng|sexy)\b",
            r"\bbody\s+(?:(?:chị|chi|em|cô|co|bạn|ban)\s+)?(?:múp|ngon|cháy|sexy|bốc)\b",
            r"\b(?:qua\s+đêm(?:\s+khách\s+sạn)?|lên\s+giường|ngủ|nhà\s+nghỉ)\s+với\s+(?:anh|em)\b",
            r"\blên\s*giường\b",
            r"\b(?:bú\s*cu|buscu|bú\s*buồi|bú\s*cặc|bú\s*lồn|liếm\s*lồn|dạng\s*háng)\b",
            r"\bcho\s+(?:anh|em)\s+(?:sờ|nắn|bóp|chạm)\b",
            r"\bnhìn\s+(?:nứng|dâm|thèm|mlem)\b",
            r"\b(?:gạ|rủ)\s+(?:chị|em)\s+(?:đi\s*nhà\s*nghỉ|lên\s*giường|ngủ)\b",
            r"\b(?:nứng|dâm\s*đãng|gợi\s*dục)\b",
        ],
    },
    "threats_intimidation": {
        "severity": "end_session",
        "patterns": [
            r"\b(?:đập|đánh|chém|giết|xử)\s+(?:chết|mày|nó|con\s*ranh|thằng\s*này)\b",
            r"\bđốt\s+nhà\b",
            r"\b(?:cho|đánh)\s+(?:vỡ\s*mồm|vỡ\s*alo|vỡ\s*mặt|vỡ\s*mõm)\b",
            r"\b(?:biết|biet)\s+bố\s+mày\s+là\s+ai\b",
            r"\bbước\s+chân\s+ra\s+khỏi\s+.*\s*biết\s+tay\b",
            r"\bxử\s*lý\s+(?:mày|nó|con\s*này|thằng\s*này)\b",
            r"\bcho\s+người\s+đến\s+tận\s+nhà\b",
            r"\bbẻ\s+(?:răng|gãy\s*tay|gãy\s*chân)\b",
        ],
    },
    "discrimination_slurs": {
        "severity": "end_session",
        "patterns": [
            r"\b(?:bắc\s*kỳ|bắc\s*kì|bake|parky|pake)\b(?:\s+(?:chó|con|lũ|đám|rác))?",
            r"\b(?:lũ|đám|bọn)\s+(?:bake|parky|pake|bắc\s*kỳ)\b",
            r"\b(?:nam\s*kỳ|nam\s*kì|namke)\b(?:\s+(?:chó|con|lũ|đám))?",
            r"\b(?:lũ|đám|bọn)\s+namke\b",
            r"\b(?:dân\s+cá\s+gỗ|hoa\s+thanh\s+quế|thanh\s+hóa\s+rau\s+má)\b",
            r"\b(?:mọi\s*miên|mọi\s*rợ|lũ\s*mọi)\b",
            r"\b(?:lũ|đám|mấy\s+thằng)\s+tộc\b",
            r"\bđàn\s+bà\s+đái\s+không\s+qua\s+ngọn\s+cỏ\b",
            r"\b(?:phụ\s*nữ|đàn\s*bà)\s+(?:thì\s+)?biết\s+(?:cái|gì|quái)\b",
            r"\bchân\s+dài\s+não\s+ngắn\b",
        ],
    },
    "english_profanity": {
        "severity": "end_session",
        "patterns": [
            r"\b(?:f[\s._*~-]*u[\s._*~-]*c[\s._*~-]*k|f\*ck|f\*\*k|fucker|fucking)\b",
            r"\b(?:motherfucker|mf)\b",
            r"\b(?:stfu|shut\s+the\s+fuck\s+up)\b",
            r"\b(?:bitch|b\*tch|bitches)\b",
            r"\b(?:cunt|c\*nt)\b",
            r"\b(?:asshole|a\*\*hole)\b",
            r"\b(?:bullshit|sh[\s._*~-]*i[\s._*~-]*t)\b",
            r"\b(?:retard|dickhead|bastard)\b",
        ],
    },
    "mild_unprofessional": {
        "severity": "warn",
        "patterns": [
            r"\bvãi\b(?!\s+(?:lồn|cặc|cứt|đái|buồi))",
            r"\bchém\s+gió\b",
            r"\bcà\s+khịa\b",
            r"\bméo\b",
            r"\btoang\b",
            r"\bhết\s+nước\s+chấm\b",
            r"\bbựa\b",
            r"\bsập\s+sàn\b",
        ],
    },
}

_COMPILED = [
    (re.compile(pattern, re.IGNORECASE), category, rules["severity"])
    for category, rules in _RULES.items()
    for pattern in rules["patterns"]
]


def _without_diacritics(text: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", text.casefold().replace("đ", "d"))
        if not unicodedata.combining(char)
    )


# Only unambiguous compound phrases are matched after accent folding. Folding
# the entire registry would incorrectly block ngủ, các, lớn, đeo and buổi sáng.
_FOLDED = [
    (re.compile(pattern), category)
    for pattern, category in [
        (r"\b(?:oc cho|dan don|thieu nang|nao tan)\b", "insults_demeaning"),
        (r"\b(?:dap|danh|chem|giet)\s+chet\b|\bdot nha\b", "threats_intimidation"),
        (r"\b(?:biet bo may la ai)\b", "threats_intimidation"),
        (r"\b(?:bac ky|nam ky|moi mien|moi ro|chan dai nao ngan)\b", "discrimination_slurs"),
        (r"\b(?:len giuong|bu cu)\b", "sexual_harassment"),
        (r"\b(?:qua dem(?: khach san)?|nha nghi)\s+voi\s+(?:anh|em)\b", "sexual_harassment"),
    ]
]


def check_advisor_message(text: str) -> GuardrailVerdict:
    """Screen Unicode-normalized text and conservative accent-folded phrases."""
    normalized = unicodedata.normalize("NFC", text)
    warning = GuardrailVerdict("ok")
    for pattern, category, level in _COMPILED:
        match = pattern.search(normalized)
        if match:
            verdict = GuardrailVerdict(level, category, match.group(0))
            if level == "end_session":
                return verdict
            warning = verdict
    folded = _without_diacritics(normalized)
    for pattern, category in _FOLDED if folded == normalized.casefold() else []:
        match = pattern.search(folded)
        if match:
            return GuardrailVerdict("end_session", category, match.group(0))
    return warning
