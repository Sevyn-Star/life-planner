"""把一段对话里已经说过的话收成计划和导图，不另编步骤。

路径、章节标题和信息种类只放进计划文档。导图只用步骤标题。
"""

import re

from planner.cli.intake import build_sheet, redact
from planner.corpus.index import build_index, load_index
from planner.filter.entries import load_entries
from planner.filter.select import select
from planner.paths import INDEX_PATH
from planner.reply.fill import FOOTER

_DETAIL = ("详细计划", "详细规划", "展开", "说全", "具体一点", "具体些", "多说一点", "写完整")
_POINT = re.compile(r"^(\d+)\.\s+(.+)$")
_LEADS = (
    ("先不要这样做：", "avoid"),
    ("遇到这种情况就停：", "stop"),
    ("怎么做：", "step"),
)
_BOOK_KINDS = ("研究结论", "个人经验", "待验证假设")
_SITUATION_LINE = ("形势判断：", "材料：", "适用范围：")


def compile_messages(messages, title: str = "", session=None) -> dict:
    said = []
    latest = []
    latest_text = ""
    for item in messages or []:
        if not isinstance(item, dict):
            continue
        content = redact(str(item.get("content") or "")).strip()
        if not content:
            continue
        if item.get("role") == "user":
            if not _detail_only(content):
                said.append(" ".join(content.split()))
            continue
        if item.get("role") == "assistant":
            found = _points(content)
            if found:
                latest = found
                latest_text = content
    question = said[0] if said else (title.strip() or "这段对话")
    steps = [point for point in latest if point["kind"] == "step"]
    avoid = [point for point in latest if point["kind"] == "avoid"]
    stop = [point for point in latest if point["kind"] == "stop"]
    review = next((point for point in latest if point["kind"] == "review"), None)
    if review is None and session is not None and getattr(session, "review_date", ""):
        review = {"title": "到日子再看", "how": f"{session.review_date} 再看这次留下的记录。", "kind": "review"}
    if not steps and not avoid and not stop and not review:
        steps = _fallback_steps(messages)
    cited = _cite(_lookup(said) or question, [*steps, *avoid, *stop])
    entry = getattr(session, "entry_label", "") if session is not None else ""
    situation = _situation(latest_text)
    return {
        "title": title.strip() or _clip(question, 18),
        "question": question,
        "entry": entry,
        "said": said,
        "steps": steps,
        "avoid": avoid,
        "stop": stop,
        "review": review,
        "situation": situation,
        "notice": FOOTER if cited else "",
    }


def _detail_only(text: str) -> bool:
    bare = text.strip().strip("。！？!?. ")
    return bare in set(_DETAIL)


def _lookup(said: list[str]) -> str:
    parts = [part.strip().rstrip("。") for part in said if part.strip()]
    return "。".join(parts)


def _points(text: str) -> list[dict]:
    stripped = text.strip()
    if not stripped:
        return []
    lines = stripped.splitlines()
    start = next((index for index, line in enumerate(lines) if _POINT.match(line.strip())), None)
    if start is None:
        return []
    body = "\n".join(lines[start:])
    found = []
    for block in re.split(r"\n(?=\d+\.\s)", body):
        point = _block(block.strip())
        if point:
            found.append(point)
    return found


def _block(block: str) -> dict | None:
    lines = [line.strip() for line in block.splitlines() if line.strip()]
    if not lines:
        return None
    matched = _POINT.match(lines[0])
    if not matched:
        return None
    title = matched.group(2).strip()
    rest = "\n".join(lines[1:]).strip()
    kind = "step"
    how = _drop_situation(rest)
    for prefix, name in _LEADS:
        if how.startswith(prefix):
            kind = name
            how = how[len(prefix) :].strip()
            break
    if title.startswith(("到日子再看", "复查")):
        kind = "review"
    return {"title": title, "how": how, "kind": kind}


def _drop_situation(text: str) -> str:
    kept = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(_SITUATION_LINE):
            continue
        kept.append(raw)
    return "\n".join(kept).strip()


def _situation(text: str) -> dict | None:
    if "形势判断：" not in text:
        return None
    body = text.split("形势判断：", 1)[1]
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    judgment = lines[0] if lines else ""
    material = ""
    scope = ""
    for line in lines[1:]:
        if line.startswith("材料："):
            material = line.removeprefix("材料：").strip()
        elif line.startswith("适用范围："):
            scope = line.removeprefix("适用范围：").strip()
    parts = [part.strip() for part in material.split("·")]
    if not judgment:
        return None
    return {
        "kind": "形势判断",
        "text": judgment,
        "title": parts[0] if parts else "",
        "date": parts[1] if len(parts) > 1 else "",
        "source": parts[2] if len(parts) > 2 else "",
        "scope": scope,
    }


def _cite(question: str, points: list[dict]) -> bool:
    kept = _kept(question)
    cited = False
    for point in points:
        if point.get("kind") == "review":
            continue
        host = _host(point.get("title") or "", kept)
        if host is None or host.kind not in _BOOK_KINDS:
            continue
        point["path"] = host.cite_path()
        point["chapter"] = host.title
        point["info"] = host.kind
        cited = True
    return cited


def _kept(question: str):
    text = question.strip()
    if not text:
        return []
    if not INDEX_PATH.exists():
        build_index()
    entries = load_entries()
    sheet = build_sheet(text, entries)
    if sheet.safety or not sheet.entry_id or sheet.cycle_blocked:
        return []
    outcome = select(sheet, load_index(), entries)
    if outcome.status != "plan":
        return []
    return list(outcome.kept)


def _host(title: str, kept):
    needle = " ".join(title.split()).strip("。！？ ")
    if len(needle) < 8:
        return None
    for segment in kept:
        flat = " ".join(segment.text.split())
        if needle in flat:
            return segment
    return None


def _fallback_steps(messages) -> list[dict]:
    last = ""
    for item in messages or []:
        if isinstance(item, dict) and item.get("role") == "assistant":
            content = redact(str(item.get("content") or "")).strip()
            if content:
                last = content
    if not last:
        return []
    steps = []
    for raw in re.split(r"[\n。]", last):
        line = " ".join(raw.split()).strip(" ，,")
        if len(line) < 8:
            continue
        steps.append({"title": _clip(line, 42), "how": line if line.endswith("。") else line + "。", "kind": "step"})
        if len(steps) >= 6:
            break
    return steps


def _clip(text: str, limit: int) -> str:
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[:limit].rstrip("，,。 ") + "…"
