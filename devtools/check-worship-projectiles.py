"""Compare persistent Worship effects with original client methods.

Original Actor478 initialization/callbacks, timer phase, Actor geometry,
animations, pooling and recycling execute unchanged. Numeric image resources,
enemy positions, actor storage and external input actions are controlled by the
host. Per-hit HP changes use the original damage function; monster death/XP,
visual opacity/scale and complete battles are outside this check.
"""
import argparse
from dataclasses import dataclass, field
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from worship_sim.models import Platform
from worship_sim.damage import apply_hits
from worship_sim.projectiles import (Projectiles, DEFAULT_PROFILE, POISON_PROFILE,
    STORM_PROFILE, FREEZE_PROFILE, VOID_PROFILE, STUN_PROFILE, FIREBALL_PROFILE, KRAKEN_PROFILE)
from worship_sim.motion import Motion
from worship_sim.simulation import Combatant, TimerLoop, freeze_velocity
from worship_sim.status import TimedStatus, add_status, void_cleanse
from worship_sim.targeting import can_hit


def load(file, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'devtools' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_parts(source):
    parts = load('check-worship-actor.py', 'actor').source_parts(source)
    parts.update(load('check-worship-simulation.py', 'timers').source_parts(source))
    marker = 'A["scripts.ActorEvents_478"]='
    registry = source.index(marker)
    owner = re.match(r'[A-Za-z_$][\w$]*', source[registry + len(marker):])[0]
    start = source.rfind('var ' + owner + '=function', 0, registry)
    end = source.index('});', source.index('},forwardMessage:', registry)) + 3
    parts['projectile_class'] = source[start:end]
    parts['projectile_owner'] = owner
    marker = 'A["com.stencyl.models.scene.ActorInstance"]='
    registry = source.index(marker)
    owner = re.match(r'[A-Za-z_$][\w$]*', source[registry + len(marker):])[0]
    start = source.rfind('var ' + owner + '=function', 0, registry)
    parts['instance'] = source[start:registry]
    for key, name, following in (('create', 'createActorOfType', 'getTopLayer'),
                                  ('acquire', 'getRecycledActorOfTypeOnLayer', 'createActorOfType')):
        start = source.index(name + ':function(') + len(name) + 1
        parts[key] = source[start:source.index('},' + following + ':', start) + 1]
    marker = 'A["com.stencyl.models.Actor"]='
    registry = source.index(marker)
    owner = re.match(r'[A-Za-z_$][\w$]*', source[registry + len(marker):])[0]
    prototype = source.index(owner + '.prototype=', registry)
    for name in ('getAnimation', 'setAngle', 'setIgnoreGravity'):
        start = source.index(name + ':function(', prototype)
        end = re.search(r'},[A-Za-z_$][\w$]*:', source[start:])
        parts['methods'][name] = source[start + len(name) + 1:start + end.start() + 1]
    loader = load('client_source.py', 'loader')
    _, parts['worship'] = loader.function(source, '_customBlock_WorshipStuff')
    parts['damage'] = load('check-worship-damage.py', 'damage').damage_function(source)
    parts['distance'] = load('check-worship-targeting.py', 'target').source_parts(source)['distance']
    parts['hitscan'] = load('check-worship-targeting.py', 'target').source_parts(source)['hitscan']
    _, parts['status'] = loader.function(source, '_customBlock_AddStatusToMonster')
    start = source.index('D.contains=function') + len('D.contains=')
    parts['contains'] = source[start:source.index('},D.', start) + 1]
    return parts


def scenarios():
    def enemy(ident, x, hp=100, *, node=0, worship=True, color=0, velocity=0, width=40, **fields):
        return dict(id=ident, node=node, x=x, hp=hp, worship=worship,
                    color=color, velocity=velocity, width=width, **fields)
    def poison(label, **changes):
        args = dict(left=100, top=0, node=0, damage=10, duration_seconds=1,
                    tick_seconds=.5, crit_percent=0)
        args.update(changes)
        return dict(kind='poison', label=label, args=args)
    def storm(label, **changes):
        args = dict(left=200, top=0, target=0, damage=10, crit_percent=0)
        args.update(changes)
        return dict(kind='storm', label=label, args=args)
    def wave(kind, label, **changes):
        args = dict(left=83, top=-16, damage=10, crit_percent=0, radius=50)
        if kind == 'freeze':
            args.update(slow_percent=90, extra_seconds=2)
        args.update(changes)
        return dict(kind=kind, label=label, args=args)
    def stun(label, **changes):
        args = dict(left=100, top=0, duration_seconds=5.6)
        args.update(changes)
        return dict(kind='stun', label=label, args=args)
    def boulder(label, **changes):
        args = dict(left=100, top=69, direction=1, node=0, damage=10,
                    duration_seconds=2.5, hit_budget=1, crit_percent=0)
        args.update(changes)
        return dict(kind='boulder', label=label, args=args)
    def fireball(label, **changes):
        args = dict(left=0, top=49, direction=1, node=0, aim_x=100, damage=10,
                    radius_percent=100, delay_seconds=0, crit_percent=0)
        args.update(changes)
        return dict(kind='fireball', label=label, args=args)
    def kraken(label, **changes):
        args = dict(left=81,top=56,node=0,damage=10,origin_x=100,contacts=2,push_direction=-1)
        args.update(changes)
        return dict(kind='kraken',label=label,args=args)
    return [
        dict(name='poison filters and fade', end=2000,
             enemies=[enemy(0,171,30),enemy(1,175),enemy(2,117,node=1),
                      enemy(3,117,worship=False),enemy(4,117,0)],
             actions=[[0,poison('cloud')]]),
        dict(name='retained ineligible storm target', end=1100, rng=[999], enemies=[enemy(0,200,5)],
             actions=[[0,storm('bolt',crit_percent=100)],
                      [0,dict(kind='enemy',target=0,changes=dict(hp=-5,alive=False))]]),
        dict(name='creation inside timer phase', end=2000, enemies=[enemy(0,117)],
             actions=[[0,dict(kind='schedule',delay=100,action=poison('cloud'))]]),
        dict(name='shared allocation-order pool and fractional positions', end=4000, enemies=[enemy(0,117)],
             actions=[[0,poison('first',damage=0,duration_seconds=2,tick_seconds=1,left=100.75)],
                      [0,storm('second',damage=0)],
                      [2800,storm('reused',damage=0,left=200.75,top=100.25)],
                      [2800,poison('other',damage=0,left=-.75,top=-.75,node=1)]]),
        dict(name='strict critical boundary and orange movement', end=1600, rng=[1000,999,0,1000],
             enemies=[enemy(0,171,200,color=5,velocity=7)],
             actions=[[0,storm('bolt',crit_percent=100)],
                      [0,poison('cloud',crit_percent=100,tick_seconds=.25,duration_seconds=.6)]]),
        dict(name='storm target removed from ordered list', end=1100, enemies=[enemy(0,200,20)],
             actions=[[0,storm('bolt')],[100,dict(kind='unlist',target=0)]]),
        dict(name='paused actor timer phases', end=1500, enemies=[enemy(0,200)],
             actions=[[0,storm('bolt')],[100,dict(kind='pause',label='bolt',value=True)],
                      [400,dict(kind='pause',label='bolt',value=False)]]),
        dict(name='pool retains explicit actor pause', end=2400, enemies=[enemy(0,117)],
             actions=[[0,storm('bolt')],[100,dict(kind='pause',label='bolt',value=True)],
                      [100,dict(kind='recycle',label='bolt')],[200,poison('cloud')],
                      [500,dict(kind='pause',label='cloud',value=False)]]),
        dict(name='simultaneous recycle changes timer iteration', end=1200, enemies=[enemy(0,117)],
             actions=[[0,storm('a')],[0,storm('b')],[0,poison('cloud',duration_seconds=0)]]),
        dict(name='freeze signed speed, zero and lethal status overwrite', end=900,
             enemies=[enemy(0,120,5,velocity=19,statuses=[['StatusFreeze',20]]),
                      enemy(1,130,node=1,velocity=-19),enemy(2,100,velocity=0)],
             actions=[[0,wave('freeze','ice')]]),
        dict(name='freeze strict range and shared alive/pet/worship guards', end=900,
             enemies=[enemy(0,150,velocity=7),enemy(1,149,velocity=-7,node=1),
                      enemy(2,100,alive=False),enemy(3,100,pet_status=1),
                      enemy(4,100,worship=False),enemy(5,100,hp=0)],
             actions=[[0,wave('freeze','ice',radius=48.021695)]]),
        dict(name='freeze damage then orange reposition then status', end=900,
             enemies=[enemy(0,125,color=5,velocity=-19)],
             actions=[[0,wave('freeze','ice',slow_percent=15)]]),
        dict(name='void lethal cleanse first status only and empty statuses', end=900,
             enemies=[enemy(0,140,5,color=3,statuses=[['StatusBuffHeal',8],['StatusSkull16',36000],['StatusNoMove',8]]),
                      enemy(1,100,color=4,statuses=[]),
                      enemy(2,120,color=2,hit_counter=-1,statuses=[['StatusSkull0',36000],['StatusBuffHeal',8]])],
             actions=[[0,wave('void','void',radius=10)]]),
        dict(name='void forty extra radius strict boundary across nodes', end=900,
             enemies=[enemy(0,150),enemy(1,149,node=1,color=3,statuses=[['StatusFreeze',8],['StatusNoMove',9]])],
             actions=[[0,wave('void','void',radius=8.021695)]]),
        dict(name='overlapping stun fade and recycle traversal', end=5820,enemies=[],
             actions=[[0,stun('first')],[0,stun('second',left=200)]]),
        dict(name='cross-animation ice void stun pool and fractional positions',end=2200,
             enemies=[enemy(0,100)],actions=[[0,wave('freeze','ice')],
             [900,wave('void','void',left=83.75,top=-16.75)],
             [1800,stun('stun',left=-.75,top=.75,duration_seconds=0)]]),
        dict(name='boulder completes six hits after budget exhaustion',end=450,
             enemies=[enemy(i,121,y=75) for i in range(6)],actions=[[0,boulder('rock')]]),
        dict(name='boulder contact memory survives hp reset',end=2800,
             enemies=[enemy(0,121,y=75)],actions=[[0,boulder('rock',hit_budget=5)],
             [100,dict(kind='enemy',target=0,changes=dict(hp=100))]]),
        dict(name='boulder left boundary and no node contact restriction',end=800,
             enemies=[enemy(0,18,y=75,node=1)],
             actions=[[0,boulder('rock',left=0,direction=-1,hit_budget=5)]]),
        dict(name='boulder right boundary strict center',end=800,platforms=[[0,0,40,100],[1,0,1000,200]],
             enemies=[],actions=[[0,boulder('rock',left=24,hit_budget=0)]]),
        dict(name='boulder right boundary equality is still active',end=650,
             platforms=[[0,0,40.5,100],[1,0,1000,200]],
             enemies=[],actions=[[0,boulder('rock',left=24,hit_budget=0)]]),
        dict(name='boulder left boundary equality is still active',end=650,
             platforms=[[0,17.5,1000,100],[1,0,1000,200]],
             enemies=[],actions=[[0,boulder('rock',left=0,direction=-1,hit_budget=0)]]),
        dict(name='boulder lifetime disables same-time contact',end=450,
             enemies=[enemy(0,121,y=75)],actions=[[0,boulder('rock',duration_seconds=.1)]]),
        dict(name='boulder expiry during contact fade and critical boundary',end=450,rng=[1000,999],
             enemies=[enemy(0,121,y=75),enemy(1,122,y=75)],
             actions=[[0,boulder('rock',duration_seconds=.2,crit_percent=100)]]),
        dict(name='fireball causal launch landing first five',end=2500,
             enemies=[enemy(i,100,y=75,node=i%2) for i in range(6)],actions=[[0,fireball('ball')]]),
        dict(name='fireball delayed and left-facing',end=3100,rng=[999,1000],
             enemies=[enemy(0,100,y=75),enemy(1,101,y=75)],
             actions=[[0,fireball('ball',delay_seconds=.5,direction=-1,crit_percent=100)]]),
        dict(name='fireball trajectory follows aim to the left',end=2500,
             enemies=[enemy(0,0,y=75),enemy(1,1,y=75,node=1)],
             actions=[[0,fireball('ball',left=100,aim_x=0,direction=-1)]]),
        dict(name='fireball strict horizontal radius and eligibility',end=2500,
             enemies=[enemy(0,57,y=92),enemy(1,56.99,y=92,node=1),enemy(2,17,y=92,alive=False),
                      enemy(3,17,y=92,pet_status=1),enemy(4,17,y=92,worship=False)],
             actions=[[0,fireball('ball',aim_x=17,radius_percent=96.04339)]]),
        dict(name='fireball zero radius and long delay frame resets',end=8500,
             enemies=[enemy(0,17,y=92)],actions=[[0,fireball('ball',aim_x=17,radius_percent=0,delay_seconds=6)]]),
        dict(name='boulder and fireball share pool in both directions',end=4600,
             enemies=[enemy(0,121,y=75)],actions=[[0,boulder('rock')],
             [500,fireball('ball',left=.75,top=49.75)],[3000,boulder('rock2',left=100.75)],
             [3500,fireball('ball2',delay_seconds=.5)]]),
        dict(name='kraken contact uses real width steering',end=800,
             enemies=[enemy(0,100,y=75)],actions=[[0,kraken('kraken')]]),
        dict(name='kraken zero-width controlled geometry changes steering',end=800,
             enemies=[enemy(0,100,y=75,width=0)],actions=[[0,kraken('kraken')]]),
        dict(name='kraken corpse contact damages previous live target',end=800,
             enemies=[enemy(0,100,0,y=75,alive=False),enemy(1,100,y=75)],
             actions=[[0,kraken('kraken')]]),
        dict(name='kraken inactive releases owner before recycling',end=600,enemies=[],
             actions=[[0,kraken('kraken')],[0,dict(kind='battle',active=False)]]),
        dict(name='kraken contacts exhaust and remove both shared owners',end=600,
             enemies=[enemy(0,100,1000,y=75)],
             actions=[[0,kraken('first',contacts=1)],[0,kraken('second',contacts=1)]]),
        dict(name='kraken size four push and odd monster width',end=900,
             enemies=[enemy(0,100,y=75,size=4,width=65)],
             actions=[[0,kraken('kraken',push_direction=1,contacts=1)]]),
        dict(name='kraken retained dead target gets damaged again',end=900,
             enemies=[enemy(0,100,5,y=75)],
             actions=[[0,kraken('kraken',push_direction=1)],
                      [200,dict(kind='enemy',target=0,changes=dict(alive=False))]]),
        dict(name='kraken generic recycle leaves shared owner entry',end=1400,
             enemies=[enemy(0,100,y=75)],actions=[[0,kraken('kraken')],
             [100,dict(kind='recycle',label='kraken')],[200,storm('reused',damage=0)]]),
        dict(name='kraken rounded left right boundary',end=800,platforms=[[0,0,90,100]],
             enemies=[],actions=[[0,kraken('kraken')]]),
        dict(name='kraken rounded left left boundary',end=800,rng=[1],
             enemies=[],actions=[[0,kraken('kraken',left=0)]]),
        dict(name='kraken two-second reset abandons dead remembered target',end=2500,
             enemies=[enemy(0,300,y=75),enemy(1,50,y=75)],
             actions=[[0,kraken('kraken')],
                      [210,dict(kind='enemy',target=0,changes=dict(hp=-5,alive=False))]]),
        dict(name='kraken wander first draw changes direction',end=3200,rng=[2,1,1],
             enemies=[],actions=[[0,kraken('kraken')]]),
        dict(name='kraken wander second independent draw stops',end=3200,rng=[2,2,1],
             enemies=[],actions=[[0,kraken('kraken')]]),
        dict(name='kraken wander neither draw changes direction',end=5200,rng=[2,2,2],
             enemies=[],actions=[[0,kraken('kraken')]]),
        dict(name='kraken origin right bound has graphic-only owned timer',end=3500,
             enemies=[],actions=[[0,kraken('kraken',left=300)]]),
        dict(name='kraken origin left bound has graphic-only owned timer',end=3500,
             enemies=[],actions=[[0,kraken('kraken',origin_x=400)]]),
        dict(name='kraken contacts critical strict equality and minimum damage',end=600,rng=[2,10],
             enemies=[enemy(0,100,y=75)],actions=[[0,kraken('kraken',contacts=1,damage=0)]]),
        dict(name='kraken contacts critical just below equality',end=600,rng=[2,9],
             enemies=[enemy(0,100,y=75)],actions=[[0,kraken('kraken',contacts=1)]]),
    ]


SCRIPT = r'''
const vm=require('node:vm'),p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
try{
 const results=[];
 for(const input of p.cases){
  let now=0,nextID=0,randomIndex=0;const events=[],history=[],active=new Map(),refs={},allEnemies=[],underlings=[];
  const gen=Array(91).fill(0);gen[84]=1;
  const attrs={WeaponType:6,CurrentMap:26,DummyList:[],MonsterHP:[0],MonsterAlive:[0],
   MapMonstersList:[],CustomLists:{h:{NonDMGLinemonsterTypes:[]}},
   MonsterDefinitionsGET:{h:{synthetic:{h:{Type:'Monster',DeathFrame:1,SpecialType:'',Defence:0}}}},
   PixelHelperActor:Array(8).fill({behaviors:{getBehavior:()=>({_GenINFO:gen})}}),
   DNSM:{h:{}},QuestComplete:{h:{Royal_Worm5:1}},Tasks:[[0,[1e300]]],NodeX:[0,0],NodeLength:[1000,1000],
   DummyNumbersStatManager:{h:{}},OriginPixelActor:[{getZIndex:()=>0}],NodeY:[100,200]};
  if(input.platforms)for(const [node,left,right,y] of input.platforms){
   attrs.NodeX[node]=left;attrs.NodeLength[node]=right;attrs.NodeY[node]=y;
  }
  const type={ID:478,__id__:478,groupID:0};
  const engine={tasks:[],recycledActorsOfType:{h:{}},whenTypeGroupCreatedEvents:{h:{}},whenTypeGroupKilledEvents:{h:{}},
   addTask(task){this.tasks.push(task)},isPaused:()=>false,getLayerById:()=>0,getLayerByName:()=>0,
   moveActorToLayer(){},removeActorFromLayer(){},gameAttributes:{h:attrs},
   getGameAttribute(key){if(!(key in attrs))throw Error('Missing attribute '+key);return attrs[key]},
   allActors:{set(id,actor){active.set(id,actor);events.push([now,'add',id])},
    unset(id){active.delete(id);events.push([now,'remove',id])}}};
  function map(){this.h={}}
  const ctx={a:{engine,STEP_SIZE:10,NO_PHYSICS:false,SCALE:1,physicsScale:10,toPhysicalUnits:x=>x/10,toPixelUnits:x=>x*10},
   c:{engine},A:{},l:map,n:{__cast:x=>x},ka:{},B:{},ch:{},va:{antialias:false},
   V:function(x,y){this.x=x;this.y=y},oa:function(){this.nameMap={h:{}}},
   E:(base,props)=>Object.assign(Object.create(base),props),w:(self,fn)=>fn.bind(self),
   ib:{getTimer:()=>now},Wc:{get:()=>({resources:{get:()=>type}})},
   ba:{remove:(xs,x)=>{const i=xs.indexOf(x);if(i>=0)xs.splice(i,1)}},
   h:{string:String},y:{replace:(s,a,b)=>s.split(a).join(b)},D:{contains:(xs,x)=>xs.includes(x)},
   t:{linear:{apply:x=>x}},p:{_customBlock_Dungon:()=>-1},
   m:{_customBlock_Windwalker:()=>0},x:{_customBlock_DamageDealed:()=>0},k:{},q:{},v:{},u:{}};
  vm.createContext(ctx);
  vm.runInContext(p.object+p.float+p.float2+p.manager+p.properties+
   p.constructor+p.prototype+p.registration+p.instance+p.projectile_class+p.worship+p.status,ctx,{timeout:2000});
  const original=key=>vm.runInContext('('+p[key]+')',ctx,{timeout:2000}),methods={};
  ctx.D.contains=original('contains');
  ctx.t.quadOut={apply:original('quad_out')};
  for(const [name,body] of Object.entries(p.methods))methods[name]=vm.runInContext('('+body+')',ctx,{timeout:2000});
  engine.recycleActor=original('recycle');engine.createActorOfType=original('create');
  engine.getRecycledActorOfTypeOnLayer=original('acquire');
  const phase=vm.runInContext('(function(){var n,t;'+p.phase+'})',ctx,{timeout:2000});
  const Manager=ctx[p.manager_owner],Properties=ctx[p.properties_owner];Manager.resetStatics();
  const profile={
   '0':{width:35,height:33,origin:[17,33],frames:Array(7).fill(100),looping:true},
   '1':{width:30,height:28,origin:[15,28],frames:[...Array(6).fill(80),10000,...Array(8).fill(80)],looping:false},
   '2':{width:72,height:80,origin:[36,80],frames:[80,80,80,...Array(7).fill(100)],looping:false},
   '3':{width:72,height:23,origin:[36,23],frames:Array(12).fill(80),looping:true},
   '4':{width:50,height:34,origin:[25,34],frames:Array(4).fill(100),looping:true},
   '5':{width:34,height:50,origin:[17,50],frames:Array(7).fill(100),looping:true},
   '7':{width:72,height:23,origin:[36,23],frames:Array(12).fill(100),looping:true},
   '6':{width:66,height:18,origin:[33,18],frames:Array(6).fill(100),looping:true}};
  function animation(data){const anim={model:{sync:false,looping:data.looping,frames:Array(data.frames.length).fill(0)},
   frameIndex:0,timer:0,finished:false,numFrames:data.frames.length,durations:data.frames,filter:null,
   set_bitmapData(){},set_filter(){},set_visible(){},get_width:()=>data.width,get_height:()=>data.height};
   anim.update=original('anim_update');anim.setFrame=original('anim_set');anim.getCurrentFrame=()=>anim.frameIndex;return anim;}
  engine.createActor=function(instance){
   const actor={...methods,engine,ID:nextID++,type,body:null,bodyDef:null,defaultGravity:true,
    physicsMode:1,defaultAnim:'0',currAnimation:null,currAnimationName:null,cacheWidth:0,cacheHeight:0,
    currOffset:{x:0,y:0},currOrigin:{x:0,y:0},realX:0,realY:0,realAngle:0,
    realScaleX:1,realScaleY:1,lastScale:{x:1,y:1},xSpeed:0,ySpeed:0,rSpeed:0,
    fixedRotation:false,paused:false,isHUD:false,ignoreGravity:true,continuousCollision:false,
    snapOnSet:false,collidable:false,shapeMap:{h:{}},bitmapFilters:null,drawActor:true,
    dead:false,recycled:false,customizedBehaviors:false,fading:false,
    animationMap:{h:Object.fromEntries(Object.entries(profile).map(([name,data])=>[name,animation(data)]))},
    originMap:{h:Object.fromEntries(Object.entries(profile).map(([name,data])=>[name,{x:data.origin[0],y:data.origin[1]}]))},
    addChild(){},removeChild(){},updateChildrenPositions(){},clearCollisionInfoList(){},
    getType:()=>type,getGroup:()=>({__id__:0}),whenKilled:{length:0},
    clearFilters(){},resetBlendMode(){},set_alpha(){},disableActorDrawing(){this.drawActor=false},
    enableActorDrawing(){this.drawActor=true},removeAttachedImages(){},removeAllListeners(){},resetListeners(){},
    makeAlwaysSimulate(){this.alwaysSimulate=true},makeSometimesSimulate(){this.alwaysSimulate=false},
    moveToLayer(){},growTo(){},sendToBack(){},setZIndex(){},fadeTo(){this.fading=true},updateDrawingMatrix(){},
    isAlive(){return !this.dead&&!this.recycled},isPaused(){return this.paused}};
   actor.tweenProps=new Properties();actor.tweenProps.xy.doOnUpdate(()=>actor.updateTweenXY());
   actor.switchToDefaultAnimation();actor.setLocation(instance.x,instance.y);
   const script=new ctx[p.projectile_owner]();script.actor=actor;script.wrapper={enabled:true};
   actor.initScripts=()=>script.init();actor.enableAllBehaviors=()=>{script.wrapper.enabled=true;actor.fading=false};
   engine.recycledActorsOfType.h[478].push(actor);engine.allActors.set(actor.ID,actor);return actor;
  };
  Object.assign(ctx.c,{asNumber:x=>x==null?0:Number(x),getCurrentSceneName:()=>'fixture',
   randomInt(low,high){const values=input.rng??[high],value=values[randomIndex++%values.length];
    if(value<low||value>high)throw Error('Random value outside requested bounds');
    events.push([now,'random',low,high,value]);return value},
   recycleActor:actor=>engine.recycleActor(actor),attachImageToActor(){},createSaturationFilter:()=>({})});
  ctx.k._customBlock_addImgInst=()=>({get_height:()=>1});
  for(const [index,data] of input.enemies.entries()){
   const script={_MonsterID:index+1,_MonsterNODE:data.node,_IsWorshipMob:Number(data.worship),
    _PetStatus:data.pet_status??0,_MonsterType:'synthetic',_StatusList:(data.statuses??[]).map(row=>row[0]),
    _StatusActive:(data.statuses??[]).map(row=>row.slice()),_StatusImgInst:(data.statuses??[]).map(()=>({get_height:()=>1})),
    _WorshipMOD:data.color,_PersNum:data.hit_counter??0,_MoveSPEED:7,_SizeMulti:data.size??2};
   const actor={...methods,id:data.id,script,cacheWidth:data.width,cacheHeight:50,currOffset:{x:0,y:0},
    physicsMode:1,realX:data.x,realY:data.y??0,xSpeed:data.velocity,ySpeed:0,realAngle:0,snapOnSet:false,
    continuousCollision:false,collidable:false,clearCollisionInfoList(){},set_alpha(){},
    clearFilters(){},setFilter(){},alive:data.alive??true,
    behaviors:{getBehavior:()=>script}};
   actor.tweenProps=new Properties();actor.tweenProps.xy.doOnUpdate(()=>actor.updateTweenXY());
   const moveBy=actor.moveBy;actor.moveBy=function(dx,dy,duration,easing){
    events.push([now,'push',this.id,dx]);return moveBy.call(this,dx,dy,duration,easing)};
   attrs.MonsterHP.push(data.hp);attrs.MonsterAlive.push(Number(actor.alive));attrs.MapMonstersList.push(actor);allEnemies.push(actor);
  }
  const damage=original('damage');
  ctx.k._customBlock_DistanceEqn=original('distance');
  ctx.q._customBlock_Hitscanning=original('hitscan');
  ctx.k._customBlock_CreateDmgPixel=(hits,actor,args)=>{
   const before=attrs.MonsterHP[actor.script._MonsterID],critical=attrs.dummyCritDmgMulti;
   const result=damage(hits,actor,args),after=attrs.MonsterHP[actor.script._MonsterID];
   events.push([now,'hit',actor.id,before-after,after,critical]);return result;
  };
  function perform(action){
   const args=action.args;
   if(['poison','storm','freeze','void','stun','boulder','fireball','kraken'].includes(action.kind)){
    attrs.WeaponType={poison:6,storm:2,freeze:3,void:7,stun:4,boulder:0,fireball:1,kraken:5}[action.kind];
    attrs.DummyList=action.kind==='poison'?[args.damage,args.node,args.duration_seconds,args.tick_seconds,args.crit_percent]
     :action.kind==='storm'?[allEnemies.find(e=>e.id===args.target),args.damage,args.crit_percent]
     :action.kind==='stun'?[args.duration_seconds]
     :action.kind==='boulder'?[args.direction,args.damage,args.duration_seconds,args.node,args.hit_budget,args.crit_percent]
     :action.kind==='fireball'?[args.direction,args.node,args.aim_x,args.damage,args.radius_percent,args.delay_seconds,args.crit_percent]
     :action.kind==='kraken'?[args.damage,args.origin_x,args.contacts,args.node,args.push_direction,underlings,Math.max(1,args.damage)]
     :[args.damage,args.slow_percent??0,args.extra_seconds??0,args.crit_percent,args.radius];
    const actor=engine.getRecycledActorOfTypeOnLayer(type,args.left,args.top,0);refs[action.label]=actor;
    if(action.kind==='kraken')underlings.push(actor);
    events.push([now,'spawn',action.label,actor.ID]);
   }else if(action.kind==='schedule')ctx.c.runLater(action.delay,()=>perform(action.action));
   else if(action.kind==='enemy'){
    const actor=allEnemies.find(e=>e.id===action.target);
    for(const [key,value] of Object.entries(action.changes)){
     if(key==='hp')attrs.MonsterHP[actor.script._MonsterID]=value;
     else if(key==='alive'){actor.alive=value;attrs.MonsterAlive[actor.script._MonsterID]=Number(value)}
     else throw Error('Unknown enemy mutation '+key);
    }
   }else if(action.kind==='unlist')attrs.MapMonstersList=attrs.MapMonstersList.filter(e=>e.id!==action.target);
   else if(action.kind==='pause')refs[action.label].paused=action.value;
   else if(action.kind==='recycle')engine.recycleActor(refs[action.label]);
   else if(action.kind==='battle')gen[8]=action.active?0:-1;
   else throw Error('Unknown input action '+action.kind);
  }
  function snapshot(){history.push([now,engine.tasks.length,(engine.recycledActorsOfType.h[478]??[]).map(actor=>
   [actor.ID,actor.isAlive(),actor.paused,actor.fading,Number(actor.getAnimation()),
    actor.getXCenter(),actor.getYCenter(),actor.getX(false),actor.getY(false),actor.cacheWidth,actor.cacheHeight,
    actor.getCurrentFrame(),actor.currAnimation.timer,actor.currAnimation.finished,
    actor.getXVelocity(),actor.getYVelocity()]),
   allEnemies.map(e=>[e.id,attrs.MonsterHP[e.script._MonsterID],e.getXCenter(),e.script._PersNum,e.alive,
    e.getXVelocity(),e.script._MoveSPEED,e.script._WorshipMOD,e.script._StatusActive]),underlings.map(e=>e.ID)]);}
  for(const [at,action] of input.actions)if(at===0)perform(action);snapshot();
  for(now=10;now<=input.end;now+=10){
   Manager.update(10);phase.call(engine);
   for(const actor of active.values())actor.internalUpdate(10,true);
   for(const [at,action] of input.actions)if(at===now)perform(action);snapshot();
  }
  results.push({events,history});
 }
 process.stdout.write(JSON.stringify(results));
}catch(error){process.stderr.write(error.stack);process.exitCode=1;}
'''


@dataclass
class EffectEnemy(Combatant):
    statuses: list[TimedStatus] = field(default_factory=list)
    move_speed: float = 7
    move_speed_initial: float = 7
    moving: bool = True
    frozen: bool = False
    max_hp: float = 100

    @property
    def row_alive(self):
        return int(self.alive)


def modeled_case(case):
    loop = TimerLoop()
    all_enemies = [EffectEnemy(**{**data, 'statuses':[TimedStatus(*row) for row in data.get('statuses',[])]})
                   for data in case['enemies']]
    listed = list(all_enemies)
    active, refs, known = {}, {}, []
    underlings, enemy_tweens = [], {}
    battle_active = True
    events, history = [], []
    next_id = random_index = 0
    platforms = {0: Platform(0, 0, 1000, 100), 1: Platform(1, 0, 1000, 200)}
    if 'platforms' in case:
        platforms = {node:Platform(node,left,right,y) for node,left,right,y in case['platforms']}

    def allocate():
        nonlocal next_id
        ident = next_id
        next_id += 1
        return ident

    def add(actor):
        active[actor.id] = actor
        if not any(existing is actor for existing in known):
            known.append(actor)
        events.append([loop.now_ms, 'add', actor.id])

    def remove(actor):
        del active[actor.id]
        events.append([loop.now_ms, 'remove', actor.id])

    def random_int(low, high):
        nonlocal random_index
        values = case.get('rng', [high])
        value = values[random_index % len(values)]
        random_index += 1
        if not low <= value <= high:
            raise AssertionError('Random value outside requested bounds.')
        events.append([loop.now_ms,'random',low,high,value])
        return value

    def hit(enemy, damage, critical):
        platform = platforms[enemy.node]
        dealt = apply_hits(enemy, damage=damage, crit_multiplier=critical,
                           bounds=(platform.left, platform.right))
        events.append([loop.now_ms, 'hit', enemy.id, dealt, enemy.hp, critical])

    def freeze(enemy, slow, seconds):
        enemy.velocity = freeze_velocity(enemy.velocity, slow)
        enemy.move_speed = abs(enemy.velocity)
        add_status(enemy, 'StatusFreeze', 6 + seconds)

    def push(enemy, dx):
        events.append([loop.now_ms,'push',enemy.id,dx])
        motion=Motion(enemy.x-math.floor(enemy.width/2),enemy.y-25)
        motion.move_by(dx,0,600,easing='quad_out')
        enemy_tweens[enemy.id]=(motion,loop.now_ms+600)

    world = Projectiles(loop, enemies=lambda: listed, platforms=platforms,
                        random_int=random_int, allocate_id=allocate, on_add=add,
                        on_remove=remove, on_hit=hit,
                        can_hit=lambda enemy,x,y,radius: can_hit(enemy,x=x,y=y,radius=radius,
                            alive_flag=int(enemy.alive),map_id=26),
                        on_freeze=freeze,on_cleanse=void_cleanse,
                        on_push=push,is_active=lambda:battle_active)

    def perform(action):
        nonlocal battle_active
        kind = action['kind']
        if kind in ('poison', 'storm', 'freeze', 'void', 'stun', 'boulder', 'fireball', 'kraken'):
            args = dict(action['args'])
            if kind == 'storm':
                args['target'] = next(enemy for enemy in all_enemies if enemy.id == args['target'])
            elif kind == 'kraken':
                args['underlings']=underlings
            actor = getattr(world, kind)(**args)
            if kind == 'kraken':
                underlings.append(actor)
            refs[action['label']] = actor
            events.append([loop.now_ms, 'spawn', action['label'], actor.id])
        elif kind == 'schedule':
            loop.schedule(action['delay'], lambda task: perform(action['action']))
        elif kind == 'enemy':
            enemy = next(enemy for enemy in all_enemies if enemy.id == action['target'])
            for key, value in action['changes'].items():
                setattr(enemy, key, value)
        elif kind == 'unlist':
            listed[:] = [enemy for enemy in listed if enemy.id != action['target']]
        elif kind == 'pause':
            refs[action['label']].paused = action['value']
        elif kind == 'recycle':
            world.recycle(refs[action['label']])
        elif kind == 'battle':
            battle_active=action['active']
        else:
            raise AssertionError('Unknown projectile action: ' + kind)

    def snapshot():
        def state(actor):
            profile = actor.body.profile
            code = next(code for code,value in ((0,DEFAULT_PROFILE),(1,FIREBALL_PROFILE),(2,STORM_PROFILE),
                (3,FREEZE_PROFILE),(4,STUN_PROFILE),(5,KRAKEN_PROFILE),(6,POISON_PROFILE),(7,VOID_PROFILE)) if profile is value)
            return [actor.id, actor.alive, actor.paused, actor.fading, code,
                    actor.body.x, actor.body.y, actor.body.left, actor.body.top,
                    actor.body.width, actor.body.height, actor.animation.frame,
                    actor.animation.elapsed_ms, actor.animation.finished,actor.motion.vx,actor.motion.vy]
        history.append([loop.now_ms, loop.pending, [state(actor) for actor in known],
                        [[enemy.id, enemy.hp, enemy.x, enemy.hit_counter, enemy.alive,
                          enemy.velocity,enemy.move_speed,enemy.color,
                          [[row.name,row.seconds] for row in enemy.statuses]] for enemy in all_enemies],
                        [actor.id for actor in underlings]])

    for at, action in case['actions']:
        if at == 0:
            perform(action)
    snapshot()
    while loop.now_ms < case['end']:
        for enemy in all_enemies:
            if enemy.id in enemy_tweens:
                motion,end=enemy_tweens[enemy.id]
                if loop.now_ms<end:
                    motion.advance_tween(10)
                    enemy.x,enemy.y=motion.x+math.floor(enemy.width/2),motion.y+25
        for actor in active.values():
            actor.motion.advance_tween(10)
        loop.tick()
        for actor in active.values():
            if not actor.paused:
                actor.motion.advance_physics(10)
                actor.animation.update(10)
        for at, action in case['actions']:
            if at == loop.now_ms:
                perform(action)
        snapshot()
    return dict(events=events, history=history)


def check(path):
    source = load('client_source.py', 'loader').source_from_asar(path)
    payload = source_parts(source)
    cases = scenarios()
    payload['cases'] = cases
    run = subprocess.run(['node', '-e', SCRIPT], input=json.dumps(payload), text=True,
                         capture_output=True, check=True, timeout=20)
    originals = json.loads(run.stdout)
    states = 0
    for case, original in zip(cases, originals, strict=True):
        model = modeled_case(case)
        for index, (client_event, model_event) in enumerate(zip(original['events'], model['events'], strict=True)):
            if client_event != model_event:
                raise AssertionError(dict(case=case['name'], event=index, client=client_event, model=model_event))
        for client, modeled in zip(original['history'], model['history'], strict=True):
            if client[:2] != modeled[:2] or client[3:] != modeled[3:]:
                raise AssertionError(dict(case=case['name'], time=client[0],
                                          client=[*client[:2], *client[3:]], model=[*modeled[:2], *modeled[3:]]))
            for left, right in zip(client[2], modeled[2], strict=True):
                for field, (a, b) in enumerate(zip(left, right, strict=True)):
                    equal = math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9) if 5 <= field <= 8 else a == b
                    if not equal:
                        raise AssertionError(dict(case=case['name'], time=client[0], actor=left[0],
                                                  field=field, client=a, model=b))
            states += 1
    return len(cases), states


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar', type=Path, required=True)
    args = parser.parse_args()
    try:
        cases, states = check(args.asar)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr[-2000:])
    print(f'{cases} persistent projectile scenarios and {states} timer/actor states match original methods. Complete battles remain unverified.')
