# Author Tool (Book Inspector)

The **LDW Author Tool** is a Tkinter desktop utility for inspecting, editing, and validating LDW XML gamebooks.
It is intended for **authors and maintainers**, not for players.

It loads a book using the same parser as the engine (`engine.book_loader.load_book`) and provides:

- full paragraph editing (text, choices, events, modifiers)
- link graph inspection (incoming/outgoing)
- interactive graph viewer (SVG)
- asset management (import/link/unlink/delete + preview)
- full-text search across paragraphs
- validation report (errors/warnings/info)
- graph export to Graphviz DOT (and optional SVG)

The tool is **non-destructive by default**, and when it edits XML it automatically creates a `.bak` backup.

---

## Where it lives

The tool is implemented as a standalone Tkinter app:

- `author_tool.py`
- `ui/graph_viewer.py` (separate process viewer for SVG graphs)
- `ui/image_viewer.py` (interactive image preview)

It can be launched directly:

```bash
python author_tool.py
```

The tool loads books from:

- `<racine>/livres/`

---

# Features by Tab

## 1) Edit

Purpose: full paragraph editing.

Includes:

- Paragraph list (with filter by ID or text)
- Text editor
- Choices editor (add/edit/remove)
- Combat event editor
- Test event editor
- Environment modifiers (`envEffect`) editor
- Add/Delete paragraph
- Safe save with automatic `.bak` backup

Graph integration:

- **Graph (SVG)** button
  - Exports DOT
  - Generates SVG via Graphviz
  - Launches interactive Graph Viewer
  - Supports zoom, pan, and refresh

The XML is rewritten safely on each save.

---

## 2) Links

Purpose: inspect the link graph around a paragraph.

Shows:

- **Outgoing** targets (choices + event gotos)
- **Incoming** sources linking to the paragraph

Tools:

- **Export DOT...**
- **Export DOT + SVG**
- Graph building via `engine.validate.build_link_index`

---

## 3) Assets

Purpose: manage `<assets>` declarations and paragraph image links.

Displays a table of:

- `asset_id`
- `file`
- `exists`
- `used_by`

Selecting an asset:

- displays resolved path
- previews image (if Pillow installed)

Buttons:

- Add Asset
- Import & link image
- Link selected asset
- Remove link
- Delete selected asset

All operations create automatic `.bak` backups before writing XML.

---

## 4) Search

Purpose: full-text search across paragraph text.

Selecting a result:

- previews snippet
- selects paragraph in Edit tab
- synchronizes with Links tab

---

## 5) Validation

Purpose: run book validation using engine validator.

Uses:

- `engine.validate.validate_book(book, book_dir)`

Displays:

- Errors
- Warnings
- Info

Selecting an issue jumps to the related paragraph.

---

# Graph Viewer (v1.2.0)

The Graph Viewer is isolated from the main Tkinter process.

Architecture:

- DOT export via engine
- SVG generated via Graphviz
- Viewer launched as separate subprocess
- Interactive via `pywebview`

Features:

- Mouse wheel zoom
- Left-click + drag pan
- Double-click fit
- Refresh button re-exports graph via CLI

CLI export mode:

```bash
python author_tool.py --export-graph --xml <book.xml> --dot graph.dot --svg graph.svg
```

This allows reuse in automation or scripting.

---

# XML Editing and Backups

Whenever the tool modifies XML:

1. Create backup:
   - `book.xml.bak`
2. Write updated XML
3. Reload book in memory

Implemented by `_save_xml_with_backup()`.

---

# Dependencies

Required:

- Python 3.8+
- Tkinter

Optional:

- Pillow (image preview & zoom)
- pywebview (Graph Viewer)
- Graphviz (for DOT → SVG)

Install optional packages:

```bash
pip install pillow pywebview
```

Graphviz must provide `dot` in PATH.

---

# Intended Use

The Author Tool assists with:

- Editing paragraph structure
- Managing events declaratively
- Managing assets safely
- Validating rule references
- Visualizing the full book graph interactively

It is not designed to:

- Generate story content
- Replace a full text IDE
- Provide WYSIWYG layout editing

---

# Design Philosophy

The Author Tool respects core engine principles:

- Engine logic remains neutral
- XML remains declarative
- UI never redefines rule behavior
- Graph viewer runs isolated to avoid mainloop conflicts
