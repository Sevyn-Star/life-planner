import re
from dataclasses import dataclass, field

from planner.cli.intake import Sheet
from planner.corpus.segment import Segment
from planner.filter.entries import Entry, nearest_label

REASON_TOPIC = "不是同一件事"
REASON_ACTION = "不能变成动作或边界"
REASON_SCOPE = "范围被用大了"
REASON_CAPACITY = "和容量不相称"
REASONS = (REASON_TOPIC, REASON_ACTION, REASON_SCOPE, REASON_CAPACITY)

_STRONG = (
    "写下",
    "填写",
    "保存",
    "记录",
    "复查",
    "停止",
    "暂停",
    "最小",
    "证据",
    "不要",
    "边界",
    "先读",
    "先写",
    "先选",
    "先确认",
    "先设计",
)
_EXPERIENCE_LIMITS = ("不能", "不是", "不要", "不把", "边界", "并不", "不代表")
_RESEARCH_LIMITS = ("不支持", "不保证", "不等于", "本章不", "不代表", "不能", "不是", "边界")


@dataclass
class Outcome:
    sheet: Sheet
    kept: list[Segment] = field(default_factory=list)
    dropped: list[tuple[Segment, str]] = field(default_factory=list)
    status: str = "reject"
    nearest_title: str = ""
    note: str = ""
    entry: Entry | None = None


def select(sheet: Sheet, segments: list[Segment], entries: list[Entry]) -> Outcome:
    if sheet.cycle_blocked:
        entry = _by_id(entries, sheet.entry_id)
        note = "今天的容量不够，而且还没有可用的十四天证据。这次不打开九十天安排。"
        if not sheet.capacity_low:
            note = "还没有十四天证据。这次不打开九十天安排。"
        return Outcome(
            sheet=sheet,
            status="reject",
            nearest_title=entry.label if entry else sheet.domain,
            note=note,
            entry=entry,
        )
    if sheet.entry_id is None:
        return Outcome(
            sheet=sheet,
            status="reject",
            nearest_title=nearest_label(sheet.text, entries),
            note="这本书里没有对上的段落，所以不写规划。",
        )
    entry = _by_id(entries, sheet.entry_id)
    if entry is None:
        return Outcome(
            sheet=sheet,
            status="reject",
            nearest_title=nearest_label(sheet.text, entries),
            note="这本书里没有对上的段落，所以不写规划。",
        )
    kept, dropped = _apply(sheet, segments, entry)
    if len(kept) < 2:
        return Outcome(
            sheet=sheet,
            kept=kept,
            dropped=dropped,
            status="reject",
            nearest_title=entry.label,
            note="筛中的原文不足两段，所以不写规划。",
            entry=entry,
        )
    return Outcome(
        sheet=sheet,
        kept=kept,
        dropped=dropped,
        status="plan",
        nearest_title=entry.label,
        entry=entry,
    )


def _by_id(entries: list[Entry], entry_id: str | None) -> Entry | None:
    for entry in entries:
        if entry.id == entry_id:
            return entry
    return None


def _apply(sheet: Sheet, segments: list[Segment], entry: Entry):
    candidates = [segment for segment in segments if _in_scope(segment, entry)]
    passed: list[Segment] = []
    dropped: list[tuple[Segment, str]] = []
    pinned: list[Segment] = []
    for segment in candidates:
        reason = _reject_reason(segment, sheet, entry)
        pinned_hit = any(title in segment.title for title in entry.pin_titles)
        if pinned_hit:
            scope_reason = _scope_reason(segment)
            capacity_reason = _capacity_reason(segment, sheet)
            if scope_reason:
                dropped.append((segment, scope_reason))
                continue
            if capacity_reason:
                dropped.append((segment, capacity_reason))
                continue
            pinned.append(segment)
            continue
        if reason:
            dropped.append((segment, reason))
            continue
        passed.append(segment)
    ranked = sorted(
        passed,
        key=lambda segment: (-_rank(segment, entry, sheet), segment.path, segment.line),
    )
    threads = [segment for segment in ranked if "/templates/" not in segment.path]
    forms = [segment for segment in ranked if "/templates/" in segment.path]
    kept: list[Segment] = []
    seen = set()
    for segment in [*pinned, *threads[:4], *forms[:1]]:
        key = (segment.path, segment.title)
        if key in seen:
            continue
        seen.add(key)
        kept.append(segment)
    return kept[:5], dropped


def _in_scope(segment: Segment, entry: Entry) -> bool:
    for path in entry.scope_paths():
        if path.endswith("/") and segment.path.startswith(path):
            return True
        if segment.path == path:
            return True
    return False


def _reject_reason(segment: Segment, sheet: Sheet, entry: Entry) -> str | None:
    if not _same_topic(segment, entry):
        return REASON_TOPIC
    if not _actionable(segment):
        return REASON_ACTION
    scope = _scope_reason(segment)
    if scope:
        return scope
    return _capacity_reason(segment, sheet)


def _same_topic(segment: Segment, entry: Entry) -> bool:
    opening = segment.title + "\n" + segment.text[:180]
    if any(topic in opening for topic in entry.topic):
        return True
    return any(keyword in opening for keyword in entry.keywords)


def _actionable(segment: Segment) -> bool:
    if "结语" in segment.title:
        return False
    text = segment.text
    has_list = any(line.startswith(("- ", "* ", "|")) or _numbered(line) for line in text.splitlines())
    hits = sum(1 for word in _STRONG if word in text)
    return hits >= 2 or (hits >= 1 and has_list)


def _numbered(line: str) -> bool:
    return re.match(r"\d+\.\s", line.lstrip()) is not None


def _scope_reason(segment: Segment) -> str | None:
    if segment.kind == "个人经验" and not any(word in segment.text for word in _EXPERIENCE_LIMITS):
        return REASON_SCOPE
    if segment.kind == "研究结论" and not any(word in segment.text for word in _RESEARCH_LIMITS):
        return REASON_SCOPE
    return None


def _capacity_reason(segment: Segment, sheet: Sheet) -> str | None:
    long_cycle = "part-5/" in segment.path or "90-day" in segment.path
    if long_cycle and not sheet.has_fourteen_day_evidence:
        return REASON_CAPACITY
    if sheet.capacity_low and ("九十" in segment.title or "九十" in segment.text):
        return REASON_CAPACITY
    return None


def _rank(segment: Segment, entry: Entry, sheet: Sheet) -> int:
    opening = segment.title + "\n" + segment.text[:180]
    score = 0
    for topic in entry.topic:
        if topic in segment.title:
            score += 5
        elif topic in opening:
            score += 2
    for keyword in entry.keywords:
        if keyword in segment.title:
            score += 6
        elif keyword in opening:
            score += 2
    if "示例" in segment.title:
        score -= 12
    if any(word in segment.title for word in ("空白", "五分钟", "最小")):
        score += 4
    if sheet.capacity_low and any(word in segment.title for word in ("最小", "今天", "恢复")):
        score += 4
    return score
