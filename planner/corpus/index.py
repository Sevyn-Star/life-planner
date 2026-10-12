import json
import re
from pathlib import Path

from planner.corpus.segment import Segment
from planner.paths import CORPUS, INDEX_DIR, INDEX_PATH

KINDS = ("研究结论", "个人经验", "待验证假设")

_FENCE = re.compile(r"^```")
_HEADING = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
_HTML = re.compile(r"<[^>]+>")
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def build_index(corpus: Path = CORPUS, dest: Path = INDEX_PATH) -> int:
    segments: list[Segment] = []
    for path in _source_files(corpus):
        rel = path.relative_to(corpus).as_posix()
        text = path.read_text(encoding="utf-8")
        segments.extend(_segments_from(rel, text))
    segments.sort(key=lambda item: (item.path, item.line, item.title))
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = "\n".join(json.dumps(item.to_json(), ensure_ascii=False) for item in segments)
    dest.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
    manifest = {
        "files": len({item.path for item in segments}),
        "segments": len(segments),
    }
    (INDEX_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return len(segments)


def load_index(path: Path = INDEX_PATH) -> list[Segment]:
    if not path.exists():
        build_index(dest=path)
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(Segment.from_json(json.loads(line)))
    return rows


def _source_files(corpus: Path) -> list[Path]:
    found = []
    for path in sorted(corpus.rglob("*.md")):
        rel = path.relative_to(corpus).as_posix()
        if _included(rel):
            found.append(path)
    return found


def _included(rel: str) -> bool:
    if rel.startswith("docs/en/") or rel.startswith("docs/public/"):
        return False
    if rel.startswith("docs/threads/word-list/"):
        return False
    if rel.startswith("docs/threads/") or rel.startswith("docs/templates/"):
        return True
    if rel.startswith("docs/reference/"):
        return True
    return rel in {"docs/practice.md", "README.md", "SUMMARY.md"}


def _segments_from(rel: str, text: str) -> list[Segment]:
    description, body = _front_matter(text)
    lines = body.splitlines()
    headings: list[tuple[int, str]] = []
    in_fence = False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if _FENCE.match(stripped):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        matched = _HEADING.match(line)
        if matched:
            headings.append((index, matched.group(2).strip()))
    segments = []
    for position, (start, title) in enumerate(headings):
        end = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        raw = "\n".join(lines[start + 1 : end]).strip()
        cleaned = _clean(raw)
        if len(re.findall(r"[\u4e00-\u9fff]", cleaned)) < 20:
            continue
        kind = _classify(raw, description)
        if kind not in KINDS:
            kind = "待验证假设"
        segments.append(Segment(rel, title, cleaned, kind, start + 1))
    return segments


def _front_matter(text: str) -> tuple[str, str]:
    if not text.startswith("---"):
        return "", text
    end = text.find("\n---", 3)
    if end == -1:
        return "", text
    matter = text[3:end]
    body = text[end + 4 :]
    if body.startswith("\n"):
        body = body[1:]
    description = ""
    for line in matter.splitlines():
        if line.startswith("description:"):
            description = line.split(":", 1)[1].strip().strip('"')
    return description, body


def _classify(raw: str, description: str) -> str:
    if any(
        phrase in raw
        for phrase in (
            "不是研究结论",
            "待验证假设",
            "待检验假设",
            "等待验证",
            "等待检验",
        )
    ):
        return "待验证假设"
    if "http" in raw and ("来源" in raw or "研究" in raw):
        return "研究结论"
    head = raw[:200]
    if any(phrase in head for phrase in ("个人记录", "作者个人", "个人经验")):
        return "个人经验"
    if "个人记录" in description and raw.count("我") >= 6:
        return "个人经验"
    return "待验证假设"


def _clean(text: str) -> str:
    text = _COMMENT.sub("", text)
    text = re.sub(r"```[^\n]*\n", "", text)
    text = text.replace("```", "")
    text = _HTML.sub("", text)
    text = _IMAGE.sub(r"\1", text)
    text = _LINK.sub(r"\1", text)
    text = _BOLD.sub(r"\1", text)
    text = re.sub(r"(?m)^>\s?", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
