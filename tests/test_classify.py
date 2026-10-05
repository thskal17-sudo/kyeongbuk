import pytest

from gyeongbuk_jobs.classify import categorize, infer_district, infer_org_type, judge


@pytest.mark.parametrize(
    "title, keyword_filter, label, expected",
    [
        ("2026학년도 척과초 초등방과후 프로그램 개인위탁 독서논술 강사 모집", True, "", "모집중"),
        ("2026년 하반기 사직실내수영장 교육강사(프리랜서) 모집 공고", True, "", "모집중"),
        ("생활체육지도자 채용 공고", True, "", "모집중"),
        ("2026학년도 2학기 방과후학교 프로그램 운영 공고(바이올린)", True, "방과후강사(관련)", "모집중"),
        ("부산가온고등학교 영어과 기간제 교원 채용 공고", True, "기간제교원(보결)", None),
        ("부산시설공단 임원(이사장·비상임이사) 공개모집 공고", True, "", None),
        ("2026년 수영강습 회원모집", True, "", None),
        ("여성회관 2학기 수강생 모집", True, "", None),
        ("수영강사 채용 최종합격자 공고", True, "", None),
        ("방과후 강사 서류전형 결과 안내", True, "", None),
        ("공모 안내", False, "", "모집중"),  # 강사 전용 게시판은 키워드 검사 생략
        ("[마감] 부산동천고등학교 시간강사 채용 재공고(미술)", False, "강사", None),
        ("[주의: 접수 마감되었습니다.] 2026학년도 2학기 시간강사 채용 공고(일본어)", False, "강사", None),
        ("[서부청소년수련관]2026년 청소년방과후아카데 하반기 스포츠강사 최종적격", False, "", None),
        ("중구수영장 시간강사(프리랜서) 서류적격 대상자 발표 및 면접심사 시행 공고", True, "", None),
        ("청소년수련활동 인증프로그램 우수기관·지도자 포상 및 수기공모전 참가 안내", True, "", None),
        ("2026학년도 늘봄학교 프로그램 운영 용역 입찰공고(적격심사)", True, "", "모집중"),
        ("청년마음건강사업 안내", True, "", None),  # '건강사업' 속 '강사'
        ("2026년 건강사업 운동강사 모집", True, "", "모집중"),
        ("2021년 아동학대예방 부모교육「최민준 강사 초청 특강」 안내", True, "", None),
        ("'기적의 놀이터 편해문 강사와 함께하는 부모 교육'안내", True, "", None),
        ("[공통부모교육]양육스트레스관리부모교육 강사진 모집 공고", True, "", "모집중"),
        ("[중부청소년수련관]2026년 문화강좌 4분기 교육강사 긴급 위·수탁 모집 최종수탁자 공고(안)", False, "", None),
    ],
)
def test_judge(rules, title, keyword_filter, label, expected):
    assert judge(title, rules, keyword_filter, label) == expected


def test_keep_result_notices(rules):
    rules.keep_result_notices = True
    assert judge("수영강사 채용 최종합격자 공고", rules, True) == "결과공고"


def test_categorize(rules):
    assert categorize("척과초 초등방과후 프로그램 개인위탁 독서논술 강사 모집", "척과초등학교", rules) == "방과후·늘봄"
    assert categorize("독서논술 강사 모집", "척과초등학교", rules) == "학교 기타"
    assert categorize("수영장 교육강사 모집", "부산시설공단", rules) == "체육·수영"
    assert categorize("도서관 인문학 강사 모집", "", rules) == "평생교육·문화"
    assert categorize("2026학년도 기간제(시간강사)교원 (화학)채용 공고", "강동고등학교", rules) == "학교 시간강사"
    assert categorize("강사 모집", "", rules) == "기타"
    # '다문화' 속 '문화' 때문에 평생교육·문화로 가지 않게 다문화·한국어를 앞에 둠
    assert categorize("2026년도 이중언어직접교육사업 (이중언어 강사) 채용", "부산 가족센터", rules) == "다문화·한국어"
    assert categorize("한국어 교육 강사 채용 공고", "영도구가족센터", rules) == "다문화·한국어"


def test_categorize_negative_terms(rules):
    # 공단 수영장의 시간강사는 학교 시간강사가 아니고, 청소년방과후아카데미는 학교 방과후가 아님
    assert categorize("중구수영장 시간강사(수영) 위촉 공고", "중구도시관리공단", rules) == "체육·수영"
    assert categorize("2026 청소년방과후아카데미 스포츠강사 (긴급) 위수탁", "기장군도시관리공단", rules) == "체육·수영"
    assert categorize("부산동천고등학교 시간강사 채용 공고(일본어)", "부산동천고등학교", rules) == "학교 시간강사"
    assert categorize("여성회관 교육강사(3학기 단기특강) 모집 공고", "부산여성회관", rules) == "평생교육·문화"


def test_infer_org_type_and_district():
    assert infer_org_type("포항시시설관리공단") == "공단(체육시설)"
    assert infer_org_type("척과초등학교") == "교육청·학교"
    assert infer_org_type("무엇", "기본") == "기본"
    assert infer_district("경상북도 포항시 북구") == "포항시"
    assert infer_district("경상북도", "경북전체") == "경북전체"
    # '시·군' 없이 쓴 이름
    assert infer_district("경상북도경주교육지원청") == "경주시"
    assert infer_district("안동대학교 평생교육원") == "안동시"
    assert infer_district("구미시설공단") == "구미시"
    # 영양·상주·고령은 다른 뜻(영양사·상주 인력·고령자)으로 흔해서 기관 이름일 때만
    assert infer_district("학교 영양사 채용", "경북전체") == "경북전체"
    assert infer_district("상주 인력 모집", "경북전체") == "경북전체"
    assert infer_district("고령자 일자리", "경북전체") == "경북전체"
    assert infer_district("상주교육지원청") == "상주시"
    assert infer_district("고령도서관") == "고령군"
    assert infer_district("영양초등학교") == "영양군"
    assert infer_district("영양군청") == "영양군"
