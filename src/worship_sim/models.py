"""Immutable Worship board data and client tower cost/stat formulas."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import math

NAMES=('Pulse Mage','Fireball Lobber','Boulder Roller','Frozone Malone','Stormcaller','Party Starter','Kraken Cosplayer','Poisonic Elder','Voidinator')
TRAITS=((3,25,5,5),(4,15,5,25),(4,50,5,2),(4,15,5,2),(4,200,1,20),(0,25,9,15),(4,1,5,25),(4,5,5,30),(4,25,9,20))
COEFFICIENTS=((15,1.4),(20,1.5),(25,1.6),(1.5,1.6),(30,1.7),(4,1.7),(3,1.6),(15,1.6),(.7,.8))

@dataclass(frozen=True)
class Tower:
    kind:int
    node:int
    x:float
    y:float
    level:int=1
    choices:str=''

@dataclass(frozen=True)
class Platform:
    node:int
    left:float
    right:float
    y:float
    direction:int=1

@dataclass(frozen=True)
class Board:
    active:bool
    map_id:int=0
    wave:int=0
    points:float=0
    hp:float=5
    towers:tuple=()
    platforms:tuple=()
    route:tuple=()
    portals:tuple=()
    construction:tuple=(1,)*9
    coefficients:tuple=COEFFICIENTS
    double_first:bool=False
    roast:float=0
    roast_level:float=0
    roast_floor:float=0
    selection_nodes:tuple=()
    placement_offset_x:float=0



def traits(tower,double=False):
    result=[0.]*10
    row=TRAITS[tower.kind]
    for i,ch in enumerate(tower.choices):
        key,value=row[:2] if ch=='A' else row[2:]
        result[key]+=value*(2 if double and i==0 else 1)
    return tuple(result)


def build_cost(kind,count):
    return math.floor((2,4,7,13,20,10,40,70,125)[kind]*math.ceil((count+1)/3)+2*(1.3+.03*count)**count)


def damage_stat(kind,level,construction,coefficients,multiplier):
    """Apply account and board multipliers before the client's final damage floor."""
    boost=1+(construction-1)*coefficients[0]/100
    if kind==0:damage=multiplier*level*(1.2-.193*level/(15+level))**level*boost
    elif kind==1:damage=multiplier*(2+1.4*level*(1.23-.225*level/(20+level))**level)*boost
    elif kind==2:damage=3*multiplier*level*(1.13-.125*level/(30+level))**level*boost
    elif kind==3:damage=3*multiplier*level
    elif kind==4:damage=multiplier*(13+5*level)*(1.2-.193*level/(20+level))**level*boost
    elif kind==5:damage=0
    elif kind==6:damage=2*multiplier*level*(1.2-.193*level/(20+level))**level*boost
    elif kind==7:damage=multiplier*(1+level)*(1.2-.193*level/(20+level))**level*boost
    else:damage=multiplier*(8+2*level)*(1.2-.193*level/(20+level))**level
    return math.floor(damage) if damage<1e9 else damage


def cooldown_stat(kind,level,construction,coefficients):
    """Return the client base cooldown before the convenience stat minimum."""
    boost=1+(construction-1)*coefficients[0]/100
    if kind==0:cd=math.floor(100*max(1,4.2-2.65*level/(level+10)))/100
    elif kind==1:cd=math.floor(100*(5.15-3.2*level/(level+7)))/100
    elif kind==2:cd=math.floor(100*(6.4-3.7*level/(level+7)))/100
    elif kind==3:cd=max(1.6,math.floor(100*(7-3.5*level/(level+7)))/100)
    elif kind==8:cd=math.floor(100*(14-4*level/(level+7)))/100
    elif kind==6:cd=math.floor((10-3*level/(level+7))*(1/boost)*100)/100
    else:cd=math.floor(100*(10-3*level/(level+7)))/100
    return cd


@lru_cache(maxsize=8192)
def stats(kind,level,construction,coefficients):
    a,b=coefficients
    boost=1+(construction-1)*a/100
    base=(2,3,4,4,5,2,6,10,15)[kind]
    slope=(3,3.5,4,3,4,2,4.5,4.8,5)[kind]
    growth=(1.57,1.58,1.61,1.5,1.63,1.55,1.6,1.63,1.65)[kind]
    cost=math.floor((base+slope*level)*growth**level*max(.05,1-(construction-1)*b/100))
    damage=damage_stat(kind,level,construction,coefficients,1)
    cd=cooldown_stat(kind,level,construction,coefficients)
    if kind<3:radius=math.floor(80+150*level/(level+7))
    elif kind==3:radius=math.floor(85+25*level/(level+7)+(construction-1)*a)
    elif kind==4:radius=math.floor(250+150*level/(level+7))
    elif kind==5:radius=math.floor(250*boost)
    elif kind==8:radius=math.floor(50+25*level/(level+7)+(construction-1)*a)
    else:radius=275
    return cost,damage,max(.01,cd),radius
