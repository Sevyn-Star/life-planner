"""页面上的多段对话。每段一个文件，打开时读回全部记录。"""

import json
import re
from datetime import datetime

from planner.paths import CHATS_DIR

_ID = re.compile(r"^[a-z0-9]{8,32}$")


def list_chats() -> list[dict]:
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    found = []
    for path in CHATS_DIR.glob("*.json"):
        data = _read(path)
        if data is None:
            continue
        found.append(
            {
                "id": data["id"],
                "title": data["title"],
                "note": data["note"],
                "updated": data["updated"],
            }
        )
    found.sort(key=lambda item: item["updated"], reverse=True)
    return found


def load_chat(chat_id: str) -> dict | None:
    path = _path(chat_id)
    if path is None or not path.is_file():
        return None
    return _read(path)


def save_chat(chat_id: str, messages: list, title: str | None = None, note: str | None = None) -> dict:
    path = _path(chat_id)
    if path is None:
        raise ValueError("对话编号不对")
    existing = _read(path) if path.is_file() else None
    kept = _messages(messages)
    if isinstance(title, str) and title.strip():
        chosen = " ".join(title.split())[:32]
    elif title is None and existing and existing.get("title"):
        chosen = existing["title"]
    else:
        chosen = _title_from(kept)
    if isinstance(note, str):
        remark = " ".join(note.split())[:80]
    elif existing:
        remark = existing.get("note") or ""
    else:
        remark = ""
    data = {
        "id": chat_id,
        "title": chosen,
        "note": remark,
        "updated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "messages": kept,
    }
    CHATS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"id": chat_id, "title": chosen, "note": remark, "updated": data["updated"]}


def _title_from(messages: list[dict]) -> str:
    for item in messages:
        if item["role"] == "user" and item["content"].strip():
            return " ".join(item["content"].split())[:18]
    return "新的对话"


def _path(chat_id: str):
    if not isinstance(chat_id, str) or not _ID.fullmatch(chat_id):
        return None
    return CHATS_DIR / f"{chat_id}.json"


def _read(path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or not _ID.fullmatch(str(data.get("id", ""))):
        return None
    return {
        "id": data["id"],
        "title": str(data.get("title") or "新的对话"),
        "note": " ".join(str(data.get("note") or "").split())[:80],
        "updated": str(data.get("updated") or ""),
        "messages": _messages(data.get("messages")),
    }


def _messages(messages) -> list[dict]:
    if not isinstance(messages, list):
        return []
    kept = []
    for item in messages:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        kept.append({"role": role, "content": content})
    return kept
