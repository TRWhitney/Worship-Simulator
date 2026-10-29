"""Compare complete isolated Pulse fights with original client callbacks.

This development experiment extracts methods from the installed ASAR at runtime.
Account-side XP and UI services are disabled explicitly. Geometry, tower stats and animations are
controlled inputs. This is not a live battle observation or a layout benchmark.
Defeat checks the original life-zero condition on a draw boundary. The HUD
termination callback and its cleanup side effects are not executed here.
"""
import argparse
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from worship_sim.models import Platform
from worship_sim.encounter import CombatTower, EncounterInput, run_encounter
from worship_sim.simulation import Combatant


def load(file, name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'devtools'/file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_parts(path):
    source = load('client_source.py', 'loader').source_from_asar(path)
    data = load('check-worship-simulation.py', 'timer').source_parts(source)
    data.update(load('check-worship-targeting.py', 'target').source_parts(source))
    data['damage'] = load('check-worship-damage.py', 'damage').damage_function(source)

    def actor_method(registry, name, following):
        start = source.index('A["scripts.ActorEvents_'+str(registry)+'"]=')
        start = source.index(name+':function', start)
        end = source.index('},'+following+':', start)
        return source[start+len(name)+1:end+1]

    data['cooldown'] = actor_method(340, '_event_01sec', '_event_Trapping')
    data['kill'] = actor_method(1, '_event_KILL', '_event_Corrections')
    data['node_boundary'] = actor_method(1, '_event_NodeBoundary', '_event_KILL')
    start = source.index('._customBlock_WorshipStuff=')
    following = source.index('._customBlock_TrappingStuffs=', start)
    end = source.rfind('},', start, following)
    data['worship'] = source[start+len('._customBlock_WorshipStuff='):end+1]
    registry = source.index('A["com.stencyl.graphics.BitmapAnimation"]=')
    start = source.index('update:function', registry)
    end = source.index('},getCurrentFrame:', start)
    data['animupdate'] = source[start+len('update:'):end+1]
    start = source.index('setFrame:function', registry)
    end = source.index('},isFinished:', start)
    data['animsetframe'] = source[start+len('setFrame:'):end+1]
    start = source.index('internalUpdate:function(')
    end = source.index('},updateDrawingMatrix:', start)
    data['internalupdate'] = source[start+len('internalUpdate:'):end+1]
    methods = load('check-worship-motion.py', 'motion').source_parts(source)['methods']
    marker = 'A["com.stencyl.models.Actor"]='
    registry = source.index(marker)
    owner = re.match(r'[A-Za-z_$][\w$]*', source[registry+len(marker):])[0]
    prototype = source.index(owner+'.prototype=', registry)
    for name in ('getXCenter', 'getYCenter', 'getWidth', 'setXCenter', 'setX', 'setY',
                 'getXVelocity', 'setXVelocity'):
        start = source.index(name+':function(', prototype)
        end = re.search(r'},[A-Za-z_$][\w$]*:', source[start:])
        if end is None:
            raise ValueError('Original Actor method boundary changed: '+name)
        methods[name] = source[start+len(name)+1:start+end.start()+1]
    data['actor_methods'] = methods
    return data


def scenarios():
    def case(name, *, hp=20, damage=10, cooldown=.1, draw=20, horizon=100000,
             x=200, wave=1, points=0, salt=0, meal=0, merit=0,
             velocity=0, direction=1, right=10000, lives=20, tower_x=100, radius=200, width=40):
        scenario = EncounterInput(
            platforms=(Platform(0, 0, right, 100, direction),), route=(0,),
            towers=(CombatTower(0, 0, tower_x, 75, damage, cooldown, radius),),
            enemies=(Combatant(1, 0, x, hp, velocity=velocity, y=75, width=width),),
            wave=wave, points=points, lives=lives, salt_lick=salt,
            meal_points=meal, meritoc_points=merit, draw_interval_ms=draw)
        return dict(name=name, scenario=asdict(scenario), horizon=horizon)

    cases = [case('first two casts'), case('sustained fight', hp=1000, damage=20, cooldown=1),
             case('point rounding boundary',hp=10,points=.49999999999999994),
             case('overkill', hp=3), case('fractional damage', hp=21, damage=10.5),
             case('horizon before first cast', horizon=490),
             case('horizon before death draw', hp=10, draw=30, horizon=500),
             case('no in-range target', x=900, horizon=2000)]
    for draw in (10, 20, 30, 50):
        cases.append(case(f'draw interval {draw}', hp=10, draw=draw))
    for wave in (0, 1, 3, 10, 100):
        for salt, meal, merit in ((0, 0, 0), (25, 20, 30), (100, 50, 50)):
            cases.append(case(f'wave {wave} bonuses {salt}/{meal}/{merit}',
                              wave=wave, points=3.6, salt=salt, meal=meal, merit=merit))
    for direction in (-1, 1):
        for draw in (10, 20, 30, 50):
            cases.append(case(f'leak direction {direction} draw {draw}',
                              x=171 if direction == 1 else 29, velocity=7*direction,
                              direction=direction, right=200, damage=0, lives=1,
                              draw=draw, horizon=1000))
            cases.append(case(f'moving kill direction {direction} draw {draw}',
                              x=200 if direction == 1 else 400, velocity=7*direction,
                              direction=direction, draw=draw))
        cases.append(case(f'repeated leaks direction {direction}',
                          x=171 if direction == 1 else 29, velocity=7*direction,
                          direction=direction, right=200, damage=0, lives=4, horizon=6000))
        cases.append(case(f'strict route boundary direction {direction}',
                          x=171 if direction == 1 else 29, velocity=10*direction,
                          direction=direction, right=200, damage=0, lives=1, horizon=1000))
        cases.append(case(f'surviving leak direction {direction}',
                          x=171 if direction == 1 else 29, velocity=7*direction,
                          direction=direction, right=200, damage=0, lives=2, horizon=300))
    cases.extend([
        case('moving range entry', velocity=7, tower_x=500),
        case('moving range exit', velocity=7, radius=150, horizon=3000),
        case('odd-width leak center', x=171.4, width=41, velocity=7,
             right=200, lives=2, damage=0, horizon=4000),
        case('opposite movement bounces at drawing', x=29, velocity=-7,
             right=200, damage=0, lives=2, horizon=4000),
    ])
    return cases


SCRIPT = r'''
const vm=require('vm'),fs=require('fs'),p=JSON.parse(fs.readFileSync(0,'utf8'));
function run(input){
 const s=input.scenario,tower=s.towers[0],enemy=s.enemies[0],platform=s.platforms[0];
 const hp=enemy.hp,damage=tower.damage,cooldown=tower.cooldown;
 let now=0,events=[],finished=null,reason='horizon',removedImages=0;
 const engine={tasks:[],paused:false,isPaused(){return false},addTask(t){this.tasks.push(t)}};
 const ctx={a:{engine,STEP_SIZE:10,NO_PHYSICS:false},c:{engine},A:{},ba:{remove:(xs,x)=>{const i=xs.indexOf(x);if(i>=0)xs.splice(i,1)}}};
 vm.createContext(ctx);vm.runInContext(p.constructor+p.prototype+p.registration,ctx);
 const phase=vm.runInContext('(function(){var n,t;'+p.phase+'})',ctx),fn=k=>vm.runInContext('('+p[k]+')',ctx);
 const anim={model:{sync:false,looping:true,frames:Array(136).fill(0)},frameIndex:0,timer:0,finished:false,numFrames:136,durations:Array(136).fill(100),filter:null,set_bitmapData(){}};
 for(const frame of [4,14,19,29,34,44,49,64,79,94,109])anim.durations[frame]=10000;
 anim.update=fn('animupdate');anim.setFrame=fn('animsetframe');
 const mb={_IsWorshipMob:1,_MonsterID:1,_MonsterNODE:0,_MonsterType:'synthetic',_PetStatus:0,_WorshipMOD:0,_PersNum:0,_StatusList:['StatusSkull0'],_StatusActive:[['StatusSkull0',36000]],_SizeMulti:2,_MoveSPEED:Math.abs(enemy.velocity),_IsCardDisp:0,_TempMonster:1,_MonsterMoving:Number(enemy.velocity!==0),_StatusImgInst:[{}],_DeathFrame:1};
 const methods={};for(const [name,body] of Object.entries(p.actor_methods))methods[name]=vm.runInContext('('+body+')',ctx);
 const mob={...methods,dead:false,recycled:false,realX:enemy.x,realY:enemy.y,
  cacheWidth:enemy.width,cacheHeight:50,currOffset:{x:0,y:0},collidable:false,
  clearCollisionInfoList(){},growTo(){},getAnimation:()=>'synthetic',getNumFrames:()=>2,
  setCurrentFrame(){},isAlive:()=>true,isPaused:()=>false,behaviors:{getBehavior:()=>mb}};
 const base={getZIndex:()=>0};
 const wizard={dead:false,recycled:false,getAnimation:()=>'Wizard',getXCenter:()=>tower.x,getYCenter:()=>tower.y,getCurrentFrame:()=>anim.frameIndex,setCurrentFrame:n=>anim.setFrame(n),setZIndex(){},isAlive:()=>true,isPaused:()=>false};
 const personal={wrapper:{enabled:true},actor:wizard,_PersonalNUM:0,_PersonalLIST:[0,0,'Filler',0,-1,-1,0,base,1]};wizard.behaviors={getBehavior:()=>personal};
 for(const actor of [wizard,mob])Object.assign(actor,{physicsMode:1,paused:false,ignoreGravity:true,isHUD:false,xSpeed:actor===mob?enemy.velocity:0,ySpeed:0,rSpeed:0,realAngle:0,realScaleX:1,realScaleY:1,lastScale:{x:1,y:1},fixedRotation:false,realX:actor===mob?enemy.x:tower.x,realY:actor===mob?enemy.y:tower.y,currAnimation:actor===wizard?anim:null});
 const gen=Array(100).fill(0);gen[8]=s.wave;gen[13]=0;gen[16]=[0];gen[17]=[platform.direction===1?0:1];gen[23]=[s.lives,s.lives];gen[27]='Blank';gen[54]=[];gen[84]=1;gen[19]=[];gen[51]=s.points;
 const row=[0,0,tower.x,0,-1,1,base,wizard,cooldown,'',{h:{1:0,3:0,5:0}},0];gen[56]=[row];
 const gen8=Array(150).fill(0);
 const helper={wrapper:{enabled:true},actor:{getY:()=>platform.y-50,isAlive:()=>true,isPaused:()=>false},_GenINFO:gen};
 const pixels=Array(9).fill({behaviors:{getBehavior:()=>helper}});pixels[8]={behaviors:{getBehavior:()=>({_GenINFO:gen8})}};
 const attrs={CurrentMap:26,MapMonstersList:[mob],MonsterHP:[0,hp],MonsterAlive:[0,1],MonsterRespawnTime:[0,0],MonsterDefinitionsGET:{h:{synthetic:{h:{Type:'Monster',HeightOfMonster:50,Defence:0,DeathFrame:1,SpecialType:'',Name:'Synthetic',ExpType:0,ExpGiven:0}}}},PixelHelperActor:pixels,CustomLists:{h:{WorshipNODESnETC:[[[0],gen[17]]],NonDMGLinemonsterTypes:[]}},CustomMaps:{h:{WorshipMapType:{h:{26:0}}}},NodeX:[platform.left],NodeLength:[platform.right],NodeY:[platform.y],DNSM:{h:{FamBonusQTYs:{h:{40:0}},StarSigns:{h:{ExpActive:0}}}},Tasks:[[0,[1e300]]],QuestComplete:{h:{Royal_Worm5:1,Capital_P3:1,Bellows2:1}},NONdummies:Array(50).fill(0),OptionsListAccount:Array(700).fill(0),OtherPlayers:{h:{'0':{behaviors:{getBehavior:()=>({_TargetEnemy:null})}}}},UserInfo:['0'],PlayerAutoMoveTOGGLE:1,SceneEvents_n:0,InventoryOrder:[],Lv0:Array(10).fill(0)};
 attrs.OptionsListAccount[327]=1;engine.gameAttributes={h:attrs};engine.getGameAttribute=k=>{if(!(k in attrs))throw Error('Missing attribute '+k);return attrs[k]};
 function service(name,values){return new Proxy(values,{get(t,k){if(k in t)return t[k];throw Error('Missing '+name+' '+String(k))}})}
 Object.assign(ctx,{n:{__cast:x=>x},B:{},ka:{},rc:{},z:{},ma:{},D:{contains:(xs,x)=>xs.includes(x)},h:{string:String},y:{replace:(s,a,b)=>s.split(a).join(b)},t:{linear:0},va:{antialias:false},
 p:service('p',{_customBlock_TowerStats:(name)=>{if(name==='damage')return damage;if(name==='range')return tower.radius;throw Error('Unexpected tower query '+name)},_customBlock_Dungon:()=>-1,_customBlock_Shrine:()=>0,_customBlock_SaltLick:id=>{if(id!==6)throw Error('Unexpected SaltLick query');return s.salt_lick}}),
 m:service('m',{_customBlock_Windwalker:()=>0,_customBlock_Summoning:()=>0,_customBlock_ArcaneType:()=>0,_customBlock_Summoning2:(name,id)=>{if(name!=='MeritocBonusz'||id!==16)throw Error('Unexpected Summoning2 query');return s.meritoc_points}}),
 x:service('x',{_customBlock_DamageDealed:()=>0,_customBlock_ExpMulti:()=>1,_customBlock_GetBuffBonuses:()=>0}),v:service('v',{_customBlock_CardBonusREAL:()=>0,_customBlock_giveEXP(){}}),q:{_customBlock_MealBonus:name=>{if(name!=='TDpts')throw Error('Unexpected meal query');return s.meal_points}},k:{_customBlock_killmonsterQuest(){}}});
 ctx.p._customBlock_WorshipStuff=fn('worship');
 Object.assign(ctx.c,{asNumber:x=>x==null?0:Number(x),randomInt:(a,b)=>b,randomFloat:()=>.9999999999999999,getCurrentSceneName:()=>'Acorn',getActorType:x=>x,removeImage(){removedImages++},createRecycledActor(type){if(type!==34)throw Error('Unexpected actor creation '+type)},getActorsOfType:id=>id===1?[mob]:id===358?[wizard]:[],getValueForScene:(scene,key)=>{if(key==='_NumberOfEnemies')return 0;throw Error('scene '+key)}});
 ctx.q._customBlock_Hitscanning=fn('hitscan');ctx.k._customBlock_DistanceEqn=fn('distance');const dmg=fn('damage');ctx.k._customBlock_CreateDmgPixel=(...args)=>{const before=attrs.MonsterHP[1],value=dmg(...args);events.push([now,'cast',enemy.id,before-attrs.MonsterHP[1]]);return value};
 const cast=fn('event'),tick=fn('cooldown'),kill=fn('kill'),boundary=fn('node_boundary'),internal=fn('internalupdate');mb.actor=mob;mb.wrapper={enabled:true};
 ctx.c.runPeriodically(100,()=>{const before=gen[23][1];tick.call(helper);if(gen[23][1]<before)events.push([now,'leak',enemy.id,gen[23][1]])},helper.actor);ctx.c.runPeriodically(100,()=>cast.call(personal),wizard);
 for(now=10;now<=input.horizon;now+=10){
  phase.call(engine);
  internal.call(wizard,10,true);internal.call(mob,10,true);
  if(now%s.draw_interval_ms===0){
   // The original HUD tests this condition here. Cleanup is outside this check.
   if(gen[23][1]<=0){reason='defeated';finished=now;break}
   boundary.call(mb);kill.call(mb);
   if(attrs.MonsterAlive[1]===0){reason='cleared';finished=now;events.push([now,'death',enemy.id,gen[51]-Math.round(s.points)]);break}
  }
 }
 if(reason==='cleared'&&(mb._StatusList.length!==0||removedImages!==1))throw Error('Original death status cleanup disagrees');
 return {result:{reason,elapsed_ms:finished===null?input.horizon:finished,points:gen[51],lives:gen[23][1],remaining_hp:Math.max(0,attrs.MonsterHP[1])},events};
}
process.stdout.write(JSON.stringify(p.cases.map(run)));
'''


def decode_scenario(data):
    return EncounterInput(**{**data,
        'platforms': tuple(Platform(**value) for value in data['platforms']),
        'route': tuple(data['route']),
        'towers': tuple(CombatTower(**value) for value in data['towers']),
        'enemies': tuple(Combatant(**value) for value in data['enemies'])})


def check(path):
    cases = scenarios()
    payload = source_parts(path)
    payload['cases'] = cases
    run = subprocess.run(['node', '-e', SCRIPT], input=json.dumps(payload),
                         text=True, capture_output=True, check=True, timeout=15)
    originals = json.loads(run.stdout)
    for case, original in zip(cases, originals, strict=True):
        scenario = decode_scenario(case['scenario'])
        before = asdict(scenario)
        events = []
        result = run_encounter(scenario, horizon_ms=case['horizon'], random_int=lambda a, b: b,
                               on_event=lambda *event: events.append(list(event)))
        actual = dict(result=asdict(result), events=events)
        if actual != original:
            raise AssertionError(dict(scenario=case['name'], model=actual, original=original))
        if asdict(scenario) != before:
            raise AssertionError('Encounter execution mutated its input.')
    return len(cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar', type=Path, required=True)
    args = parser.parse_args()
    print(f'{check(args.asar)} isolated Pulse comparisons pass. HUD termination remains unverified.')
