"""Compare Worship status mutations with original installed-client callbacks.

Controlled targets are Worship monsters, not pets or card displays. Images and
geometry are host services. The original callbacks, hit selection, damage and
timer traversal execute unchanged. These checks do not validate whole battles.
"""
import argparse
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from worship_sim.simulation import ActorClock, TimerLoop
from worship_sim.status import TimedStatus, add_status, tick_movement, tick_second, void_cleanse


def load(filename):
    spec=importlib.util.spec_from_file_location(filename,Path(__file__).with_name(filename))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_parts(source):
    def method(actor,name,following):
        start=source.index('A["scripts.ActorEvents_'+str(actor)+'"]=')
        start=source.index(name+':function',start)
        end=source.index('},'+following+':',start)
        return source[start+len(name)+1:end+1]

    parts=load('check-worship-simulation.py').source_parts(source)
    target=load('check-worship-targeting.py').source_parts(source)
    parts.update(hitscan=target['hitscan'],distance=target['distance'])
    parts['damage']=load('check-worship-damage.py').damage_function(source)
    parts['init']=load('check-worship-combat.py').projectile_init(source)
    parts['projectile_update']=method(478,'_event_01','init')
    parts['movement']=method(1,'_event_Movement','_event_1sec')
    # The method following the one-second callback is stable in this bundle;
    # read its name instead of including any part of that callback.
    start=source.index('_event_1sec:function',source.index('A["scripts.ActorEvents_1"]='))
    end=source.index('},_',start)
    parts['second']=source[start+len('_event_1sec:'):end+1]
    parts['images']=method(1,'_event_StatusEffectsHPbar','_event_Movement')
    parts['status']=load('client_source.py').function(source,'_customBlock_AddStatusToMonster')[1]
    return parts


def scenarios():
    cases=[]

    def case(name,rows=(),operations=(),**fields):
        initial=dict(move_speed=3,move_speed_initial=7,velocity=0,moving=True,
                     row_alive=1,color=0,hit_counter=0,hp=40,max_hp=100,frozen=False)
        initial.update(fields)
        cases.append(dict(name=name,initial=initial,statuses=list(rows),operations=list(operations)))

    case('append-and-overwrite',operations=[['add','StatusFreeze',6],
         ['add','StatusSkull16',36000],['add','StatusFreeze',2],
         ['add','StatusBuffHeal',3],['movement',1]])
    for skull in range(17):
        for seconds in (-1,0,1,2,3,36000):
            case(f'skull-{skull}-{seconds}',[(f'StatusSkull{skull}',seconds)],
                 [['movement',1],['movement',1]])
    for name in ('StatusFreeze','StatusNoMove'):
        for velocity in (-3,0,3):
            for direction in (-1,1):
                for alive in (0,None,1):
                    case(f'{name}-{velocity}-{direction}-{alive}',[(name,2)],
                         [['movement',direction]],velocity=velocity,row_alive=alive)
        for moving in (False,True):
            for frozen in (False,True):
                case(f'{name}-guards-{moving}-{frozen}',[(name,1)],
                     [['movement',1],['movement',1]],moving=moving,frozen=frozen)
        case(name+'-nonpositive',[(name,0)],[['movement',1],['second']])
    for direction in (-1,1):
        for rows in ([('StatusFreeze',2),('StatusNoMove',4)],
                     [('StatusNoMove',2),('StatusFreeze',4)],
                     [('StatusFreeze',0),('StatusNoMove',-1)],
                     [('StatusBuffHeal',1),('StatusFreeze',1),('StatusNoMove',1),('StatusSkull16',1)]):
            case(f'ordered-{direction}-{rows}',rows,[['movement',direction],['movement',direction]])
        case(f'no-move-retains-velocity-{direction}',[('StatusNoMove',4)],
             [['movement',direction],['movement',direction]],velocity=3)
    for hp in (0,.5,49,50,99):
        for heal in (False,True):
            case(f'regen-{hp}-{heal}',[('StatusBuffHeal',0)] if heal else [],
                 [['second']],color=3,hp=hp)
    case('ceil-after-fractional-hp-cap',[('StatusBuffHeal',-1)],
         [['second']],hp=2,max_hp=2.5)
    for counter in (-2,-1,0,5):
        for hp in (0,40):
            case(f'blue-{counter}-{hp}',[('StatusBuffHeal',3)],
                 [['second'],['second']],color=2,hp=hp,hit_counter=counter)
    for color in range(6):
        for rows in ([],[('StatusSkull0',8)],[('StatusSkull16',8)],
                     [('StatusFreeze',8)],[('StatusBuffHeal',8)],
                     [('StatusSkull0',8),('StatusBuffHeal',8),('StatusNoMove',8)],
                     [('StatusFreeze',8),('StatusBuffHeal',8)],
                     [('StatusBuffHeal',8),('StatusSkull16',8),('StatusNoMove',8)]):
            # Zero damage leaves these projected status fields unchanged before
            # cleansing. Negative blue counters also keep the hit from counting.
            case(f'void-{color}-{rows}',rows,[['void']],color=color,hit_counter=-1)
    case('image-callback-does-not-mutate-status-state',[('StatusFreeze',6)],
         [['images']],color=3,velocity=3)
    for order in ('movement-first','second-first'):
        for seconds in (1,3):
            case(f'periodic-order-{order}-{seconds}',[('StatusBuffHeal',seconds)],
                 [['periods',order],['run',990],['run',1000],['run',1990],
                  ['run',2000],['run',3990],['run',4000]],color=3)
    for applied in (1990,2010):
        case(f'status-applied-at-{applied}',operations=[['periods','movement-first'],
             ['run',applied],['add','StatusBuffHeal',3],['run',3000],
             ['run',4000],['run',5000],['run',6000]],color=3)
    return cases


@dataclass
class Target:
    statuses: list[TimedStatus]
    move_speed: float
    move_speed_initial: float
    velocity: float
    moving: bool
    row_alive: int | None
    color: int
    hit_counter: int
    hp: float
    max_hp: float
    frozen: bool


def modeled(case):
    target=Target([TimedStatus(*row) for row in case['statuses']],**case['initial'])
    clock=ActorClock()
    loop=TimerLoop()
    events=[]
    observations=[]

    def movement():
        events.append([loop.now_ms,'movement'])
        tick_movement(target,direction=1)

    def second():
        events.append([loop.now_ms,'second'])
        tick_second(target)

    for command,*args in case['operations']:
        if command=='add':
            add_status(target,*args)
        elif command=='movement':
            tick_movement(target,direction=args[0])
        elif command=='second':
            tick_second(target)
        elif command=='void':
            void_cleanse(target)
        elif command=='images':
            pass
        elif command=='periods':
            order=('movement','second') if args[0]=='movement-first' else ('second','movement')
            for name in order:
                callback=movement if name=='movement' else second
                loop.schedule(2000 if name=='movement' else 1000,
                              lambda task,callback=callback:callback(),repeat=True,actor=clock)
        elif command=='run':
            loop.run_until(args[0])
        else:
            raise ValueError('Unknown operation '+command)
        observations.append(dict(now=loop.now_ms,
            statuses=[[row.name,row.seconds] for row in target.statuses],
            **{key:getattr(target,key) for key in case['initial']},
            events=[event[:] for event in events]))
    return observations


SCRIPT=r'''
const fs=require('node:fs'),vm=require('node:vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
function run(fixture){
 const initial=fixture.initial;let now=0;const events=[];
 const attrs={CurrentMap:26,MonsterHP:[initial.hp],MonsterAlive:[1,1],
  MapMonstersList:[],DummyNumbersStatManager:{h:{}},
  MonsterDefinitionsGET:{h:{synthetic:{h:{Type:'Monster',DeathFrame:1,SpecialType:'',Defence:0}}}},
  CustomLists:{h:{NonDMGLinemonsterTypes:[]}},NodeX:[0],NodeLength:[10000],
  OriginPixelActor:Array(7).fill({getZIndex:()=>0}),OptionsList:Array(28).fill(0),
  DNSM:{h:{}},QuestComplete:{h:{Royal_Worm5:1}},Tasks:[[0,[1e300]]],dummyCritDmgMulti:1};
 const gen=Array(85).fill(0);gen[16]=[0];gen[17]=[0];gen[84]=1;
 attrs.PixelHelperActor=Array(8).fill({behaviors:{getBehavior:()=>({_GenINFO:gen})}});
 const engine={tasks:[],isPaused:()=>false,addTask(task){this.tasks.push(task)},
  getLayerByName:()=>0,gameAttributes:{h:attrs},getGameAttribute:key=>{
   if(!(key in attrs))throw Error('Unexpected attribute '+key);return attrs[key];
  },whenTypeGroupKilledEvents:{h:{}},removeActorFromLayer(){},allActors:{unset(){}}};
 const ctx={a:{engine,STEP_SIZE:10,SCALE:1},c:{engine},A:{},
  ba:{remove:(xs,x)=>{const index=xs.indexOf(x);if(index>=0)xs.splice(index,1)}},
  n:{__cast:x=>x},B:{},ka:{},D:{contains:(xs,x)=>xs.includes(x)},h:{string:String},
  y:{replace:(s,a,b)=>s.split(a).join(b)},t:{linear:0},w:(self,fn)=>fn.bind(self),
  p:{_customBlock_Dungon:()=>-1},m:{_customBlock_Windwalker:name=>{
   if(name!=='CompassTempest')throw Error('Unexpected account query '+name);return 0;
  }},x:{_customBlock_DamageDealed:name=>{if(name!=='RNG')throw Error(name);return 0}},q:{},k:{}};
 Object.assign(ctx.c,{asNumber:x=>x==null?0:Number(x),randomInt:(a,b)=>b,
  getCurrentSceneName:()=>'Acorn',attachImageToActor(){},removeImage(){},
  setXForImage(){},setYForImage(){},createSaturationFilter:()=>0});
 ctx.k._customBlock_addImgInst=name=>({name,get_height:()=>10,get_width:()=>8});
 vm.createContext(ctx);const parts=input.parts;
 vm.runInContext(parts.constructor+parts.prototype+parts.registration+parts.status,ctx);
 const fn=key=>vm.runInContext('('+parts[key]+')',ctx);
 const phase=vm.runInContext('(function(){var n,t;'+parts.phase+'})',ctx);
 const recycle=fn('recycle');ctx.c.recycleActor=actor=>recycle.call(engine,actor);
 ctx.q._customBlock_Hitscanning=fn('hitscan');ctx.k._customBlock_DistanceEqn=fn('distance');
 ctx.k._customBlock_CreateDmgPixel=fn('damage');
 const script={wrapper:{enabled:true},_MonsterID:0,_MonsterNODE:0,_MonsterType:'synthetic',
  _IsWorshipMob:1,_PetStatus:0,_IsCardDisp:0,_SizeMulti:2,_Monster0ffsetX:20,_Monster0ffsetY:0,
  _StatusList:[],_StatusActive:[],_StatusImgInst:[],_HpBarImgInst:[{}, {},0,0,0,0],
  _MoveSPEED:initial.move_speed,_MoveSPEEDinitial:initial.move_speed_initial,
  _MonsterMoving:Number(initial.moving),_Frozen:Number(initial.frozen),
  _WorshipMOD:initial.color,_PersNum:initial.hit_counter,_MonsterHPtot:initial.max_hp};
 const actor={x:100,velocity:initial.velocity,recycled:false,
  getX(){return this.x-20},setX(x){this.x=x+20},getY:()=>0,
  getXCenter(){return this.x},getYCenter:()=>0,getXVelocity(){return this.velocity},
  setXVelocity(v){this.velocity=v},growTo(){},getCurrentFrame:()=>0,setCurrentFrame(){},
  set_alpha(){},clearFilters(){},setFilter(){},isAlive:()=>true,isPaused:()=>false,
  behaviors:{getBehavior:name=>{if(name!=='ActorEvents_1')throw Error(name);return script}}};
 script.actor=actor;attrs.MapMonstersList=[actor];attrs.MonsterAlive[0]=initial.row_alive;
 for(const[name,seconds]of fixture.statuses)ctx.k._customBlock_AddStatusToMonster(name,actor,seconds);
 const movement=fn('movement'),second=fn('second'),images=fn('images'),init=fn('init');
 const observations=[];
 for(const[command,...args]of fixture.operations){
  if(command==='add')ctx.k._customBlock_AddStatusToMonster(args[0],actor,args[1]);
  else if(command==='movement'){
   gen[17]=[args[0]===1?0:1];movement.call(script);
  }else if(command==='second')second.call(script);
  else if(command==='images')images.call(script);
  else if(command==='void'){
   attrs.WeaponType=7;attrs.DummyList=[0,0,0,0,100];
   const projectile={recycled:false,physicsMode:1,whenKilled:{length:0},
    getAnimation:()=> '7',getXCenter:()=>100,getYCenter:()=>0,isAlive(){return !this.recycled},
    isPaused:()=>false,getType:()=>({__id__:0}),getGroup:()=>({__id__:0})};
   for(const name of ['makeAlwaysSimulate','moveToLayer','setAnimation','growTo','setXY',
    'cancelTweens','clearFilters','resetBlendMode','set_alpha','switchToDefaultAnimation',
    'disableActorDrawing','removeAttachedImages','removeAllListeners','resetListeners'])projectile[name]=()=>{};
   init.call({actor:projectile,wrapper:{enabled:true},_event_01:fn('projectile_update')});
  }else if(command==='periods'){
   const order=args[0]==='movement-first'?['movement','second']:['second','movement'];
   for(const name of order)ctx.c.runPeriodically(name==='movement'?2000:1000,()=>{
    events.push([now,name]);(name==='movement'?movement:second).call(script);
   },actor);
  }else if(command==='run'){
   while(now<args[0]){now+=10;phase.call(engine)}
  }else throw Error('Unknown operation '+command);
  observations.push({now,statuses:script._StatusActive.map(row=>row.slice()),
   move_speed:script._MoveSPEED,move_speed_initial:script._MoveSPEEDinitial,
   velocity:actor.velocity,moving:Boolean(script._MonsterMoving),row_alive:attrs.MonsterAlive[0],
   color:script._WorshipMOD,hit_counter:script._PersNum,hp:attrs.MonsterHP[0],
   max_hp:script._MonsterHPtot,frozen:Boolean(script._Frozen),events:events.map(row=>row.slice())});
 }
 return observations;
}
process.stdout.write(JSON.stringify(input.scenarios.map(run)));
'''


def check(path):
    source=load('client_source.py').source_from_asar(path)
    cases=scenarios()
    payload=dict(parts=source_parts(source),scenarios=cases)
    run=subprocess.run(['node','-e',SCRIPT],input=json.dumps(payload),text=True,
                       capture_output=True,check=True,timeout=30)
    original=json.loads(run.stdout)
    if len(original)!=len(cases):
        raise AssertionError('Original scenario count differs')
    count=0
    for case,expected in zip(cases,original):
        actual=modeled(case)
        if len(actual)!=len(expected):
            raise AssertionError(case['name']+': observation count differs')
        for index,(got,want) in enumerate(zip(actual,expected)):
            if got!=want:
                raise AssertionError(f"{case['name']} operation {case['operations'][index]}: "
                                     f'overlay {got}, original {want}')
            count+=1
    return len(cases),count


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar',type=Path,required=True)
    args=parser.parse_args()
    try:
        cases,observations=check(args.asar)
        print(f'{cases} original-client status scenarios and {observations} observations matched.')
    except (AssertionError,ValueError,OSError,subprocess.SubprocessError) as error:
        if isinstance(error,subprocess.CalledProcessError):
            print(error.stderr[-1500:],file=sys.stderr)
        raise SystemExit(str(error))
