import os
import sys
from pathlib import Path

from planner.corpus.index import build_index
from planner.model import ModelError
from planner.model.config import configured_backend
from planner.model.context import resolve_summary
from planner.paths import INDEX_PATH
from planner.run import answer, run_fixtures

USAGE = """用法：
  python3 -m planner.cli --rebuild-index
  python3 -m planner.cli --fixtures
  python3 -m planner.cli \"你的近况\"
  python3 -m planner.cli --session current \"你的近况\"
  python3 -m planner.cli --context data/context/sample-tight.md \"你的近况\"

启用模型时设置 PLANNER_MODEL=api 或 local。没启用时仍用填段模板。
默认把复查记在 data/sessions/current.yaml。五个验收问题不写会话。
"""


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help"}:
        print(USAGE.strip())
        return 0 if args else 2
    if args[0] == "--rebuild-index":
        count = build_index()
        print(f"索引已写入 {INDEX_PATH}，{count} 段")
        return 0
    if "--fixtures" in args:
        errors = run_fixtures()
        if errors:
            print("\n".join(errors))
            return 1
        print("五个验收问题通过")
        return 0
    try:
        model_arg, args = _option(args, "--model")
        context, args = _option(args, "--context")
        session_arg, args = _option(args, "--session")
    except ValueError as exc:
        print(f"缺少 {exc}", file=sys.stderr)
        return 2
    if model_arg is not None:
        model = model_arg.strip().lower()
        if model not in {"api", "local"}:
            print("模型只能启用 api 或 local 里的一个。", file=sys.stderr)
            return 2
    else:
        try:
            model = configured_backend()
        except ModelError as exc:
            print(str(exc), file=sys.stderr)
            return 2
    if not args:
        print(USAGE.strip())
        return 2
    summary = resolve_summary(context) if model else None
    session_dir = os.environ.get("PLANNER_SESSION_DIR", "").strip()
    try:
        output = answer(
            " ".join(args),
            context=context,
            model=model,
            session=session_arg or "current",
            session_dir=Path(session_dir) if session_dir else None,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if model and summary is None and context:
        print("这份形势摘要没有来源、日期，或已经过期，改走初版模板。", file=sys.stderr)
    elif model and summary is None and "## 规划" in output:
        print("没有一份可用的形势摘要，改走初版模板。用 --context 指定一份。", file=sys.stderr)
    elif model and summary is not None and "## 规划" in output and "## 形势对照" not in output:
        print("模型没有给出可用回复，改走初版模板。", file=sys.stderr)
    print(output, end="")
    return 0


def _option(args: list[str], name: str) -> tuple[str | None, list[str]]:
    if name not in args:
        return None, args
    index = args.index(name)
    if index + 1 >= len(args) or args[index + 1].startswith("--"):
        raise ValueError(name)
    value = args[index + 1]
    return value, args[:index] + args[index + 2 :]


if __name__ == "__main__":
    raise SystemExit(main())
