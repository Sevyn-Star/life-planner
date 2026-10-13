"""用项目里的 Qwen2.5 0.5B 权重，在书没筛中时组织一段自己的话。"""

import contextlib
import os
import re
import sys

from planner.model import ModelError
from planner.model.local.client import linked_weights

_PATH = re.compile(r"rensheng/|docs/[\w./-]+\.md|https?://", re.IGNORECASE)
_HEADING = re.compile(r"^#{1,6}\s")
_KIND = re.compile(r"信息种类\s*[:：]")
_LOADED: dict[str, object] = {}
SYSTEM = (
    "书里没有对上的段落。你用自己的话，根据筛选单写今天能做的一步。"
    "用三四句中文，包含一个最小动作、要留下的记录、什么时候再看。"
    "最接近的入口只说明书里哪一章比较近，不要把它写成今天要读的任务，也不要假装书里有答案。"
    "不要写文件路径，不要说这是书里的话，不要写成研究结论、个人经验、待验证假设或形势判断。"
    "不要写股价、买卖价、九十天安排，也不要写「你一定能」「改变命运」。"
)


def clean_own(text: str) -> str:
    kept = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or _HEADING.match(line) or _PATH.search(line) or _KIND.search(line):
            continue
        if "九十" in line or "90天" in line or "90 天" in line:
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def speak(sheet, nearest: str) -> str:
    path = linked_weights()
    if path is None:
        raise ModelError("本地模型的权重不存在")
    facts = "；".join(sheet.facts) if sheet.facts else "尚未记录"
    user = (
        f"主问题：{sheet.question}\n"
        f"领域：{sheet.domain}\n"
        f"已有事实：{facts}\n"
        f"容量：{sheet.capacity}\n"
        f"最接近的入口：{nearest}\n"
        f"想要的结果：{sheet.goal}\n"
        "请写今天能做的动作、要留下的记录、什么时候再看。不要只重复入口标题。"
    )
    try:
        with _quiet_stderr():
            result = _llama(path).create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=220,
            )
        content = result["choices"][0]["message"]["content"]
    except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
        raise ModelError("本地模型没有返回可用回复") from exc
    if not isinstance(content, str) or not content.strip():
        raise ModelError("本地模型没有返回可用回复")
    return content


HUMAN = "用口语回我，像朋友。先接住我的话，再把今天这一步说完。写到句号再停，不要停在半句。"


def stream_human(prompt: str, earlier=None, hint: str = ""):
    """按模型吐出的片段往外送，给页面一边到一边显示。"""
    path = linked_weights()
    if path is None:
        raise ModelError("本地模型的权重不存在")
    system = HUMAN if not hint else HUMAN + "可以借用的意思：" + hint
    messages = [{"role": "system", "content": system}]
    messages.extend(_turns(earlier))
    messages.append({"role": "user", "content": prompt})
    try:
        with _quiet_stderr():
            chunks = _llama(path).create_chat_completion(
                messages=messages,
                temperature=0.6,
                max_tokens=512,
                repeat_penalty=1.25,
                stream=True,
            )
            pending = ""
            cut = False
            for chunk in chunks:
                choice = chunk["choices"][0]
                if choice.get("finish_reason") == "length":
                    cut = True
                delta = choice.get("delta") or {}
                piece = delta.get("content")
                if piece is None:
                    piece = choice.get("text") or ""
                if not piece:
                    continue
                pending += piece
                while True:
                    end = _sentence_end(pending)
                    if end is None:
                        break
                    yield pending[: end + 1]
                    pending = pending[end + 1 :]
            if pending:
                kept = finish_at_sentence(pending, cut=cut)
                if kept:
                    yield kept
    except (KeyError, TypeError, ValueError, OSError, RuntimeError) as exc:
        raise ModelError("本地模型没有返回可用回复") from exc


def finish_at_sentence(text: str, *, cut: bool) -> str:
    """字数到顶时，丢掉最后一个没写完的句子。"""
    if not cut:
        return text
    last = max((text.rfind(mark) for mark in "。！？\n"), default=-1)
    if last < 0:
        return ""
    return text[: last + 1]


def _sentence_end(text: str) -> int | None:
    positions = [text.find(mark) for mark in "。！？\n" if mark in text]
    if not positions:
        return None
    return min(positions)


def _turns(earlier) -> list[dict]:
    turns = []
    for item in (earlier or [])[-6:]:
        if isinstance(item, dict):
            role = item.get("role")
            content = item.get("content")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            role, content = item
        else:
            continue
        if role not in {"user", "assistant"} or not isinstance(content, str):
            continue
        content = " ".join(content.split())
        if content:
            turns.append({"role": role, "content": content[:400]})
    return turns


def _llama(path):
    key = str(path)
    cached = _LOADED.get(key)
    if cached is not None:
        return cached
    try:
        from llama_cpp import Llama
    except ImportError as exc:
        raise ModelError("还不能读取这份权重。需要安装 llama-cpp-python。") from exc
    threads = os.cpu_count() or 4
    try:
        with _quiet_stderr():
            model = Llama(
                model_path=key,
                n_ctx=2048,
                n_threads=min(threads, 8),
                verbose=False,
                chat_format="chatml",
            )
    except (ValueError, OSError, RuntimeError) as exc:
        raise ModelError("本地模型的权重读不出来") from exc
    _LOADED[key] = model
    return model


@contextlib.contextmanager
def _quiet_stderr():
    """权重库会把加载日志直接写到系统错误输出。读权重时先按住。"""
    sys.stderr.flush()
    saved = os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(saved, 2)
        os.close(saved)
        os.close(devnull)
