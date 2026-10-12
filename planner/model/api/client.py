"""调用 OpenAI 兼容接口。PLANNER_API_KEY 不写入仓库，也不写入会话。"""

import os

from planner.model import ModelError
from planner.model.chat import build_messages
from planner.model.http import post_chat


def complete(package: dict, *, transport=None, opener=None) -> str:
    messages = build_messages(package)
    if transport is not None:
        return transport(messages, package)
    key = os.environ.get("PLANNER_API_KEY", "").strip()
    model = os.environ.get("PLANNER_API_MODEL", "").strip()
    if not key or not model:
        raise ModelError("API 还没有配置密钥或模型名")
    base = os.environ.get("PLANNER_API_BASE", "https://api.openai.com/v1").rstrip("/")
    return post_chat(
        base + "/chat/completions",
        model,
        messages,
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        opener=opener,
        timeout=45,
    )
