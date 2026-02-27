from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from ui.icon import patch_toplevel_icon

import xml.etree.ElementTree as ET

from engine.book_loader import load_book, resolve_image_path
from engine.validate import validate_book, build_link_index, asset_usage, export_dot, Issue

try:
    from PIL import Image, ImageTk

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


def _find_repo_root(start_dir: str) -> str:
    """
    Try to locate the project root (where main.py and/or engine/ lives),
    starting from the directory containing this file and walking upwards.
    """
    cur = os.path.abspath(start_dir)
    for _ in range(8):
        if os.path.isfile(os.path.join(cur, "main.py")) or os.path.isdir(os.path.join(cur, "engine")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return os.path.abspath(start_dir)


HERE = os.path.abspath(os.path.dirname(__file__))
REPO_ROOT = _find_repo_root(HERE)
BOOKS_DIR = os.path.join(REPO_ROOT, "livres")


def _pid_sort_key(pid: str):
    """
    Sort paragraphs "humanly": numeric ids first by integer order, then others.
    Examples: 1,2,3,4,5,10,11,12,... then "A1", "intro"...
    """
    s = (pid or "").strip()
    if s.isdigit():
        return (0, int(s), s)
    m = re.match(r"^(\d+)(.*)$", s)
    if m:
        return (1, int(m.group(1)), m.group(2))
    return (2, 0, s.lower())


class AuthorTool(tk.Tk):
    def __init__(self):
        super().__init__()
        patch_toplevel_icon(self)
        self.title("LDW Author Tool — (no book loaded)")
        self.geometry("1300x820")

        # Ensure default library folder exists (nice UX)
        try:
            os.makedirs(BOOKS_DIR, exist_ok=True)
        except Exception:
            pass

        self.book = None
        self.book_dir = ""

        # Keep XML tree so we can edit & save
        self._xml_tree: ET.ElementTree | None = None
        self._xml_root: ET.Element | None = None
        self._current_book_path: str | None = None

        # Editor state (Edit tab)
        self._editing_pid: str | None = None

        # Drafts / dirty tracking (per paragraph) — allows switching paragraphs without losing unsaved edits
        self._drafts = {}  # pid -> state dict
        self._dirty_pids = set()  # pids with unsaved changes
        self._suspend_dirty = False  # block dirty marking while loading UI

        # Graph export scratch (temp is fine for this viewer)
        self._graph_out_dir = os.path.join(tempfile.gettempdir(), "ldw_author_tool_graph")
        os.makedirs(self._graph_out_dir, exist_ok=True)
        self._graph_svg_path = os.path.join(self._graph_out_dir, "graph.svg")
        self._graph_dot_path = os.path.join(self._graph_out_dir, "graph.dot")
        self._graph_html_path = os.path.join(self._graph_out_dir, "viewer.html")

        self._build_menu()
        self._build_ui()

        # Confirm on close if there are unsaved changes
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # IMPORTANT: do NOT auto-load any sample book at startup.
        self._refresh_all()  # shows empty tabs nicely

    # -----------------------
    # Menu / UI
    # -----------------------

    def _build_menu(self):
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        filem = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="File", menu=filem)

        filem.add_command(label="Open book XML...", command=self.open_book_dialog)
        filem.add_separator()
        filem.add_command(label="Reload", command=self.reload_current)
        filem.add_separator()
        filem.add_command(label="Exit", command=self._on_close)

    def _build_ui(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)

        self.tab_edit = ttk.Frame(self.nb)
        self.tab_links = ttk.Frame(self.nb)
        self.tab_assets = ttk.Frame(self.nb)
        self.tab_search = ttk.Frame(self.nb)
        self.tab_validation = ttk.Frame(self.nb)

        self.nb.add(self.tab_edit, text="Edit")
        self.nb.add(self.tab_links, text="Links")
        self.nb.add(self.tab_assets, text="Assets")
        self.nb.add(self.tab_search, text="Search")
        self.nb.add(self.tab_validation, text="Validation")

        self._build_edit_tab()
        self._build_links_tab()
        self._build_assets_tab()
        self._build_search_tab()
        self._build_validation_tab()

    def _confirm_discard_if_dirty(self, action: str) -> bool:
        """Return True if it's OK to proceed with an action that would discard unsaved edits."""
        if not getattr(self, "_dirty_pids", None):
            return True
        if not self._dirty_pids:
            return True
        return messagebox.askyesno(
            "Unsaved changes",
            f"There are unsaved changes in {len(self._dirty_pids)} paragraph(s).\n\n"
            f"Proceed with '{action}' and discard them?",
        )

    def _on_close(self):
        if self._confirm_discard_if_dirty("Exit"):
            self.destroy()

    # -----------------------
    # Book load
    # -----------------------

    def open_book_dialog(self):
        if not self._confirm_discard_if_dirty("Open book"):
            return
        self._drafts.clear()
        self._dirty_pids.clear()
        initial_dir = BOOKS_DIR if os.path.isdir(BOOKS_DIR) else REPO_ROOT

        path = filedialog.askopenfilename(
            title="Open book XML",
            initialdir=initial_dir,
            filetypes=[("XML Files", "*.xml")],  # XML only
        )
        if path:
            self.load_book(path)

    def reload_current(self):
        if not self._confirm_discard_if_dirty("Reload"):
            return
        self._drafts.clear()
        self._dirty_pids.clear()
        if self._current_book_path:
            self.load_book(self._current_book_path)
        else:
            messagebox.showinfo("Reload", "No book currently loaded.")

    def load_book(self, xml_path: str):
        try:
            book = load_book(xml_path)
        except Exception as e:
            messagebox.showerror("Load error", str(e))
            return

        # Keep XML tree for editing
        try:
            self._xml_tree = ET.parse(xml_path)
            self._xml_root = self._xml_tree.getroot()
        except Exception as e:
            messagebox.showerror("XML parse error", str(e))
            return

        self._current_book_path = os.path.abspath(xml_path)
        self.book = book
        self.book_dir = os.path.dirname(self._current_book_path)
        self.title(f"LDW Author Tool — {book.title} (v{book.version})")

        self._editing_pid = None
        self._refresh_all()

    def _refresh_all(self):
        self._refresh_edit()
        self._refresh_links()
        self._refresh_assets()
        self._refresh_search()
        self._refresh_validation()

    # -----------------------
    # Helpers: XML save / selections
    # -----------------------

    def _save_xml_with_backup(self) -> str:
        if not self._xml_tree or not self._current_book_path:
            raise RuntimeError("XML tree not loaded")
        xml_path = self._current_book_path
        bak_path = xml_path + ".bak"
        shutil.copy2(xml_path, bak_path)
        self._xml_tree.write(xml_path, encoding="utf-8", xml_declaration=True)
        return bak_path

    def _get_selected_pid(self) -> str | None:
        sel = self.edit_list.curselection()
        if not sel:
            return None
        return self.edit_list.get(sel[0])

    def _get_selected_asset_id(self) -> str | None:
        sel = self.assets_tree.selection()
        if not sel:
            return None
        values = self.assets_tree.item(sel[0], "values")
        if not values:
            return None
        return str(values[0])

    def _find_paragraph_node(self, pid: str) -> ET.Element | None:
        if not self._xml_root:
            return None
        return self._xml_root.find(f".//paragraph[@id='{pid}']")

    def _ensure_assets_elem(self) -> ET.Element:
        if not self._xml_root:
            raise RuntimeError("XML root not loaded")

        assets_elem = self._xml_root.find("assets")
        if assets_elem is None:
            assets_elem = ET.SubElement(self._xml_root, "assets")
            # keep basePath consistent with loaded book
            if self.book and getattr(self.book, "assets", None) and self.book.assets.base_path:
                assets_elem.set("basePath", self.book.assets.base_path)
        return assets_elem

    def _ensure_paragraphs_container(self) -> ET.Element:
        """
        Prefer <paragraphs> container if present, else use root.
        """
        if not self._xml_root:
            raise RuntimeError("XML root not loaded")
        container = self._xml_root.find("paragraphs")
        return container if container is not None else self._xml_root

    # -----------------------
    # Drafts / dirty helpers
    # -----------------------

    def _set_dirty(self, pid: str | None, dirty: bool):
        if not pid:
            return
        if dirty:
            self._dirty_pids.add(pid)
        else:
            self._dirty_pids.discard(pid)
            # Once saved, we can drop the draft (we will reload from XML anyway)
            self._drafts.pop(pid, None)

        self._refresh_edit_list_colors()
        self._update_current_dirty_label()

    def _update_current_dirty_label(self):
        """Update the small dirty indicator in the editor header without changing state."""
        pid = self._editing_pid
        if pid and pid in self._dirty_pids:
            self.edit_dirty_var.set("● unsaved changes")
        else:
            self.edit_dirty_var.set("")

    def _refresh_edit_list_colors(self):
        if not hasattr(self, "edit_list"):
            return
        try:
            for i in range(self.edit_list.size()):
                pid = self.edit_list.get(i)
                if pid in self._dirty_pids:
                    self.edit_list.itemconfig(i, fg="black")
                else:
                    self.edit_list.itemconfig(i, fg="green")
        except Exception:
            # Some Tk builds might not support per-item config; ignore.
            pass

    def _gather_state_from_ui(self) -> dict:
        """Capture current editor UI into a serializable state dict."""
        text_val = self.edit_text.get("1.0", "end").strip("\n")

        choices = []
        for item in self.choices_tree.get_children():
            label, target = self.choices_tree.item(item, "values")
            choices.append(((label or "").strip(), (target or "").strip()))

        mods = []
        for item in self.mods_tree.get_children():
            vals = self.mods_tree.item(item, "values")
            if vals:
                mods.append(tuple((v or "").strip() for v in vals))

        combat = {
            "enabled": bool(self.ev_combat_enabled.get()),
            "rulesRef": (self.ev_rulesref.get() or "").strip(),
            "allowFlee": bool(self.ev_allowflee.get()),
            "enemyName": (self.ev_enemyname.get() or "").strip(),
            "enemySkill": (self.ev_enemyskill.get() or "").strip(),
            "enemyStamina": (self.ev_enemystamina.get() or "").strip(),
            "onWin": (self.ev_onwin.get() or "").strip(),
            "onLose": (self.ev_onlose.get() or "").strip(),
        }

        test = {
            "enabled": bool(self.ev_test_enabled.get()),
            "testRef": (self.ev_testref.get() or "").strip(),
            "stat": (self.ev_test_stat.get() or "").strip(),
            "dice": (self.ev_test_dice.get() or "").strip(),
            "successGoto": (self.ev_test_success.get() or "").strip(),
            "failGoto": (self.ev_test_fail.get() or "").strip(),
            "consumeOnSuccess": (self.ev_test_cons_s.get() or "").strip(),
            "consumeOnFail": (self.ev_test_cons_f.get() or "").strip(),
        }

        return {"text": text_val, "choices": choices, "mods": mods, "combat": combat, "test": test}

    def _state_from_xml_node(self, node: ET.Element) -> dict:
        txt_node = node.find("text")
        txt_val = (txt_node.text or "") if txt_node is not None and txt_node.text is not None else ""
        text_clean = txt_val.strip("\n")

        choices = []
        for ch in node.findall("choice"):
            target = (ch.get("target") or "").strip()
            label = (ch.get("label") or "").strip()
            if not label:
                label = (ch.text or "").strip() or "Continue"
            choices.append((label, target))

        combat = {"enabled": False, "rulesRef": "ff_classic", "allowFlee": False,
                  "enemyName": "", "enemySkill": "", "enemyStamina": "", "onWin": "", "onLose": ""}
        test = {"enabled": False, "testRef": "", "stat": "", "dice": "", "successGoto": "", "failGoto": "",
                "consumeOnSuccess": "0", "consumeOnFail": "0"}

        for ev in node.findall("event"):
            etype = (ev.get("type") or "").strip().lower()
            if etype == "combat" and not combat["enabled"]:
                combat["enabled"] = True
                combat["rulesRef"] = (ev.get("rulesRef") or "ff_classic").strip()
                combat["allowFlee"] = (ev.get("allowFlee") or "").strip().lower() in ("1", "true", "yes", "on")
                combat["enemyName"] = (ev.get("enemyName") or "").strip()
                combat["enemySkill"] = (ev.get("enemySkill") or "").strip()
                combat["enemyStamina"] = (ev.get("enemyStamina") or "").strip()
                combat["onWin"] = (ev.get("onWin") or "").strip()
                combat["onLose"] = (ev.get("onLose") or "").strip()
            if etype == "test" and not test["enabled"]:
                test["enabled"] = True
                test["testRef"] = (ev.get("testRef") or "").strip()
                test["stat"] = (ev.get("stat") or "").strip()
                test["dice"] = (ev.get("dice") or "").strip()
                test["successGoto"] = (ev.get("successGoto") or "").strip()
                test["failGoto"] = (ev.get("failGoto") or "").strip()
                test["consumeOnSuccess"] = (ev.get("consumeOnSuccess") or "0").strip()
                test["consumeOnFail"] = (ev.get("consumeOnFail") or "0").strip()

        mods = []
        for ee in node.findall("envEffect"):
            mods.append((
                (ee.get("target") or "").strip(),
                (ee.get("op") or "add").strip(),
                (ee.get("value") or "0").strip(),
                (ee.get("scope") or "paragraph").strip(),
                (ee.get("ref") or "").strip(),
                (ee.get("label") or "").strip(),
            ))
        env_block = node.find("environment")
        if env_block is not None:
            for eff in env_block.findall("effect"):
                mods.append((
                    (eff.get("target") or "").strip(),
                    (eff.get("op") or "add").strip(),
                    (eff.get("value") or "0").strip(),
                    (eff.get("scope") or "paragraph").strip(),
                    (eff.get("ref") or "").strip(),
                    (eff.get("label") or "").strip(),
                ))

        return {"text": text_clean, "choices": choices, "mods": mods, "combat": combat, "test": test}

    def _load_state_into_ui(self, pid: str, state: dict):
        self._suspend_dirty = True
        try:
            self._editing_pid = pid
            self.edit_pid_var.set(pid)

            self.edit_text.configure(state="normal")
            self.edit_text.delete("1.0", "end")
            self.edit_text.insert("1.0", state.get("text", ""))
            self.edit_text.edit_modified(False)

            for it in self.choices_tree.get_children():
                self.choices_tree.delete(it)
            for label, target in state.get("choices", []):
                self.choices_tree.insert("", "end", values=((label or "").strip(), (target or "").strip()))

            # events
            combat = state.get("combat", {}) or {}
            self.ev_combat_enabled.set(bool(combat.get("enabled", False)))
            self.ev_rulesref.set(combat.get("rulesRef", "ff_classic") or "ff_classic")
            self.ev_allowflee.set(bool(combat.get("allowFlee", False)))
            self.ev_enemyname.set(combat.get("enemyName", "") or "")
            self.ev_enemyskill.set(combat.get("enemySkill", "") or "")
            self.ev_enemystamina.set(combat.get("enemyStamina", "") or "")
            self.ev_onwin.set(combat.get("onWin", "") or "")
            self.ev_onlose.set(combat.get("onLose", "") or "")

            test = state.get("test", {}) or {}
            self.ev_test_enabled.set(bool(test.get("enabled", False)))
            self.ev_testref.set(test.get("testRef", "") or "")
            self.ev_test_stat.set(test.get("stat", "") or "")
            self.ev_test_dice.set(test.get("dice", "") or "")
            self.ev_test_success.set(test.get("successGoto", "") or "")
            self.ev_test_fail.set(test.get("failGoto", "") or "")
            self.ev_test_cons_s.set(test.get("consumeOnSuccess", "0") or "0")
            self.ev_test_cons_f.set(test.get("consumeOnFail", "0") or "0")

            for it in self.mods_tree.get_children():
                self.mods_tree.delete(it)
            for row in state.get("mods", []):
                self.mods_tree.insert("", "end", values=tuple(row))

            self._set_editor_enabled(True)
        finally:
            self._suspend_dirty = False

        self._update_current_dirty_label()

    def _capture_current_to_draft(self):
        if not self._editing_pid:
            return
        # Only store if user has actually modified or already dirty
        state = self._gather_state_from_ui()
        self._drafts[self._editing_pid] = state

    def _on_editor_var_change(self, *_args):
        if self._suspend_dirty:
            return
        self._set_dirty(self._editing_pid, True)

    # -----------------------
    # EDIT tab (new editor)
    # -----------------------

    def _build_edit_tab(self):
        root = self.tab_edit
        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        # Left panel
        left = ttk.Frame(root)
        left.grid(row=0, column=0, sticky="nsw", padx=(8, 6), pady=8)
        left.rowconfigure(2, weight=1)

        ttk.Label(left, text="Filter:").grid(row=0, column=0, sticky="w")
        self.edit_filter = tk.StringVar(value="")
        ent = ttk.Entry(left, textvariable=self.edit_filter, width=24)
        ent.grid(row=1, column=0, sticky="ew", pady=(4, 6))
        ent.bind("<KeyRelease>", lambda _e: self._refresh_edit_list())

        self.edit_list = tk.Listbox(left, width=28, height=28)
        self.edit_list.grid(row=2, column=0, sticky="nsw")
        self.edit_list.bind("<<ListboxSelect>>", lambda _e: self._edit_select())

        btns = ttk.Frame(left)
        btns.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)
        btns.columnconfigure(2, weight=1)
        btns.columnconfigure(3, weight=1)
        btns.columnconfigure(4, weight=1)

        ttk.Button(btns, text="Add", command=self._edit_add_paragraph).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(btns, text="Save", command=self._edit_save_current).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(btns, text="Save All", command=self._edit_save_all).grid(row=0, column=2, sticky="ew", padx=4)
        ttk.Button(btns, text="Delete", command=self._edit_delete_selected).grid(row=0, column=3, sticky="ew", padx=4)
        ttk.Button(btns, text="Graph (SVG)", command=self._open_graph_viewer).grid(row=0, column=4, sticky="ew", padx=(4, 0))

        # Right editor panel
        editor = ttk.Frame(root)
        editor.grid(row=0, column=1, sticky="nsew", padx=(6, 8), pady=8)
        editor.columnconfigure(0, weight=1)
        editor.rowconfigure(2, weight=1)

        topbar = ttk.Frame(editor)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.columnconfigure(1, weight=1)

        ttk.Label(topbar, text="Paragraph ID:").grid(row=0, column=0, sticky="w")
        self.edit_pid_var = tk.StringVar(value="(none)")
        ttk.Label(topbar, textvariable=self.edit_pid_var, font=("Segoe UI", 11, "bold")).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )

        self.edit_dirty_var = tk.StringVar(value="")
        ttk.Label(topbar, textvariable=self.edit_dirty_var, foreground="#666").grid(row=0, column=2, sticky="e", padx=(8, 0))

        # Text editor
        text_box_frame = ttk.LabelFrame(editor, text="Text")
        text_box_frame.grid(row=1, column=0, sticky="ew", pady=(10, 10))
        text_box_frame.columnconfigure(0, weight=1)
        text_box_frame.rowconfigure(0, weight=1)

        self.edit_text = tk.Text(text_box_frame, wrap="word", height=10)
        self.edit_text.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.edit_text.bind("<<Modified>>", lambda _e: self._mark_dirty())

        # Lower area: choices + events + modifiers
        lower = ttk.Frame(editor)
        lower.grid(row=2, column=0, sticky="nsew")
        lower.columnconfigure(0, weight=1)
        lower.columnconfigure(1, weight=1)
        lower.rowconfigure(1, weight=1)

        # Choices
        choices_box = ttk.LabelFrame(lower, text="Choices")
        choices_box.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 6))
        choices_box.columnconfigure(0, weight=1)
        choices_box.rowconfigure(0, weight=1)

        self.choices_tree = ttk.Treeview(choices_box, columns=("label", "target"), show="headings", height=10)
        self.choices_tree.heading("label", text="label")
        self.choices_tree.heading("target", text="target")
        self.choices_tree.column("label", width=360, anchor="w")
        self.choices_tree.column("target", width=80, anchor="w")
        self.choices_tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))

        cbtns = ttk.Frame(choices_box)
        cbtns.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(cbtns, text="Add", command=self._choices_add).pack(side="left")
        ttk.Button(cbtns, text="Edit", command=self._choices_edit).pack(side="left", padx=(6, 0))
        ttk.Button(cbtns, text="Remove", command=self._choices_remove).pack(side="left", padx=(6, 0))

        # Events
        events_box = ttk.LabelFrame(lower, text="Events")
        events_box.grid(row=0, column=1, sticky="ew")
        events_box.columnconfigure(0, weight=1)

        # Combat section
        self.ev_combat_enabled = tk.BooleanVar(value=False)
        combat_hdr = ttk.Checkbutton(events_box, text="Combat event", variable=self.ev_combat_enabled, command=self._mark_dirty)
        combat_hdr.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 2))

        combat_grid = ttk.Frame(events_box)
        combat_grid.grid(row=1, column=0, sticky="ew", padx=8)
        for i in range(4):
            combat_grid.columnconfigure(i, weight=1)

        self.ev_rulesref = tk.StringVar(value="ff_classic")
        self.ev_allowflee = tk.BooleanVar(value=False)
        self.ev_enemyname = tk.StringVar(value="")
        self.ev_enemyskill = tk.StringVar(value="")
        self.ev_enemystamina = tk.StringVar(value="")
        self.ev_onwin = tk.StringVar(value="")
        self.ev_onlose = tk.StringVar(value="")

        ttk.Label(combat_grid, text="rulesRef").grid(row=0, column=0, sticky="w")
        ttk.Entry(combat_grid, textvariable=self.ev_rulesref, width=14).grid(row=0, column=1, sticky="ew", padx=(6, 10))
        ttk.Checkbutton(combat_grid, text="allowFlee", variable=self.ev_allowflee, command=self._mark_dirty).grid(row=0, column=2, sticky="w")

        ttk.Label(combat_grid, text="enemyName").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(combat_grid, textvariable=self.ev_enemyname).grid(row=1, column=1, columnspan=3, sticky="ew", pady=(6, 0))

        ttk.Label(combat_grid, text="enemySkill").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(combat_grid, textvariable=self.ev_enemyskill, width=10).grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Label(combat_grid, text="enemyStamina").grid(row=2, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(combat_grid, textvariable=self.ev_enemystamina, width=10).grid(row=2, column=3, sticky="w", pady=(6, 0))

        ttk.Label(combat_grid, text="onWin").grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(combat_grid, textvariable=self.ev_onwin, width=10).grid(row=3, column=1, sticky="w", pady=(6, 0))
        ttk.Label(combat_grid, text="onLose").grid(row=3, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(combat_grid, textvariable=self.ev_onlose, width=10).grid(row=3, column=3, sticky="w", pady=(6, 0))

        # Test section
        self.ev_test_enabled = tk.BooleanVar(value=False)
        test_hdr = ttk.Checkbutton(events_box, text="Test event", variable=self.ev_test_enabled, command=self._mark_dirty)
        test_hdr.grid(row=2, column=0, sticky="w", padx=8, pady=(10, 2))

        test_grid = ttk.Frame(events_box)
        test_grid.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))
        for i in range(4):
            test_grid.columnconfigure(i, weight=1)

        self.ev_testref = tk.StringVar(value="")  # preferred
        self.ev_test_stat = tk.StringVar(value="")
        self.ev_test_dice = tk.StringVar(value="")
        self.ev_test_success = tk.StringVar(value="")
        self.ev_test_fail = tk.StringVar(value="")
        self.ev_test_cons_s = tk.StringVar(value="0")
        self.ev_test_cons_f = tk.StringVar(value="0")

        ttk.Label(test_grid, text="testRef").grid(row=0, column=0, sticky="w")
        ttk.Entry(test_grid, textvariable=self.ev_testref).grid(row=0, column=1, sticky="ew", padx=(6, 10))
        ttk.Label(test_grid, text="(optional) stat").grid(row=0, column=2, sticky="w")
        ttk.Entry(test_grid, textvariable=self.ev_test_stat, width=10).grid(row=0, column=3, sticky="w")

        ttk.Label(test_grid, text="dice").grid(row=1, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(test_grid, textvariable=self.ev_test_dice, width=10).grid(row=1, column=1, sticky="w", pady=(6, 0))
        ttk.Label(test_grid, text="successGoto").grid(row=1, column=2, sticky="w", pady=(6, 0))
        ttk.Entry(test_grid, textvariable=self.ev_test_success, width=10).grid(row=1, column=3, sticky="w", pady=(6, 0))

        ttk.Label(test_grid, text="failGoto").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(test_grid, textvariable=self.ev_test_fail, width=10).grid(row=2, column=1, sticky="w", pady=(6, 0))
        ttk.Label(test_grid, text="consume S/F").grid(row=2, column=2, sticky="w", pady=(6, 0))
        cons_row = ttk.Frame(test_grid)
        cons_row.grid(row=2, column=3, sticky="w", pady=(6, 0))
        ttk.Entry(cons_row, textvariable=self.ev_test_cons_s, width=5).pack(side="left")
        ttk.Entry(cons_row, textvariable=self.ev_test_cons_f, width=5).pack(side="left", padx=(6, 0))

        # Modifiers
        mods_box = ttk.LabelFrame(lower, text="Environment / Modifiers (envEffect)")
        mods_box.grid(row=1, column=1, sticky="nsew", pady=(10, 0))
        mods_box.columnconfigure(0, weight=1)
        mods_box.rowconfigure(0, weight=1)

        self.mods_tree = ttk.Treeview(
            mods_box,
            columns=("target", "op", "value", "scope", "ref", "label"),
            show="headings",
            height=8,
        )
        for col, w in (("target", 180), ("op", 60), ("value", 60), ("scope", 90), ("ref", 140), ("label", 340)):
            self.mods_tree.heading(col, text=col)
            self.mods_tree.column(col, width=w, anchor="w")
        self.mods_tree.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8, 4))

        mbtns = ttk.Frame(mods_box)
        mbtns.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        ttk.Button(mbtns, text="Add", command=self._mods_add).pack(side="left")
        ttk.Button(mbtns, text="Edit", command=self._mods_edit).pack(side="left", padx=(6, 0))
        ttk.Button(mbtns, text="Remove", command=self._mods_remove).pack(side="left", padx=(6, 0))

        # Helpful template button (your “luminosité faible” use-case)
        ttk.Button(
            mods_box,
            text="Insert template: low light -1 skill (attack)",
            command=self._mods_insert_low_light_template,
        ).grid(row=2, column=0, sticky="w", padx=8, pady=(0, 8))


        # Mark dirty when any event field changes (entries / checkboxes)
        for v in (
            self.ev_combat_enabled,
            self.ev_allowflee,
            self.ev_rulesref,
            self.ev_enemyname,
            self.ev_enemyskill,
            self.ev_enemystamina,
            self.ev_onwin,
            self.ev_onlose,
            self.ev_test_enabled,
            self.ev_testref,
            self.ev_test_stat,
            self.ev_test_dice,
            self.ev_test_success,
            self.ev_test_fail,
            self.ev_test_cons_s,
            self.ev_test_cons_f,
        ):
            try:
                v.trace_add("write", self._on_editor_var_change)
            except Exception:
                try:
                    v.trace("w", lambda *_a: self._on_editor_var_change())
                except Exception:
                    pass

        self._set_editor_enabled(False)

    def _set_editor_enabled(self, enabled: bool):
        if enabled:
            self.edit_text.configure(state="normal")
        else:
            self.edit_text.configure(state="disabled")
        self.edit_pid_var.set(self._editing_pid or "(none)")
        self.edit_dirty_var.set("")


    def _mark_dirty(self):
        """Called by Tk events/variable traces when the editor might have changed.

        IMPORTANT: do not mark dirty on paragraph selection / UI refresh.
        """
        if self._suspend_dirty:
            try:
                self.edit_text.edit_modified(False)
            except Exception:
                pass
            return

        # No paragraph selected => nothing to mark
        if not self._editing_pid:
            try:
                self.edit_text.edit_modified(False)
            except Exception:
                pass
            return

        # Only mark dirty if Tk reports *actual* user modifications.
        try:
            if not self.edit_text.edit_modified():
                return
            self.edit_text.edit_modified(False)
        except Exception:
            # If Tk can't report the flag, be conservative and mark dirty.
            pass

        self._set_dirty(self._editing_pid, True)


    def _refresh_edit(self):
        self._refresh_edit_list()
        self._clear_editor()

    def _refresh_edit_list(self):
        self.edit_list.delete(0, "end")
        if not self.book:
            return

        f = self.edit_filter.get().strip().lower()

        ids = sorted(self.book.paragraphs.keys(), key=_pid_sort_key)
        for pid in ids:
            if f:
                if f not in pid.lower():
                    t = (self.book.paragraphs[pid].text or "").lower()
                    if f not in t:
                        continue
            self.edit_list.insert("end", pid)

        self._refresh_edit_list_colors()

    def _clear_editor(self):
        self._editing_pid = None
        self.edit_pid_var.set("(none)")
        self.edit_dirty_var.set("")
        self.edit_text.configure(state="normal")
        self.edit_text.delete("1.0", "end")
        self.edit_text.configure(state="disabled")

        for tr in (self.choices_tree, self.mods_tree):
            for it in tr.get_children():
                tr.delete(it)

        self.ev_combat_enabled.set(False)
        self.ev_allowflee.set(False)
        self.ev_rulesref.set("ff_classic")
        self.ev_enemyname.set("")
        self.ev_enemyskill.set("")
        self.ev_enemystamina.set("")
        self.ev_onwin.set("")
        self.ev_onlose.set("")

        self.ev_test_enabled.set(False)
        self.ev_testref.set("")
        self.ev_test_stat.set("")
        self.ev_test_dice.set("")
        self.ev_test_success.set("")
        self.ev_test_fail.set("")
        self.ev_test_cons_s.set("0")
        self.ev_test_cons_f.set("0")

        self._set_editor_enabled(False)


    def _edit_select(self):
        new_pid = self._get_selected_pid()
        if not new_pid or not self.book or not self._xml_root:
            return

        # When switching paragraphs, keep the current unsaved edits in memory
        if self._editing_pid and self._editing_pid != new_pid:
            self._capture_current_to_draft()

        node = self._find_paragraph_node(new_pid)
        if node is None:
            messagebox.showerror("XML error", f"Paragraph id='{new_pid}' not found in XML.")
            return

        # Load from draft if present, otherwise from XML
        if new_pid in self._drafts:
            state = self._drafts[new_pid]
        else:
            state = self._state_from_xml_node(node)

        self._load_state_into_ui(new_pid, state)
        self._select_links_pid(new_pid)

    def _load_events_from_xml(self, p_node: ET.Element):
        # reset
        self.ev_combat_enabled.set(False)
        self.ev_allowflee.set(False)
        self.ev_rulesref.set("ff_classic")
        self.ev_enemyname.set("")
        self.ev_enemyskill.set("")
        self.ev_enemystamina.set("")
        self.ev_onwin.set("")
        self.ev_onlose.set("")

        self.ev_test_enabled.set(False)
        self.ev_testref.set("")
        self.ev_test_stat.set("")
        self.ev_test_dice.set("")
        self.ev_test_success.set("")
        self.ev_test_fail.set("")
        self.ev_test_cons_s.set("0")
        self.ev_test_cons_f.set("0")

        for ev in p_node.findall("event"):
            etype = (ev.get("type") or "").strip().lower()
            if etype == "combat" and not self.ev_combat_enabled.get():
                self.ev_combat_enabled.set(True)
                self.ev_rulesref.set((ev.get("rulesRef") or "ff_classic").strip())
                self.ev_allowflee.set((ev.get("allowFlee") or "").strip().lower() in ("1", "true", "yes", "on"))
                self.ev_enemyname.set((ev.get("enemyName") or "").strip())
                self.ev_enemyskill.set((ev.get("enemySkill") or "").strip())
                self.ev_enemystamina.set((ev.get("enemyStamina") or "").strip())
                self.ev_onwin.set((ev.get("onWin") or "").strip())
                self.ev_onlose.set((ev.get("onLose") or "").strip())
                continue

            if etype == "test" and not self.ev_test_enabled.get():
                self.ev_test_enabled.set(True)
                self.ev_testref.set((ev.get("testRef") or "").strip())
                self.ev_test_stat.set((ev.get("stat") or "").strip())
                self.ev_test_dice.set((ev.get("dice") or "").strip())
                self.ev_test_success.set((ev.get("successGoto") or "").strip())
                self.ev_test_fail.set((ev.get("failGoto") or "").strip())
                self.ev_test_cons_s.set((ev.get("consumeOnSuccess") or "0").strip())
                self.ev_test_cons_f.set((ev.get("consumeOnFail") or "0").strip())
                continue

    def _edit_add_paragraph(self):
        if not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        next_id = None
        if self.book:
            nums = []
            for pid in self.book.paragraphs.keys():
                if str(pid).isdigit():
                    nums.append(int(pid))
            if nums:
                next_id = str(max(nums) + 1)
        suggested = next_id or ""

        pid = simpledialog.askstring("Add paragraph", "New paragraph id:", initialvalue=suggested)
        if not pid:
            return
        pid = pid.strip()
        if not pid:
            return

        if self.book and pid in self.book.paragraphs:
            messagebox.showerror("Add paragraph", f"Paragraph '{pid}' already exists.")
            return

        container = self._ensure_paragraphs_container()

        new_p = ET.SubElement(container, "paragraph")
        new_p.set("id", pid)
        t = ET.SubElement(new_p, "text")
        t.text = "\n(Write your paragraph text here)\n"

        try:
            bak = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        self.load_book(self._current_book_path)
        messagebox.showinfo("Added", f"Paragraph {pid} created.\nBackup: {bak}")

        self._select_edit_pid(pid)

    def _select_edit_pid(self, pid: str):
        for i in range(self.edit_list.size()):
            if self.edit_list.get(i) == pid:
                self.edit_list.selection_clear(0, "end")
                self.edit_list.selection_set(i)
                self.edit_list.see(i)
                self._edit_select()
                break

    def _edit_delete_selected(self):
        if not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        pid = self._get_selected_pid()
        if not pid:
            messagebox.showinfo("Delete", "Select a paragraph first.")
            return

        if not messagebox.askyesno("Delete paragraph", f"Delete paragraph {pid}? This cannot be undone (backup will be created)."):
            return

        p_node = self._find_paragraph_node(pid)
        if p_node is None:
            messagebox.showerror("XML error", f"Paragraph id='{pid}' not found in XML.")
            return

        parent = self._xml_root.find("paragraphs")
        if parent is None:
            parent = self._xml_root
        try:
            parent.remove(p_node)
        except Exception:
            removed = False
            for container in (self._xml_root, parent):
                for child in list(container):
                    if child.tag == "paragraph" and child.get("id") == pid:
                        container.remove(child)
                        removed = True
                        break
                if removed:
                    break

        try:
            bak = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        self.load_book(self._current_book_path)
        messagebox.showinfo("Deleted", f"Paragraph {pid} deleted.\nBackup: {bak}")


    def _apply_state_to_xml_node(self, p_node: ET.Element, state: dict):
        # --- Save text ---
        text_val = (state.get("text") or "").strip("\n")
        txt_node = p_node.find("text")
        if txt_node is None:
            txt_node = ET.SubElement(p_node, "text")
        txt_node.text = "\n" + text_val + "\n"

        # --- Save choices ---
        for ch in list(p_node.findall("choice")):
            p_node.remove(ch)
        for label, target in state.get("choices", []) or []:
            label = (label or "").strip()
            target = (target or "").strip()
            if not target:
                continue
            ch = ET.SubElement(p_node, "choice")
            ch.set("target", target)
            ch.text = label or "Continue"

        # --- Save events (combat/test) ---
        for ev in list(p_node.findall("event")):
            et = (ev.get("type") or "").strip().lower()
            if et in ("combat", "test"):
                p_node.remove(ev)

        combat = state.get("combat", {}) or {}
        if combat.get("enabled"):
            ev = ET.SubElement(p_node, "event")
            ev.set("type", "combat")
            rules_ref = (combat.get("rulesRef") or "").strip()
            if rules_ref:
                ev.set("rulesRef", rules_ref)
            if combat.get("allowFlee"):
                ev.set("allowFlee", "1")
            enemy_name = (combat.get("enemyName") or "").strip() or "Enemy"
            ev.set("enemyName", enemy_name)

            def _int_or_default(s: str, d: int) -> str:
                try:
                    return str(int(str(s).strip()))
                except Exception:
                    return str(d)

            ev.set("enemySkill", _int_or_default(combat.get("enemySkill", ""), 6))
            ev.set("enemyStamina", _int_or_default(combat.get("enemyStamina", ""), 6))

            on_win = (combat.get("onWin") or "").strip()
            on_lose = (combat.get("onLose") or "").strip()
            if on_win:
                ev.set("onWin", on_win)
            if on_lose:
                ev.set("onLose", on_lose)

        test = state.get("test", {}) or {}
        if test.get("enabled"):
            ev = ET.SubElement(p_node, "event")
            ev.set("type", "test")
            test_ref = (test.get("testRef") or "").strip()
            if test_ref:
                ev.set("testRef", test_ref)
            stat_id = (test.get("stat") or "").strip()
            if stat_id:
                ev.set("stat", stat_id)
            dice = (test.get("dice") or "").strip()
            if dice:
                ev.set("dice", dice)
            succ = (test.get("successGoto") or "").strip()
            fail = (test.get("failGoto") or "").strip()
            if succ:
                ev.set("successGoto", succ)
            if fail:
                ev.set("failGoto", fail)

            def _int0(s: str) -> str:
                try:
                    return str(int(str(s).strip()))
                except Exception:
                    return "0"

            ev.set("consumeOnSuccess", _int0(test.get("consumeOnSuccess", "0")))
            ev.set("consumeOnFail", _int0(test.get("consumeOnFail", "0")))

        # --- Save modifiers/envEffect ---
        for ee in list(p_node.findall("envEffect")):
            p_node.remove(ee)
        env_block = p_node.find("environment")
        if env_block is not None:
            p_node.remove(env_block)

        for row in state.get("mods", []) or []:
            if not row:
                continue
            target, op, value, scope, ref, label = (list(row) + ["", "", "", "", "", ""])[:6]
            target = (target or "").strip()
            if not target:
                continue
            op = (op or "add").strip() or "add"
            scope = (scope or "paragraph").strip() or "paragraph"
            try:
                ivalue = int(str(value).strip())
            except Exception:
                ivalue = 0

            ee = ET.SubElement(p_node, "envEffect")
            ee.set("target", target)
            ee.set("op", op)
            ee.set("value", str(ivalue))
            ee.set("scope", scope)
            if (ref or "").strip():
                ee.set("ref", (ref or "").strip())
            if (label or "").strip():
                ee.set("label", (label or "").strip())

    def _edit_save_current(self):
        if not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        pid = self._editing_pid
        if not pid:
            messagebox.showinfo("Save", "Select a paragraph first.")
            return

        p_node = self._find_paragraph_node(pid)
        if p_node is None:
            messagebox.showerror("XML error", f"Paragraph id='{pid}' not found in XML.")
            return

        # Capture current UI into draft and apply to XML
        state = self._gather_state_from_ui()
        self._drafts[pid] = state
        self._apply_state_to_xml_node(p_node, state)

        try:
            bak = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        # Reload parsed book model but keep drafts for other paragraphs
        cur_path = self._current_book_path
        self.load_book(cur_path)

        self._set_dirty(pid, False)
        messagebox.showinfo("Saved", f"Paragraph {pid} saved.\nBackup: {bak}")
        self._select_edit_pid(pid)

    def _edit_save_all(self):
        if not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return
        if not self._dirty_pids:
            messagebox.showinfo("Save All", "No unsaved changes.")
            return

        # Ensure current paragraph's latest UI is in drafts
        if self._editing_pid and self._editing_pid in self._dirty_pids:
            self._drafts[self._editing_pid] = self._gather_state_from_ui()

        # Apply all drafts to XML
        for pid in sorted(self._dirty_pids, key=_pid_sort_key):
            p_node = self._find_paragraph_node(pid)
            if p_node is None:
                continue
            state = self._drafts.get(pid)
            if state is None:
                # fallback: keep existing XML
                continue
            self._apply_state_to_xml_node(p_node, state)

        try:
            bak = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        cur_path = self._current_book_path
        self.load_book(cur_path)

        saved_count = len(self._dirty_pids)
        self._dirty_pids.clear()
        self._drafts.clear()
        self._refresh_edit_list_colors()
        self._update_current_dirty_label()

        messagebox.showinfo("Save All", f"Saved {saved_count} paragraph(s).\nBackup: {bak}")


    # ---- choices CRUD ----

    def _choices_add(self):
        if not self._editing_pid:
            messagebox.showinfo("Choices", "Select a paragraph first.")
            return
        label = simpledialog.askstring("Add choice", "Choice label:")
        if label is None:
            return
        target = simpledialog.askstring("Add choice", "Choice target (paragraph id):")
        if target is None:
            return
        self.choices_tree.insert("", "end", values=((label or "").strip(), (target or "").strip()))
        self._set_dirty(self._editing_pid, True)

    def _choices_edit(self):
        sel = self.choices_tree.selection()
        if not sel:
            return
        item = sel[0]
        cur_label, cur_target = self.choices_tree.item(item, "values")
        label = simpledialog.askstring("Edit choice", "Choice label:", initialvalue=str(cur_label))
        if label is None:
            return
        target = simpledialog.askstring("Edit choice", "Choice target:", initialvalue=str(cur_target))
        if target is None:
            return
        self.choices_tree.item(item, values=((label or "").strip(), (target or "").strip()))
        self._set_dirty(self._editing_pid, True)

    def _choices_remove(self):
        sel = self.choices_tree.selection()
        if not sel:
            return
        self.choices_tree.delete(sel[0])
        self._set_dirty(self._editing_pid, True)

    # ---- modifiers CRUD ----

    def _mods_insert_low_light_template(self):
        if not self._editing_pid:
            messagebox.showinfo("Modifiers", "Select a paragraph first.")
            return
        self.mods_tree.insert(
            "",
            "end",
            values=(
                "stat:skill",
                "add",
                "-1",
                "paragraph",
                "low_light_attack",
                "Luminosité faible : -1 à l'attaque",
            ),
        )
        self._set_dirty(self._editing_pid, True)

    def _mods_add(self):
        if not self._editing_pid:
            messagebox.showinfo("Modifiers", "Select a paragraph first.")
            return
        target = simpledialog.askstring("Add modifier", "target (e.g. stat:skill):")
        if target is None:
            return
        op = simpledialog.askstring("Add modifier", "op (add):", initialvalue="add")
        if op is None:
            return
        value = simpledialog.askstring("Add modifier", "value (int):", initialvalue="0")
        if value is None:
            return
        scope = simpledialog.askstring("Add modifier", "scope (paragraph|scene|global):", initialvalue="paragraph")
        if scope is None:
            return
        ref = simpledialog.askstring("Add modifier", "ref (optional):", initialvalue="")
        if ref is None:
            return
        label = simpledialog.askstring("Add modifier", "label (optional):", initialvalue="")
        if label is None:
            return

        self.mods_tree.insert(
            "",
            "end",
            values=(
                (target or "").strip(),
                (op or "add").strip(),
                (value or "0").strip(),
                (scope or "paragraph").strip(),
                (ref or "").strip(),
                (label or "").strip(),
            ),
        )
        self._set_dirty(self._editing_pid, True)

    def _mods_edit(self):
        sel = self.mods_tree.selection()
        if not sel:
            return
        item = sel[0]
        target, op, value, scope, ref, label = self.mods_tree.item(item, "values")

        target2 = simpledialog.askstring("Edit modifier", "target:", initialvalue=str(target))
        if target2 is None:
            return
        op2 = simpledialog.askstring("Edit modifier", "op:", initialvalue=str(op))
        if op2 is None:
            return
        value2 = simpledialog.askstring("Edit modifier", "value:", initialvalue=str(value))
        if value2 is None:
            return
        scope2 = simpledialog.askstring("Edit modifier", "scope:", initialvalue=str(scope))
        if scope2 is None:
            return
        ref2 = simpledialog.askstring("Edit modifier", "ref:", initialvalue=str(ref))
        if ref2 is None:
            return
        label2 = simpledialog.askstring("Edit modifier", "label:", initialvalue=str(label))
        if label2 is None:
            return

        self.mods_tree.item(
            item,
            values=(
                (target2 or "").strip(),
                (op2 or "add").strip(),
                (value2 or "0").strip(),
                (scope2 or "paragraph").strip(),
                (ref2 or "").strip(),
                (label2 or "").strip(),
            ),
        )
        self._set_dirty(self._editing_pid, True)

    def _mods_remove(self):
        sel = self.mods_tree.selection()
        if not sel:
            return
        self.mods_tree.delete(sel[0])
        self._set_dirty(self._editing_pid, True)

    # -----------------------
    # Graph SVG viewer (spawn ui/graph_viewer.py as separate process)
    # -----------------------

    def _find_graphviz_dot(self) -> str | None:
        dot_path = shutil.which("dot")
        if dot_path:
            return dot_path
        candidates = [
            r"C:\Program Files\Graphviz\bin\dot.exe",
            r"C:\Program Files (x86)\Graphviz\bin\dot.exe",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def _export_graph_svg_to_temp(self) -> None:
        """
        Export DOT then build SVG into self._graph_svg_path.
        """
        if not self.book:
            raise RuntimeError("No book loaded")

        dot_path = self._find_graphviz_dot()
        if not dot_path:
            raise RuntimeError(
                "Graphviz (dot) not found in PATH.\n"
                "Install Graphviz or fix PATH, then restart."
            )

        export_dot(self.book, self.book_dir, self._graph_dot_path)
        subprocess.run([dot_path, "-Tsvg", self._graph_dot_path, "-o", self._graph_svg_path], check=True)

    def _write_graph_viewer_html(self) -> None:
        """
        Stage the HTML viewer file from <repo_root>/ui/viewer.html into the temp graph folder.

        This keeps HTML/JS out of the Python source (easier to edit and less fragile).
        The HTML must reference the SVG as a relative file named: graph.svg
        """
        template_path = os.path.join(REPO_ROOT, "ui", "viewer.html")
        if not os.path.exists(template_path):
            raise RuntimeError(
                "Missing viewer template.\n\n"
                f"Expected: {template_path}\n\n"
                "Create it by copying viewer.html into <repo_root>/ui/."
            )

        # Copy template into the temp output directory where graph.svg lives
        shutil.copy2(template_path, self._graph_html_path)

    def _locate_graph_viewer_script(self) -> str | None:
        """
        Look for the viewer in <repo_root>/ui/graph_viewer.py (preferred),
        but also accept <repo_root>/ui/graphviewer.py if that's what you named it.
        """
        candidates = [
            os.path.join(REPO_ROOT, "ui", "graph_viewer.py"),
            os.path.join(REPO_ROOT, "ui", "graphviewer.py"),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None

    def _open_graph_viewer(self):
        """
        Spawns the pywebview viewer as a *separate process* to avoid Tkinter/pywebview threading issues.
        Viewer file is expected at: <repo_root>\\ui\\graph_viewer.py (or graphviewer.py).
        """
        if not self.book or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        viewer_py = self._locate_graph_viewer_script()
        if not viewer_py:
            messagebox.showerror(
                "Viewer missing",
                "Could not find viewer script.\n"
                "Expected one of:\n"
                f"  {os.path.join(REPO_ROOT, 'ui', 'graph_viewer.py')}\n"
                f"  {os.path.join(REPO_ROOT, 'ui', 'graphviewer.py')}",
            )
            return

        # Export once so the window opens with something visible
        try:
            self._export_graph_svg_to_temp()
            self._write_graph_viewer_html()
        except Exception as e:
            messagebox.showerror("Graph export error", str(e))
            return

        tool_path = os.path.abspath(__file__)

        try:
            subprocess.Popen(
                [sys.executable, viewer_py, sys.executable, tool_path, self._current_book_path, self._graph_out_dir],
                cwd=REPO_ROOT,
            )
        except Exception as e:
            messagebox.showerror("Viewer launch failed", str(e))

    # -----------------------
    # Links tab
    # -----------------------

    def _build_links_tab(self):
        root = self.tab_links
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=0)
        root.rowconfigure(1, weight=1)

        ttk.Label(root, text="Paragraph:").grid(row=0, column=0, sticky="w", padx=8, pady=6)

        self.links_pid = tk.StringVar(value="")
        self.links_combo = ttk.Combobox(root, textvariable=self.links_pid, state="readonly")
        self.links_combo.grid(row=0, column=0, sticky="ew", padx=(90, 8), pady=6)
        self.links_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_links_lists())

        export_bar = ttk.Frame(root)
        export_bar.grid(row=0, column=1, sticky="e", padx=8, pady=6)

        ttk.Button(export_bar, text="Export DOT...", command=self.export_dot_dialog).pack(side="right", padx=(0, 5))
        ttk.Button(export_bar, text="Export DOT + SVG", command=self.export_dot_svg_dialog).pack(side="right")

        pan = ttk.Frame(root)
        pan.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        pan.columnconfigure(0, weight=1)
        pan.columnconfigure(1, weight=1)
        pan.rowconfigure(1, weight=1)

        ttk.Label(pan, text="Outgoing").grid(row=0, column=0, sticky="w")
        ttk.Label(pan, text="Incoming").grid(row=0, column=1, sticky="w")

        self.outgoing_list = tk.Listbox(pan)
        self.incoming_list = tk.Listbox(pan)
        self.outgoing_list.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        self.incoming_list.grid(row=1, column=1, sticky="nsew")

    def _refresh_links(self):
        if not self.book:
            self.links_combo["values"] = []
            self.links_pid.set("")
            self.outgoing_list.delete(0, "end")
            self.incoming_list.delete(0, "end")
            return

        ids = sorted(self.book.paragraphs.keys(), key=_pid_sort_key)
        self.links_combo["values"] = ids

        if not self.links_pid.get():
            self.links_pid.set(self.book.start_paragraph)

        self._refresh_links_lists()

    def _select_links_pid(self, pid: str):
        if not self.book:
            return
        values = set(self.links_combo["values"])
        if pid in values:
            self.links_pid.set(pid)
            self._refresh_links_lists()

    def _refresh_links_lists(self):
        if not self.book:
            return

        pid = self.links_pid.get()
        outgoing, incoming = build_link_index(self.book)

        self.outgoing_list.delete(0, "end")
        self.incoming_list.delete(0, "end")

        for t in outgoing.get(pid, []):
            self.outgoing_list.insert("end", t)

        for s in incoming.get(pid, []):
            self.incoming_list.insert("end", s)

    # -----------------------
    # Assets tab
    # -----------------------

    def _build_assets_tab(self):
        root = self.tab_assets
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=0)
        root.rowconfigure(3, weight=1)

        # Row 0: info + paragraph picker
        top = ttk.Frame(root)
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=8, pady=6)
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Paragraph:").grid(row=0, column=0, sticky="w")
        self.assets_pid_var = tk.StringVar(value="")
        self.assets_pid_combo = ttk.Combobox(top, textvariable=self.assets_pid_var, state="readonly", width=30)
        self.assets_pid_combo.grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(
            top,
            text="(Choose a paragraph here to link/unlink images)",
            foreground="#666",
        ).grid(row=0, column=2, sticky="w", padx=(12, 0))

        # Row 1: buttons
        btnbar = ttk.Frame(root)
        btnbar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))

        ttk.Button(btnbar, text="Add Asset...", command=self.add_asset_dialog).pack(side="left")
        ttk.Button(btnbar, text="Import & link image...", command=self.import_and_link_image_dialog).pack(side="left", padx=(6, 0))
        ttk.Button(btnbar, text="Link selected asset...", command=self.link_selected_asset_to_selected_paragraph).pack(side="left", padx=(6, 0))
        ttk.Button(btnbar, text="Remove link", command=self.remove_image_link_from_selected_paragraph).pack(side="left", padx=(6, 0))
        ttk.Button(btnbar, text="Delete selected asset...", command=self.delete_selected_asset_dialog).pack(side="right")

        # Row 2: table
        cols = ("asset_id", "file", "exists", "used_by")
        self.assets_tree = ttk.Treeview(root, columns=cols, show="headings")
        for c in cols:
            self.assets_tree.heading(c, text=c)
            self.assets_tree.column(c, width=160 if c != "used_by" else 620, anchor="w")
        self.assets_tree.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=8, pady=8)
        self.assets_tree.bind("<<TreeviewSelect>>", lambda _e: self._assets_preview_selected())

        # Row 4: preview label
        self.assets_preview = ttk.Label(root, text="(Preview)")
        self.assets_preview.grid(row=4, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 10))

        self._asset_photo = None
        self._asset_img_label = ttk.Label(root)
        self._asset_img_label.grid(row=5, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 10))

    def _refresh_assets_paragraph_picker(self):
        # Keep current selection if possible
        current = (getattr(self, "assets_pid_var", None).get() if hasattr(self, "assets_pid_var") else "") or ""
        if not hasattr(self, "assets_pid_combo"):
            return

        if not self.book:
            self.assets_pid_combo["values"] = []
            self.assets_pid_var.set("")
            return

        ids = sorted(self.book.paragraphs.keys(), key=_pid_sort_key)
        self.assets_pid_combo["values"] = ids

        # restore selection if possible, else keep empty
        if current and current in ids:
            self.assets_pid_var.set(current)
        else:
            self.assets_pid_var.set(ids[0] if ids else "")

    def _refresh_assets(self):
        self._refresh_assets_paragraph_picker()

        self.assets_tree.delete(*self.assets_tree.get_children())
        self.assets_preview.configure(text="(Preview)")
        self._asset_photo = None
        self._asset_img_label.configure(image="", text="")

        if not self.book:
            self.assets_preview.configure(text="(No book loaded)")
            return

        if not self.book.assets.images:
            base = self.book.assets.base_path or "(empty)"
            self.assets_preview.configure(text=f"No assets declared yet. assets.basePath = {base}")
            return

        usage = asset_usage(self.book)

        for asset_id, rel_file in sorted(self.book.assets.images.items(), key=lambda kv: kv[0]):
            abs_path = resolve_image_path(self.book_dir, self.book.assets, asset_id)
            exists = "YES" if os.path.exists(abs_path) else "NO"
            used_by = ", ".join(usage.get(asset_id, []))
            self.assets_tree.insert("", "end", values=(asset_id, rel_file, exists, used_by))

    def _assets_preview_selected(self):
        if not self.book:
            return
        asset_id = self._get_selected_asset_id()
        if not asset_id:
            return

        abs_path = resolve_image_path(self.book_dir, self.book.assets, asset_id)
        self.assets_preview.configure(text=f"{asset_id} -> {abs_path}")

        if not PIL_AVAILABLE or not os.path.exists(abs_path):
            self._asset_img_label.configure(image="", text="(Install Pillow and ensure file exists to preview)")
            return

        img = Image.open(abs_path)
        img.thumbnail((650, 360))
        self._asset_photo = ImageTk.PhotoImage(img)
        self._asset_img_label.configure(image=self._asset_photo, text="")

    def _assets_selected_pid(self) -> str | None:
        pid = (self.assets_pid_var.get() or "").strip() if hasattr(self, "assets_pid_var") else ""
        return pid or None

    def import_and_link_image_dialog(self):
        """
        Import an image file, copy it to assets directory, create/update <assets><image .../></assets>,
        and link it to the selected paragraph via <image ref="..."/>.
        (Assets tab version: paragraph is chosen from dropdown.)
        """
        if not self.book or not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        pid = self._assets_selected_pid()
        if not pid:
            messagebox.showwarning("No paragraph selected", "Choose a paragraph in the Assets tab dropdown.")
            return

        src = filedialog.askopenfilename(
            title="Select an image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not src:
            return

        base_path = (self.book.assets.base_path or "").strip()
        dest_dir = os.path.join(self.book_dir, base_path)
        os.makedirs(dest_dir, exist_ok=True)

        ext = os.path.splitext(src)[1].lower() or ".png"
        safe_pid = re.sub(r"[^a-zA-Z0-9_-]+", "_", pid)
        candidate = f"p{safe_pid}{ext}"
        dest_path = os.path.join(dest_dir, candidate)

        n = 2
        while os.path.exists(dest_path):
            candidate = f"p{safe_pid}_{n}{ext}"
            dest_path = os.path.join(dest_dir, candidate)
            n += 1

        try:
            shutil.copy2(src, dest_path)
        except Exception as e:
            messagebox.showerror("Copy error", str(e))
            return

        asset_id = os.path.splitext(os.path.basename(dest_path))[0]
        rel_file = os.path.basename(dest_path)

        # Update XML assets
        assets_elem = self._ensure_assets_elem()
        if self.book.assets.base_path and not assets_elem.get("basePath"):
            assets_elem.set("basePath", self.book.assets.base_path)

        img_node = None
        for im in assets_elem.findall("image"):
            if im.get("id") == asset_id:
                img_node = im
                break
        if img_node is None:
            img_node = ET.SubElement(assets_elem, "image")
            img_node.set("id", asset_id)
        img_node.set("file", rel_file)

        # Link to paragraph in XML
        p_node = self._find_paragraph_node(pid)
        if p_node is None:
            messagebox.showerror("XML error", f"Could not find paragraph id='{pid}' in XML.")
            return

        img_elem = p_node.find("image")
        if img_elem is None:
            img_elem = ET.SubElement(p_node, "image")
        img_elem.set("ref", asset_id)

        try:
            bak_path = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        # Reload models and keep selection
        self.load_book(self._current_book_path)
        self.assets_pid_var.set(pid)

        messagebox.showinfo(
            "Assigned",
            f"Image imported and linked.\n\n"
            f"Paragraph: {pid}\n"
            f"Asset id: {asset_id}\n"
            f"File: {dest_path}\n\n"
            f"Backup: {bak_path}",
        )

    def add_asset_dialog(self):
        """
        Import an image into the assets directory and add <assets><image .../></assets>.
        Does NOT link it to a paragraph.
        """
        if not self.book or not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        src = filedialog.askopenfilename(
            title="Import an asset image",
            filetypes=[
                ("Images", "*.png *.jpg *.jpeg *.webp *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not src:
            return

        base_path = (self.book.assets.base_path or "").strip()
        dest_dir = os.path.join(self.book_dir, base_path)
        os.makedirs(dest_dir, exist_ok=True)

        ext = os.path.splitext(src)[1].lower() or ".png"
        base_name = os.path.splitext(os.path.basename(src))[0]
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", base_name).strip("_") or "asset"

        candidate = f"{safe_name}{ext}"
        dest_path = os.path.join(dest_dir, candidate)

        n = 2
        while os.path.exists(dest_path):
            candidate = f"{safe_name}_{n}{ext}"
            dest_path = os.path.join(dest_dir, candidate)
            n += 1

        try:
            shutil.copy2(src, dest_path)
        except Exception as e:
            messagebox.showerror("Copy error", str(e))
            return

        asset_id = os.path.splitext(os.path.basename(dest_path))[0]
        rel_file = os.path.basename(dest_path)

        # Update XML
        assets_elem = self._ensure_assets_elem()
        if self.book.assets.base_path and not assets_elem.get("basePath"):
            assets_elem.set("basePath", self.book.assets.base_path)

        img_node = None
        for im in assets_elem.findall("image"):
            if im.get("id") == asset_id:
                img_node = im
                break
        if img_node is None:
            img_node = ET.SubElement(assets_elem, "image")
            img_node.set("id", asset_id)
        img_node.set("file", rel_file)

        try:
            bak_path = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        self.load_book(self._current_book_path)
        messagebox.showinfo("Asset added", f"Asset imported:\n{dest_path}\n\nAsset id: {asset_id}\nBackup: {bak_path}")

    def link_selected_asset_to_selected_paragraph(self):
        """
        Link an already-declared asset (selected in Assets tab) to the paragraph chosen in the Assets dropdown.
        Does NOT copy files; only writes <image ref="..."/> on the paragraph.
        """
        if not self.book or not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        pid = self._assets_selected_pid()
        if not pid:
            messagebox.showwarning("No paragraph selected", "Choose a paragraph in the Assets tab dropdown.")
            return

        asset_id = self._get_selected_asset_id()
        if not asset_id:
            messagebox.showwarning("No asset selected", "Select an asset in the Assets tab list.")
            return

        if asset_id not in self.book.assets.images:
            messagebox.showerror("Asset error", f"Asset '{asset_id}' is not declared in the book.")
            return

        p_node = self._find_paragraph_node(pid)
        if p_node is None:
            messagebox.showerror("XML error", f"Paragraph id='{pid}' not found in XML.")
            return

        img_elem = p_node.find("image")
        if img_elem is None:
            img_elem = ET.SubElement(p_node, "image")
        img_elem.set("ref", asset_id)

        try:
            bak_path = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        self.load_book(self._current_book_path)
        self.assets_pid_var.set(pid)
        messagebox.showinfo("Assigned", f"Linked asset '{asset_id}' to paragraph {pid}.\nBackup: {bak_path}")

    def remove_image_link_from_selected_paragraph(self):
        """
        Remove <image .../> from the paragraph chosen in the Assets dropdown.
        Does NOT delete the asset declaration nor the file.
        """
        if not self.book or not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        pid = self._assets_selected_pid()
        if not pid:
            messagebox.showwarning("No paragraph selected", "Choose a paragraph in the Assets tab dropdown.")
            return

        p_node = self._find_paragraph_node(pid)
        if p_node is None:
            messagebox.showerror("XML error", f"Paragraph id='{pid}' not found in XML.")
            return

        img_elem = p_node.find("image")
        if img_elem is None:
            messagebox.showinfo("No image", f"Paragraph {pid} has no image linked.")
            return

        p_node.remove(img_elem)

        try:
            bak_path = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        self.load_book(self._current_book_path)
        self.assets_pid_var.set(pid)
        messagebox.showinfo("Link removed", f"Image link removed from paragraph {pid}.\nBackup: {bak_path}")

    def delete_selected_asset_dialog(self):
        """
        Delete the selected asset declaration from <assets> and optionally delete the file.
        If the asset is used by one or more paragraphs, offers to unlink it everywhere first.
        """
        if not self.book or not self._xml_root or not self._xml_tree or not self._current_book_path:
            messagebox.showwarning("No book", "Load a book first.")
            return

        asset_id = self._get_selected_asset_id()
        if not asset_id:
            messagebox.showwarning("No asset selected", "Select an asset in the Assets tab.")
            return

        if asset_id not in self.book.assets.images:
            messagebox.showerror("Asset error", f"Asset '{asset_id}' is not declared in the book.")
            return

        usage = asset_usage(self.book)
        used_by = usage.get(asset_id, [])

        if used_by:
            msg = (
                f"Asset '{asset_id}' is used by paragraphs:\n"
                f"{', '.join(used_by)}\n\n"
                f"To delete the asset, it must be unlinked. Unlink it from ALL these paragraphs now?"
            )
            if not messagebox.askyesno("Asset in use", msg):
                return

            for pid in used_by:
                p_node = self._find_paragraph_node(pid)
                if p_node is None:
                    continue
                img_elem = p_node.find("image")
                if img_elem is not None and (img_elem.get("ref") == asset_id):
                    p_node.remove(img_elem)

        assets_elem = self._xml_root.find("assets")
        if assets_elem is not None:
            for im in list(assets_elem.findall("image")):
                if im.get("id") == asset_id:
                    assets_elem.remove(im)
                    break

        abs_path = resolve_image_path(self.book_dir, self.book.assets, asset_id)

        try:
            bak_path = self._save_xml_with_backup()
        except Exception as e:
            messagebox.showerror("Save error", str(e))
            return

        delete_file = False
        if os.path.exists(abs_path):
            delete_file = messagebox.askyesno("Delete file?", f"Asset declaration removed.\n\nDelete the file too?\n{abs_path}")

        if delete_file:
            try:
                os.remove(abs_path)
            except Exception as e:
                messagebox.showwarning("File delete failed", f"Could not delete file:\n{abs_path}\n\n{e}")

        self.load_book(self._current_book_path)
        messagebox.showinfo("Asset deleted", f"Asset '{asset_id}' deleted.\nBackup: {bak_path}")

    # -----------------------
    # Search tab
    # -----------------------

    def _build_search_tab(self):
        root = self.tab_search
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=2)
        root.rowconfigure(1, weight=1)

        ttk.Label(root, text="Query:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.search_q = tk.StringVar(value="")
        ent = ttk.Entry(root, textvariable=self.search_q)
        ent.grid(row=0, column=0, sticky="ew", padx=(70, 8), pady=6)
        ent.bind("<Return>", lambda _e: self._do_search())
        ttk.Button(root, text="Search", command=self._do_search).grid(row=0, column=1, sticky="w", padx=8, pady=6)

        self.search_results = tk.Listbox(root)
        self.search_results.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.search_results.bind("<<ListboxSelect>>", lambda _e: self._search_select())

        self.search_preview = tk.Text(root, wrap="word")
        self.search_preview.grid(row=1, column=1, sticky="nsew", padx=8, pady=8)
        self.search_preview.configure(state="disabled")

    def _refresh_search(self):
        self.search_results.delete(0, "end")
        self.search_preview.configure(state="normal")
        self.search_preview.delete("1.0", "end")
        self.search_preview.configure(state="disabled")

    def _do_search(self):
        self.search_results.delete(0, "end")
        if not self.book:
            return

        q = self.search_q.get().strip().lower()
        if not q:
            return

        for pid, para in self.book.paragraphs.items():
            text = (para.text or "").lower()
            if q in text:
                self.search_results.insert("end", pid)

    def _search_select(self):
        if not self.book:
            return
        sel = self.search_results.curselection()
        if not sel:
            return
        pid = self.search_results.get(sel[0])
        para = self.book.paragraphs[pid]

        snippet = para.text.strip()
        if len(snippet) > 1200:
            snippet = snippet[:1200] + "\n...\n"

        self.search_preview.configure(state="normal")
        self.search_preview.delete("1.0", "end")
        self.search_preview.insert("1.0", f"Paragraph {pid}\n\n{snippet}")
        self.search_preview.configure(state="disabled")

        self._select_edit_pid(pid)
        self._select_links_pid(pid)

    # -----------------------
    # Validation tab
    # -----------------------

    def _build_validation_tab(self):
        root = self.tab_validation
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        top = ttk.Frame(root)
        top.grid(row=0, column=0, sticky="ew", padx=8, pady=6)
        ttk.Button(top, text="Run validation", command=self._refresh_validation).pack(side="left")
        self.validation_summary = ttk.Label(top, text="(no data)")
        self.validation_summary.pack(side="left", padx=12)

        cols = ("severity", "paragraph", "message")
        self.val_tree = ttk.Treeview(root, columns=cols, show="headings")
        for c in cols:
            self.val_tree.heading(c, text=c)
            self.val_tree.column(c, width=120 if c != "message" else 940, anchor="w")
        self.val_tree.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.val_tree.bind("<<TreeviewSelect>>", lambda _e: self._validation_select())

    def _refresh_validation(self):
        self.val_tree.delete(*self.val_tree.get_children())
        if not self.book:
            self.validation_summary.configure(text="(no book loaded)")
            return

        issues = validate_book(self.book, self.book_dir)
        e = sum(1 for i in issues if i.severity == "ERROR")
        w = sum(1 for i in issues if i.severity == "WARNING")
        n = sum(1 for i in issues if i.severity == "INFO")
        self.validation_summary.configure(text=f"Errors: {e}   Warnings: {w}   Info: {n}")

        for iss in issues:
            self.val_tree.insert("", "end", values=(iss.severity, iss.paragraph_id or "", iss.message))

    def _validation_select(self):
        if not self.book:
            return
        sel = self.val_tree.selection()
        if not sel:
            return
        values = self.val_tree.item(sel[0], "values")
        pid = values[1]
        if pid and pid in self.book.paragraphs:
            self._select_edit_pid(pid)
            self._select_links_pid(pid)

    # -----------------------
    # DOT export
    # -----------------------

    def export_dot_dialog(self):
        if not self.book:
            messagebox.showwarning("No book", "Load a book first.")
            return

        default_name = f"{getattr(self.book, 'book_id', None) or 'book'}.dot"
        path = filedialog.asksaveasfilename(
            title="Export DOT",
            defaultextension=".dot",
            initialfile=default_name,
            initialdir=self.book_dir or os.getcwd(),
            filetypes=[("DOT files", "*.dot"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            export_dot(self.book, self.book_dir, path)
        except Exception as e:
            messagebox.showerror("Export error", str(e))
            return

        messagebox.showinfo("Exported", f"DOT exported to:\n{path}")

    def export_dot_svg_dialog(self):
        if not self.book:
            messagebox.showwarning("No book", "Load a book first.")
            return

        dot_path = shutil.which("dot")
        if not dot_path:
            candidates = [
                r"C:\Program Files\Graphviz\bin\dot.exe",
                r"C:\Program Files (x86)\Graphviz\bin\dot.exe",
            ]
            for c in candidates:
                if os.path.exists(c):
                    dot_path = c
                    break

        if not dot_path:
            messagebox.showerror(
                "Graphviz not found",
                "Graphviz (dot) is not available in PATH.\n"
                "Install Graphviz or fix PATH, then restart VS Code/terminal.",
            )
            return

        default_name = f"{getattr(self.book, 'book_id', None) or 'book'}"
        path = filedialog.asksaveasfilename(
            title="Export DOT + SVG",
            defaultextension=".svg",
            initialfile=default_name,
            initialdir=self.book_dir or os.getcwd(),
            filetypes=[("SVG files", "*.svg")],
        )
        if not path:
            return

        if not path.lower().endswith(".svg"):
            path += ".svg"
        dot_file = path[:-4] + ".dot"

        try:
            export_dot(self.book, self.book_dir, dot_file)
            subprocess.run([dot_path, "-Tsvg", dot_file, "-o", path], check=True)
        except Exception as e:
            messagebox.showerror("Export error", str(e))
            return

        messagebox.showinfo("Exported", f"SVG exported to:\n{path}")

        try:
            os.startfile(path)  # Windows
        except Exception:
            pass


# -----------------------
# CLI: export graph for viewer process
# -----------------------

def _find_graphviz_dot_cli() -> str | None:
    dot_path = shutil.which("dot")
    if dot_path:
        return dot_path
    candidates = [
        r"C:\Program Files\Graphviz\bin\dot.exe",
        r"C:\Program Files (x86)\Graphviz\bin\dot.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _cli_export_graph(xml_path: str, dot_out: str, svg_out: str) -> int:
    book = load_book(xml_path)
    book_dir = os.path.dirname(os.path.abspath(xml_path))

    dot_bin = _find_graphviz_dot_cli()
    if not dot_bin:
        print("ERROR: Graphviz dot not found", flush=True)
        return 2

    export_dot(book, book_dir, dot_out)
    subprocess.run([dot_bin, "-Tsvg", dot_out, "-o", svg_out], check=True)
    return 0


def main():
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--export-graph", action="store_true", help="Export DOT+SVG then exit")
    p.add_argument("--xml", help="Book XML path")
    p.add_argument("--dot", help="DOT output path")
    p.add_argument("--svg", help="SVG output path")
    args = p.parse_args()

    if args.export_graph:
        if not args.xml or not args.dot or not args.svg:
            print("ERROR: --xml --dot --svg are required with --export-graph", flush=True)
            raise SystemExit(2)
        raise SystemExit(_cli_export_graph(args.xml, args.dot, args.svg))

    app = AuthorTool()
    app.mainloop()


if __name__ == "__main__":
    main()