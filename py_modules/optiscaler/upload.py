"""A one-file upload page on the local network, for handing the Deck a file.

PDPerfPlugin.dll cannot be shipped or downloaded here, and fetching it in
Desktop Mode is the step people get stuck on. So the plugin can open a page on
the Deck's own address that a phone on the same Wi-Fi reaches through a QR
code: the phone downloads the file from Nexus Mods, picks it on that page, and
it arrives here.

The page is deliberately small and short-lived:

- it is only open after the user asks for it, until one file has arrived or
  UPLOAD_TTL has passed, whichever comes first;
- every path carries a fresh random token, so nothing else on the network
  finds it by scanning a port;
- the file is sent as the raw request body (the page does that with fetch), so
  there is no form parsing, and anything over UPLOAD_MAX_BYTES is refused
  before it is read.

What arrives is handed to ``on_file`` (a path to a temporary copy and the name
it was sent under), whose answer goes back to the phone.
"""

import json
import secrets
import socket
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

UPLOAD_TTL = 10 * 60  # seconds
UPLOAD_MAX_BYTES = 256 * 1024 * 1024


def lan_address():
    """This machine's address on the local network, or None when it has none.

    A UDP "connect" sends nothing; it only asks the kernel which interface
    would route outwards, which is the one the phone shares.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        address = probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()
    return None if address.startswith("127.") or address == "0.0.0.0" else address


PAGE = """<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Steam Deck으로 보내기</title>
<style>
 body{{font-family:system-ui,sans-serif;margin:0;padding:24px;background:#1b2838;color:#e6edf3}}
 h1{{font-size:1.3rem}} p{{line-height:1.5;color:#b8c4ce}}
 input,button{{font-size:1rem;margin-top:12px;width:100%}}
 button{{padding:14px;border:0;border-radius:6px;background:#1a9fff;color:#fff}}
 button:disabled{{background:#3d4f63}} #out{{margin-top:16px;font-weight:600}}
</style></head><body>
<h1>{title}</h1>
<p>{hint}</p>
<input id="f" type="file">
<button id="b">Steam Deck으로 보내기</button>
<div id="out"></div>
<script>
const b=document.getElementById('b'),f=document.getElementById('f'),o=document.getElementById('out');
b.onclick=async()=>{{
  if(!f.files.length){{o.textContent='먼저 파일을 고르세요.';return;}}
  b.disabled=true;o.textContent='보내는 중…';
  try{{
    const r=await fetch(location.pathname.replace(/\\/$/,'')+'/upload',{{method:'POST',
      headers:{{'X-File-Name':encodeURIComponent(f.files[0].name)}},body:f.files[0]}});
    const j=await r.json();o.textContent=j.message;if(!j.ok)b.disabled=false;
  }}catch(e){{o.textContent='보내지 못했습니다: '+e;b.disabled=false;}}
}};
</script></body></html>"""


class UploadSession:
    """One upload page, open until a file is taken or it expires."""

    def __init__(self, on_file, title, hint, logger=None, ttl=UPLOAD_TTL,
                 max_bytes=UPLOAD_MAX_BYTES, address=None):
        self.on_file = on_file
        self.logger = logger
        self.max_bytes = max_bytes
        self.token = secrets.token_urlsafe(16)
        self.expires_at = time.time() + ttl
        self.result = None
        self._page = PAGE.format(title=title, hint=hint).encode("utf-8")
        self._lock = threading.Lock()
        host = address or lan_address()
        if not host:
            raise OSError("이 기기의 Wi-Fi 주소를 찾지 못했습니다. 네트워크에 연결되어 있는지 확인하세요.")
        self._server = ThreadingHTTPServer(("0.0.0.0", 0), self._handler())
        self._server.daemon_threads = True
        self.url = f"http://{host}:{self._server.server_address[1]}/{self.token}"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        self._timer = threading.Timer(ttl, self.close)
        self._timer.daemon = True
        self._timer.start()

    @property
    def active(self):
        return self._server is not None

    def status(self):
        return {"active": self.active, "url": self.url if self.active else None,
                "expires_at": self.expires_at, "result": self.result}

    def close(self):
        with self._lock:
            server, self._server = self._server, None
        if server is not None:
            self._timer.cancel()
            # shutdown() waits for serve_forever, so never from its own thread.
            threading.Thread(target=lambda: (server.shutdown(), server.server_close()),
                             daemon=True).start()

    def _receive(self, handler):
        """Read one upload into a temporary file and hand it on."""
        try:
            length = int(handler.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return 400, {"ok": False, "message": "파일이 비어 있습니다."}
        if length > self.max_bytes:
            return 413, {"ok": False, "message": "파일이 너무 큽니다."}
        from urllib.parse import unquote
        name = Path(unquote(handler.headers.get("X-File-Name") or "upload")).name or "upload"
        with tempfile.TemporaryDirectory(prefix="decky-upload-") as tmp:
            path = Path(tmp) / name
            remaining = length
            with open(path, "wb") as out:
                while remaining:
                    chunk = handler.rfile.read(min(remaining, 1 << 20))
                    if not chunk:
                        break
                    out.write(chunk)
                    remaining -= len(chunk)
            if remaining:
                return 400, {"ok": False, "message": "전송이 중간에 끊겼습니다. 다시 보내 주세요."}
            try:
                answer = self.on_file(path, name)
            except Exception as exc:  # reported to the phone, which can try again
                if self.logger:
                    self.logger.warning("upload rejected: %s", exc)
                return 400, {"ok": False, "message": str(exc)}
        self.result = answer
        if answer.get("ok"):
            self.close()
        return 200, answer

    def _handler(self):
        session = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # the plugin log, not stderr
                if session.logger:
                    session.logger.debug("upload page: " + args[0], *args[1:])

            def _send(self, code, body, kind):
                self.send_response(code)
                self.send_header("Content-Type", kind)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code, payload):
                self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")

            def do_GET(self):
                if self.path.rstrip("/") == f"/{session.token}":
                    self._send(200, session._page, "text/html; charset=utf-8")
                else:
                    self._send(404, b"not found", "text/plain")

            def do_POST(self):
                if self.path != f"/{session.token}/upload":
                    self._send(404, b"not found", "text/plain")
                    return
                code, payload = session._receive(self)
                self._json(code, payload)

        return Handler
