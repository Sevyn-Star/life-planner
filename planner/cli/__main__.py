import sys

from planner.corpus.index import build_index
from planner.paths import INDEX_PATH
from planner.run import answer, run_fixtures

USAGE = """用法：
  python3 -m planner.cli --rebuild-index
  python3 -m planner.cli --fixtures
  python3 -m planner.cli \"你的近况\"
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
    if args[0] == "--fixtures":
        errors = run_fixtures()
        if errors:
            print("\n".join(errors))
            return 1
        print("五个验收问题通过")
        return 0
    print(answer(" ".join(args)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
