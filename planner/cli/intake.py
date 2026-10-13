import re
from dataclasses import dataclass, field

from planner.filter.entries import Entry, first_match

_CLAUSE = re.compile(r"[。！？；\n]")
_ID_NUMBER = re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_SECRET = re.compile(r"(密码|证件号|身份证号|身份证|住址|病历)\s*[:：]?\s*\S+")
_EVIDENCE = re.compile(r"十四天.{0,16}(证据|复测|复查|样本|做完|完成)|(已经|做过|留下).{0,12}十四天")
_LOW = (
    "几分钟",
    "五分钟",
    "今天很短",
    "很短",
    "没力气",
    "状态很差",
    "低谷",
    "容量很小",
    "失眠",
    "只有几分",
)
_CRISIS = ("自杀", "轻生", "不想活", "伤害自己", "伤害我自己", "危险念头", "活不下去", "结束生命")
_FACT = ("已经", "现在", "目前", "今天", "没有", "睡", "做过", "写了")


@dataclass
class Sheet:
    question: str
    domain: str
    entry_id: str | None
    facts: list[str] = field(default_factory=list)
    capacity: str = ""
    capacity_low: bool = False
    goal: str = ""
    has_fourteen_day_evidence: bool = False
    safety: bool = False
    cycle_blocked: bool = False
    text: str = ""


def redact(text: str) -> str:
    text = _ID_NUMBER.sub("〔已省略〕", text)
    text = _PHONE.sub("〔已省略〕", text)
    text = _SECRET.sub(lambda match: match.group(1) + "〔已省略〕", text)
    return text


def build_sheet(user_text: str, entries: list[Entry]) -> Sheet:
    text = redact(user_text).strip()
    low = any(marker in text for marker in _LOW)
    evidence = _EVIDENCE.search(text) is not None
    safety = any(marker in text for marker in _CRISIS)
    entry, blocked = first_match(text, entries, low=low, evidence=evidence)
    if safety and entry is None and blocked is None:
        for candidate in entries:
            if candidate.id == "recovery":
                entry = candidate
                break
    if blocked is not None:
        domain = blocked.label
        entry_id = blocked.id
    elif entry is not None:
        domain = entry.label
        entry_id = entry.id
    else:
        domain = "书外"
        entry_id = None
    facts = _facts(text)
    return Sheet(
        question=_question(text),
        domain=domain,
        entry_id=entry_id,
        facts=facts,
        capacity=_capacity(text, low),
        capacity_low=low,
        goal=_goal(text),
        has_fourteen_day_evidence=evidence,
        safety=safety,
        cycle_blocked=blocked is not None,
        text=text,
    )


def _question(text: str) -> str:
    clauses = [clause.strip() for clause in _CLAUSE.split(text) if clause.strip()]
    question = clauses[0] if clauses else text
    if len(question) > 80:
        return question[:80] + "…"
    return question


def _facts(text: str) -> list[str]:
    clauses = [clause.strip() for clause in _CLAUSE.split(text) if clause.strip()]
    question = clauses[0] if clauses else ""
    facts = []
    for clause in clauses:
        if clause == question:
            continue
        if any(marker in clause for marker in ("希望", "想要", "想知道")):
            continue
        if any(marker in clause for marker in _FACT):
            facts.append(clause)
    return facts[:4]


def _capacity(text: str, low: bool) -> str:
    if low:
        matched = re.search(r"[^。，]{0,14}(几分钟|五分钟|很短|没力气|状态很差|低谷|失眠)", text)
        if matched:
            return "很低：" + matched.group(0).strip("，, ")
        return "很低"
    matched = re.search(r"今天[^。，]{0,18}", text)
    if matched:
        return matched.group(0).strip()
    matched = re.search(r"(半小时|一小时|几分钟|\d+\s*分钟|\d+\s*小时)", text)
    if matched:
        return matched.group(0).strip()
    return "未说明，按一次 25–45 分钟的最小动作"


def _goal(text: str) -> str:
    if any(marker in text for marker in ("该不该", "要不要", "只想判断")):
        return "只要判断该不该做"
    if any(marker in text for marker in ("九十天", "90天", "周期规划", "复查的周期")):
        return "一份周期规划"
    return "一个今天的动作"
