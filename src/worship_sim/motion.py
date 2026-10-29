"""Collision-free simple physics and XY tweens for worship actors.

Coordinates are unrounded top-left positions. Advance tweens before timers,
then physics after timers. Collision, gravity, pause and actor lifecycle are
outside this component.
"""
from dataclasses import dataclass, field
import math
from typing import Literal


@dataclass
class _Tween:
    start_x: float
    end_x: float
    start_y: float
    end_y: float
    duration_ms: int
    easing: Literal['linear', 'quad_out']
    elapsed_ms: float = 0


@dataclass
class Motion:
    x: float
    y: float
    vx: float = 0
    vy: float = 0
    _tween: _Tween | None = field(default=None, init=False, repr=False)

    def move_by(self, dx: float, dy: float, duration_ms: float, *,
                easing: Literal['linear', 'quad_out'] = 'linear') -> None:
        if not all(math.isfinite(value) for value in (dx, dy, duration_ms)) or duration_ms < 0:
            raise ValueError('Finite displacement and a nonnegative duration are required.')
        duration = math.trunc(duration_ms)
        if duration > 0x7fffffff:
            raise ValueError('Tween duration exceeds the supported signed timer range.')
        if easing not in ('linear', 'quad_out'):
            raise ValueError('Only verified linear and quadratic easing are supported.')
        self._tween = _Tween(self.x, self.x + dx, self.y, self.y + dy, duration, easing)
        if duration == 0:
            self._apply_tween(self._tween.end_x, self._tween.end_y)
            self._tween = None

    def _apply_tween(self, x: float, y: float) -> None:
        self.x, self.y = x, y

    def _translate(self, dx: float, dy: float) -> None:
        self.x += dx
        self.y += dy

    def cancel_tween(self) -> None:
        self._tween=None

    def advance_tween(self, step_ms: float) -> None:
        if not math.isfinite(step_ms) or step_ms < 0:
            raise ValueError('A finite nonnegative step is required.')
        tween = self._tween
        if tween is None:
            return
        tween.elapsed_ms = min(tween.elapsed_ms + step_ms, tween.duration_ms)
        fraction = tween.elapsed_ms / tween.duration_ms
        if tween.easing == 'quad_out':
            fraction = -fraction*(fraction-2)
        self._apply_tween(tween.start_x * (1 - fraction) + tween.end_x * fraction,
                          tween.start_y * (1 - fraction) + tween.end_y * fraction)
        if tween.elapsed_ms == tween.duration_ms:
            self._tween = None

    def advance_physics(self, step_ms: float) -> None:
        if not math.isfinite(step_ms) or step_ms < 0:
            raise ValueError('A finite nonnegative step is required.')
        self._translate(self.vx * step_ms * .01, self.vy * step_ms * .01)
