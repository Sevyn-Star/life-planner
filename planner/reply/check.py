"""核对模型稿。路径不在筛中清单里，或形势对照写出摘要里没有的数字，就整段作废。"""

import json
import re
from dataclasses import dataclass

from planner.filter.select import Outcome
from planner.model.context import Summary

_PATH = re.compile(r"(?:rensheng/)?((?:docs/[\w./-]+|README|SUMMARY)\.md)")
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_CYCLE = ("九十", "90天", "90-day", "90 天", "part-5/")
_BANNED = ("你一定能", "改变命运", "保证成功", "人人都该")
_KINDS = ("信息种类：研究结论", "信息种类：个人经验", "信息种类：待验证假设")


@dataclass(frozen=True)
class ModelDraft:
    action: str
    situation: str


def checked_draft(raw: str, outcome: Outcome, summary: Summary) -> ModelDraft | None:
    if _outside(raw, {segment.path for segment in outcome.kept}):
        return None
    try:
        data = _parse(raw)
    except (json.JSONDecodeError, ValueError):
        return None
    action = re.sub(r"\s+", " ", str(data.get("action") or "")).strip()
    situation = str(data.get("situation") or "").strip()
    if not action or not situation or len(action) < 8 or len(action) > 180 or len(situation) < 12 or len(situation) > 500:
        return None
    if action.startswith("#") or ("收紧" not in situation and "调整顺序" not in situation):
        return None
    blob = action + "\n" + situation
    if any(phrase in blob for phrase in _BANNED) or any(label in situation for label in _KINDS):
        return None
    if _outside(blob, {segment.path for segment in outcome.kept}):
        return None
    if _numbers(situation) - _summary_numbers(summary):
        return None
    allowed = _summary_numbers(summary) | _book_numbers(outcome)
    if _numbers(action) - allowed:
        return None
    if not outcome.sheet.has_fourteen_day_evidence and any(token in blob for token in _CYCLE):
        return None
    return ModelDraft(action=action, situation=situation)


def _parse(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("不是 JSON")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("不是对象")
    return data


def _outside(text: str, allowed: set[str]) -> bool:
    for match in _PATH.finditer(text):
        if match.group(1) not in allowed:
            return True
    return False


def _numbers(text: str) -> set[str]:
    return set(_NUMBER.findall(text))


def _summary_numbers(summary: Summary) -> set[str]:
    return _numbers("\n".join((summary.title, summary.date, summary.source, summary.scope, summary.body)))


def _book_numbers(outcome: Outcome) -> set[str]:
    found: set[str] = set()
    for segment in outcome.kept:
        found.update(_numbers(segment.text))
    return found
