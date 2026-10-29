"""Bounded complete arrangements and spending orders for combat comparison.

Community compositions are refitted to current canonical packing slots. Their
historical coordinates and reported waves are not reproduced by these plans.
"""
from dataclasses import replace
import math

from .models import Tower, Board
from .layout import completion_plan
from .search import LayoutPlan, build_order
from .simulation import client_distance


# Native kinds: Frozone3, Storm4, Party5, Kraken6, Poison7, Void8.
# Numbered diagrams: https://www.youtube.com/watch?v=2VhL1jGHCi0&t=95s
# and https://www.youtube.com/watch?v=DlpakmVysiQ&t=90s . Frosty's duplicate
# label16 leaves its third Poison/fifth Party order unspecified.
_CITRIC = (7, 3, 8, 6, 7, 6, 3, 5, 5, 5, 5, 6, 6, 6, 3, 5, 5, 7, 6, 6, 6)
_FROSTY = (4, 7, 7, 5, 5, 5, 5, 8, 6, 6, 6, 3, 6, 6, 6, 7, 5, 3, 6, 6, 6)
_ALTERNATE = (7, 3, 6, 8, 7, 5, 6, 4, 7, 5, 6, 3)
_DAMAGE = (7, 7, 4, 3, 6, 5, 8, 7)
_TRAITS = ('A', 'B', 'B', 'A', 'BBBBBA', 'A', 'BAAAA', 'ABABB', 'B')
_DAMAGE_PRIORITY = (7, 2, 0, 1, 4, 6, 3, 8, 5)


def _integer(value, label, *, minimum=0, maximum=None):
    if (type(value) is not int or value < minimum
            or maximum is not None and value > maximum):
        raise ValueError(f'{label} is outside the supported integer bounds.')
    return value


def _choices(tower, level, *, citric, alternate, pending):
    pattern = 'AAAAB' if tower.kind == 5 and citric else _TRAITS[tower.kind]
    result = tower.choices
    while len(result) < level // 5:
        index = len(result)
        choice = pattern[min(index, len(pattern) - 1)]
        if alternate:
            choice = 'B' if choice == 'A' else 'A'
        if index == len(tower.choices) and index < tower.level // 5:
            choice = pending
        result += choice
    return result


def _slot_orders(state, slots, *, reverse):
    platforms = {p.node:p for p in state.platforms}
    route = {node:index for index, node in enumerate(state.route)}
    routed = sorted((slot for slot in slots if slot[0] in route), key=lambda slot:(
        route[slot[0]], platforms[slot[0]].direction * slot[1]))
    if reverse:
        routed.reverse()
    def distance(slot):
        node, x = slot
        y = platforms[node].y
        return min((client_distance(x, y, min(max(x, p.left), p.right), p.y)
                    for p in state.platforms if p.node in route), default=0)
    supports = sorted((slot for slot in slots if slot[0] not in route),
                      key=lambda slot:(distance(slot), slot))
    if reverse and not route:
        supports.reverse()
    return routed, supports


def _layout(state, slots, seed, *, reverse, target_level, max_towers, alternate, pending):
    routed, supports = _slot_orders(state, slots, reverse=reverse)
    available = {kind for kind, level in enumerate(state.construction) if level >= 1}
    fallback = next(kind for kind in _DAMAGE_PRIORITY if kind in available)
    desired = list(seed)
    for fixed in state.towers:
        if fixed.kind in desired:
            desired.remove(fixed.kind)
    sequence = [kind if kind in available else fallback for kind in desired]
    if not sequence:
        sequence = [fallback]
    result = []
    for index, old in enumerate(state.towers):
        level = max(old.level, target_level)
        result.append(replace(old, level=level, choices=_choices(
            old, level, citric=seed is _CITRIC, alternate=alternate, pending=pending[index])))
    platforms = {p.node:p for p in state.platforms}
    for index in range(min(len(slots), max(0, max_towers - len(state.towers)))):
        kind = sequence[index % len(sequence)]
        preferred = supports if kind == 5 else routed
        other = routed if kind == 5 else supports
        node, x = (preferred if preferred else other).pop(0)
        old = Tower(kind, node, x, platforms[node].y)
        result.append(replace(old, level=target_level, choices=_choices(
            old, target_level, citric=seed is _CITRIC, alternate=alternate, pending='A')))
    return tuple(result)


def candidates(state: Board, *, limit=12, max_towers=24, target_level=20) -> tuple[LayoutPlan, ...]:
    """Return complete bounded plans without assigning a combat score.

    Fixed rows remain the prefix. Unused canonical slots stay available even
    when the tower bound truncates a composition. Current pending choices
    receive A/B alternatives before other candidate dimensions.
    """
    _integer(limit, 'Candidate limit')
    _integer(max_towers, 'Tower bound')
    _integer(target_level, 'Target level', minimum=1, maximum=100)
    if not isinstance(state, Board):
        raise ValueError('A Worship state is required.')
    if (len(state.construction) != 9 or any(
            isinstance(level, bool) or not isinstance(level, (int, float))
            or not math.isfinite(level) or level < 0 for level in state.construction)):
        raise ValueError('Nine finite nonnegative construction levels are required.')
    for tower in state.towers:
        _integer(tower.level, 'Existing level', minimum=1, maximum=100)
        _integer(tower.kind, 'Existing kind', maximum=8)
        if len(tower.choices) > tower.level // 5 or any(ch not in 'AB' for ch in tower.choices):
            raise ValueError('Existing choices must be a valid earned prefix.')
    if not limit or not state.active or not any(level >= 1 for level in state.construction):
        return ()
    slots = completion_plan(state)
    pending_rows = [i for i, tower in enumerate(state.towers) if len(tower.choices) < tower.level // 5]
    all_a = {index:'A' for index in range(len(state.towers))}
    pending_modes = [all_a]
    if pending_rows:
        pending_modes.append({**all_a, **{i:'B' for i in pending_rows}})
    recipes = (
        ('citric-refit', _CITRIC, False, False, 'balanced', 'clear'),
        ('frosty-refit', _FROSTY, True, False, 'expand', 'clear'),
        ('control-alternate', _ALTERNATE, False, False, 'establish', 'rush'),
        ('damage-alternate', _DAMAGE, True, False, 'balanced', 'clear'),
        ('citric-traits', _CITRIC, True, True, 'expand', 'rush'),
        ('frosty-traits', _FROSTY, False, True, 'establish', 'hold'),
    )
    plans = []
    seen = set()
    def append(recipe, choices, style=None, send=None):
        name, seed, reverse, alternate, default_style, default_send = recipe
        style, send = style or default_style, send or default_send
        layout = _layout(state, slots, seed, reverse=reverse, target_level=target_level,
                         max_towers=max_towers, alternate=alternate, pending=choices)
        steps = build_order(state, layout, style=style)
        key = layout, steps, send
        if key not in seen:
            seen.add(key)
            plans.append(LayoutPlan(f'{name}-{style}-{send}-{len(plans)+1}', layout, steps, send))
    for choices in pending_modes:
        append(recipes[0], choices)
        if len(plans) >= limit:
            return tuple(plans)
    for recipe in recipes:
        append(recipe, all_a)
        if len(plans) >= limit:
            return tuple(plans)
    if len(pending_rows) > 1:
        for index in pending_rows:
            append(recipes[0], {**all_a, index:'B'})
            if len(plans) >= limit:
                return tuple(plans)
    for style, send in (('establish', 'clear'), ('expand', 'rush'), ('balanced', 'hold')):
        for recipe in recipes:
            append(recipe, all_a, style, send)
            if len(plans) >= limit:
                return tuple(plans)
    return tuple(plans)
