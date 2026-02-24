# Author Tool (Book Inspector)

The **LDW Author Tool** is a Tkinter desktop utility for inspecting and validating LDW XML gamebooks.
It is intended for **authors and maintainers**, not for players.

It loads a book using the same parser as the engine (`engine.book_loader.load_book`) and provides:
- paragraph outline + preview
- link graph inspection (incoming/outgoing)
- asset management (import/link/unlink/delete + preview)
- full-text search across paragraphs
- validation report (errors/warnings/info)
- graph export to Graphviz DOT (and optional SVG)

The tool is **non-destructive by default**, and when it edits XML it automatically creates a `.bak` backup.

---

## Where it lives

The tool is implemented as a standalone Tkinter app:

- `author_tool.py`

It can be launched directly:

```bash
python author_tool.py
```

On startup it tries to auto-load:

- `examples/sample_book.xml`

(if the file exists)

---

## Features by Tab

### 1) Outline

Purpose: browse paragraph IDs, preview paragraph text, and inspect choices.

Includes:
- Filter box (matches paragraph ID or paragraph text)
- Paragraph list (IDs)
- Preview panel:
  - paragraph text excerpt
  - choices list (`label -> target`)
  - image ref if present

Actions:
- **Copy ID**: copies the selected paragraph ID to clipboard
- **Assign Image (import)...**:
  - prompts for an image file
  - copies it into the book assets directory (`<assets basePath="...">`)
  - creates/updates `<assets><image id="..." file="..."/></assets>`
  - links the paragraph with `<image ref="..."/>`
  - writes the XML back to disk
  - creates a backup `book.xml.bak`

Asset naming rule:
- file is named from the paragraph id, e.g. `p10.png`, `p10_2.png`, etc.
- asset id is the filename without extension (`p10`, `p10_2`, ...)

---

### 2) Links

Purpose: inspect the link graph around a paragraph.

Shows:
- **Outgoing** targets from the paragraph (choices + combat event gotos)
- **Incoming** sources linking to the paragraph

Tools:
- **Export DOT...**: exports the whole book graph to a `.dot` file
- **Export DOT + SVG**:
  - requires Graphviz `dot`
  - exports `.dot` and runs `dot -Tsvg`
  - opens the resulting SVG (best effort on Windows via `os.startfile`)

Notes:
- The link graph is built via `engine.validate.build_link_index`.

---

### 3) Assets

Purpose: manage `<assets>` declarations and paragraph image links.

Displays a table of:
- `asset_id`
- `file` (relative file path)
- `exists` (YES/NO on disk)
- `used_by` (paragraph IDs currently referencing it)

Selecting an asset:
- displays its resolved absolute path
- previews the image if Pillow is installed and the file exists

Buttons:
- **Add Asset...**
  - imports an image into the assets directory
  - adds `<assets><image id="..." file="..."/></assets>`
  - does **not** link it to any paragraph
  - writes XML to disk (+ backup)

- **Assign to selected paragraph**
  - links the selected asset (Assets tab) to the selected paragraph (Outline tab)
  - sets/creates `<image ref="..."/>`
  - writes XML to disk (+ backup)

- **Remove link from selected paragraph**
  - removes `<image .../>` from the selected paragraph
  - does not delete the asset or file
  - writes XML to disk (+ backup)

- **Delete selected asset...**
  - removes `<image id="...">` declaration from `<assets>`
  - if used by paragraphs, offers to unlink everywhere first
  - optionally deletes the physical image file
  - writes XML to disk (+ backup)

Important safety behavior:
- XML is saved first, file deletion is optional and happens after XML save.

---

### 4) Search

Purpose: full-text search across paragraph text.

Usage:
- type a query and press Enter or click **Search**
- results list displays paragraph IDs where the query appears in paragraph text
- selecting a result:
  - previews the paragraph snippet (up to ~1200 chars)
  - selects the paragraph in the Outline tab
  - sets the paragraph in the Links tab

---

### 5) Validation

Purpose: run book validation using the engine validator.

Uses:
- `engine.validate.validate_book(book, book_dir)`

Displays:
- summary counts: Errors / Warnings / Info
- issue list:
  - severity
  - paragraph id (if any)
  - message

Behavior:
- selecting an issue with a paragraph id jumps to that paragraph in Outline and Links.

---

## XML Editing and Backups

Whenever the tool modifies the XML, it performs:

1) Create a backup file:
   - `book.xml.bak`

2) Write updated XML back to the original file path:
   - `book.xml`

This is implemented by `_save_xml_with_backup()`.

---

## Dependencies

Required:
- Python 3.8+
- Tkinter (typically bundled with Python)

Optional:
- Pillow (enables image preview & resizing)

Install Pillow:
```bash
pip install pillow
```

Optional (for SVG export):
- Graphviz (the `dot` command must be available)

Windows default Graphviz locations are checked:
- `C:\Program Files\Graphviz\bin\dot.exe`
- `C:\Program Files (x86)\Graphviz\bin\dot.exe`

---

## Intended Use

The Author Tool is meant to assist with:
- iterating quickly on XML structure
- managing assets safely
- finding broken links early
- keeping the book graph understandable (via DOT export)

It is not designed to:
- generate story content
- perform OCR conversion
- edit paragraph text (today it only edits assets and image links)

Those features can be added later if needed.
