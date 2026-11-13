# -*- coding: utf-8 -*-
"""Zero-dependency localhost HTTP + SSE server for live Markdown browser preview.

Uses Python 3.8's standard library ThreadingHTTPServer and Server-Sent Events
(EventSource) to push live edits from Sublime Text 4 to the user's browser
with no full-page reloads and no external dependencies.
"""

import html
import json
import mimetypes
import os
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Dict, List, Optional, Set
from urllib.parse import parse_qs, urlparse


_SHELL_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Rapscallion Markdown Preview</title>
<style>
:root {
    --bg: #ffffff;
    --fg: #1f2328;
    --muted: #656d76;
    --border: #d0d7de;
    --code-bg: #f6f8fa;
    --accent: #0969da;
    --quote-bg: #f6f8fa;
    --note: #0969da;
    --tip: #1a7f37;
    --important: #8250df;
    --warning: #9a6700;
    --caution: #cf222e;
}
@media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
        --bg: #0d1117;
        --fg: #e6edf3;
        --muted: #8b949e;
        --border: #30363d;
        --code-bg: #161b22;
        --accent: #58a6ff;
        --quote-bg: #161b22;
        --note: #58a6ff;
        --tip: #3fb950;
        --important: #a371f7;
        --warning: #d29922;
        --caution: #f85149;
    }
}
:root[data-theme="dark"] {
    --bg: #0d1117;
    --fg: #e6edf3;
    --muted: #8b949e;
    --border: #30363d;
    --code-bg: #161b22;
    --accent: #58a6ff;
    --quote-bg: #161b22;
    --note: #58a6ff;
    --tip: #3fb950;
    --important: #a371f7;
    --warning: #d29922;
    --caution: #f85149;
}
* { box-sizing: border-box; }
body {
    margin: 0;
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    line-height: 1.65;
}
.topbar {
    position: sticky;
    top: 0;
    z-index: 20;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 20px;
    background: var(--bg);
    border-bottom: 1px solid var(--border);
    font-size: 13px;
}
.topbar-left {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
}
.status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #3fb950;
    flex-shrink: 0;
}
.status-dot.disconnected { background: #f85149; }
.doc-title {
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.topbar-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
}
.btn {
    background: var(--code-bg);
    color: var(--fg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 12px;
    cursor: pointer;
}
.btn:hover { border-color: var(--accent); }
.btn.active { border-color: var(--accent); color: var(--accent); }
main {
    max-width: 880px;
    margin: 0 auto;
    padding: 28px 24px 64px;
}
h1, h2, h3, h4, h5, h6 {
    margin-top: 1.5em;
    margin-bottom: 0.5em;
    font-weight: 600;
    line-height: 1.25;
}
h1, h2 {
    padding-bottom: 0.3em;
    border-bottom: 1px solid var(--border);
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
code {
    font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", Menlo, monospace;
    font-size: 0.88em;
    background: var(--code-bg);
    padding: 0.15em 0.38em;
    border-radius: 4px;
}
.code-block {
    background: var(--code-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    margin: 14px 0;
    overflow: hidden;
}
.code-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 6px 12px;
    border-bottom: 1px solid var(--border);
    font-size: 12px;
    color: var(--muted);
}
.copy-btn {
    background: transparent;
    color: var(--muted);
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 11px;
    cursor: pointer;
}
.copy-btn:hover { color: var(--fg); border-color: var(--accent); }
.code-block pre {
    margin: 0;
    padding: 12px 14px;
    overflow-x: auto;
    font-size: 13.5px;
    line-height: 1.5;
}
.code-block pre code {
    background: transparent;
    padding: 0;
}
blockquote {
    margin: 14px 0;
    padding: 6px 16px;
    border-left: 4px solid var(--accent);
    background: var(--quote-bg);
    color: var(--muted);
    border-radius: 0 6px 6px 0;
}
.callout {
    margin: 14px 0;
    padding: 10px 14px;
    border-left: 4px solid var(--note);
    background: var(--quote-bg);
    border-radius: 0 6px 6px 0;
}
.callout-tip { border-left-color: var(--tip); }
.callout-important { border-left-color: var(--important); }
.callout-warning { border-left-color: var(--warning); }
.callout-caution { border-left-color: var(--caution); }
.callout-title {
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.04em;
    margin-bottom: 4px;
}
table {
    border-collapse: collapse;
    width: 100%;
    margin: 14px 0;
    display: block;
    overflow-x: auto;
}
th, td {
    border: 1px solid var(--border);
    padding: 8px 12px;
}
th {
    background: var(--code-bg);
    font-weight: 600;
}
ul, ol { padding-left: 24px; }
li.task-item {
    list-style: none;
    margin-left: -20px;
}
li.task-done > span {
    text-decoration: line-through;
    color: var(--muted);
}
img {
    max-width: 100%;
    height: auto;
    border-radius: 6px;
}
hr {
    border: none;
    border-top: 1px solid var(--border);
    margin: 24px 0;
}
.active-line-highlight {
    background: color-mix(in srgb, var(--accent) 10%, transparent);
    border-left: 3px solid var(--accent);
    padding-left: 10px;
    border-radius: 4px;
}
</style>
</head>
<body>
<div class="topbar">
    <div class="topbar-left">
        <span id="status-dot" class="status-dot" title="Connected to Sublime Text"></span>
        <span id="doc-title" class="doc-title">__INITIAL_TITLE__</span>
    </div>
    <div class="topbar-actions">
        <button id="sync-btn" class="btn active" type="button">Sync Scroll: On</button>
        <button id="theme-btn" class="btn" type="button">Theme: Auto</button>
    </div>
</div>
<main id="md-content">__INITIAL_HTML__</main>
<script>
(function() {
    var contentEl = document.getElementById("md-content");
    var titleEl = document.getElementById("doc-title");
    var dotEl = document.getElementById("status-dot");
    var syncBtn = document.getElementById("sync-btn");
    var themeBtn = document.getElementById("theme-btn");
    var syncScroll = true;
    var lastCursorLine = null;
    var themes = ["auto", "light", "dark"];
    var themeIdx = 0;

    syncBtn.addEventListener("click", function() {
        syncScroll = !syncScroll;
        syncBtn.textContent = "Sync Scroll: " + (syncScroll ? "On" : "Off");
        syncBtn.classList.toggle("active", syncScroll);
    });

    themeBtn.addEventListener("click", function() {
        themeIdx = (themeIdx + 1) % themes.length;
        var mode = themes[themeIdx];
        if (mode === "auto") {
            document.documentElement.removeAttribute("data-theme");
        } else {
            document.documentElement.setAttribute("data-theme", mode);
        }
        themeBtn.textContent = "Theme: " + mode.charAt(0).toUpperCase() + mode.slice(1);
    });

    function bindInteractions() {
        var copyBtns = contentEl.querySelectorAll(".copy-btn");
        copyBtns.forEach(function(btn) {
            btn.addEventListener("click", function() {
                var code = btn.closest(".code-block").querySelector("code");
                if (!code) return;
                navigator.clipboard.writeText(code.innerText).then(function() {
                    btn.textContent = "Copied!";
                    setTimeout(function() { btn.textContent = "Copy"; }, 1200);
                });
            });
        });

        var checkboxes = contentEl.querySelectorAll(".task-checkbox");
        checkboxes.forEach(function(cb) {
            cb.addEventListener("change", function() {
                var line = parseInt(cb.getAttribute("data-line"), 10);
                if (!line) return;
                fetch("/action/toggle_task", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ line: line })
                });
            });
        });
    }

    function highlightAndScrollToLine(cursorLine, shouldScroll) {
        if (!cursorLine) return;
        var nodes = contentEl.querySelectorAll("[data-line]");
        var best = null;
        var bestLine = -1;
        nodes.forEach(function(node) {
            node.classList.remove("active-line-highlight");
            var ln = parseInt(node.getAttribute("data-line"), 10);
            if (ln <= cursorLine && ln >= bestLine) {
                bestLine = ln;
                best = node;
            }
        });
        if (best) {
            best.classList.add("active-line-highlight");
            if (shouldScroll && syncScroll) {
                best.scrollIntoView({ behavior: "smooth", block: "center" });
            }
        }
    }

    bindInteractions();

    var es = new EventSource("/events");
    es.onopen = function() {
        dotEl.classList.remove("disconnected");
        dotEl.title = "Connected to Sublime Text";
    };
    es.onerror = function() {
        dotEl.classList.add("disconnected");
        dotEl.title = "Disconnected from Sublime Text";
    };
    es.onmessage = function(ev) {
        try {
            var payload = JSON.parse(ev.data);
            if (payload.initial) {
                lastCursorLine = payload.cursor_line || 0;
                highlightAndScrollToLine(lastCursorLine, false);
                return;
            }
            if (typeof payload.html === "string") {
                contentEl.innerHTML = payload.html;
                bindInteractions();
            }
            if (payload.title) {
                titleEl.textContent = payload.title;
                document.title = payload.title + " — Rapscallion Markdown";
            }
            if (payload.cursor_line) {
                var moved = payload.cursor_line !== lastCursorLine;
                lastCursorLine = payload.cursor_line;
                highlightAndScrollToLine(payload.cursor_line, moved);
            }
        } catch (e) {}
    };
})();
</script>
</body>
</html>
"""


class MarkdownPreviewServer:
    """Singleton localhost HTTP + SSE server for live Markdown preview."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._clients: Set[queue.Queue] = set()
        self._state: Dict[str, object] = {
            "html": "<p><em>Waiting for Markdown content...</em></p>",
            "title": "Markdown Preview",
            "source_path": "",
            "cursor_line": 0,
            "allowed_roots": [],
        }
        self._on_toggle_task: Optional[Callable[[int, str], None]] = None

    def set_toggle_task_callback(self, cb: Callable[[int, str], None]) -> None:
        self._on_toggle_task = cb

    def is_running(self) -> bool:
        with self._lock:
            return self._running and self._server is not None

    def get_url(self) -> Optional[str]:
        with self._lock:
            if not self._running or not self._server:
                return None
            host, port = self._server.server_address
            return f"http://{host}:{port}/"

    def start(self) -> str:
        with self._lock:
            if self._running and self._server:
                host, port = self._server.server_address
                return f"http://{host}:{port}/"

            manager = self

            class _Handler(BaseHTTPRequestHandler):
                def log_message(self, format, *args):
                    # Silence default stderr HTTP request logging
                    return

                def do_GET(self):
                    parsed = urlparse(self.path)
                    if parsed.path == "/":
                        manager._handle_index(self)
                    elif parsed.path == "/events":
                        manager._handle_sse(self)
                    elif parsed.path == "/asset":
                        manager._handle_asset(self, parsed.query)
                    else:
                        self.send_error(404, "Not Found")

                def do_POST(self):
                    parsed = urlparse(self.path)
                    if parsed.path == "/action/toggle_task":
                        manager._handle_toggle_task(self)
                    else:
                        self.send_error(404, "Not Found")

            self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
            self._server.daemon_threads = True
            self._running = True
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            host, port = self._server.server_address
            return f"http://{host}:{port}/"

    def stop(self) -> None:
        with self._lock:
            self._running = False
            srv = self._server
            self._server = None
            clients = list(self._clients)
            self._clients.clear()

        for q in clients:
            try:
                q.put_nowait(None)
            except Exception:
                pass

        if srv is not None:
            try:
                srv.shutdown()
                srv.server_close()
            except Exception:
                pass

    def publish(
        self,
        html_fragment: str,
        title: str,
        source_path: str = "",
        cursor_line: int = 0,
        allowed_roots: Optional[List[str]] = None,
    ) -> None:
        payload = {
            "html": html_fragment,
            "title": title,
            "cursor_line": cursor_line,
        }
        encoded = json.dumps(payload)
        with self._lock:
            self._state["html"] = html_fragment
            self._state["title"] = title
            self._state["source_path"] = source_path
            self._state["cursor_line"] = cursor_line
            self._state["allowed_roots"] = allowed_roots or []
            clients = list(self._clients)

        for q in clients:
            try:
                q.put_nowait(encoded)
            except Exception:
                pass

    def _handle_index(self, handler: BaseHTTPRequestHandler) -> None:
        with self._lock:
            initial_html = str(self._state.get("html", ""))
            initial_title = html.escape(str(self._state.get("title", "Markdown Preview")))

        page = (
            _SHELL_HTML
            .replace("__INITIAL_TITLE__", initial_title)
            .replace("__INITIAL_HTML__", initial_html)
        )
        body = page.encode("utf-8")
        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        handler.wfile.write(body)

    def _handle_sse(self, handler: BaseHTTPRequestHandler) -> None:
        handler.send_response(200)
        handler.send_header("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header("Cache-Control", "no-cache")
        handler.send_header("Connection", "keep-alive")
        handler.end_headers()

        q: queue.Queue = queue.Queue()
        with self._lock:
            self._clients.add(q)
            initial_payload = json.dumps({
                "initial": True,
                "html": self._state.get("html", ""),
                "title": self._state.get("title", "Markdown Preview"),
                "cursor_line": self._state.get("cursor_line", 0),
            })

        try:
            handler.wfile.write(f"data: {initial_payload}\n\n".encode("utf-8"))
            handler.wfile.flush()

            while True:
                with self._lock:
                    if not self._running:
                        break
                try:
                    msg = q.get(timeout=15.0)
                    if msg is None:
                        break
                    handler.wfile.write(f"data: {msg}\n\n".encode("utf-8"))
                    handler.wfile.flush()
                except queue.Empty:
                    handler.wfile.write(b": keepalive\n\n")
                    handler.wfile.flush()
        except Exception:
            pass
        finally:
            with self._lock:
                self._clients.discard(q)

    def _handle_toggle_task(self, handler: BaseHTTPRequestHandler) -> None:
        try:
            length = int(handler.headers.get("Content-Length", "0"))
            raw = handler.rfile.read(length) if length > 0 else b"{}"
            data = json.loads(raw.decode("utf-8"))
            line = int(data.get("line", 0))
            with self._lock:
                source_path = str(self._state.get("source_path", ""))
            if line > 0 and self._on_toggle_task:
                self._on_toggle_task(line, source_path)
            resp = b'{"ok":true}'
            handler.send_response(200)
            handler.send_header("Content-Type", "application/json")
            handler.send_header("Content-Length", str(len(resp)))
            handler.end_headers()
            handler.wfile.write(resp)
        except Exception:
            handler.send_error(400, "Bad Request")

    def _handle_asset(self, handler: BaseHTTPRequestHandler, query: str) -> None:
        params = parse_qs(query)
        rel_path = (params.get("path") or [""])[0]
        if not rel_path:
            handler.send_error(404, "Not Found")
            return

        with self._lock:
            source_path = str(self._state.get("source_path", ""))
            roots = list(self._state.get("allowed_roots", []))

        candidate_bases: List[str] = []
        if source_path:
            candidate_bases.append(os.path.dirname(os.path.abspath(source_path)))
        for r in roots:
            if r:
                candidate_bases.append(os.path.abspath(r))

        resolved: Optional[str] = None
        for base in candidate_bases:
            base_real = os.path.realpath(base)
            target_real = os.path.realpath(os.path.join(base_real, rel_path))
            # Prevent path traversal outside allowed base directories
            if (target_real == base_real or target_real.startswith(base_real + os.sep)) and os.path.isfile(target_real):
                resolved = target_real
                break

        if not resolved:
            handler.send_error(404, "Asset Not Found")
            return

        ctype, _ = mimetypes.guess_type(resolved)
        ctype = ctype or "application/octet-stream"
        try:
            with open(resolved, "rb") as f:
                data = f.read()
            handler.send_response(200)
            handler.send_header("Content-Type", ctype)
            handler.send_header("Content-Length", str(len(data)))
            handler.end_headers()
            handler.wfile.write(data)
        except Exception:
            handler.send_error(500, "Read Error")
