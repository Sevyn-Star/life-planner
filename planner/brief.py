"""把一段对话里已经说过的话收成计划和导图，不另编步骤。"""

import re

from planner.cli.intake import redact

_DETAIL = ("详细计划", "详细规划", "展开", "说全", "具体一点", "具体些", "多说一点", "写完整")
_POINT = re.compile(r"^(\d+)\.\s+(.+)$")
_LEADS = (
    ("先不要这样做：", "avoid"),
    ("遇到这种情况就停：", "stop"),
    ("怎么做：", "step"),
)


def compile_messages(messages, title: str = "", session=None) -> dict:
    said = []
    latest = []
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
    question = said[0] if said else (title.strip() or "这段对话")
    steps = [point for point in latest if point["kind"] == "step"]
    avoid = [point for point in latest if point["kind"] == "avoid"]
    stop = [point for point in latest if point["kind"] == "stop"]
    review = next((point for point in latest if point["kind"] == "review"), None)
    if review is None and session is not None and getattr(session, "review_date", ""):
        review = {"title": "到日子再看", "how": f"{session.review_date} 再看这次留下的记录。", "kind": "review"}
    if not steps and not avoid and not stop and not review:
        steps = _fallback_steps(messages)
    entry = getattr(session, "entry_label", "") if session is not None else ""
    return {
        "title": title.strip() or _clip(question, 18),
        "question": question,
        "entry": entry,
        "said": said,
        "steps": steps,
        "avoid": avoid,
        "stop": stop,
        "review": review,
    }


def _detail_only(text: str) -> bool:
    bare = text.strip().strip("。！？!?. ")
    return bare in set(_DETAIL)


def _points(text: str) -> list[dict]:
    stripped = text.strip()
    if not stripped or not _POINT.match(stripped.splitlines()[0].strip()):
        return []
    found = []
    for block in re.split(r"\n(?=\d+\.\s)", stripped):
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
    how = rest
    for prefix, name in _LEADS:
        if rest.startswith(prefix):
            kind = name
            how = rest[len(prefix) :].strip()
            break
    if title.startswith(("到日子再看", "复查")):
        kind = "review"
    return {"title": title, "how": how, "kind": kind}


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
