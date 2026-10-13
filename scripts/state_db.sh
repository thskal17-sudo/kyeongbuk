#!/usr/bin/env bash
# 수집 기록(DB)을 별도 브랜치에 보관·복원한다 (GitHub Actions 에서 사용).
#   bash scripts/state_db.sh restore [DB] [BRANCH]   BRANCH 의 DB 파일 → DB (없으면 첫 실행)
#   bash scripts/state_db.sh save [DB] [BRANCH]      DB → BRANCH (커밋 하나로 덮어씀, GITHUB_TOKEN 필요)
# 기본값: data/postings.db, state 브랜치. 한국 PC 실행기는 data/korea.db, state-korea 브랜치를 쓴다.
#
# state 브랜치에는 강사잇다 양식 엑셀(out/강사잇다_경북_*.xlsx, 마감 전 공고 전부)도 gangsaitda_latest.xlsx 로 같이 보관한다.
# 울산 저장소의 '오늘의 브리핑'이 이 파일을 읽어 합본에 넣고 강사잇다 사이트에 자동 등록한다 (부산판과 같은 방식).
set -euo pipefail
db=${2:-data/postings.db}
branch=${3:-state}
name=$(basename "$db")
xlsx_name=gangsaitda_latest.xlsx
xlsx_keep=$(dirname "$db")/$xlsx_name

case "${1:-}" in
  restore)
    mkdir -p "$(dirname "$db")"
    if git fetch --depth=1 origin "$branch" 2>/dev/null; then
      git show "FETCH_HEAD:$name" > "$db"
      echo "기존 수집 기록 복원: $branch/$name ($(wc -c < "$db") bytes)"
      # 지난 양식 엑셀도 가져와 둔다 (이번 실행이 엑셀을 못 만들면 지난 것을 그대로 보관)
      if [ "$branch" = state ]; then
        git show "FETCH_HEAD:$xlsx_name" > "$xlsx_keep" 2>/dev/null || rm -f "$xlsx_keep"
      fi
    else
      echo "$branch 브랜치 없음: 첫 실행"
    fi
    ;;
  save)
    tmp=$(mktemp -d)
    cp "$db" "$tmp/"
    # state 브랜치: 이번 실행에서 만든 강사잇다 양식(가장 최근 파일) → 없으면 지난 것
    if [ "$branch" = state ]; then
      latest=$(ls -t out/강사잇다_경북_*.xlsx 2>/dev/null | head -1 || true)
      if [ -n "$latest" ]; then
        cp "$latest" "$tmp/$xlsx_name"
      elif [ -f "$xlsx_keep" ]; then
        cp "$xlsx_keep" "$tmp/$xlsx_name"
      fi
    fi
    cd "$tmp"
    git init -q -b "$branch"
    git add "$name"
    [ -f "$xlsx_name" ] && git add "$xlsx_name"
    git -c user.name="github-actions[bot]" \
        -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
        commit -q -m "수집 기록 $(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M')"
    git push -q -f "https://x-access-token:${GITHUB_TOKEN}@github.com/${GITHUB_REPOSITORY}.git" "$branch"
    ;;
  *)
    echo "사용법: $0 restore|save [DB] [BRANCH]" >&2
    exit 2
    ;;
esac
