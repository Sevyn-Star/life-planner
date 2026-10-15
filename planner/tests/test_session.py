import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from io import StringIO
from pathlib import Path

from planner.cli.__main__ import main
from planner.page_reply import iter_page_answer
from planner.paths import SESSIONS_DIR
from planner.run import answer, run_fixtures
from planner.session import load_session

TEXT = "我不知道从哪开始，只想重新动一下。现在没有正在做的事，今天大概有半小时。希望先有一个今天能做的动作。"
LISTENING = "我只想练英语听力。今天有四十分钟，想要一个今天的练习。"
BROUGHT = "我做完了，这是记录：写了半页学习状态。"
CYCLE = "我想要一个九十天的周期规划，把接下来三个月排开。今天有一小时。"
DAY = date(2026, 10, 12)


class SessionTests(unittest.TestCase):
    def test_fixtures_and_plain_answers_do_not_write_sessions(self):
        before = sorted(path.name for path in SESSIONS_DIR.iterdir())
        output = answer(TEXT)
        errors = run_fixtures()
        after = sorted(path.name for path in SESSIONS_DIR.iterdir())
        self.assertEqual(before, after)
        self.assertEqual(errors, [])
        self.assertNotIn("## 复查", output)
        self.assertNotIn("## 要不要换主线", output)

    def test_a_plan_remembers_the_review_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = answer(TEXT, session="main", session_dir=root, today=DAY)
            record = load_session("main", root=root)
            self.assertIsNotNone(record)
            self.assertEqual(record.entry_id, "start")
            self.assertEqual(record.review_date, "2026-10-26")
            self.assertIn("2026-10-26", output)
            self.assertIn("docs/threads/part-0/", output)
            self.assertTrue(record.action)
            self.assertTrue(record.evidence)
            self.assertEqual(record.switch, "")
            self.assertEqual(record.brought, "")

    def test_a_side_topic_asks_before_switching(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            answer(TEXT, session="main", session_dir=root, today=DAY)
            asked = answer(LISTENING, session="main", session_dir=root, today=DAY)
            record = load_session("main", root=root)
            self.assertIn("## 要不要换主线", asked)
            self.assertNotIn("## 规划", asked)
            self.assertNotIn("docs/threads/part-1/", asked)
            self.assertEqual(record.entry_id, "start")
            self.assertIn("听力", record.switch)

            stayed = answer("不换。", session="main", session_dir=root, today=DAY)
            record = load_session("main", root=root)
            self.assertIn("这次不换", stayed)
            self.assertNotIn("docs/threads/part-1/", stayed)
            self.assertEqual(record.entry_id, "start")
            self.assertEqual(record.switch, "")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            answer(TEXT, session="move", session_dir=root, today=DAY)
            answer(LISTENING, session="move", session_dir=root, today=DAY)
            switched = answer("换主线", session="move", session_dir=root, today=DAY)
            record = load_session("move", root=root)
            self.assertIn("docs/threads/part-1/", switched)
            self.assertNotIn("docs/threads/part-0/", switched)
            self.assertIn("已换主线", switched)
            self.assertEqual(record.entry_id, "listening")

    def test_early_evidence_does_not_open_a_ninety_day_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            answer(TEXT, session="main", session_dir=root, today=DAY)
            noted = answer(BROUGHT, session="main", session_dir=root, today=DAY)
            record = load_session("main", root=root)
            self.assertIn("决定：继续", noted)
            self.assertEqual(record.entry_id, "start")
            self.assertTrue(record.brought)
            blocked = answer(CYCLE, session="main", session_dir=root, today=DAY)
            record = load_session("main", root=root)
            self.assertIn("## 没筛中", blocked)
            self.assertIn("十四天", blocked)
            self.assertNotIn("## 规划", blocked)
            self.assertNotIn("docs/threads/part-5/", blocked)
            self.assertEqual(record.entry_id, "start")

    def test_review_day_evidence_opens_the_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            answer(TEXT, session="main", session_dir=root, today=DAY)
            answer(BROUGHT, session="main", session_dir=root, today=DAY)
            prior = load_session("main", root=root).action
            opened = answer(CYCLE, session="main", session_dir=root, today=date(2026, 10, 26))
            self.assertIn("## 规划", opened)
            self.assertIn("docs/threads/part-5/", opened)
            self.assertNotIn("## 没筛中", opened)
            self.assertIn(f"- 最小动作：{prior}", opened)
            self.assertIn("上一轮已经在做的最小动作", opened)
            self.assertNotIn("先做：在九十天内，我要", opened)
            record = load_session("main", root=root)
            self.assertEqual(record.entry_id, "cycle")
            self.assertEqual(record.action, prior)

    def test_explicit_fourteen_day_evidence_opens_the_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            answer(TEXT, session="main", session_dir=root, today=DAY)
            opened = answer(
                "我已经留下十四天证据，想要一个九十天的周期规划。今天有一小时。",
                session="main",
                session_dir=root,
                today=DAY,
            )
            self.assertIn("docs/threads/part-5/", opened)
            self.assertIn("## 规划", opened)

    def test_shrinking_stays_on_the_same_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            answer(TEXT, session="main", session_dir=root, today=DAY)
            output = answer("我做不到，没做成。", session="main", session_dir=root, today=DAY)
            record = load_session("main", root=root)
            self.assertIn("决定：缩小", output)
            self.assertNotIn("docs/threads/part-5/", output)
            self.assertEqual(record.entry_id, "start")

    def test_secrets_are_not_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = answer(
                "我不知道从哪开始，身份证号 110101199001011234，住址：北京市海淀区某路1号。今天有半小时。",
                session="main",
                session_dir=root,
                today=DAY,
            )
            stored = (root / "main.yaml").read_text(encoding="utf-8")
            self.assertNotIn("110101199001011234", output)
            self.assertNotIn("110101199001011234", stored)
            self.assertNotIn("北京市海淀区某路1号", stored)
            self.assertIn("〔已省略〕", stored)

    def test_crisis_does_not_rewrite_the_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            answer(TEXT, session="main", session_dir=root, today=DAY)
            before = (root / "main.yaml").read_text(encoding="utf-8")
            output = answer("我这两天有危险念头，不想活了。", session="main", session_dir=root, today=DAY)
            after = (root / "main.yaml").read_text(encoding="utf-8")
            self.assertEqual(before, after)
            self.assertNotIn("不想活", after)
            self.assertNotIn("## 规划", output)
            self.assertIn("医疗", output)

    def test_return_is_visible_to_the_model_package(self):
        seen = []

        def transport(messages, package):
            seen.append(package)
            return '{"action":"今天把书里的最小动作做完，并留下证据。","situation":"时间够用，所以只调整顺序，先留下证据。"}'

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            answer(TEXT, session="main", session_dir=root, today=DAY)
            output = answer(
                "我还是不知道从哪开始。今天有半小时。",
                session="main",
                session_dir=root,
                today=DAY,
                context=str(Path("data/context/sample-open.md")),
                model="api",
                transport=transport,
            )
            self.assertEqual(seen[0]["session"]["entry_id"], "start")
            self.assertIn("## 复查", output)
            self.assertIn("证据还没贴来", output)
            self.assertIn("## 形势对照", output)

    def test_a_named_session_asks_one_gap_then_writes_four_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = answer("我不知道从哪开始", session="ask", session_dir=root, today=DAY, follow_up=True)
            self.assertEqual(first.strip(), "你已经做过什么？还没做过也直接说。")
            self.assertNotIn("## 规划", first)
            self.assertEqual(load_session("ask", root=root).awaiting, "done")

            second = answer("什么都没做过。", session="ask", session_dir=root, today=DAY, follow_up=True)
            self.assertEqual(second.strip(), "今天能拿出多少时间？")
            self.assertEqual(load_session("ask", root=root).awaiting, "capacity")

            third = answer(
                "今天有半小时，想要今天的一步。",
                session="ask",
                session_dir=root,
                today=DAY,
                follow_up=True,
            )
            self.assertIn("## 主线", third)
            self.assertIn("## 规划", third)
            self.assertIn("## 建议", third)
            self.assertIn("docs/threads/part-0/", third)
            saved = load_session("ask", root=root)
            self.assertEqual(saved.awaiting, "")
            self.assertEqual(saved.entry_id, "start")
            self.assertTrue(saved.action)

    def test_the_same_missing_time_asks_the_same_question(self):
        thin = "我不知道从哪开始。现在没有正在做的事。希望先有一个能做的动作。"
        question = "今天能拿出多少时间？"
        saved = {key: os.environ[key] for key in os.environ if key.startswith("PLANNER_")}
        try:
            for key in saved:
                del os.environ[key]
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                os.environ["PLANNER_SESSION_DIR"] = tmp
                page = "".join(
                    piece
                    for _event, piece in iter_page_answer(thin, session="page", session_dir=root, today=DAY)
                )
                out = StringIO()
                with redirect_stdout(out):
                    code = main(["--session", "ask", thin])
                cli = out.getvalue()
                self.assertEqual(code, 0)
                self.assertIn(question, page)
                self.assertIn(question, cli)
                self.assertNotIn("已经做过什么", cli)
                self.assertNotIn("## 规划", cli)
                self.assertEqual(load_session("ask", root=root).awaiting, "capacity")

                plain = StringIO()
                with redirect_stdout(plain):
                    plain_code = main([thin])
                self.assertEqual(plain_code, 0)
                self.assertIn("## 规划", plain.getvalue())
                self.assertNotIn(question, plain.getvalue())
        finally:
            os.environ.pop("PLANNER_SESSION_DIR", None)
            os.environ.update(saved)

        direct = answer(thin)
        self.assertIn("## 规划", direct)
        self.assertNotIn(question, direct)
        errors = run_fixtures()
        self.assertEqual(errors, [])

    def test_follow_up_skips_safety_and_a_blocked_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            crisis = answer(
                "我这两天有危险念头，不想活了。",
                session="ask",
                session_dir=root,
                today=DAY,
                follow_up=True,
            )
            self.assertIn("医疗", crisis)
            self.assertNotIn("已经做过什么", crisis)
            self.assertIsNone(load_session("ask", root=root))
            blocked = answer(CYCLE, session="ask", session_dir=root, today=DAY, follow_up=True)
            self.assertIn("## 没筛中", blocked)
            self.assertNotIn("多少时间", blocked)
            self.assertIsNone(load_session("ask", root=root))

    def test_session_name_rejects_a_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                answer(TEXT, session="../outside", session_dir=Path(tmp), today=DAY)


if __name__ == "__main__":
    unittest.main()
