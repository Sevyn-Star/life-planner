"""页面上的白话回答。书里的段落只作参考，模型的字按片段往外送。"""

import re

from planner.cli.intake import build_sheet
from planner.corpus.index import build_index, load_index
from planner.filter.entries import load_entries
from planner.filter.select import select
from planner.model import ModelError
from planner.model.local.client import linked_weights
from planner.model.local.speak import stream_human
from planner.paths import INDEX_PATH

_SAFETY = (
    "我先停一下。如果低落、失眠、绝望或危险念头一直在，"
    "我先联系信任的人，或当地合格的医疗和心理支持。先不给自己排计划。"
)
_CYCLE = "我先不排九十天。今天先做一小步，留下能看见的记录，过十四天再看要不要拉长。"
_NO_MODEL = "我这边的模型还没接上。我可以先把话说具体一点：卡在哪一件事、今天有多少时间。"


def iter_page_answer(text: str, earlier=None, streamer=None):
    """产出 (事件, 文字)。页面只显示 token，书名不单独贴在底下。"""
    prepared = _prepare(text, earlier or [])
    if prepared["kind"] == "fixed":
        yield ("token", prepared["text"])
        return
    if linked_weights() is None and streamer is None:
        yield ("token", _NO_MODEL)
        return
    if streamer is None:
        history = prepared["earlier"]
        hint = prepared["hint"]

        def fn(prompt):
            return stream_human(prompt, history, hint)
    else:
        fn = streamer
    try:
        spoken = []
        for piece in _visible(_without_loop(fn(prepared["prompt"]))):
            if piece:
                spoken.append(piece)
                yield ("token", piece)
        if not "".join(spoken).strip():
            yield ("token", "我听见了。今天先做一件最小的事，做完留个记号，明天再看。")
    except ModelError:
        yield ("token", "这句话没说完。我换一种说法再问一次。")


def _prepare(text: str, earlier: list) -> dict:
    if not INDEX_PATH.exists():
        build_index()
    entries = load_entries()
    sheet = build_sheet(text, entries)
    if sheet.safety:
        return {"kind": "fixed", "text": _SAFETY}
    outcome = select(sheet, load_index(), entries)
    if sheet.cycle_blocked:
        return {"kind": "fixed", "text": _CYCLE}
    hint = ""
    if outcome.status == "plan" and outcome.kept:
        hint = _clip(outcome.kept[0].text, 60)
    return {"kind": "model", "prompt": text.strip(), "hint": hint, "earlier": earlier}


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
