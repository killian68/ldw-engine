from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional, Literal

from engine.models import GameState, CombatSpec


CombatOutcome = Literal["player_hit", "enemy_hit", "tie"]


@dataclass
class CombatRoundResult:
    """
    Structured outcome for a single combat round.
    - player_roll / enemy_roll: (d6, d6)
    - player_attack / enemy_attack: Skill + 2d6
    - damage_to_enemy / damage_to_player: classic FF is 0 or 2
    - outcome: who was hit, or tie
    - player_stamina / enemy_stamina: post-round values
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


class CombatSession:
    """
    FF classic combat:
    - Each round: both roll 2d6, add Skill -> Attack Strength
    - Higher Attack Strength inflicts 2 stamina damage
    - Tie => no damage
    - Ends when either stamina <= 0
    """

    def __init__(self, state: GameState, spec: CombatSpec, rng: random.Random):
        self.state = state
        self.spec = spec
        self.rng = rng

        self.enemy_name = spec.enemy_name
        self.enemy_skill = int(spec.enemy_skill)
        self.enemy_stamina = int(spec.enemy_stamina)

        self.finished: bool = False
        self.won: bool = False

        self._last_round: Optional[CombatRoundResult] = None

    def start_log(self) -> List[str]:
        p_skill = int(self.state.stats.get("skill", 0))
        p_stam = int(self.state.stats.get("stamina", 0))
        return [
            "Combat begins!",
            f"You: SKILL {p_skill} / STAMINA {p_stam}",
            f"{self.enemy_name}: SKILL {self.enemy_skill} / STAMINA {self.enemy_stamina}",
            "",
            "Click 'Roll next round' to roll the dice.",
        ]

    def roll_2d6(self) -> tuple[int, int]:
        return (self.rng.randint(1, 6), self.rng.randint(1, 6))

    def roll_round(self) -> List[str]:
        """
        Executes one round and returns human logs.
        Also sets self._last_round (structured result).
        """
        if self.finished:
            return ["(Combat already finished.)"]

        p_skill = int(self.state.stats.get("skill", 0))
        p_stam = int(self.state.stats.get("stamina", 0))

        pr = self.roll_2d6()
        er = self.roll_2d6()

        p_attack = p_skill + pr[0] + pr[1]
        e_attack = self.enemy_skill + er[0] + er[1]

        dmg_to_enemy = 0
        dmg_to_player = 0
        outcome: CombatOutcome = "tie"

        logs: List[str] = []
        logs.append(f"You roll {pr[0]} + {pr[1]} (Attack Strength: {p_attack})")
        logs.append(f"{self.enemy_name} rolls {er[0]} + {er[1]} (Attack Strength: {e_attack})")

        if p_attack > e_attack:
            dmg_to_enemy = 2
            self.enemy_stamina -= dmg_to_enemy
            outcome = "player_hit"
            logs.append(f"You strike {self.enemy_name}! (-{dmg_to_enemy} STAMINA)")
        elif e_attack > p_attack:
            dmg_to_player = 2
            self.state.stats["stamina"] = p_stam - dmg_to_player
            outcome = "enemy_hit"
            logs.append(f"{self.enemy_name} strikes you! (-{dmg_to_player} STAMINA)")
        else:
            outcome = "tie"
            logs.append("You clash — no damage this round.")

        # Clamp to 0+
        if int(self.state.stats.get("stamina", 0)) < 0:
            self.state.stats["stamina"] = 0
        if self.enemy_stamina < 0:
            self.enemy_stamina = 0

        # ✅ Stamina summary line (FF-style)
        logs.append(
            f"Current STAMINA — You: {int(self.state.stats.get('stamina', 0))} | "
            f"{self.enemy_name}: {self.enemy_stamina}"
        )

        # Determine finish
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
            damage_to_enemy=dmg_to_enemy,
            damage_to_player=dmg_to_player,
            outcome=outcome,
            player_stamina=int(self.state.stats.get("stamina", 0)),
            enemy_stamina=int(self.enemy_stamina),
        )

        return logs

    def last_round(self) -> Optional[CombatRoundResult]:
        return self._last_round