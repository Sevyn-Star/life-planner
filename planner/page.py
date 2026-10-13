"""本机页面。标准库在 127.0.0.1 上打开项目根目录的 index.html。"""

import html
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from planner.brief import compile_messages
from planner.chats import delete_chat, list_chats, load_chat, save_chat
from planner.model.config import configured_backend
from planner.model import ModelError
from planner.page_reply import iter_page_answer
from planner.paths import ROOT
from planner.session import delete_session, load_session, session_path

HOST = "127.0.0.1"
PORT = 8765
PAGE = ROOT / "index.html"
MAX_BODY = 40000
_EMPTY_TEXTAREA = '<textarea id="text" rows="1" placeholder="接着说，或换一件卡着的事"></textarea>'


def render_page(text: str = "", reply: str = "", error: str = "") -> bytes:
    page = PAGE.read_text(encoding="utf-8")
    filled = _EMPTY_TEXTAREA.replace("></textarea>", f">{html.escape(text)}</textarea>", 1)
    page = page.replace(_EMPTY_TEXTAREA, filled, 1)
    if error:
        block = f'<p class="error">{html.escape(error)}</p>'
    elif reply:
        block = f"<h2>回复</h2>\n<pre>{html.escape(reply)}</pre>"
    else:
        block = ""
    page = page.replace("<!-- result -->", block, 1)
    return page.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/chats":
            self._json(200, list_chats())
            return
        if path.startswith("/chats/"):
            chat = load_chat(path.removeprefix("/chats/"))
            if chat is None:
                self._send_text(404, "没有这段对话")
                return
            self._json(200, chat)
            return
        if path not in {"/", "/index.html"}:
            self._send(404, b"")
            return
        self._send(200, render_page())

    def do_DELETE(self):
        path = self.path.split("?", 1)[0]
        if not path.startswith("/chats/"):
            self._send(404, b"")
            return
        chat_id = path.removeprefix("/chats/")
        try:
            removed = delete_chat(chat_id)
            delete_session(chat_id)
        except ValueError as exc:
            self._send_text(400, str(exc) or "这段对话对不上。")
            return
        if not removed:
            self._send_text(404, "没有这段对话")
            return
        self._json(200, {"id": chat_id})

    def do_PUT(self):
        path = self.path.split("?", 1)[0]
        if not path.startswith("/chats/"):
            self._send(404, b"")
            return
        try:
            data = json.loads(self._read_body())
            if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
                raise ValueError("请求不完整。")
            title = data.get("title")
            note = data.get("note")
            if title is not None and not isinstance(title, str):
                raise ValueError("请求不完整。")
            if note is not None and not isinstance(note, str):
                raise ValueError("请求不完整。")
            saved = save_chat(path.removeprefix("/chats/"), data["messages"], title=title, note=note)
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_text(400, str(exc) or "请求不完整。")
            return
        self._json(200, saved)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path == "/brief":
            self._brief()
            return
        if path == "/answer":
            self._stream_answer()
            return
        if path not in {"/", "/index.html"}:
            self._send(404, b"")
            return
        self._redirect("/")

    def _brief(self):
        try:
            data = json.loads(self._read_body())
            if not isinstance(data, dict) or not isinstance(data.get("messages"), list):
                raise ValueError("请求不完整。")
            title = data.get("title") or ""
            chat = data.get("chat") or ""
            if not isinstance(title, str) or not isinstance(chat, str):
                raise ValueError("请求不完整。")
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_text(400, str(exc) or "请求不完整。")
            return
        record = None
        if chat:
            try:
                record = load_session(chat)
            except ValueError as exc:
                self._send_text(400, str(exc) or "这段对话对不上。")
                return
        self._json(200, compile_messages(data["messages"], title, record))

    def _stream_answer(self):
        try:
            text, earlier, chat = self._read_turn()
        except ValueError as exc:
            self._send_text(400, str(exc))
            return
        if not text:
            self._send_text(400, "先写一段困惑。")
            return
        self.close_connection = True
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            try:
                backend = configured_backend()
            except ModelError:
                backend = None
            for event, data in iter_page_answer(text, earlier=earlier, session=chat or None, model=backend):
                self.wfile.write(_sse(event, data))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def _redirect(self, location: str):
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _json(self, status: int, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, text: str):
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_turn(self) -> tuple[str, list]:
        raw = self._read_body()
        if "application/json" in self.headers.get("Content-Type", ""):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError("请求不完整。") from exc
            if not isinstance(data, dict):
                raise ValueError("请求不完整。")
            text = data.get("text", "")
            earlier = data.get("earlier")
            chat = data.get("chat") or ""
            if not isinstance(text, str) or not isinstance(earlier, list) or not isinstance(chat, str):
                raise ValueError("请求不完整。")
            if chat:
                try:
                    session_path(chat)
                except ValueError as exc:
                    raise ValueError("这段对话对不上。") from exc
            return text.strip(), earlier, chat
        return raw.strip(), [], ""

    def _read_body(self) -> str:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError as exc:
            raise ValueError("请求不完整。") from exc
        if length > MAX_BODY:
            raise ValueError("这段话太长了。")
        raw = self.rfile.read(length)
        try:
            decoded = raw.decode("utf-8")
        except UnicodeError as exc:
            raise ValueError("请用 UTF-8 发送这段话。") from exc
        if "text/plain" in self.headers.get("Content-Type", ""):
            return decoded.strip()
        return decoded

    def _send(self, status: int, body: bytes):
        self.send_response(status)
        if body:
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


def _sse(event: str, data: str) -> bytes:
    lines = str(data).split("\n")
    payload = "".join(f"data: {line}\n" for line in lines)
    return f"event: {event}\n{payload}\n".encode("utf-8")


def make_server(port: int = PORT) -> HTTPServer:
    return HTTPServer((HOST, port), Handler)


def main() -> None:
    server = make_server(PORT)
    print(f"页面在 http://{HOST}:{PORT}/", flush=True)
    print(f"也可以直接打开 {PAGE}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
