"""确认权重在项目的 models 目录里，再把同一份输入包发给本机的 OpenAI 兼容服务。

不读取权重内容。服务要由本机事先启动。
"""

import os
from pathlib import Path

from planner.model import ModelError
from planner.model.chat import build_messages
from planner.model.http import post_chat
from planner.paths import CORPUS, MODELS_DIR


WEIGHT_NAME = "qwen2.5-0.5b-instruct-q4_k_m.gguf"


def linked_weights() -> Path | None:
    """没指定路径时，用项目 models/ 里这份已经下载的权重。"""
    raw = os.environ.get("PLANNER_LOCAL_WEIGHTS", "").strip()
    if raw:
        return checked_weights()
    path = MODELS_DIR / WEIGHT_NAME
    if path.is_file():
        return path.resolve()
    return None


def use_own_words(model: str | None) -> bool:
    """书没筛中时，只有这份本地权重可以自己组织语言。API 不走这条路。"""
    if model == "api":
        return False
    return linked_weights() is not None


def checked_weights() -> Path:
    raw = os.environ.get("PLANNER_LOCAL_WEIGHTS", "").strip()
    if not raw:
        raise ModelError("本地模型的权重路径还没有配置")
    path = Path(raw).expanduser().resolve()
    if not path.exists():
        raise ModelError("本地模型的权重不存在")
    models = MODELS_DIR.resolve()
    corpus = CORPUS.resolve()
    if path == corpus or corpus in path.parents:
        raise ModelError("本地模型的权重不放进书稿")
    if path != models and models not in path.parents:
        raise ModelError("本地模型的权重放在项目的 models 目录")
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
