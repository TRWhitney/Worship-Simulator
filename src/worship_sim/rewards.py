"""Skull currency and death reward amounts for Worship monsters."""
from dataclasses import dataclass
import math

from .simulation import js_round


@dataclass(frozen=True)
class SkullReward:
    points: int
    popup: int


def _finite(value, name):
    try:
        valid=(isinstance(value,(int,float)) and not isinstance(value,bool)
               and math.isfinite(value) and value>=0)
    except OverflowError:
        valid=False
    if not valid:
        raise ValueError(f'{name} must be finite and nonnegative')


def skull_reward(*, skull: int, size: int, wave: int, salt_lick: float,
                 meal_points: float, meritoc_points: float) -> SkullReward:
    """Return one Skull status's award before the host rounds its point balance.

    Status membership and the remaining-lives guard belong to the death callback.
    The popup amount excludes meal and Meritoc multipliers.
    """
    for name,value,minimum,maximum in (('skull',skull,0,16),('size',size,1,4),
                                       ('wave',wave,0,None)):
        if type(value) is not int or value<minimum or (maximum is not None and value>maximum):
            raise ValueError(f'{name} is outside the supported integer range')
        _finite(value,name)
    for name,value in (('salt_lick',salt_lick),('meal_points',meal_points),
                       ('meritoc_points',meritoc_points)):
        _finite(value,name)
    try:
        salt_multiplier=1+salt_lick/100
        if skull>=6:
            currency=math.floor((250*math.pow(skull-6,1.5)+math.floor(wave/1))*salt_multiplier)
        elif skull>=3:
            base=(25,70,150)[skull-3]
            currency=math.floor((base+math.floor(wave/(2 if skull==3 else 1)))*salt_multiplier)
        else:
            base=(2,5,10)[skull]
            divisor=(5,4,3)[skull]
            currency=js_round((base+math.floor(wave/divisor))*salt_multiplier)
        size_factor=max(.34,2*size-min(size+1,4))
        points=math.ceil(currency*size_factor*(1+meal_points/100)*(1+meritoc_points/100))
        popup=math.ceil(currency*size_factor)
        _finite(points,'computed points')
        _finite(popup,'computed popup amount')
    except OverflowError as error:
        raise ValueError('reward exceeds the supported numeric range') from error
    return SkullReward(points,popup)
