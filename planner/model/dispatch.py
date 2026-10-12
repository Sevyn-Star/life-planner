"""配置里只启用一个后端。"""

from planner.model import ModelError


def generate(backend: str, package: dict, *, transport=None, opener=None) -> str:
    if backend == "api":
        from planner.model.api.client import complete
    elif backend == "local":
        from planner.model.local.client import complete
    else:
        raise ModelError("模型只能启用 api 或 local 里的一个。")
    return complete(package, transport=transport, opener=opener)
