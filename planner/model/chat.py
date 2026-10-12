"""API 和本地模型共用的消息。两边看到的输入包是同一份。"""

import json

SYSTEM = (
    "你只根据用户消息里的 JSON 改写今天这一步。"
    "JSON 里只有筛选单、筛中段落、会话和一份形势摘要，没有整本书。"
    "只输出一个 JSON 对象，不要写别的字。键只有 action 和 situation。"
    "action 是规划里的最小动作：写成筛选单容量下今天就能做的一步，主线仍是筛中的那一条。"
    "situation 是形势对照，必须写明这一步是在「收紧」还是只「调整顺序」。"
    "形势对照里的数字必须已经出现在形势摘要里。摘要里没有的统计、政策条文和收入数字不要写。"
    "不要写出筛中段落以外的文件路径。"
    "不要把形势判断写成研究结论、个人经验或待验证假设。"
    "没有十四天证据时不要写九十天安排。"
    "形势和书冲突时保留书里的边界，只改这一步的尺度和顺序。"
    "不要写「你一定能」「改变命运」这类句子。"
)


def build_messages(package: dict) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": json.dumps(package, ensure_ascii=False)},
    ]
