"""Compare normal POINTS popup clocks with unchanged original Actor34 methods.

Actor29's queue statement runs with controlled locals, outside its unrelated
inventory/mouse handler. Graphics are stubbed; original timer registration,
task updates, engine timer traversal and actor recycling remain executable.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from worship_sim.popups import PointPopups
from worship_sim.simulation import ActorClock, TimerLoop


def load_sibling(filename):
    spec=importlib.util.spec_from_file_location(filename,Path(__file__).with_name(filename))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def queue_statement(source):
    handler=source.find('_event_LASTUPDATEitembox:function(')
    marker='if(1==this._PixelQueueSEND&&0!=a.engine.getGameAttribute("ItemGetPixelQueue").length)'
    start=source.find(marker,handler)
    if handler<0 or start<0:
        raise ValueError('Original Actor29 popup queue statement is unavailable')
    opening=source.find('{',start)
    depth=0
    quote=None
    escaped=False
    for index in range(opening,len(source)):
        char=source[index]
        if quote:
            if escaped:
                escaped=False
            elif char=='\\':
                escaped=True
            elif char==quote:
                quote=None
        elif char in ('"',"'"):
            quote=char
        elif char=='{':
            depth+=1
        elif char=='}':
            depth-=1
            if depth==0:
                return source[start:index+1]
    raise ValueError('Original Actor29 popup queue statement is unterminated')


def source_parts(source):
    marker='A["scripts.ActorEvents_34"]='
    registry=source.find(marker)
    if registry<0:
        raise ValueError('Original Actor34 registry is unavailable')
    owner=re.match(r'[A-Za-z_$][\w$]*',source[registry+len(marker):])[0]
    start=source.rfind('var '+owner+'=function',0,registry)
    prototype=source.find(owner+'.prototype=',registry)
    suffix=',__class__:'+owner+'});'
    end=source.find(suffix,prototype)
    if min(start,prototype,end)<0:
        raise ValueError('Original Actor34 boundaries changed')
    actor=source[start:registry]+source[prototype:end+len(suffix)]
    for method in ('init:function(', '_event_Updating:function(', '_event_ItemGet:function('):
        if method not in actor:
            raise ValueError('Original Actor34 method is unavailable: '+method)
    timer=load_sibling('check-worship-simulation.py').source_parts(source)
    return dict(actor=actor,owner=owner,queue=queue_statement(source),timer=timer)


def scenarios():
    recipes={
        'merge-and-repeat-draw':[
            ['create',10],['create',20],['create',30],['prepare'],['draw',0],
            ['draw',0],['update'],['run',990],['run',1000],['run',2590],
            ['run',2600],['draw',0],['run',3090],['run',3100]],
        'delayed-first-draw':[
            ['create',10],['prepare'],['run',200],['draw',0],['draw',0],
            ['run',1000],['run',2790],['run',2800],['run',3290],['run',3300]],
        'gate-and-later-points':[
            ['create',10],['prepare'],['draw',0],['create',20],['prepare'],
            ['run',990],['prepare'],['run',1000],['prepare'],['draw',1],
            ['create',30],['create',40],['run',2000],['update'],['prepare'],
            ['update'],['draw',2],['run',5100]],
        'helper-before-duplicate-updates':[
            ['create',10],['create',20],['create',30],['prepare'],
            ['run',1000],['prepare'],['update'],['draw',0],['draw',1],
            ['run',2000],['prepare'],['update'],['draw',2],['run',5200]],
        'duplicate-updates-before-helper':[
            ['create',10],['create',20],['create',30],['prepare'],
            ['run',1000],['update'],['prepare'],['draw',0],['draw',1],
            ['run',2000],['prepare'],['update'],['draw',2],['run',5200]],
        'recycle-traversal':[
            ['create',10],['prepare'],['timer',10000,'lingering-owned',0],
            ['draw',0],['timer',3100,'following-unowned',None],
            ['run',3090],['run',3100],['run',3110],['run',10010]],
        'zero-and-fractional-amounts':[
            ['create',0],['create',1.5],['create',-2],['prepare'],
            ['update'],['draw',0],['run',3100]],
    }
    return [dict(name=f'{name}-language{language}-hidden{hidden}',
                 language=language,hidden=hidden,operations=operations)
            for name,operations in recipes.items()
            for language in (0,2) for hidden in (False,True)]


def modeled(scenario):
    loop=TimerLoop()
    owner=ActorClock()
    actors=[]
    events=[]
    popups=[]

    def identity(actor):
        return next(index for index,value in enumerate(actors) if value is actor)

    def allocate():
        actor=ActorClock()
        actors.append(actor)
        events.append(['create',loop.now_ms,identity(actor)])
        return actor

    def recycle(actor):
        events.append(['recycle',loop.now_ms,identity(actor)])
        loop.recycle(actor)

    manager=PointPopups(loop,owner,allocate=allocate,recycle=recycle,
                        language=scenario['language'],hidden=scenario['hidden'])
    result=[]
    for command,*args in scenario['operations']:
        if command=='create':
            popups.append(manager.create(args[0]))
        elif command=='prepare':
            manager.prepare()
        elif command=='update':
            for popup in popups:
                manager.update(popup)
        elif command=='draw':
            manager.draw(popups[args[0]])
        elif command=='run':
            loop.run_until(args[0])
        elif command=='timer':
            delay,label,index=args
            loop.schedule(delay,lambda task,label=label:events.append(['timer',loop.now_ms,label]),
                          actor=None if index is None else popups[index].clock)
        else:
            raise ValueError('Unknown scenario operation '+command)
        result.append(dict(now=loop.now_ms,pending=loop.pending,
            popups=[[popup.clock.alive,None if scenario['hidden'] else popup.amount,
                     popup.deployment] for popup in popups],
            events=[event[:] for event in events]))
    return result


SCRIPT=r'''
const fs=require('node:fs'),vm=require('node:vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
function execute(scenario){
 let now=0;const events=[],popups=[];
 const attrs={OptionsListAccount:Array(540).fill(0),DummyText:'meh',dummyDisplayEXPTYPE:'Null',
  dummyDisplayPopup:'POINTS',dummyDamageDealt:0,ItemGetPixelQueue:[],
  CustomMaps:{h:{SpecLetters:{h:{}}}},MenuType2:0,PixelHelperActor:[]};
 attrs.OptionsListAccount[539]=scenario.hidden?1:0;
 const engine={tasks:[],gameAttributes:{h:attrs},getGameAttribute:key=>attrs[key],
  isPaused:()=>false,addTask(task){this.tasks.push(task)},whenTypeGroupKilledEvents:{h:{}},
  removeActorFromLayer(){},allActors:{unset(){}}};
 const remove=(xs,x)=>{const index=xs.indexOf(x);if(index>=0)xs.splice(index,1)};
 const ctx={a:{engine,STEP_SIZE:10},c:{engine},A:{},ba:{remove},
  oa:function(){this.nameMap={h:{}};this.wrapper={enabled:true}},
  E:(base,fields)=>Object.assign({},base,fields),w:(self,fn)=>fn.bind(self),
  n:{__cast:value=>value},h:{string:String},y:{replace:(s,a,b)=>s.split(a).join(b)},
  u:{getPartyMembers:()=>[]},m:{_customBlock_Language:()=>scenario.language,
   _customBlock_LANGUAGEfont:()=>0},t:{linear:0},k:{
   _customBlock_addImgInst:()=>({set_alpha(){}}),_customBlock_NotateNumber:String}};
 Object.assign(ctx.c,{attachImageToActor(){},fadeImageTo(){},removeImage(){}});
 vm.createContext(ctx);
 const parts=input.parts;
 vm.runInContext(parts.timer.constructor+parts.timer.prototype+parts.timer.registration+parts.actor,ctx,{timeout:3000});
 const actualRecycle=vm.runInContext('('+parts.timer.recycle+')',ctx);
 const phase=vm.runInContext('(function(){var n,t;'+parts.timer.phase+'})',ctx);
 function recyclable(id){
  const actor={id,recycled:false,physicsMode:1,whenKilled:{length:0},
   isAlive(){return !this.recycled},isPaused:()=>false,
   getType:()=>({__id__:0}),getGroup:()=>({__id__:0}),getZIndex:()=>10};
  for(const method of ['setXY','cancelTweens','clearFilters','resetBlendMode','set_alpha',
   'switchToDefaultAnimation','disableActorDrawing','removeAttachedImages','removeAllListeners',
   'resetListeners','makeAlwaysSimulate','anchorToScreen','setZIndex','setYVelocity'])actor[method]=()=>{};
  return actor;
 }
 const helper={actor:recyclable(-1),_PixelQueueSEND:1};attrs.PixelHelperActor[0]=helper.actor;
 ctx.c.recycleActor=actor=>{events.push(['recycle',now,actor.id]);actualRecycle.call(engine,actor)};
 const prepare=vm.runInContext('(function(){var t=this,e,i,s,u;'+parts.queue+'})',ctx);
 const graphics={setFont(){},drawString(){}};
 const result=[];
 for(const[command,...args]of scenario.operations){
  if(command==='create'){
   const actor=recyclable(popups.length),popup=new ctx[parts.owner](null,null,null);
   popup.actor=actor;popup.addListener=()=>{};
   actor.behaviors={getBehavior:key=>{if(key!=='ActorEvents_34')throw Error(key);return popup}};
   events.push(['create',now,actor.id]);attrs.dummyDisplayPopup='POINTS';
   attrs.dummyDisplayEXPTYPE='Null';attrs.dummyDamageDealt=args[0];attrs.DummyText='meh';
   popup.init();popups.push(popup);
  }else if(command==='prepare')prepare.call(helper);
  else if(command==='update'){
   for(const popup of popups)if(popup.actor.isAlive())popup._event_Updating(10);
  }else if(command==='draw'){
   const popup=popups[args[0]];if(popup.actor.isAlive())popup._event_ItemGet(graphics,0,0);
  }else if(command==='run'){
   while(now<args[0]){now+=10;phase.call(engine)}
  }else if(command==='timer'){
   const[delay,label,index]=args;ctx.c.runLater(delay,()=>events.push(['timer',now,label]),
    index===null?null:popups[index].actor);
  }else throw Error('Unknown scenario operation '+command);
  result.push({now,pending:engine.tasks.length,
   popups:popups.map(p=>[p.actor.isAlive(),scenario.hidden?null:p._NumberDisplayed,p._Deployment]),
   events:events.map(event=>event.slice())});
 }
 return result;
}
process.stdout.write(JSON.stringify(input.scenarios.map(execute)));
'''


def check(path):
    source=load_sibling('client_source.py').source_from_asar(path)
    cases=scenarios()
    payload=dict(parts=source_parts(source),scenarios=cases)
    run=subprocess.run(['node','-e',SCRIPT],input=json.dumps(payload),text=True,
                       capture_output=True,check=True,timeout=30)
    original=json.loads(run.stdout)
    if len(original)!=len(cases):
        raise AssertionError('Original scenario count differs')
    count=0
    for scenario,expected in zip(cases,original):
        actual=modeled(scenario)
        if len(actual)!=len(expected):
            raise AssertionError(scenario['name']+': observation count differs')
        for index,(got,want) in enumerate(zip(actual,expected)):
            if got!=want:
                operation=scenario['operations'][index]
                raise AssertionError(f"{scenario['name']} operation {index} {operation}: "
                                     f'overlay {got}, original {want}')
            count+=1
    return len(cases),count


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar',type=Path,required=True)
    args=parser.parse_args()
    try:
        cases,observations=check(args.asar)
        print(f'{cases} original-client popup scenarios and {observations} observations matched.')
    except (AssertionError,ValueError,OSError,subprocess.SubprocessError) as error:
        if isinstance(error,subprocess.CalledProcessError):
            print(error.stderr[-1500:],file=sys.stderr)
        raise SystemExit(str(error))
