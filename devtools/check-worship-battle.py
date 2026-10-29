"""Compare assembled persistent Worship worlds with original client callbacks.

Initial actor metadata, animation durations, statistics and helper phases are
controlled. Native births execute original helper spawning, CreateMonster and
Actor1 initialization; account recalculation and image services are host inputs.
Tower bases start with their placement delay already cleared and its one-shot
500ms initialization task absent; supplied periodic phases still start at zero.
Original combat, projectile initialization/pooling, geometry, animation, timer,
corpse, actor-table and POINTS callbacks run together. Projectile image resources
use explicit numeric profiles. Helper wave/refinery clocks and unrelated GUI
clocks are inert; birth requests use an explicit helper100 hook. Base
z-order enumeration is isolated at the graphics boundary. HUD termination is
outside this check; lives can continue below zero on the controlled clock.
Wizard/projectile clocks are compared; visual monster walking/held frame clocks
remain outside the comparison, while the original FRAME callback still runs.
"""
import argparse
from dataclasses import asdict
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from worship_sim.models import Platform
from worship_sim.battle import Battle,BattleEnemy,BattleTower,EnemyProfile,PopupProfile
from worship_sim.encounter import CombatTower,EncounterInput
from worship_sim.simulation import Combatant
from worship_sim.status import TimedStatus
from worship_sim.actor import SpriteProfile
from worship_sim.native import trial_profile
from worship_sim.spawning import spawn_stats
from worship_sim.waves import Wave


def load(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def source_parts(path):
    source=load('client_source.py').source_from_asar(path)
    parts=load('check-worship-world.py').source_parts(path)
    popup=load('check-worship-popups.py').source_parts(source)
    parts.update(popup_actor=popup['actor'],popup_owner=popup['owner'],popup_queue=popup['queue'])
    def method(actor,name,following):
        registry=source.index('A["scripts.ActorEvents_'+str(actor)+'"]=')
        start=source.index(name+':function',registry)
        end=source.index('},'+following+':',start)
        return source[start+len(name)+1:end+1]
    for key,actor,name,following in (
        ('mob_hp_bars',1,'_event_HPbars','_event_StatusEffectsHPbar'),
        ('mob_update',1,'_event_StatusEffectsHPbar','_event_Movement'),
        ('mob_move',1,'_event_Movement','_event_1sec'),
        ('mob_second',1,'_event_1sec','_event_TARGET'),
        ('mob_respawn',1,'_event_Respawn','_event_FRAME'),
        ('mob_frame',1,'_event_FRAME','_event_NodeBoundary'),
        ('mob_correct',1,'_event_Corrections','init'),
        ('tower_drawing',358,'_event_Drawing','_event_press'),
        ('sailing',358,'_event_01secsailing','_event_01secninja'),
        ('ninja',358,'_event_01secninja','_event_1sec'),
        ('tower_second',358,'_event_1sec','_customEvent_NinjaMvmt')):
        parts[key]=method(actor,name,following)
    start=source.index('draw:function(){',source.index('a.prototype='))+len('draw:')
    parts['engine_draw']=source[start:source.index('},getValue:',start)+1]
    start=source.index('c.runLater(100,(function(t){D.contains(e._StatusList,"StatusMultiCombat")')+len('c.runLater(100,(')
    end=source.index('}),this.actor)',start)+1
    parts['mob_hp_sync_factory']='function(e){return '+source[start:end]+'}'
    projectile=load('check-worship-projectiles.py').source_parts(source)
    for key in ('projectile_class','projectile_owner','instance','create'):
        parts[key]=projectile[key]
    parts['add_status']=projectile['status']
    parts['contains']=projectile['contains']
    for key,name,following in (('deep_copy_list','deepCopyList','deepCopyMap'),('deep_copy_map','deepCopyMap','sortInventoryLists')):
        start=source.index('u.'+name+'=function')+len('u.'+name+'=')
        parts[key]=source[start:source.index('},u.'+following+'=',start)+1]
    parts['projectile_methods']=projectile['methods']
    for key in ('object','float','float2','manager','manager_owner','properties','properties_owner','quad_out'):
        parts['projectile_'+key]=projectile[key]
    spawning=load('check-worship-spawning.py').source_parts(source)
    for key in ('enemy_class','enemy_owner','monster_class','monster_owner','monster_types','base_owner','WorshipBASEinfos',
                '_customBlock_CreateMonster','_customBlock_2inputs'):
        parts['native_'+key]=spawning[key]
    parts['native_spawn_helper']=spawning['helper']
    return parts


def cases():
    def make(name,*,enemies=None,towers=None,draw=20,points=0,lives=20,wave=1,
             salt=0,meal=0,merit=0,language=0,hidden=False,platforms=None,route=(0,),
             enemy_profile=None,operations=None,multi=100,crit=1000,chance=100,spread=50,kraken_direction=2,wander=4,helper_y=0,
             native=None,births=()):
        scenario=EncounterInput(tuple(platforms or (Platform(0,0,10000,100),)),tuple(route),
            tuple(towers if towers is not None else (CombatTower(0,0,100,75,10,.1,200),)),
            tuple(enemies if enemies is not None else (Combatant(1,0,200,20,y=75,width=40),)),
            wave,points,lives,salt,meal,merit,draw)
        return dict(name=name,scenario=asdict(scenario),enemy_profile=asdict(enemy_profile or EnemyProfile((100,100),1,50,50)),
                    popup_profile=asdict(PopupProfile(language,hidden)),multi=multi,crit=crit,chance=chance,spread=spread,
                    kraken_direction=kraken_direction,wander=wander,helper_y=helper_y,native=native,births=births,
                    operations=operations or [['run',100],['run',500],['run',1000],['run',1690],['run',5000]])
    two=(Combatant(1,0,200,10,y=75,width=40),Combatant(2,0,190,10,y=75,width=40))
    pair=(CombatTower(0,0,100,75,10,.1,200),)*2
    result=[make('single baseline'),make('two towers change target in same phase',enemies=two,towers=pair),
            make('staggered corpses',enemies=(Combatant(1,0,220,10,y=75,width=40),
                 Combatant(2,0,210,20,y=75,width=40),Combatant(3,0,200,30,y=75,width=40))),
            make('no targets',enemies=(),operations=[['run',500],['run',2000]]),
            make('no towers',towers=(),operations=[['run',1000],['run',5000]]),
            make('no in range',enemies=(Combatant(1,0,900,20,y=75,width=40),)),
            make('moving entry',enemies=(Combatant(1,0,600,10,velocity=-7,y=75,width=40),),
                 operations=[['run',1000],['run',4200],['run',5000],['run',8000]]),
            make('popup reuse after merged duplicates',enemies=two+(Combatant(3,0,600,10,velocity=-7,y=75,width=40),),towers=pair,
                 operations=[['run',500],['run',1000],['run',3700],['run',4200],['run',7500]]),
            make('revived HP cannot revive shared alive',enemies=(Combatant(1,0,200,10,y=75,width=40),),
                 operations=[['run',500],['hp',1,100],['run',1000],['run',1190],['run',2000]]),
            make('sub-half points round after addition',points=.49999999999999994),
            make('reward percentages',wave=13,points=3.6,salt=25,meal=20,merit=30),
            make('long corpse animation',enemies=two,enemy_profile=EnemyProfile((100,)*25,15,50,50)),
            make('no points after life zero on controlled clock',lives=1,
                 enemies=(Combatant(1,0,171,20,velocity=7,y=75,width=40),),
                 platforms=(Platform(0,0,200,100,1),)),
            make('empty world',towers=(),enemies=(),operations=[['run',100],['run',2000]])]
    for draw in (10,20,30,50):
        for language in (0,2):
            for hidden in (False,True):
                result.append(make(f'popup phase draw{draw} language{language} hidden{hidden}',
                                   enemies=two,towers=pair,draw=draw,language=language,hidden=hidden))
    for direction in (-1,1):
        result.append(make(f'moving kill direction{direction}',
            enemies=(Combatant(1,0,200 if direction==1 else 400,20,velocity=7*direction,y=75,width=40),),
            platforms=(Platform(0,0,10000,100,direction),)))
        result.append(make(f'leaks direction{direction}',towers=(),lives=2,
            enemies=(Combatant(1,0,171 if direction==1 else 29,20,velocity=7*direction,y=75,width=40),),
            platforms=(Platform(0,0,200,100,direction),),operations=[['run',100],['run',200],['run',2700],['run',5200]]))
    for node,x,velocity in ((0,380.001,4.146147772912121),(1,519.999,-4.146147772912121)):
        result.append(make(f'two-node odd width start{node}',towers=(),
            platforms=(Platform(0,0,400,300,1),Platform(1,500,900,500,-1)),route=(0,1),
            enemies=(Combatant(1,node,x,3,velocity=velocity,y=275 if node==0 else 475,width=65),),
            enemy_profile=EnemyProfile((100,)*25,15,50,50),operations=[['run',100],['run',1000],['run',5000]]))
    for helper_y in (0,46,46.001,54,53.999):
        result.append(make(f'Y normalization helper{helper_y}',helper_y=helper_y,
            towers=(CombatTower(0,0,100,75,10,.1,50),),
            enemies=(Combatant(1,0,120,10,y=150,width=40),)))
    for roll in (24,25):
        bonuses=(0,20,0,125,0,0,0,0,0,0)
        result.append(make(f'Pulse traits multihit roll{roll}',multi=roll,crit=199,
            towers=(BattleTower(0,0,100,75,10,.1,200,bonuses),),
            enemies=(Combatant(1,0,200,100,y=75,width=40),)))
    bonuses=(0,0,0,100,0,5,0,0,0,0)
    result.append(make('Pulse push after both hits',towers=(BattleTower(0,0,100,75,10,.1,200,bonuses),),
        enemies=(Combatant(1,0,200,100,velocity=7,y=75,width=40),)))
    def explicit_enemy(*,identifier=1,node=0,x=200,y=75,hp=100,max_hp=100,color=0,counter=0,velocity=0,speed=0,initial=0,
                       moving=False,frozen=False,statuses=(),size=2,skull='StatusSkull0',width=40):
        return BattleEnemy(id=identifier,node=node,x=x,hp=hp,velocity=velocity,y=y,width=width,color=color,
            hit_counter=counter,max_hp=max_hp,move_speed=speed,move_speed_initial=initial,moving=moving,
            size=size,statuses=((TimedStatus(skull,36000),) if skull is not None else ())+statuses,frozen=frozen)
    blue_bonus=(0,0,0,500,0,0,0,0,0,0)
    result.extend([
        make('blue recovery and sixth hit',enemies=(explicit_enemy(color=2),),
             towers=(BattleTower(0,0,100,75,10,.1,200,blue_bonus),),
             operations=[['run',500],['run',1000],['run',2000],['run',3500],['run',5000]]),
        make('green ordinary HP-sync guard',enemies=(explicit_enemy(hp=40,color=3),),towers=(),
             operations=[['run',100],['run',1000],['run',2000]]),
        make('green heal after guarded init task',enemies=(explicit_enemy(color=3,statuses=(TimedStatus('StatusBuffHeal',1),)),),towers=(),
             operations=[['run',100],['hp',1,40],['run',1000],['run',2000],['run',3000]]),
        make('freeze expiry restores current sign',enemies=(explicit_enemy(velocity=-1,speed=1,initial=7,moving=True,
             statuses=(TimedStatus('StatusFreeze',2),)),),towers=(),
             operations=[['run',100],['run',1000],['run',2000],['run',2100]]),
        make('no-move expiry restores route direction',enemies=(explicit_enemy(velocity=0,speed=0,initial=7,moving=True,
             statuses=(TimedStatus('StatusNoMove',2),)),),towers=(),
             operations=[['run',100],['run',1000],['run',2000],['run',2100]]),
        make('frozen state holds status duration',enemies=(explicit_enemy(velocity=1,speed=1,initial=7,moving=True,frozen=True,
             statuses=(TimedStatus('StatusFreeze',2),)),),towers=(),operations=[['run',100],['run',2000],['run',4000]]),
        make('orange per-hit teleport',enemies=(explicit_enemy(color=5,velocity=7,speed=7,initial=7,moving=True),)),
        make('no skull awards no currency',enemies=(explicit_enemy(hp=10,max_hp=10,skull=None),)),
        make('size three skull five reward',wave=27,salt=25,meal=20,merit=30,
             enemies=(explicit_enemy(hp=10,max_hp=10,size=3,skull='StatusSkull5'),)),
        make('size four prevents Pulse push',towers=(BattleTower(0,0,100,75,10,.1,200,bonuses),),
             enemies=(explicit_enemy(size=4,velocity=7,speed=7,initial=7,moving=True),)),
        make('large balance rounds each addition as binary64',points=9007199254740992.,towers=pair,
             enemies=tuple(explicit_enemy(identifier=i,x=210-i*10,hp=10,max_hp=10,size=1) for i in (1,2))),
        make('Party offset consumes no attack rolls',towers=(BattleTower(5,0,100,75,0,8,250),),
             enemies=(explicit_enemy(),),operations=[['run',100],['run',500],['run',1000],['run',9000]]),
        make('Party and Pulse share target clock',towers=(BattleTower(5,0,100,75,0,8,250),CombatTower(0,0,110,75,10,.1,200))),
        make('Party holds without target',towers=(BattleTower(5,0,100,75,0,8,250),),enemies=()),
        make('Storm weakened target delayed impact',
             towers=(BattleTower(4,0,100,75,10,100,338,(0,0,0,0,200,0,0,0,0,0)),),
             enemies=(explicit_enemy(hp=20,max_hp=100),),
             operations=[['run',500],['run',720],['run',730],['run',740],['run',1490],['run',5000]]),
        make('Poison delayed damage and corpse',towers=(BattleTower(7,0,100,75,10,100,275),),
             operations=[['run',500],['run',2480],['run',2490],['run',4490],['run',4500],['run',6000],['run',11300]]),
    ])
    for roll in (999,1000):
        result.append(make(f'Poison critical strict threshold {roll}',crit=roll,
            towers=(BattleTower(7,0,100,75,10,100,275,(0,100,0,0,0,100,0,0,0,0)),),
            enemies=(explicit_enemy(hp=100,max_hp=100),),operations=[['run',500],['run',1490],['run',2490]]))
    for roll in (199,200):
        result.append(make(f'Storm critical strict threshold {roll}',crit=roll,
            towers=(BattleTower(4,0,100,75,10,100,338,(0,20,0,0,200,0,0,0,0,0)),),
            enemies=(explicit_enemy(hp=20,max_hp=100),),operations=[['run',500],['run',730],['run',740],['run',2000]]))
    for hp in (60,59.99999999999999):
        result.append(make(f'Storm weakened strict threshold {hp}',
            towers=(BattleTower(4,0,100,75,10,100,338,(0,0,0,0,200,0,0,0,0,0)),),
            enemies=(explicit_enemy(hp=hp,max_hp=100),),operations=[['run',500],['run',730],['run',1500]]))
    result.extend([
        make('Poison duration tick and critical traits',crit=999,
             towers=(BattleTower(7,0,100,75,10,100,275,(0,100,0,0,2.5,100,0,0,0,0)),),
             enemies=(explicit_enemy(hp=1000,max_hp=1000),),
             operations=[['run',500],['run',1490],['run',2490],['run',12490],['run',13000],['run',13800]]),
        make('Storm retained target already killed by Pulse',
             towers=(BattleTower(4,0,100,75,10,100,338),CombatTower(0,0,100,75,20,100,200)),
             enemies=(explicit_enemy(hp=20,max_hp=100),),
             operations=[['run',500],['run',730],['run',1190],['run',1490],['run',5000]]),
        make('Storm and Poison cross-animation pool reuse',
             towers=(BattleTower(4,0,100,75,1,100,338),BattleTower(7,0,500,75,1,100,130)),
             enemies=(explicit_enemy(hp=1000,max_hp=1000,x=251,velocity=7,speed=7,initial=7,moving=True),),
             operations=[['run',500],['run',1490],['run',2000],['run',4000],['run',13000]]),
        make('Poison and Storm cross-animation pool reuse',
             towers=(BattleTower(7,0,100,75,1,100,275),BattleTower(4,0,1200,75,1,100,130)),
             enemies=(explicit_enemy(hp=1000,max_hp=1000,x=200,velocity=7,speed=7,initial=7,moving=True),),
             operations=[['run',500],['run',11280],['run',12500],['run',14000]]),
        make('Poison filters other route nodes',
             platforms=(Platform(0,0,1000,100,1),Platform(1,0,1000,300,1)),route=(0,1),
             towers=(BattleTower(7,0,100,75,10,100,140),),
             enemies=(Combatant(1,0,200,30,y=75,width=40),Combatant(2,0,220,20,y=75,width=40),
                      Combatant(3,0,270,20,y=75,width=40),Combatant(4,1,200,20,y=275,width=40)),
             operations=[['run',500],['run',2490],['run',2500],['run',4490],['run',4500],['run',7000],['run',11300]]),
        make('Storm targets leading route node',
             platforms=(Platform(0,0,1000,100,1),Platform(1,0,1000,300,-1)),route=(0,1),
             towers=(BattleTower(4,0,100,75,10,.1,500),BattleTower(5,0,110,75,0,8,500)),
             enemies=(Combatant(1,0,200,20,y=75,width=40),Combatant(2,1,220,20,y=275,width=40)),
             operations=[['run',500],['run',730],['run',1500],['run',5000]]),
    ])
    mixed=(BattleTower(5,0,90,75,0,8,250),BattleTower(4,0,100,75,10,1,338),
           BattleTower(7,0,110,75,4,3,275),CombatTower(0,0,120,75,5,.1,200))
    for draw in (10,20,30,50):
        result.append(make(f'mixed Pulse Party Storm Poison draw{draw}',draw=draw,towers=mixed,
            enemies=(Combatant(1,0,220,100,y=75,width=40),Combatant(2,0,210,60,y=75,width=40),
                     Combatant(3,0,200,20,y=75,width=40)),
            operations=[['run',500],['run',730],['run',1000],['run',2490],['run',5000],['run',15000]]))
    for direction in (-1,1):
        result.append(make(f'Frozone forward direction{direction} and speed expiry',
            platforms=(Platform(0,0,10000,100,direction),),
            towers=(BattleTower(3,0,100 if direction==1 else 300,75,10,100,200,(0,0,0,0,15,2,0,0,0,0)),),
            enemies=(explicit_enemy(velocity=7*direction,speed=7,initial=7,moving=True),),
            operations=[['run',500],['run',1000],['run',2000],['run',6000],['run',8000],['run',9000]]))
        result.append(make(f'Frozone behind direction{direction} holds',
            platforms=(Platform(0,0,10000,100,direction),),
            towers=(BattleTower(3,0,100 if direction==1 else 300,75,10,100,200),),
            enemies=(explicit_enemy(x=50 if direction==1 else 350),),operations=[['run',500],['run',1000]]))
    result.extend([
        make('Frozone selected later node behind blocks fallback',
            platforms=(Platform(0,0,1000,100,1),Platform(1,0,1000,300,1)),route=(0,1),
            towers=(BattleTower(3,0,100,75,10,100,500),),
            enemies=(Combatant(1,0,150,100,y=75,width=40),Combatant(2,1,50,100,y=275,width=40))),
        make('Frozone selected equal X blocks fallback',
            platforms=(Platform(0,0,1000,100,1),Platform(1,0,1000,300,1)),route=(0,1),
            towers=(BattleTower(3,0,100,75,10,100,500),),
            enemies=(Combatant(1,0,150,100,y=75,width=40),Combatant(2,1,100,100,y=275,width=40))),
        make('Frozone wave can hit behind after forward acquisition',
            towers=(BattleTower(3,0,100,75,10,100,200),),
            enemies=(Combatant(1,0,200,100,y=75,width=40),Combatant(2,0,50,100,y=75,width=40))),
        make('Frozone zero velocity expiry uses negative sign',
            towers=(BattleTower(3,0,100,75,0,100,200),),
            enemies=(explicit_enemy(velocity=0,speed=0,initial=7,moving=True),),
            operations=[['run',500],['run',2000],['run',6000],['run',6100]]),
    ])
    for chance in (24,25):
        result.append(make(f'Void half cooldown strict roll{chance}',chance=chance,
            towers=(BattleTower(8,0,100,75,0,2,100,(0,0,0,0,25,0,0,0,0,0)),),
            enemies=(explicit_enemy(x=150),),operations=[['run',500],['run',1000],['run',2000],['run',3000]]))
    for first in ('StatusBuffHeal','StatusSkull0','StatusFreeze'):
        statuses=(TimedStatus(first,8 if first!='StatusSkull0' else 36000),)+tuple(
            TimedStatus(name,8 if name!='StatusSkull0' else 36000)
            for name in ('StatusSkull0','StatusBuffHeal','StatusNoMove') if name!=first)
        result.append(make(f'Void ordered statuses first {first}',
            towers=(BattleTower(8,0,100,75,10,100,200),),
            enemies=(explicit_enemy(color=3,hp=100,max_hp=100,skull=None,statuses=statuses),),
            operations=[['run',500],['run',1000],['run',2000],['run',4000]]))
    result.append(make('Void empty status list leaves color',towers=(BattleTower(8,0,100,75,10,100,200),),
        enemies=(explicit_enemy(color=3,skull=None),),operations=[['run',500],['run',2000]]))
    for color in (1,4):
        result.append(make(f'Void lethal color{color} suppresses death effect',
            towers=(BattleTower(8,0,150,75,10,100,200),),
            enemies=(explicit_enemy(color=color,hp=10,max_hp=10),explicit_enemy(identifier=2,x=190,hp=40,max_hp=100)),
            operations=[['run',500],['run',1000],['run',2000],['run',5000]]))
        result.append(make(f'color{color} no skull has no death effect',
            towers=(CombatTower(0,0,150,75,10,100,200),),
            enemies=(explicit_enemy(color=color,hp=10,max_hp=10,skull=None),explicit_enemy(identifier=2,x=190,hp=40,max_hp=100))))
    for old in (False,True):
        result.append(make(f'color1 healing expiry overwrite{old}',
            towers=(CombatTower(0,0,100,75,10,100,200),),
            enemies=(explicit_enemy(color=1,hp=10,max_hp=10),explicit_enemy(identifier=2,x=190,hp=40,max_hp=100,
                statuses=(TimedStatus('StatusBuffHeal',8),) if old else ())),
            operations=[['run',500],['run',1000],['run',2000],['run',3000],['run',4000],['run',5000]]))
    for offset in (-1e-9,0,1e-9):
        result.append(make(f'color1 sixty range boundary {offset}',
            towers=(CombatTower(0,0,150,75,10,100,200),),
            enemies=(explicit_enemy(color=1,hp=10,max_hp=10),
                     explicit_enemy(identifier=2,x=200-60/.9604339-offset,hp=40,max_hp=100)),
            operations=[['run',500],['run',1000],['run',2000]]))
        result.append(make(f'color4 seventy placement range boundary {offset}',
            towers=(BattleTower(0,0,150,75,10,.1,200,placement_x=200+(70-.397824735*25)/.9604339+offset),),
            enemies=(explicit_enemy(color=4,hp=10,max_hp=10),explicit_enemy(identifier=2,x=190)),
            operations=[['run',500],['run',1000],['run',5000]]))
    for remaining in (2.1-1e-12,2.1,2.1+1e-12):
        result.append(make(f'color4 stored cooldown threshold {remaining}',
            towers=(BattleTower(5,0,150,75,0,2,200),),enemies=(explicit_enemy(color=4),),
            operations=[['run',500],['remaining',0,remaining],['hp',1,0],['run',520],['run',6120],['run',6500]]))
    result.append(make('color4 overlapping visual timers',towers=(CombatTower(0,0,150,75,10,.1,200),)*2,
        enemies=(explicit_enemy(color=4,hp=10,max_hp=10),explicit_enemy(identifier=2,x=190,color=4,hp=10,max_hp=10)),
        operations=[['run',500],['run',1000],['run',4580],['run',4780],['run',6000]]))
    result.append(make('color4 distance uses placement rather than Wizard X',
        towers=(BattleTower(0,0,100,75,10,.1,200,placement_x=200),),
        enemies=(explicit_enemy(color=4,hp=10,max_hp=10),explicit_enemy(identifier=2,x=190))))
    for skulls in (('StatusSkull16','StatusSkull0'),('StatusSkull5','StatusSkull2')):
        result.append(make(f'lowest Skull break {skulls}',enemies=(explicit_enemy(hp=10,max_hp=10,skull=None,
            statuses=tuple(TimedStatus(name,36000) for name in skulls)),)))
    result.append(make('retained recycled monster default differs from current',
        enemy_profile=EnemyProfile((100,100),1,50,50,SpriteProfile(35,33,(100,)*7,True)),
        enemies=(explicit_enemy(hp=10,max_hp=10,width=65),),
        operations=[['run',500],['run',700],['run',1190],['run',5000]]))
    six=mixed+(BattleTower(3,0,80,75,3,2,250,(0,0,0,0,15,2,0,0,0,0)),BattleTower(8,0,100,75,2,2,250))
    for draw in (10,20,30,50):
        result.append(make(f'six-type mixed draw{draw}',draw=draw,towers=six,
            enemies=(explicit_enemy(hp=1000,max_hp=1000,color=4),explicit_enemy(identifier=2,x=190,hp=40,max_hp=100,color=1),
                     explicit_enemy(identifier=3,x=180,hp=500,max_hp=500,color=3)),
            operations=[['run',500],['run',730],['run',1000],['run',2490],['run',5000],['run',15000]]))
    result.extend([
        make('Boulder first contact after cast',towers=(BattleTower(2,0,100,75,10,100,200),),
             enemies=(explicit_enemy(x=130),),operations=[['run',500],['run',580],['run',590],['run',3000],['run',3400]]),
        make('Fireball flight before first impact',towers=(BattleTower(1,0,22,75,10,100,200),),
             enemies=(explicit_enemy(x=100),),operations=[['run',500],['run',700],['run',2280],['run',2290],['run',3000],['run',6000]]),
        make('Boulder six contacts finish after five budget exhausted',towers=(BattleTower(2,0,100,75,10,100,200),),
             enemies=tuple(explicit_enemy(identifier=i+1,x=130) for i in range(6)),
             operations=[['run',500],['run',590],['run',600],['run',880],['run',1000]]),
        make('Boulder fractional additional hit budget and duration',
             towers=(BattleTower(2,0,100,75,10,100,200,(0,0,0,0,100,3.5,0,0,0,0)),),
             enemies=tuple(explicit_enemy(identifier=i+1,x=130) for i in range(10)),
             operations=[['run',500],['run',590],['run',880],['run',6000]]),
        make('Boulder duration trait without contact',
             towers=(BattleTower(2,0,100,75,10,100,500,(0,0,0,0,100,0,0,0,0,0)),),
             enemies=(explicit_enemy(x=500),),
             operations=[['run',500],['run',3000],['run',5490],['run',5780],['run',6000]]),
        make('Boulder selected later node blocks fallback',
             platforms=(Platform(0,0,1000,100,1),Platform(1,0,1000,300,1)),route=(0,1),
             towers=(BattleTower(2,0,100,75,10,100,500),),
             enemies=(Combatant(1,0,150,100,y=75,width=40),Combatant(2,1,150,100,y=275,width=40))),
        make('Boulder may contact a different route node',
             platforms=(Platform(0,0,10000,100,1),Platform(1,0,10000,100,1)),route=(0,1),
             towers=(BattleTower(2,0,100,75,10,100,200,(0,0,0,0,200,0,0,0,0,0)),),
             enemies=(Combatant(1,0,130,100,y=75,width=40),Combatant(2,1,320,100,y=75,width=40)),
             operations=[['run',500],['run',590],['run',3800],['run',4500],['run',8300]]),
        make('Boulder corpse eligibility after Pulse kill',
             towers=(BattleTower(2,0,100,75,10,100,200),CombatTower(0,0,100,75,10,100,200)),
             enemies=(explicit_enemy(x=130,hp=10,max_hp=10),explicit_enemy(identifier=2,x=125)),
             operations=[['run',500],['hp',1,100],['run',590],['run',690],['run',1190],['run',4000]]),
        make('Boulder remembers contact through HP reset',towers=(BattleTower(2,0,100,75,10,100,200),),
             enemies=(explicit_enemy(x=130),),operations=[['run',590],['hp',1,100],['run',690],['run',900],['run',3400]]),
        make('Fireball first five area hits and corpses',towers=(BattleTower(1,0,22,75,10,100,200),),
             enemies=tuple(explicit_enemy(identifier=i+1,x=100,hp=10,max_hp=10) for i in range(6)),
             operations=[['run',500],['run',2290],['run',2300],['run',2990],['run',6000]]),
        make('Fireball excludes Pulse corpse before landing',
             towers=(BattleTower(1,0,22,75,10,100,200),CombatTower(0,0,22,75,10,100,200)),
             enemies=(explicit_enemy(x=100,hp=10,max_hp=10),explicit_enemy(identifier=2,x=95)),
             operations=[['run',500],['run',1190],['run',2290],['run',3000],['run',6000]]),
    ])
    for direction in (-1,1):
        result.append(make(f'Boulder direction{direction} boundary and lifetime overlap',
            platforms=(Platform(0,0,240,100,direction),),
            towers=(BattleTower(2,0,100,75,10,100,100),),
            enemies=(explicit_enemy(x=60 if direction==-1 else 180),),
            operations=[['run',500],['run',1000],['run',2000],['run',3000],['run',3400]]))
        result.append(make(f'Fireball direction{direction} moving aim and critical',crit=199,
            towers=(BattleTower(1,0,22 if direction==1 else 300,75,10,100,500,(0,20,0,0,0,50,0,0,0,0)),),
            enemies=(explicit_enemy(x=100 if direction==1 else 200,velocity=direction*3,speed=3,initial=3,moving=True),),
            operations=[['run',500],['run',2290],['run',3000],['run',6000]]))
    for chance in (49,50):
        result.append(make(f'Fireball A double strict chance{chance}',chance=chance,spread=0,
            towers=(BattleTower(1,0,22,75,10,100,200,(0,0,0,0,50,0,0,0,0,0)),),
            enemies=(explicit_enemy(x=100),),
            operations=[['run',500],['run',990],['run',2290],['run',2790],['run',4000],['run',6500]]))
    for spread in (-50,50):
        result.append(make(f'Fireball double spread{spread} crosses nodes',chance=1,spread=spread,
            platforms=(Platform(0,0,10000,100,1),Platform(1,0,10000,100,1)),route=(0,1),
            towers=(BattleTower(1,0,22,75,10,100,200,(0,0,0,0,100,0,0,0,0,0)),),
            enemies=(explicit_enemy(node=1,x=100),explicit_enemy(identifier=2,x=50),explicit_enemy(identifier=3,x=150)),
            operations=[['run',500],['run',2290],['run',2790],['run',4000],['run',6500]]))
    for roll in (199,200):
        result.append(make(f'Boulder critical strict roll{roll}',crit=roll,
            towers=(BattleTower(2,0,100,75,10,100,200,(0,20,0,0,0,0,0,0,0,0)),),
            enemies=(explicit_enemy(x=130),),operations=[['run',500],['run',590],['run',3400]]))
    for first,second in ((2,1),(1,2)):
        label='Boulder and Fireball' if first==2 else 'Fireball and Boulder'
        result.append(make(label+' cross-animation pool reuse',
            towers=(BattleTower(first,0,100 if first==2 else 22,75,1,100,200),
                    BattleTower(second,0,800,75,1,100,100)),
            enemies=(explicit_enemy(x=130 if first==2 else 100,hp=1000,max_hp=1000),
                     explicit_enemy(identifier=2,x=1200,hp=1000,max_hp=1000,velocity=-7,speed=7,initial=7,moving=True)),
            operations=[['run',500],['run',3300],['run',4300],['run',6000],['run',8000]]))
    eight=six+(BattleTower(2,0,100,75,2,2,250,(0,0,0,0,100,2,0,0,0,0)),
               BattleTower(1,0,22,75,2,2,250,(0,0,0,0,50,50,0,0,0,0)))
    for draw in (10,20,30,50):
        result.append(make(f'eight-type mixed draw{draw}',draw=draw,towers=eight,chance=24,spread=0,
            enemies=(explicit_enemy(hp=1000,max_hp=1000,color=4),explicit_enemy(identifier=2,x=190,hp=40,max_hp=100,color=1),
                     explicit_enemy(identifier=3,x=180,hp=500,max_hp=500,color=3)),
            operations=[['run',500],['run',730],['run',1000],['run',2490],['run',5000],['run',15000]]))
    result.extend([
        make('Kraken targetless prestack cap',towers=(BattleTower(6,0,100,75,10,.1,200),),enemies=(),
             operations=[['run',500],['run',1000],['run',2000],['run',2500],['run',6000]]),
        make('Kraken multiple owners have independent caps',towers=(BattleTower(6,0,100,75,10,.1,200),)*2,enemies=(),
             operations=[['run',500],['run',2000],['run',2500],['run',6000]]),
        make('Kraken contacts ignore Storm critical bonus',
             towers=(BattleTower(6,0,100,75,10,100,200,(0,100,0,0,0,0,0,0,0,0)),),
             enemies=(explicit_enemy(x=100),),operations=[['run',500],['run',690],['run',1000],['run',3000]]),
    ])
    for bonus in (4,8):
        result.append(make(f'Kraken effective cap A{bonus} targetless',
            towers=(BattleTower(6,0,100,75,10,.1,200,(0,0,0,0,bonus,0,0,0,0,0)),),enemies=(),
            operations=[['run',500],['run',2500],['run',4500],['run',6500],['run',8000]]))
    for bonus in (2,4):
        result.append(make(f'Kraken effective contacts B{bonus}',
            towers=(BattleTower(6,0,100,75,10,100,200,(0,100,0,0,0,bonus,0,0,0,0)),),
            enemies=(explicit_enemy(x=100,hp=1000,max_hp=1000),),
            operations=[['run',500],['run',690],['run',1500],['run',3000],['run',6000],['run',12000]]))
    for roll in (19,20):
        result.append(make(f'Kraken contacts critical strict roll{roll}',crit=roll,
            towers=(BattleTower(6,0,100,75,10,100,200),),enemies=(explicit_enemy(x=100),),
            operations=[['run',500],['run',690],['run',3000],['run',6000]]))
    result.append(make('Kraken zero tower damage still has minimum contact damage',crit=19,
        towers=(BattleTower(6,0,100,75,0,100,200),),enemies=(explicit_enemy(x=100),),
        operations=[['run',500],['run',690],['run',3000]]))
    for width,size in ((40,1),(65,2),(50,3),(65,4)):
        for direction in (-1,1):
            result.append(make(f'Kraken width{width} size{size} direction{direction} motion',
                kraken_direction=1 if direction==-1 else 2,
                platforms=(Platform(0,0,1000,100,direction),),
                towers=(BattleTower(6,0,100,75,10,100,200),),
                enemies=(explicit_enemy(x=100,width=width,size=size),),
                operations=[['run',500],['run',690],['run',800],['run',1000],['run',1500],['run',3000],['run',6000]]))
    result.extend([
        make('Kraken retained corpse after lethal contact',towers=(BattleTower(6,0,100,75,10,100,200),),
             enemies=(explicit_enemy(x=100,hp=5,max_hp=5),explicit_enemy(identifier=2,x=110,hp=100,max_hp=100)),
             operations=[['run',500],['run',690],['run',700],['run',890],['run',1390],['run',2000],['run',5000]]),
        make('Kraken corpse contact damages previous live remembered target',
             towers=(BattleTower(6,0,100,75,10,100,200),),
             enemies=(explicit_enemy(x=100),explicit_enemy(identifier=2,x=105,hp=5,max_hp=5)),
             operations=[['run',500],['hp',2,0],['run',520],['run',690],['run',890],['run',1200],['run',5000]]),
        make('Kraken retained reference aliases survivor after corpse compaction',
             towers=(BattleTower(6,0,100,75,10,100,200),),
             enemies=(explicit_enemy(x=100),explicit_enemy(identifier=2,x=105,hp=100,max_hp=100)),
             operations=[['run',500],['run',690],['hp',1,0],['run',700],['run',1390],['run',1500],['run',2000],['run',5000]]),
        make('Kraken and Pulse create same-draw corpses',
             towers=(BattleTower(6,0,100,75,10,.1,200),CombatTower(0,0,90,75,10,.1,200)),
             enemies=tuple(explicit_enemy(identifier=i+1,x=100-i,hp=10,max_hp=10) for i in range(5)),
             operations=[['run',500],['run',690],['run',1000],['run',3000],['run',6000]]),
        make('Kraken two owners share contact space and corpse timers',
             towers=(BattleTower(6,0,100,75,10,.1,200),BattleTower(6,0,110,75,10,.1,200)),
             enemies=tuple(explicit_enemy(identifier=i+1,x=100+i,hp=100,max_hp=100) for i in range(5)),
             operations=[['run',500],['run',690],['run',1000],['run',2500],['run',5000],['run',10000]]),
    ])
    for draw in (10,20,30,50):
        for direction in (-1,1):
            result.append(make(f'nine-type mixed draw{draw} direction{direction}',draw=draw,
                platforms=(Platform(0,0,10000,100,direction),),
                towers=eight+(BattleTower(6,0,100,75,3,.1,200,(0,100,0,0,4,2,0,0,0,0)),),
                chance=24,spread=0,kraken_direction=1 if direction==-1 else 2,
                enemies=(explicit_enemy(hp=1000,max_hp=1000,color=4,width=65),
                         explicit_enemy(identifier=2,x=190,hp=40,max_hp=100,color=1,width=50),
                         explicit_enemy(identifier=3,x=180,hp=500,max_hp=500,color=3,width=65)),
                operations=[['run',500],['run',730],['run',1000],['run',2490],['run',5000],['run',15000]]))
    for direction in (-1,1):
        result.append(make(f'nine-type complete clear direction{direction}',
            platforms=(Platform(0,0,10000,100,direction),),
            towers=eight+(BattleTower(6,0,100,75,3,.1,200,(0,100,0,0,4,2,0,0,0,0)),),
            chance=24,spread=0,kraken_direction=1 if direction==-1 else 2,
            enemies=(explicit_enemy(hp=100,max_hp=100,color=4,width=65),
                     explicit_enemy(identifier=2,x=190,hp=60,max_hp=100,color=1,width=50),
                     explicit_enemy(identifier=3,x=180,hp=20,max_hp=100,color=3,width=65)),
            operations=[['run',500],['run',2490],['run',5000],['run',15000],['run',20000]]))
    for direction in (-1,1):
        result.append(make(f'off-100 route crossing direction{direction}',towers=(),
            platforms=(Platform(0,0,200,100,direction),),
            enemies=(explicit_enemy(x=179 if direction==1 else 21,velocity=7*direction,speed=7,initial=7,moving=True),),
            operations=[['run',10],['run',20],['run',30],['run',40],['run',90],['run',100],['run',110]]))
    for trial in range(8):
        native=trial_profile(trial)
        result.append(make(f'native trial{trial} spawn reuse during helper100',native=trial,enemies=(),
            enemy_profile=native.enemy,platforms=(Platform(0,0,2000,300,1),),
            towers=(CombatTower(0,0,100,275,1000,.1,2000),),
            births=({'at':100,'id':1,'wave':[1,0,2,0]},
                    {'at':3000,'id':2,'wave':[1,0,2,0]},
                    {'at':6000,'id':3,'wave':[1,0,2,0]}),
            operations=[['run',90],['run',100],['run',190],['run',500],['run',2800],['run',3000],['run',6000],['run',9000]]))
    native=trial_profile(0)
    result.append(make('native simultaneous births preserve allocated pool order',native=0,enemies=(),
        enemy_profile=native.enemy,platforms=(Platform(0,0,2000,300,1),),
        towers=(CombatTower(0,0,100,275,1000,.1,2000),)*2,
        births=tuple({'at':at,'id':identifier,'wave':[1,0,2,0]}
                     for at,identifier in ((100,1),(100,2),(3000,3),(3000,4))),
        operations=[['run',100],['run',500],['run',2800],['run',3000],['run',5000]]))
    native=trial_profile(2)
    result.append(make('native reused actor remains a retained Kraken target',native=2,enemies=(),
        enemy_profile=native.enemy,platforms=(Platform(0,0,2000,300,1),),
        towers=(BattleTower(6,0,50,275,10,100,2000,(0,0,0,0,0,4,0,0,0,0)),),
        births=({'at':100,'id':1,'wave':[1,0,2,0]},{'at':2100,'id':2,'wave':[1,0,2,0]}),
        operations=[['run',100],['run',690],['run',700],['run',2090],['run',2100],['run',2290],['run',2490],['run',5000]]))
    return result


def decode(case):
    value=case['scenario']
    towers=[]
    for tower in value['towers']:
        if 'bonuses' in tower:
            towers.append(BattleTower(**{**tower,'bonuses':tuple(tower['bonuses'])}))
        else:towers.append(CombatTower(**tower))
    enemies=[]
    for enemy in value['enemies']:
        if 'max_hp' in enemy:
            enemies.append(BattleEnemy(**{**enemy,'statuses':tuple(TimedStatus(**row) for row in enemy['statuses'])}))
        else:enemies.append(Combatant(**enemy))
    scenario=EncounterInput(**{**value,'platforms':tuple(Platform(**p) for p in value['platforms']),
        'route':tuple(value['route']),'towers':tuple(towers),'enemies':tuple(enemies)})
    profile=case['enemy_profile'];default=profile.get('default_sprite')
    return scenario,EnemyProfile(**{**profile,'frames':tuple(profile['frames']),
        'default_sprite':SpriteProfile(**{**default,'frames':tuple(default['frames'])}) if default else None}),PopupProfile(**case['popup_profile'])


def modeled(case):
    scenario,enemy_profile,popup_profile=decode(case)
    before=asdict(scenario)
    events=[];rolls=[];battle=None
    def random_int(low,high):
        value=(case['multi'] if (low,high)==(0,100) else case['crit'] if (low,high)==(0,1000)
               else case['chance'] if (low,high)==(1,100) else case['spread'] if (low,high)==(-50,50)
               else case['kraken_direction'] if (low,high)==(1,2) else case['wander'] if (low,high)==(1,4) else high)
        if type(value) is not int or not low<=value<=high:raise ValueError('The fixture supplied an invalid integer roll.')
        rolls.append([battle.loop.now_ms,low,high,value]);return value
    battle=Battle(scenario,enemy_profile=enemy_profile,popup_profile=popup_profile,random_int=random_int,
                  helper_y=case['helper_y'],on_event=lambda *event:events.append(list(event)))
    retained=battle._monster_pool
    if case['native'] is not None:
        native=trial_profile(case['native']);platform=scenario.platforms[0]
        original_tenth=battle.loop._tasks[0].callback
        def tenth(task):
            original_tenth(task)
            for birth in case['births']:
                if birth['at']!=battle.loop.now_ms:continue
                wave=Wave(*birth['wave']);stats=spawn_stats(wave,base_hp=native.base_hp,base_speed=native.base_speed,map_id=native.map_id)
                battle.spawn(BattleEnemy(birth['id'],platform.node,platform.left+25,stats.hp,velocity=stats.speed,
                    y=platform.y-native.enemy.definition_height+(native.enemy.definition_height-50)/2+25,
                    width=native.sprite.width,max_hp=stats.hp,move_speed=stats.speed,move_speed_initial=stats.speed,
                    moving=True,size=wave.size,color=wave.color,statuses=(TimedStatus('StatusSkull'+str(stats.skull),36000),)))
        battle.loop._tasks[0].callback=tenth
    def snapshot():
        return dict(now=battle.loop.now_ms,points=battle.points,lives=battle.lives,remaining_hp=battle.remaining_hp,
            monsters=[[m.source_id,m.monster_id,m.hp,battle.monsters.alive(m),m.alive,m.node,m.x,m.y,m.velocity] for m in battle.monsters.actors],
            retained=[[m.source_id,m.monster_id,m.hp,battle.monsters.alive(m),m.alive] for m in retained],
            retained_geometry=[[m.source_id,m.x,m.y,m.width,m.body.height,m.velocity] for m in retained],
            wizards=[[w.id,w.animation.frame,w.animation.elapsed_ms,w.animation.finished,w.remaining] for w in battle._wizards],
            underlings=[[w.id,[a.id for a in w.underlings]] for w in battle._wizards],
            conditions=[[m.source_id,m.color,m.hit_counter,m.move_speed,m.max_hp,m.moving,m.frozen,
                         [[row.name,row.seconds] for row in m.statuses]] for m in battle.monsters.actors],
            projectiles=[[a.id,a.alive,a.body.x,a.body.y,a.body.left,a.body.top,a.body.width,a.body.height,
                          a.animation.frame,a.animation.elapsed_ms,a.animation.finished,a.motion.vx,a.motion.vy,a.fading]
                         for a in battle.projectiles._pool],
            actors=[[a.id,a.kind] for a in battle.actors if a is not None],
            timers=[[t.actor.id if t.actor else None,t.interval_ms,t.remaining_ms,t.repeat,t.done] for t in battle.loop._tasks],
            events=[event[:] for event in events],rolls=[roll[:] for roll in rolls])
    result=[]
    for command,*args in case['operations']:
        if command=='run':battle.run_until(args[0])
        elif command=='hp':next(m for m in retained if m.source_id==args[0]).hp=args[1]
        elif command=='remaining':battle._wizards[args[0]].remaining=args[1]
        else:raise ValueError(command)
        result.append(snapshot())
    if asdict(scenario)!=before:raise AssertionError('Battle mutated its supplied encounter actors')
    return result


SCRIPT=r'''
const vm=require('node:vm'),data=JSON.parse(require('node:fs').readFileSync(0,'utf8')),p=data.parts;
function execute(test){
 let now=0,nextID=0,sceneTemp=test.scenario.enemies.length,lastCreated=null,routeSubject=null,casting=null,pendingBirth=null;
 const s=test.scenario,profile=test.enemy_profile,popupProfile=test.popup_profile,events=[],rolls=[];
 const ctx={A:{},jj:{},Dh:{},db:{_assert(x){if(!x)throw Error('Original table assertion')}},mh:{next:()=>1},
  Bc:{init(xs,x,first=0,end=xs.length){for(let i=first;i<end;i++)xs[i]=x;return xs}},
  oa:function(){this.nameMap={h:{}};this.wrapper={enabled:true}},E:(base,fields)=>Object.assign({},base,fields),
  Y:{caught:e=>({get_message:()=>e.stack??String(e)})},la:{fullError(message){throw Error(message)}},Ge:{visitStringCache(){}}};
 vm.createContext(ctx);const fn=key=>vm.runInContext('('+p[key]+')',ctx);
 ctx.Bc.blit=fn('blit');vm.runInContext(p.growth+p.inner+p.iterator+p.table,ctx);
 const Table=ctx[p.table_owner],surface={get_graphics:()=>({clear(){}})},layer={overlay:surface},attrs={};
 const engine={tasks:[],allActors:new Table(16),whenTypeGroupKilledEvents:{h:{}},whenTypeGroupCreatedEvents:{h:{}},
  recycledActorsOfType:{h:{34:[],478:[]}},isPaused:()=>false,addTask(task){this.tasks.push(task)},
  getGameAttribute:key=>{if(!(key in attrs))throw Error('Missing attribute '+key);return attrs[key]},gameAttributes:{h:attrs},
  getLayerById:()=>layer,getLayerByName:()=>layer,removeActorFromLayer(actor){actor.layer=null},moveActorToLayer(actor,target){actor.layer=target},
  whenMouseReleased:{},interactiveLayers:[],hudLayer:{overlay:surface},transitionLayer:surface,whenDrawing:{length:0},
  g:{graphics:null,resetGraphicsSettings(){},translateToActor(){},translateToScreen(){},setFont(){},drawString(){}},leave:null,enter:null,shaders:null};
 engine.allActors.reuseIterator=true;
 Object.assign(ctx,{a:{engine,STEP_SIZE:10,NO_PHYSICS:false,SCALE:1,physicsScale:10,toPhysicalUnits:x=>x/10,toPixelUnits:x=>x*10},c:{engine},n:{__cast:x=>x},B:{},ka:{},rc:{},ma:{},z:{},
  Tu:{},Di:{},Uu:{},l:function(){this.h={}},ib:{getTimer:()=>now},D:{contains:(xs,x)=>xs.includes(x)},h:{string:String},
  V:function(x,y){this.x=x;this.y=y},
  y:{replace:(text,a,b)=>text.split(a).join(b)},t:{linear:{apply:x=>x}},va:{antialias:false},w:(self,method)=>method.bind(self),
  ba:{remove:(xs,x)=>{const i=xs.indexOf(x);if(i>=0)xs.splice(i,1)}}});
 vm.runInContext(p.constructor+p.prototype+p.registration+p.popup_actor,ctx);
 vm.runInContext(p.projectile_object+p.projectile_float+p.projectile_float2+p.projectile_manager+p.projectile_properties+
                 p.projectile_class+p.instance,ctx);
 ctx[p.native_base_owner]={};
 vm.runInContext(p.native_monster_class+p.native_WorshipBASEinfos+p.native_enemy_class,ctx);
 Object.assign(ctx[p.native_monster_owner],p.native_monster_types);
 const nativeDefinitions=ctx[p.native_monster_owner].get(),nativeBase=ctx[p.native_base_owner].WorshipBASEinfos();
 const Manager=ctx[p.projectile_manager_owner];Manager.resetStatics();ctx.t.quadOut={apply:fn('projectile_quad_out')};
 const phase=vm.runInContext('(function(){var n,t;'+p.phase+'})',ctx),draw=fn('engine_draw');
 engine.recycleActor=fn('recycleActor');engine.getRecycledActorOfTypeOnLayer=fn('getRecycledActorOfTypeOnLayer');
 const actorMethods={};for(const[name,body]of Object.entries(p.actor_methods))actorMethods[name]=vm.runInContext('('+body+')',ctx);
 const projectileMethods={};for(const[name,body]of Object.entries(p.projectile_methods))projectileMethods[name]=vm.runInContext('('+body+')',ctx);
 const originalCast=fn('event'),originalDamage=fn('damage'),originalKill=fn('kill'),originalTenth=fn('cooldown');
 const popupQueue=vm.runInContext('(function(){var t=this,e,i,s,u;'+p.popup_queue+'})',ctx);
 const image=()=>({get_width:()=>8,get_height:()=>8,set_alpha(){}});
 function eventList(){return {length:0,listeners:[],_dispatchIndex:0}}
 function add(list,callback){list.listeners.push(callback);list.length=list.listeners.length}
 function animate(durations,looping,width=0,height=0){
  return {model:{sync:false,looping,frames:Array(durations.length).fill(null)},numFrames:durations.length,
   frameIndex:0,timer:0,finished:false,durations,filter:null,set_bitmapData(){},set_filter(){},set_visible(){},
   get_width:()=>width,get_height:()=>height,getCurrentFrame(){return this.frameIndex},update:fn('animupdate'),setFrame:fn('animsetframe')};
 }
 function actor(kind,x=0,y=0,width=0,height=0,animation=null){
  const a={...actorMethods,ID:nextID++,kind,physicsMode:1,ignoreGravity:true,defaultGravity:true,isHUD:false,
   paused:false,recycled:false,dead:false,dying:false,collidable:false,continuousCollision:false,
   cacheWidth:width,cacheHeight:height,currOffset:{x:0,y:0},realX:x,realY:y,xSpeed:0,ySpeed:0,rSpeed:0,
   realAngle:0,fixedRotation:false,lastScale:{x:1,y:1},realScaleX:1,realScaleY:1,currAnimation:animation,
   layer,whenKilled:{length:0},whenDrawing:eventList(),whenUpdated:eventList(),bodyDef:null,
   isAlive(){return !(this.dead||this.dying||this.recycled)},isPaused(){return this.paused},
   getType:()=>({__id__:0}),getGroup:()=>({__id__:0}),getZIndex:()=>0,
   getCurrentFrame(){return this.currAnimation?.frameIndex??0},getNumFrames(){return this.currAnimation?.numFrames??0},
   setCurrentFrame(frame){this.currAnimation?.setFrame(frame)},getAnimation(){return this.animationName??''},
   resetListeners(){this.whenDrawing=eventList();this.whenUpdated=eventList()},
   getYVelocity(){return this.ySpeed},setYVelocity(value){this.ySpeed=value},clearCollisionInfoList(){}};
  for(const method of ['growTo','fadeTo','makeAlwaysSimulate','makeSometimesSimulate','moveToBottom','anchorToScreen','setZIndex','cancelTweens','clearFilters','setFilter','sendToBack',
   'resetBlendMode','set_alpha','switchToDefaultAnimation','disableActorDrawing','removeAttachedImages','removeAllListeners',
   'enableAllBehaviors','enableActorDrawing','setAngle','setIgnoreGravity','updateDrawingMatrix'])a[method]=()=>{};
  a.setXY=function(x,y){this.realX=x+Math.floor(this.cacheWidth/2);this.realY=y+Math.floor(this.cacheHeight/2)};
  engine.allActors.set(a.ID,a);return a;
 }
 function installBody(a,profiles,defaultName,left,top){
  Object.assign(a,projectileMethods,{body:null,currAnimation:null,currAnimationName:null,
   defaultAnim:defaultName,cacheWidth:0,cacheHeight:0,currOrigin:{x:0,y:0},shapeMap:{h:{}},bitmapFilters:null,drawActor:true,
   animationMap:{h:{}},originMap:{h:{}},addChild(){},removeChild(){},updateChildrenPositions(){}});
  for(const[name,[width,height,durations,looping,ox,oy]]of Object.entries(profiles)){
   a.animationMap.h[name]=animate(durations,looping,width,height);a.originMap.h[name]={x:ox,y:oy};
  }
  a.tweenProps=new ctx[p.projectile_properties_owner]();a.tweenProps.xy.doOnUpdate(()=>a.updateTweenXY());
  a.switchToDefaultAnimation();a.setLocation(left,top);
 }
 const inventory=actor('inventory'),helperActor=actor('helper',0,test.helper_y),allMonsters=[],bases=[],wizards=[];
 const inventoryBehavior={actor:inventory,_PixelQueueSEND:1};add(inventory.whenUpdated,()=>popupQueue.call(inventoryBehavior));
 const gen=Array(100).fill(0);gen[8]=s.wave;gen[13]=0;gen[16]=s.route;gen[17]=s.route.map(node=>s.platforms.find(p=>p.node===node).direction===1?0:1);
 gen[19]=[];gen[23]=[s.lives,s.lives];gen[27]='Blank';gen[51]=s.points;gen[54]=[];gen[56]=[];gen[84]=1;
 let currentLives=s.lives;Object.defineProperty(gen[23],1,{get:()=>currentLives,set(value){
  if(value<currentLives){if(!routeSubject)throw Error('A life write has no route subject');events.push([now,'leak',routeSubject.sourceID,value])}
  currentLives=value},configurable:true});
 const helper={wrapper:{enabled:true},actor:helperActor,_GenINFO:gen};
 const misc=Array(150).fill(0),pixels=Array(9).fill({behaviors:{getBehavior:()=>helper}});
 pixels[0]=inventory;pixels[8]={behaviors:{getBehavior:()=>({_GenINFO:misc})}};
 Object.assign(attrs,{CurrentMap:26,MonsterHP:[0],MonsterAlive:[0],MonsterWillDie:[0],MapMonstersList:[],MonsterRespawnTime:Array(100).fill(0),
  NodeX:[],NodeLength:[],NodeY:[],CustomLists:{h:{NonDMGLinemonsterTypes:[],WorshipNODESnETC:[[gen[16],gen[17]]]}},
  CustomMaps:{h:{WorshipMapType:{h:{26:0}},SpecLetters:{h:{}}}},PixelHelperActor:pixels,
  MonsterDefinitionsGET:{h:{synthetic:{h:{Type:'Monster',Name:'Synthetic',DeathFrame:profile.death_frame,MovingFrame:0,
   HeightOfMonster:profile.definition_height,Defence:0,SpecialType:'',ExpType:0,ExpGiven:0}}}},
  DNSM:{h:{FamBonusQTYs:{h:{40:0}},StarSigns:{h:{ExpActive:0}}}},Tasks:[[0,[1e300]]],QuestComplete:{h:{Royal_Worm5:1,Capital_P3:1,Bellows2:1}},
  NONdummies:Array(50).fill(0),OptionsListAccount:Array(700).fill(0),OptionsList:Array(30).fill(0),OtherPlayers:{h:{'0':{behaviors:{getBehavior:()=>({_TargetEnemy:null})}}}},
  UserInfo:['0'],PlayerAutoMoveTOGGLE:1,SceneEvents_n:0,InventoryOrder:[],Lv0:Array(10).fill(0),ItemGetPixelQueue:[],MenuType2:0,dummyDisplayEXPTYPE:'Null',
  DummyText:'',DummyList:[],DummyNumbersStatManager:{h:{}},OriginPixelActor:[inventory]});
 if(test.native!==null){
  const nativeName=nativeBase[test.native][2],maps=[26,63,30,107,155,208,259,308];
  attrs.CurrentMap=maps[test.native];attrs.MonsterDefinitionsGET=nativeDefinitions;
  attrs.CustomMaps.h.WorshipMapType.h[attrs.CurrentMap]=test.native;
  attrs.CustomLists.h.WorshipNODESnETC=Array.from({length:8},()=>[gen[16],gen[17]]);
  attrs.CustomLists.h.WorshipBASEinfos=nativeBase;
  attrs.CustomLists.h.WorshipInfo=Array.from({length:8},()=>test.births.map(b=>b.wave));
  attrs.CustomLists.h.PrayerInfo=[];attrs.CustomLists.h.RANDOlist=Array.from({length:100},()=>[]);
  attrs.CustomLists.h.NinjaInfo=Array.from({length:40},()=>[]);
  attrs.MonstersOnScreen=Array(400).fill(0);attrs.DummyText3='nana';gen[24]=[0,1,1,1,2,0];gen[53]=0;gen[62]=30;
 }
 attrs.OptionsListAccount[327]=1;attrs.OptionsListAccount[539]=popupProfile.hidden?1:0;
 for(const platform of s.platforms){attrs.NodeX[platform.node]=platform.left;attrs.NodeLength[platform.node]=platform.right;attrs.NodeY[platform.node]=platform.y}
 function service(name,methods){return new Proxy(methods,{get(obj,key){if(key in obj)return obj[key];throw Error('Unexpected '+name+' service '+String(key))}})}
 Object.assign(ctx,{p:service('worship',{_customBlock_Dungon:()=>-1,_customBlock_Shrine:()=>0,_customBlock_SaltLick:()=>s.salt_lick,
   _customBlock_PlaySound(){},_customBlock_TowerStats:(name,kind,level)=>{
    const tower=s.towers[level-1];if(name==='damage')return tower.damage;if(name==='range')return tower.radius;throw Error('Unexpected tower stat '+name)}}),
  m:service('account',{_customBlock_Windwalker:()=>0,_customBlock_Summoning:()=>0,_customBlock_ArcaneType:()=>0,
   _customBlock_Summoning2:()=>s.meritoc_points,_customBlock_Language:()=>popupProfile.language,_customBlock_LANGUAGEfont:()=>0}),
  x:service('player',{_customBlock_DamageDealed:()=>0,_customBlock_ExpMulti:()=>1,_customBlock_GetBuffBonuses:()=>0}),
  v:service('progress',{_customBlock_CardBonusREAL:()=>0,_customBlock_giveEXP(){},_customBlock_performETCaction(action){
   if(action!=='MonsterRespawnTimeReset')throw Error('Unexpected account recalculation '+action)}}),u:{getPartyMembers:()=>[]},
  q:service('map',{_customBlock_MealBonus:()=>s.meal_points}),k:service('damage',{_customBlock_killmonsterQuest(){},_customBlock_addImgInst:image,_customBlock_NotateNumber:String})});
 ctx.p._customBlock_WorshipStuff=fn('worship');ctx.q._customBlock_Hitscanning=fn('hitscan');ctx.k._customBlock_DistanceEqn=fn('distance');
 ctx.D.contains=fn('contains');ctx.u.deepCopyList=fn('deep_copy_list');ctx.u.deepCopyMap=fn('deep_copy_map');
 vm.runInContext(p.add_status,ctx);
 vm.runInContext(p.native__customBlock_CreateMonster+p.native__customBlock_2inputs,ctx);
 helper._customEvent_WorshipStuff=fn('native_spawn_helper');engine.whenMouseReleased=eventList();
 Object.assign(ctx.c,{asNumber:fn('as_number'),randomFloat:()=>.9999999999999999,
  randomInt(low,high){const value=low===0&&high===100?test.multi:low===0&&high===1000?test.crit:low===1&&high===100?test.chance:
   low===-50&&high===50?test.spread:low===1&&high===2?test.kraken_direction:low===1&&high===4?test.wander:high;
   if(!Number.isInteger(value)||value<low||value>high)throw Error('The fixture supplied an invalid integer roll.');
   rolls.push([now,low,high,value]);return value},
  getCurrentSceneName:()=>'Acorn',getActorType:value=>value,
  getActorsOfType:type=>type===1?allMonsters:type===358?wizards:[],
  getLastCreatedActor:()=>lastCreated,getValueForScene:(scene,key)=>{if(key==='_NumberOfEnemies')return 0;if(key==='_NumberOfEnemiesTEMP')return sceneTemp;throw Error(key)},
  setValueForScene:(scene,key,value)=>{if(key!=='_NumberOfEnemiesTEMP')throw Error(key);sceneTemp=value},
  recycleActor(a){const wasAlive=a.isAlive();engine.recycleActor(a);if(wasAlive&&a.kind==='monster')events.push([now,'recycle',a.sourceID,0])},
  attachImageToActor(){},fadeImageTo(){},removeImage(){},setXForImage(){},setYForImage(){},createSaturationFilter:()=>({}),createHueFilter:()=>({})});
 const popupType={ID:34,__id__:34},projectileType={ID:478,__id__:478,groupID:0},monsterType={ID:1,__id__:1,groupID:0};
 ctx.Wc={get:()=>({resources:{get:id=>{if(id===478)return projectileType;if(id===1)return monsterType;throw Error('Unexpected resource '+id)}}})};
 ctx.ch={};
 const projectileProfiles={'0':[35,33,Array(7).fill(100),true,17,33],
                           '1':[30,28,[...Array(6).fill(80),10000,...Array(8).fill(80)],false,15,28],
                           '2':[72,80,[80,80,80,...Array(7).fill(100)],false,36,80],
                           '3':[72,23,Array(12).fill(80),true,36,23],
                           '4':[50,34,Array(4).fill(100),true,25,34],
                           '5':[34,50,Array(7).fill(100),true,17,50],
                           '7':[72,23,Array(12).fill(100),true,36,23],
                           '6':[66,18,Array(6).fill(100),true,33,18]};
 function projectileInit(a){
  if(!a.projectileBehavior)a.projectileBehavior=new ctx[p.projectile_owner](null,null,null);
  const script=a.projectileBehavior;script.actor=a;script.addListener=add;a.fading=false;
  a.behaviors={getBehavior:()=>script};script.init();
 }
 const nativeProfiles={
  mushG:[50,50,Array.from({length:16},(_,i)=>i===15?10000:100),false,25,50],
  goblinG:[65,50,Array.from({length:25},(_,i)=>i===24?10000:100),false,32,50],
  moonman:[52,54,Array.from({length:27},(_,i)=>i>=22&&i<=24?80:100),false,26,54],
  acorn:[80,44,Array.from({length:21},(_,i)=>i===20?10000:100),false,40,44],
  snowball:[60,50,Array(28).fill(100),false,30,50],w4b2:[50,50,Array(28).fill(100),false,25,50],
  w5b3:[45,45,Array.from({length:28},(_,i)=>i===27?1000:100),false,22,45],
  w6b4:[68,66,Array(35).fill(100),false,34,66],w7a8:[60,60,Array(32).fill(100),false,30,60]};
 function nativeInit(a){
  if(!pendingBirth)throw Error('Native actor initialization has no supplied spawn action.');
  a.sourceID=pendingBirth.id;
  if(!a.script){
   const script=new ctx[p.native_enemy_owner]();script.actor=a;script.wrapper={enabled:true};script.addListener=add;
   const kill=script._event_KILL;script._event_KILL=function(...args){
    const before=attrs.MonsterAlive[this._MonsterID],points=gen[51];kill.apply(this,args);
    if(before===1&&attrs.MonsterAlive[this._MonsterID]===0)events.push([now,'death',a.sourceID,gen[51]-Math.round(points)]);
   };
   let node=0;Object.defineProperty(script,'_MonsterNODE',{get:()=>node,set(value){node=value;routeSubject=a},configurable:true});
   a.script=script;a.behaviors={getBehavior:()=>script};allMonsters.push(a);
  }
  a.script.init();
 }
 engine.createActor=instance=>{
  if(instance.actorID===1){
   const a=actor('monster');installBody(a,nativeProfiles,'mushG',instance.x,instance.y);
   a.getType=()=>monsterType;a.initScripts=()=>nativeInit(a);engine.recycledActorsOfType.h[1].push(a);return a;
  }
  if(instance.actorID!==478)throw Error('Unexpected instance '+instance.actorID);
  const a=actor('projectile');installBody(a,projectileProfiles,'0',instance.x,instance.y);
  a.getType=()=>projectileType;a.moveToLayer=target=>engine.moveActorToLayer(a,target);
  a.fadeTo=(alpha)=>{if(alpha===0)a.fading=true};a.initScripts=()=>projectileInit(a);
  engine.recycledActorsOfType.h[478].push(a);return a;
 };
 function popupInit(a){
  if(!a.popupBehavior)a.popupBehavior=new ctx[p.popup_owner](null,null,null);
  const popup=a.popupBehavior;popup.actor=a;popup.addListener=add;
  a.behaviors={getBehavior:()=>popup};popup.init();
 }
 const createProjectile=fn('create');
 engine.createActorOfType=(type,x,y,node)=>{if(type.ID===478||type.ID===1)return createProjectile.call(engine,type,x,y,node);
  if(type.ID!==34)throw Error('Unexpected actor creation');const a=actor('popup',x,y);a.initScripts=()=>popupInit(a);engine.recycledActorsOfType.h[34].push(a);a.initScripts();return a};
 ctx.c.createRecycledActor=(type,x,y,node)=>{if(type!==34&&type!==478&&type!==1)throw Error('Unexpected actor type '+type);
  lastCreated=engine.getRecycledActorOfTypeOnLayer(type===34?popupType:type===1?monsterType:projectileType,x,y,0)};
 ctx.k._customBlock_CreateDmgPixel=(hits,target,modifiers)=>{
  const before=ctx.c.asNumber(attrs.MonsterHP[target.script._MonsterID]);const value=originalDamage(hits,target,modifiers);
  const damage=before-ctx.c.asNumber(attrs.MonsterHP[target.script._MonsterID]);
  if(casting?.kind===0)casting.damage+=damage;else events.push([now,'hit',target.sourceID,damage]);return value;
 };
 function observeCast(behavior){
  const before=behavior.actor.getCurrentFrame(),record={damage:0,kind:behavior._PersonalNUM};casting=record;
  try{originalCast.call(behavior)}finally{casting=null}
  const offset=15*behavior._PersonalNUM;
  if(behavior.actor.getAnimation()==='Wizard'&&before===offset+4&&behavior.actor.getCurrentFrame()===offset+5)
   events.push([now,'cast',behavior._PersonalNUM===6?-1:behavior._PersonalLIST[2].sourceID,record.damage]);
 }
 engine.recycledActorsOfType.h[1]=[];
 ctx.c.runPeriodically(100,()=>{
  originalTenth.call(helper);
  for(const[index,birth]of test.births.entries())if(birth.at===now){
   pendingBirth=birth;helper._TRIGGEREDtext='f'+(index+1);helper._customEvent_WorshipStuff();pendingBirth=null;
  }
 },helperActor);
 ctx.c.runPeriodically(1000,()=>{},helperActor);ctx.c.runPeriodically(10000,()=>{},helperActor);
 for(let index=0;index<s.enemies.length;index++){
  const input=s.enemies[index],a=actor('monster',input.x,input.y,input.width,profile.height,animate(profile.frames,false));
  const current=[input.width,profile.height,profile.frames,false,Math.floor(input.width/2),profile.height],
        defaultSprite=profile.default_sprite,resources={synthetic:current};
  if(defaultSprite)resources.default=[defaultSprite.width,defaultSprite.height,defaultSprite.frames,defaultSprite.looping,
                                   Math.floor(defaultSprite.width/2),defaultSprite.height];
  const defaultName=defaultSprite?'default':'synthetic',initial=resources[defaultName];
  installBody(a,resources,defaultName,input.x-Math.floor(initial[0]/2),input.y-Math.floor(initial[1]/2));
  a.setAnimation('synthetic');
  a.sourceID=input.id;a.animationName='synthetic';a.xSpeed=input.velocity;
  const script={actor:a,wrapper:{enabled:true},_MonsterID:index+1,_MonsterNODE:input.node,_MonsterType:'synthetic',_IsWorshipMob:1,
   _PetStatus:0,_WorshipMOD:input.color,_PersNum:input.hit_counter,_IsCardDisp:0,_TempMonster:1,_MonsterMoving:Number(input.moving??(input.velocity!==0)),
   _MoveSPEED:input.move_speed??Math.abs(input.velocity),_MoveSPEEDinitial:input.move_speed_initial??Math.abs(input.velocity),_Frozen:Number(input.frozen??false),_DeathFrame:profile.death_frame,_MovingFrame:0,
   _SizeMulti:input.size??2,_MonsterHPtot:input.max_hp??input.hp,_Monster0ffsetX:0,_Monster0ffsetY:0,_HpBarImgInst:[0,0,0,0,0,0],
   _StatusList:(input.statuses??[{name:'StatusSkull0',seconds:36000}]).map(row=>row.name),
   _StatusActive:(input.statuses??[{name:'StatusSkull0',seconds:36000}]).map(row=>[row.name,row.seconds]),
   _StatusImgInst:(input.statuses??[{name:'StatusSkull0',seconds:36000}]).map(image)};
  a.script=script;a.behaviors={getBehavior:()=>script};allMonsters.push(a);attrs.MapMonstersList.push(a);
  let node=input.node;Object.defineProperty(script,'_MonsterNODE',{get:()=>node,set(value){node=value;routeSubject=a},configurable:true});
  attrs.MonsterHP.push(input.hp);attrs.MonsterAlive.push(1);attrs.MonsterWillDie.push(0);
  ctx.c.runLater(100,fn('mob_hp_sync_factory')(script),a);
  ctx.c.runPeriodically(2000,fn('mob_move').bind(script),a);ctx.c.runPeriodically(1000,fn('mob_second').bind(script),a);
  add(a.whenUpdated,fn('mob_update').bind(script));
  for(const key of ['mob_hp_bars','mob_respawn','mob_frame','node_boundary'])add(a.whenDrawing,fn(key).bind(script));
  add(a.whenDrawing,()=>{const id=script._MonsterID,before=attrs.MonsterAlive[id],points=gen[51];originalKill.call(script);
   if(before===1&&attrs.MonsterAlive[id]===0)events.push([now,'death',a.sourceID,gen[51]-Math.round(points)])});
  add(a.whenDrawing,fn('mob_correct').bind(script));
 }
 for(let index=0;index<s.towers.length;index++){
  const tower=s.towers[index],base=actor('base',tower.x,tower.y),wizard=actor('wizard',tower.x,tower.y,0,0,
   animate(Array.from({length:136},(_,f)=>[4,14,19,29,34,44,49,64,79,94,109].includes(f)?10000:100),true));
  base.animationName='Tower';wizard.animationName='Wizard';bases.push(base);wizards.push(wizard);
  wizard.setCurrentFrame(15*tower.kind);
  const bonus={h:{}};for(let b=0;b<10;b++)bonus.h[b]=tower.bonuses?.[b]??0;
  const baseBehavior={actor:base,wrapper:{enabled:true},_PersonalLIST:[tower.kind,index,0,0,[]],_PersonalNUM:0};
  const wizardBehavior={actor:wizard,wrapper:{enabled:true},_PersonalNUM:tower.kind,_PersonalLIST:[tower.kind,index,'Filler',0,-1,-1,0,base,1]};
  base.behaviors={getBehavior:()=>baseBehavior};wizard.behaviors={getBehavior:()=>wizardBehavior};
  add(base.whenDrawing,fn('tower_drawing').bind(baseBehavior));add(wizard.whenDrawing,fn('tower_drawing').bind(wizardBehavior));
  gen[56].push([tower.kind,tower.node,tower.placement_x??tower.x,0,-1,index+1,base,wizard,tower.cooldown,'',bonus,0]);
  wizardBehavior._PersonalLIST[8]=s.platforms.find(p=>p.node===tower.node).direction;
  for(const [a,behavior]of [[base,baseBehavior],[wizard,wizardBehavior]]){
   ctx.c.runPeriodically(100,()=>observeCast(behavior),a);ctx.c.runPeriodically(100,fn('sailing').bind(behavior),a);
   ctx.c.runPeriodically(100,fn('ninja').bind(behavior),a);ctx.c.runPeriodically(1000,fn('tower_second').bind(behavior),a);
  }
 }
 function collect(){const out=[],it=engine.allActors.iterator();while(it.hasNext())out.push(it.next());return out}
 function snapshot(){return {now,points:gen[51],lives:gen[23][1],remaining_hp:attrs.MapMonstersList.reduce((sum,a)=>sum+Math.max(0,ctx.c.asNumber(attrs.MonsterHP[a.script._MonsterID])),0),
  monsters:attrs.MapMonstersList.map(a=>[a.sourceID,a.script._MonsterID,ctx.c.asNumber(attrs.MonsterHP[a.script._MonsterID]),attrs.MonsterAlive[a.script._MonsterID]??null,a.isAlive(),a.script._MonsterNODE,a.getXCenter(),a.getYCenter(),a.getXVelocity()]),
  retained:allMonsters.map(a=>[a.sourceID,a.script._MonsterID,ctx.c.asNumber(attrs.MonsterHP[a.script._MonsterID]),attrs.MonsterAlive[a.script._MonsterID]??null,a.isAlive()]),
  retained_geometry:allMonsters.map(a=>[a.sourceID,a.getXCenter(),a.getYCenter(),a.cacheWidth,a.cacheHeight,a.getXVelocity()]),
  wizards:wizards.map(a=>[a.ID,a.currAnimation.frameIndex,a.currAnimation.timer,a.currAnimation.finished,gen[56][a.behaviors.getBehavior()._PersonalLIST[1]][4]]),
  underlings:wizards.map(a=>[a.ID,a.behaviors.getBehavior()._PersonalLIST[7].behaviors.getBehavior()._PersonalLIST[4].map(a=>a.ID)]),
  conditions:attrs.MapMonstersList.map(a=>[a.sourceID,a.script._WorshipMOD,a.script._PersNum,a.script._MoveSPEED,a.script._MonsterHPtot,
   Boolean(a.script._MonsterMoving),Boolean(a.script._Frozen),a.script._StatusActive.map(row=>row.slice())]),
  projectiles:engine.recycledActorsOfType.h[478].map(a=>[a.ID,a.isAlive(),a.getXCenter(),a.getYCenter(),a.getX(false),a.getY(false),
   a.cacheWidth,a.cacheHeight,a.currAnimation.frameIndex,a.currAnimation.timer,a.currAnimation.finished,a.xSpeed,a.ySpeed,a.fading]),
  actors:collect().filter(Boolean).map(a=>[a.ID,a.kind]),timers:engine.tasks.map(t=>[t.actor?.ID??null,t.interval,t.timer,t.repeats,t.done]),events:events.map(e=>e.slice()),rolls:rolls.map(r=>r.slice())}}
 const observations=[];
 for(const [command,...args]of test.operations){
  if(command==='hp'){const a=allMonsters.find(a=>a.sourceID===args[0]);attrs.MonsterHP[a.script._MonsterID]=args[1]}
  else if(command==='remaining')gen[56][args[0]][4]=args[1];
  else if(command==='run')while(now<args[0]){
   now+=10;
   Manager.update(10);
   phase.call(engine);
   const it=engine.allActors.iterator();while(it.hasNext()){
    const a=it.next();if(!a||!a.isAlive())continue;a.internalUpdate(10,true);
    for(a.whenUpdated._dispatchIndex=0;a.whenUpdated._dispatchIndex<a.whenUpdated.length;a.whenUpdated._dispatchIndex++)a.whenUpdated.listeners[a.whenUpdated._dispatchIndex](10);
   }
   if(now%s.draw_interval_ms===0)draw.call(engine);
  }else throw Error(command);
  observations.push(snapshot());
 }
 return observations;
}
process.stdout.write(JSON.stringify(data.cases.map(execute)));
'''


def difference(actual,expected,path=''):
    if type(actual) is dict and type(expected) is dict:
        if actual.keys()!=expected.keys():return path,actual.keys(),expected.keys()
        for key in actual:
            found=difference(actual[key],expected[key],path+'.'+key)
            if found:return found
    elif isinstance(actual,list) and isinstance(expected,list):
        if len(actual)!=len(expected):return path+'.length',len(actual),len(expected)
        for index,(left,right) in enumerate(zip(actual,expected)):
            found=difference(left,right,f'{path}[{index}]')
            if found:return found
    elif actual!=expected:
        if re.search(r'\.(?:monsters\[\d+\]\[[678]\]|retained_geometry\[\d+\]\[[125]\]|projectiles\[\d+\]\[(?:[2345]|11|12)\])$',path) and isinstance(actual,(int,float)) and isinstance(expected,(int,float)):
            if math.isclose(actual,expected,rel_tol=1e-12,abs_tol=1e-10):return None
        return path,actual,expected
    return None


def check(path,filter_name=None):
    scenarios=[case for case in cases() if filter_name is None or filter_name in case['name']]
    if not scenarios:raise ValueError('No matching scenarios')
    run=subprocess.run(['node','-e',SCRIPT],input=json.dumps(dict(parts=source_parts(path),cases=scenarios)),
                       text=True,capture_output=True,check=True,timeout=30)
    # Integer tokens emitted by JSON.stringify still represent JS binary64.
    original=json.loads(run.stdout,parse_int=float)
    for case,expected in zip(scenarios,original,strict=True):
        if case['name'].startswith('Kraken effective cap A'):
            bonus=case['scenario']['towers'][0]['bonuses'][4]
            if len(expected[-1]['underlings'][0][1])!=4+bonus:
                raise AssertionError('The original targetless Kraken fixture did not reach its supplied cap.')
        if case['name'].startswith('nine-type complete clear') and expected[-1]['remaining_hp']!=0:
            raise AssertionError('The original complete-clear fixture did not clear its supplied enemies.')
        if 'cross-animation pool reuse' in case['name']:
            first=expected[0]['projectiles'];reused=expected[2]['projectiles']
            initial_shape,reused_shape=next(shapes for prefix,shapes in (
                ('Storm',([72,80],[66,18])),('Poison',([66,18],[72,80])),
                ('Boulder',([35,33],[30,28])),('Fireball',([30,28],[35,33]))) if case['name'].startswith(prefix))
            if not (len(first)==len(reused)==1 and first[0][0]==reused[0][0]
                    and first[0][6:8]==initial_shape and reused[0][6:8]==reused_shape and reused[0][1]):
                raise AssertionError(dict(message='The original cross-animation fixture did not reuse its projectile actor.',
                                          first=first,reused=reused,events=expected[2]['events']))
        actual=modeled(case)
        found=difference(actual,expected)
        if found:
            where,left,right=found
            detail=dict(case=case['name'],field=where,model=left,original=right)
            if '.rolls' in where:detail['original_rolls']=expected[int(where[1:where.index(']')])]['rolls']
            raise AssertionError(detail)
    return len(scenarios),sum(len(case['operations']) for case in scenarios)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar',type=Path,required=True);parser.add_argument('--case')
    args=parser.parse_args()
    try:
        count,observations=check(args.asar,args.case)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr[-2000:])
    print(f'{count} assembled Worship worlds and {observations} observations match original callbacks. HUD termination remains outside this clock.')
