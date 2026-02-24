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


@dataclass
class Ruleset:
    name: str = "basic"
    dice_sides: int = 6
    stat_defaults: Dict[str, int] = field(default_factory=dict)  # fallback values
    character_creation: Optional[CharacterCreationSpec] = None   # optional profiles/rolls


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


@dataclass
class TestSpec:
    """
    Generic stat test (FF-friendly):
      - roll dice expression (default 2d6)
      - compare roll <= stat
      - optionally consume stat points (e.g. Luck decreases after test)
    """
    stat_id: str
    dice: str = "2d6"
    success_goto: str = ""
    fail_goto: str = ""
    consume_on_success: int = 0
    consume_on_fail: int = 0


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