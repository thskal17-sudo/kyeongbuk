from datetime import date

import pytest

from gyeongbuk_jobs.collectors.base import NotConfigured
from gyeongbuk_jobs.collectors.cleaneye_api import CleaneyeCollector, parse_cleaneye_xml
from gyeongbuk_jobs.config import Source

TODAY = date(2026, 10, 12)


class _Resp:
    def __init__(self, content: bytes):
        self.content = content


class _Http:
    def __init__(self, content: bytes):
        self.content = content
        self.calls: list[dict] = []

    def get(self, url, params=None, **kw):
        self.calls.append(params)
        return _Resp(self.content)


def _source(**kw) -> Source:
    return Source(id="cleaneye_api", name="클린아이", collector="cleaneye_api", org_type="공공기관",
                  district="경북전체", auth_env="DATA_GO_KR_KEY", params={"sidoCd": "007014"}, **kw)


def test_parse_items_and_no_data(fixture_bytes):
    items = parse_cleaneye_xml(fixture_bytes("cleaneye_list.xml"))
    assert [i["ENT_NAME"] for i in items] == ["경주시설관리공단", "경상북도경제진흥원"]
    assert parse_cleaneye_xml(fixture_bytes("cleaneye_nodata.xml")) == []


def test_api_error_code_raises():
    xml = b"<response><openXmlEmployInfo-header><resultCode>11</resultCode><resultMsg>NOTEXISTPARAMETER_ERROR(type)</resultMsg></openXmlEmployInfo-header></response>"
    with pytest.raises(RuntimeError, match="NOTEXISTPARAMETER"):
        parse_cleaneye_xml(xml)


def test_collect_builds_postings(fixture_bytes, monkeypatch):
    monkeypatch.setenv("DATA_GO_KR_KEY", "abc%2Bdef")
    http = _Http(fixture_bytes("cleaneye_list.xml"))
    posts = CleaneyeCollector(_source(), http, TODAY).collect()
    assert http.calls[0]["serviceKey"] == "abc+def"  # Encoding 키는 풀어서 보낸다
    assert http.calls[0]["type"] == "xml" and http.calls[0]["sidoCd"] == "007014"
    p = posts[0]
    assert p.title == "2026년 제5회 시간강사 채용공고"
    assert p.org_name == "경주시설관리공단"
    assert p.district == "경주시"
    assert p.posted_date == date(2026, 10, 12) and p.deadline == date(2026, 10, 20)
    assert p.url.endswith("idx=80300") and p.post_key == "80300"
    assert posts[1].label == "사무보조" and p.label == ""


def test_missing_key_is_not_configured(monkeypatch):
    monkeypatch.delenv("DATA_GO_KR_KEY", raising=False)
    with pytest.raises(NotConfigured):
        CleaneyeCollector(_source(), _Http(b""), TODAY).collect()


def test_request_error_hides_key(monkeypatch):
    import requests

    monkeypatch.setenv("DATA_GO_KR_KEY", "SECRET+KEY/123")

    class _Boom:
        def get(self, url, params=None, **kw):
            raise requests.exceptions.HTTPError(
                "500 Server Error for url: https://apis.data.go.kr/x?serviceKey=SECRET%2BKEY%2F123&type=xml")

    with pytest.raises(requests.exceptions.HTTPError) as info:
        CleaneyeCollector(_source(), _Boom(), TODAY).collect()
    assert "SECRET" not in str(info.value) and "serviceKey=***" in str(info.value)
