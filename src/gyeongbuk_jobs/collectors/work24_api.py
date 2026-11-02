"""고용24(구 워크넷) 채용정보 Open API.

요청: https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do
      ?authKey=...&callTp=L&returnType=XML&startPage=1&display=100&region=47000&keyword=강사
응답: <wantedRoot><total/><wanted><wantedAuthNo/><company/><title/><region/><regDt/><closeDt/>
      <wantedInfoUrl/>...</wanted>...</wantedRoot>

고용24에는 민간 학원 강사 공고가 매우 많으므로, 기관명이 공공기관 패턴에 맞는 공고만 남긴다.

목록의 제목은 길면 앞이나 뒤가 잘려 '...' 가 붙어 온다 (2026-11-02 러너 확인: '...어교실(한국어강사/영어강사) 일반계약직 채용 공고').
그런 공고만 상세 API(callTp=D)의 wantedTitle 로 전체 제목을 받는다 ('[한동대학교] 한국어교실(한국어강사/영어강사) …').
상세를 못 받으면 목록 제목 그대로 둔다.
"""
from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET

from ..classify import infer_district, infer_org_type
from ..dates import find_all_dates, parse_date
from ..models import Posting
from .base import Collector, NotConfigured

ENDPOINT = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do"
DETAIL_ENDPOINT = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210D01.do"
# 목록 제목의 앞이나 뒤에 붙은 말줄임
_CUT = re.compile(r"^\s*(?:\.{2,}|…)|(?:\.{2,}|…)\s*$")


def looks_cut(title: str) -> bool:
    """고용24 목록 제목이 잘렸는가 ('...어교실 …', '… 우대...')."""
    return bool(_CUT.search(title or ""))

DEFAULT_ORG_INCLUDE = (
    r"학교|교육청|교육지원청|교육원|공단|공사|재단|구청|군청|시청|행정복지센터|주민센터|복지관|도서관|수련관|"
    r"문화의집|여성회관|새일센터|여성인력개발센터|평생학습|평생교육|진흥원|개발원|연구원|대학교|청소년|"
    r"체육회|문화원|보건소|국립|시립|구립|군립|도립|경상북도|경북"
)
# 민간: 학원·교습소, 회사, 민간 직업훈련기관('○○직업전문학교'는 이름에 '학교'가 들어가 공공 패턴에 걸린다)
DEFAULT_ORG_EXCLUDE = (
    r"학원|교습소|공부방|과외|\(주\)|㈜|주식회사|유한회사|"
    r"직업전문학교|직업학교|직업훈련원|기술학교|아카데미|에듀|컨설팅|협동조합|"
    # 직업훈련기관은 공공(폴리텍 등)이라도 받지 않는다 (훈련교사는 강사 공고로 보지 않음)
    r"폴리텍|직업능력개발|훈련원|훈련센터|인력개발원"
)


class Work24Collector(Collector):
    def collect(self) -> list[Posting]:
        key_env = self.source.auth_env or "WORK24_API_KEY"
        auth_key = os.environ.get(key_env, "").strip()
        if not auth_key:
            raise NotConfigured(f"{key_env} 미설정 (고용24 Open API 인증키 필요)")

        params = self.source.params
        include = re.compile(self.source.options.get("org_include", DEFAULT_ORG_INCLUDE))
        exclude = re.compile(self.source.options.get("org_exclude", DEFAULT_ORG_EXCLUDE))
        max_pages = int(self.source.options.get("max_pages", 5))
        display = 100

        postings: list[Posting] = []
        for page in range(1, max_pages + 1):
            query = {
                "authKey": auth_key,
                "callTp": "L",
                "returnType": "XML",
                "startPage": page,
                "display": display,
                "region": params.get("region", "47000"),
                "keyword": params.get("keyword", "강사"),
            }
            resp = self.http.get(ENDPOINT, params=query)
            items, total = parse_work24_xml(resp.content)
            for item in items:
                company = item.get("company", "")
                if not include.search(company) or exclude.search(company):
                    continue
                if looks_cut(item.get("title", "")):
                    full = self._full_title(auth_key, item)
                    if full:
                        item = {**item, "title": full}
                postings.append(self._to_posting(item))
            if page * display >= total or not items:
                break
        return postings

    def _full_title(self, auth_key: str, item: dict[str, str]) -> str | None:
        """상세 API 의 전체 제목. 없거나 실패하면 None (목록 제목 그대로)."""
        try:
            resp = self.http.get(DETAIL_ENDPOINT, params={
                "authKey": auth_key, "callTp": "D", "returnType": "XML",
                "wantedAuthNo": item.get("wantedAuthNo", ""), "infoSvc": item.get("infoSvc") or "VALIDATION",
            })
            return parse_work24_title(resp.content)
        except Exception:  # noqa: BLE001 — 제목을 펴지 못해도 공고는 그대로 받는다
            return None

    def _to_posting(self, item: dict[str, str]) -> Posting:
        company = item.get("company", "")
        close_dates = find_all_dates(item.get("closeDt", ""), self.today)
        return Posting(
            source_id=self.source.id,
            title=item.get("title", "").strip(),
            url=item.get("wantedInfoUrl") or item.get("wantedMobileInfoUrl") or ENDPOINT,
            post_key=item.get("wantedAuthNo", ""),
            org_name=company,
            org_type=infer_org_type(company, "국가·공공기관"),
            district=infer_district(item.get("region", ""), "경북전체"),
            posted_date=parse_date(item.get("regDt"), self.today),
            deadline=close_dates[-1][1] if close_dates else None,  # '채용시까지 26-10-30' 같은 표기 대비
        )


def parse_work24_xml(content: bytes) -> tuple[list[dict[str, str]], int]:
    root = ET.fromstring(content)
    error = root.findtext(".//error") or root.findtext(".//message")
    if root.find(".//wanted") is None and error:
        raise RuntimeError(f"고용24 API 오류: {error.strip()}")
    total_text = root.findtext("total") or root.findtext(".//total") or "0"
    try:
        total = int(total_text.strip() or 0)
    except ValueError:
        total = 0
    items = []
    for wanted in root.iter("wanted"):
        items.append({child.tag: (child.text or "").strip() for child in wanted})
    return items, total


def parse_work24_title(content: bytes) -> str | None:
    """상세 API 응답(<wantedDtl>)의 전체 제목. 없으면 None ('정보가 존재하지 않습니다' 등)."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return None
    title = (root.findtext(".//wantedTitle") or "").strip()
    return title or None
