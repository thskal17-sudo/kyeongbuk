"""SQLite 저장소: 한 번 본 공고를 기억해서 '신규'를 판정하고, 수집 이력을 남긴다.

신규 판정은 '처음 본 시각'이 아니라 '아직 메일로 보내지 않았는가(reported_at IS NULL)'로 한다.
메일 발송이 실패하면 다음 실행 때 다시 신규로 잡혀서 공고를 놓치지 않는다.

같은 공고가 여러 게시판에 올라오는 경우(경북교육청 ↔ 교육지원청 게시판, 시·군청 ↔ 경북일자리 게시판)
먼저 저장된 공고와 제목이 같고 게시일·지역이 맞으면 '중복'으로 저장해 신규·진행중에서 뺀다.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import Posting, SourceResult

SCHEMA = """
CREATE TABLE IF NOT EXISTS postings (
    uid           TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL,
    post_key      TEXT,
    org_name      TEXT,
    org_type      TEXT,
    district      TEXT,
    title         TEXT NOT NULL,
    url           TEXT NOT NULL,
    posted_date   TEXT,
    deadline      TEXT,
    category      TEXT,
    status        TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    reported_at   TEXT,
    info          TEXT
);
CREATE INDEX IF NOT EXISTS idx_postings_reported ON postings(reported_at);
CREATE TABLE IF NOT EXISTS source_runs (
    run_at    TEXT NOT NULL,
    source_id TEXT NOT NULL,
    state     TEXT NOT NULL,
    fetched   INTEGER NOT NULL,
    matched   INTEGER NOT NULL,
    new       INTEGER NOT NULL,
    error     TEXT
);
"""


CLOSED = "결과발표"  # 결과공고가 올라와 모집이 끝난 공고
DUPLICATE = "중복"  # 다른 게시판에 먼저 올라온 같은 공고
_STICKY = (CLOSED, DUPLICATE)  # 다음 날 목록에 그대로 있어도 '모집중'으로 되돌리지 않는 상태
_WHOLE_CITY = ("", "경북전체")


# 게시판이 제목 앞에 붙이는 분류 표시 (경산교육지원청 '[기타] 학교운동부 테니스지도자 채용공고' ↔ 본청 같은 글).
# 학교 이름 표시('[구정초]')는 다른 학교의 같은 제목과 구별해야 해서 남긴다
_CATEGORY_PREFIX = re.compile(
    r"^\s*\[\s*(기타|계약제\s*교원|교육공무직원?|방과후학교\s*강사|[초중]등\s*기간제|구인|공고|상시|모집)\s*\]\s*"
)


def title_key(title: str) -> str:
    """중복 비교용 제목: 글자·숫자만 (공백·괄호·기호, 앞의 분류 표시 무시)."""
    return re.sub(r"[^0-9A-Za-z가-힣]", "", _CATEGORY_PREFIX.sub("", title or ""))


def _same_posting(p: Posting, title: str, district: str | None, posted: date | None, min_key: int = 12) -> bool:
    key = title_key(p.title)
    if len(key) < min_key or key != title_key(title):
        return False  # '시간강사 채용 공고' 처럼 짧은 제목은 기관이 달라도 같을 수 있어 비교하지 않음
    if p.district not in _WHOLE_CITY and (district or "") not in _WHOLE_CITY and p.district != district:
        return False
    return p.posted_date is None or posted is None or abs((p.posted_date - posted).days) <= 7


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


class Store:
    def __init__(self, path: Path | str):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        columns = {r["name"] for r in self.conn.execute("PRAGMA table_info(postings)")}
        if "info" not in columns:  # 강사잇다 양식용 칸이 생기기 전의 DB
            self.conn.execute("ALTER TABLE postings ADD COLUMN info TEXT")

    def close(self) -> None:
        self.conn.commit()
        self.conn.close()

    def title_of(self, uid: str) -> str | None:
        row = self.conn.execute("SELECT title FROM postings WHERE uid = ?", (uid,)).fetchone()
        return row[0] if row else None

    def twin_of(self, p: Posting, now: datetime, window_days: int = 60) -> str | None:
        """다른 게시판에 먼저 저장된 같은 공고의 uid (없으면 None)."""
        since = (now - timedelta(days=window_days)).isoformat(timespec="seconds")
        rows = self.conn.execute(
            """SELECT uid, title, district, posted_date FROM postings
               WHERE source_id != ? AND status != ? AND first_seen_at >= ?""",
            (p.source_id, DUPLICATE, since),
        )
        for r in rows:
            if _same_posting(p, r["title"], r["district"], _d(r["posted_date"])):
                return r["uid"]
        return None

    def upsert(self, p: Posting, now: datetime) -> bool:
        """저장하고, 처음 보는 공고면 True (다른 게시판에 먼저 올라온 같은 공고면 '중복'으로 저장하고 False)."""
        ts = now.isoformat(timespec="seconds")
        row = self.conn.execute("SELECT uid FROM postings WHERE uid = ?", (p.uid,)).fetchone()
        if row is None:
            duplicate = p.status == "모집중" and self.twin_of(p, now) is not None
            self.conn.execute(
                """INSERT INTO postings (uid, source_id, post_key, org_name, org_type, district, title, url,
                       posted_date, deadline, category, status, first_seen_at, last_seen_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (p.uid, p.source_id, p.post_key, p.org_name, p.org_type, p.district, p.title, p.url,
                 _iso(p.posted_date), _iso(p.deadline), p.category, DUPLICATE if duplicate else p.status, ts, ts),
            )
            return not duplicate
        self.conn.execute(
            """UPDATE postings SET title = ?, url = ?, category = ?, last_seen_at = ?,
                   status = CASE WHEN status IN (?, ?) THEN status ELSE ? END,
                   org_name = COALESCE(NULLIF(?, ''), org_name),
                   posted_date = COALESCE(posted_date, ?),
                   deadline = COALESCE(?, deadline)
               WHERE uid = ?""",
            (p.title, p.url, p.category, ts, *_STICKY, p.status, p.org_name, _iso(p.posted_date), _iso(p.deadline),
             p.uid),
        )
        return False

    def open_postings(self, source_id: str, since: date) -> list[Posting]:
        """아직 모집중으로 알고 있는 이 소스의 최근 공고."""
        rows = self.conn.execute(
            """SELECT * FROM postings WHERE source_id = ? AND status = '모집중'
                 AND COALESCE(posted_date, substr(first_seen_at, 1, 10)) >= ?""",
            (source_id, since.isoformat()),
        )
        return [_to_posting(r) for r in rows]

    def mark_closed(self, uid: str) -> None:
        """결과공고가 올라와 모집이 끝난 공고로 표시 (신규·진행중에서 빠진다)."""
        self.conn.execute("UPDATE postings SET status = ? WHERE uid = ?", (CLOSED, uid))

    def detail_state(self, uid: str) -> tuple[date | None, dict | None, str]:
        """저장된 마감일·공고문 정보·상태 (정보가 None 이면 아직 공고문을 안 봄)."""
        row = self.conn.execute("SELECT deadline, info, status FROM postings WHERE uid = ?", (uid,)).fetchone()
        if row is None:
            return None, None, ""
        return _d(row["deadline"]), json.loads(row["info"]) if row["info"] else None, row["status"] or ""

    def set_info(self, uid: str, info: dict) -> None:
        self.conn.execute("UPDATE postings SET info = ? WHERE uid = ?", (json.dumps(info, ensure_ascii=False), uid))

    def set_title(self, uid: str, title: str) -> None:
        self.conn.execute("UPDATE postings SET title = ? WHERE uid = ?", (title, uid))

    def set_deadline(self, uid: str, deadline: date) -> None:
        self.conn.execute("UPDATE postings SET deadline = ? WHERE uid = ?", (_iso(deadline), uid))

    def unreported(self) -> list[Posting]:
        rows = self.conn.execute("SELECT * FROM postings WHERE reported_at IS NULL ORDER BY first_seen_at")
        return [_to_posting(r) for r in rows]

    def mark_reported(self, uids: list[str], now: datetime) -> None:
        ts = now.isoformat(timespec="seconds")
        self.conn.executemany("UPDATE postings SET reported_at = ? WHERE uid = ?", [(ts, u) for u in uids])

    def active(self, today: date, max_age_days: int, statuses: tuple[str, ...] = ("모집중",)) -> list[Posting]:
        """마감 전이거나, 마감일을 모르지만 최근 게시된 공고."""
        cutoff = (today - timedelta(days=max_age_days)).isoformat()
        marks = ",".join("?" for _ in statuses)
        rows = self.conn.execute(
            f"""SELECT * FROM postings
                WHERE status IN ({marks})
                  AND (deadline >= ?
                       OR (deadline IS NULL AND COALESCE(posted_date, substr(first_seen_at, 1, 10)) >= ?))""",
            (*statuses, today.isoformat(), cutoff),
        )
        return [_to_posting(r) for r in rows]

    def log_runs(self, results: list[SourceResult], now: datetime) -> None:
        ts = now.isoformat(timespec="seconds")
        self.conn.executemany(
            "INSERT INTO source_runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(ts, r.source_id, r.state, r.fetched, r.matched, r.new, r.error) for r in results],
        )

    def commit(self) -> None:
        self.conn.commit()


def _to_posting(r: sqlite3.Row) -> Posting:
    return Posting(
        source_id=r["source_id"],
        title=r["title"],
        url=r["url"],
        post_key=r["post_key"] or "",
        org_name=r["org_name"] or "",
        org_type=r["org_type"] or "",
        district=r["district"] or "",
        posted_date=_d(r["posted_date"]),
        deadline=_d(r["deadline"]),
        category=r["category"] or "",
        status=r["status"] or "",
        info=json.loads(r["info"]) if r["info"] else None,
    )
