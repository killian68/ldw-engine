# LDW Engine

LDW Engine is a lightweight Python engine for playing and authoring
paragraph-based interactive gamebooks (Fighting Fantasy--style).

It provides:

-   A clean XML-based book format (`formatVersion="1.0"`)
-   A reusable engine (rules, combat, tests, navigation stacks)
-   A Tkinter desktop UI with dice animation and sound effects
-   Character creation with multi-profile support
-   Save / Load support with persistent max stats

This project contains **engine code only** and an original example book.

------------------------------------------------------------------------

# Features

## Core Engine

-   Paragraph navigation system\

-   Choice conditions and effects\

-   Inventory and flags\

-   Stat system with:

    -   Current values
    -   Base (initial / max) values\

-   Centralized stat clamping:

        0 <= current_stat <= base_stat

------------------------------------------------------------------------

## Events

-   Combat (Fighting Fantasy--style)
-   Generic stat tests (e.g., Luck test)

------------------------------------------------------------------------

## Character Creation

-   Multiple profiles (classes)
-   Dice expressions (`NdM±K`, e.g., `1d6+6`, `2d6+12`)
-   Optional initial effects (flags, items, stat modifiers)

------------------------------------------------------------------------

## UI (Tkinter)

-   Dice animation widget
-   Sound effects (roll / hit / tie)
-   Image panel
-   Save / Load
-   Navigation stacks:
    -   `previous`
    -   `return`
    -   `call:<paragraph_id>` module calls

------------------------------------------------------------------------

# Requirements

-   Python 3.8+
-   Tkinter (usually included with Python)
-   Pillow (optional, for image resizing support)

Install Pillow if needed:

``` bash
pip install pillow
```

------------------------------------------------------------------------

# Running the Engine

From the project root:

``` bash
python main.py
```

By default, it loads:

    examples/sample_book.xml

You can load other books via the **File → Open** menu.

------------------------------------------------------------------------

# XML Book Format (v1.0)

Each book must declare:

``` xml
<book id="..." title="..." version="..." formatVersion="1.0">
```

## Structure Overview

``` xml
<book>
  <ruleset>...</ruleset>
  <assets>...</assets>
  <start paragraph="1" />
  <paragraphs>
    <paragraph id="1">...</paragraph>
  </paragraphs>
</book>
```

------------------------------------------------------------------------

## Ruleset

``` xml
<ruleset name="ff_basic">
  <dice sides="6" />
  <characterCreation>...</characterCreation>
  <stats>...</stats>
</ruleset>
```

------------------------------------------------------------------------

## Character Creation

``` xml
<characterCreation defaultProfile="adventurer">
  <profile id="adventurer" label="Adventurer">
    <roll stat="skill" expr="1d6+6" />
    <roll stat="stamina" expr="2d6+12" />
    <roll stat="luck" expr="1d6+6" />
  </profile>
</characterCreation>
```

### Supported dice expressions

-   `NdM`
-   `NdM+K`
-   `NdM-K`

Examples:

-   `1d6+6`
-   `2d6+12`
-   `2d6`

When a character is created:

-   `state.stats[stat]` is set to the rolled value\
-   `state.base_stats[stat]` is set to the same value (max reference)

------------------------------------------------------------------------

## Paragraph

``` xml
<paragraph id="10">
  <text>Story text...</text>
  <image ref="p1" />
  <choice target="20">Continue</choice>
  <event type="combat" ... />
</paragraph>
```

------------------------------------------------------------------------

## Choices

Basic choice:

``` xml
<choice target="20">Continue</choice>
```

With conditions and effects:

``` xml
<choice target="4">
  <conditions>
    <hasItem text="Rope" />
  </conditions>
  <effects>
    <addItem text="Silver Dagger" />
    <modifyStat id="stamina" delta="-1" />
    <setFlag key="has_magic" />
  </effects>
</choice>
```

------------------------------------------------------------------------

## Special Targets

-   `previous` --- go back in navigation history\
-   `return` --- return from module (return stack)\
-   `call:<pid>` --- module call (push return stack)

------------------------------------------------------------------------

## Combat Event (Compact Form)

``` xml
<event type="combat"
       enemyName="Bandit"
       enemySkill="8"
       enemyStamina="10"
       onWin="20"
       onLose="900" />
```

------------------------------------------------------------------------

## Test Event

``` xml
<event type="test"
       stat="luck"
       dice="2d6"
       successGoto="40"
       failGoto="901"
       consumeOnSuccess="1"
       consumeOnFail="1" />
```

### Test Rule

1.  Roll dice\
2.  Success if total ≤ current stat\
3.  Apply stat consumption\
4.  Clamp automatically applied

------------------------------------------------------------------------

# Save System

Save files store:

-   Current paragraph
-   Current stats
-   Base (initial/max) stats
-   Inventory
-   Flags
-   Navigation history
-   Return stack

This ensures a full restoration of game state.

------------------------------------------------------------------------

# Legal Notice

This repository provides:

-   A generic gamebook engine\
-   An XML authoring format\
-   An original example book

It does **not** include:

-   Story text from published commercial gamebooks\
-   Illustrations from published books\
-   Scans, PDFs, or OCR extracts\
-   Copyrighted content owned by third-party publishers or authors

Users are responsible for ensuring they have the legal right to any
content they load into this engine.

------------------------------------------------------------------------

# Copyright

Copyright (c) 2026 Laurent Cachia

------------------------------------------------------------------------

# License

This project is licensed under the MIT License.\
See the `LICENSE` file for details.
