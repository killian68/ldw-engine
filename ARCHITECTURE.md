# LDW Engine Architecture

This document explains the internal architecture of LDW Engine (v1.2.0).

------------------------------------------------------------------------

# High-Level Overview

    Book XML
       │
       ▼
    Book Loader (validation + parsing)
       │
       ▼
    Engine Models (Ruleset, CombatProfile, TestRule, etc.)
       │
       ▼
    Engine Logic Modules (combat, tests, rules)
       │
       ▼
    Runtime State (GameState)
       │
       ▼
    UI Layer (Tkinter)
       ├── author_tool.py
       ├── image_viewer.py
       └── graph_viewer.py  (separate process)

------------------------------------------------------------------------

# Layer Responsibilities

## 1. Book XML

Defines:

- Paragraphs
- Choices
- Events
- Ruleset (tests, combat profiles)
- Character creation

The XML must remain declarative.

------------------------------------------------------------------------

## 2. Book Loader

Responsibilities:

- Parse XML
- Build data models
- Validate structure
- Ensure rule references exist

The loader must NOT implement game logic.

------------------------------------------------------------------------

## 3. Engine Models

Data-only structures:

- Ruleset
- TestRule
- CombatProfile
- LuckRule
- FleeRule
- GameState

No UI logic belongs here.

------------------------------------------------------------------------

## 4. Engine Logic Modules

- combat.py
- tests.py
- rules.py

These modules interpret declarative models.

They must:
- Use model data
- Avoid hardcoded assumptions
- Remain reusable
- Remain UI-independent

------------------------------------------------------------------------

## 5. Runtime State (GameState)

Stores:

- Current paragraph
- Stats (current + base)
- Inventory
- Flags
- Navigation stacks

Clamping rule:

    0 <= current_stat <= base_stat

------------------------------------------------------------------------

## 6. UI Layer (Tkinter)

Responsibilities:

- Rendering paragraphs
- Dice animation
- Sound effects
- Save/Load dialogs
- Character creation dialogs
- Authoring tools
- Image viewer (interactive zoom/pan)
- Graph viewer launcher

The UI must never redefine rule logic.

------------------------------------------------------------------------

# Graph Viewer Architecture (v1.2.0)

The graph viewer is intentionally isolated from the main Tkinter UI loop.

Design rationale:

- Avoid Tkinter mainloop conflicts
- Allow independent refresh/export cycle
- Keep graph visualization decoupled from engine core

Structure:

    author_tool.py
        │
        ├── Exports DOT via engine.export_dot()
        ├── Generates SVG via Graphviz
        └── Launches graph_viewer.py (subprocess)
                │
                ├── Loads SVG in pywebview
                ├── Provides zoom & pan
                └── Calls CLI export for refresh

Key properties:

- Runs in a separate process
- Uses CLI mode: --export-graph
- Does not access engine internals directly
- Keeps UI responsibilities separated

------------------------------------------------------------------------

# Data Flow Example (Combat)

1. XML defines `combatProfile`
2. Loader builds `CombatProfile`
3. Event references `rulesRef`
4. CombatSession interprets profile
5. Results update GameState
6. UI displays outcome

------------------------------------------------------------------------

# Data Flow Example (Graph Export)

1. Author Tool loads Book
2. User clicks "Graph (SVG)"
3. DOT is generated via export_dot()
4. Graphviz produces SVG
5. graph_viewer.py displays SVG
6. Refresh triggers CLI export and reload

------------------------------------------------------------------------

# Extensibility Model

New features should:

1. Be declarative in XML (if gameplay-related)
2. Be validated in loader
3. Extend models cleanly
4. Be interpreted by engine modules
5. Avoid UI coupling
6. Maintain process isolation for external viewers

------------------------------------------------------------------------

# Future Architecture Enhancements

- XML Schema Definition (XSD)
- CLI validator tool
- Headless engine mode
- Web frontend adapter
- Automated test coverage
- Plugin-based UI components

------------------------------------------------------------------------

# Design Philosophy

LDW Engine prioritizes:

- Deterministic behavior
- Declarative design
- Strict separation of concerns
- Engine reuse across multiple rulesets
- UI modularity
- Process isolation where appropriate
