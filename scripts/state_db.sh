#!/usr/bin/env bash
# 수집 기록(DB)을 별도 브랜치에 보관·복원한다 (GitHub Actions 에서 사용).
#   bash scripts/state_db.sh restore [DB] [BRANCH]   BRANCH 의 DB 파일 → DB (없으면 첫 실행)
#   bash scripts/state_db.sh save [DB] [BRANCH]      DB → BRANCH (커밋 하나로 덮어씀, GITHUB_TOKEN 필요)
# 기본값: data/postings.db, state 브랜치. 한국 PC 실행기는 data/korea.db, state-korea 브랜치를 쓴다.
set -euo pipefail
db=${2:-data/postings.db}
branch=${3:-state}
name=$(basename "$db")

case "${1:-}" in
  restore)
    mkdir -p "$(dirname "$db")"
    if git fetch --depth=1 origin "$branch" 2>/dev/null; then
      git show "FETCH_HEAD:$name" > "$db"
      echo "기존 수집 기록 복원: $branch/$name ($(wc -c < "$db") bytes)"
    else
      echo "$branch 브랜치 없음: 첫 실행"
    fi
    ;;
  save)
    tmp=$(mktemp -d)
    cp "$db" "$tmp/"
    cd "$tmp"
    git init -q -b "$branch"
    git add "$name"
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
