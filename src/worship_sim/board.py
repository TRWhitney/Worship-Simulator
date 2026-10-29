"""Normalized complete-board values after the client's trait recomputation event."""
from dataclasses import dataclass
import math

from .models import Tower, Board, TRAITS, cooldown_stat, damage_stat, stats, traits
from .simulation import client_distance


@dataclass(frozen=True)
class BoardStats:
    bonuses: tuple[float, ...]
    damage: float
    base_cooldown: float
    cooldown: float
    radius: float
    cost: int


def _finite(value, name, minimum=None):
    try:
        valid=(isinstance(value,(int,float)) and not isinstance(value,bool)
               and math.isfinite(value) and (minimum is None or value>=minimum))
    except OverflowError:
        valid=False
    if not valid:
        raise ValueError(f'{name} must be a finite number' +
                         (f' at least {minimum}' if minimum is not None else ''))


def _integer(value, name, minimum, maximum=None):
    _finite(value,name,minimum)
    if not isinstance(value,int) or (maximum is not None and value>maximum):
        raise ValueError(f'{name} must be an integer in the supported range')


def _validate(state, atom_bonus):
    if not isinstance(state,Board):
        raise ValueError('state must be a Board')
    _finite(atom_bonus,'Atom bonus',0)
    _finite(state.roast,'Slow Roast counter')
    _finite(state.roast_level,'Slow Roast level',0)
    if not isinstance(state.double_first,bool):
        raise ValueError('first-choice doubling must be a boolean')
    if not isinstance(state.construction,(tuple,list)) or len(state.construction)!=9:
        raise ValueError('construction must contain nine levels')
    for value in state.construction:
        _integer(value,'construction level',0)
    if not isinstance(state.coefficients,(tuple,list)) or len(state.coefficients)!=9:
        raise ValueError('coefficients must contain nine pairs')
    for pair in state.coefficients:
        if not isinstance(pair,(tuple,list)) or len(pair)!=2:
            raise ValueError('each coefficient row must contain two values')
        for value in pair:
            _finite(value,'tower coefficient',0)
    if not isinstance(state.towers,(tuple,list)):
        raise ValueError('towers must be an ordered sequence')
    for tower in state.towers:
        if not isinstance(tower,Tower):
            raise ValueError('each board entry must be a Tower')
        _integer(tower.kind,'tower kind',0,8)
        _integer(tower.level,'tower level',1,100)
        _integer(tower.node,'tower node',0)
        _finite(tower.x,'tower x')
        _finite(tower.y,'tower y')
        if state.construction[tower.kind]<1:
            raise ValueError('board contains a locked tower')
        if (not isinstance(tower.choices,str) or any(ch not in 'AB' for ch in tower.choices)
                or len(tower.choices)>tower.level//5):
            raise ValueError('tower choices must be A/B choices earned at its level')


def board_stats(state: Board, *, atom_bonus: float) -> tuple[BoardStats, ...]:
    """Return ordered values after recomputation, separate from live upgrade cooldowns.

    Positions are base-actor centers. Slow Roast uses the supplied current counter,
    including negative counters, without applying its future minimum.
    """
    _validate(state,atom_bonus)
    towers=state.towers
    if not towers:
        return ()
    coefficients=tuple(tuple(row) for row in state.coefficients)
    try:
        values=[stats(t.kind,t.level,state.construction[t.kind],coefficients[t.kind])
                for t in towers]
    except OverflowError as error:
        raise ValueError('board statistics exceed the supported numeric range') from error
    bonuses=[list(traits(t,state.double_first)) for t in towers]
    for source,tower in enumerate(towers):
        for index,choice in enumerate(tower.choices):
            factor=2 if state.double_first and index==0 else 1
            if tower.kind==5 and choice=='A':
                slot,amount=TRAITS[5][:2]
            elif tower.kind in (4,5,8) and choice=='B':
                slot,amount=TRAITS[tower.kind][2:]
            else:
                continue
            for target,other in enumerate(towers):
                if source==target and not (tower.kind==5 and choice=='A'):
                    continue
                if slot!=9:
                    distance=client_distance(tower.x,tower.y,other.x,other.y)
                    if not values[source][3]+10>distance:
                        continue
                bonuses[target][slot]+=factor*amount
    result=[]
    try:
        multiplier=((1+atom_bonus/100)*(1+max(0,state.roast_level*state.roast/100))
                    *(1+bonuses[0][9]/100))
        _finite(multiplier,'combined damage multiplier',0)
        for tower,bonus,(cost,_,_,radius) in zip(towers,bonuses,values):
            damage=damage_stat(tower.kind,tower.level,state.construction[tower.kind],
                               coefficients[tower.kind],multiplier)
            base_cd=cooldown_stat(tower.kind,tower.level,state.construction[tower.kind],
                                  coefficients[tower.kind])
            cooldown=base_cd/(1+bonus[0]/100)
            for value in (damage,base_cd,cooldown,radius,cost):
                _finite(value,'computed board statistic',0)
            result.append(BoardStats(tuple(bonus),damage,base_cd,cooldown,radius,cost))
    except OverflowError as error:
        raise ValueError('board statistics exceed the supported numeric range') from error
    return tuple(result)
