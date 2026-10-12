"""会话记录的位置。初版不读写。

复查阶段才在 data/sessions/ 里记下主线、选定入口、上次最小动作、
要留下的证据和复查日期。密码、证件号、住址、病历和他人隐私不写入。
"""


def load_session(session_id: str | None = None):
    """初版没有会话。返回空，调用方把第二样输入当作没有。"""
    return None
