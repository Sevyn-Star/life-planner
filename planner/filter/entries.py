from dataclasses import dataclass, field

from planner.paths import ENTRIES_PATH
from planner.yamlutil import parse_yaml


@dataclass(frozen=True)
class Entry:
    id: str
    label: str
    keywords: list[str]
    paths: list[str]
    templates: list[str] = field(default_factory=list)
    topic: list[str] = field(default_factory=list)
    pin_titles: list[str] = field(default_factory=list)
    needs_fourteen_day_evidence: bool = False

    def scope_paths(self) -> list[str]:
        return [*self.paths, *self.templates]


def load_entries(path=ENTRIES_PATH) -> list[Entry]:
    data = parse_yaml(path.read_text(encoding="utf-8"))
    rows = data["entries"] if isinstance(data, dict) else data
    entries = []
    for row in rows:
        entries.append(
            Entry(
                id=row["id"],
                label=row["label"],
                keywords=list(row.get("keywords") or []),
                paths=list(row.get("paths") or []),
                templates=list(row.get("templates") or []),
                topic=list(row.get("topic") or []),
                pin_titles=list(row.get("pin_titles") or []),
                needs_fourteen_day_evidence=bool(row.get("needs_fourteen_day_evidence", False)),
            )
        )
    return entries


def keyword_hit(text: str, keyword: str) -> bool:
    start = 0
    while True:
        found = text.find(keyword, start)
        if found < 0:
            return False
        window = text[max(0, found - 4) : found]
        if "不" in window or "别" in window:
            start = found + len(keyword)
            continue
        return True


def first_match(text: str, entries: list[Entry], *, low: bool, evidence: bool):
    """返回 (选中的入口, 被挡住的周期入口)。

    周期入口在没有十四天证据或容量很低时不打开，也不改去别的领域。
    """
    for entry in entries:
        if not any(keyword_hit(text, keyword) for keyword in entry.keywords):
            continue
        blocked = entry.needs_fourteen_day_evidence and (not evidence or low)
        if blocked:
            return None, entry
        return entry, None
    return None, None


def nearest_label(text: str, entries: list[Entry]) -> str:
    best_label = ""
    best_score = 0
    start_label = "阅读指南、序章"
    for entry in entries:
        if entry.id == "start":
            start_label = entry.label
        score = 0
        for keyword in entry.keywords:
            if keyword in text:
                score += len(keyword)
        if score > best_score:
            best_score = score
            best_label = entry.label
    if best_score <= 0:
        return start_label
    return best_label
