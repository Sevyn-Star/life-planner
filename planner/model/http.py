"""两边都走 OpenAI 兼容的 chat completions。密钥由调用方放进请求头。"""

import json
import urllib.error
import urllib.request

from planner.model import ModelError


def post_chat(url: str, model: str, messages: list[dict], headers: dict, *, opener=None, timeout: int = 45) -> str:
    payload = {"model": model, "temperature": 0, "messages": messages}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    for key, value in headers.items():
        request.add_header(key, value)
    open_fn = opener.open if opener is not None else urllib.request.urlopen
    try:
        with open_fn(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, TypeError, UnicodeError) as exc:
        raise ModelError("模型没有返回可用回复") from exc
    if not isinstance(content, str) or not content.strip():
        raise ModelError("模型没有返回可用回复")
    return content
