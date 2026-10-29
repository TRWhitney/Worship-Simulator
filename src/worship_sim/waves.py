"""Worship wave selection and ordered spawn/send timers.

This schedules waves only. Enemy combat, points and battle termination belong
to the caller. Wave numbers are one-based; table indices are zero-based.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable

from .simulation import TimerLoop, TimedTask, js_round


@dataclass(frozen=True)
class Wave:
    count: int
    tier: int
    size: int
    color: int


def resolve_wave(waves: tuple[Wave, ...], index: int, *, cycle_length: int = 30) -> Wave:
    """Resolve the client's repeating suffix and its count/skull extension."""
    if not waves or not isinstance(index, int) or index < 0:
        raise ValueError('A wave table and nonnegative integer index are required.')
    if not isinstance(cycle_length, int) or not 0 < cycle_length <= len(waves):
        raise ValueError('The cycle must be a nonempty suffix of the wave table.')
    extension = max(index - (len(waves) - cycle_length), 0) // cycle_length
    row = waves[min(max(0, index - extension * cycle_length), len(waves) - 1)]
    if extension:
        return Wave(math.ceil(row.count * (1 + extension / 3)),
                    row.tier + 2 * extension, row.size, row.color)
    return row


def next_wave_countdown(wave: int) -> int:
    if wave != 0 and wave % 10 == 0:
        return 9999
    if wave // 10 > 19:
        return 25 + 5 * ((wave - 10) // 10)
    if wave > 9:
        return 25
    if wave > 4:
        return 20
    return 15 if wave > 0 else 6


def send_bonus(wave: int, countdown: float) -> float | None:
    """Return points gained, or None while the button is disabled."""
    if countdown >= 999:
        return None
    if countdown > 2 and wave > 0 and wave % 10 != 0:
        return min(999, math.floor(countdown / 4) + wave + (wave + 1) // 10)
    return 0


@dataclass
class SpawnQueue:
    wave: int
    remaining: int
    interval: float
    countdown: float = 0


class WaveTimeline:
    """Queue each wave at its one-second boundary and spawn on tenth-seconds.

    Register before towers to match actor340 initialization order. Repeated
    subtraction intentionally retains client floating-point timing. Each queued
    spawn resolves its original wave even after a later wave has been sent.
    """
    def __init__(self, loop: TimerLoop | None, waves: tuple[Wave, ...], *,
                 cycle_length: int = 30,
                 on_spawn: Callable[[int, Wave], None]):
        resolve_wave(waves, 0, cycle_length=cycle_length)
        self.wave = 0
        self.countdown = 6
        self.queues: list[SpawnQueue] = []
        self._waves = waves
        self._cycle_length = cycle_length
        self._on_spawn = on_spawn
        if loop is not None:
            loop.schedule(100, self._tenth, repeat=True)
            loop.schedule(1000, self._second, repeat=True)

    def advance_second(self) -> None:
        self._second(None)

    def advance_tenth(self) -> None:
        self._tenth(None)

    def send(self) -> float | None:
        bonus = send_bonus(self.wave, self.countdown)
        if bonus is not None:
            self.countdown = 0
        return bonus

    def _second(self, task: TimedTask | None) -> None:
        self.countdown = js_round(self.countdown - 1)
        if self.countdown < 0:
            self.wave += 1
            self.countdown = next_wave_countdown(self.wave)
            row = resolve_wave(self._waves, self.wave - 1, cycle_length=self._cycle_length)
            interval = (7 + 1.3 * math.floor(row.count / 5)) * (1 / max(row.count, 1))
            self.queues.append(SpawnQueue(self.wave, row.count, interval))
            self._wave_started(row)

    def _wave_started(self, row: Wave) -> None:
        """Allow the host to account for the already resolved new wave."""

    def _tenth(self, task: TimedTask | None) -> None:
        for queue in self.queues:
            queue.countdown -= .1
            if queue.countdown <= 0:
                queue.remaining -= 1
                queue.countdown = queue.interval
                row = resolve_wave(self._waves, queue.wave - 1, cycle_length=self._cycle_length)
                self._on_spawn(queue.wave, row)
        self.queues[:] = [queue for queue in self.queues if queue.remaining > 0]
