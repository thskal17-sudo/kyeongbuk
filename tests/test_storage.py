from datetime import date, datetime

from gyeongbuk_jobs.models import KST, Posting
from gyeongbuk_jobs.storage import DUPLICATE, Store, title_key

NOW = datetime(2026, 9, 29, 6, 37, tzinfo=KST)


def _p(source, key, title, district="경북전체", posted=date(2026, 9, 29), org=""):
    return Posting(source, title, f"https://example.org/{source}/{key}", key, org, district=district, posted_date=posted)


def test_title_key_ignores_spacing_and_marks():
    assert title_key("[우암초등학교 공고 제2026-27호] 특수학급 시간강사") == title_key("[우암초등학교 공고 제2026 27호]특수학급 시간강사")


def test_same_posting_on_two_boards_is_new_once(tmp_path):
    # 부산교육청 학교인력채용에 올라온 공고가 북부교육지원청 게시판에도 올라온다
    store = Store(tmp_path / "db.sqlite")
    main = _p("pen_school_hire", "1180893", "2026학년도 가람중학교 문화예술교육 강사 채용 공고", org="가람중학교")
    mirror = _p("bukbu_edu_hire", "1039718", "2026학년도 가람중학교 문화예술교육 강사 채용 공고", org="가람중학교")
    assert store.upsert(main, NOW) is True
    assert store.upsert(mirror, NOW) is False
    statuses = {p.source_id: p.status for p in store.unreported()}
    assert statuses == {"pen_school_hire": "모집중", "bukbu_edu_hire": DUPLICATE}
    assert [p.source_id for p in store.active(NOW.date(), 30)] == ["pen_school_hire"]

    # 다음 날 목록에 그대로 있어도 '중복'이 '모집중'으로 돌아가지 않는다
    store.upsert(_p("bukbu_edu_hire", "1039718", "2026학년도 가람중학교 문화예술교육 강사 채용 공고"), NOW)
    assert {p.source_id: p.status for p in store.unreported()}["bukbu_edu_hire"] == DUPLICATE
    store.close()


def test_different_postings_are_not_merged(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    # 같은 제목이라도 다른 구의 공단 공고, 짧은 제목, 게시일이 멀리 떨어진 공고는 따로 본다
    assert store.upsert(_p("bnfmc_hire", "297", "2026년 제4회 시간강사 채용공고 (수영)", "남구"), NOW)
    assert store.upsert(_p("gijangcmc_hire", "1700", "2026년 제4회 시간강사 채용공고 (수영)", "기장군"), NOW)
    assert store.upsert(_p("a", "1", "시간강사 채용 공고"), NOW)
    assert store.upsert(_p("b", "1", "시간강사 채용 공고"), NOW)
    assert store.upsert(_p("c", "1", "2026년 해운대구 건강생활지원센터 건강지도자 위촉 공고", "해운대구",
                           posted=date(2026, 6, 1)), NOW)
    assert store.upsert(_p("d", "1", "2026년 해운대구 건강생활지원센터 건강지도자 위촉 공고", "해운대구"), NOW)
    assert all(p.status == "모집중" for p in store.unreported())
    store.close()
