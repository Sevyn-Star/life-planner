import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

import planner.chats as chats
import planner.page as page
from planner.page_reply import _visible, _without_loop, iter_page_answer
from planner.paths import SESSIONS_DIR
from planner.session import load_session


class PageTests(unittest.TestCase):
    def test_index_is_a_plain_document(self):
        html = page.PAGE.read_text(encoding="utf-8")
        self.assertIn(page._EMPTY_TEXTAREA, html)
        self.assertIn("<!-- result -->", html)
        self.assertIn("我想听一句今天能做的话", html)
        self.assertIn("我说卡在哪", html)
        self.assertIn('id="thread"', html)
        self.assertIn("新对话", html)
        self.assertIn("删除", html)
        self.assertIn('id="compile"', html)
        self.assertIn("思维导图", html)
        self.assertNotIn("vitepress", html.lower())
        self.assertNotIn("<script src", html.lower())

    def test_reply_text_is_escaped(self):
        body = page.render_page("今天有半小时 <b>", "回复 <script>").decode("utf-8")
        self.assertIn("回复 &lt;script&gt;", body)
        self.assertIn("今天有半小时 &lt;b&gt;", body)
        self.assertNotIn("回复 <script>", body)

    def test_page_post_returns_to_a_plain_get(self):
        server, thread = _serve()
        try:
            host, port = server.server_address
            data = urllib.parse.urlencode({"text": "今天有半小时"}).encode()
            request = urllib.request.Request(f"http://{host}:{port}/", data=data)
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.build_opener(_NoRedirect).open(request)
            self.assertEqual(caught.exception.code, 303)
            self.assertEqual(caught.exception.headers.get("Location"), "/")
        finally:
            _stop(server, thread)


    def test_plain_answer_uses_the_book_as_reference_only(self):
        def boom(_prompt):
            raise AssertionError("不该写")
            yield ""

        safety = list(iter_page_answer("我这两天有危险念头，不想活了。", streamer=boom))
        self.assertIn("我先停一下", "".join(item[1] for item in safety if item[0] == "token"))

        seen = []

        def own_speaker(sheet, nearest):
            seen.append(nearest)
            self.assertTrue(sheet.question)
            return "今天先把这件事写下来，留下一句话。\n见 docs/threads/part-9/missing.md\n这是研究结论。"

        import planner.page_reply as page_reply

        original = page_reply.use_own_words
        page_reply.use_own_words = lambda model: model != "api"
        try:
            events = list(iter_page_answer("帮我判断明天哪只股票会涨。", streamer=boom, speaker=own_speaker))
            api_events = list(iter_page_answer(
                "帮我判断明天哪只股票会涨。",
                model="api",
                speaker=lambda _sheet, _nearest: (_ for _ in ()).throw(AssertionError("API 不写自述")),
            ))
        finally:
            page_reply.use_own_words = original
        text = "".join(item[1] for item in events if item[0] == "token")
        self.assertTrue(seen)
        self.assertIn("没有对上", text)
        self.assertIn(seen[0], text)
        self.assertIn("模型自述", text)
        self.assertIn("信息种类：模型自述", text)
        self.assertIn("今天先把这件事写下来", text)
        self.assertNotIn("docs/", text)
        self.assertNotIn("研究结论", text)
        self.assertNotIn("先动一下", text)
        api = "".join(item[1] for item in api_events if item[0] == "token")
        self.assertIn("没有对上", api)
        self.assertNotIn("模型自述", api)

        later = "".join(
            item[1]
            for item in iter_page_answer(
                "那我今天只有五分钟呢？",
                speaker=lambda _sheet, _nearest: "五分钟就记下这一句。",
            )
            if item[0] == "token"
        )
        self.assertIn("没有对上", later)
        self.assertIn("五分钟就记下这一句", later)
        self.assertNotIn("我说", later)

    def test_a_chat_asks_before_leaving_its_line(self):
        day = date(2026, 10, 12)
        start = "我不知道从哪开始，只想重新动一下。现在没有正在做的事，今天大概有半小时。希望先有一个今天能做的动作。"
        listening = "我只想练英语听力。还没练过。今天有四十分钟，想要一个今天的练习。"

        def speak(_prompt):
            yield "先动一下。"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = _tokens(iter_page_answer(start, streamer=speak, session="chat1", session_dir=root, today=day))
            record = load_session("chat1", root=root)
            self.assertEqual(record.entry_id, "start")
            self.assertEqual(record.review_date, "2026-10-26")
            self.assertNotIn("docs/", first)
            self.assertNotIn("## ", first)

            def boom(_prompt):
                raise AssertionError("岔开时不该先写新的一步")
                yield ""

            asked = _tokens(iter_page_answer(listening, streamer=boom, session="chat1", session_dir=root, today=day))
            self.assertIn("换主线", asked)
            self.assertIn("不换", asked)
            self.assertNotIn("docs/", asked)
            self.assertEqual(load_session("chat1", root=root).entry_id, "start")

            stayed = _tokens(iter_page_answer("不换。", streamer=boom, session="chat1", session_dir=root, today=day))
            self.assertIn("这次不换", stayed)
            self.assertEqual(load_session("chat1", root=root).switch, "")

            def follow(prompt):
                self.assertIn("五分钟", prompt)
                yield "那就五分钟。"

            continued = _tokens(iter_page_answer(
                "那我今天只有五分钟呢？",
                earlier=[{"role": "user", "content": start}, {"role": "assistant", "content": "先动一下。"}],
                streamer=follow,
                session="chat1",
                session_dir=root,
                today=day,
            ))
            self.assertIn("五分钟", continued)
            self.assertNotIn("换主线", continued)
            self.assertEqual(load_session("chat1", root=root).entry_id, "start")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def speak_again(prompt):
                self.assertIn("听力", prompt)
                yield "先听一小段。"

            list(iter_page_answer(start, streamer=speak, session="move", session_dir=root, today=day))
            list(iter_page_answer(listening, streamer=boom, session="move", session_dir=root, today=day))
            switched = _tokens(iter_page_answer("换主线", streamer=speak_again, session="move", session_dir=root, today=day))
            self.assertIn("主线换过来了", switched)
            self.assertIn("怎么做", switched)
            self.assertNotIn("docs/", switched)
            self.assertEqual(load_session("move", root=root).entry_id, "listening")

            import planner.page_reply as page_reply

            seen = {}

            def capture(prompt, earlier=None, hint=""):
                seen["prompt"] = prompt
                seen["earlier"] = list(earlier or [])
                yield "先听一小段。"

            original_speak = page_reply.stream_human
            original_weights = page_reply.linked_weights
            page_reply.stream_human = capture
            page_reply.linked_weights = lambda: Path("models/fake.gguf")
            try:
                list(iter_page_answer(start, streamer=speak, session="fresh", session_dir=root, today=day))
                list(iter_page_answer(listening, streamer=boom, session="fresh", session_dir=root, today=day))
                heard = _tokens(iter_page_answer(
                    "换主线",
                    earlier=[{"role": "assistant", "content": "上一轮还在说阅读指南"}],
                    session="fresh",
                    session_dir=root,
                    today=day,
                ))
            finally:
                page_reply.stream_human = original_speak
                page_reply.linked_weights = original_weights
            self.assertNotIn("prompt", seen)
            self.assertIn("怎么做", heard)
            self.assertNotIn("阅读指南", heard)

    def test_crisis_and_early_cycle_do_not_replace_the_chat_line(self):
        day = date(2026, 10, 12)
        start = "我不知道从哪开始，只想重新动一下。现在没有正在做的事，今天大概有半小时。希望先有一个今天能做的动作。"

        def speak(_prompt):
            yield "先动一下。"

        def boom(_prompt):
            raise AssertionError("这条不该往下写")
            yield ""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            list(iter_page_answer(start, streamer=speak, session="chat1", session_dir=root, today=day))
            before = (root / "chat1.yaml").read_text(encoding="utf-8")
            crisis = _tokens(iter_page_answer("我这两天有危险念头，不想活了。", streamer=boom, session="chat1", session_dir=root, today=day))
            self.assertIn("我先停一下", crisis)
            self.assertEqual((root / "chat1.yaml").read_text(encoding="utf-8"), before)
            blocked = _tokens(iter_page_answer(
                "我想要一个九十天的周期规划，把接下来三个月排开。今天有一小时。",
                streamer=boom,
                session="chat1",
                session_dir=root,
                today=day,
            ))
            self.assertIn("不排九十天", blocked)
            self.assertEqual(load_session("chat1", root=root).entry_id, "start")

            list(iter_page_answer(
                "我做完了，这是记录：写了半页学习状态。",
                streamer=speak,
                session="chat1",
                session_dir=root,
                today=day,
            ))
            prior = load_session("chat1", root=root).action
            seen = {}

            def opened_cycle(prompt):
                seen["prompt"] = prompt
                yield "继续原来那一步。"

            opened = _tokens(iter_page_answer(
                "我想要一个九十天的周期规划，把接下来三个月排开。今天有一小时。",
                streamer=opened_cycle,
                session="chat1",
                session_dir=root,
                today=date(2026, 10, 26),
            ))
            self.assertIn("原来那一步放进九十天", opened)
            self.assertIn("2026-11-09", opened)
            self.assertIn(prior[:24], opened)
            self.assertNotIn("产品演示", opened)
            self.assertNotIn("docs/", opened)
            self.assertIn("怎么做", opened)
            self.assertEqual(load_session("chat1", root=root).entry_id, "cycle")
            self.assertEqual(load_session("chat1", root=root).action, prior)
            self.assertNotIn("prompt", seen)

    def test_plain_answers_without_a_chat_do_not_write_sessions(self):
        before = sorted(path.name for path in SESSIONS_DIR.iterdir())

        def speak(_prompt):
            yield "先动一下。"

        list(iter_page_answer("我不知道从哪开始，只想重新动一下。今天有半小时。", streamer=speak))
        after = sorted(path.name for path in SESSIONS_DIR.iterdir())
        self.assertEqual(before, after)

    def test_saved_chat_opens_with_its_messages(self):
        origin = chats.CHATS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            chats.CHATS_DIR = Path(tmp)
            try:
                saved = chats.save_chat(
                    "abc12345",
                    [
                        {"role": "user", "content": "我不知道从哪开始"},
                        {"role": "assistant", "content": "先动一下。"},
                        {"role": "note", "content": "丢掉"},
                    ],
                )
                self.assertEqual(saved["title"], "我不知道从哪开始")
                renamed = chats.save_chat(
                    "abc12345",
                    [
                        {"role": "user", "content": "我不知道从哪开始"},
                        {"role": "assistant", "content": "先动一下。"},
                    ],
                    title="重新出发",
                    note="这周只看从哪开始",
                )
                self.assertEqual(renamed["title"], "重新出发")
                self.assertEqual(renamed["note"], "这周只看从哪开始")
                kept = chats.save_chat(
                    "abc12345",
                    [
                        {"role": "user", "content": "我不知道从哪开始"},
                        {"role": "assistant", "content": "先动一下。"},
                    ],
                )
                self.assertEqual(kept["title"], "重新出发")
                self.assertEqual(kept["note"], "这周只看从哪开始")
                self.assertEqual(chats.list_chats()[0]["note"], "这周只看从哪开始")
                loaded = chats.load_chat("abc12345")
                self.assertEqual(
                    loaded["messages"],
                    [
                        {"role": "user", "content": "我不知道从哪开始"},
                        {"role": "assistant", "content": "先动一下。"},
                    ],
                )
                self.assertEqual(chats.list_chats()[0]["id"], "abc12345")
                self.assertIsNone(chats.load_chat("../secrets"))
            finally:
                chats.CHATS_DIR = origin

    def test_markdown_marks_are_removed(self):
        text = "".join(_visible(["1. **提高口语**：每天说一点。\n", "加油。"]))
        self.assertEqual(text, "提高口语：每天说一点。\n加油。")
        self.assertNotIn("*", text)

    def test_repeated_sentence_stops(self):
        sentence = "我会在什么时候再看一眼？"
        kept = "".join(_without_loop([sentence] * 6))
        self.assertLess(kept.count(sentence), 4)

    def test_answer_endpoint_streams_tokens(self):
        def fake(text, earlier=None, streamer=None, session=None, session_dir=None, today=None, **_extra):
            self.assertEqual(text, "今天有半小时")
            self.assertEqual(earlier, [])
            self.assertIsNone(session)
            yield ("token", "先动")
            yield ("token", "一下。")

        original = page.iter_page_answer
        page.iter_page_answer = fake
        server = page.make_server(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            data = "今天有半小时".encode("utf-8")
            request = urllib.request.Request(
                f"http://{host}:{port}/answer",
                data=data,
                headers={"Content-Type": "text/plain; charset=utf-8"},
            )
            with urllib.request.urlopen(request) as response:
                body = response.read().decode("utf-8")
            self.assertNotIn("event: note", body)
            self.assertIn("event: token", body)
            self.assertIn("data: 先动", body)
            self.assertIn("data: 一下。", body)
        finally:
            page.iter_page_answer = original
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


    def test_answer_endpoint_keeps_the_chat_id(self):
        seen = {}

        def fake(text, earlier=None, streamer=None, session=None, session_dir=None, today=None, **_extra):
            seen["session"] = session
            yield ("token", "先动一下。")

        original = page.iter_page_answer
        page.iter_page_answer = fake
        server = page.make_server(0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host, port = server.server_address
            body = json.dumps({"text": "今天有半小时", "earlier": [], "chat": "abc12345"}).encode()
            request = urllib.request.Request(
                f"http://{host}:{port}/answer",
                data=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            with urllib.request.urlopen(request) as response:
                response.read()
            self.assertEqual(seen["session"], "abc12345")
            bad = json.dumps({"text": "今天有半小时", "earlier": [], "chat": "../outside"}).encode()
            rejected = urllib.request.Request(
                f"http://{host}:{port}/answer",
                data=bad,
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            with self.assertRaises(urllib.error.HTTPError) as caught:
                urllib.request.urlopen(rejected)
            self.assertEqual(caught.exception.code, 400)
        finally:
            page.iter_page_answer = original
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_a_plan_is_spoken_in_full(self):
        def boom(_prompt):
            raise AssertionError("筛中之后不该把步骤缩成模型的一句")
            yield ""

        spoken = _tokens(iter_page_answer(
            "我只想练英语听力。今天有四十分钟，想要一个今天的练习。",
            streamer=boom,
        ))
        self.assertIn("1. ", spoken)
        self.assertIn("怎么做", spoken)
        self.assertIn("30 秒", spoken)
        self.assertIn("不要用第二遍", spoken)
        self.assertIn("复测", spoken)
        self.assertIn("不排长周期", spoken)
        self.assertNotIn("rensheng/", spoken)
        self.assertNotIn("文件：", spoken)
        self.assertGreater(len(spoken), 80)

    def test_asking_for_detail_finishes_the_current_plan(self):
        day = date(2026, 10, 12)
        listening = "我只想练英语听力。还没练过。今天有四十分钟，想要一个今天的练习。"

        def boom(_prompt):
            raise AssertionError("要把规划说完时，不该写到一半被截断")
            yield ""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            list(iter_page_answer(listening, streamer=boom, session="hear", session_dir=root, today=day))
            more = _tokens(iter_page_answer("详细规划", streamer=boom, session="hear", session_dir=root, today=day))
        self.assertIn("30 秒", more)
        self.assertIn("怎么做", more)
        self.assertIn("1. ", more)
        self.assertTrue(more.rstrip().endswith("。"))

    def test_a_thin_opening_asks_one_missing_piece(self):
        day = date(2026, 10, 12)

        def boom(_prompt):
            raise AssertionError("还没听清就不该写计划")
            yield ""

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = _tokens(iter_page_answer("我不知道从哪开始", streamer=boom, session="ask", session_dir=root, today=day))
            self.assertIn("已经做过什么", first)
            self.assertNotIn("多少时间", first)
            self.assertNotIn("怎么做", first)
            pending = load_session("ask", root=root)
            self.assertEqual(pending.awaiting, "done")
            self.assertEqual(pending.action, "")

            second = _tokens(iter_page_answer("什么都没做过。", streamer=boom, session="ask", session_dir=root, today=day))
            self.assertIn("多少时间", second)
            self.assertNotIn("已经做过什么", second)
            self.assertEqual(load_session("ask", root=root).awaiting, "capacity")

            third = _tokens(iter_page_answer(
                "今天有半小时，想要今天的一步。",
                streamer=boom,
                session="ask",
                session_dir=root,
                today=day,
            ))
            self.assertIn("怎么做", third)
            saved = load_session("ask", root=root)
            self.assertEqual(saved.entry_id, "start")
            self.assertEqual(saved.awaiting, "")
            self.assertTrue(saved.action)

    def test_a_valid_summary_rewrites_only_the_step(self):
        start = "我不知道从哪开始，只想重新动一下。现在没有正在做的事，今天大概有半小时。希望先有一个今天能做的动作。"
        tight = _page_transport("今天只做 20 分钟，做完就停。", "空档更紧，所以这一步收紧到 20 分钟，长安排后移。")
        open_step = _page_transport("今天把书里的最小动作做完，并留下证据。", "时间够用，所以只调整顺序，先留下证据。")

        def boom(_prompt):
            raise AssertionError("形势对照不该改走自由生成")
            yield ""

        tight_text = _tokens(iter_page_answer(
            start,
            streamer=boom,
            model="api",
            context="data/context/sample-tight.md",
            transport=tight,
        ))
        open_text = _tokens(iter_page_answer(
            start,
            streamer=boom,
            model="api",
            context="data/context/sample-open.md",
            transport=open_step,
        ))
        self.assertEqual(_point_title(tight_text), _point_title(open_text))
        self.assertIn("今天只做 20 分钟，做完就停。", tight_text)
        self.assertIn("今天把书里的最小动作做完，并留下证据。", open_text)
        self.assertIn("形势判断：空档更紧", tight_text)
        self.assertIn("时间被压短的一周", tight_text)
        self.assertIn("2026-10-01", tight_text)
        self.assertIn("本周可用时间记录", tight_text)
        self.assertIn("形势判断：时间够用，所以只调整顺序", open_text)
        self.assertNotIn("docs/", tight_text)
        self.assertNotIn("20 分钟", open_text)

    def test_a_bad_summary_keeps_the_book_step(self):
        start = "我不知道从哪开始，只想重新动一下。现在没有正在做的事，今天大概有半小时。希望先有一个今天能做的动作。"

        def outside(_messages, _package):
            return '{"action":"去看 docs/threads/part-9/missing.md 再做完。","situation":"这一步收紧，但路径被改掉了。"}'

        def untouched(_messages, _package):
            raise AssertionError("不合格的摘要不该交给模型")

        leaked = _tokens(iter_page_answer(
            start,
            model="api",
            context="data/context/sample-tight.md",
            transport=outside,
        ))
        self.assertNotIn("形势判断", leaked)
        self.assertNotIn("part-9", leaked)
        self.assertIn("怎么做", leaked)

        plain = _tokens(iter_page_answer(
            start,
            model="api",
            context="data/context/sample-invalid.md",
            transport=untouched,
        ))
        self.assertNotIn("形势判断", plain)

        def called(_messages, _package):
            raise AssertionError("没筛中不该读形势摘要")

        missed = _tokens(iter_page_answer(
            "帮我判断明天哪只股票会涨。",
            speaker=lambda _sheet, _nearest: (_ for _ in ()).throw(AssertionError("API 不写自述")),
            model="api",
            context="data/context/sample-tight.md",
            transport=called,
        ))
        self.assertIn("没有对上", missed)
        self.assertNotIn("模型自述", missed)
        self.assertNotIn("形势判断", missed)

    def test_detail_uses_the_earlier_question_as_points(self):
        earlier = [
            {"role": "user", "content": "我只想练英语听力。今天有四十分钟。"},
            {"role": "assistant", "content": "先听一小段。"},
        ]

        def boom(_prompt):
            raise AssertionError("详细计划要沿用刚才的事，不交给模型另编")
            yield ""

        spoken = _tokens(iter_page_answer("详细计划", earlier=earlier, streamer=boom))
        self.assertIn("1. ", spoken)
        self.assertIn("怎么做", spoken)
        self.assertIn("30 秒", spoken)
        self.assertNotIn("Happy", spoken)

    def test_a_chat_compiles_into_a_plan_and_a_map(self):
        from planner.brief import compile_messages

        messages = [
            {"role": "user", "content": "我只想练英语听力。今天有四十分钟。"},
            {"role": "assistant", "content": "先听一小段。"},
            {"role": "user", "content": "详细计划"},
            {
                "role": "assistant",
                "content": "1. 选择 30 秒到 5 分钟的材料\n怎么做：先选定一段能合法打开的音频。\n\n2. 不要用第二遍盖掉第一遍\n先不要这样做：第一遍听到什么就留着什么。\n\n3. 到日子再看\n怎么做：十四天后再看这份记录。",
            },
        ]
        brief = compile_messages(messages, "练听力")
        self.assertEqual(brief["question"], "我只想练英语听力。今天有四十分钟。")
        self.assertEqual(brief["said"], ["我只想练英语听力。今天有四十分钟。"])
        self.assertEqual(brief["steps"][0]["how"], "先选定一段能合法打开的音频。")
        self.assertEqual(brief["avoid"][0]["title"], "不要用第二遍盖掉第一遍")
        self.assertEqual(brief["review"]["how"], "十四天后再看这份记录。")
        self.assertNotIn("Happy", str(brief))
        self.assertEqual(brief["notice"], "")
        self.assertIsNone(brief["situation"])

        origin = chats.CHATS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            chats.CHATS_DIR = Path(tmp)
            try:
                server = page.make_server(0)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    host, port = server.server_address
                    body = json.dumps({"title": "练听力", "messages": messages, "chat": ""}).encode()
                    request = urllib.request.Request(
                        f"http://{host}:{port}/brief",
                        data=body,
                        headers={"Content-Type": "application/json; charset=utf-8"},
                    )
                    with urllib.request.urlopen(request) as response:
                        payload = json.loads(response.read().decode("utf-8"))
                    self.assertEqual(payload["steps"][0]["title"], "选择 30 秒到 5 分钟的材料")
                    self.assertEqual(payload["review"]["kind"], "review")
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
            finally:
                chats.CHATS_DIR = origin

    def test_a_compiled_plan_cites_the_book_and_keeps_the_map_plain(self):
        from planner.brief import compile_messages
        from planner.paths import ROOT
        from planner.reply.fill import FOOTER

        question = "我只想练英语听力。还没练过。今天有四十分钟，想要一个今天的练习。"
        spoken = _tokens(iter_page_answer(question))
        self.assertNotIn("rensheng/", spoken)
        self.assertNotIn("docs/", spoken)
        self.assertNotIn("信息种类", spoken)
        note = (
            "\n\n形势判断：空档更紧，所以这一步收紧到 20 分钟。\n"
            "材料：时间被压短的一周 · 2026-10-01 · 本人 2026-10-01 的本周可用时间记录\n"
            "适用范围：只约束这一步的时长，不改书里的入口"
        )
        brief = compile_messages(
            [
                {"role": "user", "content": question},
                {"role": "assistant", "content": spoken + note},
            ],
            "练听力",
        )
        cited = [*brief["steps"], *brief["avoid"], *brief["stop"]]
        self.assertTrue(cited)
        for point in cited:
            self.assertTrue(point["path"].startswith("rensheng/"))
            self.assertTrue((ROOT / point["path"]).is_file())
            self.assertTrue(point["chapter"])
            self.assertIn(point["info"], ("研究结论", "个人经验", "待验证假设"))
            self.assertNotIn("rensheng/", point["title"])
            self.assertNotIn("形势判断", point["how"])
        self.assertNotIn("path", brief["review"])
        self.assertEqual(brief["situation"]["kind"], "形势判断")
        self.assertEqual(brief["situation"]["title"], "时间被压短的一周")
        self.assertEqual(brief["situation"]["date"], "2026-10-01")
        self.assertIn("本周可用时间记录", brief["situation"]["source"])
        self.assertNotIn("研究结论", brief["situation"]["kind"])
        self.assertEqual(brief["notice"], FOOTER)
        self.assertIn("韩先凯", brief["notice"])
        self.assertIn("CC BY-NC 4.0", brief["notice"])
        self.assertIn("背书", brief["notice"])
        visible = "\n".join(
            [
                brief["question"],
                brief["title"],
                *brief["said"],
                *(point["title"] for point in cited),
                brief["review"]["title"],
                brief["review"]["how"],
            ]
        )
        self.assertNotIn("rensheng/", visible)
        self.assertNotIn("docs/", visible)
        self.assertNotIn("形势判断", visible)

    def test_a_later_plan_is_cited_from_its_own_question(self):
        from planner.brief import compile_messages
        from planner.paths import ROOT

        question = "我已经留下十四天证据，想要一个九十天的周期规划。今天有一小时。"
        spoken = _tokens(iter_page_answer(question))
        brief = compile_messages(
            [
                {"role": "user", "content": "我只想练英语听力。还没练过。今天有四十分钟，想要一个今天的练习。"},
                {"role": "assistant", "content": "1. 先听一小段\n怎么做：先听一小段。"},
                {"role": "user", "content": "换主线"},
                {"role": "user", "content": question},
                {"role": "assistant", "content": spoken},
            ]
        )
        cited = [point for point in (*brief["steps"], *brief["avoid"], *brief["stop"]) if point.get("path")]
        self.assertTrue(cited)
        self.assertTrue(all("90-day" in point["path"] for point in cited))
        self.assertTrue(all((ROOT / point["path"]).is_file() for point in cited))
        self.assertNotIn("3-listening.md", str(point["path"] for point in cited))

    def test_a_cut_reply_stops_at_the_last_sentence(self):
        from planner.model.local.speak import finish_at_sentence

        cut = finish_at_sentence("先听一小段。然后再翻译成句子和", cut=True)
        self.assertEqual(cut, "先听一小段。")
        whole = finish_at_sentence("先听一小段。然后再翻译成句子和", cut=False)
        self.assertEqual(whole, "先听一小段。然后再翻译成句子和")

    def test_delete_removes_the_chat(self):
        origin = chats.CHATS_DIR
        with tempfile.TemporaryDirectory() as tmp:
            chats.CHATS_DIR = Path(tmp)
            try:
                chats.save_chat("abc12345", [{"role": "user", "content": "你好"}])
                server = page.make_server(0)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    host, port = server.server_address
                    request = urllib.request.Request(f"http://{host}:{port}/chats/abc12345", method="DELETE")
                    with urllib.request.urlopen(request) as response:
                        self.assertEqual(response.status, 200)
                    self.assertIsNone(chats.load_chat("abc12345"))
                    again = urllib.request.Request(f"http://{host}:{port}/chats/abc12345", method="DELETE")
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(again)
                    self.assertEqual(caught.exception.code, 404)
                    bad = urllib.request.Request(f"http://{host}:{port}/chats/nope", method="DELETE")
                    with self.assertRaises(urllib.error.HTTPError) as caught:
                        urllib.request.urlopen(bad)
                    self.assertEqual(caught.exception.code, 400)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(timeout=2)
            finally:
                chats.CHATS_DIR = origin


def _tokens(events) -> str:
    return "".join(item[1] for item in events if item[0] == "token")


def _page_transport(action, situation):
    payload = json.dumps({"action": action, "situation": situation}, ensure_ascii=False)

    def transport(_messages, _package):
        return payload

    return transport


def _point_title(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("1. "):
            return line
    raise AssertionError(text[:240])


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _serve():
    server = page.make_server(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
