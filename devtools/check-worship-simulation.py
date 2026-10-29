"""Compare selected simulator mechanics with the installed original client.

Checks timers, poison pulses and freeze effects. Complete battles and layout
quality remain unverified.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from worship_sim.simulation import TimerLoop,ActorClock,Combatant,PoisonPuddle,apply_freeze,AnimationClock


def source_parts(source):
    registry='A["com.stencyl.behavior.TimedTask"]='
    reg=source.find(registry)
    if reg<0:raise ValueError('Original TimedTask registry is unavailable.')
    owner=re.match(r'[A-Za-z_$][\w$]*',source[reg+len(registry):])[0]
    start=source.rfind('var '+owner+'=function',0,reg)
    prototype=source.find(owner+'.prototype=',reg)
    end=source.find(';var ',prototype)
    if min(start,prototype,end)<0:raise ValueError('Original TimedTask boundaries changed.')
    constructor=source[start:reg]
    prototype=source[prototype:end]+';'
    start=source.find('for(n=0;n<this.tasks.length;)')
    end=source.find('if(0<this.whenKeyPressedEvents',start)
    if start<0 or end<start:raise ValueError('Original engine timer phase changed.')
    phase=source[start:end]
    start=source.find('c.runLater=function(')
    end=source.find(',c.getStepSize=',start)
    if start<0 or end<start:raise ValueError('Original timer registration changed.')
    registration=source[start:end]+';'
    start=source.find('recycleActor:function(')+len('recycleActor:')
    end=source.find('},getRecycledActorOfType:',start)
    if start<len('recycleActor:') or end<start:raise ValueError('Original actor recycling changed.')
    recycle=source[start:end+1]
    registry=source.find('A["com.stencyl.graphics.BitmapAnimation"]=')
    start=source.find('update:function(',registry)+len('update:')
    end=source.find('},getCurrentFrame:',start)
    if registry<0 or end<start:raise ValueError('Original animation update changed.')
    animation_update=source[start:end+1]
    start=source.find('setFrame:function(',end)+len('setFrame:')
    end=source.find('},isFinished:',start)
    if end<start:raise ValueError('Original animation reset changed.')
    return dict(constructor=constructor,prototype=prototype,phase=phase,registration=registration,
                recycle=recycle,animation_update=animation_update,animation_set_frame=source[start:end+1])


def modeled_cases():
    results=[]
    loop=TimerLoop();fired=[]
    loop.schedule(2000/1.3,lambda task:fired.append(loop.now_ms),repeat=True)
    loop.run_until(4620);results.append(fired)
    loop=TimerLoop();fired=[]
    loop.schedule(10,lambda task:loop.schedule(10,lambda task:fired.append(loop.now_ms)))
    loop.run_until(10);results.append(fired)
    loop=TimerLoop();fired=[];actor=ActorClock(paused=True)
    loop.schedule(20,lambda task:fired.append(loop.now_ms),repeat=True,actor=actor)
    loop.run_until(30);actor.paused=False;loop.run_until(50);actor.alive=False;loop.run_until(100)
    results.append([fired,loop.pending])
    loop=TimerLoop(step_ms=100);fired=[]
    loop.schedule(10,lambda task:fired.append(loop.now_ms),repeat=True)
    loop.run_until(100);results.append(fired)
    loop=TimerLoop();loop.paused=True;fired=[]
    loop.schedule(10,lambda task:fired.append('unowned'))
    loop.schedule(10,lambda task:fired.append('actor'),actor=ActorClock())
    loop.run_until(10);loop.paused=False;loop.run_until(20);results.append(fired)
    loop=TimerLoop();hits=[]
    enemies=[Combatant(0,0,154,100),Combatant(1,0,155,100),Combatant(2,1,100,100),Combatant(3,0,100,0),Combatant(4,0,100,100,worship=False)]
    puddle=PoisonPuddle(loop,node=0,x=100,damage=10,duration_seconds=1,tick_seconds=.5,
        crit_percent=0,enemies=enemies,random_int=lambda a,b:b,
        on_hit=lambda e,d:hits.append([loop.now_ms,e.id,d]))
    loop.run_until(2000);results.append([hits,puddle.clock.alive,puddle.fading])
    loop=TimerLoop();hits=[]
    PoisonPuddle(loop,node=0,x=100,damage=.49999999999999994,duration_seconds=1,tick_seconds=.5,
        crit_percent=0,enemies=[Combatant(0,0,100,100)],random_int=lambda a,b:b,
        on_hit=lambda e,d:hits.append([loop.now_ms,e.id,d]))
    loop.run_until(500);results.append(hits)
    mob=Combatant(0,0,100,100,velocity=7);freeze=[]
    apply_freeze(mob,0,0);freeze.append([mob.velocity,mob.freeze_seconds])
    apply_freeze(mob,0,2);freeze.append([mob.velocity,mob.freeze_seconds])
    mob.velocity=-7;apply_freeze(mob,15,0);freeze.append([mob.velocity,mob.freeze_seconds])
    results.append(freeze)
    freeze=[]
    for initial in (19,-19):
        mob=Combatant(0,0,100,100,velocity=initial)
        apply_freeze(mob,90,0);freeze.append(mob.velocity)
    results.append(freeze)
    for earlier,repeat in ((False,False),(True,False),(False,True)):
        loop=TimerLoop();actor=ActorClock();events=[]
        if earlier:loop.schedule(100,lambda task:None,actor=actor)
        loop.schedule(10,lambda task:(events.append('recycle'),loop.recycle(actor)),actor=actor,repeat=repeat)
        loop.schedule(10,lambda task:events.append('other'))
        loop.run_until(10);events.append('boundary');loop.run_until(20)
        results.append(events)
    animation=AnimationClock((100,100,100),looping=True);frames=[]
    for step in (100,250,0,0):
        animation.update(step);frames.append([animation.frame,animation.elapsed_ms,animation.finished])
    results.append(frames)
    animation=AnimationClock((100,100),looping=False);frames=[]
    animation.update(201);animation.update(1);frames.append([animation.frame,animation.elapsed_ms,animation.finished])
    for frame in (1,99):
        animation.set_frame(frame);frames.append([animation.frame,animation.elapsed_ms,animation.finished])
    results.append(frames)
    return results


SCRIPT=r'''
const fs=require('node:fs'),vm=require('node:vm'),parts=JSON.parse(fs.readFileSync(0,'utf8'));
function create(step=10){
 const engine={tasks:[],paused:false,isPaused(){return this.paused},addTask(task){this.tasks.push(task)},
  whenTypeGroupKilledEvents:{h:{}},removeActorFromLayer(){},allActors:{unset(){}}};
 const ctx={a:{engine,STEP_SIZE:step},c:{engine},A:{},ba:{remove:(xs,x)=>{const i=xs.indexOf(x);if(i>=0)xs.splice(i,1)}}};
 vm.createContext(ctx);vm.runInContext(parts.constructor+parts.prototype+parts.registration,ctx,{timeout:2000});
 engine.recycleActor=vm.runInContext('('+parts.recycle+')',ctx,{timeout:2000});
 const phase=vm.runInContext('(function(){var n,t;'+parts.phase+'})',ctx,{timeout:2000});
 const loop={now:0,engine,ctx,schedule:(ms,fn,repeat=false,actor=null)=>(repeat?ctx.c.runPeriodically:ctx.c.runLater)(ms,fn,actor),runTo(end){while(this.now<end){this.now+=step;phase.call(engine)}}};return loop;
}
function recyclable(extra={}){
 const actor={alive:true,recycled:false,physicsMode:1,whenKilled:{length:0},
  isAlive(){return this.alive&&!this.recycled},isPaused:()=>false,getType:()=>({__id__:0}),getGroup:()=>({__id__:0})};
 for(const method of ['setXY','cancelTweens','clearFilters','resetBlendMode','set_alpha',
  'switchToDefaultAnimation','disableActorDrawing','removeAttachedImages','removeAllListeners','resetListeners'])actor[method]=()=>{};
 return Object.assign(actor,extra);
}
const results=[];let loop=create(),fired=[];
loop.schedule(2000/1.3,()=>fired.push(loop.now),true);loop.runTo(4620);results.push(fired);
loop=create();fired=[];loop.schedule(10,()=>loop.schedule(10,()=>fired.push(loop.now)));loop.runTo(10);results.push(fired);
loop=create();fired=[];const actor={alive:true,paused:true,isAlive(){return this.alive},isPaused(){return this.paused}};
loop.schedule(20,()=>fired.push(loop.now),true,actor);loop.runTo(30);actor.paused=false;loop.runTo(50);actor.alive=false;loop.runTo(100);results.push([fired,loop.engine.tasks.length]);
loop=create(100);fired=[];loop.schedule(10,()=>fired.push(loop.now),true);loop.runTo(100);results.push(fired);
loop=create();loop.engine.paused=true;fired=[];loop.schedule(10,()=>fired.push('unowned'));
loop.schedule(10,()=>fired.push('actor'),false,{isAlive:()=>true,isPaused:()=>false});loop.runTo(10);loop.engine.paused=false;loop.runTo(20);results.push(fired);
function projectileWorld(type,data){
 const loop=create(),ctx=loop.ctx,attrs={WeaponType:type,DummyList:data,MonsterHP:[],MapMonstersList:[]};
 loop.engine.getGameAttribute=k=>attrs[k];loop.engine.gameAttributes={h:attrs};
 Object.assign(ctx,{n:{__cast:x=>x},B:{},p:{_customBlock_WorshipStuff:()=>1.5},h:{string:String},t:{linear:0},w:(self,fn)=>fn.bind(self)});
 const hits=[];ctx.c.asNumber=x=>x==null?0:Number(x);ctx.c.randomInt=(a,b)=>b;
 ctx.c.recycleActor=actor=>loop.engine.recycleActor(actor);
 ctx.k={
  _customBlock_CreateDmgPixel:(_,mob)=>{hits.push([loop.now,mob.script._MonsterID,Math.round(Number(attrs.DummyText.slice('WorshipTowerDMG'.length))*attrs.dummyCritDmgMulti)])},
  _customBlock_AddStatusToMonster:(_,mob,seconds)=>{mob.seconds=seconds}};
 ctx.k._customBlock_DistanceEqn=vm.runInContext('('+parts.distance+')',ctx);
 ctx.q={_customBlock_Hitscanning:()=>1};
 const actor=recyclable({fading:false,
  getAnimation:()=>String(type),setAnimation(){},getXCenter:()=>100,getYCenter:()=>0,
  makeAlwaysSimulate(){},moveToLayer(){},growTo(){},fadeTo(){this.fading=true}});
 ctx.c.engine.getLayerByName=()=>0;
 const self={actor,_event_01(){}};
 function mob(x,node,hp,velocity=7,worship=1){
  const script={_IsWorshipMob:worship,_MonsterNODE:node,_MonsterID:attrs.MapMonstersList.length};
  const mob={x,velocity,script,seconds:0,getXCenter(){return this.x},getXVelocity(){return this.velocity},
   setXVelocity(v){this.velocity=v},behaviors:{getBehavior:()=>script}};
  attrs.MonsterHP.push(hp);attrs.MapMonstersList.push(mob);return mob;
 }
 return {loop,actor,hits,mob,cast(){vm.runInContext('('+parts.initialization+')',ctx,{timeout:2000}).call(self)}};
}
let world=projectileWorld(6,[10,0,1,.5,0]);world.mob(154,0,100);world.mob(155,0,100);world.mob(100,1,100);world.mob(100,0,0);world.mob(100,0,100,7,0);world.cast();world.loop.runTo(2000);results.push([world.hits,world.actor.isAlive(),world.actor.fading]);
world=projectileWorld(6,[.49999999999999994,0,1,.5,0]);world.mob(100,0,100);world.cast();world.loop.runTo(500);results.push(world.hits);
world=projectileWorld(3,[0,0,0,0,100]);let enemy=world.mob(100,0,100),freeze=[];world.cast();freeze.push([enemy.velocity,enemy.seconds]);
world.loop.engine.getGameAttribute('DummyList')[2]=2;world.cast();freeze.push([enemy.velocity,enemy.seconds]);
enemy.velocity=-7;world.loop.engine.getGameAttribute('DummyList')[1]=15;world.loop.engine.getGameAttribute('DummyList')[2]=0;world.cast();freeze.push([enemy.velocity,enemy.seconds]);results.push(freeze);
freeze=[];
for(const initial of [19,-19]){
 world=projectileWorld(3,[0,90,0,0,100]);enemy=world.mob(100,0,100,initial);
 world.cast();freeze.push(enemy.velocity);
}
results.push(freeze);

for(const [earlier,repeat] of [[false,false],[true,false],[false,true]]){
 loop=create();const actor=recyclable(),events=[];
 if(earlier)loop.schedule(100,()=>{},false,actor);
 loop.schedule(10,()=>{events.push('recycle');loop.engine.recycleActor(actor)},repeat,actor);
 loop.schedule(10,()=>events.push('other'));loop.runTo(10);events.push('boundary');loop.runTo(20);results.push(events);
}
function animation(durations,looping){
 const ctx={va:{antialias:false}},self={model:{sync:false,looping,frames:[]},
  numFrames:durations.length,durations,frameIndex:0,timer:0,finished:false,filter:null,set_bitmapData(){}};
 vm.createContext(ctx);self.update=vm.runInContext('('+parts.animation_update+')',ctx);
 self.setFrame=vm.runInContext('('+parts.animation_set_frame+')',ctx);return self;
}
let anim=animation([100,100,100],true),frames=[];
for(const step of [100,250,0,0]){anim.update(step);frames.push([anim.frameIndex,anim.timer,anim.finished])}results.push(frames);
anim=animation([100,100],false);frames=[];anim.update(201);anim.update(1);frames.push([anim.frameIndex,anim.timer,anim.finished]);
for(const frame of [1,99]){anim.setFrame(frame);frames.push([anim.frameIndex,anim.timer,anim.finished])}results.push(frames);
process.stdout.write(JSON.stringify(results));
'''


def check(path):
    spec=importlib.util.spec_from_file_location('client_check',Path(__file__).with_name('client_source.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source=module.source_from_asar(path)
    parts=source_parts(source)
    projectile_spec=importlib.util.spec_from_file_location('projectile_check',Path(__file__).with_name('check-worship-combat.py'))
    projectile=importlib.util.module_from_spec(projectile_spec);projectile_spec.loader.exec_module(projectile)
    parts['initialization']=projectile.projectile_init(source)
    target_spec=importlib.util.spec_from_file_location('target_check',Path(__file__).with_name('check-worship-targeting.py'))
    target=importlib.util.module_from_spec(target_spec);target_spec.loader.exec_module(target)
    parts['distance']=target.source_parts(source)['distance']
    run=subprocess.run(['node','-e',SCRIPT],input=json.dumps(parts),text=True,capture_output=True,check=True,timeout=15)
    actual=modeled_cases();expected=json.loads(run.stdout)
    if actual!=expected:raise AssertionError({'model':actual,'original':expected})
    return len(actual)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar',type=Path,required=True)
    args=parser.parse_args()
    print(f'{check(args.asar)} simulator mechanics scenarios match the original client. Complete battles remain unverified.')
