"""一个会话一份记录，放在 data/sessions/。

只记主线、选定入口、上次最小动作、要留下的证据、复查日期。
岔开话题时，把「要不要换」记在同一份里。密码、证件号、住址、病历和他人隐私不写入。
"""

import re
from dataclasses import dataclass
from pathlib import Path

from planner.cli.intake import redact
from planner.paths import SESSIONS_DIR
from planner.yamlutil import parse_yaml

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,40}$")


@dataclass
class Record:
    question: str
    entry_id: str
    entry_label: str
    action: str
    evidence: str
    review_date: str
    switch: str = ""
    switch_text: str = ""
    brought: str = ""
    awaiting: str = ""
    context: str = ""

    def to_dict(self) -> dict:
        return {
            "question": self.question,
            "entry_id": self.entry_id,
            "entry_label": self.entry_label,
            "action": self.action,
            "evidence": self.evidence,
            "review_date": self.review_date,
            "switch": self.switch,
            "brought": self.brought,
            "awaiting": self.awaiting,
            "context": self.context,
        }


def load_session(session_id: str | None = None, *, root: Path | None = None) -> Record | None:
    """没有会话名，或文件不存在，就当作这一轮没有记忆。"""
    if not session_id:
        return None
    path = session_path(session_id, root)
    if not path.is_file():
        return None
    try:
        data = parse_yaml(path.read_text(encoding="utf-8"))
    except OSError:
        return None
    if not isinstance(data, dict):
        return None
    question = _text(data.get("question"))
    entry_id = _text(data.get("entry_id"))
    entry_label = _text(data.get("entry_label"))
    action = _text(data.get("action"))
    evidence = _text(data.get("evidence"))
    review_date = _text(data.get("review_date"))
    awaiting = _text(data.get("awaiting"))
    context = _text(data.get("context"))
    if awaiting:
        if not question:
            return None
        return Record(
            question=question,
            entry_id=entry_id,
            entry_label=entry_label,
            action=action,
            evidence=evidence,
            review_date=review_date,
            switch=_text(data.get("switch")),
            switch_text=_text(data.get("switch_text")),
            brought=_text(data.get("brought")),
            awaiting=awaiting,
            context=context,
        )
    if not question or not entry_id or not entry_label or not action or not review_date:
        return None
    return Record(
        question=question,
        entry_id=entry_id,
        entry_label=entry_label,
        action=action,
        evidence=evidence,
        review_date=review_date,
        switch=_text(data.get("switch")),
        switch_text=_text(data.get("switch_text")),
        brought=_text(data.get("brought")),
    )


def delete_session(session_id: str, root: Path | None = None) -> None:
    path = session_path(session_id, root)
    if path.is_file():
        path.unlink()


def save_session(record: Record, session_id: str, root: Path | None = None) -> None:
    path = session_path(session_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = {
        "question": plain(record.question),
        "entry_id": plain(record.entry_id),
        "entry_label": plain(record.entry_label),
        "action": plain(record.action),
        "evidence": plain(record.evidence),
        "review_date": plain(record.review_date),
        "switch": plain(record.switch),
        "switch_text": plain(record.switch_text, limit=160),
        "brought": plain(record.brought, limit=160),
        "awaiting": plain(record.awaiting),
        "context": plain(record.context, limit=400),
    }
    lines = [f"{key}: {yaml_quote(value)}" for key, value in fields.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def session_path(session_id: str, root: Path | None = None) -> Path:
    if not _ID.fullmatch(session_id or ""):
        raise ValueError("会话名只能用字母、数字和连字符")
    return (root or SESSIONS_DIR) / f"{session_id}.yaml"


def _text(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def plain(text: str, limit: int = 180) -> str:
    cleaned = redact(text or "")
    cleaned = cleaned.replace("\n", " ").replace('"', "'").strip()
    return cleaned[:limit]


def yaml_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\") + '"'
