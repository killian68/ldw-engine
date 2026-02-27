# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog
and this project follows Semantic Versioning.

## \[1.4.0\] -- 2026-02-27

### 🚀 Major Improvements

#### Graph Viewer -- Architecture Rewrite

-   Replaced direct pywebview file loading with a local HTTP server
    architecture
-   `graph_viewer.py` now:
    -   Starts a lightweight local server (127.0.0.1)
    -   Serves `viewer.html`
    -   Serves `graph.svg`
    -   Exposes `/api/refresh` endpoint
-   Eliminates fragile GTK WebKit issues on Linux
-   Removes dependency on WebKitGTK
-   Works reliably on Windows and Linux
-   Automatic fallback to system browser when embedded backend is
    unavailable

------------------------------------------------------------------------

### ✍ Author Tool Improvements

#### Draft Editing Model

-   Added in-memory draft system
-   Paragraph edits are preserved when navigating between paragraphs
-   No more accidental loss of changes
-   Explicit save required to write to XML

#### Visual State Indicators

-   Paragraph list color coding:
    -   Green → Clean (saved)
    -   Black → Dirty (modified)
-   Dirty state updates only when actual modifications occur
-   Fixed recursive dirty-state stack overflow bug

#### Graph Export Stability

-   Refresh button now triggers export through HTTP endpoint
-   Improved reliability across platforms

------------------------------------------------------------------------

### 🎨 UI Enhancements

-   Unified icon injection for:
    -   Main application (`app_tk`)
    -   Author Tool
-   Centralized icon logic via `ui/icon.py`
-   Removed duplicated icon handling logic

------------------------------------------------------------------------

### 🧹 Internal Cleanup

-   Removed embedded HTML from Python source
-   Separated `viewer.html` into standalone file
-   Simplified dependency model
-   Improved process isolation for Graph Viewer
-   Reduced platform-specific workarounds

------------------------------------------------------------------------

### 🔧 Dependency Changes

#### Linux

-   WebKitGTK no longer required
-   Qt backend optional
-   Default behavior uses system browser for Graph Viewer

#### Windows

-   Qt backend optional
-   No system-level Qt installation required

------------------------------------------------------------------------

### ⚠ Breaking Changes

-   Graph Viewer no longer depends on direct pywebview file loading
-   WebKitGTK support removed
-   Embedded HTML in `graph_viewer.py` removed (now external
    `viewer.html`)

------------------------------------------------------------------------

### 📦 Version Rationale

This release introduces architectural changes and major cross-platform
stabilization. Therefore it is released as a minor version bump (1.4.0).

## [1.3.0] – 2026-02-27

### ✨ Improved – Graph Viewer Stability & Cross-Platform Support

- Switched Graph Viewer backend to Qt (PySide6) for consistent behavior across Windows and Linux
- Removed WebKitGTK dependency (Linux)
- Forced qtpy backend to PySide6 to prevent accidental fallback to PyQt5
- Integrated HTML viewer directly into `graph_viewer.py` (no external viewer.html dependency)
- Implemented custom SVG pan/zoom engine:
  - Mouse wheel → zoom centered on cursor
  - Left-click + drag → pan
  - Double-click → fit to viewport
  - Keyboard shortcuts (`F`, `1`, `0`)
- Fixed mouse wheel zoom not working under QtWebEngine
- Improved refresh behavior (propagated Qt environment variables to subprocess)
- Added robust fallback to system browser if WebView fails

### 🐧 Linux

- Documented required dependency: `libxcb-cursor0`
- Added guidance for GNOME/Wayland (`QT_QPA_PLATFORM=xcb`)
- Eliminated GTK/WebKit version mismatch issues

### 🛠 Internal

- Viewer HTML now embedded directly in Python code
- Reduced runtime dependency ambiguity (no backend auto-selection)

## [1.2.1] - 2026-02-26

### Added
- Global application icon system (`ui/icon.py`)
- Automatic icon injection for all Tkinter windows (root + Toplevel)
- UI asset directory (`ui/assets/icons/`)
- Windows multi-resolution `.ico`
- macOS `.icns`
- Linux PNG variants (512 / 256 / 128)

### Improved
- Professional desktop integration across platforms
- Consistent branding across all UI windows


## [1.2.0] - 2026-02-26

### Added
- Interactive Graph Viewer (Edit tab → "Graph (SVG)")
  - Runs in a separate process using pywebview
  - Embedded SVG display
  - Mouse wheel zoom
  - Left-click + drag pan
  - Double-click to fit
  - "Refresh" button re-exports DOT + SVG
- CLI export mode:
  - `--export-graph --xml <file> --dot <file> --svg <file>`
  - Enables programmatic graph export
- Improved image viewer:
  - Mouse wheel now performs zoom (instead of vertical scroll)
  - Left-click + drag for panning
  - Double-click to fit image to window
  - Keyboard shortcuts:
    - `F` → Fit to window
    - `1` → 100% zoom

### Changed
- Image viewer mouse wheel behavior updated to match modern UX expectations (zoom instead of scroll)
- Graph viewer logic moved to `ui/graph_viewer.py`
- SVG export logic refactored to support CLI usage

### Technical
- Introduced new dependency: `pywebview`
- Graph viewer runs in isolated process to avoid Tkinter mainloop conflicts
- Temporary graph files generated in system temp directory

------------------------------------------------------------------------

## \[1.0.1\] - 2026-02-25

### Added

-   Declarative combat profiles (`<combatProfiles>`)
-   Declarative test definitions (`<tests>`)
-   `rulesRef` support for combat events
-   `testRef` support for test events
-   Optional `allowFlee` per combat event
-   Strict XML validation integration
-   Base stats persistence in save files

### Changed

-   Engine logic fully decoupled from hardcoded Fighting Fantasy rules
-   Combat and test logic now entirely ruleset-driven
-   README rewritten for GitHub optimization
-   Project documentation expanded (CONTRIBUTING, ARCHITECTURE)

### Fixed

-   Proper stat clamping after test consumption
-   Save/load compatibility for base stats
-   Minor XML parsing edge cases

------------------------------------------------------------------------

## \[1.0.0\]

### Initial Stable Release

-   Paragraph navigation system
-   Choice conditions and effects
-   Inventory and flags system
-   Stat system (current + base values)
-   Fighting Fantasy-style combat
-   Generic stat tests
-   Character creation with dice expressions
-   Tkinter UI with dice animation and sound effects
-   Save/Load system
-   Navigation stacks (previous / return / call)

------------------------------------------------------------------------

## Future Releases

Planned:

-   XML Schema (XSD)
-   CLI validator tool
-   Headless engine mode
-   Web frontend adapter
-   Automated test coverage

------------------------------------------------------------------------

# Versioning

This project follows Semantic Versioning:

MAJOR.MINOR.PATCH

-   MAJOR → Breaking XML or engine changes
-   MINOR → Backward-compatible feature additions
-   PATCH → Bug fixes and improvements
