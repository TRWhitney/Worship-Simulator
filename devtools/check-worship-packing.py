"""Audit whether canonical placement preserves future tower capacity.

This checks geometry only. It establishes no combat or highest-wave advantage.
The exhaustive oracle is for small fabricated platforms, not live planning.
"""
import argparse
from dataclasses import replace
import itertools
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from worship_sim.models import Platform, Board
from worship_sim.layout import completion_plan


def maximum_packing(allowed,spacing):
    """Earliest feasible equal-width placement is optimal by exchange."""
    chosen=[]
    for x in sorted(set(allowed)):
        if not chosen or x-chosen[-1]>=spacing:
            chosen.append(x)
    return tuple(chosen)


def check_oracle():
    # Compare with exhaustive subset search, including holes and fixed blockers.
    cases=0
    for forbidden in ((),(3,),(4,5),(1,6),(0,1,7,8)):
        allowed=tuple(x for x in range(9) if x not in forbidden)
        for spacing in (2,3,4):
            optimum=max(len(subset) for n in range(len(allowed)+1)
                        for subset in itertools.combinations(allowed,n)
                        if all(b-a>=spacing for a,b in zip(subset,subset[1:])))
            if len(maximum_packing(allowed,spacing))!=optimum:
                raise AssertionError('The capacity oracle disagrees with exhaustive search.')
            cases+=1
    return cases


def audit():
    state=Board(True,points=100,platforms=(Platform(0,0,400,300),),route=(0,),
                       construction=(0,0,0,0,0,0,0,1,0))
    _,x=completion_plan(state)[0]
    legal=range(80,321)
    full=maximum_packing(legal,61)
    remaining=maximum_packing((p for p in legal if abs(p-x)>=61),61)
    return x,full,tuple(sorted((x,*remaining)))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fail-on-loss',action='store_true')
    args=parser.parse_args()
    print(f'{check_oracle()} geometry-oracle comparisons with exhaustive search passed.')
    x,before,after=audit()
    print(f'Canonical first placement: x={x:g}. Capacity before: {len(before)}. Capacity after: {len(after)}.')
    print(f'Feasible full arrangement: {before}. Arrangement with recommendation: {after}.')
    if args.fail_on_loss and len(after)<len(before):
        raise SystemExit('Recommendation loses future capacity. Combat quality remains unverified.')
