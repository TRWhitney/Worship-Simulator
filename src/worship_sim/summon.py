"""Controlled multiwave summons with explicit account and drawing inputs.

The clock starts at aligned helper phases with initialized existing towers.
It does not restore arbitrary live actors, random state or external GUI tasks.
"""
from dataclasses import replace

from .models import Board,damage_stat,stats
from .battle import Battle,BattleTower,BattleEnemy,PopupProfile
from .board import board_stats
from .controls import SummonClock
from .encounter import EncounterInput
from .investments import Investment,invest
from .layout import validate_placement,LayoutUnavailable
from .native import trial_profile
from .simulation import js_round
from .spawning import spawn_stats
from .status import TimedStatus


class Summon(Battle):
    def __init__(self,state: Board,waves,*,trial: int,atom_bonus: float,
                 salt_lick: float,meal_points: float,meritoc_points: float,
                 refunds: tuple[float,...],random_int,popup_profile: PopupProfile,
                 draw_interval_ms: int=20,helper_y: float=0,cycle_length: int=30,on_event=None):
        if not state.active:raise ValueError('An active controlled summon is required.')
        if len(refunds)!=len(state.towers):raise ValueError('Every existing tower needs its refund balance.')
        self.native=trial_profile(trial,map_id=state.map_id)
        self.atom_bonus=atom_bonus
        self.investment_state=state
        self.refunds=refunds
        self._birth_id=0
        self.clock=SummonClock(None,tuple(waves),base_hp=self.native.base_hp,
            roast_floor=state.roast_floor,on_spawn=self._spawn_wave,cycle_length=cycle_length)
        self.clock.wave=self.clock.reached=state.wave
        self.clock.roast=state.roast
        rows=self._board()
        towers=tuple(self._combat_tower(t,row) for t,row in zip(state.towers,rows))
        scenario=EncounterInput(state.platforms,state.route,towers,(),state.wave,state.points,
            int(state.hp),salt_lick,meal_points,meritoc_points,draw_interval_ms)
        super().__init__(scenario,enemy_profile=self.native.enemy,popup_profile=popup_profile,
                         random_int=random_int,helper_y=helper_y,on_event=on_event)

    def _board(self):
        centers=tuple(replace(t,x=t.x+6,y=t.y-12) for t in self.investment_state.towers)
        return board_stats(replace(self.investment_state,towers=centers),atom_bonus=self.atom_bonus)

    @staticmethod
    def _combat_tower(tower,row):
        return BattleTower(tower.kind,tower.node,tower.x+4,tower.y-21,row.damage,
                           row.cooldown,row.radius,row.bonuses,tower.x)

    def _recompute(self):
        for wizard,tower,row in zip(self._wizards,self.investment_state.towers,self._board()):
            wizard.tower=self._combat_tower(tower,row)

    def _spawn_wave(self,birth_wave,row):
        profile=self.native
        values=spawn_stats(row,base_hp=profile.base_hp,base_speed=profile.base_speed,map_id=profile.map_id)
        platform=self._nodes[self.scenario.route[0]]
        self._birth_id+=1
        x=(platform.left if platform.direction==1 else platform.right)+25
        height=profile.enemy.definition_height
        y=platform.y-height+(height-50)/2+25
        enemy=BattleEnemy(self._birth_id,platform.node,x,values.hp,velocity=values.speed,
            y=y,width=profile.sprite.width,color=row.color,max_hp=values.hp,
            move_speed=values.speed,move_speed_initial=values.speed,moving=True,size=row.size,
            statuses=(TimedStatus(f'StatusSkull{values.skull}',36000),))
        self.spawn(enemy)
        self._event('spawn',enemy.id,birth_wave)

    def _tenth(self,task):
        super()._tenth(task)
        self.clock.advance_tenth()

    def _second(self,task):
        self.clock.advance_second()
        self.wave=self.clock.wave
        self.investment_state=replace(self.investment_state,wave=self.wave,roast=self.clock.roast)
        if self.wave>3:self._recompute()

    def _cast(self,wizard):
        index=self._wizards.index(wizard)
        tower=self.investment_state.towers[index]
        global_damage=self._wizards[0].tower.bonuses[9]
        multiplier=((1+self.atom_bonus/100)
                    *(1+max(0,self.investment_state.roast_level*self.clock.roast/100))
                    *(1+global_damage/100))
        damage=damage_stat(tower.kind,tower.level,self.investment_state.construction[tower.kind],
                           self.investment_state.coefficients[tower.kind],multiplier)
        wizard.tower=replace(wizard.tower,damage=damage)
        super()._cast(wizard)

    def _draw_helper(self):
        self.clock.draw((mob.hp for mob in self.monsters.actors),lives=self.lives)
        if self.lives<=0 and self.wave>=0:
            self.wave=self.clock.wave=-5
            for mob in self.monsters.actors:mob.hp=0
            self.loop.schedule(2500,lambda task:None,actor=self._helper)
            self.loop.schedule(3200,lambda task:None,actor=self._helper)
            self._event('defeat',-1,self.clock.credited)

    def send(self):
        if self.wave<0:return None
        self.loop.schedule(100,lambda task:None,actor=self._helper)
        bonus=self.clock.send()
        if bonus is not None:self.points=float(js_round(self.points+float(bonus)))
        return bonus

    @property
    def outstanding_hp(self):
        total=max(0,self.clock.pending_hp)
        for mob in self.monsters.actors:total+=max(0,mob.hp)
        return total

    def apply(self,action: Investment) -> bool:
        if self.wave<0:return False
        state=replace(self.investment_state,points=self.points)
        if action.kind=='build' and action.tower is not None:
            tower=action.tower
            try:
                validate_placement(state,tower)
            except LayoutUnavailable:return False
        elif action.kind!='build':
            self.loop.schedule(100,lambda task:None,actor=self._helper)
        result=invest(state,self.refunds,action)
        if result is None:return False
        self.investment_state=result.state;self.refunds=result.refunds;self.points=float(result.state.points)
        if action.kind=='build':
            self.add_tower(self._combat_tower(result.state.towers[-1],self._board()[-1]),selection_delay=True)
        elif action.kind=='sell':self.remove_tower(action.index)
        if result.recompute:self._recompute()
        elif result.cooldown_override is not None:
            index,cooldown=result.cooldown_override
            tower=result.state.towers[index]
            radius=stats(tower.kind,tower.level,state.construction[tower.kind],
                         tuple(state.coefficients[tower.kind]))[3]
            self._wizards[index].tower=replace(self._wizards[index].tower,cooldown=cooldown,radius=radius)
        return True

    def run_until(self,end_ms: int) -> None:
        if (type(end_ms) is not int or end_ms<self.loop.now_ms or end_ms%10 or end_ms>=36000000):
            raise ValueError('End time must be a forward 10ms boundary before skull expiry.')
        while self.loop.now_ms<end_ms and self.wave>=0:
            super().run_until(self.loop.now_ms+10)
