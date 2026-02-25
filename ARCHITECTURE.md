# LDW Engine Architecture

This document explains the internal architecture of LDW Engine.

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
    Runtime State (GameState)
       │
       ▼
    UI Layer (Tkinter)

------------------------------------------------------------------------

# Layer Responsibilities

## 1. Book XML

Defines:

-   Paragraphs
-   Choices
-   Events
-   Ruleset (tests, combat profiles)
-   Character creation

The XML must remain declarative.

------------------------------------------------------------------------

## 2. Book Loader

Responsibilities:

-   Parse XML
-   Build data models
-   Validate structure
-   Ensure rule references exist

The loader must NOT implement game logic.

------------------------------------------------------------------------

## 3. Engine Models

Data-only structures:

-   Ruleset
-   TestRule
-   CombatProfile
-   LuckRule
-   FleeRule
-   GameState

No UI logic belongs here.

------------------------------------------------------------------------

## 4. Engine Logic Modules

-   combat.py
-   tests.py
-   rules.py

These modules interpret declarative models.

They must: - Use model data - Avoid hardcoded assumptions - Remain
reusable

------------------------------------------------------------------------

## 5. Runtime State (GameState)

Stores:

-   Current paragraph
-   Stats (current + base)
-   Inventory
-   Flags
-   Navigation stacks

Clamping rule:

    0 <= current_stat <= base_stat

------------------------------------------------------------------------

## 6. UI Layer (Tkinter)

Responsibilities:

-   Rendering paragraphs
-   Dice animation
-   Sound effects
-   Save/Load dialogs
-   Character creation dialogs

The UI must never redefine rule logic.

------------------------------------------------------------------------

# Data Flow Example (Combat)

1.  XML defines `combatProfile`
2.  Loader builds `CombatProfile`
3.  Event references `rulesRef`
4.  CombatSession interprets profile
5.  Results update GameState
6.  UI displays outcome

------------------------------------------------------------------------

# Extensibility Model

New features should:

1.  Be declarative in XML
2.  Be validated in loader
3.  Extend models cleanly
4.  Be interpreted by engine modules
5.  Avoid UI coupling

------------------------------------------------------------------------

# Future Architecture Enhancements

-   XML Schema Definition (XSD)
-   CLI validator tool
-   Headless engine mode
-   Web frontend adapter
-   Automated test coverage

------------------------------------------------------------------------

# Design Philosophy

LDW Engine prioritizes:

-   Deterministic behavior
-   Declarative design
-   Strict separation of concerns
-   Engine reuse across multiple rulesets
