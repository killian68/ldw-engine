from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Literal

from engine.models import GameState, CombatSpec, Ruleset, CombatProfile, LuckRule, Modifier
from engine.tests import run_test  # ✅ single neutral test engine


CombatOutcome = Literal["player_hit", "enemy_hit", "tie"]


@dataclass
class CombatRoundResult:
    """
    Structured outcome for a single combat round.
    - player_roll / enemy_roll: (d6, d6) for the main attack roll
    - player_attack / enemy_attack: Attack Strength
    - damage_to_enemy / damage_to_player: applied damages for this round
    - outcome: who was hit, or tie
    - player_stamina / enemy_stamina: post-round values
    - luck_used: whether player attempted luck this round
    - luck_roll: the 2d6 luck roll total (if used)
    - luck_success: result of luck test (if used)
    - luck_after: player's luck after consumption (if used)
    """
    player_roll: tuple[int, int]
    enemy_roll: tuple[int, int]
    player_attack: int
    enemy_attack: int
    damage_to_enemy: int
    damage_to_player: int
    outcome: CombatOutcome
    player_stamina: int
    enemy_stamina: int
    luck_used: bool = False
    luck_roll: Optional[int] = None
    luck_success: Optional[bool] = None
    luck_after: Optional[int] = None


def _roll_2d6(rng: random.Random) -> tuple[int, int]:
    return (rng.randint(1, 6), rng.randint(1, 6))


def _sum_roll(r: tuple[int, int]) -> int:
    return int(r[0]) + int(r[1])


# -----------------------------
# Runtime modifiers helpers (NEW)
# -----------------------------

def _sum_stat_modifiers(state: GameState, stat_id: str) -> int:
    """
    Sum all runtime modifiers that target a given stat.

    Expected target format: "stat:<stat_id>"
    Only supports op="add" for now.

    Backward compatible if state has no 'modifiers' attribute.
    """
    mods = getattr(state, "modifiers", None)
    if not mods:
        return 0

    target = f"stat:{stat_id}"
    total = 0
    for m in mods:
        try:
            if getattr(m, "target", None) != target:
                continue
            if (getattr(m, "op", "add") or "add").strip() != "add":
                continue
            total += int(getattr(m, "value", 0))
        except Exception:
            # Never let a malformed modifier break combat
            continue
    return total


def _get_effective_stat(state: GameState, stat_id: str) -> int:
    """
    Base stat from state.stats plus runtime modifiers.
    """
    base = int(state.stats.get(stat_id, 0))
    return base + _sum_stat_modifiers(state, stat_id)


def _default_profile() -> CombatProfile:
    # FF classic fallback
    return CombatProfile(
        combat_id="__fallback_ff_classic__",
        attack_dice="2d6",
        attack_stat="skill",
        tie_policy="no_damage",
        base_damage=2,
        luck=None,
        flee=None,
    )


def _resolve_profile(ruleset: Optional[Ruleset], spec: CombatSpec) -> CombatProfile:
    if ruleset and spec.rules_ref:
        prof = ruleset.combat_profiles.get(spec.rules_ref)
        if prof:
            return prof
    return _default_profile()


class CombatSession:
    """
    Neutral combat session, driven by a book Ruleset when provided.

    Backward compatible behavior (no ruleset / no rulesRef):
      - FF classic: each round both roll 2d6, add SKILL
      - higher Attack Strength inflicts 2 STAMINA damage
      - tie => no damage
      - ends when either stamina <= 0

    When ruleset + rulesRef are provided:
      - uses CombatProfile to define attack stat/dice, base damage, tie policy
      - supports Luck mapping (DF "Tentez votre chance") via declarative TestRule (engine.tests)
      - supports flee() with DF defaults
    """

    def __init__(self, state: GameState, spec: CombatSpec, rng: random.Random, ruleset: Optional[Ruleset] = None):
        self.state = state
        self.spec = spec
        self.rng = rng
        self.ruleset = ruleset

        self.profile: CombatProfile = _resolve_profile(ruleset, spec)

        self.enemy_name = spec.enemy_name
        self.enemy_skill = int(spec.enemy_skill)
        self.enemy_stamina = int(spec.enemy_stamina)

        self.finished: bool = False
        self.won: bool = False

        self._last_round: Optional[CombatRoundResult] = None

    # -----------------------------
    # UI helpers
    # -----------------------------

    def start_log(self) -> List[str]:
        atk_stat = (self.profile.attack_stat or "skill").strip()
        p_skill = _get_effective_stat(self.state, atk_stat)
        p_stam = int(self.state.stats.get("stamina", 0))

        lines = [
            "Combat begins!",
            f"You: {atk_stat.upper()} {p_skill} / STAMINA {p_stam}",
            f"{self.enemy_name}: SKILL {self.enemy_skill} / STAMINA {self.enemy_stamina}",
            "",
            "Click 'Roll next round' to roll the dice.",
        ]

        if self.profile.luck:
            luck_now = int(self.state.stats.get("luck", 0))
            lines.append(f"(Luck available: LUCK {luck_now} — you may 'Test your Luck' on hits.)")

        return lines

    def last_round(self) -> Optional[CombatRoundResult]:
        return self._last_round

    # -----------------------------
    # Core mechanics
    # -----------------------------

    def _player_attack_strength(self, pr: tuple[int, int]) -> int:
        stat_id = (self.profile.attack_stat or "skill").strip()
        p_stat = _get_effective_stat(self.state, stat_id)
        return p_stat + _sum_roll(pr)

    def _enemy_attack_strength(self, er: tuple[int, int]) -> int:
        return int(self.enemy_skill) + _sum_roll(er)

    def _try_luck(self) -> tuple[bool, int, int]:
        """
        Executes a luck test via the neutral TestEngine (engine.tests).
        Returns: (success, luck_roll_total, luck_after)
        """
        luck_now = int(self.state.stats.get("luck", 0))
        if luck_now <= 0:
            return (False, 0, luck_now)

        test_ref = "luck_test"
        if self.profile.luck and self.profile.luck.test_ref:
            test_ref = self.profile.luck.test_ref

        outcome = run_test(
            self.state,
            self.rng,
            ruleset=self.ruleset,
            test_ref=test_ref,
            stat_id="luck",
            dice="2d6",
            success_if="roll<=stat",
            consume_on_success=1,
            consume_on_fail=1,
        )
        return (outcome.success, int(outcome.roll_total), int(outcome.stat_after))

    def roll_round(self, *, use_luck: bool = False) -> List[str]:
        if self.finished:
            return ["(Combat already finished.)"]

        p_stam_before = int(self.state.stats.get("stamina", 0))

        pr = _roll_2d6(self.rng)
        er = _roll_2d6(self.rng)

        p_attack = self._player_attack_strength(pr)
        e_attack = self._enemy_attack_strength(er)

        outcome: CombatOutcome
        if p_attack > e_attack:
            outcome = "player_hit"
        elif e_attack > p_attack:
            outcome = "enemy_hit"
        else:
            outcome = "tie"

        luck_used = False
        luck_roll_total: Optional[int] = None
        luck_success: Optional[bool] = None
        luck_after: Optional[int] = None

        base = int(self.profile.base_damage or 2)
        dmg_to_enemy = 0
        dmg_to_player = 0

        logs: List[str] = []
        logs.append(f"You roll {pr[0]} + {pr[1]} (Attack Strength: {p_attack})")
        logs.append(f"{self.enemy_name} rolls {er[0]} + {er[1]} (Attack Strength: {e_attack})")

        if outcome == "tie":
            logs.append("You clash — no damage this round.")

        elif outcome == "player_hit":
            dmg_to_enemy = base

            if use_luck and self.profile.luck:
                luck_used = True
                luck_success, luck_roll_total, luck_after = self._try_luck()

                lr: LuckRule = self.profile.luck
                dmg_to_enemy = int(lr.on_player_hit_success_damage if luck_success else lr.on_player_hit_fail_damage)

                logs.append(f"Test your Luck! You roll {luck_roll_total} -> {'LUCKY' if luck_success else 'UNLUCKY'}")

            self.enemy_stamina -= int(dmg_to_enemy)
            logs.append(f"You strike {self.enemy_name}! (-{dmg_to_enemy} STAMINA)")

        elif outcome == "enemy_hit":
            dmg_to_player = base

            if use_luck and self.profile.luck:
                luck_used = True
                luck_success, luck_roll_total, luck_after = self._try_luck()

                lr = self.profile.luck
                dmg_to_player = int(lr.on_player_hurt_success_damage if luck_success else lr.on_player_hurt_fail_damage)

                logs.append(f"Test your Luck! You roll {luck_roll_total} -> {'LUCKY' if luck_success else 'UNLUCKY'}")

            self.state.stats["stamina"] = p_stam_before - int(dmg_to_player)
            logs.append(f"{self.enemy_name} strikes you! (-{dmg_to_player} STAMINA)")

        # Clamp to 0+
        if int(self.state.stats.get("stamina", 0)) < 0:
            self.state.stats["stamina"] = 0
        if self.enemy_stamina < 0:
            self.enemy_stamina = 0

        logs.append(
            f"Current STAMINA — You: {int(self.state.stats.get('stamina', 0))} | "
            f"{self.enemy_name}: {self.enemy_stamina}"
        )

        if self.enemy_stamina <= 0:
            self.finished = True
            self.won = True
            logs.append("")
            logs.append(f"{self.enemy_name} is defeated!")
        elif int(self.state.stats.get("stamina", 0)) <= 0:
            self.finished = True
            self.won = False
            logs.append("")
            logs.append("You fall to the ground. Defeat.")

        self._last_round = CombatRoundResult(
            player_roll=pr,
            enemy_roll=er,
            player_attack=p_attack,
            enemy_attack=e_attack,
            damage_to_enemy=int(dmg_to_enemy),
            damage_to_player=int(dmg_to_player),
            outcome=outcome,
            player_stamina=int(self.state.stats.get("stamina", 0)),
            enemy_stamina=int(self.enemy_stamina),
            luck_used=luck_used,
            luck_roll=luck_roll_total,
            luck_success=luck_success,
            luck_after=luck_after,
        )

        return logs

    # -----------------------------
    # Flee mechanic
    # -----------------------------

    def flee(self, *, use_luck: bool = False) -> List[str]:
        if self.finished:
            return ["(Combat already finished.)"]

        p_stam_before = int(self.state.stats.get("stamina", 0))

        base = 2
        if self.profile.flee:
            base = int(self.profile.flee.base_damage or 2)

        dmg = int(base)

        logs: List[str] = []
        logs.append("You attempt to flee...")

        luck_used = False
        luck_roll_total: Optional[int] = None
        luck_success: Optional[bool] = None
        luck_after: Optional[int] = None

        if use_luck and self.profile.luck:
            luck_used = True
            luck_success, luck_roll_total, luck_after = self._try_luck()

            lr = self.profile.luck
            dmg = int(lr.on_player_hurt_success_damage if luck_success else lr.on_player_hurt_fail_damage)

            logs.append(f"Test your Luck! You roll {luck_roll_total} -> {'LUCKY' if luck_success else 'UNLUCKY'}")

        self.state.stats["stamina"] = p_stam_before - int(dmg)
        if int(self.state.stats.get("stamina", 0)) < 0:
            self.state.stats["stamina"] = 0

        logs.append(f"You escape, but take a blow while fleeing. (-{dmg} STAMINA)")
        logs.append(
            f"Current STAMINA — You: {int(self.state.stats.get('stamina', 0))} | {self.enemy_name}: {self.enemy_stamina}"
        )

        self.finished = True
        self.won = False

        self._last_round = CombatRoundResult(
            player_roll=(0, 0),
            enemy_roll=(0, 0),
            player_attack=0,
            enemy_attack=0,
            damage_to_enemy=0,
            damage_to_player=int(dmg),
            outcome="enemy_hit",
            player_stamina=int(self.state.stats.get("stamina", 0)),
            enemy_stamina=int(self.enemy_stamina),
            luck_used=luck_used,
            luck_roll=luck_roll_total,
            luck_success=luck_success,
            luck_after=luck_after,
        )

        return logs