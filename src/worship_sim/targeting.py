"""Wizard target acquisition before tower-specific cast eligibility."""
from collections.abc import Iterable, Sequence
from typing import TypeVar

from .simulation import CombatantState, client_distance


Target=TypeVar('Target',bound=CombatantState)

def can_hit(enemy: CombatantState, *, x: float, y: float, radius: float,
            alive_flag: int | None, map_id: int=0) -> bool:
    """Match Hitscanning using the shared array flag supplied by the host."""
    return (alive_flag==1 and client_distance(x,y,enemy.x,enemy.y)<radius
            and enemy.hp>0 and enemy.pet_status==0 and enemy.monster_type=='Monster'
            and not (map_id==216 and enemy.y>950))


def select_target(enemies: Iterable[Target], *, x: float, y: float,
                  radius: float, route: Sequence[int], directions: Sequence[int],
                  map_id: int = 0) -> Target | None:
    """Select the furthest progressed eligible enemy, preserving list-order ties.

    Directions use +1 for rightward movement and -1 for leftward movement.
    As in the client, unknown nodes have route index -1 and use leftward
    comparison. Boulder node checks and Frozone facing checks happen after
    selection and must not cause acquisition to choose a different enemy.
    """
    if len(route) != len(directions) or any(d not in (-1, 1) for d in directions):
        raise ValueError('Each route node needs a direction of +1 or -1.')
    selected = None
    selected_progress = None
    for enemy in enemies:
        if not enemy.worship or not can_hit(enemy,x=x,y=y,radius=radius,
                alive_flag=int(enemy.alive),map_id=map_id):
            continue
        try:
            index = route.index(enemy.node)
        except ValueError:
            index = -1
        direction = directions[index] if index >= 0 else -1
        progress = index, direction*enemy.x
        if selected_progress is None or progress > selected_progress:
            selected, selected_progress = enemy, progress
    return selected
