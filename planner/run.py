from planner.cli.intake import build_sheet
from planner.corpus.index import build_index, load_index
from planner.filter.entries import load_entries
from planner.filter.select import select
from planner.paths import FIXTURES, INDEX_PATH
from planner.reply.fill import render, render_safety
from planner.session import load_session
from planner.yamlutil import parse_yaml


def answer(user_text: str, *, rebuild: bool = False) -> str:
    """初版一轮：整理筛选单，筛选，用留下的段填回复。会话为空。"""
    if rebuild or not INDEX_PATH.exists():
        build_index()
    segments = load_index()
    entries = load_entries()
    sheet = build_sheet(user_text, entries)
    load_session(None)
    if sheet.safety:
        nearest = next((entry.label for entry in entries if entry.id == "recovery"), "低谷、恢复")
        return render_safety(sheet, segments, nearest)
    outcome = select(sheet, segments, entries)
    return render(outcome, segments)


def run_fixtures() -> list[str]:
    if not INDEX_PATH.exists():
        build_index()
    errors = []
    for path in sorted(FIXTURES.glob("*.md")):
        meta, body = _fixture(path.read_text(encoding="utf-8"))
        output = answer(body)
        for token in meta.get("must_include") or []:
            if token not in output:
                errors.append(f"{path.name} 缺少 {token}")
        for token in meta.get("must_exclude") or []:
            if token in output:
                errors.append(f"{path.name} 不该出现 {token}")
        choices = meta.get("any_include") or []
        if choices and not any(token in output for token in choices):
            errors.append(f"{path.name} 至少要出现其中一项：{choices}")
        if meta.get("expect") == "reject":
            for heading in ("## 主线", "## 规划", "## 建议", "## 下次开口可以带什么"):
                if heading in output:
                    errors.append(f"{path.name} 拒绝时不该有 {heading}")
        if errors and errors[-1].startswith(path.name):
            errors.append(output)
    return errors


def _fixture(text: str):
    if not text.startswith("---"):
        raise ValueError("验收问题缺少头部")
    end = text.find("\n---", 3)
    meta = parse_yaml(text[3:end])
    body = text[end + 4 :].strip()
    return meta, body
