from __future__ import annotations

import json
import os
import random
import re
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, filedialog

from engine.book_loader import load_book, resolve_image_path
from engine.models import GameState, Book, Paragraph, Choice, CombatSpec, TestSpec, CharacterProfile
from engine.rules import is_choice_available, apply_choice_effects, clamp_stats_non_negative
from engine.combat import CombatSession
from engine.tests import resolve_test_rule, run_test_with_roll, roll_expr as test_roll_expr

from ui.image_viewer import ImagePanel
from ui.dice_widget import DiceRoller
from ui.sfx import play_wav
from engine.validator import validate_book


DEFAULT_BOOK_PATH = os.path.join(os.path.dirname(__file__), "..", "examples", "sample_book.xml")

# UI assets live next to ui/ (stable)
UI_DIR = os.path.abspath(os.path.dirname(__file__))
UI_ASSETS_DIR = os.path.join(UI_DIR, "assets")
UI_DICE_DIR = os.path.join(UI_ASSETS_DIR, "dice")
UI_SFX_DIR = os.path.join(UI_ASSETS_DIR, "sfx")

SFX_ROLL = os.path.join(UI_SFX_DIR, "Roll.wav")
SFX_HIT = os.path.join(UI_SFX_DIR, "Grunting.wav")
SFX_TIE = os.path.join(UI_SFX_DIR, "Sword.wav")

SPECIAL_PREVIOUS = "previous"
SPECIAL_RETURN = "return"
CALL_PREFIX = "call:"
SAVE_VERSION = 2  # bumped: base_stats are now persisted

# NdM±K (e.g., 1d6+6, 2d6+12, 1d6-1, 2d6)
ROLL_EXPR_RE = re.compile(r"^\s*(\d+)\s*d\s*(\d+)\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)

# clamp these stats to [0..base_stats] via engine.rules.clamp_stats_non_negative
CLAMP_KEYS = ("stamina", "luck")


# -----------------------------
# Dice helpers (FF style)
# -----------------------------
_DICE_RE = re.compile(r"^\s*(\d+)\s*d\s*(\d+)\s*$", re.IGNORECASE)


def roll_expr(expr: str, rng: random.Random) -> int:
    """
    Supports NdM like '2d6'. Falls back to int(expr) if possible.
    Used as fallback when dice widget can't animate non-2d6 expressions.
    """
    m = _DICE_RE.match(expr or "")
    if m:
        n = int(m.group(1))
        sides = int(m.group(2))
        total = 0
        for _ in range(max(0, n)):
            total += rng.randint(1, max(1, sides))
        return total

    try:
        return int(expr)
    except Exception:
        return rng.randint(1, 6) + rng.randint(1, 6)


def parse_roll_expression(expr: str) -> tuple[int, int, int]:
    """
    Parse NdM±K and return (n, sides, offset).
    Raises ValueError if invalid.
    """
    m = ROLL_EXPR_RE.match(expr or "")
    if not m:
        raise ValueError(f"Invalid roll expression: {expr!r}")
    n = int(m.group(1))
    sides = int(m.group(2))
    offset = 0
    if m.group(3):
        offset = int(m.group(3).replace(" ", ""))
    return n, sides, offset


def _sfx_warn_if_missing(txt_widget: tk.Text) -> None:
    # Helpful debug without crashing
    if not os.path.exists(UI_DICE_DIR):
        txt_widget.insert("end", f"[WARN] UI dice dir not found: {UI_DICE_DIR}\n")
    for p in (SFX_ROLL, SFX_HIT, SFX_TIE):
        if not os.path.exists(p):
            txt_widget.insert("end", f"[WARN] UI sound not found: {p}\n")
    txt_widget.see("end")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LDW Engine (Python)")
        self.geometry("1200x780")

        self.book: Book | None = None
        self.book_dir: str = ""
        self.state: GameState | None = None

        self.rng = random.Random()

        self._build_menu()
        self._build_layout()

        self.load_book(DEFAULT_BOOK_PATH)

    # ---------- Menus ----------

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        self.config(menu=menubar)

        filem = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="File", menu=filem)

        filem.add_command(label="Open book XML...", command=self.open_book_dialog)
        filem.add_separator()
        filem.add_command(label="Save...", command=self.save_dialog)
        filem.add_command(label="Load save...", command=self.load_save_dialog)
        filem.add_separator()
        filem.add_command(label="Restart", command=self.restart_book)
        filem.add_separator()
        filem.add_command(label="Exit", command=self.destroy)

        charm = tk.Menu(menubar, tearoff=False)
        menubar.add_cascade(label="Character", menu=charm)
        charm.add_command(label="Re-roll character...", command=self.reroll_character_dialog)

    # ---------- Layout ----------

    def _build_layout(self) -> None:
        self.main = ttk.Frame(self)
        self.main.pack(fill="both", expand=True)

        self.main.columnconfigure(1, weight=1)
        self.main.rowconfigure(0, weight=1)

        # Stats panel (left)
        self.stats_frame = ttk.LabelFrame(self.main, text="Stats")
        self.stats_frame.grid(row=0, column=0, sticky="ns", padx=8, pady=8)

        self.stats_vars = {
            "skill": tk.StringVar(value="0"),
            "stamina": tk.StringVar(value="0"),
            "luck": tk.StringVar(value="0"),
        }

        # show max/base next to entries (read-only labels)
        self.stats_base_vars = {
            "skill": tk.StringVar(value=""),
            "stamina": tk.StringVar(value=""),
            "luck": tk.StringVar(value=""),
        }

        r = 0
        for k, var in self.stats_vars.items():
            ttk.Label(self.stats_frame, text=k.capitalize()).grid(row=r, column=0, sticky="w", padx=8, pady=6)
            ent = ttk.Entry(self.stats_frame, textvariable=var, width=8)
            ent.grid(row=r, column=1, sticky="e", padx=(8, 2), pady=6)

            ttk.Label(self.stats_frame, textvariable=self.stats_base_vars[k]).grid(
                row=r, column=2, sticky="w", padx=(2, 8), pady=6
            )
            r += 1

        ttk.Button(self.stats_frame, text="Apply", command=self.apply_stats_from_ui).grid(
            row=r, column=0, columnspan=3, pady=10, padx=8, sticky="ew"
        )

        # Center content
        self.center = ttk.Frame(self.main)
        self.center.grid(row=0, column=1, sticky="nsew", padx=8, pady=8)
        self.center.columnconfigure(0, weight=1)
        self.center.rowconfigure(0, weight=1)

        self.text_frame = ttk.Frame(self.center)
        self.text_frame.grid(row=0, column=0, sticky="nsew")
        self.text_frame.columnconfigure(0, weight=2)
        self.text_frame.columnconfigure(1, weight=1)
        self.text_frame.rowconfigure(0, weight=1)

        # Paragraph text + scrollbar
        self.text_box = tk.Text(self.text_frame, wrap="word")
        self.text_box.grid(row=0, column=0, sticky="nsew")

        yscroll = ttk.Scrollbar(self.text_frame, orient="vertical", command=self.text_box.yview)
        yscroll.grid(row=0, column=0, sticky="nse")
        self.text_box.configure(yscrollcommand=yscroll.set)
        self.text_box.configure(state="disabled")

        # Image panel (book illustrations)
        self.image_panel = ImagePanel(self.text_frame)
        self.image_panel.grid(row=0, column=1, sticky="nsew", padx=(12, 0))

        # Choices panel
        self.choices_frame = ttk.LabelFrame(self.center, text="Choices")
        self.choices_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.choices_frame.columnconfigure(0, weight=1)

        # Inventory panel (right)
        self.inv_frame = ttk.LabelFrame(self.main, text="Inventory")
        self.inv_frame.grid(row=0, column=2, sticky="ns", padx=8, pady=8)

        self.inv_list = tk.Listbox(self.inv_frame, height=25)
        self.inv_list.grid(row=0, column=0, columnspan=3, padx=8, pady=8, sticky="ns")

        ttk.Button(self.inv_frame, text="Add", command=self.inv_add).grid(row=1, column=0, padx=8, pady=6, sticky="ew")
        ttk.Button(self.inv_frame, text="Edit", command=self.inv_edit).grid(row=1, column=1, padx=8, pady=6, sticky="ew")
        ttk.Button(self.inv_frame, text="Remove", command=self.inv_remove).grid(row=1, column=2, padx=8, pady=6, sticky="ew")

    # ---------- Book lifecycle ----------

    def open_book_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Open book XML",
            filetypes=[("XML Files", "*.xml"), ("All Files", "*.*")]
        )
        if path:
            self.load_book(path)

    def _init_state_for_book(self) -> None:
        if not self.book:
            return
        stats = dict(self.book.ruleset.stat_defaults)
        self.state = GameState(
            current_paragraph=self.book.start_paragraph,
            stats=stats,
            base_stats=dict(stats),
            inventory=[],
            flags={}
        )
        self.state.history = []
        self.state.return_stack = []

    def load_book(self, xml_path: str) -> None:
        try:
            book = load_book(xml_path)

            # ✅ XML/ruleset validation (strict mode by default)
            # Use strict=False if you prefer warnings-only behavior.
            validate_book(book, strict=True)

        except Exception as e:
            messagebox.showerror("Load error", str(e))
            return

        self.book = book
        self.book_dir = os.path.dirname(os.path.abspath(xml_path))

        self._init_state_for_book()
        self.rng = random.Random()

        self._maybe_run_character_creation(on_load=True)

        self._sync_stats_to_ui()
        self._sync_inventory_to_ui()
        self.render_current_paragraph()

        self.title(f"LDW Engine — {book.title} (v{book.version})")

    def restart_book(self) -> None:
        if not self.book:
            return
        self._init_state_for_book()
        self.rng = random.Random()

        self._maybe_run_character_creation(on_load=True)

        self._sync_stats_to_ui()
        self._sync_inventory_to_ui()
        self.render_current_paragraph()

    # ---------- Save / Load ----------

    def _default_save_filename(self) -> str:
        if not self.book:
            return "savegame.json"

        safe_title = re.sub(r"[^a-zA-Z0-9_-]+", "_", self.book.title.strip())
        safe_title = safe_title.strip("_") or "book"
        return f"savegame_{safe_title}.json"

    def save_dialog(self) -> None:
        if not self.book or not self.state:
            return
        path = filedialog.asksaveasfilename(
            title="Save game",
            defaultextension=".json",
            initialfile=self._default_save_filename(),
            initialdir=self.book_dir or os.getcwd(),
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            self._save_to_file(path)
            messagebox.showinfo("Saved", f"Saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Save error", str(e))

    def load_save_dialog(self) -> None:
        path = filedialog.askopenfilename(
            title="Load save game",
            initialdir=self.book_dir or os.getcwd(),
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            self._load_from_file(path)
            messagebox.showinfo("Loaded", f"Loaded:\n{path}")
        except Exception as e:
            messagebox.showerror("Load error", str(e))

    def _save_to_file(self, path: str) -> None:
        if not self.book or not self.state:
            return
        data = {
            "save_version": SAVE_VERSION,
            "book_id": self.book.book_id,
            "book_version": self.book.version,
            "state": {
                "current_paragraph": self.state.current_paragraph,
                "stats": self.state.stats,
                "base_stats": getattr(self.state, "base_stats", {}),
                "inventory": self.state.inventory,
                "flags": self.state.flags,
                "history": list(getattr(self.state, "history", [])),
                "return_stack": list(getattr(self.state, "return_stack", [])),
            }
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_from_file(self, path: str) -> None:
        if not self.book:
            raise RuntimeError("No book loaded.")

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("book_id") != self.book.book_id:
            raise ValueError(
                f"Save is for a different book_id: {data.get('book_id')} (current: {self.book.book_id})"
            )

        s = data.get("state") or {}
        cur = str(s.get("current_paragraph") or self.book.start_paragraph)

        stats = dict(s.get("stats") or {})
        base_stats = dict(s.get("base_stats") or {}) or dict(stats)

        self.state = GameState(
            current_paragraph=cur,
            stats=stats,
            base_stats=base_stats,
            inventory=list(s.get("inventory") or []),
            flags=dict(s.get("flags") or {}),
        )
        self.state.history = list(s.get("history") or [])
        self.state.return_stack = list(s.get("return_stack") or [])

        self._clamp_core()
        self._sync_stats_to_ui()
        self._sync_inventory_to_ui()
        self.render_current_paragraph()

    # ---------- Character creation ----------

    def reroll_character_dialog(self) -> None:
        self._maybe_run_character_creation(on_load=False)
        self._sync_stats_to_ui()
        self._sync_inventory_to_ui()
        self.render_current_paragraph()

    def _maybe_run_character_creation(self, *, on_load: bool) -> None:
        if not self.book or not self.state:
            return

        cc = getattr(self.book.ruleset, "character_creation", None)
        if not cc or not getattr(cc, "profiles", None):
            return

        profiles: list[CharacterProfile] = list(cc.profiles)
        if not profiles:
            return

        default_pid = getattr(cc, "default_profile", None)
        default_index = 0
        if default_pid:
            for i, p in enumerate(profiles):
                if p.profile_id == default_pid:
                    default_index = i
                    break

        top = tk.Toplevel(self)
        top.title("Character Creation")
        top.geometry("820x520")
        top.minsize(720, 460)

        top.transient(self)
        top.grab_set()
        top.lift()
        top.attributes("-topmost", True)
        top.after(150, lambda: top.attributes("-topmost", False))
        top.focus_force()

        root = ttk.Frame(top)
        root.pack(fill="both", expand=True, padx=12, pady=12)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(2, weight=1)

        left = ttk.LabelFrame(root, text="Profile")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        left.columnconfigure(0, weight=1)

        sel_profile = tk.StringVar(value=profiles[default_index].profile_id)

        for p in profiles:
            ttk.Radiobutton(
                left,
                text=p.label or p.profile_id,
                value=p.profile_id,
                variable=sel_profile,
            ).pack(anchor="w", padx=10, pady=6)

        right = ttk.LabelFrame(root, text="Rolls")
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))
        right.columnconfigure(0, weight=1)

        rows_frame = ttk.Frame(right)
        rows_frame.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        rows_frame.columnconfigure(1, weight=1)

        bottom = ttk.Frame(root)
        bottom.grid(row=1, column=0, columnspan=2, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        bottom.columnconfigure(1, weight=1)
        bottom.columnconfigure(2, weight=1)

        roll_btn = ttk.Button(bottom, text="Roll")
        roll_btn.grid(row=0, column=0, sticky="w", padx=4)

        start_btn = ttk.Button(bottom, text="Start", state="disabled")
        start_btn.grid(row=0, column=2, sticky="e", padx=4)

        log = tk.Text(root, height=8, wrap="word")
        log.grid(row=2, column=0, columnspan=2, sticky="nsew")
        log.insert("end", "Choose a profile, then click Roll.\n")
        log.configure(state="disabled")

        def log_append(msg: str) -> None:
            log.configure(state="normal")
            log.insert("end", msg + "\n")
            log.see("end")
            log.configure(state="disabled")

        dice_widgets: dict[str, DiceRoller] = {}
        value_vars: dict[str, tk.StringVar] = {}

        def build_rows_for_profile(profile: CharacterProfile) -> None:
            for child in rows_frame.winfo_children():
                child.destroy()
            dice_widgets.clear()
            value_vars.clear()

            keys = list(profile.stat_rolls.keys())
            preferred = ["skill", "stamina", "luck"]
            ordered: list[str] = [k for k in preferred if k in profile.stat_rolls] + [k for k in keys if k not in preferred]

            if not ordered:
                ttk.Label(rows_frame, text="(No rolls defined for this profile)").grid(row=0, column=0, sticky="w")
                return

            for r, stat_id in enumerate(ordered):
                expr = profile.stat_rolls.get(stat_id, "").strip()

                ttk.Label(rows_frame, text=stat_id.upper()).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=6)
                ttk.Label(rows_frame, text=expr).grid(row=r, column=1, sticky="w", pady=6)

                dw = DiceRoller(rows_frame, UI_DICE_DIR, size_px=56)
                dw.grid(row=r, column=2, padx=8, pady=2)
                dice_widgets[stat_id] = dw

                v = tk.StringVar(value="—")
                value_vars[stat_id] = v
                ttk.Label(rows_frame, textvariable=v, width=8).grid(row=r, column=3, sticky="e", pady=6)

        def get_selected_profile() -> CharacterProfile:
            pid = sel_profile.get()
            for p in profiles:
                if p.profile_id == pid:
                    return p
            return profiles[default_index]

        build_rows_for_profile(get_selected_profile())

        def on_profile_changed(*_args):
            build_rows_for_profile(get_selected_profile())
            start_btn.config(state="disabled")

        sel_profile.trace_add("write", on_profile_changed)

        rolled_values: dict[str, int] = {}
        rolled_profile: CharacterProfile | None = None

        def do_roll():
            nonlocal rolled_profile, rolled_values
            rolled_profile = get_selected_profile()
            rolled_values = {}
            start_btn.config(state="disabled")

            if not rolled_profile.stat_rolls:
                messagebox.showerror("Roll error", "This profile has no roll definitions.")
                return

            specs: dict[str, tuple[int, int, int]] = {}
            for stat_id, expr in rolled_profile.stat_rolls.items():
                try:
                    specs[stat_id] = parse_roll_expression(expr)
                except Exception as e:
                    messagebox.showerror("Roll error", f"{stat_id}: {e}")
                    return

            play_wav(SFX_ROLL)
            log_append(f"Rolling for profile: {rolled_profile.label or rolled_profile.profile_id}")

            pending = {"n": 0}

            def finish_if_done():
                if pending["n"] <= 0:
                    for sid, val in rolled_values.items():
                        if sid in value_vars:
                            value_vars[sid].set(str(val))
                    log_append("Done. Click Start to begin.")
                    start_btn.config(state="normal")

            for stat_id, (n, sides, offset) in specs.items():
                expr = rolled_profile.stat_rolls[stat_id]

                if stat_id not in dice_widgets:
                    rolled_values[stat_id] = roll_expr(f"{n}d{sides}", self.rng) + offset
                    continue

                if n == 2 and sides == 6:
                    pending["n"] += 1

                    def on_done_factory(sid: str, off: int):
                        def _done(total_2d6: int):
                            rolled_values[sid] = int(total_2d6) + int(off)
                            pending["n"] -= 1
                            finish_if_done()
                        return _done

                    dice_widgets[stat_id].animate_and_lock(self.rng, on_done=on_done_factory(stat_id, offset))
                    log_append(f"  {stat_id.upper()}: {expr}")

                elif n == 1 and sides == 6:
                    rolled_values[stat_id] = self.rng.randint(1, 6) + offset
                    pending["n"] += 1

                    def _done_ignore(_total: int):
                        pending["n"] -= 1
                        finish_if_done()

                    dice_widgets[stat_id].animate_and_lock(self.rng, on_done=_done_ignore)
                    log_append(f"  {stat_id.upper()}: {expr}")

                else:
                    rolled_values[stat_id] = roll_expr(f"{n}d{sides}", self.rng) + offset
                    pending["n"] += 1

                    def _done_ignore(_total: int):
                        pending["n"] -= 1
                        finish_if_done()

                    dice_widgets[stat_id].animate_and_lock(self.rng, on_done=_done_ignore)
                    log_append(f"  {stat_id.upper()}: {expr}  -> fallback roll")

            if pending["n"] == 0:
                finish_if_done()

        def apply_and_close():
            nonlocal rolled_profile, rolled_values
            if not self.state:
                top.destroy()
                return
            if not rolled_profile or not rolled_values:
                messagebox.showinfo("Roll first", "Click Roll first.")
                return

            # Apply rolled stats to CURRENT and BASE (initial/max)
            for sid, val in rolled_values.items():
                self.state.stats[sid] = int(val)
                self.state.base_stats[sid] = int(val)

            # Apply profile effects (CURRENT only)
            for eff in rolled_profile.effects:
                if eff.add_item:
                    self.state.inventory.append(eff.add_item)
                if eff.remove_item:
                    target = eff.remove_item.strip().lower()
                    for i, line in enumerate(self.state.inventory):
                        if target in line.strip().lower():
                            self.state.inventory.pop(i)
                            break
                if eff.set_flag:
                    self.state.flags[eff.set_flag] = True
                if eff.clear_flag:
                    self.state.flags[eff.clear_flag] = False
                if eff.modify_stat:
                    for k, delta in eff.modify_stat.items():
                        self.state.stats[k] = int(self.state.stats.get(k, 0)) + int(delta)

            self._clamp_core()
            self._sync_stats_to_ui()
            self._sync_inventory_to_ui()
            top.destroy()

        top.protocol("WM_DELETE_WINDOW", lambda: top.destroy())

        roll_btn.config(command=do_roll)
        start_btn.config(command=apply_and_close)

        self.wait_window(top)

    # ---------- Navigation helpers ----------

    def _goto(self, target: str, *, push_history: bool = True) -> None:
        if not self.state:
            return

        t = (target or "").strip()
        if not t:
            return

        if t.startswith(CALL_PREFIX):
            real_target = t.split(":", 1)[1].strip()
            if not real_target:
                return
            self.state.return_stack.append(self.state.current_paragraph)
            self.state.current_paragraph = real_target
            self.render_current_paragraph()
            return

        if t == SPECIAL_PREVIOUS:
            self._go_previous()
            return

        if t == SPECIAL_RETURN:
            self._go_return()
            return

        if push_history:
            cur = (self.state.current_paragraph or "").strip()
            if cur:
                self.state.history.append(cur)

        self.state.current_paragraph = t
        self.render_current_paragraph()

    def _go_previous(self) -> None:
        if not self.state:
            return
        if not self.state.history:
            messagebox.showinfo("Back", "No previous paragraph in history.")
            return
        self.state.current_paragraph = self.state.history.pop()
        self.render_current_paragraph()

    def _go_return(self) -> None:
        if not self.state:
            return
        if self.state.return_stack:
            self.state.current_paragraph = self.state.return_stack.pop()
            self.render_current_paragraph()
            return
        self._go_previous()

    # ---------- Clamp (centralized in engine.rules) ----------

    def _clamp_core(self) -> None:
        if not self.state:
            return
        clamp_stats_non_negative(self.state, keys=CLAMP_KEYS)

    # ---------- UI actions ----------

    def apply_stats_from_ui(self) -> None:
        if not self.state:
            return
        for k, var in self.stats_vars.items():
            try:
                self.state.stats[k] = int(var.get())
            except ValueError:
                pass
        self._clamp_core()
        self._sync_stats_to_ui()
        self.render_current_paragraph()

    def inv_add(self) -> None:
        if not self.state:
            return
        val = simpledialog.askstring("Add item", "Item text:")
        if val:
            self.state.inventory.append(val.strip())
            self._sync_inventory_to_ui()
            self.render_current_paragraph()

    def inv_edit(self) -> None:
        if not self.state:
            return
        sel = self.inv_list.curselection()
        if not sel:
            return
        idx = sel[0]
        current = self.state.inventory[idx]
        val = simpledialog.askstring("Edit item", "Item text:", initialvalue=current)
        if val is not None:
            self.state.inventory[idx] = val.strip()
            self._sync_inventory_to_ui()
            self.render_current_paragraph()

    def inv_remove(self) -> None:
        if not self.state:
            return
        sel = self.inv_list.curselection()
        if not sel:
            return
        self.state.inventory.pop(sel[0])
        self._sync_inventory_to_ui()
        self.render_current_paragraph()

    # ---------- Rendering ----------

    def render_current_paragraph(self) -> None:
        if not self.book or not self.state:
            return

        para = self.book.paragraphs.get(self.state.current_paragraph)
        if not para:
            messagebox.showerror("Error", f"Paragraph not found: {self.state.current_paragraph}")
            return

        self.text_box.configure(state="normal")
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", f"[{para.pid}]\n\n{para.text}")
        self.text_box.configure(state="disabled")

        img_path = None
        if para.image_ref:
            img_path = resolve_image_path(self.book_dir, self.book.assets, para.image_ref)
        self.image_panel.set_image(img_path)

        if para.events and self._handle_events(para):
            return

        self._render_choices(para)

    def _render_choices(self, para: Paragraph) -> None:
        for child in self.choices_frame.winfo_children():
            child.destroy()

        if not self.state:
            return

        available_choices: list[Choice] = [c for c in para.choices if is_choice_available(self.state, c)]

        if not available_choices:
            ttk.Label(self.choices_frame, text="(No available choices)").grid(
                row=0, column=0, sticky="w", padx=10, pady=10
            )
            return

        for i, choice in enumerate(available_choices):
            ttk.Button(self.choices_frame, text=choice.label, command=lambda ch=choice: self.on_choice(ch)).grid(
                row=i, column=0, sticky="ew", padx=10, pady=6
            )

    def on_choice(self, choice: Choice) -> None:
        if not self.state:
            return
        apply_choice_effects(self.state, choice)
        self._clamp_core()
        self._sync_stats_to_ui()
        self._sync_inventory_to_ui()
        self._goto(choice.target, push_history=True)

    # ---------- Events ----------

    def _handle_events(self, para: Paragraph) -> bool:
        if not self.state:
            return False
        for ev in para.events:
            if ev.type == "combat":
                return self._run_combat(ev.payload)
            if ev.type == "test":
                return self._run_test(ev.payload)
        return False

    # ---------- Combat ----------

    def _run_combat(self, spec: CombatSpec) -> bool:
        if not self.state or not self.book:
            return False

        session = CombatSession(self.state, spec, self.rng, ruleset=self.book.ruleset)

        top = tk.Toplevel(self)
        top.title("Combat")
        top.geometry("900x660")
        top.minsize(700, 520)

        root = ttk.Frame(top)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        # --- Options row (Luck / Flee) ---
        options_row = ttk.Frame(root)
        options_row.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        options_row.columnconfigure(0, weight=1)
        options_row.columnconfigure(1, weight=1)

        use_luck_var = tk.BooleanVar(value=False)

        luck_supported = getattr(session.profile, "luck", None) is not None
        flee_supported = getattr(session.profile, "flee", None) is not None
        flee_allowed = bool(getattr(spec, "allow_flee", False))

        luck_cb = ttk.Checkbutton(
            options_row,
            text="Use Luck (Test your Luck) when applicable",
            variable=use_luck_var
        )
        luck_cb.grid(row=0, column=0, sticky="w")
        if not luck_supported:
            luck_cb.state(["disabled"])

        flee_btn = ttk.Button(options_row, text="Flee", state="disabled")
        flee_btn.grid(row=0, column=1, sticky="e")
        if flee_supported and flee_allowed:
            flee_btn.config(state="normal")

        # --- Dice row ---
        dice_row = ttk.Frame(root)
        dice_row.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))
        dice_row.columnconfigure(0, weight=1)
        dice_row.columnconfigure(1, weight=1)

        player_box = ttk.LabelFrame(dice_row, text="You (2d6)")
        enemy_box = ttk.LabelFrame(dice_row, text=f"{spec.enemy_name} (2d6)")
        player_box.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        enemy_box.grid(row=0, column=1, sticky="ew")

        dice_player = DiceRoller(player_box, UI_DICE_DIR, size_px=72)
        dice_enemy = DiceRoller(enemy_box, UI_DICE_DIR, size_px=72)
        dice_player.pack(padx=6, pady=6)
        dice_enemy.pack(padx=6, pady=6)

        # --- Log text ---
        txt_frame = ttk.Frame(root)
        txt_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 6))
        txt_frame.columnconfigure(0, weight=1)
        txt_frame.rowconfigure(0, weight=1)

        txt = tk.Text(txt_frame, wrap="word")
        txt.grid(row=0, column=0, sticky="nsew")

        ybar = ttk.Scrollbar(txt_frame, orient="vertical", command=txt.yview)
        ybar.grid(row=0, column=1, sticky="ns")
        txt.configure(yscrollcommand=ybar.set)

        txt.insert("end", "\n".join(session.start_log()) + "\n")
        txt.see("end")

        # --- Buttons ---
        btn_bar = ttk.Frame(root)
        btn_bar.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        btn_bar.columnconfigure(0, weight=1)

        roll_btn = ttk.Button(btn_bar, text="Roll next round")
        roll_btn.grid(row=0, column=0, sticky="w")

        continue_btn = ttk.Button(btn_bar, text="Continue", state="disabled")
        continue_btn.grid(row=0, column=1, sticky="e")

        def _close_as_lose():
            top.destroy()
            self._sync_stats_to_ui()
            self._goto(spec.on_lose_goto, push_history=True)

        top.protocol("WM_DELETE_WINDOW", _close_as_lose)

        def roll_round():
            if session.finished:
                return

            _sfx_warn_if_missing(txt)
            play_wav(SFX_ROLL)
            roll_btn.config(state="disabled")

            results: dict[str, int] = {"p": 0, "e": 0}

            def maybe_continue():
                if results["p"] and results["e"]:
                    logs = session.roll_round(use_luck=bool(use_luck_var.get()))
                    if logs:
                        txt.insert("end", "\n".join(logs) + "\n")
                        txt.see("end")

                    info = session.last_round()
                    if info:
                        if info.damage_to_enemy == 0 and info.damage_to_player == 0:
                            play_wav(SFX_TIE)
                        else:
                            play_wav(SFX_HIT)

                    self._clamp_core()
                    self._sync_stats_to_ui()

                    if session.finished:
                        continue_btn.config(state="normal")
                        roll_btn.config(state="disabled")
                    else:
                        roll_btn.config(state="normal")

            def done_player(total: int):
                results["p"] = total
                maybe_continue()

            def done_enemy(total: int):
                results["e"] = total
                maybe_continue()

            dice_player.animate_and_lock(self.rng, on_done=done_player)
            dice_enemy.animate_and_lock(self.rng, on_done=done_enemy)

        def do_flee():
            if session.finished:
                return
            _sfx_warn_if_missing(txt)
            play_wav(SFX_ROLL)

            logs = session.flee(use_luck=bool(use_luck_var.get()))
            if logs:
                txt.insert("end", "\n".join(logs) + "\n")
                txt.see("end")

            self._clamp_core()
            self._sync_stats_to_ui()

            continue_btn.config(state="normal")
            roll_btn.config(state="disabled")

        flee_btn.config(command=do_flee)
        roll_btn.config(command=roll_round)

        def finish():
            top.destroy()
            next_pid = spec.on_win_goto if session.won else spec.on_lose_goto
            self._sync_stats_to_ui()
            self._goto(next_pid, push_history=True)

        continue_btn.config(command=finish)

        return True

    # ---------- Test (ruleset-driven) ----------

    def _run_test(self, spec: TestSpec) -> bool:
        if not self.state or not self.book:
            return False

        ruleset = self.book.ruleset
        rule = resolve_test_rule(ruleset, getattr(spec, "test_ref", None))

        # Dice/stat come from rule first, fallback to spec (strict books will usually be rule-driven)
        dice_expr = (rule.dice if rule and rule.dice else (spec.dice or "2d6")).strip()
        stat_id = (rule.stat if rule and rule.stat else spec.stat_id).strip()

        top = tk.Toplevel(self)
        top.title(f"Test: {stat_id}")
        top.geometry("760x520")
        top.minsize(520, 360)

        root = ttk.Frame(top)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        txt = tk.Text(root, wrap="word")
        txt.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 6))

        ybar = ttk.Scrollbar(root, orient="vertical", command=txt.yview)
        ybar.grid(row=0, column=1, sticky="ns", pady=(10, 6))
        txt.configure(yscrollcommand=ybar.set)

        dice_widget = DiceRoller(root, UI_DICE_DIR, size_px=84)
        dice_widget.grid(row=1, column=0, columnspan=2, pady=(0, 6))

        btn_bar = ttk.Frame(root)
        btn_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 10))
        btn_bar.columnconfigure(0, weight=1)

        roll_btn = ttk.Button(btn_bar, text="Roll")
        roll_btn.grid(row=0, column=0, sticky="w")

        continue_btn = ttk.Button(btn_bar, text="Continue", state="disabled")
        continue_btn.grid(row=0, column=1, sticky="e")

        result = {"done": False, "success": False}

        def _close_as_fail():
            if not result["done"]:
                result["done"] = True
                result["success"] = False
            top.destroy()
            self._sync_stats_to_ui()
            self._goto(spec.fail_goto, push_history=True)

        top.protocol("WM_DELETE_WINDOW", _close_as_fail)

        stat_val = int(self.state.stats.get(stat_id, 0))
        txt.insert("end", f"Testing {stat_id.upper()} ({stat_val})\n")
        txt.insert("end", f"Roll: {dice_expr}\n\n")
        txt.insert("end", "Click 'Roll' to throw the dice.\n\n")
        txt.see("end")

        def _apply_outcome(outcome) -> None:
            result["done"] = True
            result["success"] = bool(outcome.success)

            txt.insert("end", f"You rolled {outcome.roll_total} against {outcome.stat_before} -> ")
            txt.insert("end", "SUCCESS\n" if outcome.success else "FAILURE\n")

            if outcome.consumed:
                txt.insert(
                    "end",
                    f"{outcome.stat_id.upper()} decreases by {outcome.consumed}. Now: {outcome.stat_after}\n"
                )

            txt.see("end")
            self._clamp_core()
            self._sync_stats_to_ui()
            continue_btn.config(state="normal")

        def do_roll():
            if result["done"]:
                return

            _sfx_warn_if_missing(txt)
            play_wav(SFX_ROLL)
            roll_btn.config(state="disabled")

            # 2d6 -> animate, then apply pre-rolled total (NO double-roll)
            if dice_expr.lower() == "2d6":
                def after_roll(total: int):
                    outcome = run_test_with_roll(
                        self.state,
                        ruleset=ruleset,
                        test_ref=getattr(spec, "test_ref", None),
                        stat_id=stat_id,
                        success_if="roll<=stat",
                        consume_on_success=spec.consume_on_success,
                        consume_on_fail=spec.consume_on_fail,
                        roll_total=int(total),
                        roll_detail=(),
                    )
                    _apply_outcome(outcome)

                dice_widget.animate_and_lock(self.rng, on_done=after_roll)
                return

            # Other dice (NdM±K) -> roll in engine.tests (supports offset), no animation
            total, detail = test_roll_expr(dice_expr, self.rng)
            outcome = run_test_with_roll(
                self.state,
                ruleset=ruleset,
                test_ref=getattr(spec, "test_ref", None),
                stat_id=stat_id,
                success_if="roll<=stat",
                consume_on_success=spec.consume_on_success,
                consume_on_fail=spec.consume_on_fail,
                roll_total=int(total),
                roll_detail=tuple(int(x) for x in detail),
            )
            _apply_outcome(outcome)

        def finish():
            if not result["done"]:
                messagebox.showinfo("Roll first", "Click 'Roll' first.")
                return
            top.destroy()
            next_pid = spec.success_goto if result["success"] else spec.fail_goto
            self._sync_stats_to_ui()
            self._goto(next_pid, push_history=True)

        roll_btn.config(command=do_roll)
        continue_btn.config(command=finish)

        return True

    # ---------- Sync helpers ----------

    def _sync_inventory_to_ui(self) -> None:
        if not self.state:
            return
        self.inv_list.delete(0, "end")
        for line in self.state.inventory:
            self.inv_list.insert("end", line)

    def _sync_stats_to_ui(self) -> None:
        if not self.state:
            return
        for k, var in self.stats_vars.items():
            var.set(str(int(self.state.stats.get(k, 0))))
            base = int(self.state.base_stats.get(k, self.state.stats.get(k, 0)))
            self.stats_base_vars[k].set(f"/ {base}" if base else "")


def run_app() -> None:
    app = App()
    app.mainloop()