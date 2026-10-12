import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

from planner.cli.__main__ import main
from planner.model import ModelError
from planner.model.api.client import complete as complete_api
from planner.model.config import configured_backend
from planner.model.context import load_summary, resolve_summary
from planner.model.local.client import checked_weights, complete as complete_local
from planner.paths import CONTEXT_DIR, CORPUS, INDEX_PATH, ROOT, SESSIONS_DIR
from planner.reply.check import _outside, _summary_numbers
from planner.run import answer, run_fixtures

TIGHT = CONTEXT_DIR / "sample-tight.md"
OPEN = CONTEXT_DIR / "sample-open.md"
INVALID = CONTEXT_DIR / "sample-invalid.md"
TEXT = "我不知道从哪开始，只想重新动一下。现在没有正在做的事，今天大概有半小时。希望先有一个今天能做的动作。"
LOW = "我在低谷里，今天只有几分钟。睡得很少，没有力气做长计划。只想要一个今天能完成的短动作。"
TIGHT_ACTION = "今天只做 20 分钟，做完就停。"
TIGHT_SITUATION = "空档更紧，所以这一步收紧到 20 分钟，长安排后移。"
OPEN_ACTION = "今天把书里的最小动作做完，并留下证据。"
OPEN_SITUATION = "时间够用，所以只调整顺序，先留下证据。"


def _payload(action: str, situation: str) -> str:
    return json.dumps({"action": action, "situation": situation}, ensure_ascii=False)


def _model(action: str, situation: str):
    payload = _payload(action, situation)

    def transport(messages, package):
        return payload

    return transport


def _boom(messages, package):
    raise AssertionError("模型不该被调用")


def _no_network(*args, **kwargs):
    raise AssertionError("不该访问网络")


def _section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    stop = text.index(end, begin + len(start))
    return text[begin:stop]


def _action(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("- 最小动作："):
            return line
    raise AssertionError(text[:400])


def _cited(text: str) -> set[str]:
    return set(re.findall(r"rensheng/(docs/[\w./-]+\.md)", text))


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self):
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Opener:
    def __init__(self, content: str):
        self.content = content
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        body = json.dumps({"choices": [{"message": {"content": self.content}}]}).encode()
        return _Response(body)


class ModelTests(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.copy()
        for key in list(os.environ):
            if key.startswith("PLANNER_"):
                del os.environ[key]

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)

    def test_path_regex_and_summary_numbers(self):
        allowed = {"docs/threads/part-0/reader-guide.md"}
        self.assertFalse(_outside("见 docs/threads/part-0/reader-guide.md", allowed))
        self.assertTrue(_outside("见 docs/threads/part-9/missing.md", allowed))
        self.assertTrue(_outside("见 rensheng/docs/threads/part-9/missing.md", allowed))
        tight = load_summary(TIGHT, today=date(2026, 10, 12))
        opened = load_summary(OPEN, today=date(2026, 10, 12))
        self.assertIsNotNone(tight)
        self.assertIsNotNone(opened)
        self.assertIsNone(load_summary(INVALID, today=date(2026, 10, 12)))
        self.assertIn("20", _summary_numbers(tight))
        self.assertNotIn("20", _summary_numbers(opened))
        self.assertIsNone(resolve_summary(today=date(2026, 10, 12)))

    def test_expiry_is_inclusive_on_the_last_day(self):
        text = TIGHT.read_text(encoding="utf-8").replace("expires: 2026-12-31", "expires: 2026-10-12")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "edge.md"
            path.write_text(text, encoding="utf-8")
            self.assertIsNotNone(load_summary(path, today=date(2026, 10, 12)))
            self.assertIsNone(load_summary(path, today=date(2026, 10, 13)))

    def test_backends_send_the_same_input_and_render_the_same_reply(self):
        seen = []

        def transport(messages, package):
            seen.append(messages)
            return _payload(TIGHT_ACTION, TIGHT_SITUATION)

        left = answer(TEXT, context=str(TIGHT), model="api", transport=transport)
        right = answer(TEXT, context=str(TIGHT), model="local", transport=transport)
        self.assertEqual(left, right)
        self.assertEqual(seen[0], seen[1])
        self.assertIn("## 形势对照", left)
        self.assertIn("信息种类：形势判断", left)
        payload = json.loads(seen[0][1]["content"])
        self.assertEqual(set(payload), {"sheet", "kept", "session", "context"})
        self.assertIsNone(payload["session"])
        self.assertGreaterEqual(len(payload["kept"]), 2)
        self.assertTrue(any(item["path"].startswith("docs/threads/part-0/") for item in payload["kept"]))
        self.assertTrue(all(not item["path"].startswith("docs/en/") for item in payload["kept"]))
        self.assertEqual(payload["context"]["title"], "时间被压短的一周")
        self.assertIn("样本形势：时间被压短", payload["context"]["body"])

    def test_swapping_context_changes_the_step_not_the_book(self):
        plain = answer(TEXT)
        tight = answer(TEXT, context=str(TIGHT), model="api", transport=_model(TIGHT_ACTION, TIGHT_SITUATION))
        opened = answer(TEXT, context=str(OPEN), model="local", transport=_model(OPEN_ACTION, OPEN_SITUATION))
        self.assertEqual(_section(tight, "## 主线", "## 规划"), _section(plain, "## 主线", "## 规划"))
        self.assertEqual(_section(opened, "## 主线", "## 规划"), _section(plain, "## 主线", "## 规划"))
        self.assertEqual(_section(tight, "## 建议", "## 下次"), _section(plain, "## 建议", "## 下次"))
        self.assertEqual(_section(opened, "## 建议", "## 下次"), _section(plain, "## 建议", "## 下次"))
        self.assertEqual(_cited(tight), _cited(plain))
        self.assertEqual(_cited(opened), _cited(plain))
        self.assertNotEqual(_action(tight), _action(opened))
        self.assertNotEqual(_action(tight), _action(plain))
        self.assertIn("20 分钟", _action(tight))
        self.assertNotIn("20", _action(opened))
        self.assertIn("本人 2026-10-01 的本周可用时间记录", tight)
        self.assertIn("本人 2026-10-01 的本周日程记录", opened)
        self.assertIn("2026-10-01", tight)
        self.assertNotIn("docs/threads/part-1/", tight)
        self.assertNotIn("docs/threads/part-5/", tight)
        for line in tight.splitlines():
            if "依据：" in line:
                self.assertNotIn("形势判断", line)

    def test_outside_path_discards_the_whole_draft(self):
        output = answer(
            TEXT,
            context=str(TIGHT),
            model="api",
            transport=_model(TIGHT_ACTION, "这一步收紧，但去看 docs/threads/part-9/missing.md。"),
        )
        self.assertEqual(output, answer(TEXT))
        self.assertNotIn("今天只做 20 分钟", output)
        self.assertNotIn("part-9", output)
        self.assertNotIn("## 形势对照", output)

    def test_invented_number_is_not_shown(self):
        output = answer(
            TEXT,
            context=str(OPEN),
            model="api",
            transport=_model(OPEN_ACTION, "这一步只调整顺序，但写成 20 分钟。"),
        )
        self.assertNotIn("## 形势对照", output)
        self.assertNotIn("但写成 20 分钟", output)
        self.assertIn("## 规划", output)

    def test_cycle_language_without_evidence_is_discarded(self):
        output = answer(
            TEXT,
            context=str(TIGHT),
            model="api",
            transport=_model("今天先把这件事写进九十天总表里。", "这一步收紧，并写进九十天总表。"),
        )
        self.assertEqual(output, answer(TEXT))
        self.assertNotIn("写进九十天总表", output)

    def test_situation_cannot_be_relabelled_as_a_book_kind(self):
        output = answer(
            TEXT,
            context=str(TIGHT),
            model="api",
            transport=_model(TIGHT_ACTION, "信息种类：研究结论。这一步收紧到 20 分钟。"),
        )
        self.assertNotIn("## 形势对照", output)
        self.assertNotIn(TIGHT_ACTION, output)

    def test_no_plan_means_no_model_call(self):
        questions = [
            "帮我判断明天哪只股票会涨，给我一个具体的买入价和卖出价。",
            "我想要一个九十天的周期规划，把接下来三个月排开。今天有一小时。",
            "我这两天有危险念头，不想活了。",
        ]
        for question in questions:
            output = answer(question, context=str(TIGHT), model="api", transport=_boom)
            self.assertEqual(output, answer(question))
            self.assertNotIn("## 形势对照", output)

    def test_invalid_or_expired_summary_is_not_read(self):
        self.assertEqual(answer(TEXT, context=str(INVALID), model="api", transport=_boom), answer(TEXT))
        text = TIGHT.read_text(encoding="utf-8").replace("expires: 2026-12-31", "expires: 2020-01-01")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.md"
            path.write_text(text, encoding="utf-8")
            self.assertIsNone(load_summary(path, today=date(2026, 10, 12)))
            self.assertEqual(answer(TEXT, context=str(path), model="api", transport=_boom), answer(TEXT))
        self.assertEqual(answer(TEXT, model="api", transport=_boom), answer(TEXT))

    def test_low_capacity_keeps_the_short_entry(self):
        output = answer(LOW, context=str(TIGHT), model="api", transport=_model(TIGHT_ACTION, TIGHT_SITUATION))
        self.assertIn("## 形势对照", output)
        self.assertNotIn("docs/threads/part-5/", output)
        self.assertNotIn("90-day", output)
        self.assertTrue("docs/threads/part-2/recovery.md" in output or "docs/threads/part-4/daily-system.md" in output)

    def test_secrets_are_not_sent_or_stored(self):
        seen = []

        def transport(messages, package):
            seen.append(messages[1]["content"])
            return _payload(TIGHT_ACTION, TIGHT_SITUATION)

        before = sorted(path.name for path in SESSIONS_DIR.iterdir())
        output = answer(
            "我不知道从哪开始。身份证号 110101199001011234。只想重新动一下。今天有半小时。",
            context=str(TIGHT),
            model="api",
            transport=transport,
        )
        after = sorted(path.name for path in SESSIONS_DIR.iterdir())
        self.assertEqual(before, after)
        self.assertNotIn("110101199001011234", seen[0])
        self.assertNotIn("110101199001011234", output)
        self.assertIsNone(json.loads(seen[0])["session"])

    def test_context_is_not_indexed_and_corpus_stays_untouched(self):
        before = subprocess.check_output(["git", "status", "--short", "--", "rensheng"], cwd=ROOT, text=True)
        answer(TEXT, context=str(TIGHT), model="api", transport=_model(TIGHT_ACTION, TIGHT_SITUATION))
        after = subprocess.check_output(["git", "status", "--short", "--", "rensheng"], cwd=ROOT, text=True)
        self.assertEqual(before, after)
        blob = INDEX_PATH.read_text(encoding="utf-8")
        self.assertNotIn("样本形势：时间被压短", blob)
        self.assertNotIn("样本形势：故意不写来源", blob)

    def test_answer_and_fixtures_ignore_model_env(self):
        os.environ["PLANNER_MODEL"] = "api"
        os.environ["PLANNER_API_KEY"] = "sk-test-secret"
        os.environ["PLANNER_API_MODEL"] = "demo"
        os.environ["PLANNER_CONTEXT"] = str(TIGHT)
        with patch("urllib.request.urlopen", _no_network):
            output = answer(TEXT)
            errors = run_fixtures()
        self.assertNotIn("## 形势对照", output)
        self.assertEqual(errors, [])

    def test_missing_backend_config_falls_back_without_network(self):
        with patch("urllib.request.urlopen", _no_network):
            api = answer(TEXT, context=str(TIGHT), model="api")
            local = answer(TEXT, context=str(TIGHT), model="local")
        self.assertEqual(api, answer(TEXT))
        self.assertEqual(local, answer(TEXT))

    def test_api_request_keeps_the_key_out_of_the_body(self):
        opener = _Opener(_payload(TIGHT_ACTION, TIGHT_SITUATION))
        os.environ["PLANNER_API_KEY"] = "sk-test-secret"
        os.environ["PLANNER_API_MODEL"] = "demo"
        text = complete_api({"sheet": {"question": "从哪开始"}, "kept": [], "session": None, "context": {}}, opener=opener)
        self.assertIn("收紧", text)
        request = opener.requests[0]
        self.assertTrue(request.full_url.endswith("/chat/completions"))
        self.assertEqual(request.get_header("Authorization"), "Bearer sk-test-secret")
        raw = request.data.decode()
        self.assertNotIn("sk-test-secret", raw)
        body = json.loads(raw)
        self.assertEqual(body["temperature"], 0)
        self.assertEqual(body["messages"][0]["role"], "system")
        self.assertEqual(body["messages"][1]["role"], "user")

    def test_local_weights_stay_outside_the_repo(self):
        opener = _Opener(_payload(TIGHT_ACTION, TIGHT_SITUATION))
        with self.assertRaises(ModelError):
            complete_local({}, opener=opener)
        self.assertEqual(opener.requests, [])

        os.environ["PLANNER_LOCAL_WEIGHTS"] = str(CORPUS / "README.md")
        with self.assertRaises(ModelError):
            checked_weights()

        inside = CONTEXT_DIR / "_tmp_weights"
        inside.write_text("SECRETWEIGHT", encoding="utf-8")
        try:
            os.environ["PLANNER_LOCAL_WEIGHTS"] = str(inside)
            with self.assertRaises(ModelError):
                checked_weights()
        finally:
            inside.unlink()

        with tempfile.TemporaryDirectory() as tmp:
            weights = Path(tmp) / "weights"
            weights.write_text("SECRETWEIGHT", encoding="utf-8")
            os.environ["PLANNER_LOCAL_WEIGHTS"] = str(weights)
            os.environ["PLANNER_LOCAL_URL"] = "http://127.0.0.1:9/v1"
            os.environ["PLANNER_LOCAL_MODEL"] = "small"
            self.assertEqual(checked_weights(), weights.resolve())
            complete_local({"sheet": {"question": "从哪开始"}, "kept": [], "session": None, "context": {}}, opener=opener)
            request = opener.requests[0]
            raw = request.data.decode()
            self.assertIsNone(request.get_header("Authorization"))
            self.assertNotIn("SECRETWEIGHT", raw)
            self.assertNotIn(str(weights), raw)
            self.assertTrue(request.full_url.startswith("http://127.0.0.1:9/v1/chat/completions"))

    def test_cli_rejects_an_unknown_backend_and_skips_an_invalid_summary(self):
        self.assertIsNone(configured_backend())
        os.environ["PLANNER_MODEL"] = "both"
        with self.assertRaises(ModelError):
            configured_backend()
        err = io.StringIO()
        with redirect_stderr(err):
            code = main(["--model", "both", TEXT])
        self.assertEqual(code, 2)
        self.assertIn("api 或 local", err.getvalue())

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), patch("urllib.request.urlopen", _no_network):
            code = main(["--model", "api", "--context", str(INVALID), TEXT])
        self.assertEqual(code, 0)
        self.assertIn("## 规划", out.getvalue())
        self.assertNotIn("## 形势对照", out.getvalue())
        self.assertIn("改走初版模板", err.getvalue())


if __name__ == "__main__":
    unittest.main()
