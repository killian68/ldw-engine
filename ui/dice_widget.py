import os
import random
import tkinter as tk
from tkinter import ttk
from typing import List

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


class DiceRoller(ttk.Frame):
    """
    DiceRoller: animated d6 roller.
    - Supports 1 or 2 visible dice (num_dice=1 or 2).
    - Can still compute totals for any num_dice, but UI displays max 2 dice.
    """

    def __init__(self, master, dice_dir: str, size_px: int = 96):
        super().__init__(master)

        self.dice_dir = dice_dir
        self.size_px = size_px
        self._photos = {}

        self.die1 = ttk.Label(self)
        self.die2 = ttk.Label(self)
        self.total_lbl = ttk.Label(self, font=("Segoe UI", 12, "bold"))

        self.die1.grid(row=0, column=0, padx=6, pady=6)
        self.die2.grid(row=0, column=1, padx=6, pady=6)
        self.total_lbl.grid(row=1, column=0, columnspan=2)

        self._load_images()

    def _load_images(self):
        if not PIL_AVAILABLE:
            self.die1.configure(text="d6")
            self.die2.configure(text="d6")
            return

        for face in range(1, 7):
            path = os.path.join(self.dice_dir, f"{face}.png")
            if os.path.exists(path):
                img = Image.open(path)
                img = img.resize((self.size_px, self.size_px))
                self._photos[face] = ImageTk.PhotoImage(img)

    def _set_die_face(self, label: ttk.Label, face: int):
        if PIL_AVAILABLE and face in self._photos:
            label.configure(image=self._photos[face], text="")
        else:
            label.configure(text=str(face))

    def _set_faces(self, faces: List[int], num_dice: int):
        """
        Update UI for 1 or 2 visible dice, and total label.
        faces: list of rolled faces (length = num_dice, can be >2 but only first 2 displayed)
        """
        num_dice = max(1, int(num_dice))

        a = faces[0] if len(faces) >= 1 else 1
        b = faces[1] if len(faces) >= 2 else 1

        self._set_die_face(self.die1, a)

        if num_dice >= 2:
            self.die2.grid()  # ensure visible
            self._set_die_face(self.die2, b)
            total = sum(faces)
            self.total_lbl.configure(text="Total: %d" % total)
        else:
            self.die2.grid_remove()
            total = a
            self.total_lbl.configure(text="Total: %d" % total)

    def animate_and_lock(
        self,
        rng: random.Random,
        duration_ms: int = 700,
        tick_ms: int = 60,
        on_done=None,
        num_dice: int = 2,
        sides: int = 6,
    ):
        """
        Animate and lock a roll.
        - num_dice: number of dice to roll (int)
        - sides: number of sides (only 6 supported for images; others fallback to text)
        Calls on_done(total) at the end if provided.
        """
        num_dice = max(1, int(num_dice))
        sides = max(2, int(sides))

        steps = max(1, duration_ms // max(1, tick_ms))
        state = {"i": 0}

        final_faces = [rng.randint(1, sides) for _ in range(num_dice)]
        final_total = sum(final_faces)

        def tick():
            if state["i"] < steps:
                faces = [rng.randint(1, sides) for _ in range(num_dice)]
                self._set_faces(faces, num_dice=num_dice)
                state["i"] += 1
                self.after(tick_ms, tick)
            else:
                self._set_faces(final_faces, num_dice=num_dice)
                if on_done:
                    on_done(final_total)

        tick()