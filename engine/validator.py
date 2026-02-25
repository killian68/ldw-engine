from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from engine.models import Book, CombatSpec, TestSpec


@dataclass
class ValidationError:
    code: str
    message: str
    where: Optional[str] = None  # e.g. "paragraph 10", "ruleset.tests", ...


class BookValidationException(ValueError):
    def __init__(self, errors: List[ValidationError]):
        self.errors = errors
        msg = "Book validation failed:\n" + "\n".join(
            f"- [{e.code}] {e.message}" + (f" ({e.where})" if e.where else "")
            for e in errors
        )
        super().__init__(msg)


def validate_book(book: Book, *, strict: bool = True) -> None:
    """
    Strict book validation:
      - required fields sanity
      - all goto targets exist
      - all rulesRef/testRef references exist in ruleset when provided
      - combat/test minimal requirements

    Raises BookValidationException if any errors.
    """
    errors: List[ValidationError] = []

    # ---- Basic sanity ----
    if not book.book_id:
        errors.append(ValidationError("BOOK_ID_MISSING", "book_id is missing", "book"))
    if not book.start_paragraph:
        errors.append(ValidationError("START_MISSING", "start_paragraph is missing", "book"))
    if book.start_paragraph not in book.paragraphs:
        errors.append(ValidationError(
            "START_NOT_FOUND",
            f"Start paragraph '{book.start_paragraph}' not found in paragraphs",
            "book/start"
        ))

    # ruleset presence / name (contract)
    if strict:
        if not book.ruleset or not book.ruleset.name:
            errors.append(ValidationError("RULESET_MISSING", "ruleset is required and must have a name", "ruleset"))

    # ---- Paragraph-level validation ----
    pids = set(book.paragraphs.keys())

    for pid, para in book.paragraphs.items():
        where_p = f"paragraph {pid}"

        # choices targets must exist (except special tokens)
        for ch in para.choices:
            tgt = (ch.target or "").strip()
            if not tgt:
                errors.append(ValidationError("CHOICE_TARGET_MISSING", "Choice target is empty", where_p))
                continue
            if tgt in ("previous", "return") or tgt.startswith("call:"):
                continue
            if tgt not in pids:
                errors.append(ValidationError(
                    "CHOICE_TARGET_UNKNOWN",
                    f"Choice target '{tgt}' does not exist",
                    where=f"{where_p}/choice[{ch.label}]"
                ))

        # events
        for ev in para.events:
            if ev.type == "combat":
                spec: CombatSpec = ev.payload
                # goto targets
                if spec.on_win_goto and spec.on_win_goto not in pids:
                    errors.append(ValidationError(
                        "COMBAT_ONWIN_UNKNOWN",
                        f"Combat onWin target '{spec.on_win_goto}' does not exist",
                        where=where_p
                    ))
                if spec.on_lose_goto and spec.on_lose_goto not in pids:
                    errors.append(ValidationError(
                        "COMBAT_ONLOSE_UNKNOWN",
                        f"Combat onLose target '{spec.on_lose_goto}' does not exist",
                        where=where_p
                    ))

                # rulesRef validity (if present)
                if spec.rules_ref:
                    if spec.rules_ref not in book.ruleset.combat_profiles:
                        errors.append(ValidationError(
                            "COMBAT_RULESREF_UNKNOWN",
                            f"rulesRef '{spec.rules_ref}' not found in ruleset.combatProfiles",
                            where=where_p
                        ))

                # numeric sanity (optional strict)
                if strict:
                    if int(spec.enemy_skill) < 0:
                        errors.append(ValidationError("COMBAT_ENEMY_SKILL_INVALID", "enemySkill must be >= 0", where_p))
                    if int(spec.enemy_stamina) < 0:
                        errors.append(ValidationError("COMBAT_ENEMY_STAMINA_INVALID", "enemyStamina must be >= 0", where_p))

            elif ev.type == "test":
                spec: TestSpec = ev.payload

                # goto targets
                if spec.success_goto and spec.success_goto not in pids:
                    errors.append(ValidationError(
                        "TEST_SUCCESS_UNKNOWN",
                        f"Test successGoto '{spec.success_goto}' does not exist",
                        where=where_p
                    ))
                if spec.fail_goto and spec.fail_goto not in pids:
                    errors.append(ValidationError(
                        "TEST_FAIL_UNKNOWN",
                        f"Test failGoto '{spec.fail_goto}' does not exist",
                        where=where_p
                    ))

                # testRef validity (if present)
                if spec.test_ref:
                    if spec.test_ref not in book.ruleset.tests:
                        errors.append(ValidationError(
                            "TEST_TESTREF_UNKNOWN",
                            f"testRef '{spec.test_ref}' not found in ruleset.tests",
                            where=where_p
                        ))

                # stat_id required (should already be resolved by loader; we enforce)
                if strict and not (spec.stat_id or "").strip():
                    errors.append(ValidationError("TEST_STAT_MISSING", "Test stat_id is missing", where_p))

            else:
                # forward-compat: unknown events ignored by runtime, but in strict mode you can flag them
                if strict:
                    errors.append(ValidationError(
                        "EVENT_UNKNOWN_TYPE",
                        f"Unknown event type '{ev.type}'",
                        where=where_p
                    ))

    # ---- Ruleset internal validation (refs inside ruleset) ----
    if strict:
        # tests must have stat
        for tid, tr in book.ruleset.tests.items():
            if not (tr.stat or "").strip():
                errors.append(ValidationError("RULE_TEST_STAT_MISSING", f"TestRule '{tid}' has no stat", "ruleset/tests"))

        # combatProfiles: if luck.test_ref exists, it must exist in tests
        for cid, cp in book.ruleset.combat_profiles.items():
            if cp.luck and cp.luck.test_ref:
                if cp.luck.test_ref not in book.ruleset.tests:
                    errors.append(ValidationError(
                        "RULE_COMBAT_LUCK_TESTREF_UNKNOWN",
                        f"CombatProfile '{cid}' luck.testRef '{cp.luck.test_ref}' not found in ruleset.tests",
                        "ruleset/combatProfiles"
                    ))

    if errors:
        raise BookValidationException(errors)