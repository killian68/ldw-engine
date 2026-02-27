# LDW Engine

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Format](https://img.shields.io/badge/XML-formatVersion%201.1-orange)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![GitHub release](https://img.shields.io/github/v/release/killian68/ldw-engine)

LDW Engine is an open-source Python engine for playing and authoring
paragraph-based interactive gamebooks (Fighting Fantasy--style).

The core philosophy is simple:

> The engine stays neutral.\
> The rules live in the XML ruleset.

------------------------------------------------------------------------

# ✨ Key Features

## Engine Core

-   Paragraph navigation system

-   Choice conditions & effects

-   Inventory + flags

-   Current stats + base (max) stats

-   Centralized stat clamping:

          0 <= current_stat <= base_stat

## Declarative Rules (formatVersion 1.1)

-   `<tests>` definitions (Luck tests, Skill tests, etc.)
-   `<combatProfiles>` definitions
-   `rulesRef` & `testRef` bindings
-   Optional `allowFlee` per combat event
-   Luck mappings fully ruleset-driven

## Character Creation

-   Multiple profiles (classes)
-   Dice expressions: `NdM`, `NdM+K`, `NdM-K`
-   Initial effects (flags, items, stat modifiers)

------------------------------------------------------------------------

# 🖥 UI Layer (Tkinter Desktop)

-   Animated dice widget
-   Sound effects
-   Image panel with interactive viewer
-   Save/Load system
-   Global application icon support (Windows / macOS / Linux)
-   Navigation stack:
    -   `previous`
    -   `return`
    -   `call:<pid>`

## 🖼 Image Viewer (v1.2.0)

The image viewer now includes modern interaction:

-   Mouse wheel → Zoom (centered on cursor)
-   Left-click + drag → Pan
-   Double-click → Fit to window
-   Keyboard shortcuts:
    -   `F` → Fit to window
    -   `1` → 100% zoom

This behavior matches modern design tools and image viewers.

------------------------------------------------------------------------

# 🎨 Application Icons (v1.2.0)

LDW Engine now includes professional multi-platform application icons.

### Included formats

-   **Windows** → Multi-resolution `.ico` (16 → 256 px)
-   **macOS** → `.icns`
-   **Linux** → PNG variants (512 / 256 / 128)

### Implementation

-   Centralized icon injection via `ui/icon.py`
-   Automatically applied to:
    -   Root Tk window
    -   All `Toplevel` windows
-   No UI duplication required

This ensures consistent branding and clean desktop integration across
platforms.

------------------------------------------------------------------------

# 📊 Graph Viewer (New in v1.2.0)

The Author Tool now includes an interactive graph viewer.

Access it via:

Edit tab → **Graph (SVG)**

Features:

-   Embedded SVG viewer (pywebview-based)
-   Interactive zoom & pan
-   Double-click fit
-   Refresh button to re-export DOT + SVG
-   Runs in a separate process to avoid Tkinter mainloop conflicts

The graph export can also be used via CLI:

    python author_tool.py --export-graph --xml <book.xml> --dot graph.dot --svg graph.svg

------------------------------------------------------------------------

# 🏗 Architecture Overview

LDW Engine is layered:

    Book XML
       │
       ▼
    Book Loader (validation + parsing)
       │
       ▼
    Engine Models (Ruleset, CombatProfile, TestRule, etc.)
       │
       ▼
    Runtime State (GameState)
       │
       ▼
    UI Layer (Tkinter)
       ├── author_tool.py
       ├── image_viewer.py
       └── graph_viewer.py

## Design Principle

-   No hardcoded game mechanics
-   Combat logic is driven by `CombatProfile`
-   Tests are driven by `TestRule`
-   XML is validated before runtime use
-   Graph viewer runs in isolated process for stability

------------------------------------------------------------------------

# 📄 XML Format (formatVersion="1.1")

Books must declare:

``` xml
<book id="..." title="..." version="..." formatVersion="1.1">
```

## Ruleset

``` xml
<ruleset name="ff_basic">
  <dice sides="6"/>
  <tests>...</tests>
  <combatProfiles>...</combatProfiles>
</ruleset>
```

## Declarative Test Example

``` xml
<test id="luck_test"
      stat="luck"
      dice="2d6"
      successIf="roll<=stat"
      consume="1" />
```

## Declarative Combat Example

``` xml
<combat id="ff_classic">
  <attack dice="2d6" stat="skill" />
  <damage base="2" />
  <luck testRef="luck_test">
    <onPlayerHit successDamage="4" failDamage="1" />
    <onPlayerHurt successDamage="1" failDamage="3" />
  </luck>
  <flee baseDamage="2" luckLike="onPlayerHurt" />
</combat>
```

## Event Binding

``` xml
<event type="combat"
       rulesRef="ff_classic"
       allowFlee="1"
       enemyName="Bandit"
       enemySkill="8"
       enemyStamina="10"
       onWin="20"
       onLose="900" />
```

------------------------------------------------------------------------

# 💾 Save System

Save files persist:

-   Current paragraph
-   Current stats
-   Base stats
-   Inventory
-   Flags
-   History stack
-   Return stack

Save versioning allows forward compatibility handling.

------------------------------------------------------------------------

# 🔎 Strict XML Validation

Recommended workflow:

1.  Validate XML before loading
2.  Fail fast on structural errors
3.  Ensure referenced `rulesRef` and `testRef` exist

The project includes a validator module for strict checking.

------------------------------------------------------------------------

# 🚀 Running the Engine

## Requirements

- Python 3.8+
- Tkinter
- Pillow
- pywebview (for graph viewer)
- Qt backend (PySide6 + QtWebEngine)
- Graphviz (`dot` executable available in PATH)

---

### Linux (Ubuntu / Debian)

#### System dependencies

    sudo apt install python3-tk python3-pil.imagetk graphviz \
                     libxcb-cursor0

Notes:

- `libxcb-cursor0` is required by Qt ≥ 6.5 when using the XCB platform plugin.
- WebKitGTK is no longer required (Qt backend is now used for the Graph Viewer).

---

#### Python dependencies

    pip install pillow pywebview pyside6 qtpy

The Graph Viewer uses the Qt backend (PySide6) via `pywebview`.

The application forces `QT_API=pyside6` internally to prevent accidental
fallback to PyQt5 if it is installed on the system.

---

#### GNOME / Wayland

If Qt fails to start under Wayland (GNOME), force the XCB platform plugin:

    export QT_QPA_PLATFORM=xcb

To make this persistent:

    echo 'export QT_QPA_PLATFORM=xcb' >> ~/.bashrc

This only affects Qt applications launched from your user session and
does not modify the system display manager.

---

### Windows

#### System dependencies

Install **Graphviz** and ensure `dot.exe` is available in your system `PATH`.

You can verify:

    dot -V

---

#### Python dependencies

    pip install pillow pywebview pyside6 qtpy

The Graph Viewer uses the Qt backend (PySide6) via `pywebview`.

`qtpy` is required to ensure consistent Qt binding selection.

No additional system-level Qt installation is required on Windows
when using PySide6 from pip.

---

### Notes

- The Graph Viewer uses Qt (via PySide6) as the WebView backend.
- WebKitGTK is no longer required.
- On Linux, Qt may require `libxcb-cursor0` when using the XCB platform plugin.
- JavaScript console warnings about passive event listeners are harmless.

---

## Run

    python main.py

------------------------------------------------------------------------

# 🤝 Contributing

Contributions are welcome.

Guidelines:

-   Keep engine neutral
-   Never hardcode specific ruleset behavior
-   Maintain XML backward compatibility
-   Update validation when adding attributes
-   Update documentation when formatVersion changes

------------------------------------------------------------------------

# 🛣 Roadmap

-   XML Schema (XSD)
-   CLI validation tool
-   Headless engine mode
-   Web frontend
-   Additional ruleset templates
-   Automated tests (pytest)

------------------------------------------------------------------------

# ⚖ Legal Notice

This repository provides:

-   A generic gamebook engine
-   An XML authoring format
-   An original example book

It does not include copyrighted commercial content.

Users are responsible for ensuring legal rights to loaded content.

------------------------------------------------------------------------

# 📜 License

MIT License

Copyright (c) 2026 Laurent Cachia
