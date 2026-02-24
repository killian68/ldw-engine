from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from engine.models import Book
from engine.book_loader import resolve_image_path

# Targets that are not paragraph IDs but control-flow directives handled by the engine.
SPECIAL_TARGETS = {"previous", "return"}

# PRO: module call prefix supported by app_tk.py (_goto)
CALL_PREFIX = "call:"

# Basic roll expression sanity check for character creation (NdM±K)
ROLL_EXPR_RE = re.compile(r"^\s*\d+\s*d\s*\d+\s*([+-]\s*\d+)?\s*$", re.IGNORECASE)


@dataclass
class Issue:
    severity: str  # "ERROR" | "WARNING" | "INFO"
    message: str
    paragraph_id: Optional[str] = None
    asset_id: Optional[str] = None


def _normalize_target(t: str) -> Tuple[str, Optional[str]]:
    """
    Returns (kind, value)
      kind:
        - "special" -> previous/return
        - "call"    -> call:<pid> (value=<pid>)
        - "pid"     -> regular paragraph id (value=<pid>)
        - "empty"   -> empty/whitespace
    """
    raw = (t or "").strip()
    if not raw:
        return "empty", None
    if raw in SPECIAL_TARGETS:
        return "special", raw
    if raw.startswith(CALL_PREFIX):
        inner = raw.split(":", 1)[1].strip()
        if not inner:
            return "empty", None
        return "call", inner
    return "pid", raw


def build_link_index(book: Book) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """
    Returns:
      outgoing[pid] = [target_pid, ...]
      incoming[pid] = [source_pid, ...]
    Notes:
      - special targets are ignored
      - call:<pid> is treated as a link to <pid>
    """
    outgoing: Dict[str, List[str]] = {pid: [] for pid in book.paragraphs.keys()}
    incoming: Dict[str, List[str]] = {pid: [] for pid in book.paragraphs.keys()}

    for pid, para in book.paragraphs.items():
        for c in para.choices:
            kind, val = _normalize_target(c.target)
            if kind in ("empty", "special"):
                continue
            assert val is not None
            outgoing[pid].append(val)
            if val in incoming:
                incoming[val].append(pid)

        # events: combat goto links
        for ev in para.events:
            if ev.type == "combat":
                spec = ev.payload
                for target in [spec.on_win_goto, spec.on_lose_goto]:
                    kind, val = _normalize_target(target)
                    if kind in ("empty", "special"):
                        continue
                    assert val is not None
                    outgoing[pid].append(val)
                    if val in incoming:
                        incoming[val].append(pid)

    # de-dup + keep stable-ish order
    for pid in outgoing:
        outgoing[pid] = list(dict.fromkeys(outgoing[pid]))
    for pid in incoming:
        incoming[pid] = list(dict.fromkeys(incoming[pid]))

    return outgoing, incoming


def compute_reachability(book: Book) -> Set[str]:
    """
    Simple DFS from start paragraph following:
      - choice targets (pid + call:<pid>)
      - event goto targets (combat win/lose)
    """
    outgoing, _incoming = build_link_index(book)
    start = book.start_paragraph

    visited: Set[str] = set()
    stack: List[str] = [start]

    while stack:
        pid = stack.pop()
        if pid in visited:
            continue
        visited.add(pid)
        for t in outgoing.get(pid, []):
            if t in book.paragraphs and t not in visited:
                stack.append(t)

    return visited


def validate_book(book: Book, book_dir: str) -> List[Issue]:
    issues: List[Issue] = []

    # ---- Start paragraph
    if book.start_paragraph not in book.paragraphs:
        issues.append(Issue(
            severity="ERROR",
            message=f"Start paragraph '{book.start_paragraph}' not found.",
            paragraph_id=book.start_paragraph
        ))

    # ---- Validate character creation (if present)
    allowed_stats = set(book.ruleset.stat_defaults.keys())

    cc = getattr(book.ruleset, "character_creation", None)
    if cc is not None:
        profiles = getattr(cc, "profiles", []) or []
        if not profiles:
            issues.append(Issue(
                severity="WARNING",
                message="ruleset.characterCreation present but contains no <profile>.",
                paragraph_id=None
            ))
        else:
            # default profile validity (optional)
            default_profile = getattr(cc, "default_profile", None)
            if default_profile:
                if not any(getattr(p, "profile_id", None) == default_profile for p in profiles):
                    issues.append(Issue(
                        severity="WARNING",
                        message=f"characterCreation defaultProfile '{default_profile}' does not match any profile id.",
                        paragraph_id=None
                    ))

            # validate profile stat ids and roll expressions
            for p in profiles:
                pid = getattr(p, "profile_id", "") or ""
                rolls = getattr(p, "stat_rolls", {}) or {}
                if not rolls:
                    issues.append(Issue(
                        severity="WARNING",
                        message=f"characterCreation profile '{pid}' has no <stat roll='...'> entries.",
                        paragraph_id=None
                    ))

                for stat_id, expr in rolls.items():
                    if allowed_stats and stat_id not in allowed_stats:
                        issues.append(Issue(
                            severity="ERROR",
                            message=f"characterCreation profile '{pid}' references unknown stat id '{stat_id}'. "
                                    f"Allowed: {sorted(allowed_stats)}",
                            paragraph_id=None
                        ))
                    if not expr or not ROLL_EXPR_RE.match(expr):
                        issues.append(Issue(
                            severity="ERROR",
                            message=f"characterCreation profile '{pid}' has invalid roll expression for '{stat_id}': '{expr}'. "
                                    f"Expected NdM±K (e.g., 1d6+6, 2d6+12).",
                            paragraph_id=None
                        ))

                # validate effects modifyStat stat ids
                for eff in getattr(p, "effects", []) or []:
                    ms = getattr(eff, "modify_stat", None)
                    if ms:
                        for stat_id in ms.keys():
                            if allowed_stats and stat_id not in allowed_stats:
                                issues.append(Issue(
                                    severity="ERROR",
                                    message=f"characterCreation profile '{pid}' uses modifyStat on unknown stat id '{stat_id}'. "
                                            f"Allowed: {sorted(allowed_stats)}",
                                    paragraph_id=None
                                ))

    # ---- Choice targets + event targets + endings
    for pid, para in book.paragraphs.items():
        # Choices
        for c in para.choices:
            kind, val = _normalize_target(c.target)
            if kind == "empty":
                issues.append(Issue(
                    severity="ERROR",
                    message=f"Choice has empty target (from paragraph '{pid}').",
                    paragraph_id=pid
                ))
                continue

            if kind == "special":
                continue

            assert val is not None
            if val not in book.paragraphs:
                src_t = (c.target or "").strip()
                issues.append(Issue(
                    severity="ERROR",
                    message=f"Choice target '{src_t}' not found (resolved to '{val}', from paragraph '{pid}').",
                    paragraph_id=pid
                ))

        # Events
        for ev in para.events:
            if ev.type == "combat":
                spec = ev.payload

                for which, raw in [("onWin", spec.on_win_goto), ("onLose", spec.on_lose_goto)]:
                    kind, val = _normalize_target(raw)
                    if kind == "empty":
                        issues.append(Issue(
                            severity="ERROR",
                            message=f"Combat {which} goto is empty (from paragraph '{pid}').",
                            paragraph_id=pid
                        ))
                        continue
                    if kind == "special":
                        continue
                    assert val is not None
                    if val not in book.paragraphs:
                        issues.append(Issue(
                            severity="ERROR",
                            message=f"Combat {which} goto '{raw}' not found (resolved to '{val}', from paragraph '{pid}').",
                            paragraph_id=pid
                        ))

            if ev.type == "test":
                spec = ev.payload
                # validate test stat id exists (when we can)
                if allowed_stats and spec.stat_id not in allowed_stats:
                    issues.append(Issue(
                        severity="ERROR",
                        message=f"Test event uses unknown stat id '{spec.stat_id}' (paragraph '{pid}'). "
                                f"Allowed: {sorted(allowed_stats)}",
                        paragraph_id=pid
                    ))

                # validate destinations
                for which, raw in [("successGoto", spec.success_goto), ("failGoto", spec.fail_goto)]:
                    kind, val = _normalize_target(raw)
                    if kind == "empty":
                        issues.append(Issue(
                            severity="ERROR",
                            message=f"Test {which} is empty (from paragraph '{pid}').",
                            paragraph_id=pid
                        ))
                        continue
                    if kind == "special":
                        continue
                    assert val is not None
                    if val not in book.paragraphs:
                        issues.append(Issue(
                            severity="ERROR",
                            message=f"Test {which} '{raw}' not found (resolved to '{val}', from paragraph '{pid}').",
                            paragraph_id=pid
                        ))

        # Paragraph endings
        if not para.choices and not para.events:
            issues.append(Issue(
                severity="WARNING",
                message=f"Paragraph '{pid}' has no choices and no events (may be an ending).",
                paragraph_id=pid
            ))

    # ---- Stats referenced in choice effects
    for pid, para in book.paragraphs.items():
        for c in para.choices:
            for eff in c.effects:
                if eff.modify_stat:
                    for stat_id in eff.modify_stat.keys():
                        if allowed_stats and stat_id not in allowed_stats:
                            issues.append(Issue(
                                severity="ERROR",
                                message=f"Unknown stat id '{stat_id}' used in modifyStat (paragraph '{pid}'). "
                                        f"Allowed: {sorted(allowed_stats)}",
                                paragraph_id=pid
                            ))

    # ---- Assets: image refs and missing files
    for pid, para in book.paragraphs.items():
        if para.image_ref:
            if para.image_ref not in book.assets.images:
                issues.append(Issue(
                    severity="ERROR",
                    message=f"Image ref '{para.image_ref}' not declared in <assets> (paragraph '{pid}').",
                    paragraph_id=pid,
                    asset_id=para.image_ref
                ))
            else:
                path = resolve_image_path(book_dir, book.assets, para.image_ref)
                if not os.path.exists(path):
                    issues.append(Issue(
                        severity="WARNING",
                        message=f"Image file missing for ref '{para.image_ref}': {path} (paragraph '{pid}').",
                        paragraph_id=pid,
                        asset_id=para.image_ref
                    ))

    # ---- Reachability
    reachable = compute_reachability(book)
    for pid in book.paragraphs.keys():
        if pid not in reachable:
            issues.append(Issue(
                severity="INFO",
                message=f"Paragraph '{pid}' is unreachable from start '{book.start_paragraph}'.",
                paragraph_id=pid
            ))

    # Sort: ERROR first, then WARNING, then INFO; stable by pid/message
    sev_rank = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    issues.sort(key=lambda x: (sev_rank.get(x.severity, 9), x.paragraph_id or "", x.message))
    return issues


def asset_usage(book: Book) -> Dict[str, List[str]]:
    """
    Returns mapping: image_ref -> [paragraph_id, ...]
    """
    usage: Dict[str, List[str]] = {}
    for pid, para in book.paragraphs.items():
        if para.image_ref:
            usage.setdefault(para.image_ref, []).append(pid)
    for k in usage:
        usage[k].sort()
    return usage


def _dot_escape(s: str) -> str:
    # DOT uses C-like escaping inside quotes
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def export_dot(book: Book, book_dir: str, out_path: str) -> None:
    """
    Export the book structure as a Graphviz DOT file.
    Node colors:
      - start: green
      - ending (no choices + no events): red
      - unreachable: gray
      - normal: default
    Edge styles:
      - combat: dashed
      - choice: solid
    Notes:
      - call:<pid> edges are exported as edges to <pid>
      - previous/return are omitted
    """
    outgoing, _incoming = build_link_index(book)
    reachable = compute_reachability(book)

    start = book.start_paragraph
    endings = {pid for pid, p in book.paragraphs.items() if (not p.choices and not p.events)}

    edges: List[Tuple[str, str, str, str]] = []  # (src, dst, label, style)
    for pid, para in book.paragraphs.items():
        # Choice edges (with label)
        for c in para.choices:
            kind, val = _normalize_target(c.target)
            if kind in ("empty", "special"):
                continue
            assert val is not None
            edges.append((pid, val, c.label, "solid"))

        # Event edges
        for ev in para.events:
            if ev.type == "combat":
                spec = ev.payload
                for dst, lbl in [(spec.on_win_goto, "Combat win"), (spec.on_lose_goto, "Combat lose")]:
                    kind, val = _normalize_target(dst)
                    if kind in ("empty", "special"):
                        continue
                    assert val is not None
                    edges.append((pid, val, lbl, "dashed"))
            if ev.type == "test":
                spec = ev.payload
                for dst, lbl in [(spec.success_goto, "Test success"), (spec.fail_goto, "Test fail")]:
                    kind, val = _normalize_target(dst)
                    if kind in ("empty", "special"):
                        continue
                    assert val is not None
                    edges.append((pid, val, lbl, "dotted"))

    # Write DOT
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("digraph Book {\n")
        f.write('  graph [rankdir=LR, bgcolor="white"];\n')
        f.write('  node  [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10, fillcolor="white"];\n')
        f.write('  edge  [fontname="Helvetica", fontsize=9, color="black"];\n\n')

        # Nodes
        for pid in sorted(book.paragraphs.keys(), key=lambda x: str(x)):
            fill = "white"
            fontcolor = "black"

            if pid == start:
                fill = "palegreen"
            elif pid not in reachable:
                fill = "lightgray"
                fontcolor = "gray25"
            elif pid in endings:
                fill = "mistyrose"

            label = _dot_escape(pid)
            f.write(f'  "{_dot_escape(pid)}" [label="{label}", fillcolor="{fill}", fontcolor="{fontcolor}"];\n')

        f.write("\n")

        # Edges
        for src, dst, label, style in edges:
            src_e = _dot_escape(src)
            dst_e = _dot_escape(dst)
            label_e = _dot_escape(label or "")
            if label_e:
                f.write(f'  "{src_e}" -> "{dst_e}" [label="{label_e}", style="{style}"];\n')
            else:
                f.write(f'  "{src_e}" -> "{dst_e}" [style="{style}"];\n')

        f.write("}\n")