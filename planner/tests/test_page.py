import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import planner.chats as chats
import planner.page as page
from planner.page_reply import _visible, _without_loop, iter_page_answer


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
        def fake(text, earlier=None):
            self.assertEqual(text, "今天有半小时")
            self.assertEqual(earlier, [])
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
