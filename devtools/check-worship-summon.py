"""Compare controlled complete summons with unchanged installed-client callbacks.

Native wave spawning, combat, corpses, POINTS, purchases and scoring run on one
clock. Account scalars, initial actor phases, assets and drawing cadence are
explicit inputs. Scene graphics, account XP delivery, unrelated GUI clocks and
post-defeat scene cleanup are outside the controlled profile.

Existing bases begin after their selection delay; purchases retain the original
500ms task. Placement ghosts, the totem marker and base z-order enumeration are
graphics services. The first HUD defeat ends execution after recording its two
pending cleanup tasks. Monster raw anchors are compared exactly alongside
combat state, actor identities, ordered timers, rewards and scoring.
"""
import argparse
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from worship_sim.models import Platform,Tower,Board
from worship_sim.battle import PopupProfile
from worship_sim.investments import Investment
from worship_sim.native import trial_profile
from worship_sim.summon import Summon
from worship_sim.waves import Wave


def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'devtools'/name)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def cases():
    def make(name,operations,*,towers=(Tower(0,0,100,100),),wave=0,points=10000,lives=20,
             platforms=(Platform(0,0,1000,100),),waves=(Wave(2,0,2,0),)*30,
             roast=0,roast_level=0,roast_floor=0,atom=200,construction=(1,)*9,salt=0,meal=0,merit=0):
        state=Board(True,map_id=26,wave=wave,points=points,hp=lives,towers=towers,
            platforms=platforms,route=tuple(p.node for p in platforms),roast=roast,
            roast_level=roast_level,roast_floor=roast_floor,construction=construction)
        return dict(name=name,state=asdict(state),waves=[list(asdict(w).values()) for w in waves],
            trial=0,atom_bonus=atom,salt=salt,meal=meal,merit=merit,refunds=[3]*len(towers),draw=20,
            helper_y=0,operations=operations)
    result=[make('native opening complete clear', [['run',6000],['run',7000],['run',7100],
                 ['run',10600],['run',15000],['run',25000],['run',35000]]),
            make('native overlap manual send', [['run',7100],['send'],['run',8000],['run',8100],
                 ['run',10600],['run',15000],['run',25000]])]
    result.append(make('native build before wave then upgrade choice sale',[
        ['run',1000],['apply',dict(kind='build',tower=asdict(Tower(0,0,100,300)))],
        ['run',1490],['run',1500],*([['apply',dict(kind='upgrade',index=0)]]*5),
        ['apply',dict(kind='choose',index=0,choice='A')],['run',7100],['run',15000],
        ['apply',dict(kind='sell',index=0)],['run',16000]],towers=(),platforms=(Platform(0,0,1000,300),)))
    result.append(make('source base wizard pool reused after sale',[
        ['run',1000],['apply',dict(kind='sell',index=0)],
        ['apply',dict(kind='build',tower=asdict(Tower(4,0,300,300)))],
        ['run',1500],['run',7100],['run',8000]],
        towers=(Tower(0,0,100,300),),platforms=(Platform(0,0,1000,300),)))
    result.append(make('native leaks stop on first HUD defeat',[
        ['run',7100],['run',10600],['run',11000],['run',14000],['run',16000]],
        towers=(),lives=2,platforms=(Platform(0,0,200,300),)))
    result.append(make('captured poison survives sale and roast wave reset',[
        ['run',7000],['run',8000],['run',9200],['run',9300],
        ['apply',dict(kind='sell',index=0)],['run',9500],['send'],
        ['run',10000],['run',10730],['run',11000],['run',15000]],wave=3,
        towers=(Tower(7,0,390,300,5,'B'),Tower(3,0,280,300)),
        platforms=(Platform(0,0,1200,300),),waves=(Wave(2,3,2,0),)*30,
        roast=100,roast_level=2,roast_floor=40))
    result.append(make('mixed nine kinds multiwave account scaling',[
        ['run',7100],['run',9500],['send'],['run',14590],['run',14600],
        ['run',15000],['run',25000],['run',40000],['run',60000]],
        towers=tuple(Tower(kind,0,100+61*kind,300,5,'A' if kind in (0,3,5,6) else 'B') for kind in range(9)),
        platforms=(Platform(0,0,1200,300),),waves=(Wave(3,3,4,0),)*30,
        roast_level=2,roast_floor=40))
    for color in range(1,6):
        result.append(make(f'native color {color} account rewards and construction',[
            ['run',7100],['run',9500],['send'],['run',15000],['run',25000],['run',35000]],
            towers=(Tower(0,0,80,300,5,'A'),Tower(4,0,141,300),Tower(7,0,202,300,5,'B')),
            platforms=(Platform(0,0,1000,300),),waves=(Wave(3,1,2,color),)*30,
            construction=(7,)*9,salt=25,meal=20,merit=30,atom=50,points=10000.5))
    return result


def source_parts(path):
    battle=load('check-worship-battle.py')
    parts=battle.source_parts(path)
    client=load('client_source.py')
    source=client.source_from_asar(path)
    def method(actor,name,following):
        registry=source.index('A["scripts.ActorEvents_'+str(actor)+'"]=')
        start=source.index(name+':function',registry)+len(name)+1
        return source[start:source.index('},'+following+':',start)+1]
    for key,actor,name,following in (
        ('second',340,'_event_1sec','_event_10sec'),('send',340,'_event_3','_event_4'),
        ('press',340,'_event_press','_event_3'),('hud',340,'_event_4','_event_5'),
        ('placement',131,'_event_Click','_event_Updating')):
        parts[key]=method(actor,name,following)
    for key in ('TDtraits','TowerInfo','_customBlock_TowerStats','_customBlock_Tower2Stats'):
        owner,code=client.function(source,key);parts[key]=dict(owner=owner,code=code)
    marker='A["scripts.ActorEvents_358"]='
    registry=source.index(marker)
    owner=re.match(r'[A-Za-z_$][\w$]*',source[registry+len(marker):])[0]
    start=source.rfind('var '+owner+'=function',0,registry)
    proto=source.index(owner+'.prototype=',registry)
    suffix=',__class__:'+owner+'});'
    end=source.index(suffix,proto)+len(suffix)
    parts['baseclass']=dict(owner=owner,code=source[start:registry]+source[proto:end])
    return parts


def script():
    """Adapt fixture wiring only; every extracted client callback stays unchanged."""
    text=load('check-worship-battle.py').SCRIPT
    def replace(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('The shared original-host hook changed: '+old[:70])
        text=text.replace(old,new)
    replace('const s=test.scenario,profile=test.enemy_profile,popupProfile=test.popup_profile,events=[],rolls=[];',
        'const s=test.scenario,profile=test.enemy_profile,popupProfile=test.popup_profile,events=[],rolls=[];let birthID=0,click=null;')
    replace('recycleActor(a){const wasAlive=a.isAlive();', 'recycleActor(a){if(a?.isFixtureGraphic)return;const wasAlive=a.isAlive();')
    replace('const helper={wrapper:{enabled:true},actor:helperActor,_GenINFO:gen};',
        'const helper={wrapper:{enabled:true},actor:helperActor,_GenINFO:gen,_customEvent_RefineryStuff(){}};')
    replace("helper._customEvent_WorshipStuff=fn('native_spawn_helper');engine.whenMouseReleased=eventList();",r'''
 helper._customEvent_WorshipStuff=fn('native_spawn_helper');engine.whenMouseReleased=eventList();engine.whenMousePressed=eventList();
 const state=test.state;
 let lastResult=null,ghostCreated=false,initializingBase=false;
 Object.assign(gen,{6:0,8:state.wave,10:[0,0],11:-1,13:6,14:{isFixtureGraphic:true},51:state.points,52:Array(10).fill('Mob'),
  53:0,55:state.wave,57:0,59:0,60:Array(9).fill(0),61:Array(9).fill(-1),62:30,64:-1,65:-1,74:0,
  85:state.roast,88:1,89:0});
 const ui={...image(),get_x:()=>0,get_y:()=>0,get_alpha:()=>1};
 helper._UIinventoryOn8=Array(100).fill(0);helper._UIinventory8=Array(100).fill(ui);
 for(const index of [7,41,42,43,46])helper._UIinventory8[index]=Array(30).fill(ui);
 helper._UIinventoryOn8[8]=1;helper._UIinventoryOn8[46]=Array(30).fill(0);
 Object.assign(attrs,{Refinery:[[-3]],TowerInfo:Array(30).fill(1),MenuType:0,
  TotemInfo:Array.from({length:3},()=>Array(8).fill(0)),Dream:Array(10).fill(0),
  QuestComplete:{h:{...attrs.QuestComplete.h,Hoggindaz4:1}},
  Number2Letter:Array(27).fill('').concat(['A','B'])});
 attrs.Dream[7]=state.roast_level;
 attrs.CustomLists.h.WorshipInfo=Array.from({length:8},()=>test.waves);
 for(const key of ['TDtraits','TowerInfo','_customBlock_TowerStats','_customBlock_Tower2Stats']){
  const part=p[key];ctx[part.owner]??={};vm.runInContext(part.code,ctx);
 }
 for(const key of ['TDtraits','TowerInfo'])attrs.CustomLists.h[key]=ctx[p[key].owner][key]();
 for(let kind=0;kind<9;kind++)attrs.TowerInfo[9+kind]=state.construction[kind];
 Object.assign(ctx.p,{_customBlock_ArcadeBonus:()=>0,_customBlock_Reg_ach_add_status(){},_customBlock_ActionBlock(){}});
 Object.assign(ctx.m,{_customBlock_AtomCollider:()=>test.atom_bonus,_customBlock_GetSetBonus:()=>0,_customBlock_Bubbastuff:()=>0});
 Object.assign(ctx.x,{_customBlock_skillstats2:key=>key==='WorshipEXPmulti'?1:0,_customBlock_ArbitraryCode:()=>1});
 Object.assign(ctx.v,{_customBlock_ProgressStarsign(){}});
 Object.assign(ctx.q,{_customBlock_MenagerieStuff:(key,id)=>key==='BoostQTY'&&id===15?state.roast_floor:0,
  _customBlock_CommaNotation:String,_customBlock_TotalFoodBonuses:()=>0,_customBlock_DropSomething(){},
  _customBlock_IsXYmouseWithinBounds:(x1,x2,y1,y2)=>Number(click!==null&&click[0]>=x1&&click[0]<=x2&&click[1]>=y1&&click[1]<=y2)});
 Object.assign(ctx.k,{_customBlock_DialogueETC:()=>'',_customBlock_TalentCalc:()=>0,_customBlock_AdjustImgInst(){}});
 Object.assign(ctx.c,{getScreenX:()=>0,getScreenY:()=>0,getMouseX:()=>click?.[0]??0,getMouseY:()=>click?.[1]??0,
  getFont:()=>({getTextWidth:()=>0}),setFilterForImage(){},clearFiltersForImage(){},moveImageBy(){},moveImageTo(){},
  createBrightnessFilter:()=>({})});
 const originalSpawn=ctx.k._customBlock_CreateMonster;
 ctx.k._customBlock_CreateMonster=function(...args){
  const birth={id:++birthID,wave:helper._DummyNumber};pendingBirth=birth;
  try{const value=originalSpawn(...args);events.push([now,'spawn',birth.id,birth.wave]);return value}
  finally{pendingBirth=null}
 };
 const second=fn('second'),release=fn('send'),hud=fn('hud');
 const graphics={alpha:1,font:{getTextWidth:()=>0},setFont(){},drawString(){},drawCircle(){}};
 add(helperActor.whenDrawing,()=>{const before=gen[8];hud.call(helper,graphics);
  if(before>=0&&gen[8]<0)events.push([now,'defeat',-1,attrs.TotemInfo[0][test.native]]);
 });
 vm.runInContext(p.baseclass.code,ctx);
 const press=fn('press'),place=fn('placement');
 const rawAttribute=engine.getGameAttribute;
 engine.getGameAttribute=key=>initializingBase&&key==='MapMonstersList'&&!attrs.MapMonstersList.length
   ?[{getZIndex:()=>0}]:rawAttribute(key);
''')
    old=""" ctx.c.runPeriodically(100,()=>{
  originalTenth.call(helper);
  for(const[index,birth]of test.births.entries())if(birth.at===now){
   pendingBirth=birth;helper._TRIGGEREDtext='f'+(index+1);helper._customEvent_WorshipStuff();pendingBirth=null;
  }
 },helperActor);
 ctx.c.runPeriodically(1000,()=>{},helperActor);ctx.c.runPeriodically(10000,()=>{},helperActor);"""
    replace(old,"ctx.c.runPeriodically(100,()=>originalTenth.call(helper),helperActor);\n ctx.c.runPeriodically(1000,()=>second.call(helper),helperActor);ctx.c.runPeriodically(10000,()=>{},helperActor);")
    replace('const popupType={ID:34,__id__:34},projectileType={ID:478,__id__:478,groupID:0},monsterType={ID:1,__id__:1,groupID:0};',
        'const popupType={ID:34,__id__:34},projectileType={ID:478,__id__:478,groupID:0},monsterType={ID:1,__id__:1,groupID:0},baseType={ID:358,__id__:358,groupID:0};engine.recycledActorsOfType.h[358]=[];')
    replace("if(id===478)return projectileType;if(id===1)return monsterType;", "if(id===478)return projectileType;if(id===1)return monsterType;if(id===358)return baseType;")
    replace(' const nativeProfiles={',r'''
 const baseProfiles={BoxTrap:[70,50,Array.from({length:51},(_,i)=>[6,13,21,29,36,50].includes(i)?10000:1000),true,35,25],
  Tower:[54,55,Array(19).fill(1000),false,27,55],
  Wizard:[51,73,Array.from({length:136},(_,i)=>[4,14,19,29,34,44,49,64,79,94,109].includes(i)?10000:100),true,25,73]};
 function baseInit(a){
  a.kind=attrs.DummyText3==='Tower'?'base':'wizard';
  if(!a.towerBehavior){const script=new ctx[p.baseclass.owner]();script.actor=a;script.addListener=add;
   script._event_01sec=function(){observeCast(this)};a.towerBehavior=script;a.behaviors={getBehavior:()=>script};}
  initializingBase=true;try{a.towerBehavior.init()}finally{initializingBase=false}
  if(a.kind==='base'&&!bases.includes(a))bases.push(a);
  if(a.kind==='wizard'&&!wizards.includes(a))wizards.push(a);
 }
 const nativeProfiles={''')
    replace("if(instance.actorID!==478)throw Error('Unexpected instance '+instance.actorID);",r'''
  if(instance.actorID===358){const a=actor('base');installBody(a,baseProfiles,'BoxTrap',instance.x,instance.y);
   a.getType=()=>baseType;a.initScripts=()=>baseInit(a);engine.recycledActorsOfType.h[358].push(a);return a;}
  if(instance.actorID!==478)throw Error('Unexpected instance '+instance.actorID);''')
    replace('if(type.ID===478||type.ID===1)return createProjectile.call(engine,type,x,y,node);',
        'if(type.ID===478||type.ID===1||type.ID===358)return createProjectile.call(engine,type,x,y,node);')
    replace("ctx.c.createRecycledActor=(type,x,y,node)=>{if(type!==34&&type!==478&&type!==1)throw Error('Unexpected actor type '+type);\n  lastCreated=engine.getRecycledActorOfTypeOnLayer(type===34?popupType:type===1?monsterType:projectileType,x,y,0)};",r'''
 ctx.c.createRecycledActor=(type,x,y,node)=>{if(type===131){ghostCreated=true;return}
  if(type!==34&&type!==478&&type!==1&&type!==358)throw Error('Unexpected actor type '+type);
  lastCreated=engine.getRecycledActorOfTypeOnLayer(type===34?popupType:type===1?monsterType:type===358?baseType:projectileType,x,y,0)};
 attrs.PixelHelperActor[7].shout=()=>helper._customEvent_WorshipStuff();
 function purchase(action){
  const before=JSON.stringify(gen[56].map(row=>[row[0],row[5],row[9],row[11]])),points=gen[51];
  if(action.kind==='build'){
   const tower=action.tower;ghostCreated=false;gen[64]=-1;gen[57]=0;click=[261+49*tower.kind+20,85];press.call(helper);click=null;
   if(ghostCreated){const controller={wrapper:{enabled:true},_PixelType:2,
    _PersonalList1:[1,0,0,tower.kind,Array(12).fill(0)],actor:{getX:()=>tower.x}};
    controller.actor.isFixtureGraphic=true;controller._PersonalList1[4][1]=tower.node;place.call(controller);}
  }else{
   const base=gen[56][action.index][6];gen[64]=action.index;gen[59]=action.kind==='sell'?1:0;
   const x=Math.min(action.kind==='choose'?738:768,Math.max(5,base.getXCenter()-(action.kind==='choose'?106:93))),
    y=Math.min(375,Math.max(5,base.getYCenter()-165));
   click=action.kind==='upgrade'?[x+150,y+65]:action.kind==='sell'?[x+30,y+50]:[x+190,y+(action.choice==='A'?20:60)];
   release.call(helper);click=null;
  }
  return points!==gen[51]||before!==JSON.stringify(gen[56].map(row=>[row[0],row[5],row[9],row[11]]));
 }
''')
    start=text.index(' for(let index=0;index<s.towers.length;index++){')
    end=text.index(' function collect(){',start)
    text=text[:start]+r'''
 for(let index=0;index<state.towers.length;index++){
  const tower=state.towers[index];attrs.DummyNumber4=index;attrs.DummyNumber5=tower.kind;
  attrs.DummyNumber3=s.platforms.find(p=>p.node===tower.node).direction===1?0:1;
  attrs.DummyText3='Tower';ctx.c.createRecycledActor(358,tower.x-29,tower.y-37,0);const base=lastCreated;
  const delay=engine.tasks.find(task=>task.actor===base&&!task.repeats&&task.interval===500);
  if(!delay)throw Error('Initial base delay registration changed');engine.tasks.splice(engine.tasks.indexOf(delay),1);
  base.towerBehavior._PersonalLIST[2]=0;
  attrs.DummyText3='Wizard';attrs.DummyList=[base];ctx.c.createRecycledActor(358,tower.x-31,tower.y-46,0);const wizard=lastCreated;
  gen[56].push([tower.kind,tower.node,tower.x,0,-1,tower.level,base,wizard,1,tower.choices,{h:{}},test.refunds[index]]);
 }
 helper._TRIGGEREDtext='z';if(gen[56].length)helper._customEvent_WorshipStuff();
'''+text[end:]
    replace('wizards:wizards.map(a=>', 'wizards:gen[56].map(row=>row[7]).map(a=>')
    replace('underlings:wizards.map(a=>', 'underlings:gen[56].map(row=>row[7]).map(a=>')
    replace('events:events.map(e=>e.slice()),rolls:rolls.map(r=>r.slice())}}',r'''events:events.map(e=>e.slice()),rolls:rolls.map(r=>r.slice()),
  clock:[gen[8],gen[13],gen[85],gen[53],gen[55],attrs.TotemInfo[0][test.native],gen[54].map(row=>row.slice())],
  rows:gen[56].map(row=>[row[0],row[1],row[2],row[5],row[9],row[11],row[8]]),result:lastResult,
  anchors:attrs.MapMonstersList.map(a=>[a.sourceID,a.realX,a.realY,a.currOffset.x,a.currOffset.y,
    a.cacheWidth,a.cacheHeight,a.getX(false),a.getY(false)])}}''')
    replace("else if(command==='run')while(now<args[0]){",r'''
  else if(command==='send'){const before=gen[51],enabled=gen[13]<999;click=[180,20];release.call(helper);click=null;lastResult=enabled?gen[51]-before:null;}
  else if(command==='apply')lastResult=purchase(args[0]);
  else if(command==='run')while(now<args[0]&&gen[8]>=0){''')
    replace('for(const [command,...args]of test.operations){', 'for(const [command,...args]of test.operations){lastResult=null;')
    replace('process.stdout.write(JSON.stringify(data.cases.map(execute)));',r'''
try{process.stdout.write(JSON.stringify(data.cases.map(execute)))}catch(error){
 process.stderr.write(error.name+': '+error.message+'\n'+String(error.stack).split('\n').filter(line=>line.length<300).slice(-12).join('\n'));
 process.exitCode=1;
}''')
    return text


def decode_state(data):
    data=dict(data)
    data['towers']=tuple(Tower(**tower) for tower in data['towers'])
    data['platforms']=tuple(Platform(**platform) for platform in data['platforms'])
    data['selection_nodes']=tuple(Platform(**platform) for platform in data['selection_nodes'])
    for key in ('route','construction','coefficients'):data[key]=tuple(data[key])
    return Board(**data)


def inputs(case):
    state=decode_state(case['state'])
    # These supplied combat fields are initialization metadata only; original
    # TowerStats/z replace their values before any timer callback executes.
    towers=[dict(kind=t.kind,node=t.node,x=t.x+4,y=t.y-21,damage=0,cooldown=1,radius=1,
                 bonuses=[0]*10,placement_x=t.x) for t in state.towers]
    result=dict(case)
    result.update(scenario=dict(platforms=case['state']['platforms'],route=case['state']['route'],towers=towers,
        enemies=[],wave=state.wave,points=state.points,lives=int(state.hp),salt_lick=case['salt'],
        meal_points=case['meal'],meritoc_points=case['merit'],draw_interval_ms=case['draw']),
        enemy_profile=asdict(trial_profile(case['trial']).enemy),popup_profile=asdict(PopupProfile(0,False)),
        native=case['trial'],births=[],multi=100,crit=1000,chance=100,spread=50,kraken_direction=2,wander=4)
    return result


def modeled(case):
    state=decode_state(case['state']);events=[];rolls=[];world=None;last_result=None
    def random_int(low,high):
        value=high
        rolls.append([world.loop.now_ms,low,high,value]);return value
    world=Summon(state,tuple(Wave(*row) for row in case['waves']),trial=case['trial'],atom_bonus=case['atom_bonus'],
        salt_lick=case['salt'],meal_points=case['meal'],meritoc_points=case['merit'],refunds=tuple(case['refunds']),
        random_int=random_int,popup_profile=PopupProfile(0,False),draw_interval_ms=case['draw'],helper_y=case['helper_y'],
        on_event=lambda *event:events.append(list(event)))
    def snapshot():
        return dict(now=world.loop.now_ms,points=world.points,lives=world.lives,remaining_hp=world.remaining_hp,
            monsters=[[m.source_id,m.monster_id,m.hp,world.monsters.alive(m),m.alive,m.node,m.x,m.y,m.velocity] for m in world.monsters.actors],
            retained=[[m.source_id,m.monster_id,m.hp,world.monsters.alive(m),m.alive] for m in world._monster_pool],
            retained_geometry=[[m.source_id,m.x,m.y,m.width,m.body.height,m.velocity] for m in world._monster_pool],
            wizards=[[w.id,w.animation.frame,w.animation.elapsed_ms,w.animation.finished,w.remaining] for w in world._wizards],
            underlings=[[w.id,[a.id for a in w.underlings]] for w in world._wizards],
            conditions=[[m.source_id,m.color,m.hit_counter,m.move_speed,m.max_hp,m.moving,m.frozen,
                [[row.name,row.seconds] for row in m.statuses]] for m in world.monsters.actors],
            projectiles=[[a.id,a.alive,a.body.x,a.body.y,a.body.left,a.body.top,a.body.width,a.body.height,
                a.animation.frame,a.animation.elapsed_ms,a.animation.finished,a.motion.vx,a.motion.vy,a.fading] for a in world.projectiles._pool],
            actors=[[a.id,a.kind] for a in world.actors if a is not None],
            timers=[[t.actor.id if t.actor else None,t.interval_ms,t.remaining_ms,t.repeat,t.done] for t in world.loop._tasks],
            events=[event[:] for event in events],rolls=[roll[:] for roll in rolls],
            clock=[world.clock.wave,world.clock.countdown,world.clock.roast,world.clock.pending_hp,world.clock.reached,
                   world.clock.credited,[[q.wave,q.remaining,q.interval,q.countdown] for q in world.clock.queues]],
            rows=[[t.kind,t.node,t.x,t.level,t.choices,refund,w.tower.cooldown]
                  for t,refund,w in zip(world.investment_state.towers,world.refunds,world._wizards,strict=True)],result=last_result,
            anchors=[[m.source_id,m.body.real_x,m.body.real_y,m.body.offset_x,m.body.offset_y,
                      m.width,m.body.height,m.motion.x,m.motion.y]
                     for m in world.monsters.actors])
    observations=[]
    for command,*args in case['operations']:
        last_result=None
        if command=='run':world.run_until(args[0])
        elif command=='send':last_result=world.send()
        elif command=='apply':
            action=dict(args[0])
            if 'tower' in action:action['tower']=Tower(**action['tower'])
            last_result=world.apply(Investment(**action))
        else:raise ValueError(command)
        observations.append(snapshot())
    return observations


def check(path,filter_name=None):
    samples=[case for case in cases() if filter_name is None or filter_name in case['name']]
    if not samples:raise ValueError('No matching summons.')
    payload=dict(parts=source_parts(path),cases=[inputs(case) for case in samples])
    run=subprocess.run(['node','-e',script()],input=json.dumps(payload),text=True,capture_output=True,check=True,timeout=30)
    originals=json.loads(run.stdout,parse_int=float)
    difference=load('check-worship-battle.py').difference
    failures=[]
    for case,original in zip(samples,originals,strict=True):
        if case['name']=='captured poison survives sale and roast wave reset':
            hits=[event for event in original[-1]['events'] if event[1]=='hit' and 10000<event[0]<11000 and event[3]>0]
            if not hits:raise AssertionError('The original Poison fixture missed its post-reset, pre-floor damage window.')
            sold=original[4]
            if (any(row[0]==7 for row in sold['rows'])
                    or not any(actor[1] and actor[6:8]==[66,18] for actor in sold['projectiles'])):
                raise AssertionError('The original Poison fixture did not retain its projectile after selling its tower.')
        model=modeled(case)
        for index,(actual,expected) in enumerate(zip(model,original,strict=True)):
            if actual.keys()!=expected.keys():raise AssertionError('The combined host snapshot schema changed.')
            for field in actual:
                found=difference(actual[field],expected[field],f'[{index}].{field}')
                if found:
                    detail=dict(case=case['name'],field=found[0],model=found[1],original=found[2])
                    if field=='projectiles':
                        row=int(found[0].split('.projectiles[')[1].split(']')[0])
                        if row<len(actual[field]) and row<len(expected[field]):
                            detail['actor_context']=[actual[field][row],expected[field][row]]
                            detail['target_context']=[actual['monsters'],expected['monsters']]
                            detail['anchors_before']=[model[index-1]['anchors'],original[index-1]['anchors']] if index else None
                    failures.append(detail)
    if failures:raise AssertionError(failures)
    return len(samples),sum(len(case['operations']) for case in samples)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar',type=Path,required=True);parser.add_argument('--case')
    args=parser.parse_args()
    try:count,observations=check(args.asar,args.case)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr[-2000:])
    print(f'{count} controlled complete summons and {observations} observations match original callbacks.')
