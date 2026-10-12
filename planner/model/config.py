"""PLANNER_MODEL 决定启用哪一个。空着就走初版模板。"""

import os

from planner.model import ModelError


def configured_backend() -> str | None:
    name = os.environ.get("PLANNER_MODEL", "").strip().lower()
    if name in {"", "off", "none"}:
        return None
    if name not in {"api", "local"}:
        raise ModelError("PLANNER_MODEL 只能是 api 或 local。")
    return name
