"""把筛选单、筛中段落、会话和形势摘要收成模型唯一能看见的输入包。"""

from planner.cli.intake import Sheet
from planner.corpus.segment import Segment
from planner.model.context import Summary


def build_package(sheet: Sheet, kept: list[Segment], summary: Summary, session) -> dict:
    return {
        "sheet": {
            "question": sheet.question,
            "domain": sheet.domain,
            "facts": list(sheet.facts),
            "capacity": sheet.capacity,
            "capacity_low": sheet.capacity_low,
            "goal": sheet.goal,
            "has_fourteen_day_evidence": sheet.has_fourteen_day_evidence,
        },
        "kept": [
            {"path": segment.path, "title": segment.title, "kind": segment.kind, "text": segment.text}
            for segment in kept
        ],
        "session": session,
        "context": summary.to_dict(),
    }
