from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from typing import Optional, Dict

from engine.models import (
    Assets, Ruleset, CharacterCreationSpec, CharacterProfile,
    Book, Paragraph, Choice, ChoiceCondition, ChoiceEffect,
    Event, CombatSpec, TestSpec,
    TestRule, CombatProfile, LuckRule, FleeRule,
)


def _get_attr_int(elem: Optional[ET.Element], name: str, default: int) -> int:
    if elem is None:
        return default
    val = elem.get(name)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default


def _first_text(elem: Optional[ET.Element]) -> str:
    if elem is None or elem.text is None:
        return ""
    return elem.text.strip()


def load_book(xml_path: str) -> Book:
    tree = ET.parse(xml_path)
    root = tree.getroot()
    if root.tag != "book":
        raise ValueError("Root element must be <book>")

    book_id = root.get("id", "unknown")
    title = root.get("title", "Untitled")
    version = root.get("version", "1.0")

    # -------------------------
    # Assets
    # -------------------------
    assets = Assets(base_path="")
    assets_elem = root.find("assets")
    if assets_elem is not None:
        assets.base_path = assets_elem.get("basePath", "") or ""
        for img in assets_elem.findall("image"):
            img_id = img.get("id")
            img_file = img.get("file")
            if img_id and img_file:
                assets.images[img_id] = img_file

    # -------------------------
    # Ruleset
    # -------------------------
    ruleset = Ruleset()
    ruleset_elem = root.find("ruleset")
    if ruleset_elem is not None:
        ruleset.name = ruleset_elem.get("name", "basic")

        dice_elem = ruleset_elem.find("dice")
        if dice_elem is not None:
            ruleset.dice_sides = _get_attr_int(dice_elem, "sides", 6)

        # ---- Optional: character creation (profiles / classes) ----
        cc_elem = ruleset_elem.find("characterCreation")
        if cc_elem is not None:
            cc = CharacterCreationSpec(
                default_profile=(cc_elem.get("defaultProfile") or "").strip() or None
            )

            for p in cc_elem.findall("profile"):
                pid = (p.get("id") or "").strip()
                if not pid:
                    continue

                prof = CharacterProfile(
                    profile_id=pid,
                    label=(p.get("label") or pid).strip(),
                    stat_rolls={},
                    effects=[]
                )

                # New format: <roll stat="skill" expr="1d6+6" />
                for r in p.findall("roll"):
                    sid = (r.get("stat") or "").strip()
                    expr = (r.get("expr") or "").strip()
                    if sid and expr:
                        prof.stat_rolls[sid] = expr

                # Backward-compatible format: <stat id="skill" roll="1d6+6" />
                for s in p.findall("stat"):
                    sid = (s.get("id") or s.get("name") or "").strip()
                    expr = (s.get("roll") or "").strip()
                    if sid and expr:
                        prof.stat_rolls.setdefault(sid, expr)

                if not prof.stat_rolls:
                    # gentle diagnostics
                    prof.effects.append(ChoiceEffect(set_flag=f"warn_empty_profile_{pid}"))

                effects = p.find("effects")
                if effects is not None:
                    for add in effects.findall("addItem"):
                        t = add.get("text")
                        if t:
                            prof.effects.append(ChoiceEffect(add_item=t))

                    for rem in effects.findall("removeItem"):
                        t = rem.get("text")
                        if t:
                            prof.effects.append(ChoiceEffect(remove_item=t))

                    for sf in effects.findall("setFlag"):
                        k = sf.get("key")
                        if k:
                            prof.effects.append(ChoiceEffect(set_flag=k))

                    for cf in effects.findall("clearFlag"):
                        k = cf.get("key")
                        if k:
                            prof.effects.append(ChoiceEffect(clear_flag=k))

                    for ms in effects.findall("modifyStat"):
                        sid = ms.get("id") or ms.get("name")
                        delta = _get_attr_int(ms, "delta", 0)
                        if sid:
                            prof.effects.append(ChoiceEffect(modify_stat={sid: delta}))

                cc.profiles.append(prof)

            if cc.profiles:
                ruleset.character_creation = cc

        # ---- Stat defaults (fallback values) ----
        stats_elem = ruleset_elem.find("stats")
        if stats_elem is not None:
            defaults: Dict[str, int] = {}
            for s in stats_elem.findall("stat"):
                sid = s.get("id") or s.get("name")
                default = _get_attr_int(s, "default", 0)
                if sid:
                    defaults[sid] = default
            if defaults:
                ruleset.stat_defaults = defaults

        # ---- Declarative tests (v1.1) ----
        tests_elem = ruleset_elem.find("tests")
        if tests_elem is not None:
            for t in tests_elem.findall("test"):
                tid = (t.get("id") or "").strip()
                if not tid:
                    continue
                stat = (t.get("stat") or "").strip()
                if not stat:
                    continue
                rule = TestRule(
                    test_id=tid,
                    stat=stat,
                    dice=(t.get("dice") or "2d6").strip(),
                    success_if=(t.get("successIf") or "roll<=stat").strip(),
                    consume=_get_attr_int(t, "consume", 0),
                )
                ruleset.tests[tid] = rule

        # ---- Declarative combat profiles (v1.1) ----
        cps_elem = ruleset_elem.find("combatProfiles")
        if cps_elem is not None:
            for c in cps_elem.findall("combat"):
                cid = (c.get("id") or "").strip()
                if not cid:
                    continue

                # attack
                attack_elem = c.find("attack")
                attack_dice = (attack_elem.get("dice") if attack_elem is not None else None) or "2d6"
                attack_stat = (attack_elem.get("stat") if attack_elem is not None else None) or "skill"

                # tie
                tie_elem = c.find("tie")
                tie_policy = (tie_elem.get("policy") if tie_elem is not None else None) or "no_damage"

                # damage
                dmg_elem = c.find("damage")
                base_damage = _get_attr_int(dmg_elem, "base", 2)

                # luck
                luck_elem = c.find("luck")
                luck_rule: Optional[LuckRule] = None
                if luck_elem is not None:
                    test_ref = (luck_elem.get("testRef") or "luck_test").strip()

                    on_hit = luck_elem.find("onPlayerHit")
                    on_hurt = luck_elem.find("onPlayerHurt")

                    luck_rule = LuckRule(
                        test_ref=test_ref,
                        on_player_hit_success_damage=_get_attr_int(on_hit, "successDamage", 4),
                        on_player_hit_fail_damage=_get_attr_int(on_hit, "failDamage", 1),
                        on_player_hurt_success_damage=_get_attr_int(on_hurt, "successDamage", 1),
                        on_player_hurt_fail_damage=_get_attr_int(on_hurt, "failDamage", 3),
                    )

                # flee
                flee_elem = c.find("flee")
                flee_rule: Optional[FleeRule] = None
                if flee_elem is not None:
                    flee_rule = FleeRule(
                        base_damage=_get_attr_int(flee_elem, "baseDamage", 2),
                        luck_like=(flee_elem.get("luckLike") or "onPlayerHurt").strip(),
                    )

                profile = CombatProfile(
                    combat_id=cid,
                    attack_dice=attack_dice.strip(),
                    attack_stat=attack_stat.strip(),
                    tie_policy=tie_policy.strip(),
                    base_damage=int(base_damage),
                    luck=luck_rule,
                    flee=flee_rule,
                )
                ruleset.combat_profiles[cid] = profile

    # -------------------------
    # Start
    # -------------------------
    start_elem = root.find("start")
    if start_elem is None or start_elem.get("paragraph") is None:
        raise ValueError("Missing <start paragraph='...'>")
    start_paragraph = start_elem.get("paragraph")  # type: ignore

    # -------------------------
    # Paragraph nodes
    # -------------------------
    para_nodes = root.findall("paragraph")
    if not para_nodes:
        para_nodes = root.findall("paragraphs/paragraph")

    paragraphs: Dict[str, Paragraph] = {}

    for p in para_nodes:
        pid = p.get("id")
        if not pid:
            continue

        text_elem = p.find("text")
        text = _first_text(text_elem)

        image_ref: Optional[str] = None
        img_elem = p.find("image")
        if img_elem is not None:
            image_ref = img_elem.get("ref")

        para = Paragraph(pid=pid, text=text, image_ref=image_ref)

        # -------------------------
        # Choices
        # -------------------------
        for c in p.findall("choice"):
            target = (c.get("target") or "").strip()
            if not target:
                continue

            label = c.get("label")
            if not label:
                label = _first_text(c) or "Continue"

            choice = Choice(label=label, target=target)

            conds = c.find("conditions")
            if conds is not None:
                for hi in conds.findall("hasItem"):
                    ccnd = ChoiceCondition(
                        has_item_key=hi.get("key"),
                        has_item_text=hi.get("text"),
                    )
                    choice.conditions.append(ccnd)

            effects = c.find("effects")
            if effects is not None:
                for add in effects.findall("addItem"):
                    t = add.get("text")
                    if t:
                        choice.effects.append(ChoiceEffect(add_item=t))

                for rem in effects.findall("removeItem"):
                    t = rem.get("text")
                    if t:
                        choice.effects.append(ChoiceEffect(remove_item=t))

                for sf in effects.findall("setFlag"):
                    k = sf.get("key")
                    if k:
                        choice.effects.append(ChoiceEffect(set_flag=k))

                for cf in effects.findall("clearFlag"):
                    k = cf.get("key")
                    if k:
                        choice.effects.append(ChoiceEffect(clear_flag=k))

                for ms in effects.findall("modifyStat"):
                    sid = ms.get("id") or ms.get("name")
                    delta = _get_attr_int(ms, "delta", 0)
                    if sid:
                        choice.effects.append(ChoiceEffect(modify_stat={sid: delta}))

            para.choices.append(choice)

        # -------------------------
        # Events
        # -------------------------
        for e in p.findall("event"):
            etype = (e.get("type", "") or "").strip().lower()
            if not etype:
                continue

            # ---- Combat ----
            if etype == "combat":
                enemy = e.find("enemy")
                on_win = e.find("onWin")
                on_lose = e.find("onLose")

                rules_ref = (e.get("rulesRef") or "").strip() or None
                allow_flee = (e.get("allowFlee") or "").strip().lower() in ("1", "true", "yes", "on")

                if enemy is not None and on_win is not None and on_lose is not None:
                    spec = CombatSpec(
                        enemy_name=enemy.get("name", "Enemy"),
                        enemy_skill=_get_attr_int(enemy, "skill", 6),
                        enemy_stamina=_get_attr_int(enemy, "stamina", 6),
                        on_win_goto=on_win.get("goto", start_paragraph),
                        on_lose_goto=on_lose.get("goto", start_paragraph),
                        rules_ref=rules_ref,
                        allow_flee=allow_flee,
                    )
                    para.events.append(Event(type="combat", payload=spec))
                    continue

                # compact format
                spec = CombatSpec(
                    enemy_name=e.get("enemyName", "Enemy"),
                    enemy_skill=_get_attr_int(e, "enemySkill", 6),
                    enemy_stamina=_get_attr_int(e, "enemyStamina", 6),
                    on_win_goto=e.get("onWin", start_paragraph),
                    on_lose_goto=e.get("onLose", start_paragraph),
                    rules_ref=rules_ref,
                    allow_flee=allow_flee,
                )
                para.events.append(Event(type="combat", payload=spec))
                continue

            # ---- Test (strict: testRef drives everything) ----
            if etype == "test":
                test_ref = (e.get("testRef") or "").strip() or None
                stat_id = (e.get("stat") or "").strip()

                # If stat omitted but testRef exists, resolve stat from ruleset.tests
                if not stat_id and test_ref:
                    tr = ruleset.tests.get(test_ref)
                    if tr:
                        stat_id = (tr.stat or "").strip()

                # Strict mode: require either a stat_id OR a valid test_ref that resolves stat
                if not stat_id:
                    continue

                spec = TestSpec(
                    stat_id=stat_id,
                    dice=(e.get("dice") or "").strip(),  # strict: empty means "use ruleset"
                    success_goto=(e.get("successGoto") or "").strip(),
                    fail_goto=(e.get("failGoto") or "").strip(),
                    consume_on_success=_get_attr_int(e, "consumeOnSuccess", 0),
                    consume_on_fail=_get_attr_int(e, "consumeOnFail", 0),
                    test_ref=test_ref,
                )

                if not spec.success_goto or not spec.fail_goto:
                    continue

                para.events.append(Event(type="test", payload=spec))
                continue

            # Unknown event types are ignored (forward-compatibility)

        paragraphs[pid] = para

    if start_paragraph not in paragraphs:
        raise ValueError(f"Start paragraph '{start_paragraph}' not found in book")

    return Book(
        book_id=book_id,
        title=title,
        version=version,
        start_paragraph=start_paragraph,
        assets=assets,
        ruleset=ruleset,
        paragraphs=paragraphs,
    )


def resolve_image_path(book_dir: str, assets: Assets, image_ref: str) -> str:
    """
    image_ref is an image id defined in <assets><image id="..." file="..."/>
    Returns absolute path.
    """
    rel = assets.images.get(image_ref, "")
    base = assets.base_path or ""
    return os.path.abspath(os.path.join(book_dir, base, rel))