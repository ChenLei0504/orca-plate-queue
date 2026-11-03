"""Short-lived loopback receiver for user-driven official Bambu browser sign-in.
No passwords, verification-code requests, cookie discovery or print endpoints.
"""
import json
import queue
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import TCPServer
from urllib.parse import parse_qs, urlencode, urlsplit


class _QuietServer(HTTPServer):
    def server_bind(self):
        TCPServer.server_bind(self)
        self.server_name = '127.0.0.1'
        self.server_port = self.server_address[1]

    def handle_error(self, request, client_address):
        pass  # No request URLs or tickets in exception traces.


class BrowserLogin:
    def __init__(self, region, *, lifetime=300):
        if region not in ('CN', 'US'):
            raise ValueError('请选择中国大陆或全球区。')
        self.region = region
        self._path = '/callback/' + secrets.token_urlsafe(32)
        self._ticket = queue.Queue(maxsize=1)
        self._stop = threading.Event()
        self._taken = False
        self._lock = threading.Lock()
        self._deadline = time.monotonic() + lifetime
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(2)

            def log_message(self, *_):
                pass  # Request URLs can contain a one-time ticket.

            def reply(self, status, body):
                body = body.encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()
                self.wfile.write(body)

            def allowed(self):
                try:
                    path = urlsplit(self.path).path
                except ValueError:
                    return False
                host = self.headers.get_all('Host', [])
                return (host == [owner.authority] and
                        sum(len(k)+len(v) for k,v in self.headers.items()) <= 8192 and
                        path == owner._path and
                        self.path.startswith(owner._path) and
                        time.monotonic() < owner._deadline and not owner._stop.is_set())

            def do_GET(self):
                if not self.allowed():
                    self.reply(404, 'Login request is invalid or expired.'); return
                try:
                    params = parse_qs(urlsplit(self.path).query, max_num_fields=20, keep_blank_values=True)
                except ValueError:
                    self.reply(400, 'Invalid callback.'); return
                tickets = params.get('ticket', [])
                if len(tickets) == 1:
                    accepted = owner.take(tickets[0])
                    self.reply(200 if accepted else 409,
                        '<!doctype html><meta charset="utf-8"><script>history.replaceState(null,"",location.pathname)</script>'
                        + ('登录票据已接收，请返回 Orca 查看结果。<br>Sign-in received. Return to Orca to check the result.' if accepted else 'Login already received or invalid.'))
                elif tickets:
                    self.reply(400, 'Invalid callback.')
                else:
                    # Some website versions use a fragment. Only this local page
                    # reads it, scrubs history, then posts to its own nonce path.
                    self.reply(200, '''<!doctype html><meta charset="utf-8"><p id="s">正在接收登录结果…</p><script>
const p=new URLSearchParams(location.hash.slice(1));const a=p.getAll('ticket');history.replaceState(null,'',location.pathname);
if(a.length===1){fetch(location.pathname,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticket:a[0]})}).then(r=>{document.getElementById('s').textContent=r.ok?'登录票据已接收，请返回 Orca 查看结果。':'登录结果无效，请返回 Orca 重新登录。'}).catch(()=>{document.getElementById('s').textContent='接收失败，请返回 Orca。'})}else{document.getElementById('s').textContent='未收到登录票据，请返回 Orca 重新登录。'}
</script>''')

            def do_POST(self):
                if not self.allowed() or self.headers.get('Origin') != owner.origin:
                    self.reply(403, 'Invalid callback origin.'); return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 12000 or self.headers.get('Transfer-Encoding'):
                        raise ValueError()
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict) or set(data) != {'ticket'}:
                        raise ValueError()
                    accepted = owner.take(data['ticket'])
                except (ValueError, OSError):
                    self.reply(400, 'Invalid callback.'); return
                self.reply(200 if accepted else 409, 'Return to Orca to check sign-in.')

        self._server = _QuietServer(('127.0.0.1', 0), Handler)
        self._server.timeout = .2
        self.authority = '127.0.0.1:' + str(self._server.server_port)
        self.origin = 'http://' + self.authority
        self.callback_url = self.origin + self._path
        # Same ticket flow used by Orca-derived browser login implementations.
        base = 'https://' + ('bambulab.cn' if region == 'CN' else 'bambulab.com') + '/sign-in'
        callback = base + '/callback?' + urlencode(dict(source='portal', locale='zh-cn' if region=='CN' else 'en',
            redirect_url=self.callback_url, openBy='suite', **{'from':'studio'}, slicerLoginType='ticket'))
        self.url = base + '?' + urlencode({'from':'studio','source':'portal','to':callback})
        self._thread = threading.Thread(target=self._serve, daemon=True, name='queue-browser-callback')
        try:
            self._thread.start()
        except Exception:
            self._server.server_close()
            raise

    def _serve(self):
        try:
            while not self._stop.is_set() and time.monotonic() < self._deadline:
                self._server.handle_request()
        finally:
            self._server.server_close()

    def take(self, ticket):
        if not isinstance(ticket, str) or not re.fullmatch(r'[A-Za-z0-9_.~-]{1,8192}', ticket):
            return False
        with self._lock:
            if self._taken or self._stop.is_set() or time.monotonic() >= self._deadline:
                return False
            self._taken = True
            self._ticket.put_nowait(ticket)
            return True

    def poll(self):
        try:
            return self._ticket.get_nowait()
        except queue.Empty:
            return None

    @property
    def expired(self):
        return time.monotonic() >= self._deadline

    def close(self):
        self._stop.set()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=3)
        self._server.server_close()
        try:
            self._ticket.get_nowait()
        except queue.Empty:
            pass
