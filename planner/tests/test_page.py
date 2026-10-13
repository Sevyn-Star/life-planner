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

        def streamer(prompt):
            seen.append(prompt)
            self.assertNotIn("rensheng/", prompt)
            yield "先动一下。"

        events = list(iter_page_answer("帮我判断明天哪只股票会涨。", streamer=streamer))
        self.assertTrue(seen)
        self.assertIn("股票", seen[0])
        self.assertNotIn("我现在说", seen[0])
        self.assertNotIn("不要", seen[0])
        self.assertFalse(any(item[0] == "note" for item in events))
        self.assertEqual([item[1] for item in events if item[0] == "token"], ["先动一下。"])

        def follow(prompt):
            seen.append(prompt)
            yield "那就五分钟。\n这本书没有直接写到这件事。\n我现在说：「好的」。"

        later = list(iter_page_answer(
            "那我今天只有五分钟呢？",
            earlier=[{"role": "user", "content": "我不知道从哪开始"}, {"role": "assistant", "content": "先动一下。"}],
            streamer=follow,
        ))
        self.assertIn("五分钟", seen[-1])
        self.assertNotIn("我说", seen[-1])
        self.assertEqual(
            "".join(item[1] for item in later if item[0] == "token").strip(),
            "那就五分钟。",
        )

    def test_a_chat_asks_before_leaving_its_line(self):
        day = date(2026, 10, 12)
        start = "我不知道从哪开始，只想重新动一下。现在没有正在做的事，今天大概有半小时。希望先有一个今天能做的动作。"
        listening = "我只想练英语听力。今天有四十分钟，想要一个今天的练习。"

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
            self.assertIn("听力", seen["prompt"])
            self.assertEqual(seen["earlier"], [])
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
        def fake(text, earlier=None, streamer=None, session=None, session_dir=None, today=None):
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

        def fake(text, earlier=None, streamer=None, session=None, session_dir=None, today=None):
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


def _tokens(events) -> str:
    return "".join(item[1] for item in events if item[0] == "token")


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
