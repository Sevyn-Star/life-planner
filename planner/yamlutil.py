"""只解析本项目用到的 YAML 子集：映射、列表、标量。"""


def parse_yaml(text: str):
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        lines.append((indent, stripped))
    parser = _Parser(lines)
    peeked = parser.peek()
    if peeked is None:
        return {}
    if peeked[1].startswith("- "):
        return parser.parse_list(peeked[0])
    return parser.parse_map(0)


def _scalar(value: str):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    if value == "true":
        return True
    if value == "false":
        return False
    return value


def _split_key(content: str):
    if content.endswith(":") and ": " not in content:
        return content[:-1].strip(), ""
    key, value = content.split(":", 1)
    return key.strip(), value.strip()


class _Parser:
    def __init__(self, lines):
        self.lines = lines
        self.i = 0

    def peek(self):
        if self.i >= len(self.lines):
            return None
        return self.lines[self.i]

    def parse_value(self, indent: int):
        item = self.peek()
        if item is None or item[0] < indent:
            return None
        if item[1].startswith("- "):
            return self.parse_list(item[0])
        return self.parse_map(indent)

    def parse_list(self, indent: int):
        result = []
        while True:
            item = self.peek()
            if item is None or item[0] != indent or not item[1].startswith("- "):
                break
            self.i += 1
            content = item[1][2:].strip()
            if content == "":
                result.append(self.parse_map(item[0] + 2))
            elif content.endswith(":") or ": " in content or (
                ":" in content and not content.startswith('"')
            ):
                key, value = _split_key(content)
                mapping = {}
                if value == "":
                    mapping[key] = self.parse_value(item[0] + 2)
                else:
                    mapping[key] = _scalar(value)
                mapping.update(self.parse_map(item[0] + 2))
                result.append(mapping)
            else:
                result.append(_scalar(content))
        return result

    def parse_map(self, indent: int):
        result = {}
        while True:
            item = self.peek()
            if item is None or item[0] != indent or item[1].startswith("- "):
                break
            self.i += 1
            key, value = _split_key(item[1])
            if value == "":
                result[key] = self.parse_value(indent + 2)
            else:
                result[key] = _scalar(value)
        return result
