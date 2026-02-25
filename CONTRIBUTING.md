# Contributing to LDW Engine

Thank you for considering contributing to LDW Engine.

This project follows a strict design philosophy:

> The engine must remain neutral.\
> Game mechanics belong in the XML ruleset.

------------------------------------------------------------------------

# Core Principles

## 1. Engine Neutrality

-   Do NOT hardcode specific rule behavior.
-   All combat logic must be driven by `CombatProfile`.
-   All tests must be driven by `TestRule`.
-   Avoid embedding book-specific assumptions.

## 2. Backward Compatibility

-   Maintain compatibility with `formatVersion="1.1"` unless explicitly
    bumping the version.
-   When adding XML attributes:
    -   Make them optional
    -   Update the validator
    -   Update documentation

## 3. XML Validation

If you introduce new XML features:

-   Add strict validation rules
-   Fail fast on missing required attributes
-   Validate cross-references (`rulesRef`, `testRef`)

------------------------------------------------------------------------

# Development Setup

Requirements:

-   Python 3.8+
-   Tkinter
-   Pillow (optional)

Run locally:

    python main.py

------------------------------------------------------------------------

# Code Guidelines

-   Keep modules small and focused.
-   Avoid circular dependencies.
-   Use dataclasses for data models.
-   Keep UI logic separate from engine logic.
-   Add comments for non-obvious mechanics.

------------------------------------------------------------------------

# Pull Request Guidelines

Before submitting a PR:

-   Ensure XML validation passes.
-   Ensure no rule logic is hardcoded.
-   Update README if format changes.
-   Keep changes focused and atomic.

------------------------------------------------------------------------

# Reporting Issues

When reporting a bug, include:

-   Python version
-   OS
-   formatVersion used
-   Minimal XML example reproducing the issue

------------------------------------------------------------------------

# Roadmap Alignment

Major features should align with:

-   Declarative expansion
-   Validation improvements
-   Engine neutrality
-   Testing coverage

------------------------------------------------------------------------

# License

By contributing, you agree that your contributions will be licensed
under the MIT License.
