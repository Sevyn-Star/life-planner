"""回来时先对照上一份记录，再决定继续、缩小或换入口。"""

from datetime import date, timedelta

from planner.cli.intake import Sheet
from planner.reply.fill import FOOTER
from planner.session import Record, plain

_STAY = ("不换", "不要换", "先不换", "留在原来")
_SWITCH = ("换主线", "同意换", "换吧", "就换主线")
_BROUGHT = ("留下了", "贴上", "做完了", "写好了", "这是记录", "证据是", "记录如下", "我做了")
_SHRINK = ("做不到", "没做成", "没做完", "太难", "做不了", "没完成")


def choice(text: str) -> str | None:
    if any(mark in text for mark in _STAY):
        return "stay"
    if any(mark in text for mark in _SWITCH):
        return "switch"
    return None


def only_switch(text: str) -> bool:
    bare = text.strip().strip("。！？!?. ")
    return bare in set(_SWITCH)


def shrinking(text: str) -> bool:
    return any(mark in text for mark in _SHRINK)


def bringing(text: str) -> bool:
    if shrinking(text):
        return False
    return any(mark in text for mark in _BROUGHT)


def looks_like_return(text: str) -> bool:
    return bringing(text) or shrinking(text)


def pin_return(sheet: Sheet, record: Record) -> None:
    """没对上新入口、但明显在说上一轮的记录时，仍留在原来的入口。"""
    if sheet.entry_id is None and looks_like_return(sheet.text):
        sheet.entry_id = record.entry_id
        sheet.domain = record.entry_label
        sheet.cycle_blocked = False


def side_topic(sheet: Sheet, record: Record) -> bool:
    if sheet.entry_id == record.entry_id:
        return False
    if sheet.entry_id == "cycle":
        return False
    if sheet.entry_id is None and looks_like_return(sheet.text):
        return False
    return True


def fourteen_ready(record: Record, text: str, today: date) -> bool:
    if "十四" in text and any(mark in text for mark in ("证据", "复测", "复查", "做完", "完成", "留下")):
        return True
    if not record.brought:
        return False
    try:
        due = date.fromisoformat(record.review_date)
    except ValueError:
        return False
    return today >= due


def next_review(today: date) -> str:
    return (today + timedelta(days=14)).isoformat()


def ask_switch_plain(sheet: Sheet, record: Record) -> str:
    return (
        f"上一轮还在说「{record.question}」，入口是「{record.entry_label}」。"
        f"这次说的是「{sheet.domain}」。两条线不并在一起。"
        "要换就回我「换主线」，不换就回「不换」。"
    )


def stay_plain(record: Record) -> str:
    return (
        f"那就还留在「{record.entry_label}」。这次不换。"
        f"上次那一步先做完，{record.review_date}再看。"
    )


def ask_switch(sheet: Sheet, record: Record) -> str:
    lines = [
        "## 要不要换主线",
        "",
        f"上一轮的主线是「{record.question}」，入口是「{record.entry_label}」。",
        f"这次说的是「{sheet.question}」，领域是「{sheet.domain}」。",
        "两条线不并成一份计划。",
        "",
        "要换主线，下一次说「换主线」。要留在原来的入口，说「不换」，并贴上上次要留的证据。",
        "",
        f"上次最小动作：{record.action}",
        f"要留下的证据：{record.evidence}",
        f"复查日期：{record.review_date}",
        "",
        FOOTER,
    ]
    return "\n".join(lines).rstrip() + "\n"


def stay_reply(record: Record) -> str:
    lines = [
        "## 主线",
        "",
        f"仍走「{record.entry_label}」。这次不换。旁边的事不并进这一份计划。",
        "",
        "## 规划",
        "",
        f"- 问题：{record.question}",
        f"- 基线：{record.brought or '尚未记录'}",
        f"- 最小动作：{record.action}",
        f"- 证据：{record.evidence}",
        f"- 复查：{record.review_date} 复测。没有这次留下的记录之前，不排长周期。",
        "",
        "## 下次开口可以带什么",
        "",
        "贴上上次要留的那份证据。有了它，才决定继续、缩小，还是换入口。",
        "",
        FOOTER,
    ]
    return "\n".join(lines).rstrip() + "\n"


def review_note(record: Record, decision: str, brought_now: bool) -> str:
    seen = "这次带来了记录。" if brought_now else "这次还没有贴上那份记录。"
    return "\n".join(
        [
            "## 复查",
            "",
            f"上次要留下的证据是：{record.evidence}",
            seen,
            f"决定：{decision}。入口仍是「{record.entry_label}」。",
            "",
        ]
    )


def switched_note(record: Record) -> str:
    return "\n".join(
        [
            "## 复查",
            "",
            f"已换主线。上一轮的入口「{record.entry_label}」不并进这一份计划。",
            "",
        ]
    )


def stamp_review(reply: str, day: str, *, low: bool) -> str:
    if low:
        replacement = f"- 复查：{day} 看这一次短动作留下的记录。这一轮不排长周期。"
    else:
        replacement = f"- 复查：{day} 复测。没有这次留下的记录之前，不排长周期。"
    lines = []
    for line in reply.splitlines():
        if line.startswith("- 复查："):
            lines.append(replacement)
        else:
            lines.append(line)
    return "\n".join(lines).rstrip() + "\n"


def insert_review(reply: str, note: str) -> str:
    marker = "## 主线"
    if marker not in reply:
        return reply
    return reply.replace(marker, note + marker, 1)


def remember(reply: str, sheet: Sheet, record: Record | None, review_day: str, brought_now: bool) -> Record | None:
    action = _field(reply, "- 最小动作：")
    evidence = _field(reply, "- 证据：")
    if not action or not sheet.entry_id:
        return None
    brought = record.brought if record else ""
    if brought_now:
        brought = plain(sheet.text, limit=160)
    return Record(
        question=plain(sheet.question, limit=80),
        entry_id=sheet.entry_id,
        entry_label=sheet.domain,
        action=plain(action),
        evidence=plain(evidence),
        review_date=review_day,
        brought=brought,
    )


def _field(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""
