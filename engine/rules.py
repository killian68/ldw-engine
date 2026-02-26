from __future__ import annotations

from typing import Tuple, Any, Optional

from engine.models import GameState, Choice, ChoiceCondition, ChoiceEffect, Modifier, Event


def inventory_has_item(state: GameState, key: str | None, text: str | None) -> bool:
    inv_lower = [x.strip().lower() for x in state.inventory]
    if key:
        k = key.strip().lower()
        # key matching: allow "rope" to match a line that contains "rope".
        return any(k in line for line in inv_lower)
    if text:
        t = text.strip().lower()
        return any(t in line for line in inv_lower)
    return True


def is_choice_available(state: GameState, choice: Choice) -> bool:
    for cond in choice.conditions:
        if not _check_condition(state, cond):
            return False
    return True


def _check_condition(state: GameState, cond: ChoiceCondition) -> bool:
    return inventory_has_item(state, cond.has_item_key, cond.has_item_text)


def apply_choice_effects(state: GameState, choice: Choice) -> None:
    for eff in choice.effects:
        _apply_effect(state, eff)


def _apply_effect(state: GameState, eff: ChoiceEffect) -> None:
    if eff.add_item:
        state.inventory.append(eff.add_item)

    if eff.remove_item:
        # remove first matching (case-insensitive contains)
        target = eff.remove_item.strip().lower()
        for i, line in enumerate(state.inventory):
            if target in line.strip().lower():
                state.inventory.pop(i)
                break

    if eff.set_flag:
        state.flags[eff.set_flag] = True

    if eff.clear_flag:
        state.flags[eff.clear_flag] = False

    if eff.modify_stat:
        for k, delta in eff.modify_stat.items():
            state.stats[k] = int(state.stats.get(k, 0)) + int(delta)


def clamp_stats(
    state: GameState,
    keys: Tuple[str, ...] = ("stamina", "luck"),
    *,
    clamp_min_zero: bool = True,
    clamp_to_base: bool = True,
) -> None:
    """
    Clamp stats in state.stats:
      - min: 0 (optional)
      - max: state.base_stats[k] (optional, if present)

    Default behavior fits FF/Sorcellerie:
      - stamina/luck never below 0
      - stamina/luck never above their initial/max (base_stats)
    """
    base = getattr(state, "base_stats", None)

    for k in keys:
        if k not in state.stats:
            continue

        v = int(state.stats.get(k, 0))

        if clamp_min_zero and v < 0:
            v = 0

        if clamp_to_base and isinstance(base, dict):
            b = base.get(k)
            if b is not None:
                b = int(b)
                if v > b:
                    v = b

        state.stats[k] = v


# Backward-compatible alias (so you don't have to refactor all callers)
def clamp_stats_non_negative(state: GameState, keys: Tuple[str, ...] = ("stamina",)) -> None:
    """
    Legacy helper: previously only clamped to >=0.
    Now also clamps to base_stats if present, for the given keys.
    """
    clamp_stats(state, keys=keys, clamp_min_zero=True, clamp_to_base=True)


# -----------------------------
# Runtime modifiers (NEW)
# -----------------------------

def add_modifier(state: GameState, payload: dict[str, Any]) -> None:
    """
    Add a runtime modifier to state.modifiers.

    Expected keys in payload (from book_loader):
      - source (str)
      - target (str) e.g. "stat:skill"
      - op (str) default "add"
      - value (int)
      - scope (str) "paragraph"|"scene"|"global"
      - ref (str|None)
      - label (str|None) optional (user-facing)
    """
    mods = getattr(state, "modifiers", None)
    if mods is None:
        # backward compatibility if older GameState doesn't have modifiers
        state.modifiers = []
        mods = state.modifiers

    source = str(payload.get("source") or "environment")
    target = str(payload.get("target") or "").strip()
    if not target:
        return

    op = str(payload.get("op") or "add").strip().lower() or "add"
    value = int(payload.get("value") or 0)
    scope = str(payload.get("scope") or "paragraph").strip().lower() or "paragraph"
    ref = payload.get("ref", None)
    if ref is not None:
        ref = str(ref).strip() or None

    label = payload.get("label", None)
    if label is not None:
        label = str(label).strip() or None

    if scope not in ("paragraph", "scene", "global"):
        scope = "paragraph"

    # If a ref is provided, replace existing with same ref (prevents stacking duplicates)
    if ref:
        mods[:] = [m for m in mods if getattr(m, "ref", None) != ref]

    mods.append(
        Modifier(
            source=source,
            target=target,
            op=op,
            value=int(value),
            scope=scope,
            ref=ref,
            label=label,  # requires label field in Modifier; if you didn't add it yet, remove this line
        )
    )


def remove_modifier(state: GameState, *, ref: str) -> None:
    mods = getattr(state, "modifiers", None)
    if not mods:
        return
    r = ref.strip()
    if not r:
        return
    mods[:] = [m for m in mods if getattr(m, "ref", None) != r]


def clear_modifiers(state: GameState, *, scope: str = "paragraph") -> None:
    mods = getattr(state, "modifiers", None)
    if not mods:
        return

    s = (scope or "paragraph").strip().lower()
    if s not in ("paragraph", "scene", "global"):
        s = "paragraph"

    mods[:] = [m for m in mods if (getattr(m, "scope", "paragraph") or "paragraph").strip().lower() != s]


def purge_paragraph_modifiers(state: GameState) -> None:
    """
    Convenience helper: call this automatically when moving to a new paragraph.
    """
    clear_modifiers(state, scope="paragraph")


def apply_event(state: GameState, event: Event) -> None:
    """
    Minimal event applier for modifier events.
    (Other event types like combat/test are handled elsewhere.)
    """
    et = (event.type or "").strip().lower()
    payload = event.payload

    if et == "modifiers.add":
        if isinstance(payload, dict):
            add_modifier(state, payload)
        return

    if et == "modifiers.remove":
        if isinstance(payload, dict):
            ref = str(payload.get("ref") or "").strip()
            if ref:
                remove_modifier(state, ref=ref)
        return

    if et == "modifiers.clear":
        if isinstance(payload, dict):
            scope = str(payload.get("scope") or "paragraph").strip()
            clear_modifiers(state, scope=scope)
        return

    # unknown event type: ignore
    return