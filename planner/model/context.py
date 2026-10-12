"""读取 data/context/ 里的形势摘要。没有来源、没有日期或已过期的不交给模型。"""

import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from planner.paths import CONTEXT_DIR, ROOT
from planner.yamlutil import parse_yaml

_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class Summary:
    title: str
    date: str
    source: str
    scope: str
    expires: str
    body: str
    file: str

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "date": self.date,
            "source": self.source,
            "scope": self.scope,
            "expires": self.expires,
            "body": self.body,
        }


def load_summary(path: Path, today: date | None = None) -> Summary | None:
    """不合格就返回空。调用方改走初版模板，不把这份文件交给模型。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    split = _split_front(text)
    if split is None:
        return None
    meta, body = split
    title = _text(meta.get("title"))
    day = _day(meta.get("date"))
    source = _text(meta.get("source"))
    scope = _text(meta.get("scope"))
    expires = _day(meta.get("expires"))
    if not title or not day or not source or not scope or not expires or not body:
        return None
    current = today or date.today()
    if expires < current:
        return None
    try:
        rel = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rel = path.name
    return Summary(
        title=title,
        date=day.isoformat(),
        source=source,
        scope=scope,
        expires=expires.isoformat(),
        body=body,
        file=rel,
    )


def resolve_summary(explicit: str | Path | None = None, today: date | None = None) -> Summary | None:
    """指定了路径就只读那一份。没指定时，目录里恰好一份合格摘要才采用。"""
    if explicit:
        path = _locate(explicit)
        if path is None:
            return None
        return load_summary(path, today)
    env = os.environ.get("PLANNER_CONTEXT", "").strip()
    if env:
        path = _locate(env)
        if path is None:
            return None
        return load_summary(path, today)
    qualified = []
    if CONTEXT_DIR.is_dir():
        for path in sorted(CONTEXT_DIR.glob("*.md")):
            summary = load_summary(path, today)
            if summary is not None:
                qualified.append(summary)
    if len(qualified) == 1:
        return qualified[0]
    return None


def _locate(explicit: str | Path) -> Path | None:
    path = Path(explicit)
    if path.is_file():
        return path
    rooted = ROOT / path
    if rooted.is_file():
        return rooted
    return None


def _split_front(text: str):
    text = text.lstrip("\ufeff")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end < 0:
        return None
    meta = parse_yaml(text[3:end])
    if not isinstance(meta, dict):
        return None
    body = text[end + 4 :].strip()
    return meta, body


def _text(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _day(value) -> date | None:
    if not isinstance(value, str) or not _DAY.fullmatch(value.strip()):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None
