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
    place_in_cycle,
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
    opened = _open(text, earlier=earlier, session=session, session_dir=session_dir, today=today)
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
    detail = opened.get("detail") or ""
    if detail:
        yield ("token", detail)
        return
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


def _open(user_text: str, *, earlier=None, session, session_dir, today: date | None) -> dict:
    current = today or date.today()
    sheet_text = user_text
    if _wants_detail(user_text):
        recovered = _earlier_question(earlier)
        if recovered:
            sheet_text = recovered
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
    lookup = text if text != user_text else sheet_text
    sheet = build_sheet(lookup, entries)
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
            if not _wants_detail(user_text):
                return {
                    "kind": "speak",
                    "prompt": user_text.strip(),
                    "hint": _continue_hint(record),
                    "lead": "",
                    "commit": None,
                }
            sheet.entry_id = record.entry_id
            sheet.domain = record.entry_label
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
    entering_cycle = bool(record) and sheet.entry_id == "cycle" and record.entry_id != "cycle" and record.action
    if record and record.action and sheet.entry_id == "cycle":
        template = place_in_cycle(template, record.action)
    book = "" if sheet.entry_id == "cycle" else (_clip(outcome.kept[0].text, 60) if outcome.kept else "")
    hint = _step_hint(template, book)
    detail = spoken_plan(template, outcome.kept)
    lead = ""
    if entering_cycle:
        lead = (
            "十四天的记录够了。原来那一步放进九十天。"
            f"今天仍是：{_clip(record.action, 80)}。"
            f"{review_day}再看。"
        )
    elif record and same:
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
        "detail": detail,
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


_DETAIL = ("详细", "展开", "说全", "具体一点", "具体些", "多说一点", "写完整")


def _wants_detail(text: str) -> bool:
    return any(mark in text for mark in _DETAIL)


def _continue_hint(record) -> str:
    return (
        f"还在「{record.entry_label}」这件事上。"
        f"上次那一步是：{_clip(record.action, 80)}。"
        f"{record.review_date}再看。"
    )


def _earlier_question(earlier) -> str:
    for item in reversed(earlier or []):
        if isinstance(item, dict) and item.get("role") == "user":
            content = str(item.get("content") or "").strip()
            if content and not _wants_detail(content):
                return content
    return ""


def spoken_plan(template: str, kept=None) -> str:
    """按点写出每一步要做什么。路径不进这段话。"""
    steps = _items(template, "先做：")
    avoids = _items(template, "先不做：")
    stops = _items(template, "出现这种情况就停：")
    known = {_clean(item) for item in (*steps, *avoids, *stops)}
    points = []
    for sentence in steps:
        points.append(_point(len(points) + 1, sentence, "怎么做", kept, known))
    for sentence in avoids:
        points.append(_point(len(points) + 1, sentence, "先不要这样做", kept, known))
    for sentence in stops:
        points.append(_point(len(points) + 1, sentence, "遇到这种情况就停", kept, known))
    if not points:
        action = _clean(_line(template, "- 最小动作："))
        if action:
            points.append(_point(1, action, "怎么做", kept, set()))
    review = _as_sentence(_clean(_line(template, "- 复查：")))
    if review:
        points.append(f"{len(points) + 1}. 到日子再看\n怎么做：{review}")
    return "\n\n".join(point for point in points if point)


def _point(index: int, sentence: str, lead: str, kept, known: set[str]) -> str:
    title = _clean(sentence)
    if not title:
        return ""
    extra = _after(title, kept, known)
    body = _as_sentence(title)
    if extra:
        body += extra
    return f"{index}. {title}\n{lead}：{body}"


def _after(sentence: str, kept, known: set[str]) -> str:
    if not kept:
        return ""
    host = next((segment for segment in kept if sentence in segment.text), None)
    if host is None:
        return ""
    rest = host.text.split(sentence, 1)[1].lstrip("。！？ \n")
    fields: list[str] = []
    intro = ""
    parts: list[str] = []

    def flush_fields() -> None:
        nonlocal intro
        labels = [label for label in fields if label]
        fields.clear()
        if not labels:
            return
        prefix = f"{intro}：" if intro else "写下这些："
        parts.append(prefix + "、".join(labels) + "。")
        intro = ""

    for raw in rest.splitlines():
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        if line.startswith("#") or line.startswith("|"):
            break
        plain = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        plain = re.sub(r"^(\d+\.|[-*])\s*", "", plain).strip().lstrip("。！？ ")
        if not plain or set(plain) <= set("-: "):
            continue
        if any(other and other != sentence and other in plain for other in known):
            break
        if plain.endswith(("：", ":")):
            if "。" in plain:
                sentence_part, _, tail = plain.rpartition("。")
                flush_fields()
                if sentence_part.strip():
                    parts.append(_as_sentence(sentence_part.strip()))
                plain = tail.strip()
            label = plain.rstrip("：: ").strip()
            if not label:
                continue
            if label.endswith(("记录", "写", "记下")) and len(label) <= 16:
                flush_fields()
                intro = label
            else:
                fields.append(label)
            if len(fields) >= 8:
                flush_fields()
            continue
        flush_fields()
        if len(plain) > 100 or len(parts) >= 4:
            break
        parts.append(_as_sentence(plain))
    flush_fields()
    return "".join(parts)


def _items(template: str, label: str) -> list[str]:
    found = []
    marker = f". {label}"
    for line in template.splitlines():
        if marker in line:
            found.append(line.split(marker, 1)[1].strip())
    return found


def _clean(text: str) -> str:
    text = re.sub(r"文件：\S+", "", text)
    text = re.sub(r"rensheng/\S+", "", text)
    text = re.sub(r"docs/[\w./-]+\.md", "", text)
    return " ".join(text.split()).strip(" ，,。")


def _as_sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return ""
    if text[-1] not in "。！？":
        text += "。"
    return text


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
