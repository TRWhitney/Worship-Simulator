"""Cooperative comparisons of complete layouts and executable build orders."""
from collections.abc import Callable
from dataclasses import dataclass,replace
import math
import random
import time
from typing import Literal

from .models import Tower,Board
from .investments import Investment,invest
from .layout import completion_plan,validate_placement
from .summon import Summon


@dataclass(frozen=True)
class LayoutPlan:
    name: str
    layout: tuple[Tower,...]
    steps: tuple[Investment,...]
    send: Literal['clear','rush','hold'] = 'clear'


@dataclass(frozen=True)
class PlanOutcome:
    plan: LayoutPlan
    cleared_wave: int
    lives: int
    remaining_hp: float
    inconclusive: bool
    runs: int
    horizon_ms: int

    @property
    def rank(self):
        return self.cleared_wave,self.lives,-self.remaining_hp


def build_order(state: Board,layout: tuple[Tower,...],*,
                style: Literal['expand','establish','balanced']='expand') -> tuple[Investment,...]:
    """Compile all target levels and choices while retaining existing towers.

    Layout order is creation order. Existing rows form its unchanged prefix;
    target levels may increase and earned choices may be appended.
    """
    if style not in ('expand','establish','balanced'):raise ValueError('Unknown build-order style.')
    if len(layout)<len(state.towers):raise ValueError('A completion must preserve existing towers.')
    actions=[];levels=[];choices=[]
    for index,target in enumerate(layout):
        if (type(target.level) is not int or not 1<=target.level<=100
                or len(target.choices)!=target.level//5 or any(c not in 'AB' for c in target.choices)):
            raise ValueError('Each target needs its complete level and trait choices within the search bound.')
        if index<len(state.towers):
            old=state.towers[index]
            if ((old.kind,old.node,old.x,old.y)!=(target.kind,target.node,target.x,target.y)
                    or old.level>target.level or not target.choices.startswith(old.choices)):
                raise ValueError('An existing tower cannot be moved, replaced or downgraded by a completion.')
            levels.append(old.level);choices.append(old.choices)
        else:levels.append(0);choices.append('')
    def establish(index,limit):
        target=layout[index]
        if levels[index]==0:
            actions.append(Investment('build',tower=replace(target,level=1,choices='')))
            levels[index]=1
        while True:
            while len(choices[index])<levels[index]//5:
                choice=target.choices[len(choices[index])]
                actions.append(Investment('choose',index=index,choice=choice));choices[index]+=choice
            if levels[index]>=min(limit,target.level):break
            actions.append(Investment('upgrade',index=index));levels[index]+=1
    if style=='expand':
        for index in range(len(state.towers),len(layout)):establish(index,1)
    elif style=='balanced':
        for index in range(len(layout)):establish(index,5)
    for index in range(len(layout)):establish(index,layout[index].level)
    return tuple(actions)


class _Run:
    def __init__(self,world: Summon,plan: LayoutPlan,horizon_ms: int,action_interval_ms: int):
        self._validation=_validate_plan(world.investment_state,world.refunds,plan)
        self.world=world;self.plan=plan;self.horizon=horizon_ms
        self.action_interval=action_interval_ms;self.next_action=0;self.step=0

    @property
    def complete(self):return self.world.wave<0 or self.world.loop.now_ms>=self.horizon

    def phase(self):
        if self._validation is not None:
            try:
                next(self._validation)
                return
            except StopIteration:self._validation=None
        world=self.world
        if world.loop.now_ms>=self.next_action:
            acted=False
            if self.step<len(self.plan.steps) and world.apply(self.plan.steps[self.step]):
                self.step+=1;acted=True
            clock=world.clock
            clear=clock.wave>0 and clock.credited>=clock.wave and clock.pending_hp<=0 and world.remaining_hp<=0
            if (not acted and clock.countdown>0 and clock.countdown<999
                    and (self.plan.send=='rush' or self.plan.send=='clear' and clear)):
                world.send()
            self.next_action=world.loop.now_ms+self.action_interval
        world.run_until(world.loop.now_ms+10)


def _validate_plan(state,refunds,plan):
    # Unlimited synthetic purchasing power checks permanent action legality;
    # actual affordability and timing still belong to the combat run.
    build_order(state,plan.layout)
    platforms={p.node:p for p in state.platforms}
    if any(t.node not in platforms or t.y!=platforms[t.node].y for t in plan.layout):
        raise ValueError('The plan contains an inconsistent platform height.')
    capacity=len(state.towers)+len(completion_plan(state))
    fixed=len(state.towers)
    shadow=replace(state,points=1e300)
    for action in plan.steps:
        if action.kind=='sell' and action.index<fixed:
            raise ValueError('A completion cannot sell a fixed tower.')
        if action.kind=='build':
            if not isinstance(action.tower,Tower):raise ValueError('A build needs a tower.')
            validate_placement(shadow,action.tower)
        result=invest(shadow,refunds,action)
        if result is None:raise ValueError('The build order contains a permanently disabled action.')
        shadow,refunds=result.state,result.refunds
        if action.kind in ('build','sell') and len(shadow.towers)+len(completion_plan(shadow))<capacity:
            raise ValueError('The build order consumes reserved tower capacity.')
        yield
    if shadow.towers!=plan.layout:
        raise ValueError('The build order does not produce its claimed layout.')


class PlanSearch:
    """Evaluate every plan with the same seed set and a common time horizon.

    Each advance is bounded between complete 10ms simulation phases. A horizon
    result is a lower bound on clears, not a claim that a board cannot advance.
    Ranking uses the worst credited wave/lives and worst remaining HP across
    the supplied random streams. Global optimality is not established.
    """
    def __init__(self,factory: Callable[[Callable[[int,int],int]],Summon],
                 plans: tuple[LayoutPlan,...],*,horizon_ms: int,
                 random_seeds: tuple[int,...]=(13,71,211),action_interval_ms: int=200):
        if (not plans or not random_seeds or type(horizon_ms) is not int
                or not 0<horizon_ms<36000000 or horizon_ms%10
                or type(action_interval_ms) is not int or action_interval_ms<100 or action_interval_ms%10):
            raise ValueError('Plans, random streams and positive bounded clock intervals are required.')
        if any(p.send not in ('clear','rush','hold') for p in plans):raise ValueError('Unknown send policy.')
        self._factory=factory;self.plans=plans;self.horizon=horizon_ms;self.seeds=random_seeds
        self.action_interval=action_interval_ms
        self._plan_index=0;self._seed_index=0;self._run=None;self._outcomes=[]
        self.best: PlanOutcome | None=None
        self.results: list[PlanOutcome]=[]

    def deepen(self,horizon_ms: int):
        """Reevaluate every plan on a longer common clock after a completed pass.

        Faster progress within a short window does not establish a higher final
        wave. Inconclusive plans remain eligible for these longer comparisons.
        """
        if (not self.complete or type(horizon_ms) is not int or horizon_ms<=self.horizon
                or horizon_ms>=36000000 or horizon_ms%10):
            raise ValueError('Deepening requires a finished pass and a longer supported horizon.')
        self.horizon=horizon_ms
        self._plan_index=self._seed_index=0
        self._run=None;self._outcomes=[];self.best=None;self.results=[]

    @property
    def complete(self):return self._plan_index>=len(self.plans)

    @property
    def progress(self):
        return (self._plan_index*len(self.seeds)+self._seed_index)/(len(self.plans)*len(self.seeds))

    def advance(self,budget_seconds: float=.003):
        if not isinstance(budget_seconds,(int,float)) or not math.isfinite(budget_seconds) or budget_seconds<0:
            raise ValueError('The planning budget must be finite and nonnegative.')
        deadline=time.perf_counter()+budget_seconds
        while not self.complete and time.perf_counter()<deadline:
            plan=self.plans[self._plan_index]
            if self._run is None:
                rng=random.Random(self.seeds[self._seed_index])
                self._run=_Run(self._factory(rng.randint),plan,self.horizon,self.action_interval)
            if not self._run.complete:self._run.phase()
            if not self._run.complete:continue
            world=self._run.world
            self._outcomes.append((world.clock.credited,world.lives,world.outstanding_hp,world.wave>=0))
            self._run=None;self._seed_index+=1
            if self._seed_index<len(self.seeds):continue
            outcome=PlanOutcome(plan,min(r[0] for r in self._outcomes),min(r[1] for r in self._outcomes),
                max(r[2] for r in self._outcomes),any(r[3] for r in self._outcomes),len(self._outcomes),self.horizon)
            self.results.append(outcome)
            if self.best is None or outcome.rank>self.best.rank:self.best=outcome
            self._plan_index+=1;self._seed_index=0;self._outcomes=[]
        return self.best
