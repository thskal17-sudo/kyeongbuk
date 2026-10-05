"""표(table) 형태 게시판 공통 수집기.

공공기관 게시판은 대부분 '번호 | 제목 | 작성자 | 등록일 | 조회수' 형태의 표라서, 셀렉터를 일일이
적지 않아도 머리글(th)로 열을 찾아 읽을 수 있다. 사이트별 차이는 sources.yaml 의 옵션으로 흡수한다.

options (모두 선택)
    page_param      목록 페이지 번호 파라미터 이름 (예: pageIndex). 없으면 1페이지만 본다
    page_offset     쪽 번호 대신 건너뛸 글 수를 넘기는 게시판의 한 쪽 글 수 (offset=0,10,20 → 10. 부산육아종합지원센터 어린이집 구인)
    row_selector    행 CSS 셀렉터 (자동 판별이 틀릴 때만)
    link_template   제목 링크가 javascript 일 때 onclick 인자로 상세 주소를 만드는 틀 ({0}, {1} …)
    key_param       상세 주소에서 게시글 번호로 쓸 쿼리 파라미터 (예: q_bbsDocNo)
    key_pattern     상세 주소에서 게시글 번호를 뽑는 정규식 (첫 괄호). 같은 글이 두 가지 주소로
                    나오는 게시판용 (XE: /xe/sub7_01/24564 와 ?document_srl=24564)
    key_selector    행 안에서 게시글 식별값으로 쓸 요소. 링크가 __doPostBack('…$ctl02$lnkSubject') 처럼
                    줄 위치뿐이라 새 글이 올라오면 값이 밀리는 게시판용 (신라대 평생교육원: 제목)
    form_link       true 면 onclick 으로 제출하는 <form> 의 action + hidden 값으로 상세 주소를 만든다
    detail_get      상세 페이지를 GET 으로 열 수 있으면 true (마감일 추출에 사용, 기본 true)
    org_name        기관명 기본값 (작성자 열이 '관리자' 등일 때)
    org_prefix      부서 칸 앞에 붙일 기관 이름 (새올 '체육진흥과' → '부산 서구청 체육진흥과')
    org_fixed       true 면 작성자·부서 칸을 보지 않고 늘 org_name 을 쓴다 (도서관 공지: 작성자가 '총무과'·'독서문화과')
    link_base       상대 링크를 풀 기준 주소 (페이지 주소와 다를 때. <base href> 가 있으면 자동 적용)
    row_must_contain 이 글자가 있는 행만 (예: 근무지 열이 있는 전국 게시판에서 '부산')
    link_attr       제목 링크의 이 속성 값으로 상세 주소를 만든다 (예: data-id → link_template 의 {0},
                    link_template 이 없으면 값 자체를 주소로. 부산교육청 게시판 <a data-id="1180893">).
                    행에 링크가 없으면 행(row_selector)의 이 속성 (<tr data-href="/board/notice/read/68">)
    title_selector  행 안에서 제목만 담긴 요소 (표가 아닌 <li> 목록에서 링크에 날짜·기관이 섞일 때). 링크면 상세 주소도 거기서
    date_selector   행 안의 날짜 요소. '시작 ~ 끝' 이면 시작을 게시일, 끝을 마감일로.
                    'li.time@title' 처럼 쓰면 요소의 속성 값을 읽는다 (셀렉터 옵션 공통)
    org_selector    행 안의 기관명 요소 (제목이 기관명으로 시작하면 제목에서는 뺀다).
                    짚어 준 칸이라 사람 이름 검사는 건너뛴다 (동 공지 작성자 칸 '괘법동')
    title_org_pattern 제목에서 기관명을 뽑는 정규식 (첫 괄호). 예: 제목 앞 '[송도사랑요양원]' 의 기관명
    district_selector 행 안의 지역 요소 (다누리 채용정보 '[ 부산 부산진구 ]' → 구를 정함)
    include         이 게시판에만 쓸 강사 공고 포함 키워드 (keywords.yaml 의 include 대신)
    encoding        페이지가 선언한 문자셋이 틀릴 때 실제 문자셋 (예: utf-8 이라 적고 EUC-KR 로 보내는 그누보드 → cp949)
    ok_status       목록 응답이 이 상태 코드여도 그대로 읽는다 (해양대 평생교육원: 목록을 다 보내고 404)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup, Tag

from ..classify import infer_district
from ..dates import extract_deadline, has_full_date, parse_date
from ..models import Posting
from .base import Collector

_HEADER_MAP = {
    "title": r"제목|공고명|모집명|프로그램명|강좌명",
    "posted": r"등록일|작성일|게시일|공고일|날짜|일자",
    "deadline": r"마감|접수기간|모집기간|신청기간|접수일|기간",
    "org": r"작성자|부서|기관|학교|담당|등록자|글쓴이",
    "label": r"^(구분|분류|분야|직종)$",
    "district": r"^(지역|구군|구·군)$",
}
# 게시글 식별값에서 빼는 쿼리 파라미터 (페이지 번호·검색어·검색 기간(srchBeginDt)·세션 등은 같은 글이라도 달라진다)
_VOLATILE_PARAMS = re.compile(r"page|currpage|rowperpage|search|srch|sort|_csrf|jsessionid", re.I)
# 작성자 칸의 계정·직위 ('문화의집관리자', '인사담당자', '분관 과장')는 기관명이 아니다
_NOT_ORG = re.compile(
    r"^(\S*(관리자|담당자)|담당|admin|운영자|홈페이지|-|\S*\s?(과장|팀장|주임|대리|실장|센터장|관장))?$", re.I
)
# 작성자 칸의 사람 이름 (최희상, 김예솔): 한글 2~4자이고 기관 이름처럼 끝나지 않는 것
_PERSON = re.compile(r"[가-힣]{2,4}")
_ORG_END = re.compile(r"(청|원|교|관|과|팀|실|단|터|회|소|부|국|처|사|군|구|시)$")
# 제목 속 학교·유치원 이름 (작성자가 사람 이름인 교육청 게시판에서 기관명으로 씀)
_SCHOOL = re.compile(r"[가-힣]{1,20}?(?:초등학교|중학교|고등학교|(?<!방과후)학교(?!밖)|유치원)")  # '통합방과후학교'·'학교밖'은 빼고
_GENERIC_SCHOOLS = {"초등학교", "중학교", "고등학교", "대학교"}  # '검정고시 고등학교' 처럼 이름 없이 쓴 말
_HIDDEN_CHARS = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_JS_CALL = re.compile(r"([A-Za-z_$][\w$.]*)\s*\(([^)]*)\)")
_JS_ARG = re.compile(r"""['"]([^'"]*)['"]|(-?\d+)""")
_LOCATION_HREF = re.compile(r"""location(?:\.href)?\s*=\s*['"]([^'"]+)['"]""")


@dataclass
class BoardRow:
    title: str
    url: str
    key: str
    posted: date | None
    deadline: date | None
    org: str
    detail_ok: bool
    label: str = ""
    district: str = ""


class BoardCollector(Collector):
    def collect(self) -> list[Posting]:
        opts = self.source.options
        postings: list[Posting] = []
        seen: set[str] = set()
        for page in range(1, max(1, self.source.pages) + 1):
            resp = self.fetch_page(page)
            if resp is None:
                break
            rows = parse_board(resp.content, resp.url, opts, self.today)
            fresh = []
            for r in rows:
                if r.key not in seen:  # 공지 줄과 일반 줄에 같은 글이 두 번 나오는 게시판도 있다
                    seen.add(r.key)
                    fresh.append(r)
            for r in fresh:
                postings.append(
                    Posting(
                        source_id=self.source.id,
                        title=r.title,
                        url=r.url,
                        post_key=r.key,
                        org_name=(
                            opts["org_name"] if opts.get("org_fixed")
                            else _with_prefix(opts.get("org_prefix"), r.org) or opts.get("org_name", "")
                        ),
                        org_type=self.source.org_type,
                        district=infer_district(f"{r.district} {r.org}", self.source.district),
                        posted_date=r.posted,
                        deadline=r.deadline,
                        label=r.label,
                        detail_url=r.url if r.detail_ok and opts.get("detail_get", True) else None,
                    )
                )
            if not fresh:
                break
        return postings

    def fetch_page(self, page: int):
        url = self.page_url(page)
        if url is None:
            return None
        try:
            return self.http.get(url)
        except requests.exceptions.HTTPError as exc:
            # 목록은 제대로 보내면서 상태 코드만 404 인 서버 (해양대 평생교육원)
            if exc.response is not None and exc.response.status_code in self.source.options.get("ok_status", ()):
                return exc.response
            raise

    def page_url(self, page: int) -> str | None:
        url = self.source.url or ""
        if page == 1:
            return url
        param = self.source.options.get("page_param")
        if not param:
            return None
        step = self.source.options.get("page_offset")
        return set_query(url, **{param: (page - 1) * step if step else page})


def _with_prefix(prefix: str | None, org: str) -> str:
    """부서 칸 앞에 기관 이름을 붙인다 (새올 '체육진흥과' → '부산 서구청 체육진흥과')."""
    if not prefix:
        return org
    return f"{prefix} {org}" if org and not org.startswith(prefix) else prefix


class FormBoardCollector(BoardCollector):
    """검색 폼을 POST 해야 목록이 나오는 게시판 (예: 잡알리오 - 폼의 _csrf 토큰이 필요).

    목록 화면을 한 번 GET 해서 폼의 숨은 값(토큰 등)을 얻은 뒤, 검색 조건을 더해 POST 한다.
    options
        form_selector   폼 CSS 셀렉터 (기본 form)
        data            검색 조건 (예: {location: R3016})
        page_param      폼의 쪽 번호 이름 (예: pageNo)
    """

    _form: tuple[str, dict[str, str]] | None = None

    def fetch_page(self, page: int):
        opts = self.source.options
        if page > 1 and not opts.get("page_param"):
            return None
        if self._form is None:
            resp = self.http.get(self.source.url or "")
            soup = BeautifulSoup(resp.content, "lxml")
            form = soup.select_one(opts.get("form_selector", "form"))
            if form is None:
                raise ValueError(f"검색 폼을 찾지 못함: {opts.get('form_selector', 'form')}")
            fields = {
                i["name"]: i.get("value", "") for i in form.find_all("input", {"type": "hidden"}) if i.get("name")
            }
            self._form = (urljoin(resp.url, form.get("action") or "") or resp.url, fields)
        action, fields = self._form
        data = {**fields, **opts.get("data", {})}
        if opts.get("page_param"):
            data[opts["page_param"]] = str(page)
        return self.http.post(action, data=data)


def set_query(url: str, **params) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({k: str(v) for k, v in params.items()})
    return urlunsplit(parts._replace(query=urlencode(query)))


def stable_key(url: str) -> str:
    """같은 글이면 목록 페이지가 달라도 같은 값이 되도록 URL 을 정리한다."""
    parts = urlsplit(url)
    path = re.sub(r";jsessionid=[^/?#]*", "", parts.path, flags=re.I)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not _VOLATILE_PARAMS.search(k) and v]
    return urlunsplit(parts._replace(path=path, query=urlencode(sorted(query)), fragment=""))


def _clean(text: str | None) -> str:
    return re.sub(r"\s+", " ", _HIDDEN_CHARS.sub("", text or "")).strip()


def _list_date(text: str, today: date) -> date | None:
    """목록 날짜 칸. 연도 없는 '09-03'(그누보드 기본 목록)은 오늘 이전의 가장 가까운 날로 본다."""
    m = re.fullmatch(r"\s*(\d{1,2})-(\d{1,2})\s*", text or "")
    if not m:
        return parse_date(text, today)
    for year in (today.year, today.year - 1):
        try:
            d = date(year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            continue
        if d <= today:
            return d
    return None


def _org_name(raw: str, title: str, maybe_person: bool = True) -> str:
    """작성자·부서 칸의 값을 기관명으로. 사람 이름·관리자·가린 이름(일*과)이면 제목 속 학교 이름, 그것도 없으면 빈 값.

    org_selector 로 기관 칸을 짚어 준 값은 사람 이름 검사를 하지 않는다 (동 이름 '괘법동'·'금곡동'이 이름처럼 보임)."""
    org = re.sub(r"^ou=", "", raw)
    person = maybe_person and _PERSON.fullmatch(org) and not _ORG_END.search(org)
    if _NOT_ORG.match(org) or "*" in org or person:
        org = ""
    if not org:
        m = _SCHOOL.search(re.sub(r"(19|20)\d{2}\s*(학년도|년도|년)", " ", title))
        org = m.group(0) if m and m.group(0) not in _GENERIC_SCHOOLS else ""
    return org


def _pick_rows(soup: BeautifulSoup, row_selector: str | None) -> tuple[list[Tag], list[str]]:
    if row_selector:
        rows = soup.select(row_selector)
        table = rows[0].find_parent("table") if rows else None
    else:
        best, best_rows = None, []
        for table in soup.find_all("table"):
            if table.find("table"):  # 레이아웃용 바깥 표는 건너뜀
                continue
            rows = [
                tr for tr in table.find_all("tr")
                if tr.find("td") and (tr.find("a") or _submit_title(tr) or _onclick_cells(tr))
            ]
            if len(rows) > len(best_rows):
                best, best_rows = table, rows
        table, rows = best, best_rows
    headers: list[str] = []
    if table is not None:
        # 머리글은 th 만 있는 첫 행 ('전체게시물: n개' 같은 요약 행은 건너뜀)
        head_row = next((tr for tr in table.find_all("tr") if tr.find("th") and not tr.find("td")), None)
        if head_row is None:  # 머리글을 td 로 쓴 옛 게시판 (새올 옛 화면 등): '제목' 칸이 있는 링크 없는 행
            head_row = next(
                (
                    tr for tr in table.find_all("tr")
                    if not tr.find("a") and not _onclick_cells(tr)
                    and any(re.fullmatch(r"제\s*목", _clean(td.get_text())) for td in tr.find_all("td"))
                ),
                None,
            )
        if head_row is not None:
            headers = [_clean(th.get_text()) for th in head_row.find_all(["th", "td"])]
    return rows, headers


def _onclick_cells(tr: Tag) -> list[Tag]:
    """링크 없이 칸(td)을 누르면 상세로 가는 행의 칸들 (영도구 새올: <td onclick="searchDetail('36478')">)."""
    return [td for td in tr.find_all("td", recursive=False) if td.get("onclick")]


def _submit_title(tag: Tag) -> Tag | None:
    """제목이 링크 대신 폼 제출 버튼(<input type=submit value="제목">)인 게시판."""
    for inp in tag.find_all("input"):
        if (inp.get("type") or "").lower() == "submit" and len(_clean(inp.get("value"))) >= 2:
            return inp
    return None


def _form_get_url(form: Tag, base_url: str) -> str:
    params = {
        i.get("name"): i.get("value", "")
        for i in form.find_all("input")
        if i.get("name") and i.get("name") != "_csrf" and (i.get("type") or "").lower() != "submit"
    }
    action = urljoin(base_url, form.get("action") or base_url)
    return f"{stable_key(action) if ';jsessionid' in action.lower() else action}?{urlencode(params)}"


def _column_index(headers: list[str]) -> dict[str, int]:
    index: dict[str, int] = {}
    for role, pattern in _HEADER_MAP.items():
        for i, h in enumerate(headers):
            if re.search(pattern, h) and i not in index.values():
                index[role] = i
                break
    return index


def _js_args(code: str) -> list[str]:
    m = _JS_CALL.search(code or "")
    if not m:
        return []
    return [a if a else n for a, n in _JS_ARG.findall(m.group(2))]


def _pick_key(args: list[str]) -> str:
    """JS 인자 중 게시글 번호로 보이는 값 (boardView('employ','207','') → '207').

    숫자만인 인자가 여럿이면 가장 긴 것 (fn_apmView('020', '303834') → '303834', '020' 은 구분 코드).
    """
    digits = [a for a in args if re.fullmatch(r"\d+", a)]
    if digits:
        return max(digits, key=len)
    for a in args:
        if re.search(r"\d{3,}", a):
            return a
    return next((a for a in args if a), "")


def _form_url(soup: BeautifulSoup, onclick: str, base_url: str) -> tuple[str, str] | None:
    """onclick="document.getElementById('X').submit()" → 폼 action + hidden 값으로 GET 주소."""
    m = re.search(r"""getElementById\(\s*['"]([^'"]+)['"]\s*\)\s*\.submit""", onclick or "")
    if not m:
        m = re.search(r"""document\.(\w+)\.submit""", onclick or "")
    if not m:
        return None
    form = soup.find("form", id=m.group(1)) or soup.find("form", attrs={"name": m.group(1)})
    if form is None:
        return None
    params = {
        i.get("name"): i.get("value", "")
        for i in form.find_all("input")
        if i.get("name") and i.get("name") != "_csrf" and i.get("value")
    }
    action = urljoin(base_url, form.get("action") or base_url)
    return f"{action}?{urlencode(params)}", m.group(1)


def parse_board(html: bytes | str, base_url: str, opts: dict, today: date) -> list[BoardRow]:
    if opts.get("encoding") and isinstance(html, bytes):
        html = html.decode(opts["encoding"], errors="replace")
    soup = BeautifulSoup(html, "lxml")
    base_tag = soup.find("base", href=True)
    if opts.get("link_base"):
        base_url = opts["link_base"]
    elif base_tag is not None:
        base_url = urljoin(base_url, base_tag["href"])
    rows, headers = _pick_rows(soup, opts.get("row_selector"))
    col = _column_index(headers)
    out: list[BoardRow] = []
    must = opts.get("row_must_contain")
    for tr in rows:
        if must and must not in tr.get_text():
            continue
        tds = tr.find_all("td")
        aligned = bool(headers) and len(tds) == len(headers)
        title_td = tds[col["title"]] if aligned and "title" in col else None
        anchors = (title_td or tr).find_all("a")
        anchor = max(anchors, key=lambda a: len(_clean(a.get_text())), default=None)
        titled = tr.select_one(opts["title_selector"].partition("@")[0]) if opts.get("title_selector") else None
        if titled is not None and (titled.name == "a" or titled.find("a")):
            anchor = titled if titled.name == "a" else titled.find("a")  # 제목 요소의 링크 (행이 겹쳐 읽히는 깨진 표)
        submit = _submit_title(title_td or tr) if anchor is None or len(_clean(anchor.get_text())) < 2 else None
        if submit is not None and submit.find_parent("form") is not None:
            title = _clean(submit.get("value"))
            url = _form_get_url(submit.find_parent("form"), base_url)
            key_param = opts.get("key_param")
            values = parse_qs(urlsplit(url).query).get(key_param) if key_param else None
            key, detail_ok = (values[0] if values else url), True
        elif anchor is None and _onclick_cells(tr):
            # 제목 칸(없으면 글자가 가장 긴 칸)의 onclick 으로 상세 주소를 만든다
            cells = _onclick_cells(tr)
            cell = title_td if title_td in cells else max(cells, key=lambda td: len(_clean(td.get_text())))
            title = _clean(cell.get_text(" "))
            url, key, detail_ok = _resolve_link(soup, cell, tr, base_url, opts)
        elif anchor is not None:
            title = _clean(anchor.get_text())
            full = _clean(anchor.get("title"))
            if len(title) < 2 or (title.endswith(("..", "…")) and full.startswith(title.rstrip(".… "))):
                title = full  # 목록 제목이 '..' 로 잘리고 title 속성에 전체 제목 (남구 동 공지)
            if len(title) < 2:
                # <a href="…"/>제목</a> 처럼 링크가 비고 제목은 칸에만 있는 경우 (잡알리오)
                title = _clean((title_td or anchor.parent).get_text(" "))
            url, key, detail_ok = _resolve_link(soup, anchor, tr, base_url, opts)
        elif (opts.get("link_attr") and tr.get(opts["link_attr"])) or _LOCATION_HREF.search(tr.get("onclick") or ""):
            # 링크 없이 행에 주소를 단 목록 (<tr class="clickable-row" data-href="/board/notice/read/68">,
            # 부산외대 평생교육원 <tr onclick="window.location='/community_notice_detail/35'">)
            title = _clean((title_td or tr).get_text(" "))
            url, key, detail_ok = _resolve_link(soup, tr, tr, base_url, opts)
        else:
            continue
        if opts.get("key_pattern"):
            m = re.search(opts["key_pattern"], url)
            key = m.group(1) if m else key
        key = _select_text(tr, opts.get("key_selector")) or key
        picked = _select_text(tr, opts.get("title_selector"))
        if picked:
            title = picked
        title = re.sub(r"\s*(새글|NEW|new|첨부파일|파일첨부)$", "", title)
        if len(title) < 2 or re.fullmatch(r"\[\d+\]", title):  # '[10]': 표 안에 든 쪽 번호 줄
            continue

        def cell(role: str) -> str:
            if not (aligned and role in col):
                return ""
            text = _clean(tds[col[role]].get_text(" "))
            # 모바일용으로 칸마다 숨겨 둔 머리글 (<em class="mTit">작성자</em> 가람중학교)
            label = headers[col[role]]
            return text[len(label):].strip() if label and text.startswith(label + " ") else text

        posted = _list_date(cell("posted"), today)
        if posted is None:
            for td in tds:
                text = _visible_text(td)  # 숨겨 둔 본문 미리보기 속 면접일은 게시일이 아님 (동부산아동보호전문기관)
                if td is not title_td and has_full_date(text):
                    posted = parse_date(text, today)
                    break
        deadline_text = cell("deadline")
        deadline = extract_deadline(deadline_text, today) or (
            parse_date(deadline_text, today) if deadline_text else None
        )
        deadline = deadline or extract_deadline(title, today)
        date_text = _select_text(tr, opts.get("date_selector"))
        if date_text:
            posted = _list_date(date_text, today) or posted  # '09-16' 처럼 연도 없는 날짜도
            if re.search(r"[~∼～]", date_text):
                deadline = extract_deadline(date_text, today) or deadline
        picked_org = _select_text(tr, opts.get("org_selector"))
        if picked_org and title.startswith(picked_org + " ") and len(title) > len(picked_org) + 5:
            title = title[len(picked_org) + 1:]  # 제목 칸 안에 기관 이름이 먼저 나오는 목록 (청소년활동진흥센터 채용정보)
        org = _org_name(picked_org or cell("org"), title, maybe_person=not picked_org)
        if opts.get("title_org_pattern") and not picked_org:
            m = re.search(opts["title_org_pattern"], title)
            org = m.group(1).strip() if m else org
        district = _select_text(tr, opts.get("district_selector")) or cell("district")
        out.append(BoardRow(title, url, key, posted, deadline, org, detail_ok, cell("label"), district))
    return out


def _select_text(row: Tag, selector: str | None) -> str:
    """행 안 요소의 글자. 'li.time@title' 처럼 @속성 을 붙이면 그 속성 값 (화면에는 '2일전', 속성에 날짜)."""
    if not selector:
        return ""
    selector, _, attr = selector.partition("@")
    el = row.select_one(selector)
    if el is None:
        return ""
    return _clean(str(el.get(attr) or "")) if attr else _clean(el.get_text(" "))


def _hidden(el: Tag) -> bool:
    return "display:none" in re.sub(r"\s", "", el.get("style") or "")


def _visible_text(cell: Tag) -> str:
    """칸의 글자 중 style="display:none" 으로 숨긴 요소 안의 글자는 뺀다."""
    return " ".join(
        s for s in cell.find_all(string=True)
        if not any(_hidden(p) for p in s.parents if p is not cell and isinstance(p, Tag))
    )


def _resolve_link(soup, anchor: Tag, tr: Tag, base_url: str, opts: dict) -> tuple[str, str, bool]:
    href = (anchor.get("href") or "").strip()
    onclick = anchor.get("onclick") or tr.get("onclick") or ""
    key_param = opts.get("key_param")
    template = opts.get("link_template")

    def key_from(url: str, fallback: str) -> str:
        if key_param:
            values = parse_qs(urlsplit(url).query).get(key_param)
            return values[0] if values else fallback
        return fallback

    attr = opts.get("link_attr")
    if attr and (anchor.get(attr) or tr.get(attr)):
        # 링크에 없으면 행의 속성 (<tr class="data-cont" data-idx="202"><a class="act_view" href="#">)
        value = str(anchor.get(attr) or tr.get(attr)).strip()
        url = template.format(value) if template else urljoin(base_url, value)
        return url, key_from(url, value), True

    # onclick="location.href='/p41.php?md=V&idx=22387'" (금곡·사상·구덕 청소년수련관): 주소를 그대로 쓴다
    m = _LOCATION_HREF.search(onclick)
    if m and not (href and not href.lower().startswith("javascript") and not href.startswith("#")):
        url = urljoin(base_url, m.group(1))
        return url, key_from(url, stable_key(url)), True

    # link_template 이 있고 onclick 에 인자가 있으면 href 보다 우선
    # (남구 평생학습: href="/edu/board/eduBoard/view.do" + onclick="goBoardArticle('534458')")
    onclick_args = _js_args(onclick) if onclick else []
    if template and onclick_args:
        try:
            url = template.format(*onclick_args)
            return url, key_from(url, _pick_key(onclick_args)), True
        except (IndexError, KeyError):
            pass

    if href and not href.lower().startswith("javascript") and not href.startswith("#"):
        url = urljoin(base_url, href)
        key = stable_key(url)
        if key_param:
            values = parse_qs(urlsplit(url).query).get(key_param)
            key = values[0] if values else url
        return url, key, True

    code = onclick if onclick else href
    if opts.get("form_link", True):
        form = _form_url(soup, code, base_url)
        if form:
            url, form_id = form
            key = form_id
            if key_param:
                values = parse_qs(urlsplit(url).query).get(key_param)
                key = values[0] if values else form_id
            return url, key, True

    args = _js_args(code)
    if template and args:
        try:
            url = template.format(*args)
            return url, key_from(url, _pick_key(args)), True
        except (IndexError, KeyError):
            pass
    title = _clean(anchor.get_text())
    return base_url, (_pick_key(args) or title), False
