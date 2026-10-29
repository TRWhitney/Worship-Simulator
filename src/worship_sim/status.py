"""Worship status mutations from the original monster and Void callbacks.

The battle host owns callback timing, actor liveness, hit eligibility and damage.
Movement uses the shared monster-row flag separately from engine actor liveness.
"""
from dataclasses import dataclass
import math
from typing import Protocol

from .simulation import js_round


SUPPORTED_STATUSES=frozenset(('StatusFreeze','StatusNoMove','StatusBuffHeal',
                            *(f'StatusSkull{index}' for index in range(17))))


def _finite(value, name, minimum=None):
    try:
        valid=(isinstance(value,(int,float)) and not isinstance(value,bool)
               and math.isfinite(value) and (minimum is None or value>=minimum))
    except OverflowError:
        valid=False
    if not valid:
        raise ValueError(f'{name} must be a finite number' +
                         (f' at least {minimum}' if minimum is not None else ''))


def _status(name, seconds):
    if not isinstance(name,str) or name not in SUPPORTED_STATUSES:
        raise ValueError(f'Unsupported Worship status: {name!r}')
    _finite(seconds,'status duration')


@dataclass
class TimedStatus:
    name: str
    seconds: float

    def __post_init__(self):
        _status(self.name,self.seconds)


class StatusTarget(Protocol):
    statuses: list[TimedStatus]
    move_speed: float
    move_speed_initial: float
    velocity: float
    moving: bool
    row_alive: int | None
    color: int
    hit_counter: int
    hp: float
    max_hp: float
    frozen: bool


def _validate(target: StatusTarget):
    if not isinstance(target.statuses,list):
        raise ValueError('statuses must be an ordered list')
    names=set()
    for row in target.statuses:
        if not isinstance(row,TimedStatus):
            raise ValueError('each status must be a TimedStatus')
        _status(row.name,row.seconds)
        if row.name in names:
            raise ValueError('status names must be unique')
        names.add(row.name)
    for name in ('move_speed','move_speed_initial','max_hp'):
        _finite(getattr(target,name),name,0)
    for name in ('velocity','hp','hit_counter'):
        _finite(getattr(target,name),name)
    if target.max_hp<=0:
        raise ValueError('max_hp must be positive')
    if not isinstance(target.hit_counter,int):
        raise ValueError('hit_counter must be an integer')
    if not isinstance(target.moving,bool) or not isinstance(target.frozen,bool):
        raise ValueError('moving and frozen must be booleans')
    if target.row_alive is not None and (type(target.row_alive) is not int
                                          or target.row_alive not in (0,1)):
        raise ValueError('row_alive must be 0, 1 or None')
    if type(target.color) is not int or not 0<=target.color<=5:
        raise ValueError('color must be a Worship color from 0 through 5')


def add_status(target: StatusTarget, name: str, seconds: float) -> None:
    """Append a new status, or replace its duration without changing row order."""
    _validate(target)
    _status(name,seconds)
    for row in target.statuses:
        if row.name==name:
            row.seconds=seconds
            return
    target.statuses.append(TimedStatus(name,seconds))


def tick_movement(target: StatusTarget, *, direction: int) -> None:
    """Run the Worship portion of the two-second Movement callback."""
    _validate(target)
    if type(direction) is not int or direction not in (-1,1):
        raise ValueError('direction must be +1 or -1')
    if target.frozen:
        return
    names={row.name for row in target.statuses}
    if 'StatusNoMove' in names:
        target.move_speed=0
    elif 'StatusFreeze' not in names:
        target.move_speed=target.move_speed_initial
    index=0
    while index<len(target.statuses):
        row=target.statuses[index]
        if row.seconds>0:
            row.seconds-=2
            if row.seconds<=0:
                if row.name in ('StatusFreeze','StatusNoMove') and target.moving:
                    target.move_speed=target.move_speed_initial
                    if target.row_alive==1:
                        sign=(1 if target.velocity>0 else -1) if row.name=='StatusFreeze' else direction
                        target.velocity=sign*target.move_speed_initial
                del target.statuses[index]
                continue
        index+=1


def tick_second(target: StatusTarget) -> None:
    """Run color regeneration or blue recovery, followed by BuffHeal membership."""
    _validate(target)
    if target.color==3:
        if 0<target.hp<.5*target.max_hp:
            target.hp=min(target.max_hp,target.hp+.013*target.max_hp)
    elif target.color==2 and target.hit_counter<0:
        target.hit_counter=js_round(target.hit_counter+1)
    if target.hp>0 and any(row.name=='StatusBuffHeal' for row in target.statuses):
        target.hp=math.ceil(min(target.max_hp,target.hp+.08*target.max_hp))


def void_cleanse(target: StatusTarget) -> None:
    """Run the post-hit status loop after the host establishes Void eligibility."""
    _validate(target)
    for row in target.statuses:
        if target.color!=0:
            if row.name!='StatusFreeze' and 'StatusSkull' not in row.name:
                row.seconds=1
            target.color=0
