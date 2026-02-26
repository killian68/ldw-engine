from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageTk

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


class ImagePanel(ttk.Frame):
    def __init__(self, master: tk.Widget):
        super().__init__(master)
        self._path: str | None = None

        # Keep references to avoid Tk image GC issues
        self._photo = None
        self._pil_image = None

        self.label = ttk.Label(self, text="(No image)")
        self.label.pack(fill="both", expand=True)

        self.label.bind("<Button-1>", self._on_click)

    def clear(self) -> None:
        """Clear image safely (prevents 'pyimageX doesn't exist' issues)."""
        self._path = None
        self._photo = None
        self._pil_image = None

        # Important: remove image FIRST
        self.label.configure(image="")
        # Also remove any lingering attribute reference
        try:
            self.label.image = None
        except Exception:
            pass

        self.label.configure(text="(No image)")

    def set_image(self, path: str | None, max_size: tuple[int, int] = (520, 320)) -> None:
        # Always start by clearing safely
        self.clear()

        if not path or not os.path.exists(path):
            return

        self._path = path

        if not PIL_AVAILABLE:
            self.label.configure(image="")
            try:
                self.label.image = None
            except Exception:
                pass
            self.label.configure(text=f"(Image: {os.path.basename(path)} — install Pillow for preview)")
            return

        # Load + thumbnail
        img = Image.open(path)
        img.thumbnail(max_size)

        self._pil_image = img
        self._photo = ImageTk.PhotoImage(img)

        # Set image, clear text
        self.label.configure(text="")
        self.label.configure(image=self._photo)

        # Extra safety: keep a reference on the widget
        self.label.image = self._photo

    def _on_click(self, _evt) -> None:
        if not self._path:
            return
        if not PIL_AVAILABLE:
            return
        if not os.path.exists(self._path):
            return

        top = tk.Toplevel(self)
        top.title("Image Viewer")
        top.geometry("900x700")

        container = ttk.Frame(top)
        container.pack(fill="both", expand=True)

        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        canvas = tk.Canvas(container, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="nsew")

        ybar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        ybar.grid(row=0, column=1, sticky="ns")

        xbar = ttk.Scrollbar(container, orient="horizontal", command=canvas.xview)
        xbar.grid(row=1, column=0, sticky="ew")

        canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)

        # --- State (per viewer window) ---
        pil_orig = Image.open(self._path)
        pil_mode = pil_orig.mode
        if pil_mode not in ("RGB", "RGBA"):
            # avoid odd modes when resizing
            pil_orig = pil_orig.convert("RGBA")

        state = {
            "orig": pil_orig,
            "scale": 1.0,
            "min_scale": 0.05,
            "max_scale": 12.0,
            "img_id": None,
            "photo": None,
        }

        def _render_at_scale(scale: float, keep_point: tuple[float, float] | None = None, screen_xy: tuple[int, int] | None = None):
            """
            Render the image at given scale and keep the (canvas) point under the cursor stable.
            keep_point: (canvas_x, canvas_y) before redraw
            screen_xy: (event.x, event.y) within canvas widget
            """
            scale = max(state["min_scale"], min(state["max_scale"], float(scale)))
            state["scale"] = scale

            ow, oh = state["orig"].size
            nw = max(1, int(ow * scale))
            nh = max(1, int(oh * scale))

            # Resize with Pillow
            resized = state["orig"].resize((nw, nh), Image.LANCZOS)
            photo = ImageTk.PhotoImage(resized)
            state["photo"] = photo  # keep ref

            if state["img_id"] is None:
                state["img_id"] = canvas.create_image(0, 0, anchor="nw", image=photo)
            else:
                canvas.itemconfigure(state["img_id"], image=photo)

            # Update scroll region
            canvas.configure(scrollregion=(0, 0, nw, nh))

            # Keep cursor point stable
            if keep_point is not None and screen_xy is not None:
                # After redraw, compute new canvas coords under the same screen point,
                # then shift view by the delta
                new_cx = canvas.canvasx(screen_xy[0])
                new_cy = canvas.canvasy(screen_xy[1])

                dx = new_cx - keep_point[0]
                dy = new_cy - keep_point[1]

                # Shift view: use xview/yview "moveto" based on scrollregion size
                sr = canvas.bbox("all")
                if sr:
                    x0, y0, x1, y1 = sr
                    w = max(1, x1 - x0)
                    h = max(1, y1 - y0)

                    # Current fractions:
                    fx0, fx1 = canvas.xview()
                    fy0, fy1 = canvas.yview()

                    # Convert pixel shift to fraction shift:
                    canvas.xview_moveto(max(0.0, min(1.0, fx0 + dx / w)))
                    canvas.yview_moveto(max(0.0, min(1.0, fy0 + dy / h)))

        def _fit_to_window():
            # Fit image to canvas area (leave a tiny margin)
            canvas.update_idletasks()
            cw = max(1, canvas.winfo_width())
            ch = max(1, canvas.winfo_height())
            ow, oh = state["orig"].size
            scale = min(cw / ow, ch / oh) * 0.98
            _render_at_scale(scale)
            canvas.xview_moveto(0.0)
            canvas.yview_moveto(0.0)

        def _reset_view(_event=None):
            _render_at_scale(1.0)
            canvas.xview_moveto(0.0)
            canvas.yview_moveto(0.0)

        # Initial render: fit
        _fit_to_window()

        # --- Bindings: zoom / pan / reset ---
        def _zoom_wheel(event):
            # Determine wheel direction and step
            if sys.platform.startswith("linux"):
                # Button-4 up, Button-5 down
                direction = 1 if event.num == 4 else -1
            else:
                direction = 1 if event.delta > 0 else -1

            # Zoom factor: smooth-ish
            factor = 1.1 if direction > 0 else 0.9

            # Keep point under mouse
            keep_cx = canvas.canvasx(event.x)
            keep_cy = canvas.canvasy(event.y)

            _render_at_scale(state["scale"] * factor, keep_point=(keep_cx, keep_cy), screen_xy=(event.x, event.y))

        # Pan: click + drag (scan)
        def _pan_start(event):
            canvas.scan_mark(event.x, event.y)

        def _pan_move(event):
            canvas.scan_dragto(event.x, event.y, gain=1)

        # Double click: reset to fit (more useful than 1:1 in most cases)
        def _dbl_click(_event):
            _fit_to_window()

        # Bind mousewheel for zoom (only when mouse is over canvas)
        def _bind_wheel(_event):
            if sys.platform.startswith("linux"):
                canvas.bind_all("<Button-4>", _zoom_wheel)
                canvas.bind_all("<Button-5>", _zoom_wheel)
            else:
                canvas.bind_all("<MouseWheel>", _zoom_wheel)

        def _unbind_wheel(_event):
            if sys.platform.startswith("linux"):
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            else:
                canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_wheel)
        canvas.bind("<Leave>", _unbind_wheel)

        canvas.bind("<ButtonPress-1>", _pan_start)
        canvas.bind("<B1-Motion>", _pan_move)
        canvas.bind("<Double-Button-1>", _dbl_click)

        # Nice-to-have: F key to fit, 1 key to 100%
        top.bind("<KeyPress-f>", lambda _e: _fit_to_window())
        top.bind("<KeyPress-1>", _reset_view)

        # If the window is resized, keep the image visible (do not constantly refit; just update scrollregion)
        # Optional: refit once on first configure after open
        _did_first_configure = {"done": False}

        def _on_configure(_e):
            if not _did_first_configure["done"]:
                _did_first_configure["done"] = True
                _fit_to_window()

        top.bind("<Configure>", _on_configure)
