from datetime import date
from pathlib import Path

from planner.cli.intake import build_sheet
from planner.corpus.index import build_index, load_index
from planner.filter.entries import load_entries
from planner.filter.select import select
from planner.model import ModelError
from planner.model.context import resolve_summary
from planner.model.dispatch import generate
from planner.model.package import build_package
from planner.paths import FIXTURES, INDEX_PATH
from planner.reply.check import checked_draft
from planner.model.local.speak import clean_own, speak
from planner.reply.fill import render, render_model, render_own, render_safety, situation_lines
from planner.session import load_session, save_session
from planner.session.review import (
    ASK,
    ask_switch,
    bringing,
    choice,
    fourteen_ready,
    hold_question,
    next_gap,
    insert_review,
    next_review,
    only_switch,
    pin_return,
    place_in_cycle,
    remember,
    review_note,
    shrinking,
    side_topic,
    stamp_review,
    stay_reply,
    switched_note,
)
from planner.yamlutil import parse_yaml


def answer(
    user_text: str,
    *,
    rebuild: bool = False,
    context: str | None = None,
    model: str | None = None,
    transport=None,
    own: bool = False,
    speaker=None,
    session: str | None = None,
    session_dir: Path | None = None,
    today: date | None = None,
    follow_up: bool = False,
) -> str:
    """整理筛选单，筛选，用留下的段填回复。

    model 为空时不调用模型。启用之后，没有合格摘要、调用失败或路径对不上，都退回同一份模板。
    给出会话名时，先读上一份记录，写完规划再更新同一份。没给会话名时不读写。
    follow_up 为真时，和页面一样缺一项只问那一项，答完才写四块回复。
    """
    current = today or date.today()
    if rebuild or not INDEX_PATH.exists():
        build_index()
    segments = load_index()
    entries = load_entries()
    record = load_session(session, root=session_dir)
    prior = record.to_dict() if record else None
    sheet_text = user_text
    if follow_up and record and record.awaiting and choice(user_text) != "switch":
        sheet_text = record.context.rstrip("。") + "。" + user_text.strip()
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
        nearest = next((entry.label for entry in entries if entry.id == "recovery"), "低谷、恢复")
        return render_safety(sheet, segments, nearest)
    if record:
        pin_return(sheet, record)
        if record.switch and choice(user_text) == "stay" and not switched:
            record.switch = ""
            record.switch_text = ""
            save_session(record, session, session_dir)
            return stay_reply(record)
        if not switched and not (follow_up and record.awaiting) and side_topic(sheet, record):
            record.switch = f"要不要换到「{sheet.domain}」"
            record.switch_text = sheet.text
            save_session(record, session, session_dir)
            return ask_switch(sheet, record)
        if fourteen_ready(record, sheet.text, current) and not sheet.capacity_low:
            sheet.has_fourteen_day_evidence = True
            if sheet.cycle_blocked:
                sheet.cycle_blocked = False
    shrink = bool(record) and not switched and sheet.entry_id == record.entry_id and shrinking(sheet.text)
    if shrink:
        sheet.capacity_low = True
        if sheet.entry_id == "cycle":
            sheet.cycle_blocked = True
    if follow_up and session and sheet.entry_id and not sheet.cycle_blocked and not (record and record.action):
        gap = next_gap(lookup, sheet, record.awaiting if record else "")
        if gap:
            hold_question(session, session_dir, sheet, gap, lookup)
            return ASK[gap] + "\n"
    outcome = select(sheet, segments, entries)
    reply = _finish(
        outcome,
        segments,
        sheet,
        prior,
        context=context,
        model=model,
        transport=transport,
        own=own,
        speaker=speaker,
    )
    if not session:
        return reply
    if "## 规划" not in reply or "## 没筛中" in reply:
        if record and switched:
            save_session(record, session, session_dir)
        return reply
    same = bool(record) and record.action and record.entry_id == sheet.entry_id and not switched
    review_day = record.review_date if same else next_review(current)
    reply = stamp_review(reply, review_day, low=sheet.capacity_low)
    if record and record.action and sheet.entry_id == "cycle":
        reply = place_in_cycle(reply, record.action)
    if record and same:
        decision = "缩小" if shrink else ("继续" if bringing(sheet.text) else "证据还没贴来")
        reply = insert_review(reply, review_note(record, decision, bringing(sheet.text)))
    elif record and switched:
        reply = insert_review(reply, switched_note(record))
    updated = remember(reply, sheet, record, review_day, bringing(sheet.text))
    if updated is not None:
        save_session(updated, session, session_dir)
    return reply


def _finish(outcome, segments, sheet, prior, *, context, model, transport, own, speaker) -> str:
    template = render(outcome, segments)
    if outcome.status != "plan":
        if own and model != "api" and not sheet.cycle_blocked:
            prose = _own_prose(sheet, outcome.nearest_title, speaker)
            if prose:
                return render_own(outcome, prose)
        return template
    if "## 规划" not in template:
        return template
    found = situation_draft(outcome, prior, context=context, model=model, transport=transport)
    if found is None:
        return template
    draft, summary = found
    extra = situation_lines(
        draft.situation,
        title=summary.title,
        day=summary.date,
        source=summary.source,
        scope=summary.scope,
    )
    return render_model(outcome, segments, action=draft.action, situation=extra)


def situation_draft(outcome, prior, *, context, model, transport=None):
    """筛中且摘要合格时，返回核对过的形势稿。否则为空，调用方仍用填段。"""
    if not model or outcome.status != "plan":
        return None
    summary = resolve_summary(context)
    if summary is None:
        return None
    package = build_package(outcome.sheet, outcome.kept, summary, prior)
    try:
        raw = generate(model, package, transport=transport)
    except ModelError:
        return None
    draft = checked_draft(raw, outcome, summary)
    if draft is None:
        return None
    return draft, summary


def _own_prose(sheet, nearest: str, speaker) -> str:
    fn = speaker or speak
    try:
        raw = fn(sheet, nearest)
    except ModelError:
        return ""
    if not isinstance(raw, str):
        return ""
    return clean_own(raw)


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
