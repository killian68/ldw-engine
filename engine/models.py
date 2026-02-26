from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# -------------------------
# Core book structures
# -------------------------

@dataclass
class Assets:
    base_path: str = ""
    images: Dict[str, str] = field(default_factory=dict)  # asset_id -> relative file path


@dataclass
class CharacterCreationSpec:
    """
    Optional character creation definition (FF / Sorcery style).

    - default_profile: profile_id selected by default in UI
    - profiles: list of profiles/classes (e.g. adventurer, mage)
    """
    default_profile: Optional[str] = None
    profiles: List["CharacterProfile"] = field(default_factory=list)


# -------------------------
# Declarative rules (data-only)
# -------------------------

@dataclass
class TestRule:
    """
    Declarative stat test rule (data-only).
    Example: luck_test: roll 2d6 <= luck, consume 1 luck
    """
    test_id: str
    stat: str
    dice: str = "2d6"
    success_if: str = "roll<=stat"
    consume: int = 0


@dataclass
class LuckRule:
    """
    Luck mapping for combat outcomes (data-only).
    """
    test_ref: str = "luck_test"
    on_player_hit_success_damage: int = 4
    on_player_hit_fail_damage: int = 1
    on_player_hurt_success_damage: int = 1
    on_player_hurt_fail_damage: int = 3


@dataclass
class FleeRule:
    """
    Flee rule (data-only).
    """
    base_damage: int = 2
    luck_like: str = "onPlayerHurt"  # semantic mapping name


@dataclass
class CombatProfile:
    """
    Declarative combat profile (data-only).
    Defaults match classic FF:
      - attack: 2d6 + skill
      - damage: 2
      - tie: no damage
      - optional luck and flee rules
    """
    combat_id: str

    attack_dice: str = "2d6"
    attack_stat: str = "skill"

    tie_policy: str = "no_damage"
    base_damage: int = 2

    luck: Optional[LuckRule] = None
    flee: Optional[FleeRule] = None


@dataclass
class Ruleset:
    name: str = "basic"
    dice_sides: int = 6
    stat_defaults: Dict[str, int] = field(default_factory=dict)  # fallback values
    character_creation: Optional[CharacterCreationSpec] = None   # optional profiles/rolls

    # Declarative rules declared in the book's ruleset (formatVersion >= 1.1)
    tests: Dict[str, TestRule] = field(default_factory=dict)
    combat_profiles: Dict[str, CombatProfile] = field(default_factory=dict)


@dataclass
class ChoiceCondition:
    # Very simple v1: allow either key-based or text-based item check
    has_item_key: Optional[str] = None
    has_item_text: Optional[str] = None


@dataclass
class ChoiceEffect:
    add_item: Optional[str] = None
    remove_item: Optional[str] = None
    set_flag: Optional[str] = None
    clear_flag: Optional[str] = None
    modify_stat: Optional[Dict[str, int]] = None  # {stat_id: delta}


@dataclass
class Choice:
    label: str
    target: str
    conditions: List[ChoiceCondition] = field(default_factory=list)
    effects: List[ChoiceEffect] = field(default_factory=list)


@dataclass
class CharacterProfile:
    """
    A playable class/profile (e.g. Adventurer, Mage).

    stat_rolls:
      - mapping {stat_id: roll_expr}
      - roll_expr uses NdM±K (e.g. 1d6+6, 2d6+12)

    effects:
      - initial effects applied once after rolling (flags/items/stats adjustments)
    """
    profile_id: str
    label: str = ""
    stat_rolls: Dict[str, str] = field(default_factory=dict)
    effects: List[ChoiceEffect] = field(default_factory=list)


# -------------------------
# Events (ruleset-compliant)
# -------------------------

@dataclass
class CombatSpec:
    enemy_name: str
    enemy_skill: int
    enemy_stamina: int
    on_win_goto: str
    on_lose_goto: str

    # Optional ref to a declarative combat profile in Ruleset
    rules_ref: Optional[str] = None

    # NEW: allow flee per-event (XML allowFlee="0/1", "true/false", etc. parsed in loader)
    allow_flee: bool = False


@dataclass
class TestSpec:
    """
    Generic stat test (ruleset-driven in strict mode).

    In strict mode:
      - stat_id may be empty and resolved from test_ref
      - dice/consume fields are ignored if test_ref exists
    """
    stat_id: str = ""   # <-- now optional / may be resolved from test_ref
    dice: str = "2d6"
    success_goto: str = ""
    fail_goto: str = ""
    consume_on_success: int = 0
    consume_on_fail: int = 0

    # Reference to declarative test rule in Ruleset (recommended in strict mode)
    test_ref: Optional[str] = None


@dataclass
class Event:
    type: str
    payload: Any


@dataclass
class Paragraph:
    pid: str
    text: str
    image_ref: Optional[str] = None
    choices: List[Choice] = field(default_factory=list)
    events: List[Event] = field(default_factory=list)


@dataclass
class Book:
    book_id: str
    title: str
    version: str
    start_paragraph: str
    assets: Assets
    ruleset: Ruleset
    paragraphs: Dict[str, Paragraph]


# -------------------------
# Runtime modifiers (NEW)
# -------------------------

@dataclass
class Modifier:
    """
    Generic modifier applied at runtime (buff/debuff/environment).

    target examples:
      - "stat:skill"
      - "stat:stamina"
      - "tag:ranged_attack" (if you later add tag-based resolution)

    scope:
      - "paragraph": active while current paragraph is active
      - "scene": active for a whole scene/chapter until cleared
      - "global": active until explicitly removed
    """
    source: str
    target: str
    op: str = "add"
    value: int = 0
    scope: str = "paragraph"
    ref: Optional[str] = None
    label: Optional[str] = None


# -------------------------
# Runtime state
# -------------------------

@dataclass
class GameState:
    """
    Runtime state.

    stats:
      - current/variable values (what changes during play)

    base_stats:
      - initial/max reference values (useful for:
          - showing "current / max"
          - clamping heals above max
          - persisting character creation results
        )

    Notes:
      - history / return_stack are attached by the UI (app_tk) for navigation stacks.
        If you want them strictly typed, add them here too.
    """
    current_paragraph: str

    stats: Dict[str, int] = field(default_factory=dict)       # current values
    base_stats: Dict[str, int] = field(default_factory=dict)  # initial/max values

    inventory: List[str] = field(default_factory=list)
    flags: Dict[str, bool] = field(default_factory=dict)

    # NEW: active runtime modifiers (environment, buffs, etc.)
    modifiers: List[Modifier] = field(default_factory=list)