from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Optional, Tuple

from engine.models import GameState, Ruleset, TestRule, TestSpec


# NdM±K (e.g., 1d6+6, 2d6+12, 1d6-1, 2d6)
_ROLL_EXPR_RE = re.compile(r"^\s*(\d+)\s*d\s*(\d+)\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)


@dataclass
class TestOutcome:
    """
    Result of a stat test (data-only outcome suitable for UI logs).

    - roll_total: total rolled (including offset)
    - roll_detail: raw dice (n rolls) when available
    - stat_id: which stat was tested
    - stat_before/stat_after: stat values before and after consume
    - success: whether the test succeeded
    - consumed: how many points were consumed from the stat
    - test_ref: which declarative rule was used (if any)
    """
    roll_total: int
    roll_detail: Tuple[int, ...]
    stat_id: str
    stat_before: int
    stat_after: int
    success: bool
    consumed: int
    test_ref: Optional[str] = None


def parse_roll_expression(expr: str) -> tuple[int, int, int]:
    m = _ROLL_EXPR_RE.match(expr or "")
    if not m:
        raise ValueError(f"Invalid roll expression: {expr!r}")
    n = int(m.group(1))
    sides = int(m.group(2))
    offset = 0
    if m.group(3):
        offset = int(m.group(3).replace(" ", ""))
    return n, sides, offset


def roll_expr(expr: str, rng: random.Random) -> tuple[int, tuple[int, ...]]:
    """
    Roll NdM±K. Returns (total, detail_tuple).
    If invalid -> fallback to 2d6.
    """
    try:
        n, sides, offset = parse_roll_expression(expr)
        rolls = tuple(rng.randint(1, max(1, sides)) for _ in range(max(0, n)))
        return (sum(rolls) + offset, rolls)
    except Exception:
        r = (rng.randint(1, 6), rng.randint(1, 6))
        return (r[0] + r[1], r)


def eval_success_if(expr: str, *, roll_total: int, stat_value: int) -> bool:
    """
    Minimal safe evaluator for successIf.
    Supported:
      roll<=stat, roll<stat, roll>=stat, roll>stat, roll==stat, roll=stat
    Fallback: roll<=stat
    """
    e = (expr or "").strip().lower().replace(" ", "")
    if e in ("roll<=stat", "roll≤stat"):
        return roll_total <= stat_value
    if e == "roll<stat":
        return roll_total < stat_value
    if e == "roll>=stat":
        return roll_total >= stat_value
    if e == "roll>stat":
        return roll_total > stat_value
    if e in ("roll==stat", "roll=stat"):
        return roll_total == stat_value
    return roll_total <= stat_value


def resolve_test_rule(ruleset: Optional[Ruleset], test_ref: Optional[str]) -> Optional[TestRule]:
    if not ruleset or not test_ref:
        return None
    return ruleset.tests.get(test_ref)


def run_test_with_roll(
    state: GameState,
    *,
    ruleset: Optional[Ruleset] = None,
    test_ref: Optional[str] = None,
    stat_id: Optional[str] = None,
    success_if: str = "roll<=stat",
    consume_on_success: int = 0,
    consume_on_fail: int = 0,
    roll_total: int,
    roll_detail: Tuple[int, ...] = (),
) -> TestOutcome:
    """
    Apply a stat test using a PRE-ROLLED dice result (roll_total).
    This is crucial for UI dice animation (Tk dice widget) to avoid double-rolling.

    Priority:
      1) if test_ref exists in ruleset.tests, use that TestRule (stat/successIf/consume)
      2) else use provided (stat_id, success_if, consume_on_success/fail)
    """
    rule = resolve_test_rule(ruleset, test_ref)

    if rule:
        _stat_id = rule.stat
        _success_if = rule.success_if or "roll<=stat"
        consume_success = int(rule.consume or 0)
        consume_fail = int(rule.consume or 0)
        used_ref = rule.test_id
    else:
        _stat_id = (stat_id or "").strip()
        if not _stat_id:
            raise ValueError("run_test_with_roll: stat_id is required when no test_ref rule exists.")
        _success_if = (success_if or "roll<=stat").strip()
        consume_success = int(consume_on_success or 0)
        consume_fail = int(consume_on_fail or 0)
        used_ref = test_ref

    before = int(state.stats.get(_stat_id, 0))
    success = eval_success_if(_success_if, roll_total=int(roll_total), stat_value=before)

    consumed = (consume_success if success else consume_fail)
    consumed = max(0, int(consumed))

    after = max(0, before - consumed)
    state.stats[_stat_id] = after

    return TestOutcome(
        roll_total=int(roll_total),
        roll_detail=tuple(int(x) for x in (roll_detail or ())),
        stat_id=_stat_id,
        stat_before=before,
        stat_after=after,
        success=bool(success),
        consumed=int(consumed),
        test_ref=used_ref,
    )


def run_test(
    state: GameState,
    rng: random.Random,
    *,
    ruleset: Optional[Ruleset] = None,
    test_ref: Optional[str] = None,
    stat_id: Optional[str] = None,
    dice: str = "2d6",
    success_if: str = "roll<=stat",
    consume_on_success: int = 0,
    consume_on_fail: int = 0,
) -> TestOutcome:
    """
    Runs a stat test (rolls internally).
    Use run_test_with_roll() if UI already rolled (animated dice).
    """
    rule = resolve_test_rule(ruleset, test_ref)

    if rule:
        _stat_id = rule.stat
        _dice = rule.dice or "2d6"
        _success_if = rule.success_if or "roll<=stat"
        consume_success = int(rule.consume or 0)
        consume_fail = int(rule.consume or 0)
    else:
        _stat_id = (stat_id or "").strip()
        if not _stat_id:
            raise ValueError("run_test: stat_id is required when no test_ref rule exists.")
        _dice = (dice or "2d6").strip()
        _success_if = (success_if or "roll<=stat").strip()
        consume_success = int(consume_on_success or 0)
        consume_fail = int(consume_on_fail or 0)

    total, detail = roll_expr(_dice, rng)

    return run_test_with_roll(
        state,
        ruleset=ruleset,
        test_ref=test_ref,
        stat_id=_stat_id,
        success_if=_success_if,
        consume_on_success=consume_success,
        consume_on_fail=consume_fail,
        roll_total=int(total),
        roll_detail=tuple(int(x) for x in detail),
    )


def run_test_from_spec(
    state: GameState,
    rng: random.Random,
    spec: TestSpec,
    *,
    ruleset: Optional[Ruleset] = None,
) -> TestOutcome:
    """
    Convenience wrapper for event-driven tests (TestSpec).
    Uses spec.test_ref if present; otherwise uses spec fields.
    """
    return run_test(
        state,
        rng,
        ruleset=ruleset,
        test_ref=spec.test_ref,
        stat_id=spec.stat_id,
        dice=spec.dice,
        success_if="roll<=stat",
        consume_on_success=spec.consume_on_success,
        consume_on_fail=spec.consume_on_fail,
    )