"""Compare spawn stats with original Worship and Actor1 initialization.

Loads the installed client source at runtime. Original wave selection, spawn
scratch fields, CreateMonster HP override, Actor1 constructor/init and skull
status creation execute unchanged. Graphics use numeric animation profiles
independently read from the client resource cache on 2026-10-27. Account
recalculation, image services and listeners are host boundaries; no battle
outcomes or live gameplay are established by this check.
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
from worship_sim.spawning import spawn_stats
from worship_sim.waves import Wave


# Width, height, originX, originY, frameCount. These are controlled graphics
# inputs; scalar spawn stats do not depend on the animation geometry.
ANIMATIONS = {
    'mushG': (50, 50, 25, 50, 16),
    'goblinG': (65, 50, 32, 50, 25),
    'moonman': (52, 54, 26, 54, 27),
    'acorn': (80, 44, 40, 44, 21),
    'snowball': (60, 50, 30, 50, 28),
    'w4b2': (50, 50, 25, 50, 28),
    'w5b3': (45, 45, 22, 45, 28),
    'w6b4': (68, 66, 34, 66, 35),
    'w7a8': (60, 60, 30, 60, 32),
}
MAPS = (26, 63, 30, 107, 155, 208, 259, 308)


def load(file, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'devtools' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_parts(source):
    loader = load('client_source.py', 'loader')
    data = load('check-worship-waves.py', 'waves').source_parts(source)

    registry = 'A["scripts.ActorEvents_1"]='
    reg = source.index(registry)
    enemy_owner = re.match(r'[A-Za-z_$][\w$]*', source[reg + len(registry):])[0]
    start = source.rfind('var ' + enemy_owner + '=function', 0, reg)
    end = source.index('});', source.index('},forwardMessage:', reg)) + 3
    if start < 0:
        raise ValueError('Original enemy constructor boundary changed.')
    data['enemy_class'] = source[start:end]
    data['enemy_owner'] = enemy_owner

    registry = 'A["scripts.MonsterDefinitions"]='
    reg = source.index(registry)
    monster_owner = re.match(r'[A-Za-z_$][\w$]*', source[reg + len(registry):])[0]
    start = source.rfind('var ' + monster_owner + '=function', 0, reg)
    end = source.index('};var ', source.index(monster_owner + '.addNewMonster=function', reg)) + 2
    if start < 0:
        raise ValueError('Original monster definition boundaries changed.')
    data['monster_class'] = source[start:end]
    data['monster_owner'] = monster_owner
    data['monster_types'] = dict(re.findall(
        re.escape(monster_owner) + r'\.([A-Z_]+_TYPE)="([^"]+)"', source))
    if not data['monster_types']:
        raise ValueError('Original monster type constants are unavailable.')

    for name in ('WorshipBASEinfos', '_customBlock_CreateMonster', '_customBlock_AddStatusToMonster'):
        owner, data[name] = loader.function(source, name)
        if name == 'WorshipBASEinfos':
            data['base_owner'] = owner
    data['methods'] = load('check-worship-motion.py', 'motion').source_parts(source)['methods']
    registry = 'A["com.stencyl.models.Actor"]='
    reg = source.index(registry)
    actor_owner = re.match(r'[A-Za-z_$][\w$]*', source[reg + len(registry):])[0]
    prototype = source.index(actor_owner + '.prototype=', reg)
    for name in ('getWidth', 'getAngle', 'getXCenter', 'getYCenter', 'getXVelocity',
                 'setXVelocity', 'setX', 'setY', 'setXY', 'setLocation',
                 'setAnimation', 'switchAnimation', 'setOriginPoint'):
        start = source.index(name + ':function(', prototype)
        end = re.search(r'},[A-Za-z_$][\w$]*:', source[start:])
        if end is None:
            raise ValueError('Original Actor method boundary changed: ' + name)
        data['methods'][name] = source[start + len(name) + 1:start + end.start() + 1]
    return data


def cases():
    result = []
    # Both ordinary opening waves, then every color and multiple size/tier
    # combinations, including uncapped HP tier above the skull-status cap.
    variants = ((2, 0, 2, 0, 1), (5, 0, 2, 0, 2), (1, 0, 1, 1, 1),
                (1, 3, 2, 2, 1), (1, 5, 3, 3, 1), (1, 16, 4, 4, 1), (1, 18, 2, 5, 1))
    for trial, map_id in enumerate(MAPS):
        for count, tier, size, color, birth_wave in variants:
            result.append(dict(trial=trial, map_id=map_id,
                               wave=[count, tier, size, color], birth_wave=birth_wave))
    result.extend([
        dict(trial=0, map_id=26, wave=[1, 2, 3, 0], birth_wave=1),
        dict(trial=0, map_id=26, wave=[1, 20, 2, 0], birth_wave=1),
        dict(trial=7, map_id=308, wave=[2, 0, 2, 0], birth_wave=1, base_hp=3, base_speed=4),
        dict(trial=7, map_id=100, wave=[2, 0, 2, 0], birth_wave=1),
        dict(trial=0, map_id=26, wave=[2, 0, 2, 0], birth_wave=1, native_hp_multiplier=1000),
        dict(trial=0, map_id=26, wave=[2, 0, 2, 0], birth_wave=1, base_hp=3.5),
        dict(trial=0, map_id=26, wave=[2, 0, 2, 0], birth_wave=1, base_hp=0),
        dict(trial=0, map_id=26, wave=[2, 0, 2, 0], birth_wave=1, base_speed=0),
    ])
    result.extend(dict(trial=0, map_id=26, wave=[5, 2, 3, color], birth_wave=1)
                  for color in range(6))
    return result


SCRIPT = r'''
const vm=require('node:vm'),p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
function stringMap(){this.h=Object.create(null)}
try {
 const definitions={A:{},l:stringMap};definitions[p.base_owner]={};
 vm.createContext(definitions);
 vm.runInContext(p.monster_class+p.WorshipBASEinfos,definitions,{timeout:2000});
 Object.assign(definitions[p.monster_owner],p.monster_types);
 const native=definitions[p.monster_owner].get(),baseRows=definitions[p.base_owner].WorshipBASEinfos();
 const results=[];
 for(const input of p.cases){
  const [count,tier,size,color]=input.wave,base=baseRows.map(row=>row.slice()),name=base[input.trial][2];
  const definition={...native.h[name].h};
  definition.MonsterHPTotal*=input.native_hp_multiplier??1;
  if(input.base_hp!==undefined)base[input.trial][0]=input.base_hp;
  if(input.base_speed!==undefined)definition.MoveSPEED=input.base_speed;
  const gen=Array(91).fill(0),battle=Array(150).fill(0);
  Object.assign(gen,{8:input.birth_wave,16:[0,1],17:[0,1],23:[20,20],
    24:[777,888,999,111,222,333],27:'Blank',53:0,56:[],62:30});
  battle[57]=input.trial;
  const helper={_GenINFO:gen},scene={_NumberOfEnemiesTEMP:0,_NumberOfEnemies:0};
  const waves=base.map(()=>Array.from({length:30},()=>[1,0,2,0]));
  waves[input.trial][input.birth_wave-1]=input.wave;
  const attrs={CurrentMap:input.map_id,DummyText:'blah',SceneEvents_n:'fixture',
    MonstersOnScreen:Array(400).fill(0),MonsterHP:[0],MonsterAlive:[0],MonsterWillDie:[0],
    MonsterRespawnTime:Array(100).fill(0),MapMonstersList:[],OriginPixelActor:[{getZIndex:()=>0}],
    CustomMaps:{h:{WorshipMapType:{h:{[input.map_id]:input.trial}}}},
    CustomLists:{h:{WorshipBASEinfos:base,WorshipInfo:waves,PrayerInfo:[],
      RANDOlist:Array.from({length:100},()=>[]),NinjaInfo:Array.from({length:40},()=>[])}},
    MonsterDefinitionsGET:{h:{[name]:{h:definition}}},NodeX:[0,500],NodeLength:[400,900],NodeY:[300,500],
    OptionsListAccount:Array(700).fill(0),PixelHelperActor:[],DummyNumbersStatManager:{h:{}}};
  attrs.PixelHelperActor[7]={behaviors:{getBehavior:()=>helper}};
  attrs.PixelHelperActor[8]={behaviors:{getBehavior:()=>({_GenINFO:battle})}};
  let lastActor=null;
  const engine={tasks:[],addTask(task){this.tasks.push(task)},gameAttributes:{h:attrs},whenMouseReleased:[],
    getGameAttribute(key){if(!(key in attrs))throw Error('Missing attribute '+key);return attrs[key]}};
  const image=()=>({get_width:()=>10,get_height:()=>10});
  const ctx={a:{engine,STEP_SIZE:10,NO_PHYSICS:false,SCALE:1,physicsScale:10,
      toPhysicalUnits:x=>x/10,toPixelUnits:x=>x*10},c:{engine},A:{},l:stringMap,
    n:{__cast:x=>x},ka:{},rc:{},z:{},ma:{},va:{antialias:false},
    V:function(x,y){this.x=x;this.y=y},oa:function(){this.nameMap={h:{}}},
    E:(base,props)=>Object.assign(Object.create(base),props),w:(self,fn)=>fn.bind(self),
    h:{string:String},u:{deepCopyList:x=>JSON.parse(JSON.stringify(x))},
    y:{replace:(s,a,b)=>s.split(a).join(b)},D:{contains:(xs,x)=>xs!=null&&Array.prototype.includes.call(xs,x)},
    t:{linear:0},p:{_customBlock_Dungon:()=>-1},q:{},
    k:{_customBlock_addImgInst:image},v:{_customBlock_performETCaction(action){
      if(action!=='MonsterRespawnTimeReset')throw Error('Unexpected account action '+action);
      // The supplied monster definition is fixed for this isolated initialization.
    }}};
  ctx.oa.prototype.addListener=function(list,fn){list.push(fn)};
  vm.createContext(ctx);
  vm.runInContext(p.constructor+p.prototype+p.registration+p.enemy_class+
    p._customBlock_WorshipStuff+p._customBlock_2inputs+
    p._customBlock_CreateMonster+p._customBlock_AddStatusToMonster,ctx,{timeout:2000});
  const methods={};for(const [name,body] of Object.entries(p.methods))
    methods[name]=vm.runInContext('('+body+')',ctx,{timeout:2000});
  function animation(profile){
    return {model:{frames:Array(profile[4]).fill(0)},timer:0,frameIndex:0,finished:false,filter:null,
      set_filter(){},set_visible(){},set_bitmapData(){},
      get_width:()=>profile[0],get_height:()=>profile[1]};
  }
  Object.assign(ctx.c,{asNumber:x=>x==null?0:Number(x),randomInt:(a,b)=>b,
    getCurrentSceneName:()=>'fixture',getActorType:x=>x,
    getValueForScene:(_,key)=>{if(!(key in scene))throw Error('Unknown scene value '+key);return scene[key]},
    setValueForScene:(_,key,value)=>{scene[key]=value},getLastCreatedActor:()=>lastActor,
    attachImageToActor(){},createSaturationFilter:()=>0,createHueFilter:()=>0,
    createRecycledActor(type,x,y){
      if(type!==1)throw Error('Unexpected actor creation '+type);
      const actor={...methods,whenDrawing:[],whenUpdated:[],physicsMode:1,body:null,
        currAnimation:null,currAnimationName:null,cacheWidth:0,cacheHeight:0,
        currOffset:{x:0,y:0},currOrigin:{x:0,y:0},realX:0,realY:0,realAngle:0,
        realScaleX:1,realScaleY:1,lastScale:{x:1,y:1},xSpeed:0,ySpeed:0,rSpeed:0,
        fixedRotation:false,paused:false,isHUD:false,ignoreGravity:true,continuousCollision:false,
        snapOnSet:false,collidable:false,shapeMap:{h:{}},bitmapFilters:null,drawActor:true,
        animationMap:{h:Object.fromEntries(Object.entries(p.animations).map(([n,profile])=>[n,animation(profile)]))},
        originMap:{h:Object.fromEntries(Object.entries(p.animations).map(([n,profile])=>[n,{x:profile[2],y:profile[3]}]))},
        addChild(){},removeChild(){},updateChildrenPositions(){},clearCollisionInfoList(){},
        sendToBack(){},moveToBottom(){},setZIndex(){},getZIndex:()=>0,makeAlwaysSimulate(){},
        growTo(x,y){this.realScaleX=x;this.realScaleY=y},setFilter(){},isAlive:()=>true,isPaused:()=>false};
      actor.setAnimation('mushG');actor.setLocation(x,y);
      const script=new ctx[p.enemy_owner]();script.actor=actor;script.wrapper={enabled:true};
      actor.behaviors={getBehavior:()=>script};script.init();lastActor=actor;
    }});
  helper._customEvent_WorshipStuff=vm.runInContext('('+p.helper+')',ctx,{timeout:2000});
  helper._TRIGGEREDtext='f'+input.birth_wave;helper._customEvent_WorshipStuff();
  const script=lastActor.behaviors.getBehavior(),status=script._StatusActive[0];
  if(status[1]!==36000||gen[24][1]!==1||gen[24][2]!==1||gen[24][4]!==size||gen[24][5]!==tier)
    throw Error('Original spawn scratch/status contract changed');
  if(script._SizeMulti!==size||script._WorshipMOD!==color||script._IsWorshipMob!==1)
    throw Error('Original enemy initialization flags changed');
  const hp=attrs.MonsterHP[script._MonsterID];
  if(script._MonsterHPtot!==hp)throw Error('Original maximum HP override disagrees');
  results.push({base_hp:Number(base[input.trial][0]),base_speed:definition.MoveSPEED,
    stats:{hp,speed:script._MoveSPEEDinitial,skull:Number(status[0].slice('StatusSkull'.length))}});
 }
 process.stdout.write(JSON.stringify(results));
} catch(error) {process.stderr.write(error.stack);process.exitCode=1;}
'''


def check(path):
    source = load('client_source.py', 'loader').source_from_asar(path)
    payload = source_parts(source)
    inputs = cases()
    payload.update(cases=inputs, animations=ANIMATIONS)
    run = subprocess.run(['node', '-e', SCRIPT], input=json.dumps(payload), text=True,
                         capture_output=True, check=True, timeout=30)
    # JSON integer tokens still represent JavaScript doubles. Parsing large
    # tokens as arbitrary-precision Python integers would change their value.
    originals = json.loads(run.stdout, parse_int=float)
    for index, (case, original) in enumerate(zip(inputs, originals, strict=True)):
        actual = asdict(spawn_stats(Wave(*case['wave']), base_hp=original['base_hp'],
                                   base_speed=original['base_speed'], map_id=case['map_id']))
        if actual != original['stats']:
            raise AssertionError(dict(case=index, inputs=case, model=actual, original=original['stats']))
    return len(inputs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar', type=Path, required=True)
    args = parser.parse_args()
    try:
        count = check(args.asar)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr[-2000:])
    print(f'{count} spawn cases match full original Actor1 initialization across all 8 trials. Battles remain unverified.')
