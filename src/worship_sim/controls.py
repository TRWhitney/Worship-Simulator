"""Summon wave clocks, pending HP, Slow Roast and HUD wave credit."""
import math
from numbers import Real

from .simulation import js_round
from .waves import Wave, WaveTimeline


def _finite(value, label, *, nonnegative=False):
    if not isinstance(value, Real) or isinstance(value, bool):
        raise ValueError(f'{label} must be finite numbers.')
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f'{label} must be finite numbers.') from error
    if not math.isfinite(result) or nonnegative and result < 0:
        raise ValueError(f'{label} must be finite nonnegative numbers.' if nonnegative
                         else f'{label} must be finite numbers.')
    return result


class SummonClock(WaveTimeline):
    """Apply helper clock and eligible HUD-draw accounting.

    A None loop lets an existing host drive the two helper callbacks at its
    own timer phase. The draw input contains HP only for unrecycled Worship
    actors; defeat animations and scene cleanup belong to the host.
    """
    def __init__(self, loop_or_None, waves, *, base_hp, on_spawn,
                 roast_floor=0, cycle_length=30):
        self.base_hp = _finite(base_hp, 'Base HP', nonnegative=True)
        self.roast_floor = _finite(roast_floor, 'Roast floor', nonnegative=True)
        self.roast = 0
        self.pending_hp = 0
        self.reached = 0
        self.credited = 0
        self._host_spawn = on_spawn
        super().__init__(loop_or_None, waves, cycle_length=cycle_length,
                         on_spawn=self._spawn)

    def _pending_amount(self, row, count=1):
        multiplier = math.pow(3, row.size - 2) * math.pow(3 + .3 * row.tier, row.tier)
        return count * float(math.ceil(self.base_hp * multiplier))

    def _wave_started(self, row: Wave) -> None:
        self.reached = max(self.wave, self.reached)
        self.roast = -10
        queued = float(js_round(self._pending_amount(row, row.count)))
        self.pending_hp = float(js_round(self.pending_hp + queued))

    def _spawn(self, wave, row):
        self.pending_hp = float(js_round(self.pending_hp - self._pending_amount(row)))
        self._host_spawn(wave, row)

    def _second(self, task):
        if self.wave in (-1, -5):
            return
        self.roast = min(14400, self.roast + 1)
        if self.roast < self.roast_floor:
            self.roast = min(14400, self.roast_floor)
        super()._second(task)

    def _tenth(self, task):
        if self.wave not in (-1, -5):
            super()._tenth(task)

    def draw(self, live_hp_sequence, *, lives, menu_open=False):
        lives = _finite(lives, 'Lives')
        health = tuple(_finite(hp, 'Enemy HP') for hp in live_hp_sequence)
        if menu_open or self.wave == -1:
            return
        living = tuple(hp for hp in health if hp > 0)
        total = self.pending_hp
        for hp in living:
            total += hp
        if not living and total <= .5 and self.wave > 0 and lives > 0:
            self.credited = max(self.credited, js_round(self.reached))
        if self.countdown > 999 and total <= 0:
            self.countdown = 20
