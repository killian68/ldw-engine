# LDW Engine

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Format](https://img.shields.io/badge/XML-formatVersion%201.1-orange)
![Status](https://img.shields.io/badge/status-active-brightgreen)
![GitHub release](https://img.shields.io/github/v/release/killian68/ldw-engine)

LDW Engine is an open-source Python engine for playing and authoring
paragraph-based interactive gamebooks (Fighting Fantasy–style).

The core philosophy is simple:

> The engine stays neutral.  
> The rules live in the XML ruleset.

------------------------------------------------------------------------

# ✨ Key Features

## Engine Core

- Paragraph navigation system
- Choice conditions & effects
- Inventory + flags
- Current stats + base (max) stats
- Centralized stat clamping:

        0 <= current_stat <= base_stat

## Declarative Rules (formatVersion 1.1)

- `<tests>` definitions (Luck tests, Skill tests, etc.)
- `<combatProfiles>` definitions
- `rulesRef` & `testRef` bindings
- Optional `allowFlee` per combat event
- Luck mappings fully ruleset-driven

## Character Creation

- Multiple profiles (classes)
- Dice expressions: `NdM`, `NdM+K`, `NdM-K`
- Initial effects (flags, items, stat modifiers)

------------------------------------------------------------------------

# 🖥 UI Layer (Tkinter Desktop)

- Animated dice widget
- Sound effects
- Image panel with interactive viewer
- Save/Load system
- Global application icon support (Windows / macOS / Linux)
- Navigation stack:
  - `previous`
  - `return`
  - `call:<pid>`

------------------------------------------------------------------------

# 🖼 Image Viewer

Modern interaction model:

- Mouse wheel → Zoom (centered on cursor)
- Left-click + drag → Pan
- Double-click → Fit to window
- Keyboard shortcuts:
  - `F` → Fit to window
  - `1` → 100% zoom

------------------------------------------------------------------------

# 🎨 Application Icons

LDW Engine includes multi-platform application icons.

### Included formats

- Windows → Multi-resolution `.ico` (16 → 256 px)
- macOS → `.icns`
- Linux → PNG variants (512 / 256 / 128)

### Implementation

- Centralized icon injection via `ui/icon.py`
- Automatically applied to:
  - Root Tk window
  - All `Toplevel` windows
- Compatible with PyInstaller bundles

------------------------------------------------------------------------

# 📊 Graph Viewer

The Author Tool includes an interactive SVG graph viewer.

Access:

    Edit tab → Graph (SVG)

## Architecture

The graph viewer runs in a **separate process** and starts a lightweight
local HTTP server.

    graph_viewer.py
        └── local HTTP server (127.0.0.1)
              ├── serves viewer.html
              ├── serves graph.svg
              └── exposes /api/refresh endpoint

This design:

- Avoids fragile GTK WebKit bindings on Linux
- Does not require WebKitGTK
- Does not require a specific Qt backend
- Works reliably on Windows and Linux
- Falls back automatically to the system browser if needed

## Features

- Interactive pan & zoom (svg-pan-zoom)
- Refresh button (rebuilds DOT + SVG)
- Reset / Fit view
- Separate process (no Tkinter mainloop conflicts)

CLI export:

    python author_tool.py --export-graph --xml <book.xml> --dot graph.dot --svg graph.svg

------------------------------------------------------------------------

# ✍ Author Tool Editing Model

- Paragraph list:
  - Green text → Saved / clean
  - Black text → Modified (dirty)
- You can navigate between paragraphs without losing edits
- Changes remain in memory until explicitly saved
- Saving writes XML and creates `.bak` backup

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

## Design Principles

- No hardcoded game mechanics
- Combat logic driven by `CombatProfile`
- Tests driven by `TestRule`
- XML validated before runtime use
- Graph viewer isolated for stability

------------------------------------------------------------------------

# 📄 XML Format (formatVersion="1.1")

Books must declare:

```xml
<book id="..." title="..." version="..." formatVersion="1.1">
```

------------------------------------------------------------------------

# 💾 Save System

Save files persist:

- Current paragraph
- Current stats
- Base stats
- Inventory
- Flags
- History stack
- Return stack

Save versioning allows forward compatibility handling.

------------------------------------------------------------------------

# 🚀 Running the Engine

## Core Requirements

- Python 3.8+
- Tkinter
- Pillow
- Graphviz (`dot` executable available in PATH)

------------------------------------------------------------------------

### Linux (Ubuntu / Debian)

System:

    sudo apt install python3-tk python3-pil.imagetk graphviz

Python:

    pip install pillow

Optional (embedded window instead of system browser):

    pip install pywebview pyside6 qtpy

By default, the Graph Viewer uses the system browser on Linux for maximum stability.

------------------------------------------------------------------------

### Windows

Install Graphviz and ensure `dot.exe` is available in PATH.

Verify:

    dot -V

Python:

    pip install pillow

Optional (embedded window):

    pip install pywebview pyside6 qtpy

No system-level Qt installation is required when using PySide6 from pip.

------------------------------------------------------------------------

## Run

    python main.py

------------------------------------------------------------------------

# 🤝 Contributing

Contributions are welcome.

Guidelines:

- Keep engine neutral
- Never hardcode specific ruleset behavior
- Maintain XML backward compatibility
- Update validation when adding attributes
- Update documentation when formatVersion changes

------------------------------------------------------------------------

# 🛣 Roadmap

- XML Schema (XSD)
- CLI validation tool
- Headless engine mode
- Web frontend
- Additional ruleset templates
- Automated tests (pytest)

------------------------------------------------------------------------

# ⚖ Legal Notice

This repository provides:

- A generic gamebook engine
- An XML authoring format
- An original example book

It does not include copyrighted commercial content.

Users are responsible for ensuring legal rights to loaded content.

------------------------------------------------------------------------

# 📜 License

MIT License

Copyright (c) 2026 Laurent Cachia
