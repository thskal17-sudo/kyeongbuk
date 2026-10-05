"""게시판 목록 파서 회귀 시험 — 부산판에서 가져온 실제 화면(tests/fixtures/busan_*.html, 2026-09-29 GitHub 러너에서 받아 줄인 것).

경북판도 같은 파서(collectors/board.py)를 쓰므로, 여러 게시판 형태를 그대로 읽는지 여기서 확인한다.
게시판 옵션은 부산판 sources.yaml 사본(tests/fixtures/busan_config/sources.yaml)을 쓴다.
"""
from datetime import date
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from gyeongbuk_jobs.classify import categorize, judge
from gyeongbuk_jobs.collectors.board import BoardCollector, _list_date, _org_name, parse_board, stable_key
from gyeongbuk_jobs.config import load_settings, source_rules

TODAY = date(2026, 9, 29)
SOURCES = {s.id: s for s in load_settings(Path(__file__).resolve().parent / "fixtures" / "busan_config").sources}


def rows_of(fixture_bytes, source_id, fixture, page_url=None):
    src = SOURCES[source_id]
    return parse_board(fixture_bytes(fixture), page_url or src.url, src.options, TODAY)


def test_pen_board_data_id_links_and_hidden_labels(fixture_bytes):
    # 부산교육청 학교인력채용: <a class="nttInfoBtn" data-id="1180893" href="javascript:">, 칸마다 <em class="mTit">작성자</em>
    rows = rows_of(fixture_bytes, "pen_school_hire", "busan_pen_hire.html")
    assert [r.key for r in rows] == ["1180895", "1180893", "1180889", "1180887"]
    r = rows[1]
    assert r.title == "2026학년도 가람중학교 문화예술교육 강사 채용 공고"  # 숨은 '새글' 표시는 뺌
    assert r.url == "https://www.pen.go.kr/main/na/ntt/selectNttInfo.do?mi=30367&bbsId=2364&nttSn=1180893"
    assert r.org == "가람중학교"  # 작성자 칸 'ou=가람중학교'
    assert r.posted == date(2026, 9, 29) and r.deadline == date(2026, 10, 7)  # 접수기간 2026/09/29 ~ 2026/10/07
    # 작성자가 담당 교사 이름이면 제목 속 학교 이름을 기관명으로
    assert rows[0].org == "브니엘고등학교"
    assert all(r.detail_ok for r in rows)


def test_pen_board_keyword_filter(fixture_bytes, rules):
    rows = rows_of(fixture_bytes, "pen_school_hire", "busan_pen_hire.html")
    verdicts = {r.title: judge(r.title, rules, True, r.label) for r in rows}
    assert verdicts["2026학년도 가람중학교 문화예술교육 강사 채용 공고"] == "모집중"
    # 조리실무사 결과·통학차량 도우미·기간제교사는 강사 공고가 아님
    assert sum(v == "모집중" for v in verdicts.values()) == 1


def test_afterschool_private_board(fixture_bytes):
    # 부산늘봄지원센터 개인위탁 모집공고: 작성자 칸이 학교 이름, 마감일 칸이 따로 있음
    rows = rows_of(fixture_bytes, "afterschool_private", "busan_afterschool_private.html")
    assert [(r.org, r.posted, r.deadline) for r in rows] == [
        ("구남초등학교", date(2026, 9, 4), date(2026, 9, 10)),
        ("남천초등학교", date(2026, 9, 3), date(2026, 9, 9)),
        ("장림여자중학교", date(2026, 9, 3), date(2026, 9, 4)),
    ]
    assert rows[1].url.endswith("selectNttInfo.do?mi=14360&bbsId=4177&nttSn=1014630")
    assert rows[1].key == "1014630"


def test_eminwon_list_with_detail_template(fixture_bytes):
    # 부산 서구 새올 채용공고: <a href="#" onclick="searchDetail('36862')">
    rows = rows_of(fixture_bytes, "seogu_eminwon", "busan_eminwon_seogu.html")
    assert [r.key for r in rows] == ["36862", "36859", "36852"]
    query = parse_qs(urlsplit(rows[0].url).query)
    assert urlsplit(rows[0].url).netloc == "eminwon.bsseogu.go.kr"
    assert query["method"] == ["selectOfrNotAncmt"] and query["not_ancmt_mgt_no"] == ["36862"]
    assert rows[0].org == "의회사무과" and rows[0].posted == date(2026, 9, 29)


def test_eminwon_old_screen_with_cell_onclick(fixture_bytes):
    # 영도구 새올 옛 화면: 제목에 링크가 없고 <td onclick="javaScript:searchDetail('36478')">, 머리글도 td
    rows = rows_of(fixture_bytes, "yeongdo_eminwon", "busan_eminwon_yeongdo.html")
    assert [r.key for r in rows] == ["36478", "36477", "36463"]
    r = rows[1]
    assert r.title == "2026년 하반기 산림병해충예찰방제단 채용 재공고"  # 고시공고번호 칸이 아니라 제목 칸
    assert r.org == "경제산업과" and r.posted == date(2026, 9, 24)
    assert "not_ancmt_mgt_no=36477" in r.url and r.detail_ok


def test_facility_corp_js_view_links(fixture_bytes):
    # 부산남구시설관리공단: fn_go_view(297) 은 목록 폼을 view.do 로 제출 → 같은 값을 GET 으로
    rows = rows_of(fixture_bytes, "bnfmc_hire", "busan_bnfmc.html")
    r = next(r for r in rows if r.title == "2026년 제4회 시간강사 채용공고")
    assert r.url == "https://www.bnfmc.or.kr/portal/gosiInfo/view.do?mId=0404000000&idx=297"
    assert r.key == "297" and r.posted == date(2026, 6, 11)


def test_city_board_key_ignores_search_period(fixture_bytes):
    # 부산시청 게시판 링크에는 오늘 날짜로 바뀌는 검색 기간(srchBeginDt·srchEndDt)이 붙는다 → 글 식별값에서 뺀다
    rows = rows_of(fixture_bytes, "city_stadium_notice", "busan_city_stadium.html")
    assert rows and all("srch" not in r.key for r in rows)
    assert rows[0].key == "https://www.busan.go.kr/stadium/sfnotice/1756178"
    tomorrow = stable_key(rows[0].url.replace("srchBeginDt=2025-09-29", "srchBeginDt=2025-09-30"))
    assert tomorrow == rows[0].key


def test_source_include_narrows_keywords(rules):
    # 체육시설관리사업소 공지에는 '수영강습 접수 안내' 가 많다 → 이 게시판은 강사·지도자 등만 포함 키워드로
    src = SOURCES["city_stadium_notice"]
    narrow = source_rules(rules, src)
    assert judge("[사직실내수영장] 2026년 10월 수영강습 현장접수 인원안내", rules, True) == "모집중"
    assert judge("[사직실내수영장] 2026년 10월 수영강습 현장접수 인원안내", narrow, True) is None
    assert judge("[사직실내수영장] 2026년 수영강사(프리랜서) 모집 공고", narrow, True) == "모집중"
    assert source_rules(rules, SOURCES["pen_school_hire"]) is rules


def test_list_board_with_selectors(fixture_bytes):
    # 부산일자리정보망 공공채용: 표가 아닌 <ul class="emif-lst"><li><a onclick="show('288592')"> 목록
    rows = rows_of(fixture_bytes, "busanjob_public", "busan_busanjob_public.html")
    r = rows[0]
    assert r.title == "(제2026-8호) 한국보건복지인재원 신규직원(일반공무직_장애) 채용 공고"  # 링크 안의 날짜·기관은 빼고
    assert r.org == "한국보건복지인재원"
    assert (r.posted, r.deadline) == (date(2026, 9, 28), date(2026, 10, 12))  # '2026-09-28 ~ 2026-10-12'
    assert r.url == "https://www.busanjob.net/view.do?no=1309&pgMode=show&id=288592" and r.key == "288592"


@pytest.mark.parametrize(
    "raw, title, expected",
    [
        ("ou=가람중학교", "", "가람중학교"),
        ("최희상", "2026학년도 브니엘고등학교 조리실무사 채용", "브니엘고등학교"),
        ("이승희", "2026학년도 2학기 금양중학교 시간강사(도덕윤리) 채용 공고", "금양중학교"),
        ("김예솔", "한문 기간제교사 채용 공고", ""),
        ("체육진흥과", "", "체육진흥과"),  # 부서 이름은 그대로
        ("서구청", "", "서구청"),
        ("일*과", "", ""),  # 가린 이름
        ("관리자", "부산정관늘봄전용학교 강사 모집", "부산정관늘봄전용학교"),
        ("문화의집관리자", "", ""),  # 관리자 계정 이름
        ("인사담당자", "", ""),
        ("분관 과장", "", ""),  # 직위
        ("체육진흥과", "", "체육진흥과"),  # '…과'(부서)는 기관명
        ("", "[모집] 부산진구통합방과후학교 안전도우미 인력 모집 공고", ""),  # 방과후학교는 사업 이름
        ("", "2026학년도 우암초등학교 방과후학교 강사 모집", "우암초등학교"),
        ("", "2026년 학교 밖 청소년 고등학교 검정고시 합격축하금 지원 사업 안내", ""),  # 이름 없는 '고등학교'
        ("", "2026년 사상구학교밖청소년지원센터 신규 학교밖청소년 모집", ""),  # '학교밖'은 학교 이름이 아님
        # 경북교육청 구인 게시판 '기관별' 칸은 분류 값이라 기관명이 아님 → 제목 속 학교 이름
        ("학교", "2026학년도 순심여자고등학교 조리원 채용 공고", "순심여자고등학교"),
        ("지역교육청", "지방공무원(보건직) 결원 대체인력 채용 공고", ""),
    ],
)
def test_org_name(raw, title, expected):
    assert _org_name(raw, title) == expected


def test_sources_yaml_is_consistent():
    from gyeongbuk_jobs.collectors import COLLECTORS

    for src in SOURCES.values():
        assert src.collector in COLLECTORS, src.id
        assert src.enabled or src.options.get("blocked"), f"{src.id}: 끈 소스는 blocked 에 까닭을 적는다"
        assert not isinstance(src.options.get("key_param", ""), bool), f"{src.id}: key_param 에 no 를 쓰면 따옴표로"
        template = src.options.get("link_template")
        if template:
            template.format(*["1"] * 8)  # 틀의 {n} 이 모두 채워지는지


def test_bukgu_jobs_board(fixture_bytes):
    # 북구청 일자리정보: 구청 채용공고 게시판, '접수기간' 칸에서 마감일
    rows = rows_of(fixture_bytes, "bukgu_hire", "busan_bukgu_jobs.html")
    r = rows[0]
    assert r.title == "2027년도 환경관리원 공개채용계획 변경 공고"
    assert r.key == "1108008" and r.org == "자원순환과"
    assert (r.posted, r.deadline) == (date(2026, 9, 28), date(2026, 10, 8))
    # 목록 제목은 '..' 로 잘리지만 링크의 title 속성에 전체 제목이 있다
    assert rows[1].title == "2026년 제4단계 공공근로사업 민생지킴이 분야 참여자 모집 공고"


def test_gangseo_gosi_all_notices(fixture_bytes):
    # 강서구 새올 고시공고 전체: 채용공고(05)가 비어 있어 모집 공고가 섞인 고시공고를 키워드로 거른다
    rows = rows_of(fixture_bytes, "gangseo_gosi", "busan_eminwon_gangseo_gosi.html")
    assert [r.key for r in rows] == ["41291", "41289", "41284"]
    assert "not_ancmt_mgt_no=41289" in rows[1].url and urlsplit(rows[1].url).netloc == "eminwon.bsgangseo.go.kr"
    assert rows[1].org == "안전관리과" and rows[1].posted == date(2026, 9, 29)


def test_women_center_aspx_board(fixture_bytes):
    # 부산진·동래·사하 여성인력개발센터 공통 게시판: sub1_view.aspx?b=글번호
    rows = rows_of(fixture_bytes, "bswoman_notice", "busan_bswoman_notice.html")
    r = rows[0]
    assert r.title == "[채용공고] 부산진여성새로일하기센터 취업상담사 모집공고(긴급)"
    assert r.key == "855" and r.posted == date(2026, 9, 28)
    assert r.url == "https://www.bswoman.or.kr/sub4/sub1_view.aspx?b=855&p=0&cdt=&txt="


def test_women_center_list_board(fixture_bytes):
    # 해운대여성인력개발센터: <ul class="bbsList"><li> 목록, 날짜는 '26.09.04', 글 주소는 zipEncode 로 감쌈
    rows = rows_of(fixture_bytes, "hwcenter_notice", "busan_hwcenter_notice.html")
    assert [r.posted for r in rows] == [date(2026, 9, 4), date(2026, 6, 15), date(2026, 4, 24)]
    assert rows[0].title == "★교육비 전액 지원★ 홈케어(정리수납2급) 마스터 양성과정 교육생 모집"
    assert all(r.url.startswith("https://www.hwcenter.or.kr/SW_bbs/notice/view.php?zipEncode=") for r in rows)
    assert len({r.key for r in rows}) == 3


def test_women_center_board_with_private_posts(fixture_bytes, rules):
    # 동구여성인력개발센터: bbs_uid 글번호, '비밀글 입니다.' 줄은 링크가 없어 강사 공고로 잡히지 않는다
    rows = rows_of(fixture_bytes, "donggu_woman_notice", "busan_ewoman_notice.html")
    assert [r.key for r in rows[:2]] == ["199", "187"]
    assert rows[0].title == "(동구새일) 직업상담사 채용공고(직업상담사, 육아휴직대체근무자)"
    assert judge(rows[2].title, rules, True) is None


def test_youth_hire_list_strips_org_from_title(fixture_bytes, rules):
    # 부산청소년활동진흥센터 채용정보: <li><span class="tit"><span>기관</span> 제목</span>, 바로가기는 u_re('글번호','공고 주소')
    rows = rows_of(fixture_bytes, "busanyouth_hire", "busan_busanyouth_hire.html")
    r = rows[2]
    assert r.title == "2026년 해운대청소년수련관 청소년활동팀 팀원 채용 공고" and r.org == "해운대청소년수련관"
    assert r.key == "234760" and r.posted == date(2026, 9, 8)
    assert r.url.startswith("https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?wantedAuthNo=K130112609080079")
    assert rows[0].org == "동래구청소년지원센터꿈드림"
    # 직원 채용은 청소년 기관용 포함 키워드(강사·코치·활동지도자 등)에 걸리지 않는다
    narrow = source_rules(rules, SOURCES["busanyouth_hire"])
    assert all(judge(r.title, narrow, True) is None for r in rows)


def test_youth_center_onclick_board(fixture_bytes, rules):
    # 사상구청소년센터(금곡·구덕과 같은 제작사): 제목 칸 <td onclick="location.href='/sb55.php?md=V&idx=…'">,
    # 위쪽 메뉴 표도 td onclick 이라 row_selector 로 게시판 줄만 고른다
    rows = rows_of(fixture_bytes, "yzzang_hire", "busan_yzzang_hire.html")
    assert [r.key for r in rows] == ["1810", "1784", "1768", "1757"]
    r = rows[2]
    assert r.title == "긴급) 주말방과후아카데미 활동지도자 채용 공고" and r.posted == date(2026, 8, 4)
    assert r.url.startswith("https://www.yzzang.com/sb55.php?md=V&idx=1768")
    narrow = source_rules(rules, SOURCES["yzzang_hire"])
    verdicts = [judge(r.title, narrow, True) for r in rows]
    assert verdicts == [None, None, "모집중", None]  # 아르바이트·학교밖센터 직원·최종합격자 안내는 거름
    assert judge(rows[1].title, narrow, True, keep_results=True) == "결과공고"


def test_youth_notice_keywords(rules):
    narrow = source_rules(rules, SOURCES["busanyouth_notice"])
    assert judge("[모집]2026년 청소년자원봉사 신규 교육강사", narrow, True) == "모집중"
    assert judge("주말형청소년방과후아카데미 음악(기타/베이스/드럼), 뉴스포츠 강사 모집 공고", narrow, True) == "모집중"
    assert judge("2026 청소년방과후아카데미 신규 청소년 모집", narrow, True) is None
    assert judge("청소년지도사 채용 공고", narrow, True) is None
    assert judge("방과후과정 지원 자원봉사자 모집", rules, True) is None
    # 멘토: 꿈드림 검정고시 학습멘토처럼 가르치는 사람을 뽑는 글은 남기고, 멘토링에 참가할 청소년 모집은 거름
    assert judge("[꿈드림] 검정고시대비반 '스마트교실' 멘토 모집", narrow, True) == "모집중"
    assert judge("수영구학교밖청소년지원센터 검정고시 학습멘토 모집", narrow, True) == "모집중"
    assert judge("2026년 영도구학교밖청소년지원센터 꿈드림 멘토단 모집(모집완료)", narrow, True) is None
    assert judge("[홍보] 2026 청소년 방과후 아카데미 통통한 멘토링 참가 신청", narrow, True) is None
    assert judge("2026 청소년 멘토링 프로그램 참여자 모집", narrow, True) is None


def test_xe_board_same_key_for_both_link_forms(fixture_bytes, rules):
    # 부산진구 부전 청소년센터(XE): 공지 줄은 /xe/sub7_01/24564, 일반 줄은 index.php?…&document_srl=24556
    # → key_pattern 으로 글번호만 식별값으로 (공지에서 내려와도 같은 글)
    rows = rows_of(fixture_bytes, "bujeon_youth_notice", "busan_teenstory_notice.html")
    assert [r.key for r in rows] == ["24564", "24556", "24288", "24273", "24153"]
    assert rows[0].url == "https://teenstory.kr/xe/sub7_01/24564" and rows[0].org == ""  # '통합방과후학교'는 기관명 아님
    assert rows[4].title == "청소년방과후아카데미 강사 모집 공고(댄스)" and rows[4].posted == date(2026, 2, 11)
    narrow = source_rules(rules, SOURCES["bujeon_youth_notice"])
    verdicts = [judge(r.title, narrow, True) for r in rows]
    assert verdicts == [None, None, None, None, "모집중"]  # 안전도우미·직원 합격자·'[마감]' 강사 공고는 거름


def test_onclick_board_with_pc_and_mobile_lists(fixture_bytes):
    # 중구청소년문화의집: 같은 목록이 <div id="only_pc">·<div id="only_mobile"> 에 두 번 → PC 쪽만 (날짜 칸이 있음)
    rows = rows_of(fixture_bytes, "purun1318_notice", "busan_purun1318_notice.html")
    assert [(r.key, r.posted) for r in rows] == [("1672", date(2026, 6, 30)), ("1647", date(2026, 4, 7))]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("09-03", date(2026, 9, 3)),
        ("11-18", date(2025, 11, 18)),  # 오늘(9/29)보다 뒤 → 작년 글
        ("09-29", date(2026, 9, 29)),
        ("2026-04-02", date(2026, 4, 2)),
        ("10:57", None),  # 오늘 글은 시각만
    ],
)
def test_list_date_without_year(text, expected):
    # 그누보드 기본 목록(남구청소년상담복지센터)은 날짜를 '09-03' 으로만 보여 준다
    assert _list_date(text, TODAY) == expected


def test_ajax_list_with_js_form_links(fixture_bytes, rules):
    # 해운대구청소년상담복지센터: 화면이 AJAX 로 불러오는 목록(mode=list_ok)을 바로 받고,
    # 제목 링크 onclick="view('270')" (GET 폼 제출) → link_template 로 mode=view&uid=270
    rows = rows_of(fixture_bytes, "udream_notice", "busan_udream_notice.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("267", date(2026, 9, 9)), ("270", date(2026, 9, 23)), ("258", date(2026, 1, 27)),
    ]
    assert rows[2].url == "http://u-dream.or.kr/04/01.php?mode=view&uid=258" and rows[2].detail_ok
    narrow = source_rules(rules, SOURCES["udream_notice"])
    assert [judge(r.title, narrow, True) for r in rows] == [None, None, "모집중"]  # '전문강사 모집 공고'만


def test_gnuboard_li_list(fixture_bytes):
    # 사하구청소년상담복지센터: 그누보드인데 표가 아닌 <li class="gw_tb_tr"> 목록
    rows = rows_of(fixture_bytes, "saha1388_notice", "busan_saha1388_notice.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("186", date(2026, 7, 24)), ("189", date(2026, 9, 2)), ("188", date(2026, 8, 31)),
    ]
    assert rows[1].title == "2026년 학교 밖 청소년 수학여행 지원사업 수의계약 내역 공개"


def test_child_center_hire_board_org_from_writer(fixture_bytes, rules):
    # 지역아동센터 부산지원단 인재채용: 작성자 칸이 공고를 올린 기관(○○지역아동센터·○○구청)
    rows = rows_of(fixture_bytes, "bro3c_hire", "busan_bro3c_hire.html")
    assert [(r.key, r.org) for r in rows] == [
        ("https://www.bro3c.org/5_4/74004", "부산 영도구"),
        ("https://www.bro3c.org/5_4/73998", "부곡지역아동센터"),
        ("https://www.bro3c.org/5_4/73989", "한나래지역아동센터"),
    ]
    narrow = source_rules(rules, SOURCES["bro3c_hire"])
    # 구청 아동복지교사·프로그램 강사는 받고, 돌봄 보조인력은 거름
    assert [judge(r.title, narrow, True) for r in rows] == ["모집중", None, "모집중"]
    assert judge("[부산 부산진구] 수지역아동센터 생활복지사 채용공고", narrow, True) is None


def test_child_center_national_board_filtered_to_busan(fixture_bytes, rules):
    # 아동권리보장원 구인게시판: 시도 '부산' 으로 거른 목록, fnDetail('17686') → GET 상세, 모집기간 칸에서 마감일
    rows = rows_of(fixture_bytes, "icare_busan_hire", "busan_icare_hire.html")
    assert [r.key for r in rows] == ["17686", "17662", "17607"]
    r = rows[0]
    assert r.url == (
        "https://www.icareinfo.go.kr/notice/jobOffer/jobOfferDetail.do?bbs_no=17686&menuNo=3001110&bbs_section_cd=job"
    )
    assert (r.posted, r.deadline) == (date(2026, 6, 10), date(2026, 6, 19))
    narrow = source_rules(rules, SOURCES["icare_busan_hire"])
    assert [judge(r.title, narrow, True) for r in rows] == ["모집중", None, "모집중"]  # 사회복지사 채용은 거름


def test_imweb_board_date_attr_and_title_org(fixture_bytes, rules):
    # 부산광역시사회복지협의회 취업정보(아임웹): 날짜 칸 글자는 '2일전' 이고 title 속성에 '2026-09-28 14:35',
    # 기관명은 제목 앞 [대괄호] 에서 (title_org_pattern)
    rows = rows_of(fixture_bytes, "bswin_job", "busan_bswin_job.html")
    assert [(r.key, r.posted, r.org) for r in rows] == [
        ("174853397", date(2026, 9, 28), "KRX국민행복재단"),
        ("174658524", date(2026, 9, 23), "송도사랑요양원"),
        ("173872331", date(2026, 9, 8), "늘봄실버요양센터"),
    ]
    narrow = source_rules(rules, SOURCES["bswin_job"])
    assert all(judge(r.title, narrow, True) is None for r in rows)  # 요양보호사·조리원 등은 거름 ('늘봄'실버요양센터 포함)
    assert judge("[운봉종합사회복지관] 수면요가테라피 강사 모집", narrow, True) == "모집중"


def test_sw_bbs_li_list_board(fixture_bytes):
    # 영도구노인복지관(SW_bbs 의 <li> 목록형): 제목 p.txt1 a, 날짜는 p.txt2 ('25.11.05 | 조회')
    rows = rows_of(fixture_bytes, "senior_yeongdo_notice", "busan_youngdosenior_notice.html")
    assert [r.posted for r in rows] == [date(2025, 11, 5), date(2026, 9, 21), date(2026, 9, 11)]
    assert rows[1].title == "[알림/분관] 2026년 4분기 노년사회화교육사업 사회교육 프로그램 추첨결과 알림"
    assert all("/SW_bbs/notice/view.php?zipEncode=" in r.url for r in rows) and len({r.key for r in rows}) == 3


def test_path_number_key_and_senior_center_keywords(fixture_bytes, rules):
    # 연제구노인복지관: 글 주소 /board/notice/detail/16177/page/1 → key_pattern 으로 글번호만
    rows = rows_of(fixture_bytes, "senior_yeonje_notice", "busan_yjsilver_notice.html")
    assert [(r.key, r.posted) for r in rows] == [("16181", date(2026, 9, 16)), ("16177", date(2026, 6, 1))]
    narrow = source_rules(rules, SOURCES["senior_yeonje_notice"])
    assert [judge(r.title, narrow, True) for r in rows] == [None, "모집중"]  # '우쿨렐레·밴드운동교실 강사 모집'


class _PageHttp:
    """목록 한 쪽만 돌려주는 가짜 Http (수집기 단계의 기관명 처리를 보려고)"""

    def __init__(self, content):
        self.content = content

    def get(self, url, **kw):
        return type("Resp", (), {"url": url, "content": self.content})()


def test_pen_library_notice_org_fixed_and_keywords(fixture_bytes, rules):
    # 교육청 도서관 공지 (시민도서관과 같은 <a data-id>): 작성자 칸은 '총무과'·'사하도서관' 같은 부서라서
    # 기관명은 늘 도서관 이름 (org_fixed)
    from gyeongbuk_jobs.collectors.board import BoardCollector

    src = SOURCES["lib_saha"]
    rows = rows_of(fixture_bytes, "lib_saha", "busan_sahalib_notice.html")
    assert [(r.key, r.posted, r.org) for r in rows] == [
        ("1039754", date(2026, 9, 29), "총무과"),
        ("1039439", date(2026, 9, 28), "총무과"),
        ("1038396", date(2026, 9, 19), "사하도서관"),
    ]
    assert rows[1].url == "https://home.pen.go.kr/sahalib/na/ntt/selectNttInfo.do?mi=12293&bbsId=3505&nttSn=1039439"
    items = BoardCollector(src, _PageHttp(fixture_bytes("busan_sahalib_notice.html")), TODAY).collect()
    assert {p.org_name for p in items} == {"부산광역시립사하도서관"}
    narrow = source_rules(rules, src)
    assert all(judge(r.title, narrow, True) is None for r in rows)  # '계약제교원 및 자원봉사자 인력풀' 은 거름
    assert judge("2027년 독서문화프로그램 강사 모집 공고", narrow, True) == "모집중"
    assert judge("2026년 하반기 초등 원어민 영어교실 수강생 모집", narrow, True) is None
    assert judge("늘봄학교 연계 도서관 프로그램 운영 안내", narrow, True) is None  # 도서관은 '늘봄'·'방과후' 로 받지 않음


def test_gijang_library_shared_board(fixture_bytes):
    # 기장군 도서관 8곳이 나눠 쓰는 게시판: goTo.view('list', 글번호, ptIdx, mId), 분류 칸('공통'·'고촌어울림')은 구분값
    rows = rows_of(fixture_bytes, "lib_gj_gochon", "busan_gijang_library_notice.html")
    assert [(r.key, r.label, r.posted) for r in rows] == [
        ("54022", "공통", date(2026, 9, 28)),
        ("54009", "고촌어울림", date(2026, 9, 22)),
        ("53983", "공통", date(2026, 9, 16)),
    ]
    assert rows[1].url == "https://library.gijang.go.kr/gochon/bbs/view.do?bIdx=54009&ptIdx=207&mId=0401000000"
    assert all(r.detail_ok for r in rows)


def test_library_boards_with_js_and_masked_writer(fixture_bytes):
    # 서구아미드림도서관: <a data-req-get-p-idx="379" onclick="yhLib.inline.post(this)">, 날짜 '2026-09-21(월)'
    rows = rows_of(fixture_bytes, "lib_seogu_ami", "busan_amlib_notice.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("379", date(2026, 9, 21)), ("378", date(2026, 9, 19)), ("377", date(2026, 9, 18)),
    ]
    assert rows[0].url == "https://www.bsseogu.go.kr/amlib/portal/board/post/view.do?idx=379&bcIdx=500&mid=0801000000"
    # 강서기적의도서관 (동래구 도서관과 같은 틀): 글번호는 bb_code, 작성자는 '강*기적의도*관' 처럼 가려짐
    rows = rows_of(fixture_bytes, "lib_gs_miracle", "busan_gmlib_notice.html")
    assert [r.key for r in rows] == ["70h40mv0n4d5c59", "70h50670n0213fc", "70h508z0mze43a5"]
    assert [r.org for r in rows] == ["", "", ""]
    assert rows[1].title.endswith("서류전형 합격…")  # 목록 제목이 잘려 있음


def test_yeongdo_library_li_list(fixture_bytes):
    # 영도도서관: 표가 아닌 <li> 목록 (제목 strong.t1, 본문 요약 span.t2 는 빼고, 작성일은 첫 span.t3)
    rows = rows_of(fixture_bytes, "lib_yeongdo", "busan_yeongdo_library_notice.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("334085", date(2026, 9, 27)), ("334017", date(2026, 9, 18)), ("333980", date(2026, 9, 15)),
    ]
    assert rows[0].title == "[공지] [영도도서관] 제 38회 영도도서관 인문학 기행 참가신청 안내"
    assert rows[0].url.startswith("https://www.yeongdo.go.kr/library/01349/01352/01354.web?gcode=1136&idx=334085&amode=view")


def test_welfare_center_hire_board_org_fixed_and_results(fixture_bytes, rules):
    # 운봉종합사회복지관 직원채용 (SW_bbs 표): 프로그램 강사 모집과 그 합격자 발표가 함께 올라옴
    from gyeongbuk_jobs.collectors.board import BoardCollector

    src = SOURCES["cw_unbong_hire"]
    rows = rows_of(fixture_bytes, "cw_unbong_hire", "busan_woonbong_hire.html")
    assert [r.posted for r in rows] == [date(2026, 9, 22), date(2026, 9, 21), date(2026, 9, 3), date(2026, 9, 3)]
    assert len({r.key for r in rows}) == 4 and all(r.detail_ok for r in rows)
    narrow = source_rules(rules, src)
    assert [judge(r.title, narrow, True, keep_results=True) for r in rows] == ["결과공고", None, "모집중", "모집중"]
    items = BoardCollector(src, _PageHttp(fixture_bytes("busan_woonbong_hire.html")), TODAY).collect()
    assert {p.org_name for p in items} == {"운봉종합사회복지관"}  # 작성자 칸은 '관리자'
    # 영진종합사회복지관은 모집이 끝나면 제목 앞에 '(완료)' 를 붙임
    assert judge("(완료)장수대학 노래교실 강사 구인 공고", narrow, True, keep_results=True) == "결과공고"
    assert judge("[완료]겟잇뷰티 강사 구인 공고", narrow, True, keep_results=True) == "결과공고"


def test_ajax_list_url_with_view_onclick(fixture_bytes):
    # 낙동종합사회복지관: 첫 화면은 빈 틀이고 목록은 /06/01.php?mode=list_ok (머리글이 td 인 표), 글은 view('1437')
    rows = rows_of(fixture_bytes, "cw_nakdong_notice", "busan_ndswc_notice.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("1437", date(2026, 1, 21)), ("1435", date(2026, 1, 8)), ("1161", date(2023, 6, 9)),
    ]
    assert rows[0].url == "https://www.ndswc.or.kr/06/01.php?mode=view&uid=1437"


def test_board_rows_made_of_th_cells(fixture_bytes, rules):
    # 와치종합사회복지관: 행의 칸이 <td> 가 아니라 <th class="board_title"> 등, 날짜 '26.04.09'
    rows = rows_of(fixture_bytes, "cw_wachi_notice", "busan_wachi_notice.html")
    assert [r.posted for r in rows] == [date(2026, 8, 5), date(2026, 7, 23), date(2026, 4, 9)]
    assert rows[2].title == "2026년 BMC행복나눔사업 스마트폰 교육 강사 채용 공고"
    assert all("/SW_bbs/view.php?zipEncode=" in r.url for r in rows) and len({r.key for r in rows}) == 3
    narrow = source_rules(rules, SOURCES["cw_wachi_notice"])
    assert [judge(r.title, narrow, True) for r in rows] == [None, None, "모집중"]


def test_broken_table_rows_use_title_link(fixture_bytes):
    # 해운대종합사회복지관: 행 태그가 <trf> 이고 닫히지 않아 뒤 행이 앞 행 안에 겹쳐 읽힘
    # → 행 바로 아래 칸만 보고, 링크도 제목 칸(title_selector)의 것을 쓴다
    rows = rows_of(fixture_bytes, "cw_haeundae_notice", "busan_haeundae_saem_notice.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("2869", date(2026, 9, 29)), ("2868", date(2026, 9, 23)), ("2855", date(2026, 9, 4)),
    ]
    assert rows[1].title == "[안내] 2026 대상자 욕구 및 만족도조사 진행"


def test_wrongly_declared_charset(fixture_bytes):
    # 반여종합사회복지관: utf-8 이라고 적고 EUC-KR 로 보내는 그누보드 → encoding: cp949, 날짜 칸은 '09-29'
    rows = rows_of(fixture_bytes, "cw_banyeo_notice", "busan_banyeo_notice.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("716", date(2026, 9, 29)), ("713", date(2026, 7, 28)), ("712", date(2026, 7, 10)),
    ]
    assert rows[2].title == "[채용] 정규직 선임사회복지사/사회복지사 채용 결과 공고"


def test_page_number_row_is_not_a_post():
    html = """<table><tr><th>번호</th><th>제목</th><th>작성일</th></tr>
    <tr><td>1</td><td><a href="view.php?no=1">한글 교실 강사 모집</a></td><td>26.09.01</td></tr>
    <tr><td colspan="3"><a href="list.php?page=10">[10]</a></td></tr></table>"""
    rows = parse_board(html, "https://example.or.kr/list.php", {}, TODAY)
    assert [r.title for r in rows] == ["한글 교실 강사 모집"]


def test_sports_center_li_board_with_month_day_dates(fixture_bytes, rules):
    # 수영구 국민체육센터 채용공고: <li class="row board-row"> 목록, 날짜 칸은 연도 없는 '09-16'
    rows = rows_of(fixture_bytes, "sports_suyeong_hire", "busan_sysports_recru.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("4343", date(2026, 9, 16)), ("4341", date(2026, 9, 15)), ("4333", date(2026, 9, 9)),
    ]
    assert rows[1].url == "https://sysports.or.kr/emSolution/post/4341"
    narrow = source_rules(rules, SOURCES["sports_suyeong_hire"])
    # 수영 지도자는 받고 안전요원 채용은 거름
    assert [judge(r.title, narrow, True) for r in rows] == [None, "모집중", None]


def test_sports_association_keywords(rules):
    narrow = source_rules(rules, SOURCES["assoc_saha_hire"])
    assert judge("2026년 부산광역시사하구체육회 신규(어르신(전담)생활체육지도자) 채용공고", narrow, True) == "모집중"
    assert judge("2026년 부산광역시수영구체육회 해달맞이생활체육교실 강사 채용 공고", narrow, True) == "모집중"
    assert judge("2025년도 부산광역시사하구체육회 생활체육지도자 대체근무자 서류 합격 공고", narrow, True,
                 keep_results=True) == "결과공고"
    assert judge("◎ 수영구 국민체육센터 안내데스크 기간제 채용공고", narrow, True) is None


def test_rows_linked_by_row_attribute(fixture_bytes):
    # 북구체육회 공지: 행에 <a> 가 없고 <tr class="clickable-row" data-href="/board/notice/read/68"> 로 연다
    rows = rows_of(fixture_bytes, "assoc_bukgu_notice", "busan_bbsc_notice.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("68", date(2026, 9, 21)), ("67", date(2026, 8, 26)), ("60", date(2026, 5, 7)),
    ]
    assert rows[0].title == "지방체육회장선거 제한 금지행위 등 안내"
    assert rows[0].url == "https://bbsc.kr/board/notice/read/68" and all(r.detail_ok for r in rows)


def test_swimming_pool_boards(fixture_bytes, rules):
    # 사상국민체육센터 채용공고 (삼락복합문화체육센터 포함): 글번호 ident, 강사 채용만 받고 행정직원 채용은 거름
    rows = rows_of(fixture_bytes, "pool_sasang_hire", "busan_ssnsc_hire.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("6264", date(2026, 9, 22)), ("6256", date(2026, 9, 16)), ("6186", date(2026, 8, 19)),
    ]
    narrow = source_rules(rules, SOURCES["pool_sasang_hire"])
    assert [judge(r.title, narrow, True) for r in rows] == ["모집중", None, "모집중"]
    assert judge("사직실내수영장 수영강습 접수 안내", narrow, True) is None  # 수영장 게시판은 '강습' 으로 받지 않음
    # 스포원 공지: 글번호 BOARD_SEQ 는 암호화된 값이지만 실행마다 같다
    rows = rows_of(fixture_bytes, "pool_spo1_notice", "busan_spo1_notice.html")
    assert [r.key for r in rows] == ["v4TQNyGcRoKZRf+TgKSThQ==", "W+QMlFZ_8XHN6CXb_4tKsQ==", "LYeEuZzlCKdnDP144p495g=="]
    assert rows[0].url.startswith("https://www.spo1.or.kr/bbs/list.do?cmd=view&CT_ID=NOTICE")


def test_cultural_center_row_attribute_with_dummy_link(fixture_bytes, rules):
    # 부산진문화원 공지: <tr class="data-cont" data-idx="195"> 안의 <a class="act_view" href="#"> → 행의 data-idx 로 상세 주소
    rows = rows_of(fixture_bytes, "culture_busanjin_notice", "busan_busanjin_cc_notice.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("195", date(2026, 5, 18)), ("194", date(2026, 5, 6)), ("202", date(2026, 9, 14)),
    ]
    assert rows[0].url == "http://busanjin.kccf.or.kr/board/notice.php?mode=view&idx=195"
    narrow = source_rules(rules, SOURCES["culture_busanjin_notice"])
    assert [judge(r.title, narrow, True) for r in rows] == ["모집중", "모집중", None]


def test_cultural_center_list_inside_layout_table(fixture_bytes):
    # 부산동구문화원 공지: 메뉴용 레이아웃 표가 목록보다 행이 많아서 row_selector 로 목록 줄만
    # (제목 칸 onclick="location.href='/sb51.php?md=V&idx=323…'")
    rows = rows_of(fixture_bytes, "culture_donggu_notice", "busan_bdgcc_notice.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("323", date(2026, 1, 2)), ("321", date(2025, 12, 5)), ("337", date(2026, 9, 1)),
    ]
    assert rows[0].title == "2026. 퓨전난타 강사모집"


def test_div_row_board(fixture_bytes):
    # 사하구 국민체육센터 공지: 표가 아닌 <div class="boardList"><a href="?action-value=…&action=read"> (머리글 줄은 링크가 없어 빠짐)
    rows = rows_of(fixture_bytes, "sports_saha_notice", "busan_sahaksports_notice.html")
    assert [r.posted for r in rows] == [date(2026, 4, 9), date(2025, 12, 9), date(2025, 6, 11)]
    assert rows[0].key == "ff7a23e7c1fd1162512ceb2e19a7b50b"
    assert rows[0].url.endswith("/saha/207?action-value=ff7a23e7c1fd1162512ceb2e19a7b50b&action=read")


def test_postback_board_keyed_by_title(fixture_bytes, rules):
    # 신라대 평생교육원: 제목 링크가 __doPostBack('…$ctl02$lnkSubject') 라 줄 위치만 담겨 새 글이 오면 밀린다
    # → 제목을 식별값으로 (key_selector), 링크는 목록. 맨 아래 쪽 번호 줄은 빠진다
    rows = rows_of(fixture_bytes, "univ_silla_notice", "busan_silla_lifelong.html")
    assert [(r.key, r.posted, r.detail_ok) for r in rows] == [
        ("2026년 4분기 각종변경신청 및 학습자등록·학점인정 신청 안내", date(2026, 9, 30), False),
        ("2026학년도 2학기 평생교육부 강좌 개설 희망자 모집 및 서류 제출 안내", date(2026, 8, 3), False),
    ]
    assert {r.url for r in rows} == {"https://soc.silla.ac.kr/Home/Sub04/NoticeBoard01.aspx"}
    narrow = source_rules(rules, SOURCES["univ_silla_notice"])
    assert [judge(r.title, narrow, True) for r in rows] == [None, "모집중"]


def test_row_onclick_window_location(fixture_bytes):
    # 부산외대 평생교육원: 행에 링크 없이 <tr onclick="window.location='/community_notice_detail/35'">
    rows = rows_of(fixture_bytes, "univ_bufs_notice", "busan_bufs_lifelong.html")
    assert [(r.key, r.posted) for r in rows] == [("35", date(2026, 9, 22)), ("34", date(2026, 7, 27))]
    assert rows[0].url == "https://lec.bufs.ac.kr/community_notice_detail/35" and rows[0].detail_ok
    assert rows[0].title == "[일반] 2026학년도 2학기 초등 통합방과후학교 프로그램 수강 안내"


def test_post_only_detail_uses_list_link(fixture_bytes):
    # 부산가톨릭대 평생교육원: fn_View('402','374','058000000000000','') 는 POST 로만 열려서 글 번호만 식별값으로 쓰고
    # 상세는 열지 않는다 (detail_get: false). 셋째 인자는 모든 글이 같은 값이라 식별값이 될 수 없다
    from gyeongbuk_jobs.collectors.board import BoardCollector

    src = SOURCES["univ_cup_notice"]
    rows = rows_of(fixture_bytes, "univ_cup_notice", "busan_cup_lifelong.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("374", date(2026, 6, 22)), ("368", date(2026, 1, 27)), ("367", date(2026, 1, 23)),
    ]
    assert rows[0].url == "https://edu.cup.ac.kr/organ/edu/front/board/List402.do?seq=374"
    items = BoardCollector(src, _PageHttp(fixture_bytes("busan_cup_lifelong.html")), TODAY).collect()
    assert [p.detail_url for p in items] == [None, None, None]
    assert {p.org_name for p in items} == {"부산가톨릭대학교 평생교육원"}


def test_dl_list_board_and_lifelong_keywords(fixture_bytes, rules):
    # 동의대 미래교육원: 표가 아닌 <dl> 목록, 날짜는 '학점은행제 / 2026.10.02'
    rows = rows_of(fixture_bytes, "univ_deu_notice", "busan_deu_lifelong.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("191388", date(2026, 10, 2)), ("191380", date(2026, 8, 6)), ("191233", date(2025, 1, 14)),
    ]
    narrow = source_rules(rules, SOURCES["univ_deu_notice"])
    # '파크골프 2급지도자(강사) 양성과정 모집안내(3기)' 는 강사가 될 사람을 모으는 과정
    assert [judge(r.title, narrow, True) for r in rows] == [None, None, None]
    assert judge("2026학년도 2학기 평생교육부 강좌 개설 희망자 모집", narrow, True) == "모집중"
    assert judge("2027학년도 1학기 신규 강좌 및 강사 모집", narrow, True) == "모집중"
    assert judge("[평생교육지원센터] 2025학년도 중독 예방 강사 양성 과정 모집", narrow, True) is None
    assert judge("2026년 하반기 시니어아카데미 교육생 모집", narrow, True) is None
    assert judge("파크골프 기초·실전 및 지도자 양성과정(오후반, 저녁반)", narrow, True) is None  # 대학은 '지도자' 로 받지 않음
    # 전체 규칙: '강사 양성' 과정 모집은 거르지만 양성과정 강사를 뽑는 글은 남긴다
    assert judge('부산형 영어교육 "영유아 영어강사 양성" 초급과정 모집 안내', rules, True) is None
    assert judge("요양보호사 양성과정 강사 모집", rules, True) == "모집중"


def test_list_page_sent_with_404_status():
    # 해양대 평생교육원: 목록을 다 보내면서 상태 코드만 404 → ok_status 에 있으면 그대로 읽는다
    import requests

    from gyeongbuk_jobs.collectors.board import BoardCollector

    class _Http404:
        def get(self, url, **kw):
            resp = requests.Response()
            resp.status_code, resp.url, resp._content = 404, url, b"<table></table>"
            raise requests.exceptions.HTTPError("404", response=resp)

    src = SOURCES["univ_kmou_notice"]
    assert BoardCollector(src, _Http404(), TODAY).fetch_page(1).status_code == 404
    with pytest.raises(requests.exceptions.HTTPError):
        BoardCollector(SOURCES["univ_bdu_notice"], _Http404(), TODAY).fetch_page(1)


def test_youth_support_center_board_title_without_icon_text(fixture_bytes, rules):
    # 청소년종합지원센터·청소년성문화센터 (bbs_shop): 제목 뒤 <i class="sp-ico file">file</i> 아이콘 글자를 빼고 <span> 만
    rows = rows_of(fixture_bytes, "youth_onestop_notice", "busan_onestop_notice.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("57134", date(2026, 1, 30)), ("57074", date(2026, 1, 29)), ("56254", date(2026, 1, 12)),
    ]
    assert rows[0].title == "[채용공고] 시간제상담원 회복조정단"
    assert rows[1].title == "부산광역시청소년종합지원센터 20주년 청소년 목소리 포럼 {청지개관}"
    assert rows[0].url.startswith("http://www.busanonestop.or.kr/bbs_shop/read.htm?") and rows[0].url.endswith("&idx=57134")
    narrow = source_rules(rules, SOURCES["youth_onestop_notice"])
    assert all(judge(r.title, narrow, True) is None for r in rows)  # 직원·상담원 채용은 거름
    assert judge("2027년 청소년 성교육 외부강사 모집 공고", narrow, True) == "모집중"


def test_disabled_center_js_view_form_link(fixture_bytes, rules):
    # 부산시각장애인복지관: 제목 링크 boardViewDo1(201512011, 20261001155552, 1, 1) → GET 폼 /boardView.do.
    # 폼의 숨은 값(leftMenuTitle·BTYPE)이 없으면 500 이라 상세 주소에 함께 붙는다
    rows = rows_of(fixture_bytes, "dis_sigak_notice", "busan_newwhite_notice.html")
    assert [(r.key, r.posted) for r in rows] == [
        ("20261001155552", date(2026, 10, 1)), ("20260921165143", date(2026, 9, 21)), ("20260915171859", date(2026, 9, 15)),
    ]
    assert rows[0].url == (
        "https://www.newwhite.or.kr/boardView.do?BNUM=201512011&SEQ=20261001155552&leftMenuNum=1"
        "&leftMenuTitle=%EB%B3%B5%EC%A7%80%EA%B4%80%EC%86%8C%EC%8B%9D&parentMenuNum=3&BTYPE=&reqPage=1&imgNum=1"
    )
    narrow = source_rules(rules, SOURCES["dis_sigak_notice"])
    assert all(judge(r.title, narrow, True) is None for r in rows)  # 직원 채용은 거름


def test_li_board_skips_pinned_copy(fixture_bytes, rules):
    # 기장장애인복지관 채용안내 (SW_bbs <li> 목록): 위에 한 번 더 나오는 고정글은 주소(zipEncode)가 달라 같은 글로 못 묶어서 뺀다
    rows = rows_of(fixture_bytes, "dis_gijang_hire", "busan_gijangbok_hire.html")
    assert [(r.title, r.posted) for r in rows] == [
        ("직원채용(언어재활사) 재공고", date(2026, 9, 18)),
        ("[강사모집] 장애아동 예비학교 보조강사 모집", date(2026, 7, 1)),
    ]
    narrow = source_rules(rules, SOURCES["dis_gijang_hire"])
    assert [judge(r.title, narrow, True) for r in rows] == [None, "모집중"]


def test_dong_board_keeps_dong_name_as_org(fixture_bytes, rules):
    # 강서구 동 소식 (여러 동 통합): 담당 부서 칸이 동 이름. '신호동'은 사람 이름처럼 보여도 org_selector 칸이라 남긴다
    rows = rows_of(fixture_bytes, "dong_gangseo_notice", "busan_dong_gangseo.html")
    assert [(r.org, r.key, r.posted) for r in rows] == [
        ("대저1동", "408486", date(2026, 6, 10)),
        ("신호동", "408430", date(2026, 6, 5)),
    ]
    assert rows[1].url == "https://www.bsgangseo.go.kr/portal/board/post/view.do?idx=408430&bcIdx=543&mid=0604010200"
    narrow = source_rules(rules, SOURCES["dong_gangseo_notice"])
    assert [judge(r.title, narrow, True) for r in rows] == ["모집중", "모집중"]
    assert _org_name("신호동", "") == ""  # 짚어 준 칸이 아니면 여전히 사람 이름으로 본다


def test_dong_board_pinned_rows_and_full_title(fixture_bytes, rules):
    # 북구 동 소식: 맨 위 공지 줄(금곡동 수강생 모집)은 강사 모집이 아니고, 일반 줄의 '구포1동 … 강사 공개모집'만 남는다
    rows = rows_of(fixture_bytes, "dong_bukgu_notice", "busan_dong_bukgu.html")
    assert [r.org for r in rows] == ["금곡동", "구포1동", "구포2동"]
    narrow = source_rules(rules, SOURCES["dong_bukgu_notice"])
    assert [judge(r.title, narrow, True) for r in rows] == [None, "모집중", "모집중"]
    # 남구 동 소식: 목록 제목은 '지도강..' 처럼 잘리고 링크 title 속성에 전체 제목
    rows = rows_of(fixture_bytes, "dong_namgu_notice", "busan_dong_namgu.html")
    assert [r.title for r in rows] == [
        "오륙도 인생후반전 지원센터 3월 시범운영 프로그램 및 재능기부 강사모집",
        "부산광역시 남구 소년소녀합창단 지도강사 모집 안내",
    ]


def test_manpa_cms_board_js_view_and_new_badge(fixture_bytes, rules):
    # 국립부산국악원 공지사항: <a onclick="fn_goView('20260211…')"><b>제목</b> <em class="new">N</em></a>
    rows = rows_of(fixture_bytes, "hall_gugak_notice", "busan_gugak_notice.html")
    assert rows[0].title == "국립남도국악원 2027 토요상설공연 '국악이 좋다' 출연자 공모"  # 새 글 표시 'N' 은 뺌
    r = rows[2]
    assert (r.title, r.key, r.posted) == ("2026년 국립부산국악원 외부강사 모집 공고", "20260211111711194631", date(2026, 2, 11))
    assert r.url == "https://busan.gugak.go.kr/BG/contents/BG0402010000.do?schM=view&id=20260211111711194631"
    narrow = source_rules(rules, SOURCES["hall_gugak_notice"])
    assert [judge(r.title, narrow, True) for r in rows] == [None, None, "모집중", None]  # 합격자 공고는 결과
    # 시청자미디어재단 부산센터: 같은 틀이고 공지 줄은 fn_goView('값', 'busanTTTnotice') 로 인자가 하나 더 붙음
    rows = rows_of(fixture_bytes, "media_kcmf_busan_notice", "busan_kcmf_notice.html")
    assert rows[0].url.endswith("schM=view&id=fuFoONisUcoNIeqlKdRA4UrAdYRrJ0w-XbqJJMVNTpg")
    assert rows[1].key == "CJSONOIHhcctr_ul9r1-R_a9R4N3Cud2xksvkc6Eu58"
    narrow = source_rules(rules, SOURCES["media_kcmf_busan_notice"])
    assert [judge(r.title, narrow, True) for r in rows] == [None, "모집중"]


def test_danuri_job_list_district_and_center(fixture_bytes, rules):
    # 다누리 채용정보 (부산): <dl> 목록, 지역 '[ 부산 부산진구 ]', 채용기간 '시작 ~ 끝', 기관명은 제목 속 센터 이름
    rows = rows_of(fixture_bytes, "family_danuri_hire", "busan_danuri_hire.html")
    assert [(r.key, r.posted, r.deadline) for r in rows[:2]] == [
        ("169574", date(2026, 10, 2), date(2026, 10, 18)),
        ("165525", date(2026, 2, 27), date(2026, 12, 11)),
    ]
    assert [next(d for d in ("동래구", "부산진구", "북구", "사상구") if d in f"{r.district} {r.org}") for r in rows] == [
        "동래구", "부산진구", "북구", "사상구"
    ]
    assert [r.org for r in rows] == ["동래구가족센터", "부산진구다문화가족지원센터", "", "사상구가족센터"]
    assert rows[1].url.startswith("https://www.liveinkorea.kr/web/lay1/bbs/S1T10C29/A/6/view.do?article_seq=165525")
    narrow = source_rules(rules, SOURCES["family_danuri_hire"])
    # 통번역지원사 채용은 강사가 아니고, 서류전형 합격자 발표는 결과 공고
    assert [judge(r.title, narrow, True) for r in rows] == [None, "모집중", "모집중", None]
    assert categorize(rows[1].title, rows[1].org, rules) == "다문화·한국어"


def test_bgli_notice_and_trust_boards(fixture_bytes, rules):
    # 부산여성가족과평생교육진흥원 공지사항: 위촉 강사 모집은 남기고 교육 대상자 공지·강사육성 과정 수료자 공고는 뺌
    rows = rows_of(fixture_bytes, "bgli_notice", "busan_bgli_notice.html")
    assert [r.key for r in rows] == ["25379", "24205", "23477"]
    assert rows[0].posted == date(2026, 2, 13)
    narrow = source_rules(rules, SOURCES["bgli_notice"])
    assert [judge(r.title, narrow, True) for r in rows] == ["모집중", None, None]
    # 여평원 수탁기관: 부산광역시건강가정지원센터 채용을 진흥원이 대신 올림. 기관명은 제목 속 센터 이름
    rows = rows_of(fixture_bytes, "bgli_trust", "busan_bgli_trust.html")
    assert (rows[0].org, rows[0].key) == ("부산광역시건강가정지원센터", "26175")
    assert judge(rows[0].title, source_rules(rules, SOURCES["bgli_trust"]), True) is None  # 직원 채용


def test_child_protection_boards(fixture_bytes):
    # 동부산아동보호전문기관 (워드프레스 게시판): 날짜 칸이 없고, 숨긴 본문 미리보기 속 면접일·첨부파일 링크는 읽지 않음
    rows = rows_of(fixture_bytes, "cpa_dongbusan_notice", "busan_dbchild_notice.html")
    assert [(r.title, r.key, r.posted) for r in rows] == [
        ("[공고] 2026년 3차 방문똑똑마음톡톡사업 행정보조인력 채용 계획", "230816", None),
        ("[모집] CHILD 서포터즈 자원봉사자 모집", "230815", None),
    ]
    assert rows[0].url == "http://dbchild.saem.or.kr/community/notice-3/?lhwb_mode=view&board_id=9&list_id=230816"
    # 북부산아동보호전문기관 (굿네이버스 누리집): 글 주소 /info/58933 의 번호가 식별값
    rows = rows_of(fixture_bytes, "cpa_bukbusan_notice", "busan_bukbusan_cpa_notice.html")
    assert [(r.key, r.posted) for r in rows] == [("58933", date(2026, 3, 31)), ("46383", date(2023, 8, 22))]
    assert rows[1].url == "https://busansb.gcps.or.kr/gnbusansb/board/cd103101100/info/46383"


def test_childcare_center_boards(fixture_bytes, rules):
    # 부산육아종합지원센터 구·군 센터 채용공고: 목록 제목이 '...' 로 잘리고 title 속성에 전체 제목, 기관명은 제목 앞 [센터 이름]
    rows = rows_of(fixture_bytes, "childcare_busan_gu_hire", "busan_childcare_gu_hire.html")
    assert [(r.org, r.key) for r in rows] == [("영도구육아종합지원센터", "219014"), ("사상구육아종합지원센터", "218822")]
    assert rows[1].title == "[사상구육아종합지원센터] 2026년 시간제대체교사 채용 공고"
    narrow = source_rules(rules, SOURCES["childcare_busan_gu_hire"])
    assert [judge(r.title, narrow, True) for r in rows] == [None, None]  # 행정원·대체교사 채용은 강사가 아님
    # 기장군육아종합지원센터: charset=euc-kr 이라 적고 응답 머리글에 문자셋이 없는 ASP 게시판 → encoding: cp949
    rows = rows_of(fixture_bytes, "childcare_gijang_notice", "busan_gijangchild_notice.html")
    assert [(r.title, r.key, r.posted) for r in rows] == [
        ("[센터소식] 기장군 보육교직원 힐링캠프 안내", "3486", date(2026, 10, 2)),
        ("★ 제10회 「현장은 나의 경험학교」 사진공모전 수상작 발표 ★", "3475", date(2026, 9, 17)),
    ]


def test_daycare_joboffer_board(fixture_bytes, rules):
    # 부산육아종합지원센터 어린이집 구인: 제목·어린이집명 칸 모두 fnGoBoardSl('…') 링크, 소재지 칸으로 구, 쪽은 offset(0,10,20)
    rows = rows_of(fixture_bytes, "childcare_daycare_joboffer", "busan_daycare_joboffer.html")
    assert [(r.title, r.org, r.key, r.deadline) for r in rows] == [
        ("육아휴직_대체교사 채용공고", "부산경찰청어린이집", "2338462", date(2026, 10, 30)),
        ("시간연장 교사 모집합니다", "칸타빌어린이집", "2338444", date(2026, 10, 15)),  # 어린이집명 뒤 '공공형' 표시는 뺌
    ]
    assert rows[0].url == "https://busan.childcare.go.kr/ccef/job/JobOfferSl.jsp?flag=Sl&JOSEQ=2338462"
    assert ["동래구" in rows[0].district, "부산진구" in rows[1].district] == [True, True]
    narrow = source_rules(rules, SOURCES["childcare_daycare_joboffer"])
    assert [judge(r.title, narrow, True) for r in rows] == [None, None]  # 보육교직원 채용은 강사 공고가 아님
    collector = BoardCollector(SOURCES["childcare_daycare_joboffer"], None, TODAY)
    assert collector.page_url(3).endswith("offset=20")
