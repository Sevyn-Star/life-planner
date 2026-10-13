"""页面上的白话回答。书里的段落只作参考，模型的字按片段往外送。

每一段对话有会话名时，先对照上一份主线。岔到另一个入口先问要不要换。
没对上新入口的追问留在原来的主线，不另写一份计划。
"""

import re
from datetime import date

from planner.cli.intake import build_sheet
from planner.corpus.index import build_index, load_index
from planner.filter.entries import load_entries
from planner.filter.select import select
from planner.model import ModelError
from planner.model.local.client import linked_weights
from planner.model.local.speak import stream_human
from planner.paths import INDEX_PATH
from planner.reply.fill import render
from planner.session import load_session, save_session
from planner.session.review import (
    ask_switch_plain,
    bringing,
    choice,
    fourteen_ready,
    next_review,
    only_switch,
    pin_return,
    remember,
    shrinking,
    side_topic,
    stamp_review,
    stay_plain,
)

_SAFETY = (
    "我先停一下。如果低落、失眠、绝望或危险念头一直在，"
    "我先联系信任的人，或当地合格的医疗和心理支持。先不给自己排计划。"
)
_CYCLE = "我先不排九十天。今天先做一小步，留下能看见的记录，过十四天再看要不要拉长。"
_NO_MODEL = "我这边的模型还没接上。我可以先把话说具体一点：卡在哪一件事、今天有多少时间。"


def iter_page_answer(
    text: str,
    earlier=None,
    streamer=None,
    *,
    session: str | None = None,
    session_dir=None,
    today: date | None = None,
):
    """产出 (事件, 文字)。页面只显示 token，书名不单独贴在底下。"""
    opened = _open(text, session=session, session_dir=session_dir, today=today)
    if opened["kind"] == "fixed":
        yield ("token", opened["text"])
        return
    if opened.get("commit"):
        opened["commit"]()
    if opened.get("lead"):
        lead = opened["lead"]
        if not lead.endswith("\n"):
            lead += "\n"
        yield ("token", lead)
    if linked_weights() is None and streamer is None:
        if not opened.get("lead"):
            yield ("token", opened["hint"] or _NO_MODEL)
        return
    history = [] if opened.get("fresh") else (earlier or [])
    hint = opened["hint"]
    prompt = opened["prompt"]
    if streamer is None:

        def fn(user_text):
            return stream_human(user_text, history, hint)
    else:
        fn = streamer
    try:
        spoken = []
        for piece in _visible(_without_loop(fn(prompt))):
            if piece:
                spoken.append(piece)
                yield ("token", piece)
        if not "".join(spoken).strip() and not opened.get("lead"):
            yield ("token", opened["hint"] or "我听见了。今天先做一件最小的事，做完留个记号，明天再看。")
    except ModelError:
        if not opened.get("lead"):
            yield ("token", "这句话没说完。我换一种说法再问一次。")


def _open(user_text: str, *, session, session_dir, today: date | None) -> dict:
    current = today or date.today()
    if not INDEX_PATH.exists():
        build_index()
    segments = load_index()
    entries = load_entries()
    record = load_session(session, root=session_dir) if session else None
    text = user_text
    switched = False
    if record and choice(user_text) == "switch":
        switched = True
        if record.switch_text and only_switch(user_text):
            text = record.switch_text
        record.switch = ""
        record.switch_text = ""
    sheet = build_sheet(text, entries)
    if sheet.safety:
        return {"kind": "fixed", "text": _SAFETY}
    if record:
        pin_return(sheet, record)
        if record.switch and choice(user_text) == "stay" and not switched:
            record.switch = ""
            record.switch_text = ""
            save_session(record, session, session_dir)
            return {"kind": "fixed", "text": stay_plain(record)}
        if sheet.entry_id is None and not switched:
            return {
                "kind": "speak",
                "prompt": user_text.strip(),
                "hint": _continue_hint(record),
                "lead": "",
                "commit": None,
            }
        if not switched and side_topic(sheet, record):
            record.switch = f"要不要换到「{sheet.domain}」"
            record.switch_text = sheet.text
            save_session(record, session, session_dir)
            return {"kind": "fixed", "text": ask_switch_plain(sheet, record)}
        if fourteen_ready(record, sheet.text, current) and not sheet.capacity_low:
            sheet.has_fourteen_day_evidence = True
            if sheet.cycle_blocked:
                sheet.cycle_blocked = False
    shrink = bool(record) and not switched and sheet.entry_id == record.entry_id and shrinking(sheet.text)
    if shrink:
        sheet.capacity_low = True
        if sheet.entry_id == "cycle":
            sheet.cycle_blocked = True
    outcome = select(sheet, segments, entries)
    if sheet.cycle_blocked:
        _keep_switch_clear(record, switched, session, session_dir)
        return {"kind": "fixed", "text": _CYCLE}
    if outcome.status != "plan":
        _keep_switch_clear(record, switched, session, session_dir)
        hint = ""
        if outcome.kept:
            hint = _clip(outcome.kept[0].text, 60)
        return {"kind": "speak", "prompt": text.strip(), "hint": hint, "lead": "", "commit": None}
    template = render(outcome, segments)
    if "## 规划" not in template or "## 没筛中" in template:
        _keep_switch_clear(record, switched, session, session_dir)
        return {"kind": "speak", "prompt": text.strip(), "hint": "", "lead": "", "commit": None}
    same = bool(record) and record.entry_id == sheet.entry_id and not switched
    review_day = record.review_date if same else next_review(current)
    template = stamp_review(template, review_day, low=sheet.capacity_low)
    book = _clip(outcome.kept[0].text, 60) if outcome.kept else ""
    hint = _step_hint(template, book)
    lead = ""
    if record and same:
        lead = _lead(shrink, bringing(sheet.text))
    elif record and switched:
        lead = "主线换过来了，上一轮不并进这一份。"

    def commit():
        updated = remember(template, sheet, record, review_day, bringing(sheet.text))
        if updated is not None and session:
            save_session(updated, session, session_dir)

    return {
        "kind": "speak",
        "prompt": text.strip(),
        "hint": hint,
        "lead": lead,
        "fresh": bool(switched),
        "commit": commit if session else None,
    }


def _keep_switch_clear(record, switched: bool, session, session_dir) -> None:
    if session and record and switched:
        save_session(record, session, session_dir)


def _lead(shrink: bool, brought_now: bool) -> str:
    if shrink:
        return "上次那一步没做成，这次把它缩小。"
    if brought_now:
        return "上次的记录我看见了。"
    return "上次要留的记录还没贴来。"


def _continue_hint(record) -> str:
    return (
        f"还在「{record.entry_label}」这件事上。"
        f"上次那一步是：{_clip(record.action, 80)}。"
        f"{record.review_date}再看。"
    )


def _step_hint(template: str, book: str) -> str:
    action = _line(template, "- 最小动作：")
    evidence = _line(template, "- 证据：")
    parts = [part for part in (book, f"今天先做：{_clip(action, 80)}" if action else "", f"留下：{_clip(evidence, 40)}" if evidence else "") if part]
    return "。".join(parts)


def _line(text: str, prefix: str) -> str:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :].strip()
    return ""


_LEAK = (
    "这本书没有直接写到",
    "用自己的话",
    "不要照抄",
    "不要写",
    "书里的话只是参考",
    "书里的参考",
    "我现在说",
    "我已经谈过",
    "我已经聊过",
    "请继续聊",
    "我说 ",
    "你回答",
    "可以借用的意思",
)


_MARKS = str.maketrans("", "", "*`#")
_LIST = re.compile(r"^\d+\s*[\.、．]\s*")
_BULLET = re.compile(r"^[-•]\s*")


def _visible(pieces):
    """丢掉提示词，并去掉 **、# 和编号这类记号。"""
    pending = ""
    for piece in pieces:
        pending += piece.translate(_MARKS)
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            kept = _keep_line(line)
            if kept:
                yield kept + "\n"
    kept = _keep_line(pending)
    if kept:
        yield kept


def _keep_line(line: str) -> str:
    text = _BULLET.sub("", _LIST.sub("", line.strip()))
    if not text or any(mark in text for mark in _LEAK):
        return ""
    return text


def _without_loop(pieces):
    """同一小段话出现第三次就停下，避免小模型把一句说个不停。"""
    got = ""
    for piece in pieces:
        if not piece:
            continue
        candidate = got + piece
        tail = candidate[-12:]
        if len(tail) >= 12 and candidate[: -len(piece)].count(tail) >= 2:
            break
        got = candidate
        yield piece


def _clip(text: str, limit: int = 80) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rstrip("，,。 ") + "…"
