# ui/graph_viewer.py
from __future__ import annotations

import argparse
import os
import platform
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socket import socket
from typing import Optional


def _repo_root() -> str:
    """
    Resolve project root both in dev mode and PyInstaller bundle.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller
        return sys._MEIPASS  # type: ignore
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ui_viewer_html_path() -> str:
    """
    <root>/ui/viewer.html
    """
    return os.path.join(_repo_root(), "ui", "viewer.html")


def _free_port() -> int:
    s = socket()
    s.bind(("127.0.0.1", 0))
    port = int(s.getsockname()[1])
    s.close()
    return port


class _ViewerServer(HTTPServer):
    def __init__(self, server_address, RequestHandlerClass, *, out_dir: str, viewer_html: str, py_exe: str, tool_py: str, xml_path: str):
        super().__init__(server_address, RequestHandlerClass)
        self.out_dir = out_dir
        self.viewer_html = viewer_html
        self.py_exe = py_exe
        self.tool_py = tool_py
        self.xml_path = xml_path


class _Handler(BaseHTTPRequestHandler):
    def _send_bytes(self, data: bytes, content_type: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, text: str, content_type: str, code: int = 200) -> None:
        self._send_bytes(text.encode("utf-8"), content_type, code)

    def do_GET(self):  # noqa: N802
        srv: _ViewerServer = self.server  # type: ignore

        if self.path in ("/", "/index.html"):
            try:
                html = Path(srv.viewer_html).read_text(encoding="utf-8")
                self._send_text(html, "text/html; charset=utf-8")
            except Exception as e:
                self._send_text(f"viewer.html read error: {e}", "text/plain; charset=utf-8", 500)
            return

        if self.path.startswith("/graph.svg"):
            svg_path = Path(srv.out_dir) / "graph.svg"
            if not svg_path.exists():
                self._send_text("graph.svg not found (export first)", "text/plain; charset=utf-8", 404)
                return
            self._send_bytes(svg_path.read_bytes(), "image/svg+xml")
            return

        # optional: serve local JS/CSS assets later (offline mode); for now, 404
        self._send_text("Not found", "text/plain; charset=utf-8", 404)

    def do_POST(self):  # noqa: N802
        srv: _ViewerServer = self.server  # type: ignore

        if self.path == "/api/refresh":
            try:
                dot_out = str(Path(srv.out_dir) / "graph.dot")
                svg_out = str(Path(srv.out_dir) / "graph.svg")
                subprocess.run(
                    [srv.py_exe, srv.tool_py, "--export-graph", "--xml", srv.xml_path, "--dot", dot_out, "--svg", svg_out],
                    check=True,
                    cwd=_repo_root(),
                )
                self._send_text("OK", "text/plain; charset=utf-8", 200)
            except Exception as e:
                self._send_text(f"ERROR: {e}", "text/plain; charset=utf-8", 500)
            return

        self._send_text("Not found", "text/plain; charset=utf-8", 404)

    def log_message(self, fmt, *args):  # quiet
        return


def _start_server(py_exe: str, tool_py: str, xml_path: str, out_dir: str):
    viewer_html = _ui_viewer_html_path()
    if not os.path.exists(viewer_html):
        raise FileNotFoundError(f"viewer.html not found at {viewer_html}")

    port = _free_port()
    srv = _ViewerServer(
        ("127.0.0.1", port),
        _Handler,
        out_dir=out_dir,
        viewer_html=viewer_html,
        py_exe=py_exe,
        tool_py=tool_py,
        xml_path=xml_path,
    )
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, port


def _try_pywebview_open(url: str) -> bool:
    """
    On some Linux GTK/WebKit combos, pywebview can be broken (your stacktrace).
    We'll:
      - default to system browser on Linux
      - allow forcing pywebview with env FORCE_PYWEBVIEW=1
    """
    if platform.system().lower() == "linux" and os.environ.get("FORCE_PYWEBVIEW", "").strip() != "1":
        return False

    try:
        import webview  # type: ignore
    except Exception:
        return False

    # JS API is optional here; refresh works via /api/refresh anyway.
    try:
        webview.create_window("LDW Graph Viewer", url=url, width=1200, height=850)
        webview.start()
        return True
    except Exception:
        return False


def main(argv: Optional[list[str]] = None) -> int:
    """
    Called by author_tool.py as:
      python ui/graph_viewer.py <py_exe> <tool_py> <book.xml> <out_dir>
    """
    p = argparse.ArgumentParser()
    p.add_argument("py_exe", help="Python executable")
    p.add_argument("tool_py", help="Path to author_tool.py")
    p.add_argument("xml_path", help="Book XML path")
    p.add_argument("out_dir", help="Output dir containing graph.dot/graph.svg")
    args = p.parse_args(argv)

    srv = None
    try:
        srv, port = _start_server(args.py_exe, args.tool_py, args.xml_path, args.out_dir)
        url = f"http://127.0.0.1:{port}/"

        # Try pywebview (Windows/macOS), otherwise system browser (Linux default).
        if not _try_pywebview_open(url):
            webbrowser.open(url)

        # Keep process alive
        while True:
            threading.Event().wait(3600)

    except KeyboardInterrupt:
        pass
    finally:
        if srv is not None:
            try:
                srv.shutdown()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
