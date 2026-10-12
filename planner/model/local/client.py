"""确认权重在项目外，再把同一份输入包发给本机的 OpenAI 兼容服务。

不读取权重内容，也不把权重拷进仓库。服务要由本机事先启动。
"""

import os
from pathlib import Path

from planner.model import ModelError
from planner.model.chat import build_messages
from planner.model.http import post_chat
from planner.paths import CORPUS, ROOT


def checked_weights() -> Path:
    raw = os.environ.get("PLANNER_LOCAL_WEIGHTS", "").strip()
    if not raw:
        raise ModelError("本地模型的权重路径还没有配置")
    path = Path(raw).expanduser().resolve()
    if not path.exists():
        raise ModelError("本地模型的权重不存在")
    root = ROOT.resolve()
    corpus = CORPUS.resolve()
    if path == root or root in path.parents or path == corpus or corpus in path.parents:
        raise ModelError("本地模型的权重要放在项目外面")
    return path


def complete(package: dict, *, transport=None, opener=None) -> str:
    messages = build_messages(package)
    if transport is not None:
        return transport(messages, package)
    checked_weights()
    url = os.environ.get("PLANNER_LOCAL_URL", "").strip().rstrip("/")
    model = os.environ.get("PLANNER_LOCAL_MODEL", "").strip()
    if not url or not model:
        raise ModelError("本地模型还没有配置地址或模型名")
    return post_chat(
        url + "/chat/completions",
        model,
        messages,
        {"Content-Type": "application/json"},
        opener=opener,
        timeout=120,
    )
