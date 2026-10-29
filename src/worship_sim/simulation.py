"""Client arithmetic, timer phases and combat primitives for Worship forecasts.

Battle and Summon compose these primitives into persistent encounters. Their
controlled clock and actor contracts have independent original-client checks.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Protocol


def js_round(value: float) -> int:
    """Round finite values toward positive infinity on ties, without adding .5."""
    lower=math.floor(value)
    return lower+int(value-lower>=.5)


def client_distance(x: float, y: float, target_x: float, target_y: float) -> float:
    """Return the client's weighted max/min distance approximation."""
    dx,dy=abs(x-target_x),abs(y-target_y)
    return .9604339*max(dx,dy)+.397824735*min(dx,dy)


@dataclass
class ActorClock:
    alive: bool = True
    paused: bool = False


@dataclass(eq=False)
class TimedTask:
    callback: Callable[[TimedTask], None]
    interval_ms: int
    remaining_ms: int
    repeat: bool
    actor: ActorClock | None
    done: bool = False


class SimulationLimit(RuntimeError):
    pass


class TimerLoop:
    """Port of Stencyl TimedTask and Engine's ordered task-update phase.

    Registration truncates delays to signed int32. Each task gets at most one
    callback per phase; overshoot is carried into its next interval. Tasks
    appended by callbacks are visited in that same phase. Physics, actor
    updates and animation must be added separately in their client order.
    """
    def __init__(self, step_ms: int = 10, max_callbacks: int = 100000):
        if not isinstance(step_ms,int) or step_ms<=0 or max_callbacks<=0:
            raise ValueError('A positive step and callback limit are required.')
        self.step_ms=step_ms
        self.max_callbacks=max_callbacks
        self.now_ms=0
        self.paused=False
        self._tasks: list[TimedTask]=[]

    @property
    def pending(self) -> int:
        return len(self._tasks)

    def schedule(self, delay_ms: float, callback: Callable[[TimedTask],None], *,
                 repeat: bool = False, actor: ActorClock | None = None) -> TimedTask:
        if not math.isfinite(delay_ms):
            raise ValueError('A finite timer delay is required.')
        delay=math.trunc(delay_ms)&0xffffffff
        if delay>=0x80000000:
            delay-=0x100000000
        task=TimedTask(callback,delay,delay,repeat,actor)
        self._tasks.append(task)
        return task

    def cancel(self, task: TimedTask) -> None:
        if task in self._tasks:
            self._tasks.remove(task)

    def recycle(self, actor: ActorClock) -> None:
        # Engine.recycleActor removes tasks immediately, even inside a callback.
        actor.alive=False
        self._tasks[:]=[task for task in self._tasks if task.actor is not actor]

    def tick(self) -> None:
        self.now_ms+=self.step_ms
        index=0
        callbacks=0
        while index<len(self._tasks):
            task=self._tasks[index]
            if not task.done:
                if task.actor is not None and not task.actor.alive:
                    task.done=True
                elif not (self.paused if task.actor is None else task.actor.paused):
                    task.remaining_ms-=self.step_ms
                    if task.remaining_ms<=0:
                        callbacks+=1
                        if callbacks>self.max_callbacks:
                            raise SimulationLimit('A timer phase exceeded the callback limit.')
                        task.callback(task)
                        task.done=not task.repeat
                        if task.repeat:
                            task.remaining_ms+=task.interval_ms
            if task.done:
                self.cancel(task)
                index-=1
            index+=1

    def run_until(self, end_ms: int) -> None:
        if end_ms<self.now_ms:
            raise ValueError('Simulation time cannot go backwards.')
        while self.now_ms<end_ms:
            self.tick()


class CombatantState(Protocol):
    id: int
    node: int
    x: float
    y: float
    hp: float
    velocity: float
    freeze_seconds: float
    alive: bool
    worship: bool
    pet_status: int
    monster_type: str
    color: int
    hit_counter: int
    width: float
    size: int


@dataclass
class Combatant:
    id: int
    node: int
    x: float
    hp: float
    velocity: float = 0
    freeze_seconds: float = 0
    y: float = 0
    alive: bool = True
    worship: bool = True
    pet_status: int = 0
    monster_type: str = 'Monster'
    color: int = 0
    hit_counter: int = 0
    width: float = 0
    size: int = 2


def freeze_velocity(velocity: float, slow_percent: float) -> int:
    slowed=velocity*(.3/(1+slow_percent/100))
    return math.ceil(slowed) if velocity>0 else math.floor(slowed)


def apply_freeze(enemy: CombatantState, slow_percent: float, extra_seconds: float) -> None:
    """Apply actor478 animation 3 after the caller establishes cast/hit eligibility."""
    enemy.velocity=freeze_velocity(enemy.velocity,slow_percent)
    enemy.freeze_seconds=6+extra_seconds


class PoisonPuddle:
    """Stationary actor478 animation 6; damage/status handling is injected.

    This models the puddle's timing and target filter. Tower acquisition,
    creation position, target damage/status effects and actor phase ordering
    outside TimerLoop are the responsibility of the future battle model.
    """
    def __init__(self, loop: TimerLoop, *, node: int, x: float, damage: float,
                 duration_seconds: float, tick_seconds: float, crit_percent: float,
                 enemies: list[Combatant], random_int: Callable[[int,int],int],
                 on_hit: Callable[[Combatant,float],None]):
        self.clock=ActorClock()
        self.fading=False

        def pulse(task: TimedTask) -> None:
            for enemy in enemies:
                if enemy.worship and enemy.node==node and enemy.hp>0 and client_distance(enemy.x,1,x,1)<55:
                    crit=1.5 if crit_percent>random_int(0,1000)/10 else 1
                    on_hit(enemy,js_round(damage*crit))

        def recycle(task: TimedTask) -> None:
            loop.recycle(self.clock)

        def fade(task: TimedTask) -> None:
            self.fading=True
            loop.schedule(800,recycle,actor=self.clock)

        loop.schedule(1000*tick_seconds,pulse,repeat=True,actor=self.clock)
        loop.schedule(1000*duration_seconds,fade,actor=self.clock)


class AnimationClock:
    """Unsynchronized BitmapAnimation frame timing, without bitmap rendering."""
    def __init__(self, durations_ms: tuple[int, ...], *, looping: bool):
        if not durations_ms or any(d <= 0 for d in durations_ms):
            raise ValueError('Positive animation frame durations are required.')
        self.durations_ms=durations_ms
        self.looping=looping
        self.frame=0
        self.elapsed_ms=0
        self.finished=False

    def update(self, step_ms: int) -> None:
        self.elapsed_ms+=step_ms
        if self.elapsed_ms>self.durations_ms[self.frame]:
            self.elapsed_ms-=self.durations_ms[self.frame]
            self.frame+=1
            if self.frame==len(self.durations_ms):
                if self.looping:
                    self.frame=0
                else:
                    self.finished=True
                    self.frame-=1

    def set_frame(self, frame: int) -> None:
        self.frame=frame if 0<=frame<len(self.durations_ms) else 0
        self.elapsed_ms=0
        self.finished=False
