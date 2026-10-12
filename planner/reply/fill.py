import re

from planner.cli.intake import Sheet
from planner.corpus.segment import Segment
from planner.filter.entries import Entry
from planner.filter.select import REASONS, Outcome

FOOTER = (
    "依据来自韩先凯（笔名：离谱）《人生进阶指南》，正文 CC BY-NC 4.0。"
    "引用这些段落不表示作者为本项目背书。"
)
_INSTRUCTION = (
    "先",
    "写下",
    "填写",
    "保存",
    "记录",
    "选择",
    "完成",
    "打开",
    "留下",
    "复制",
    "检查",
    "走",
    "最小动作",
    "最小版本",
    "最小任务",
    "最小输出",
)
_NARRATIVE = ("我曾经", "我那时", "后来我", "我没有资格", "我高中")


def render(outcome: Outcome, segments: list[Segment]) -> str:
    if outcome.status != "plan":
        return _reject(outcome)
    return _plan(outcome, segments)


def render_safety(sheet: Sheet, segments: list[Segment], nearest: str) -> str:
    quote, segment = _safety_quote(segments)
    lines = [
        "## 筛选单",
        "",
        *_sheet_lines(sheet),
        "",
        "## 先停在这里",
        "",
        "持续的低落、失眠、绝望或危险念头，优先联系可信的人和当地合格的医疗或心理支持。这里先停住，不继续做成长规划。",
        "",
    ]
    if quote and segment:
        lines.append(quote)
        lines.append(f"出处：{segment.cite_path()} · {segment.title} · {segment.kind}")
        lines.append("")
    lines.append(f"最接近的入口是「{nearest}」。")
    lines.append("")
    lines.append(FOOTER)
    return "\n".join(lines).rstrip() + "\n"


def _reject(outcome: Outcome) -> str:
    lines = [
        "## 筛选单",
        "",
        *_sheet_lines(outcome.sheet),
        "",
        "## 没筛中",
        "",
        outcome.note,
        f"最接近的入口是「{outcome.nearest_title}」。",
        "可以把问题说得更具体，或承认它在这本书外面。",
        "",
        FOOTER,
    ]
    return "\n".join(lines).rstrip() + "\n"


def render_model(outcome: Outcome, segments: list[Segment], *, action: str, situation: list[str]) -> str:
    """最小动作换成已核对的模型稿，并在四块之后附上形势对照。其余仍用筛中段落。"""
    return _plan(outcome, segments, action=action, situation=situation)


def situation_lines(text: str, *, title: str, day: str, source: str, scope: str) -> list[str]:
    return [
        "## 形势对照",
        "",
        text.strip(),
        "",
        "信息种类：形势判断",
        f"材料：{title} · {day} · {source}",
        f"适用范围：{scope}",
    ]


def _plan(
    outcome: Outcome,
    segments: list[Segment],
    *,
    action: str | None = None,
    situation: list[str] | None = None,
) -> str:
    sheet = outcome.sheet
    entry = outcome.entry
    assert entry is not None
    suggestions = _suggestions(outcome.kept, sheet, entry)
    if not any(item[0] == "先做" for item in suggestions):
        outcome.note = "筛中的原文不足两段，所以不写规划。"
        outcome.nearest_title = entry.label
        return _reject(outcome)
    if action is None:
        action = next(item[1] for item in suggestions if item[0] == "先做")
    evidence = _evidence(outcome.kept, sheet, entry)
    lines = [
        "## 筛选单",
        "",
        *_sheet_lines(sheet),
        "",
        _kept_block(outcome),
        "",
        "## 主线",
        "",
        f"{sheet.question}。这一轮只走「{entry.label}」。旁边的事这次不并进同一份计划。",
        "",
        "## 规划",
        "",
        f"- 问题：{sheet.question}",
        f"- 基线：{_baseline(sheet)}",
        f"- 最小动作：{action}",
        f"- 证据：{evidence}",
        f"- 复查：{_review(sheet)}",
        "",
        "## 建议",
        "",
    ]
    for index, (kind, sentence, segment) in enumerate(suggestions, start=1):
        lines.append(f"{index}. {kind}：{sentence}")
        lines.append(f"   依据：{segment.cite_path()} · {segment.title} · {segment.kind}")
    lines.extend(
        [
            "",
            "## 下次开口可以带什么",
            "",
            _next_time(outcome.kept, entry),
            "",
        ]
    )
    if situation:
        lines.extend([*situation, ""])
    lines.append(FOOTER)
    return "\n".join(lines).rstrip() + "\n"


def _sheet_lines(sheet: Sheet) -> list[str]:
    facts = "；".join(sheet.facts) if sheet.facts else "尚未记录"
    return [
        f"- 主问题：{sheet.question}",
        f"- 领域：{sheet.domain}",
        f"- 已有事实：{facts}",
        f"- 容量：{sheet.capacity}",
        f"- 想要的结果：{sheet.goal}",
    ]


def _kept_block(outcome: Outcome) -> str:
    lines = ["留下的段落："]
    for segment in outcome.kept:
        lines.append(f"- {segment.cite_path()} · {segment.title} · {segment.kind}")
    counts = {reason: 0 for reason in REASONS}
    for _, reason in outcome.dropped:
        counts[reason] = counts.get(reason, 0) + 1
    summary = "；".join(f"{reason} {count}" for reason, count in counts.items() if count)
    if summary:
        lines.append(f"丢掉：{summary}。")
    return "\n".join(lines)


def _baseline(sheet: Sheet) -> str:
    if not sheet.facts:
        return "尚未记录"
    return "；".join(sheet.facts)


def _review(sheet: Sheet) -> str:
    if sheet.capacity_low:
        return "十四天后看这一次短动作留下的记录。这一轮不排长周期。"
    return "十四天后复测。没有这次留下的记录之前，不排长周期。"


def _next_time(kept: list[Segment], entry: Entry) -> str:
    hosts = [segment for segment in kept if not _pinned(segment, entry)]
    form = next((segment for segment in hosts if "/templates/" in segment.path), None)
    host = form or (hosts[0] if hosts else kept[0])
    return (
        f"回来时贴上这次留下的记录，对应「{host.title}」。"
        "有了它，才决定继续、缩小，还是换入口。"
        f"这一轮的入口仍是「{entry.label}」。"
    )


def _evidence(kept: list[Segment], sheet: Sheet, entry: Entry) -> str:
    hosts = [segment for segment in kept if not _pinned(segment, entry)]
    form = next((segment for segment in hosts if "/templates/" in segment.path), None)
    host = form or (hosts[0] if hosts else kept[0])
    sentence = _best_sentence(host.text, sheet, "do")
    if sentence and any(word in sentence for word in ("证据", "留下", "记录", "保存", "复制", "填写")):
        return f"做完后留下的记录对应「{host.title}」：{sentence} 文件：{host.cite_path()}。"
    recorded = _best_record_sentence(host.text, sheet)
    if recorded:
        return f"做完后留下的记录对应「{host.title}」：{recorded} 文件：{host.cite_path()}。"
    return f"做完后留下一页能核对的记录。文件：{host.cite_path()}。"


def _suggestions(kept: list[Segment], sheet: Sheet, entry: Entry) -> list[tuple[str, str, Segment]]:
    grouped: dict[str, list[tuple[str, Segment, int]]] = {"do": [], "dont": [], "stop": []}
    seen = set()
    for segment in kept:
        pinned = _pinned(segment, entry)
        for sentence in _candidates(segment.text, sheet):
            if sentence in seen:
                continue
            role = _role(sentence)
            if role is None or (pinned and role == "do"):
                continue
            seen.add(sentence)
            score = _action_score(sentence, sheet) if role == "do" else _role_score(sentence, role)
            grouped[role].append((sentence, segment, score))
    for role in grouped:
        grouped[role].sort(key=lambda item: (-item[2], len(item[0])))
    items: list[tuple[str, str, Segment]] = []
    for sentence, segment, _score in grouped["do"][:3]:
        items.append(("先做", sentence, segment))
    if grouped["dont"]:
        sentence, segment, _score = grouped["dont"][0]
        items.append(("先不做", sentence, segment))
    if grouped["stop"]:
        sentence, segment, _score = grouped["stop"][0]
        items.append(("出现这种情况就停", sentence, segment))
    if len(items) < 3:
        for sentence, segment, _score in grouped["do"][3:]:
            items.append(("先做", sentence, segment))
            if len(items) >= 3:
                break
    return items[:5]


def _best_sentence(text: str, sheet: Sheet, role: str) -> str | None:
    best = ""
    best_score = -1
    for sentence in _candidates(text, sheet):
        if _role(sentence) != role:
            continue
        score = _action_score(sentence, sheet) if role == "do" else _role_score(sentence, role)
        if score > best_score:
            best = sentence
            best_score = score
    return best or None


def _pinned(segment: Segment, entry: Entry) -> bool:
    return any(title in segment.title for title in entry.pin_titles)


def _best_record_sentence(text: str, sheet: Sheet) -> str | None:
    best = ""
    best_score = -1
    for sentence in _candidates(text, sheet):
        if not any(word in sentence for word in ("证据", "留下", "记录", "保存")):
            continue
        if _role(sentence) == "stop":
            continue
        score = _action_score(sentence, sheet)
        if score > best_score:
            best = sentence
            best_score = score
    return best or None


def _candidates(text: str, sheet: Sheet) -> list[str]:
    found = []
    seen = set()
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("```"):
            continue
        if set(line.replace(" ", "")) <= set("|-:"):
            continue
        pieces = _pieces(line)
        for piece in pieces:
            for sentence in re.split(r"[。！？；]", piece):
                sentence = re.sub(r"\s+", " ", sentence).strip(" -，,")
                if sentence in seen or not _usable(sentence, sheet):
                    continue
                seen.add(sentence)
                found.append(sentence)
    return found


def _pieces(line: str) -> list[str]:
    if not line.startswith("|"):
        return [re.sub(r"^(\d+\.|[-*])\s*", "", line)]
    cells = [
        cell.strip()
        for cell in line.strip("|").split("|")
        if cell.strip() and not set(cell.strip()) <= set("-: ")
    ]
    if len(cells) < 2 or len(cells[0]) > 18:
        return cells
    if cells[0] in {"档位", "模式", "任务", "日程", "天数", "层次", "资源", "观察"}:
        return []
    action = next(
        (
            cell
            for cell in cells[1:]
            if any(word in cell for word in ("分钟", "最小", "留下", "证据", "保存", "写", "走", "停止", "暂停"))
        ),
        cells[-1],
    )
    if action == cells[0]:
        return cells
    return [f"{cells[0]}：{action}"]


def _usable(sentence: str, sheet: Sheet) -> bool:
    if "http" in sentence or " — " in sentence or sentence.count("/") >= 2:
        return False
    if len(sentence) < 8:
        return False
    if len(sentence) < 12 and not sentence.startswith(("不要", "先", "暂停", "停止")):
        return False
    if len(sentence) > 160:
        return False
    if not sheet.has_fourteen_day_evidence and any(
        token in sentence for token in ("九十", "90-day", "90 天", "part-5/")
    ):
        return False
    if sentence.endswith(("：", ":")):
        if any(word in sentence for word in ("我会", "什么时候", "哪一个")):
            return False
        body = sentence[:-1]
        if "/" in body or len(body) < 18 or not any(word in body for word in _INSTRUCTION):
            return False
    return True


def _role(sentence: str) -> str | None:
    if any(word in sentence for word in ("危险念头", "专业评估", "医疗或心理", "合格的医疗")):
        return "stop"
    if sentence.startswith("如果") and "专业支持" in sentence:
        return "stop"
    probe = sentence.replace("不暂停", "").replace("不必暂停", "")
    if any(word in probe for word in ("停止", "做不到", "恶化", "就停")):
        return "stop"
    if sentence.startswith("先") and not sentence.startswith(("先不", "先不要")):
        return "do"
    if sentence.startswith(("不要", "先不", "不必", "暂停")):
        return "dont"
    if "不要" in sentence and len(sentence) <= 36:
        return "dont"
    if "暂停" in probe and "最小" not in sentence:
        return "dont"
    if any(word in sentence for word in ("无字幕", "不看完整字幕")):
        return "do"
    if sentence.startswith(("恢复日", "降档模式")):
        return "do"
    hits = [word for word in _INSTRUCTION if word in sentence]
    if hits == ["选择"] and ("工作选择" in sentence or "不是" in sentence):
        return None
    if hits:
        return "do"
    return None


def _action_score(sentence: str, sheet: Sheet) -> int:
    score = 0
    if any(word in sentence for word in ("最小动作", "最小版本", "最小任务", "最小输出", "五分钟")):
        score += 6
    if "分钟" in sentence:
        score += 4
    if sentence.startswith("先"):
        score += 3
    if any(word in sentence for word in ("写下", "填写", "保存", "复制")):
        score += 2
    if "完成" in sentence and "完成标准" not in sentence:
        score += 2
    if "先填" in sentence or "写完就去做" in sentence:
        score += 4
    if "完成标准是" in sentence:
        score -= 6
    if any(word in sentence for word in ("下一步", "先做调查", "可被推翻")):
        score += 3
    if "字幕" in sheet.text and any(word in sentence for word in ("无字幕", "不看完整字幕")):
        score += 8
    if re.match(r"^(迁移|执行动作|抓主旨|找关键|追踪关系|进入互动)", sentence):
        score -= 5
    if "后再" in sentence:
        score -= 5
    if re.search(r"\d+\s*[–—-]\s*\d+\s*分钟|\d+\s*分钟|几分钟|十分钟", sentence):
        score += 5
    if re.match(r"第\s*\d+", sentence):
        score -= 2
    if any(phrase in sentence for phrase in _NARRATIVE):
        score -= 8
    if sentence.endswith("？"):
        score -= 3
    if len(sentence) > 70:
        score -= 3
    if sheet.capacity_low:
        if any(word in sentence for word in ("分钟", "最小", "今天")):
            score += 4
        if any(word in sentence for word in ("专业", "十四天", "七天", "两周")):
            score -= 6
        if "几分钟" in sheet.text and sentence.startswith("恢复日"):
            score += 12
        if "几分钟" in sheet.text and re.search(r"(1\d|\d{2})\s*[–—-]?\s*\d*\s*分钟", sentence):
            score -= 8
    return score


def _role_score(sentence: str, role: str) -> int:
    score = 1
    if role == "stop" and "危险念头" in sentence:
        score += 6
    if role == "stop" and any(word in sentence for word in ("专业", "停止", "做不到")):
        score += 4
    if role == "dont" and sentence.startswith(("不要", "先不", "暂停")):
        score += 3
    if len(sentence) <= 42:
        score += 1
    return score


def _safety_quote(segments: list[Segment]) -> tuple[str, Segment | None]:
    preferred = []
    fallback = []
    for segment in segments:
        if segment.path.endswith("docs/threads/part-0/reader-guide.md"):
            preferred.append(segment)
        elif segment.path.endswith("recovery.md"):
            fallback.append(segment)
    for segment in [*preferred, *fallback]:
        for piece in re.split(r"[。\n]", segment.text):
            piece = piece.strip()
            if "专业" in piece and any(word in piece for word in ("可信", "危险", "绝望", "医疗")):
                if len(piece) >= 12:
                    return piece + "。", segment
    return "", None
