# ui/icon.py

from __future__ import annotations
import os
import sys
import tkinter as tk


_ICON_PHOTO: tk.PhotoImage | None = None


def _repo_root() -> str:
    """
    Resolve project root both in dev mode and PyInstaller bundle.
    """
    if getattr(sys, "frozen", False):
        # PyInstaller
        return sys._MEIPASS  # type: ignore
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _icon_path() -> str:
    """
    <racine>/ui/assets/Icons/lveh_256.png
    """
    root = _repo_root()
    return os.path.join(root, "ui", "assets", "Icons", "lveh_256.png")


def get_icon_path() -> str:
    """
    Public helper: absolute path to the PNG icon used by the app.
    Useful for non-Tk windows (e.g. pywebview).
    """
    return _icon_path()


def _load_icon(root: tk.Misc) -> tk.PhotoImage | None:
    global _ICON_PHOTO

    path = _icon_path()

    if not os.path.exists(path):
        print(f"[icon] Icon not found: {path}")
        return None

    if _ICON_PHOTO is None:
        _ICON_PHOTO = tk.PhotoImage(master=root, file=path)

    return _ICON_PHOTO


def set_app_icon(window: tk.Misc) -> None:
    """
    Apply icon to a single window.
    """
    photo = _load_icon(window)
    if photo:
        try:
            window.iconphoto(True, photo)
        except Exception:
            pass


def patch_toplevel_icon(root: tk.Tk) -> None:
    """
    Automatically apply icon to:
      - root window
      - all future Toplevel windows
    """

    # Set icon on root
    set_app_icon(root)

    original_toplevel = tk.Toplevel

    class IconToplevel(original_toplevel):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            set_app_icon(self)

    tk.Toplevel = IconToplevel  # type: ignore
