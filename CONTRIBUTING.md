# Contributing to LDW Engine

Thank you for your interest in contributing to **LDW Engine**.

This project is currently maintained as a personal initiative. Contributions are welcome, but the architectural direction is curated to keep the engine lightweight, readable, and legally safe.

---

## Philosophy

LDW Engine is designed to be:

- Lightweight
- Explicit over magical
- XML-driven
- Deterministic and debuggable
- Legally clean (no copyrighted book content)

Please keep these principles in mind when proposing changes.

---

## Before Contributing

1. Open an issue describing:
   - The problem
   - The proposed solution
   - Why it fits the project philosophy

2. Wait for feedback before submitting large changes.

Small fixes (typos, minor bugfixes, doc improvements) can be submitted directly.

---

## Development Guidelines

### Code Style

- Python 3.8+ compatible
- Clear, explicit code over clever shortcuts
- Avoid unnecessary dependencies
- Keep engine logic separate from UI logic

### Structure Rules

- `engine/` must remain UI-independent
- `ui/` must not embed core rules logic
- `examples/` must only contain original, non-copyrighted content
- `docs/` contains documentation only

Do not mix responsibilities between these layers.

---

## XML Format Changes

If modifying the XML specification:

- Update validation rules (`engine/validate.py`)
- Update loader (`engine/book_loader.py`)
- Update documentation (`README.md` and `docs/`)
- Preserve backward compatibility when possible

Any breaking change must bump `formatVersion`.

---

## Legal Notice

Do NOT submit:

- Text copied from commercial gamebooks
- Scanned illustrations
- OCR extracts of copyrighted works

This repository must remain legally distributable.

---

## Pull Request Checklist

Before submitting a PR:

- [ ] Code runs without errors
- [ ] Validation still works
- [ ] No UI-engine coupling introduced
- [ ] Documentation updated if needed
- [ ] No copyrighted material included

---

## Maintainer Notes

The maintainer reserves the right to:

- Reject changes that complicate the engine unnecessarily
- Refactor submitted code before merging
- Prioritize architectural coherence over feature expansion

---

## License

By contributing, you agree that your contributions will be licensed under the MIT License used by this project.
