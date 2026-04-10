"""
Copilot Local Proxy - TK GUI
本地 OpenAI 兼容代理，自动管理 Copilot token 并转发请求
"""
import tkinter as tk
from tkinter import scrolledtext
import threading, json, os, time, uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
import requests

# ============ Config ============
OAUTH_PATH = os.path.join(os.path.expanduser('~'), '.copilot_oauth.json')
COPILOT_TOKEN_URL = 'https://api.github.com/copilot_internal/v2/token'
COPILOT_API_BASE = 'https://api.githubcopilot.com'
PROXY = {'https': 'http://127.0.0.1:2082'}
LOCAL_PORT = 15432
REFRESH_MARGIN = 120  # 提前120秒刷新

COPILOT_HEADERS = {
    'Editor-Version': 'vscode/1.110.1',
    'Editor-Plugin-Version': 'copilot-chat/0.38.2',
    'User-Agent': 'GitHubCopilotChat/0.38.2',
    'Copilot-Integration-Id': 'vscode-chat',
    'openai-intent': 'conversation-panel',
}


# ============ Token Manager ============
class TokenManager:
    def __init__(self, log_fn=print):
        self.copilot_token = None
        self.expires_at = 0
        self.log = log_fn
        self._lock = threading.Lock()
        with open(OAUTH_PATH) as f:
            self.access_token = json.load(f)['access_token']
        self.log(f"[Token] OAuth token loaded: ***{self.access_token[-6:]}")

    def get_token(self):
        with self._lock:
            if time.time() < self.expires_at - REFRESH_MARGIN:
                return self.copilot_token
            return self._refresh()

    def _refresh(self):
        self.log("[Token] Refreshing copilot token...")
        try:
            resp = requests.get(COPILOT_TOKEN_URL, headers={
                'Authorization': f'token {self.access_token}',
                'User-Agent': 'GitHubCopilotChat/0.38.2',
                'Accept': 'application/json',
            }, proxies=PROXY, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            self.copilot_token = data['token']
            self.expires_at = data['expires_at']
            remain = int(self.expires_at - time.time())
            self.log(f"[Token] Refreshed OK, expires in {remain}s")
            return self.copilot_token
        except Exception as e:
            self.log(f"[Token] Refresh FAILED: {e}")
            return self.copilot_token


# ============ Proxy Handler ============
class ProxyHandler(BaseHTTPRequestHandler):
    token_mgr: TokenManager = None
    log_fn = print

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            model = body.get('model', '?')
            stream = body.get('stream', False)
            self.log_fn(f"[Req] {model} stream={stream}")

            token = self.token_mgr.get_token()
            if not token:
                self._error(503, "No copilot token available")
                return

            headers = {**COPILOT_HEADERS,
                       'Authorization': f'Bearer {token}',
                       'Content-Type': 'application/json',
                       'x-request-id': str(uuid.uuid4())}

            path = self.path
            if path.startswith('/v1/'):
                path = path[3:]  # strip /v1 prefix
            target = f"{COPILOT_API_BASE}{path}"
            resp = requests.post(target, headers=headers, json=body,
                                 proxies=PROXY, timeout=120, stream=stream)

            if stream and 'text/event-stream' in resp.headers.get('content-type', ''):
                self.send_response(resp.status_code)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                for chunk in resp.iter_content(chunk_size=None):
                    if chunk:
                        self.wfile.write(chunk)
                        self.wfile.flush()
            else:
                self.send_response(resp.status_code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(resp.content)

            self.log_fn(f"[Resp] {resp.status_code}")
        except Exception as e:
            self.log_fn(f"[Error] {e}")
            self._error(502, str(e))

    def do_GET(self):
        try:
            token = self.token_mgr.get_token()
            headers = {**COPILOT_HEADERS, 'Authorization': f'Bearer {token}'}
            path = self.path
            if path.startswith('/v1/'):
                path = path[3:]
            target = f"{COPILOT_API_BASE}{path}"
            resp = requests.get(target, headers=headers, proxies=PROXY, timeout=15)
            self.send_response(resp.status_code)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(resp.content)
        except Exception as e:
            self._error(502, str(e))

    def _error(self, code, msg):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': msg}).encode())

    def log_message(self, fmt, *args):
        pass


# ============ TK GUI ============
class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Copilot Proxy")
        self.root.geometry("520x360")
        self.root.resizable(False, False)

        frm = tk.Frame(self.root)
        frm.pack(fill='x', padx=8, pady=4)
        self.status_var = tk.StringVar(value="Starting...")
        tk.Label(frm, textvariable=self.status_var, fg='blue', anchor='w').pack(side='left')
        tk.Label(frm, text=f":{LOCAL_PORT}", fg='gray').pack(side='right')

        self.log_area = scrolledtext.ScrolledText(
            self.root, height=18, state='disabled', font=('Consolas', 9))
        self.log_area.pack(fill='both', expand=True, padx=8, pady=4)

        self.token_mgr = TokenManager(log_fn=self.log)
        threading.Thread(target=self._run_server, daemon=True).start()

    def log(self, msg):
        ts = time.strftime('%H:%M:%S')
        def _append():
            self.log_area.config(state='normal')
            self.log_area.insert('end', f"[{ts}] {msg}\n")
            self.log_area.see('end')
            self.log_area.config(state='disabled')
        self.root.after(0, _append)

    def _run_server(self):
        ProxyHandler.token_mgr = self.token_mgr
        ProxyHandler.log_fn = self.log
        server = HTTPServer(('127.0.0.1', LOCAL_PORT), ProxyHandler)
        self.log(f"[Server] Listening on http://127.0.0.1:{LOCAL_PORT}")
        self.root.after(0, lambda: self.status_var.set(f"Running  127.0.0.1:{LOCAL_PORT}"))
        self.token_mgr.get_token()
        server.serve_forever()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    App().run()
