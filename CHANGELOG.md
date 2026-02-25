# Changelog

All notable changes to LDW Engine will be documented in this file.

The format is inspired by Keep a Changelog and follows semantic
versioning principles.

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
