"""Compare persistent actor slots and monster indices with original methods.

Original table classes, pooling, damage and ordinary corpse cleanup execute in
an isolated host. Initial health and actor profiles are controlled inputs;
this checks storage and identity, not complete initialization or battles.
"""
import argparse
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from worship_sim.world import ActorTable, MonsterTable


def load(file, name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'devtools'/file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_parts(path):
    source = load('client_source.py', 'loader').source_from_asar(path)
    parts = load('check-worship-encounter.py', 'encounter').source_parts(path)

    def original_class(name):
        marker = 'A["'+name+'"]='
        registry = source.index(marker)
        owner = re.match(r'[A-Za-z_$][\w$]*', source[registry+len(marker):])[0]
        start = source.rfind('var '+owner+'=function', 0, registry)
        end = source.index(';var ', source.index('__class__:'+owner, registry))
        return owner, source[start:end]+';'

    for key, name in [('table', 'polygonal.ds.IntHashTable'),
                      ('inner', 'polygonal.ds.IntIntHashTable'),
                      ('iterator', 'polygonal.ds.IntHashTableIterator')]:
        parts[key+'_owner'], parts[key] = original_class(name)
    start = source.index('var Ch=function')
    parts['growth'] = source[start:source.index(';var ', start)]+';'
    start = source.index('Bc.blit=function')+len('Bc.blit=')
    parts['blit'] = source[start:source.index('},Bc.', start)+1]
    for name, following in [('recycleActor', 'getRecycledActorOfType'),
                            ('getRecycledActorOfTypeOnLayer', 'createActorOfType')]:
        start = source.index(name+':function(')+len(name)+1
        parts[name] = source[start:source.index('},'+following+':', start)+1]
    start = source.index('c.asNumber=function')+len('c.asNumber=')
    parts['as_number'] = source[start:source.index('},c.hasValue=', start)+1]
    start = source.index('._customBlock_CreateMonster=function')
    start = source.index('a.engine.getGameAttribute("MapMonstersList").push(c.getLastCreatedActor())', start)
    end = source.index('},k.', start)
    parts['spawn_tail'] = 'function(){'+source[start:end+1]
    match = re.search(r'this\.allActors=new '+re.escape(parts['table_owner'])+r'\((\d+)\)', source)
    if match is None:
        raise ValueError('Original engine actor-table initialization changed.')
    parts['engine_capacity'] = int(match[1])
    return parts


def modeled_slots():
    result = {}
    for remove_gui in (False, True):
        table = ActorTable[str](4)
        for key, name in ((1, 'A'), (2, 'GUI'), (3, 'B')):
            table.add(key, name)
        table.remove(1)
        if remove_gui:
            table.remove(2)
        table.add(4, 'C'); table.add(5, 'D')
        result['free_gui' if remove_gui else 'retain_gui'] = list(table)
    table = ActorTable[int](4)
    for key in range(20):
        table.add(key, key)
    for key in range(1, 19):
        table.remove(key)
    before = [table.capacity, list(table)]
    table.add(21, 21)
    result['growth'] = [before, [table.capacity, list(table)]]
    table = ActorTable[str](2)
    table.add(1, 'A'); table.add(2, 'B')
    iterator = iter(table)
    first = next(iterator)
    table.add(3, 'C'); table.remove(2)
    result['growth_during_iteration'] = [first, list(iterator), list(table)]
    table = ActorTable[str](4)
    table.add(1, 'A'); table.add(2, 'B'); table.add(3, 'C')
    iterator = iter(table)
    first = next(iterator)
    table.remove(2)
    result['remove_cached_next'] = [first, list(iterator), list(table)]
    table = ActorTable[str](4)
    table.add(1, 'A'); table.add(2, 'B'); table.add(3, 'C')
    iterator = iter(table)
    first = next(iterator)
    table.remove(2); table.add(4, 'D')
    result['replace_cached_next'] = [first, list(iterator), list(table)]
    table = ActorTable[str](4, reuse_iterator=True)
    table.add(1, 'A'); table.add(2, 'B'); table.add(3, 'C')
    outer = iter(table)
    first = next(outer)
    inner = iter(table)
    result['reuse_nested_iterator'] = [first, inner is outer, next(inner), next(outer), list(outer)]
    table = ActorTable[str](2, reuse_iterator=True)
    table.add(1, 'A'); table.add(2, 'B')
    outer = iter(table)
    first = next(outer)
    table.add(3, 'C'); table.remove(2)
    inner = iter(table)
    result['reuse_reset_after_growth'] = [first, inner is outer, list(outer)]
    return result


CASES = [
    dict(name='first removal aliases survivor', hp=[-5, 100], actions=[['kill', 0], ['remove', 0], ['damage', 0]]),
    dict(name='last removal leaves missing entries', hp=[-5], actions=[['kill', 0], ['remove', 0], ['damage', 0]]),
    dict(name='middle removal aliases last', hp=[100, -5, 200], actions=[['kill', 1], ['remove', 1], ['damage', 1]]),
    dict(name='reuse actor identity', hp=[-5, 100], actions=[['kill', 0], ['remove', 0], ['spawn', 0, 200]]),
    dict(name='spawn replaces stale extended entry', hp=[-5], actions=[['kill', 0], ['remove', 0], ['damage', 0], ['spawn', 0, 200]]),
    dict(name='two cleanup closures compact dynamically', hp=[-5, -5, 100], actions=[['kill', 0], ['kill', 1], ['remove', 0], ['remove', 1]]),
    dict(name='reverse cleanup order preserves removed index', hp=[-5, -5, 100], actions=[['kill', 0], ['kill', 1], ['remove', 1], ['remove', 0]]),
]


@dataclass(eq=False)
class Monster:
    name: str
    key: int
    monster_id: int = -1


def modeled_monsters(case):
    table = MonsterTable[Monster](hp_sentinel=77, alive_sentinel=9, will_die_sentinel=8)
    registry = ActorTable[Monster]()
    actors = [Monster(chr(65+i), 100+i) for i in range(len(case['hp']))]
    for actor, hp in zip(actors, case['hp'], strict=True):
        table.add(actor, hp)
        registry.add(actor.key, actor)
    for action, index, *args in case['actions']:
        actor = actors[index]
        if action == 'kill':
            table.set_alive(actor, 0)
        elif action == 'remove':
            table.remove(actor)
            registry.remove(actor.key)
        elif action == 'damage':
            table.set_hp(actor, table.hp(actor)-10)
        elif action == 'spawn':
            table.add(actor, args[0])
            registry.add(actor.key, actor)
    sentinel = Monster('sentinel', -1, 0)
    return dict(actors=[actor.name for actor in table.actors],
                ids=[actor.monster_id for actor in actors], hp=[table.hp(actor) for actor in actors],
                alive=[table.alive(actor) for actor in actors], will_die=[table.will_die(actor) for actor in actors],
                engine_order=[actor.name for actor in registry if actor is not None],
                sentinels=[table.hp(sentinel), table.alive(sentinel), table.will_die(sentinel)])


SCRIPT = r'''
const vm=require('node:vm'),p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
let nextKey=0;
function context(){
 const ctx={A:{},jj:{},Dh:{},db:{_assert(value){if(!value)throw Error('Original assertion')}},
  mh:{next:()=>++nextKey},Bc:{init(xs,value,first=0,end=xs.length){for(let i=first;i<end;i++)xs[i]=value;return xs}}};
 vm.createContext(ctx);ctx.Bc.blit=vm.runInContext('('+p.blit+')',ctx);
 vm.runInContext(p.growth+p.inner+p.iterator+p.table,ctx);return ctx;
}
const collect=table=>{const out=[],it=table.iterator();while(it.hasNext())out.push(it.next());return out};
function slots(){
 const ctx=context(),Table=ctx[p.table_owner],out={};
 for(const removeGui of [false,true]){const t=new Table(4);t.set(1,'A');t.set(2,'GUI');t.set(3,'B');t.unset(1);if(removeGui)t.unset(2);t.set(4,'C');t.set(5,'D');out[removeGui?'free_gui':'retain_gui']=collect(t)}
 let t=new Table(4);for(let i=0;i<20;i++)t.set(i,i);for(let i=1;i<19;i++)t.unset(i);
 let before=[t.capacity,collect(t)];t.set(21,21);out.growth=[before,[t.capacity,collect(t)]];
 t=new Table(2);t.set(1,'A');t.set(2,'B');let it=t.iterator(),first=it.next();t.set(3,'C');t.unset(2);let rest=[];while(it.hasNext())rest.push(it.next());out.growth_during_iteration=[first,rest,collect(t)];
 for(const replace of [false,true]){t=new Table(4);t.set(1,'A');t.set(2,'B');t.set(3,'C');it=t.iterator();first=it.next();t.unset(2);if(replace)t.set(4,'D');rest=[];while(it.hasNext())rest.push(it.next());out[replace?'replace_cached_next':'remove_cached_next']=[first,rest,collect(t)]}
 t=new Table(4);t.reuseIterator=true;t.set(1,'A');t.set(2,'B');t.set(3,'C');let outer=t.iterator();first=outer.next();let inner=t.iterator();let shared=inner===outer,a=inner.next(),b=outer.next();rest=[];while(outer.hasNext())rest.push(outer.next());out.reuse_nested_iterator=[first,shared,a,b,rest];
 t=new Table(2);t.reuseIterator=true;t.set(1,'A');t.set(2,'B');outer=t.iterator();first=outer.next();t.set(3,'C');t.unset(2);inner=t.iterator();rest=[];while(outer.hasNext())rest.push(outer.next());out.reuse_reset_after_growth=[first,inner===outer,rest];
 return out;
}
function monsterWorld(input){
 const ctx=context(),Table=ctx[p.table_owner],attrs={},tasks=[];
 const engine={tasks,allActors:new Table(p.engine_capacity),recycledActorsOfType:{h:{}},
  whenTypeGroupKilledEvents:{h:{}},whenTypeGroupCreatedEvents:{h:{}},isPaused:()=>false,
  addTask(t){this.tasks.push(t)},getGameAttribute:key=>{if(!(key in attrs))throw Error('Missing attribute '+key);return attrs[key]},
  gameAttributes:{h:attrs},removeActorFromLayer(actor){actor.layer=null},getLayerById:()=>({}),
  moveActorToLayer(actor,layer){actor.layer=layer},createActorOfType(){throw Error('Unexpected new actor')}};
 Object.assign(ctx,{a:{engine,STEP_SIZE:10},c:{engine},n:{__cast:x=>x},B:{},ka:{},ma:{},z:{},Tu:{},Di:{},Uu:{},
  l:function(){this.h={}},ib:{getTimer:()=>0},D:{contains:(xs,x)=>xs.includes(x)},h:{string:String},
  y:{replace:(s,a,b)=>s.split(a).join(b)},t:{linear:0},ba:{remove:(xs,x)=>{const i=xs.indexOf(x);if(i>=0)xs.splice(i,1)}},
  w:(self,fn)=>fn.bind(self)});
 const original=key=>vm.runInContext('('+p[key]+')',ctx);
 vm.runInContext(p.constructor+p.prototype+p.registration,ctx);
 engine.recycleActor=original('recycleActor');engine.getRecycledActorOfTypeOnLayer=original('getRecycledActorOfTypeOnLayer');
 const gen=Array(100).fill(0);gen[8]=1;gen[23]=[20,20];gen[19]=[];gen[51]=0;gen[56]=[];gen[84]=1;
 const misc=Array(150).fill(0),pixels=Array(9).fill({behaviors:{getBehavior:()=>({_GenINFO:gen})}});pixels[8]={behaviors:{getBehavior:()=>({_GenINFO:misc})}};
 Object.assign(attrs,{CurrentMap:26,MonsterHP:[77,...input.hp],MonsterAlive:[9,...input.hp.map(()=>1)],
  MonsterWillDie:[8,...input.hp.map(()=>0)],MonsterRespawnTime:Array(20).fill(0),MapMonstersList:[],
  MonsterDefinitionsGET:{h:{synthetic:{h:{Type:'Monster',Name:'Synthetic',DeathFrame:1,ExpType:0,ExpGiven:0,SpecialType:'',Defence:0}}}},
  PixelHelperActor:pixels,CustomLists:{h:{NonDMGLinemonsterTypes:[]}},DNSM:{h:{FamBonusQTYs:{h:{40:0}},StarSigns:{h:{ExpActive:0}}}},
  NONdummies:Array(50).fill(0),OptionsListAccount:Array(700).fill(0),QuestComplete:{h:{Royal_Worm5:1,Capital_P3:1,Bellows2:1}},
  OtherPlayers:{h:{'0':{behaviors:{getBehavior:()=>({_TargetEnemy:null})}}}},UserInfo:['0'],PlayerAutoMoveTOGGLE:1,
  SceneEvents_n:0,InventoryOrder:[],Lv0:Array(10).fill(0),Tasks:[[0,[1e300]]],DummyList:[],dummyCritDmgMulti:1});
 attrs.OptionsListAccount[327]=1;attrs.OptionsListAccount[539]=1;
 function service(name,values){return new Proxy(values,{get(obj,key){if(key in obj)return obj[key];throw Error('Unexpected '+name+' '+String(key))}})}
 Object.assign(ctx,{p:service('worship',{_customBlock_Dungon:()=>-1,_customBlock_Shrine:()=>0,_customBlock_WorshipStuff:(name)=>{if(name==='SkullCurrency')return 2;if(name==='TrialType')return 0;throw Error(name)}}),
  x:service('player',{_customBlock_ExpMulti:()=>1,_customBlock_GetBuffBonuses:()=>0,_customBlock_DamageDealed:()=>0}),
  m:service('account',{_customBlock_Summoning:()=>0,_customBlock_ArcaneType:()=>0,_customBlock_Summoning2:()=>0,_customBlock_Windwalker:()=>0}),
  v:service('progress',{_customBlock_CardBonusREAL:()=>0,_customBlock_giveEXP(){}}),
  q:service('map',{_customBlock_MealBonus:()=>0}),k:service('damage',{_customBlock_killmonsterQuest(){}})});
 let sceneTemp=input.hp.length,lastCreated=null;
 Object.assign(ctx.c,{asNumber:original('as_number'),randomFloat:()=>.9999999999999999,randomInt:(a,b)=>b,
  getCurrentSceneName:()=>'Acorn',getActorType:x=>x,createRecycledActor(type){if(type!==34)throw Error('Unexpected actor type')},
  recycleActor:actor=>engine.recycleActor(actor),getLastCreatedActor:()=>lastCreated,removeImage(){},
  getValueForScene:(scene,key)=>{if(key==='_NumberOfEnemies')return 0;if(key==='_NumberOfEnemiesTEMP')return sceneTemp;throw Error(key)},
  setValueForScene:(scene,key,value)=>{if(key!=='_NumberOfEnemiesTEMP')throw Error(key);sceneTemp=value}});
 const type={ID:1,__id__:1},actors=input.hp.map((hp,index)=>{
  const script={_MonsterID:index+1,_MonsterNODE:0,_MonsterType:'synthetic',_IsWorshipMob:1,_PetStatus:0,_WorshipMOD:0,
   _PersNum:0,_IsCardDisp:0,_TempMonster:1,_MonsterMoving:1,_DeathFrame:1,_SizeMulti:2,
   _StatusList:['StatusSkull0'],_StatusActive:[['StatusSkull0',36000]],_StatusImgInst:[{}],wrapper:{enabled:true}};
  const actor={ID:100+index,name:String.fromCharCode(65+index),script,physicsMode:1,recycled:false,
   isAlive(){return !this.recycled},isPaused:()=>false,getType:()=>type,getGroup:()=>({__id__:0}),
   whenKilled:{length:0},whenDrawing:{},whenUpdated:{},getAnimation:()=>'synthetic',getNumFrames:()=>2,
   getX:()=>100,getY:()=>0,getXCenter:()=>100,getYCenter:()=>0,setXY(){},getXVelocity:()=>7,setXVelocity(){},
   initScripts(){script._MonsterID=attrs.dummyMonsterID},behaviors:{getBehavior:()=>script}};
  for(const method of ['setCurrentFrame','fadeTo','cancelTweens','clearFilters','resetBlendMode','set_alpha',
   'switchToDefaultAnimation','disableActorDrawing','removeAttachedImages','removeAllListeners','resetListeners',
   'enableAllBehaviors','enableActorDrawing','setAngle','setIgnoreGravity','updateDrawingMatrix'])actor[method]=()=>{};
  script.actor=actor;attrs.MapMonstersList.push(actor);engine.allActors.set(actor.ID,actor);return actor;
 });engine.recycledActorsOfType.h[1]=actors;
 const kill=original('kill'),damage=original('damage'),spawnTail=original('spawn_tail');
 for(const [action,index,value] of input.actions){const actor=actors[index];
  if(action==='kill')kill.call(actor.script);
  if(action==='remove'){
   const outer=engine.tasks.find(task=>task.actor===actor&&task.interval===200);if(!outer)throw Error('Missing original death callback');
   outer.toExecute(outer);
   const inner=engine.tasks.find(task=>task.actor===actor&&task.interval===500);if(!inner)throw Error('Missing original cleanup callback');inner.toExecute(inner);
  }
  if(action==='damage'){attrs.DummyText='WorshipTowerDMG10';attrs.DummyList=[];attrs.dummyCritDmgMulti=1;damage(1,actor,[])}
  if(action==='spawn'){
   attrs.dummyMonsterID=attrs.MapMonstersList.length+1;sceneTemp++;
   lastCreated=engine.getRecycledActorOfTypeOnLayer(type,100,0,0);if(lastCreated!==actor)throw Error('Unexpected pool reuse');
   attrs.MonsterHP[attrs.dummyMonsterID]=value;spawnTail();
  }
 }
 return {actors:attrs.MapMonstersList.map(a=>a.name),ids:actors.map(a=>a.script._MonsterID),
  hp:actors.map(a=>ctx.c.asNumber(attrs.MonsterHP[a.script._MonsterID])),
  alive:actors.map(a=>attrs.MonsterAlive[a.script._MonsterID]??null),will_die:actors.map(a=>attrs.MonsterWillDie[a.script._MonsterID]??null),
  engine_order:collect(engine.allActors).map(a=>a.name),sentinels:[attrs.MonsterHP[0],attrs.MonsterAlive[0],attrs.MonsterWillDie[0]]};
}
process.stdout.write(JSON.stringify({slots:slots(),monsters:p.cases.map(monsterWorld),engine_capacity:p.engine_capacity}));
'''


def check(path):
    parts = source_parts(path)
    parts['cases'] = CASES
    run = subprocess.run(['node', '-e', SCRIPT], input=json.dumps(parts), text=True,
                         capture_output=True, check=True, timeout=15)
    original = json.loads(run.stdout)
    modeled = dict(slots=modeled_slots(), monsters=[modeled_monsters(case) for case in CASES], engine_capacity=256)
    if modeled != original:
        raise AssertionError(dict(model=modeled, original=original))
    return len(modeled['slots']), len(CASES)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar', type=Path, required=True)
    args = parser.parse_args()
    try:
        slots, monsters = check(args.asar)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr[-1800:])
    print(f'{slots} actor-slot and {monsters} monster-index scenarios match original methods. Battles remain outside this check.')
