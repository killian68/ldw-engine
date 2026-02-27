from __future__ import annotations

import os
import sys
import subprocess
import webbrowser
from typing import Optional

# --- Force qtpy backend selection BEFORE importing webview ---
# This prevents qtpy from picking PyQt5 when it is present on the system.
os.environ.setdefault("QT_API", "pyside6")

# On Linux GNOME/Wayland, Qt WebEngine + Wayland plugin may crash depending on system libs.
# Using xcb (XWayland) is often the most stable. We only set it on Linux and only if not already set.
if sys.platform.startswith("linux"):
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

import webview

VIEWER_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>LDW Graph Viewer</title>
  <style>
    html, body { height: 100%; margin: 0; background: #101114; color: #eaeaea; font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; }
    .topbar {
      height: 44px;
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 0 10px;
      border-bottom: 1px solid rgba(255,255,255,.08);
      background: #14161a;
      user-select: none;
    }
    .topbar button {
      height: 28px;
      padding: 0 10px;
      border-radius: 8px;
      border: 1px solid rgba(255,255,255,.12);
      background: rgba(255,255,255,.06);
      color: #eaeaea;
      cursor: pointer;
    }
    .topbar button:hover { background: rgba(255,255,255,.10); }
    .topbar .spacer { flex: 1; }
    .topbar .status { opacity: .8; font-size: 12px; }

    #viewport {
      height: calc(100% - 44px);
      overflow: hidden; /* important: we manage pan ourselves */
      position: relative;
    }

    /* SVG container (we load SVG inline into this div) */
    #svgHost {
      width: 100%;
      height: 100%;
      transform-origin: 0 0;
      cursor: grab;
      will-change: transform;
    }
    #svgHost.dragging { cursor: grabbing; }

    /* Make the SVG fit nicely initially */
    #svgHost svg {
      width: 100%;
      height: 100%;
    }
  </style>
</head>
<body>
  <div class="topbar">
    <button id="btnRefresh">Refresh</button>
    <button id="btnFit">Fit</button>
    <button id="btnReset">Reset</button>
    <button id="btn100">100%</button>
    <div class="spacer"></div>
    <div class="status" id="status">(ready)</div>
  </div>

  <div id="viewport">
    <div id="svgHost"></div>
  </div>

<script>
(() => {
  const svgHost = document.getElementById('svgHost');
  const statusEl = document.getElementById('status');

  // Simple pan/zoom state (no external lib)
  let scale = 1.0;
  let tx = 0; // translate x
  let ty = 0; // translate y

  let isDragging = false;
  let lastX = 0;
  let lastY = 0;

  function setStatus(s) { statusEl.textContent = s; }

  function applyTransform() {
    svgHost.style.transform = `translate(${tx}px, ${ty}px) scale(${scale})`;
  }

  function resetView() {
    scale = 1.0;
    tx = 0;
    ty = 0;
    applyTransform();
  }

  function fitToViewport() {
    const svg = svgHost.querySelector('svg');
    const vp = document.getElementById('viewport');
    if (!svg) return;

    let w, h;

    // Prefer SVG viewBox when present (most graphviz outputs have it)
    const vb = svg.viewBox && svg.viewBox.baseVal ? svg.viewBox.baseVal : null;
    if (vb && vb.width && vb.height) {
      w = vb.width; h = vb.height;
    } else {
      // Fallback: bbox (can fail if SVG not fully rendered yet)
      try {
        const bb = svg.getBBox();
        w = bb.width; h = bb.height;
      } catch (_e) {
        // last resort: intrinsic size
        w = svg.width && svg.width.baseVal ? svg.width.baseVal.value : 1000;
        h = svg.height && svg.height.baseVal ? svg.height.baseVal.value : 800;
      }
    }

    const vpW = vp.clientWidth;
    const vpH = vp.clientHeight;
    if (w <= 0 || h <= 0 || vpW <= 0 || vpH <= 0) return;

    const margin = 20;
    const s = Math.min((vpW - margin) / w, (vpH - margin) / h);
    scale = Math.max(0.05, Math.min(10, s));

    tx = (vpW - w * scale) / 2;
    ty = (vpH - h * scale) / 2;

    applyTransform();
  }

  function zoomAt(clientX, clientY, factor) {
    const vp = document.getElementById('viewport');
    const rect = vp.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;

    const worldX = (x - tx) / scale;
    const worldY = (y - ty) / scale;

    const newScale = Math.max(0.05, Math.min(10, scale * factor));
    if (newScale === scale) return;

    scale = newScale;
    tx = x - worldX * scale;
    ty = y - worldY * scale;

    applyTransform();
  }

  async function loadSvg(cacheBust=true) {
    const url = cacheBust ? `graph.svg?v=${Date.now()}` : 'graph.svg';
    setStatus('loading…');

    try {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      svgHost.innerHTML = text;

      resetView();
      // Fit after a tick to let layout settle a bit
      requestAnimationFrame(() => {
        fitToViewport();
        setStatus('ready');
      });
    } catch (e) {
      setStatus(`load failed: ${e}`);
      svgHost.innerHTML = `<div style="padding:16px;color:#ffb4b4">Failed to load graph.svg<br/>${e}</div>`;
    }
  }

  const viewport = document.getElementById('viewport');

  // Wheel -> zoom (IMPORTANT: passive:false so preventDefault works in Chromium/QtWebEngine)
  viewport.addEventListener('wheel', (e) => {
    e.preventDefault();

    // Normalize direction: wheel down => zoom out
    const factor = (e.deltaY > 0) ? 0.9 : 1.1;
    zoomAt(e.clientX, e.clientY, factor);
  }, { passive: false });

  // Drag -> pan
  viewport.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return;
    isDragging = true;
    lastX = e.clientX;
    lastY = e.clientY;
    svgHost.classList.add('dragging');
  });

  window.addEventListener('mousemove', (e) => {
    if (!isDragging) return;
    const dx = e.clientX - lastX;
    const dy = e.clientY - lastY;
    lastX = e.clientX;
    lastY = e.clientY;
    tx += dx;
    ty += dy;
    applyTransform();
  });

  window.addEventListener('mouseup', () => {
    isDragging = false;
    svgHost.classList.remove('dragging');
  });

  // Double-click -> fit
  viewport.addEventListener('dblclick', (e) => {
    e.preventDefault();
    fitToViewport();
  });

  // Buttons
  document.getElementById('btnFit').addEventListener('click', () => fitToViewport());
  document.getElementById('btnReset').addEventListener('click', () => resetView());
  document.getElementById('btn100').addEventListener('click', () => { scale = 1; tx = 0; ty = 0; applyTransform(); });

  document.getElementById('btnRefresh').addEventListener('click', async () => {
    setStatus('refreshing…');
    try {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.refresh) {
        const r = await window.pywebview.api.refresh();
        if (r !== true) {
          setStatus(`refresh error: ${r}`);
          return;
        }
      }
      await loadSvg(true);
    } catch (e) {
      setStatus(`refresh failed: ${e}`);
    }
  });

  // Keyboard shortcuts
  window.addEventListener('keydown', (e) => {
    if (e.key === 'f' || e.key === 'F') fitToViewport();
    if (e.key === '1') { scale = 1; tx = 0; ty = 0; applyTransform(); }
    if (e.key === '0') resetView();
  });

  // Initial load
  loadSvg(false);
})();
</script>
</body>
</html>
"""


def _file_url(path: str) -> str:
    ap = os.path.abspath(path)
    if sys.platform.startswith("win"):
        return "file:///" + ap.replace("\\", "/")
    return "file://" + ap


def _write_viewer_html(html_path: str) -> None:
    # Always (re)write to avoid stale/outdated HTML between versions.
    os.makedirs(os.path.dirname(html_path), exist_ok=True)
    with open(html_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(VIEWER_HTML)


def main() -> int:
    # args: <python_exe> <author_tool.py> <xml_path> <out_dir>
    if len(sys.argv) < 5:
        print("Usage: graph_viewer.py <python_exe> <author_tool.py> <xml_path> <out_dir>")
        return 2

    py = sys.argv[1]
    tool = sys.argv[2]
    xml = sys.argv[3]
    out_dir = sys.argv[4]

    dot_path = os.path.join(out_dir, "graph.dot")
    svg_path = os.path.join(out_dir, "graph.svg")
    html_path = os.path.join(out_dir, "viewer.html")

    # Ensure refresh uses the same Qt backend selection (important on Linux after reboot)
    refresh_env = os.environ.copy()
    refresh_env.setdefault("QT_API", "pyside6")
    if sys.platform.startswith("linux"):
        refresh_env.setdefault("QT_QPA_PLATFORM", "xcb")

    class Api:
        def refresh(self):
            try:
                subprocess.run(
                    [
                        py,
                        tool,
                        "--export-graph",
                        "--xml",
                        xml,
                        "--dot",
                        dot_path,
                        "--svg",
                        svg_path,
                    ],
                    env=refresh_env,
                    check=True,
                )
                return True
            except Exception as e:
                return str(e)

    api = Api()

    # Ensure viewer.html exists (embedded HTML template)
    try:
        _write_viewer_html(html_path)
    except Exception as e:
        print("Graph viewer error: could not write viewer.html:", e)
        # If we cannot write HTML, fallback to browser if SVG exists
        if os.path.exists(svg_path):
            webbrowser.open(_file_url(svg_path))
            return 0
        return 1

    # If SVG is missing, we can still open the UI, but it will show "Failed to load graph.svg".
    # However, for safety, keep the old fallback when both are missing.
    if not os.path.exists(svg_path) and not os.path.exists(dot_path):
        print("Graph viewer warning: graph files not found yet (graph.svg/graph.dot). Viewer will still open.")

    try:
        webview.create_window(
            "LDW Graph Viewer",
            url=_file_url(html_path),
            js_api=api,
            width=1200,
            height=800,
        )
        webview.start(gui="qt", debug=False)
        return 0

    except Exception as e:
        print("WebView failed:", e)
        print("Falling back to system browser...")

        if os.path.exists(svg_path):
            webbrowser.open(_file_url(svg_path))
            return 0

        return 1


if __name__ == "__main__":
    raise SystemExit(main())