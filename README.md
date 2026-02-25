# LDW Engine

![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Format](https://img.shields.io/badge/XML-formatVersion%201.1-orange)
![Status](https://img.shields.io/badge/status-active-brightgreen)

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

## UI (Tkinter Desktop)

-   Animated dice widget
-   Sound effects
-   Image panel
-   Save/Load system
-   Navigation stack:
    -   `previous`
    -   `return`
    -   `call:<pid>`

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

## Design Principle

-   No hardcoded game mechanics
-   Combat logic is driven by `CombatProfile`
-   Tests are driven by `TestRule`
-   XML is validated before runtime use

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

Requirements:

-   Python 3.8+
-   Tkinter
-   Pillow (optional)

Linux:

    sudo apt install python3-tk python3-pil.imagetk
    pip install pillow

Run:

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
