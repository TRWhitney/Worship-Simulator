"""Normal POINTS popup allocation and timer effects, without graphics.

The battle host invokes prepare in the inventory-helper update, update for each
popup in actor order, and draw at that actor's drawing callback. These phases
are separate because popup timers can affect combat task traversal.
"""
from collections.abc import Callable
from dataclasses import dataclass
import math

from .simulation import ActorClock, TimerLoop, TimedTask


@dataclass(eq=False)
class PointPopup:
    clock: ActorClock
    amount: float
    deployment: int = 0


class PointPopups:
    def __init__(self, loop: TimerLoop, owner: ActorClock, *,
                 allocate: Callable[[], ActorClock],
                 recycle: Callable[[ActorClock], None], language: int, hidden: bool):
        if not isinstance(language,int) or isinstance(language,bool) or language<-1:
            raise ValueError('A language profile of -1 or greater is required.')
        if not isinstance(hidden,bool):
            raise ValueError('The hidden-popup option must be a boolean.')
        self._loop=loop
        self._owner=owner
        self._allocate=allocate
        self._recycle=recycle
        self._language=language
        self._hidden=hidden
        self._ready=True
        self._queue: list[PointPopup]=[]

    def create(self, amount: float) -> PointPopup:
        if isinstance(amount,bool) or not isinstance(amount,(int,float)) or not math.isfinite(amount):
            raise ValueError('The popup amount must be finite.')
        popup=PointPopup(self._allocate(),amount)
        if self._hidden:
            self._recycle(popup.clock)
        else:
            self._queue.append(popup)
        return popup

    def prepare(self) -> None:
        if not self._ready or not self._queue:
            return
        head=self._queue[0]
        for duplicate in self._queue[1:]:
            head.amount+=duplicate.amount
            duplicate.deployment=-1
        head.deployment=1
        del self._queue[0]
        self._ready=False
        self._loop.schedule(1000,self._release,actor=self._owner)

    def _release(self, task: TimedTask) -> None:
        self._ready=True

    def update(self, popup: PointPopup) -> None:
        if popup.clock.alive and popup.deployment==-1:
            if popup in self._queue:
                self._queue.remove(popup)
            self._recycle(popup.clock)

    def draw(self, popup: PointPopup) -> None:
        if not popup.clock.alive or popup.deployment!=1:
            return
        popup.deployment=2
        if self._language<2:
            # The original fade callback changes images only, but occupies a task.
            self._loop.schedule(2600,lambda task:None,actor=popup.clock)
        self._loop.schedule(3100,lambda task:self._recycle(popup.clock),actor=popup.clock)
