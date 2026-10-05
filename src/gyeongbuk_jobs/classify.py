"""강사 공고 판별과 분야·기관유형 분류."""
from __future__ import annotations

import re

from .config import Rules


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _has_any(text: str, terms: list[str]) -> str | None:
    t = _squash(text)
    for term in terms:
        if _squash(term) and _squash(term) in t:
            return term
    return None


def _without(text: str, terms: list[str]) -> str:
    """포함 검사 전에 다른 뜻의 낱말을 지운다 ('청년마음건강사업' 속 '강사'). 지운 자리가 붙지 않게 '|' 로."""
    t = _squash(text)
    for term in terms:
        if _squash(term):
            t = t.replace(_squash(term), "|")
    return t


def judge(
    title: str, rules: Rules, keyword_filter: bool, label: str = "", *, keep_results: bool | None = None
) -> str | None:
    """강사 공고면 상태('모집중' 또는 '결과공고'), 아니면 None.

    포함 키워드는 제목과 게시판 구분값(label, 예: '방과후강사(관련)')에서 찾고,
    제외·결과 키워드는 제목에서만 찾는다. 공백은 무시한다 ('회원 모집' == '회원모집').
    keep_results 를 주면 rules.keep_result_notices 대신 그 값으로 결과공고를 남길지 정한다.
    """
    keep = rules.keep_result_notices if keep_results is None else keep_results
    if _has_any(title, rules.exclude):
        return None
    if keyword_filter and not _has_any(_without(f"{title} {label}", rules.include_ignore), rules.include):
        return None
    if _has_any(title, rules.result_notice):
        return "결과공고" if keep else None
    return "모집중"


def categorize(title: str, org_name: str, rules: Rules) -> str:
    """위에서부터 먼저 맞는 분야. '!' 로 시작하는 단어가 있으면 그 분야는 건너뛴다."""
    text = f"{title} {org_name}"
    for category, terms in rules.categories.items():
        negatives = [t[1:] for t in terms if t.startswith("!")]
        positives = [t for t in terms if not t.startswith("!")]
        if _has_any(text, negatives):
            continue
        if _has_any(text, positives):
            return category
    return "기타"


_ORG_TYPES = [
    ("교육청·학교", r"학교|교육청|교육지원청|유치원|교육원"),
    ("공단(체육시설)", r"공단|체육회|체육센터|스포츠센터|수영장"),
    ("여성·가족", r"여성|새일|가족"),
    ("청소년", r"청소년"),
    ("평생교육·도서관", r"도서관|평생|문화원|문화의집|박물관"),
    ("지자체", r"구청|군청|시청|도청|읍사무소|면사무소|행정복지센터|주민센터|보건소|경상북도"),
]


def infer_org_type(org_name: str, default: str = "") -> str:
    for org_type, pattern in _ORG_TYPES:
        if re.search(pattern, org_name or ""):
            return org_type
    return default


# 경북 22개 시·군 (군위군은 2023-07 대구로 옮겨 뺌). 다른 이름을 품은 이름이 없어 순서는 상관없다.
DISTRICTS = [
    "포항시", "경주시", "김천시", "안동시", "구미시", "영주시", "영천시", "상주시", "문경시", "경산시",
    "의성군", "청송군", "영양군", "영덕군", "청도군", "고령군", "성주군", "칠곡군", "예천군", "봉화군",
    "울진군", "울릉군",
]

# '시·군' 없이 쓴 이름 ('포항교육지원청', '경주시립도서관', '안동대학교'). '영양(사)·상주(인력)·고령(자)'는
# 다른 뜻으로 흔히 쓰여서 뒤에 기관을 가리키는 말이 올 때만 그 시·군으로 본다.
_AMBIGUOUS = r"(?=\s*(?:교육지원청|교육청|도서관|문화원|체육회|군청|시청|군민|시민|문화|청소년|평생|여성|가족|노인|장애인|종합|복지|보건|국민체육|스포츠|육아|읍|면|지역|[가-힣]{0,6}(?:초|중|고)(?:등)?학교))"
_STEMS = [
    (d, re.compile(re.escape(d[:-1]) + (_AMBIGUOUS if d[:-1] in ("영양", "상주", "고령") else "")))
    for d in DISTRICTS
]


def infer_district(text: str, default: str = "") -> str:
    text = text or ""
    for d in DISTRICTS:
        if d in text:
            return d
    for d, pattern in _STEMS:
        if pattern.search(text):
            return d
    return default
