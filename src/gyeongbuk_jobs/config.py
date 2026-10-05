from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


@dataclass
class Source:
    id: str
    name: str
    collector: str
    url: str | None = None
    org_type: str = ""
    district: str = ""
    pages: int = 1
    keyword_filter: bool = True
    phase: int = 1
    enabled: bool = True
    verified: bool = False
    auth_env: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class Rules:
    include: list[str]
    exclude: list[str]
    result_notice: list[str]
    keep_result_notices: bool
    categories: dict[str, list[str]]
    new_max_age_days: int = 45
    active_max_age_days: int = 30
    closing_soon_days: int = 3
    include_ignore: list[str] = field(default_factory=list)


def source_rules(rules: Rules, src: Source) -> Rules:
    """게시판에 include 옵션이 있으면 포함 키워드만 그것으로 바꾼 규칙
    (이용자 공지가 많은 게시판에서 '수영강습 접수 안내' 같은 글이 '강습'으로 걸리지 않게)."""
    return replace(rules, include=list(src.options["include"])) if src.options.get("include") else rules


@dataclass
class Settings:
    max_phase: int
    sources: list[Source]


_SOURCE_FIELDS = set(Source.__dataclass_fields__)


def load_settings(config_dir: Path = DEFAULT_CONFIG_DIR) -> Settings:
    data = yaml.safe_load((config_dir / "sources.yaml").read_text(encoding="utf-8"))
    sources = []
    for raw in data["sources"]:
        known = {k: v for k, v in raw.items() if k in _SOURCE_FIELDS}
        extra = {k: v for k, v in raw.items() if k not in _SOURCE_FIELDS}
        src = Source(**known)
        src.options = {**extra, **src.options}
        sources.append(src)
    ids = [s.id for s in sources]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise ValueError(f"sources.yaml 에 중복 id: {sorted(duplicates)}")
    return Settings(max_phase=int(data.get("max_phase", 1)), sources=sources)


def load_rules(config_dir: Path = DEFAULT_CONFIG_DIR) -> Rules:
    data = yaml.safe_load((config_dir / "keywords.yaml").read_text(encoding="utf-8"))
    return Rules(
        include=data.get("include", []),
        exclude=data.get("exclude", []),
        result_notice=data.get("result_notice", []),
        keep_result_notices=bool(data.get("keep_result_notices", False)),
        categories=data.get("categories", {}),
        new_max_age_days=int(data.get("new_max_age_days", 45)),
        active_max_age_days=int(data.get("active_max_age_days", 30)),
        closing_soon_days=int(data.get("closing_soon_days", 3)),
        include_ignore=data.get("include_ignore", []),
    )
