from dataclasses import dataclass


@dataclass(frozen=True)
class Segment:
    path: str
    title: str
    text: str
    kind: str
    line: int

    def cite_path(self) -> str:
        return f"rensheng/{self.path}"

    def to_json(self) -> dict:
        return {
            "path": self.path,
            "title": self.title,
            "text": self.text,
            "kind": self.kind,
            "line": self.line,
        }

    @classmethod
    def from_json(cls, data: dict) -> "Segment":
        return cls(
            path=data["path"],
            title=data["title"],
            text=data["text"],
            kind=data["kind"],
            line=int(data["line"]),
        )
