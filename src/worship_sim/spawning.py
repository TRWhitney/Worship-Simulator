"""Initial enemy values from a resolved Worship wave and explicit trial inputs.

Trial base HP replaces native monster HP. Speed uses the live monster
definition's base speed. Geometry, actor identity, statuses after spawning and
death rewards belong to the battle model.
"""
from dataclasses import dataclass
import math
from numbers import Real

from .waves import Wave


@dataclass(frozen=True)
class SpawnStats:
    hp: float
    speed: float
    skull: int


def _integer(value, minimum, maximum=None):
    return (isinstance(value, int) and not isinstance(value, bool)
            and value >= minimum and (maximum is None or value <= maximum))


def _factor(value):
    if not isinstance(value, Real) or isinstance(value, bool):
        raise ValueError('Spawn base values must be finite nonnegative numbers.')
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError('Spawn base values must be finite nonnegative numbers.') from error
    if not math.isfinite(result) or result < 0:
        raise ValueError('Spawn base values must be finite nonnegative numbers.')
    return result


def spawn_stats(wave: Wave, *, base_hp: float, base_speed: float, map_id: int) -> SpawnStats:
    """Apply original initialization order without rounding fractional HP.

    The wave must already include repeating-table tier/count adjustments.
    Sizes 1 through 4 and colors 0 through 5 cover the current client tables.
    HP uses the full tier; only the initial skull status is capped at 16.
    The map308 speed adjustment depends on actual map ID, not trial number.
    """
    if (not isinstance(wave, Wave) or not _integer(wave.count, 1)
            or not _integer(wave.tier, 0) or not _integer(wave.size, 1, 4)
            or not _integer(wave.color, 0, 5) or not _integer(map_id, 0)):
        raise ValueError('The wave or map values exceed the supported spawn inputs.')
    base_hp = _factor(base_hp)
    base_speed = _factor(base_speed)
    try:
        # Math.pow returns floating values even for integer exponents. Keep
        # the helper's two powers together before the outer base-HP multiply.
        multiplier = math.pow(3, wave.size - 2) * math.pow(3 + .3 * wave.tier, wave.tier)
        hp = base_hp * multiplier
        speed_factor = 1.5 - math.pow((wave.size - 1) / 3, .7)
        if map_id == 308:
            speed_factor /= 1.2
        speed = speed_factor * base_speed
    except OverflowError as error:
        raise ValueError('The computed spawn values exceed the finite supported range.') from error
    if not math.isfinite(hp) or not math.isfinite(speed):
        raise ValueError('The computed spawn values exceed the finite supported range.')
    return SpawnStats(hp, speed, min(wave.tier, 16))
