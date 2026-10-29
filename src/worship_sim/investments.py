"""Point balances and tower purchases, independent of placement and combat clocks."""
from dataclasses import dataclass,replace
import math
from typing import Literal

from .models import Tower,Board,build_cost,stats,cooldown_stat
from .simulation import js_round


@dataclass(frozen=True)
class Investment:
    kind: Literal['build','upgrade','choose','sell']
    index: int = -1
    tower: Tower | None = None
    choice: str = ''


@dataclass(frozen=True)
class InvestmentResult:
    state: Board
    refunds: tuple[float,...]
    recompute: bool
    cooldown_override: tuple[int,float] | None = None


def invest(state: Board,refunds: tuple[float,...],action: Investment) -> InvestmentResult | None:
    """Apply one affordable purchase, or return None when its button is disabled.

    Positions must be checked by the caller. An upgrade writes the bare base
    cooldown; builds, choices and sales request complete trait recomputation.
    Inputs and outputs are immutable. Balances retain client binary64 precision.
    """
    if not isinstance(state,Board) or not isinstance(action,Investment):
        raise ValueError('A Worship state and investment are required.')
    if (not isinstance(refunds,tuple) or len(refunds)!=len(state.towers)
            or not all(isinstance(v,(int,float)) and not isinstance(v,bool)
                       and math.isfinite(v) and v>=0 for v in (state.points,)+refunds)):
        raise ValueError('Finite point and refund balances are required for every tower.')
    towers=list(state.towers);balances=list(refunds)
    points=float(state.points);recompute=True;override=None
    if action.kind=='build':
        tower=action.tower
        if (not isinstance(tower,Tower) or type(tower.kind) is not int or not 0<=tower.kind<9
                or tower.level!=1 or tower.choices):
            raise ValueError('A build requires a level-one tower without choices.')
        if state.construction[tower.kind]<1:return None
        cost=build_cost(tower.kind,len(towers))
        if points<cost:return None
        points=float(js_round(points-cost));towers.append(tower);balances.append(math.ceil(.6*cost))
    elif action.kind in ('upgrade','choose','sell'):
        if type(action.index) is not int or not 0<=action.index<len(towers):
            raise ValueError('The investment references an unknown tower.')
        index=action.index;tower=towers[index]
        if action.kind=='upgrade':
            if len(tower.choices)<tower.level//5:return None
            cost=stats(tower.kind,tower.level,state.construction[tower.kind],
                       tuple(state.coefficients[tower.kind]))[0]
            if points<cost:return None
            points=float(js_round(points-cost))
            balances[index]=js_round(float(balances[index])+.6*cost)
            towers[index]=replace(tower,level=tower.level+1)
            recompute=False
            override=(index,cooldown_stat(tower.kind,tower.level+1,state.construction[tower.kind],
                                          tuple(state.coefficients[tower.kind])))
        elif action.kind=='choose':
            if action.choice not in ('A','B'):raise ValueError('The trait must be A or B.')
            if len(tower.choices)>=tower.level//5:return None
            towers[index]=replace(tower,choices=tower.choices+action.choice)
        else:
            points=float(js_round(points+float(balances[index])))
            del towers[index];del balances[index]
    else:
        raise ValueError('Unknown Worship investment.')
    if not math.isfinite(points):raise ValueError('The purchase exceeds the finite point range.')
    return InvestmentResult(replace(state,points=points,towers=tuple(towers)),tuple(balances),recompute,override)
