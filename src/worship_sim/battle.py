"""Persistent controlled Worship encounters.

Supports all nine towers on a supplied initialized actor-state clock.
Combat-owned timers and normal POINTS popups are represented;
external GUI scheduling, account recalculation and HUD termination are excluded.
This is not a continuation of an arbitrary live client.
"""
from collections.abc import Callable
from dataclasses import dataclass,replace
import math
from typing import Literal

from .damage import apply_hits
from .encounter import CombatTower, EncounterInput
from .motion import Motion
from .actor import ActorBody, SpriteProfile
from .popups import PointPopups, PointPopup
from .simulation import ActorClock, AnimationClock, Combatant, TimerLoop, TimedTask, js_round, freeze_velocity, client_distance
from .status import TimedStatus, add_status, tick_movement, tick_second, void_cleanse
from .rewards import skull_reward
from .projectiles import Projectiles
from .targeting import select_target, can_hit
from .world import ActorTable, MonsterTable


@dataclass(frozen=True)
class BattleTower(CombatTower):
    bonuses: tuple[float, ...] = (0,)*10
    placement_x: float | None = None


@dataclass(kw_only=True)
class BattleEnemy(Combatant):
    max_hp: float
    move_speed: float
    move_speed_initial: float
    moving: bool
    size: int
    statuses: tuple[TimedStatus, ...]
    frozen: bool = False


@dataclass(frozen=True)
class EnemyProfile:
    frames: tuple[int, ...]
    death_frame: int
    height: float
    definition_height: float
    default_sprite: SpriteProfile | None = None


@dataclass(frozen=True)
class PopupProfile:
    language: int
    hidden: bool


class _Actor(ActorClock):
    __eq__=object.__eq__
    __hash__=object.__hash__

    def __init__(self, actor_id: int, kind: Literal['helper','inventory','monster','base','wizard','popup']):
        super().__init__()
        self.id=actor_id
        self.kind=kind
        self.body: ActorBody | None=None
        self.motion: Motion | None=None
        self.animation: AnimationClock | None=None
        self.popup: PointPopup | None=None


class BattleMonster(_Actor):
    def __init__(self, actor_id, enemy, table, profile):
        super().__init__(actor_id,'monster')
        self.source_id=enemy.id
        self.monster_id=-1
        self.table=table
        current=SpriteProfile(enemy.width,profile.height,profile.frames,False)
        default=profile.default_sprite or current
        self.body=ActorBody(default,left=enemy.x-math.floor(default.width/2),
                            top=enemy.y-math.floor(default.height/2))
        self.body.set_animation(current)
        self.motion=self.body.motion
        self.animation=self.body.animation
        self.motion.vx=enemy.velocity
        self.node=enemy.node
        self.worship=enemy.worship
        self.pet_status=enemy.pet_status
        self.monster_type=enemy.monster_type
        self.color=enemy.color
        self.hit_counter=enemy.hit_counter
        if isinstance(enemy,BattleEnemy):
            self.max_hp=enemy.max_hp
            self.move_speed=enemy.move_speed
            self.move_speed_initial=enemy.move_speed_initial
            self.moving=enemy.moving
            self.size=enemy.size
            self.frozen=enemy.frozen
            self.statuses=[TimedStatus(row.name,row.seconds) for row in enemy.statuses]
        else:
            self.max_hp=enemy.hp
            self.move_speed=self.move_speed_initial=abs(enemy.velocity)
            self.moving=enemy.velocity!=0
            self.size=enemy.size
            self.frozen=False
            self.statuses=[TimedStatus('StatusSkull0',36000)]

    @property
    def row_alive(self):return self.table.alive(self)

    @property
    def freeze_seconds(self):
        return next((row.seconds for row in self.statuses if row.name=='StatusFreeze'),0)

    @freeze_seconds.setter
    def freeze_seconds(self,value):add_status(self,'StatusFreeze',value)

    @property
    def hp(self):return self.table.hp(self)

    @hp.setter
    def hp(self,value):self.table.set_hp(self,value)

    @property
    def x(self):return self.body.x

    @x.setter
    def x(self,value):self.body.set_left(value-math.floor(self.body.width/2))

    @property
    def y(self):return self.body.y

    @y.setter
    def y(self,value):self.body.set_top(value-math.floor(self.body.height/2))

    @property
    def velocity(self):return self.motion.vx

    @velocity.setter
    def velocity(self,value):self.motion.vx=value

    @property
    def width(self):return self.body.width

    def set_center(self,x):
        self.body.set_x_center(x)


class _TowerActor(_Actor):
    def __init__(self,actor_id,tower,kind):
        super().__init__(actor_id,kind)
        self.tower=tower
        self.remaining=-1.
        self.underlings=[]
        durations=tuple(10000 if frame in (4,14,19,29,34,44,49,64,79,94,109)
                        else 100 for frame in range(136))
        if kind=='wizard':
            self.animation=AnimationClock(durations,looping=True)
            self.animation.set_frame(15*tower.kind)


def _validate(scenario,enemy_profile,popup_profile):
    if not isinstance(scenario,EncounterInput) or not isinstance(enemy_profile,EnemyProfile):
        raise ValueError('A controlled encounter and enemy animation profile are required.')
    if not isinstance(popup_profile,PopupProfile):
        raise ValueError('An explicit popup profile is required.')
    if enemy_profile.default_sprite is not None and not isinstance(enemy_profile.default_sprite,SpriteProfile):
        raise ValueError('The default enemy sprite must be a validated profile.')
    nodes={p.node:p for p in scenario.platforms}
    if (not nodes or len(nodes)!=len(scenario.platforms) or not scenario.route
            or len(set(scenario.route))!=len(scenario.route) or set(scenario.route)-nodes.keys()):
        raise ValueError('A unique platform route is required.')
    values=[scenario.points,scenario.salt_lick,scenario.meal_points,scenario.meritoc_points,
            enemy_profile.height,enemy_profile.definition_height]
    for platform in scenario.platforms:
        values.extend((platform.left,platform.right,platform.y))
        if platform.direction not in (-1,1) or platform.right<=platform.left:
            raise ValueError('Platform bounds and direction must be valid.')
    for tower in scenario.towers:
        if not isinstance(tower,CombatTower):
            raise ValueError('Each tower needs explicit combat values.')
        bonus=tower.bonuses if isinstance(tower,BattleTower) else (0,)*10
        if isinstance(tower,BattleTower) and tower.placement_x is not None:values.append(tower.placement_x)
        if len(bonus)!=10:
            raise ValueError('Each tower needs ten effective trait slots.')
        values.extend(bonus)
        if any(value<0 for value in bonus):
            raise ValueError('Effective traits must be nonnegative.')
        values.extend((tower.x,tower.y,tower.damage,tower.cooldown,tower.radius))
        if (tower.kind not in range(9) or tower.node not in nodes
                or tower.damage<0 or tower.cooldown<=0 or tower.radius<=0):
            raise ValueError('Unsupported tower kind or invalid combat values.')
    ids=set()
    for enemy in scenario.enemies:
        values.extend((enemy.x,enemy.y,enemy.hp,enemy.width,enemy.velocity))
        if (enemy.id in ids or enemy.node not in scenario.route or enemy.hp<=0 or enemy.width<=0
                or not enemy.alive or not enemy.worship or enemy.pet_status!=0
                or type(enemy.size) is not int or not 1<=enemy.size<=4
                or enemy.monster_type!='Monster' or type(enemy.color) is not int or not 0<=enemy.color<=5
                or enemy.freeze_seconds!=0):
            raise ValueError('Only distinct living worship enemies with valid colors are supported.')
        if isinstance(enemy,BattleEnemy):
            values.extend((enemy.max_hp,enemy.move_speed,enemy.move_speed_initial))
            if (enemy.max_hp<=0 or enemy.move_speed<0 or enemy.move_speed_initial<0
                    or type(enemy.moving) is not bool or type(enemy.frozen) is not bool
                    or type(enemy.size) is not int or not 1<=enemy.size<=4 or not isinstance(enemy.statuses,tuple)
                    or any(not isinstance(row,TimedStatus) for row in enemy.statuses)
                    or len({row.name for row in enemy.statuses})!=len(enemy.statuses)):
                raise ValueError('Explicit enemy state must have valid size, movement and statuses.')
        if type(enemy.hit_counter) is not int:
            raise ValueError('Hit counters must be integers.')
        ids.add(enemy.id)
    if not all(isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) for x in values):
        raise ValueError('Encounter values must be finite numbers.')
    if (min(scenario.points,scenario.salt_lick,scenario.meal_points,scenario.meritoc_points)<0
            or enemy_profile.height<=0 or enemy_profile.definition_height<=0
            or not isinstance(scenario.wave,int) or isinstance(scenario.wave,bool) or scenario.wave<0
            or not isinstance(scenario.lives,int) or isinstance(scenario.lives,bool) or scenario.lives<1):
        raise ValueError('Wave, lives, rewards and enemy geometry must be valid.')
    if (not isinstance(scenario.draw_interval_ms,int) or isinstance(scenario.draw_interval_ms,bool)
            or scenario.draw_interval_ms<=0 or scenario.draw_interval_ms%10):
        raise ValueError('Draw interval must be a positive multiple of 10ms.')
    if (not enemy_profile.frames or any(not isinstance(x,int) or isinstance(x,bool) or x<=0
                                       for x in enemy_profile.frames)
            or not isinstance(enemy_profile.death_frame,int) or isinstance(enemy_profile.death_frame,bool)
            or not 0<=enemy_profile.death_frame<len(enemy_profile.frames)):
        raise ValueError('Valid enemy animation durations and death frame are required.')


class Battle:
    def __init__(self,scenario: EncounterInput,*,enemy_profile: EnemyProfile,
                 popup_profile: PopupProfile,random_int: Callable[[int,int],int],helper_y: float=0,
                 on_event: Callable[[int,str,int,float],None] | None=None):
        _validate(scenario,enemy_profile,popup_profile)
        if isinstance(helper_y,bool) or not isinstance(helper_y,(int,float)) or not math.isfinite(helper_y):
            raise ValueError('The helper Y position must be finite.')
        self.helper_y=helper_y
        self.loop=TimerLoop()
        self.actors=ActorTable(capacity=16,reuse_iterator=True)
        self.monsters=MonsterTable(hp_sentinel=0,alive_sentinel=0,will_die_sentinel=0)
        self.points=float(scenario.points)
        self.lives=scenario.lives
        self.wave=scenario.wave
        self.scenario=scenario
        self.profile=enemy_profile
        self._popup_profile=popup_profile
        self._random=random_int
        self._on_event=on_event
        self._next_id=0
        self._nodes={p.node:p for p in scenario.platforms}
        self._wizards=[]
        self._popup_pool=[]
        self._monster_pool=[]
        self._tower_pool=[]
        self._inventory=self._actor('inventory')
        self._helper=self._actor('helper')
        self.popups=PointPopups(self.loop,self._inventory,allocate=self._allocate_popup,
                               recycle=self._recycle,language=popup_profile.language,
                               hidden=popup_profile.hidden)
        self.projectiles=Projectiles(self.loop,enemies=lambda:self.monsters.actors,
            platforms=self._nodes,random_int=self._random,allocate_id=self._id,
            on_add=lambda actor:self.actors.add(actor.id,actor),
            on_remove=lambda actor:self.actors.remove(actor.id),on_hit=self._projectile_hit,
            can_hit=self._can_hit,on_freeze=self._projectile_freeze,on_cleanse=void_cleanse,
            on_push=lambda enemy,dx:enemy.motion.move_by(dx,0,600,easing='quad_out'),
            is_active=lambda:self.wave>-1)
        self.loop.schedule(100,self._tenth,repeat=True,actor=self._helper)
        self.loop.schedule(1000,self._second,repeat=True,actor=self._helper)
        self.loop.schedule(10000,lambda task:None,repeat=True,actor=self._helper)
        for enemy in scenario.enemies:
            self.spawn(enemy,initialize_movement=False)
        for tower in scenario.towers:
            self.add_tower(tower)

    def add_tower(self,tower: CombatTower,*,selection_delay: bool=False):
        _validate(replace(self.scenario,enemies=(),towers=(tower,)),self.profile,self._popup_profile)
        base=self._tower_actor('base',tower)
        if selection_delay:self.loop.schedule(500,lambda task:None,actor=base)
        self._tower_tasks(base,lambda task:None)
        wizard=self._tower_actor('wizard',tower)
        wizard.base=base
        wizard.underlings=base.underlings
        self._wizards.append(wizard)
        self._tower_tasks(wizard,lambda task:self._cast(wizard))
        return wizard

    def _tower_actor(self,kind,tower):
        actor=next((a for a in self._tower_pool if not a.alive),None)
        if actor is None:
            actor=_TowerActor(self._id(),tower,kind)
            self._tower_pool.append(actor)
        else:actor.__init__(actor.id,tower,kind)
        self.actors.add(actor.id,actor)
        return actor

    def remove_tower(self,index: int):
        wizard=self._wizards.pop(index)
        self._recycle(wizard.base)
        self._recycle(wizard)

    def spawn(self,enemy: Combatant,*,initialize_movement: bool=True) -> BattleMonster:
        """Initialize one ordinary enemy, reusing the first available actor."""
        _validate(replace(self.scenario,enemies=(enemy,),towers=()),self.profile,self._popup_profile)
        if any(m.source_id==enemy.id for m in self.monsters.actors):
            raise ValueError('A living or retained corpse already uses this enemy ID.')
        mob=next((m for m in self._monster_pool if not m.alive),None)
        if mob is None:
            if initialize_movement:
                default=self.profile.default_sprite
                width=default.width if default else enemy.width
                height=default.height if default else self.profile.height
                def fresh_center(center,dimension):
                    half=math.floor(dimension/2)
                    left=math.trunc(center-half)&0xffffffff
                    if left>=0x80000000:left-=0x100000000
                    return left+half
                enemy=replace(enemy,x=fresh_center(enemy.x,width),y=fresh_center(enemy.y,height))
            mob=BattleMonster(self._id(),enemy,self.monsters,self.profile)
            self._monster_pool.append(mob)
        else:
            mob.__init__(mob.id,enemy,self.monsters,self.profile)
        self.monsters.add(mob,hp=enemy.hp)
        self.actors.add(mob.id,mob)
        if initialize_movement and mob.moving:self._random(-1,1)
        self.loop.schedule(100,lambda task:None,actor=mob)
        self.loop.schedule(2000,lambda task:tick_movement(mob,direction=self._nodes[mob.node].direction),
                           repeat=True,actor=mob)
        self.loop.schedule(1000,lambda task:tick_second(mob),repeat=True,actor=mob)
        return mob

    def _id(self):
        result=self._next_id
        self._next_id+=1
        return result

    def _actor(self,kind):
        actor=_Actor(self._id(),kind)
        self.actors.add(actor.id,actor)
        return actor

    def _allocate_popup(self):
        actor=next((item for item in self._popup_pool if not item.alive),None)
        if actor is not None:
            actor.alive=True
            actor.paused=False
            actor.popup=None
            self.actors.add(actor.id,actor)
        else:
            actor=self._actor('popup')
            self._popup_pool.append(actor)
        return actor

    def _recycle(self,actor):
        if actor.body is not None:
            actor.body.recycle()
            actor.animation=actor.body.animation
        self.loop.recycle(actor)
        self.actors.remove(actor.id)

    def _tower_tasks(self,actor,cast):
        self.loop.schedule(100,cast,repeat=True,actor=actor)
        self.loop.schedule(100,lambda task:None,repeat=True,actor=actor)
        self.loop.schedule(100,lambda task:None,repeat=True,actor=actor)
        self.loop.schedule(1000,lambda task:None,repeat=True,actor=actor)

    def _event(self,kind,who,value):
        if self._on_event is not None:self._on_event(self.loop.now_ms,kind,who,value)

    def _second(self,task):
        pass

    def _draw_helper(self):
        pass

    def _tenth(self,task):
        for mob in self.monsters.actors:
            p=self._nodes[mob.node]
            if mob.x>p.right-20 if p.direction==1 else mob.x<p.left+20:
                index=self.scenario.route.index(mob.node)
                if index<len(self.scenario.route)-1:
                    mob.node=self.scenario.route[index+1]
                elif mob.hp>0:
                    mob.node=self.scenario.route[0]
                    self.lives-=1
                    self._event('leak',mob.source_id,self.lives)
                else:mob.hp=0
                p=self._nodes[mob.node]
                mob.set_center(p.left+10 if p.direction==1 else p.right-10)
                mob.y=p.y-self.profile.definition_height+(self.profile.definition_height-50)/2+math.floor(self.profile.height/2)
                if self.monsters.alive(mob)==1:
                    left=js_round(mob.x-math.floor(mob.width/2))
                    mob.velocity=-mob.move_speed if left>(p.left+p.right)/2 else mob.move_speed
            top=p.y-self.profile.definition_height+(self.profile.definition_height-50)/2
            if abs(top-js_round(self.helper_y))>=4:
                mob.y=top+math.floor(self.profile.height/2)
        for wizard in self._wizards:
            if wizard.remaining>0:
                wizard.remaining-=.1
                if wizard.remaining<=0:wizard.animation.set_frame(15*wizard.tower.kind+1)

    def _can_hit(self,enemy,x,y,radius):
        return can_hit(enemy,x=x,y=y,radius=radius,alive_flag=self.monsters.alive(enemy))

    def _projectile_freeze(self,enemy,slow_percent,extra_seconds):
        enemy.velocity=freeze_velocity(enemy.velocity,slow_percent)
        enemy.move_speed=abs(enemy.velocity)
        add_status(enemy,'StatusFreeze',6+extra_seconds)

    def _projectile_hit(self,enemy,damage,critical):
        platform=self._nodes[enemy.node]
        dealt=apply_hits(enemy,damage=damage,crit_multiplier=critical,
                         bounds=(platform.left,platform.right))
        self._event('hit',enemy.source_id,dealt)

    def _cast(self,wizard):
        animation=wizard.animation
        tower=wizard.tower
        offset=15*tower.kind
        if animation.frame-offset in (4,14):animation.set_frame(animation.frame)
        if animation.frame-offset!=4:return
        bonus=tower.bonuses if isinstance(tower,BattleTower) else (0,)*10
        if tower.kind==6:
            if len(wizard.underlings)>=js_round(4+bonus[4]):return
            underling=self.projectiles.kraken(left=js_round(tower.x-19),top=js_round(tower.y-19),
                node=tower.node,damage=tower.damage,origin_x=tower.x,contacts=2+bonus[5],
                push_direction=-self._nodes[tower.node].direction,underlings=wizard.underlings)
            wizard.underlings.append(underling)
            animation.set_frame(offset+5)
            wizard.remaining=tower.cooldown
            self._event('cast',-1,0)
            return
        target=select_target((mob for mob in self.monsters.actors if self.monsters.alive(mob)==1),
                             x=tower.x,y=tower.y,radius=tower.radius,
                             route=self.scenario.route,
                             directions=tuple(self._nodes[n].direction for n in self.scenario.route),
                             map_id=0)
        if target is None:return
        if tower.kind in (1,2,3,4,5,7,8):
            if tower.kind==1:
                platform=self._nodes[target.node]
                direction=1 if target.x+12*target.velocity>tower.x else -1
                aim=max(platform.left,min(platform.right,js_round(target.x+18.3*target.velocity)))
                self.projectiles.fireball(left=tower.x-22,top=js_round(platform.y-51),
                    direction=direction,node=target.node,aim_x=aim,damage=tower.damage,
                    radius_percent=js_round(100+bonus[5]),delay_seconds=0,crit_percent=bonus[1])
                if bonus[4]>self._random(1,100):
                    aim=max(platform.left,min(platform.right,
                        js_round(self._random(-50,50)+target.x+12*target.velocity)))
                    self.projectiles.fireball(left=tower.x-22,top=js_round(platform.y-51),
                        direction=direction,node=target.node,aim_x=aim,damage=tower.damage,
                        radius_percent=js_round(100+bonus[5]),delay_seconds=.5,crit_percent=bonus[1])
            elif tower.kind==2:
                if target.node!=tower.node:return
                self.projectiles.boulder(left=tower.x,top=js_round(self._nodes[tower.node].y-31),
                    direction=1 if target.x>tower.x else -1,node=tower.node,damage=tower.damage,
                    duration_seconds=2.5*(1+bonus[4]/100),hit_budget=5+bonus[5],crit_percent=bonus[1])
            elif tower.kind==3:
                if (target.x-tower.x)*self._nodes[tower.node].direction<=0:return
                self.projectiles.freeze(left=js_round(tower.x-19),top=js_round(tower.y-5),
                    damage=tower.damage,slow_percent=bonus[4],extra_seconds=bonus[5],
                    crit_percent=bonus[1],radius=tower.radius-6)
            elif tower.kind==8:
                self.projectiles.void(left=js_round(tower.x-19),top=js_round(tower.y-5),
                    damage=tower.damage,crit_percent=bonus[1],radius=tower.radius-6)
            elif tower.kind==4:
                damage=tower.damage*(1+bonus[4]/100) if target.hp/target.max_hp<.6 else tower.damage
                self.projectiles.storm(left=target.x,top=js_round(self._nodes[target.node].y-55),
                    target=target,damage=damage,crit_percent=bonus[1])
            elif tower.kind==7:
                self.projectiles.poison(left=target.x,top=js_round(self._nodes[target.node].y-24),
                    node=target.node,damage=tower.damage,duration_seconds=10+bonus[4],
                    tick_seconds=2/(1+bonus[5]/100),crit_percent=bonus[1])
            animation.set_frame(offset+5)
            wizard.remaining=tower.cooldown
            if tower.kind==8 and self._random(1,100)<bonus[4]:wizard.remaining*=.5
            self._event('cast',target.source_id,0)
            return
        extra=math.floor(bonus[3]/100)
        hits=1+extra+int(bonus[3]-100*extra>self._random(0,100))
        critical=1.5 if bonus[1]>self._random(0,1000)/10 else 1
        platform=self._nodes[target.node]
        dealt=apply_hits(target,damage=tower.damage,hits=hits,crit_multiplier=critical,
                         bounds=(platform.left,platform.right))
        if bonus[5]>0 and target.size!=4:
            platform=self._nodes[target.node]
            half_width=math.floor(target.width/2)
            for _ in range(hits):
                left=js_round(target.x-half_width)
                pushed=(max(platform.left+10,left-bonus[5]) if target.velocity>0
                        else min(platform.right-10,left+bonus[5]))
                target.x=js_round(pushed)+half_width
        self._event('cast',target.source_id,dealt)
        animation.set_frame(offset+5)
        wizard.remaining=tower.cooldown

    def _death_effects(self,mob):
        if mob.color==4:
            for wizard in self._wizards:
                tower=wizard.tower
                x=tower.placement_x if isinstance(tower,BattleTower) and tower.placement_x is not None else tower.x
                y=self._nodes[tower.node].y
                if client_distance(mob.x,mob.y,x,y)<70 and wizard.remaining<.1+tower.cooldown:
                    wizard.remaining=4+tower.cooldown
                    self.projectiles.stun(left=x-14,top=y-96,duration_seconds=4+.8*tower.cooldown)
        elif mob.color==1:
            for target in self.monsters.actors:
                if self._can_hit(target,mob.x,mob.y,60):add_status(target,'StatusBuffHeal',3)

    def _draw_monster(self,mob):
        p=self._nodes[mob.node]
        if mob.moving:
            if mob.x<p.left:
                mob.set_center(p.left+1);mob.velocity=-mob.velocity
            if mob.x>p.right:
                mob.set_center(p.right-1);mob.velocity=-mob.velocity
        if mob.hp>0 or self.monsters.alive(mob)!=1:return
        mob.velocity=0
        self.loop.schedule(100,lambda task:None,actor=mob)
        self.loop.schedule(700,lambda task:None,actor=mob)
        self.monsters.set_alive(mob,0)
        mob.animation.set_frame(self.profile.death_frame)
        previous=js_round(self.points)
        if self.lives>.5:
            names={row.name for row in mob.statuses}
            for skull in range(17):
                if f'StatusSkull{skull}' not in names:continue
                reward=skull_reward(skull=skull,size=mob.size,wave=self.wave,
                    salt_lick=self.scenario.salt_lick,meal_points=self.scenario.meal_points,
                    meritoc_points=self.scenario.meritoc_points)
                balance=self.points+float(reward.points)
                if not math.isfinite(balance):
                    raise ValueError('The simulated point balance exceeds the finite supported range.')
                self.points=float(js_round(balance))
                popup=self.popups.create(reward.popup)
                popup.clock.popup=popup
                self._death_effects(mob)
                break
        mob.statuses.clear()
        self._event('death',mob.source_id,self.points-previous)
        delay=js_round(len(self.profile.frames)-self.profile.death_frame+1)/10*1000
        self.loop.schedule(delay,lambda task:self._fade_monster(mob),actor=mob)

    def _fade_monster(self,mob):
        if mob.moving:
            def drift(task):
                if self.monsters.alive(mob)==0:mob.velocity=self._random(-5,5)
            self.loop.schedule(600,drift,actor=mob)
        self.loop.schedule(500,lambda task:self._remove_monster(mob),actor=mob)

    def _remove_monster(self,mob):
        self.monsters.remove(mob)
        self._recycle(mob)
        self._event('recycle',mob.source_id,0)

    @property
    def remaining_hp(self):
        total=0.
        for mob in self.monsters.actors:total+=max(0,mob.hp)
        return total

    def run_until(self,end_ms: int) -> None:
        if (not isinstance(end_ms,int) or isinstance(end_ms,bool) or end_ms<self.loop.now_ms
                or end_ms%10 or end_ms>=36000000):
            raise ValueError('End time must be a forward 10ms boundary before skull expiry.')
        while self.loop.now_ms<end_ms:
            for actor in self.actors:
                if actor is not None and actor.motion is not None:actor.motion.advance_tween(10)
            self.loop.tick()
            for actor in self.actors:
                if actor is None or not actor.alive:continue
                if actor.motion is not None:actor.motion.advance_physics(10)
                if actor.animation is not None:actor.animation.update(10)
                if actor.kind=='inventory':self.popups.prepare()
                elif actor.kind=='popup' and actor.popup is not None:self.popups.update(actor.popup)
            if self.loop.now_ms%self.scenario.draw_interval_ms==0:
                for actor in self.actors:
                    if actor is None or not actor.alive:continue
                    if actor.kind=='helper':self._draw_helper()
                    elif actor.kind=='monster':self._draw_monster(actor)
                    elif actor.kind=='popup' and actor.popup is not None:self.popups.draw(actor.popup)
