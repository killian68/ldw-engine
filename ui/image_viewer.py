from __future__ import annotations

import os
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

        img = Image.open(self._path)
        photo = ImageTk.PhotoImage(img)
        canvas.image = photo  # keep reference
        canvas.create_image(0, 0, anchor="nw", image=photo)
        canvas.configure(scrollregion=(0, 0, img.width, img.height))

        # Mouse wheel vertical scroll (cross-platform)
        import sys

        def _on_mousewheel(event):
            if sys.platform.startswith("win"):
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif sys.platform == "darwin":
                canvas.yview_scroll(int(-1 * event.delta), "units")
            else:
                if event.num == 4:
                    canvas.yview_scroll(-1, "units")
                elif event.num == 5:
                    canvas.yview_scroll(1, "units")

        def _bind_mousewheel(_event):
            if sys.platform.startswith("linux"):
                canvas.bind_all("<Button-4>", _on_mousewheel)
                canvas.bind_all("<Button-5>", _on_mousewheel)
            else:
                canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(_event):
            if sys.platform.startswith("linux"):
                canvas.unbind_all("<Button-4>")
                canvas.unbind_all("<Button-5>")
            else:
                canvas.unbind_all("<MouseWheel>")

        canvas.bind("<Enter>", _bind_mousewheel)
        canvas.bind("<Leave>", _unbind_mousewheel)