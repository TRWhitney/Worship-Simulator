"""Worship hit resolution before the separate enemy death phase."""
import math

from .simulation import CombatantState, js_round


def apply_hits(enemy: CombatantState, *, damage: float, crit_multiplier: float = 1,
               hits: int = 1, player: bool = False,
               bounds: tuple[float, float] | None = None) -> float:
    """Apply each hit, including blue immunity and orange displacement.

    Damage can reduce HP below zero. This phase does not change actor liveness.
    Orange uses the rounded left coordinate returned by Actor.getX(), then
    converts Actor.setX() back to a center with a zero animation offset.
    """
    if not isinstance(hits, int) or isinstance(hits, bool) or not 0 <= hits <= 0x7fffffff:
        raise ValueError('The number of hits must be a nonnegative signed-int32 integer.')
    if not enemy.worship or enemy.pet_status != 0 or enemy.monster_type != 'Monster':
        raise ValueError('Only worship monsters without pet status are supported.')
    if not math.isfinite(damage) or not math.isfinite(crit_multiplier):
        raise ValueError('Damage and critical multiplier must be finite.')
    if enemy.color == 5:
        if bounds is None or len(bounds) != 2 or not all(math.isfinite(x) for x in bounds):
            raise ValueError('Orange monsters require explicit finite platform bounds.')
        if bounds[0] > bounds[1] or not math.isfinite(enemy.width) or enemy.width < 0:
            raise ValueError('Orange monster bounds and width must be valid.')
    multiplier = 1 if crit_multiplier == -1 else crit_multiplier
    per_hit = 1 if player else js_round(damage*multiplier)
    total = 0
    for _ in range(hits):
        dealt = per_hit
        if enemy.color == 2:
            if enemy.hit_counter >= 0:
                enemy.hit_counter += 1
                if enemy.hit_counter > 5:
                    enemy.hit_counter = -3
                    dealt = 0
            else:
                dealt = 0
        elif enemy.color == 5:
            half_width = math.floor(enemy.width/2)
            left = js_round(enemy.x-half_width)
            if enemy.velocity > 0:
                left = min(bounds[1]-10, left+10)
            else:
                left = max(bounds[0]+10, left-10)
            enemy.x = js_round(left)+half_width
        enemy.hp -= dealt
        total += dealt
    return total
