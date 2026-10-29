"""Maximum remaining tower capacity within supplied platform intervals.

This is a geometry plan. Tower count does not establish combat performance.
"""
import math
from dataclasses import replace
from numbers import Real

from .models import Board, Tower


class LayoutUnavailable(ValueError):
    """The supplied geometry is outside supported placement constraints."""


def validate_placement(state: Board,tower: Tower) -> None:
    """Check a new anchor against platform height, packing and direct selection."""
    platform=next((p for p in state.platforms if p.node==tower.node),None)
    if platform is None or tower.y!=platform.y:
        raise LayoutUnavailable('A tower must use its platform height.')
    completion_plan(replace(state,towers=state.towers+(tower,)))
    nodes=_selection_geometry(state,{p.node:p for p in state.platforms})
    _check_selection(((tower.node,tower.x),),nodes)


def _coordinate(value, lower=-10000, upper=100000):
    """Use the memory reader's bounds, accepting boxed integer coordinates."""
    if not isinstance(value, Real) or isinstance(value, bool):
        raise LayoutUnavailable('Geometry coordinates must be finite numbers.')
    if not isinstance(value, int) and not math.isfinite(value):
        raise LayoutUnavailable('Geometry coordinates must be finite numbers.')
    if not lower <= value <= upper:
        raise LayoutUnavailable('Geometry coordinates exceed supported runtime bounds.')
    if value != int(value):
        raise LayoutUnavailable('Only integer-valued geometry is supported.')
    return int(value)


def _blocked(center, distance):
    """Integer points strictly closer than distance, with both endpoints legal."""
    return center-distance+1, center+distance-1


def _free_intervals(lo, hi, blocked):
    """Subtract a union of closed integer intervals in a single sorted sweep."""
    cursor = lo
    for start, end in sorted(blocked):
        if end < cursor:
            continue
        if start > hi:
            break
        if start > cursor:
            yield cursor, start-1
        cursor = max(cursor, end+1)
        if cursor > hi:
            return
    if cursor <= hi:
        yield cursor, hi


def _selection_geometry(state, platforms):
    """Include scene nodes omitted from the buildable platform intervals."""
    if not state.selection_nodes:
        return platforms
    nodes = {}
    for node in state.selection_nodes:
        if not isinstance(node.node, int) or isinstance(node.node, bool):
            raise LayoutUnavailable('Selection node IDs must be integers.')
        if node.node in nodes:
            raise LayoutUnavailable(f'Duplicate selection node {node.node}.')
        for coordinate in (node.left, node.right, node.y):
            _coordinate(coordinate)
        nodes[node.node] = node
    for node, platform in platforms.items():
        selection = nodes.get(node)
        if selection is None or (selection.left, selection.right, selection.y) != (
                platform.left, platform.right, platform.y):
            raise LayoutUnavailable(f'Selection geometry does not match platform {node}.')
    return nodes


def _check_selection(plan, nodes):
    """Require a direct integer-height click that reaches each intended node."""
    ordered = sorted(nodes.items())
    for target, x in plan:
        platform = nodes[target]
        blocked = []
        for node, earlier in ordered:
            if node >= target:
                break
            if earlier.left-5 < x < earlier.right+5:
                blocked.append((int(earlier.y)-79, int(earlier.y)+39))
        free = _free_intervals(int(platform.y)-79, int(platform.y)+39, blocked)
        if next(free, None) is None:
            raise LayoutUnavailable(f'Cannot directly select completion slot on node {target}.')


def completion_plan(state: Board) -> tuple[tuple[int, int], ...]:
    """Return a leftmost maximum-cardinality completion, excluding fixed towers.

    Each new slot has an integer x. Geometry must be integer-valued within the
    memory reader's bounds. Boxed floats representing integers are supported.
    Existing positions must satisfy platform, route, portal and spacing rules.
    Unsupported fixed positions raise LayoutUnavailable and are never moved.
    Horizontal camera offsets are unsupported. Each new slot must be directly
    selectable at its proposed x using some integer mouse height. Raw scene
    nodes omitted from packing can still intercept clicks. Fixed towers
    are not required to remain selectable.

    Earliest feasible placement is optimal by exchange: replacing the first
    new tower of any completion by an earlier legal point cannot reduce room
    for its successors. Repeat after each placement, including across holes.
    Independent platforms first give a capacity upper bound within the supplied
    buildable intervals. Return that plan
    only if all slots pass selection checks, which proves the bound attainable.
    Otherwise report unsupported geometry, rather than claim a smaller plan
    has maximum capacity. Indirect clicks that snap to the proposed x are not
    searched. Sorting blockers
    costs O((P+T+R) log(P+T+R)); the sweep and output cost O(P+T+R+K), where
    P, T, R and K count platforms, fixed towers, portals and returned slots.
    Selection checks add O(K*S*log(S+1)) for S raw scene nodes. They subtract
    intervals of blocked click heights without a per-pixel search.
    """
    if state.placement_offset_x != 0:
        raise LayoutUnavailable('Horizontal camera offsets are unsupported for placement.')
    platforms = {}
    for platform in state.platforms:
        if not isinstance(platform.node, int) or isinstance(platform.node, bool):
            raise LayoutUnavailable('Platform node IDs must be integers.')
        if platform.node in platforms:
            raise LayoutUnavailable(f'Duplicate platform node {platform.node}.')
        for coordinate in (platform.left, platform.right, platform.y):
            _coordinate(coordinate)
        if platform.right <= platform.left:
            raise LayoutUnavailable(f'Invalid width on platform {platform.node}.')
        if platform.direction not in (-1, 1):
            raise LayoutUnavailable(f'Invalid direction on platform {platform.node}.')
        platforms[platform.node] = platform

    selection_nodes = _selection_geometry(state, platforms)
    portals = {node: [] for node in platforms}
    fixed = {node: [] for node in platforms}
    for node, x in state.portals:
        # The reader adds 20px to the bounded source portal x coordinate.
        x = _coordinate(x, -9980, 100020)
        if node in portals:
            portals[node].append(x)
    for tower in state.towers:
        x = _coordinate(tower.x)
        _coordinate(tower.y)
        if tower.node not in platforms:
            raise LayoutUnavailable(f'Fixed tower references unknown node {tower.node}.')
        fixed[tower.node].append(x)

    plan = []
    for node, platform in sorted(platforms.items()):
        left, right = int(platform.left), int(platform.right)
        lo, hi = left+30, right-30
        if state.route and node == state.route[0]:
            if platform.direction == 1:
                lo = max(lo, left+80)
            else:
                hi = min(hi, right-80)
        if state.route and node == state.route[-1]:
            if platform.direction == 1:
                hi = min(hi, right-80)
            else:
                lo = max(lo, left+80)

        positions = sorted(fixed[node])
        for x in positions:
            if not lo <= x <= hi:
                raise LayoutUnavailable(f'Fixed tower on node {node} violates current edge margins.')
        if any(b-a < 61 for a, b in zip(positions, positions[1:])):
            raise LayoutUnavailable(f'Fixed towers on node {node} are less than 61px apart.')
        # Sorted portal intervals also let us validate fixed towers by a sweep.
        portal_positions = sorted(portals[node])
        index = 0
        for x in positions:
            while index < len(portal_positions) and portal_positions[index] <= x-60:
                index += 1
            if index < len(portal_positions) and abs(portal_positions[index]-x) < 60:
                raise LayoutUnavailable(f'Fixed tower on node {node} violates a current portal exclusion.')

        blocked = [_blocked(x, 60) for x in portal_positions]
        blocked.extend(_blocked(x, 61) for x in positions)
        next_x = lo
        for start, end in _free_intervals(next_x, hi, blocked):
            start = max(start, next_x)
            if start <= end:
                slots = range(start, end+1, 61)
                plan.extend((node, x) for x in slots)
                next_x = slots[-1]+61
    _check_selection(plan, selection_nodes)
    return tuple(plan)
