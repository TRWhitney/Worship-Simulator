"""Compare summon accounting with unchanged original helper and HUD callbacks.

The source is extracted from the installed client at runtime. Monster creation,
account bonuses and graphics are explicit host boundaries. HUD comparisons cover
credit and boss-countdown release; scene defeat cleanup belongs to the host.
"""
import argparse
from dataclasses import astuple
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from worship_sim.controls import SummonClock
from worship_sim.simulation import TimerLoop
from worship_sim.waves import Wave


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), ROOT / 'devtools' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_parts(source):
    loader = load('client_source')
    parts = load('check-worship-waves').source_parts(source)
    start = source.index('_event_4:function', source.index('A["scripts.ActorEvents_340"]='))
    end = source.index('},_event_5:', start)
    parts['hud'] = source[start + len('_event_4:'):end + 1]
    for name in ('WorshipBASEinfos', 'WorshipMapType', 'TDtraits', 'TowerInfo',
                 '_customBlock_TowerStats', '_customBlock_Tower2Stats'):
        owner, code = loader.function(source, name)
        parts[name] = dict(owner=owner, code=code)
    return parts


def cases():
    result = []
    def add(name, operations, **values):
        result.append(dict(name=name, operations=operations, **values))
    add('aligned-native-opening', [['run', 7100], ['run', 10600], ['send'],
                                  ['run', 11100], ['run', 12100]], native_trial=0)
    add('overlap-and-prune', [['second'], ['tenth'], ['send'], ['second'], ['tenth'],
                            *[['tenth'] for _ in range(40)], ['draw', [], 20, False]], countdown=0)
    for pending in (-1, -.1, 0, .5, .5000001):
        for hp in ([], [0, -1], [.1]):
            add(f'credit-{pending}-{hp}', [['draw', hp, 20, False]],
                wave=11, reached=11, countdown=9999, pending_hp=pending)
    for countdown in (999, 1000):
        add(f'boss-boundary-{countdown}', [['draw', [], 20, False]],
            wave=10, reached=10, countdown=countdown)
    for lives, menu in ((0, False), (20, True)):
        add(f'credit-gates-{lives}-{menu}', [['draw', [], lives, menu]],
            wave=10, reached=10, countdown=9999)
    for floor in (0, 40, 600, 20000):
        add(f'roast-floor-{floor}', [['second'], ['second']],
            wave=9, reached=9, countdown=0, roast=123, roast_floor=floor)
    for roast in (14399, 14400):
        add(f'roast-cap-{roast}', [['second']], wave=4, reached=4, countdown=15, roast=roast)
    for wave in (-1, -5):
        add(f'inactive-{wave}', [['second'], ['tenth']], wave=wave, roast=3, roast_floor=600)
    for wave, countdown in ((0, 6), (9, 20), (10, 9999), (10, 999), (10, 998), (10, 2), (201, 120)):
        add(f'send-{wave}-{countdown}', [['send'], ['second']],
            wave=wave, reached=max(0, wave), countdown=countdown)
    for trial in range(8):
        for wave in (29, 30, 59, 60, 90, 250, 1000):
            add(f'native-tier-{trial}-{wave}', [['second'], ['tenth']],
                native_trial=trial, wave=wave, reached=wave, countdown=0)
    add('fractional-pending', [['second'], ['tenth'], *[['tenth'] for _ in range(35)]],
        rows=[[2, 0, 1, 0], [1, 3, 3, 0]], base_hp=3.5, countdown=0)
    for pending in (-.5000001, -.5, .49, .5):
        add(f'pending-balance-rounding-{pending}', [['second'], ['tenth']],
            countdown=0, pending_hp=pending)
    add('retain-higher-credit', [['draw', [], 20, False]],
        wave=11, reached=11, credited=20, countdown=9999)
    add('fractional-countdown', [['second']], countdown=1.5)
    return result


SCRIPT = r'''
const vm=require('node:vm'),p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
function world(input){
 let now=0;const events=[],monsters=[];
 const engine={tasks:[],isPaused:()=>false,addTask(t){this.tasks.push(t)},gameAttributes:{h:{}}};
 const attrs={CurrentMap:26,CustomLists:{h:{}},CustomMaps:{h:{}},PixelHelperActor:[],
  Refinery:[[-3]],OptionsList:Array(30).fill(0),OptionsListAccount:Array(700).fill(0),
  NodeX:[0],NodeLength:[400],NodeY:[0],MenuType:0,MenuType2:0,TowerInfo:Array(30).fill(1),
  Tasks:[[0,[1e300]]],MapMonstersList:monsters,MonsterHP:[],MonsterAlive:[],Dream:Array(10).fill(0),
  DNSM:{h:{}},DummyNumbersStatManager:{h:{}},TotemInfo:Array.from({length:3},()=>Array(8).fill(0)),
  OriginPixelActor:Array(7).fill({getZIndex:()=>0}),QuestComplete:{h:{Royal_Worm5:1,Hoggindaz4:1}},
  Number2Letter:Array(27).fill('').concat(['A','B']),DummyList:[],SceneEvents_n:0};
 engine.gameAttributes.h=attrs;engine.getGameAttribute=key=>{if(!(key in attrs))throw Error('Missing attr '+key);return attrs[key]};
 const img={get_y:()=>0,get_x:()=>0,get_alpha:()=>1,get_width:()=>10,get_height:()=>10,set_alpha(){}};
 const actor={isAlive:()=>true,isPaused:()=>false};
 const self={actor,_customEvent_RefineryStuff(){},wrapper:{enabled:true},_GenINFO:Array(100).fill(0),
  _UIinventoryOn8:Array(100).fill(0),_UIinventory8:Array(100).fill(img)};
 for(const key of [7,41,42,43,46])self._UIinventory8[key]=Array(30).fill(img);
 self._UIinventoryOn8[8]=1;self._UIinventoryOn8[46]=Array(30).fill(0);
 const g=self._GenINFO;Object.assign(g,{6:0,8:0,10:[0,0],11:-1,13:6,14:{},16:[0],17:[0],
  23:[20,20],24:[1,1,1,1,2,0],27:'Blank',51:0,52:Array(10).fill('Mob'),53:0,54:[],55:0,
  56:[],57:-1,59:0,60:Array(9).fill(0),61:Array(9).fill(-1),62:30,64:-1,65:-1,74:0,84:1,85:0,88:0,89:0});
 for(const [name,index] of Object.entries({wave:8,countdown:13,pending_hp:53,reached:55,roast:85}))
  if(input[name]!==undefined)g[index]=input[name];
 attrs.TotemInfo[0][0]=input.credited??0;
 attrs.PixelHelperActor[7]={behaviors:{getBehavior:()=>self}};
 const ctx={a:{engine,STEP_SIZE:10,SCALE:1},c:{engine,asNumber:x=>x==null?0:Number(x),getActorType:x=>x,
  getActorsOfType:type=>type===1?monsters:[],getScreenX:()=>0,getScreenY:()=>0,getFont:()=>({getTextWidth:()=>0}),
  getValueForScene:()=>0,getLastCreatedActor:()=>({setFilter(){}}),createHueFilter:()=>0,
  createSaturationFilter:()=>0,createBrightnessFilter:()=>0,attachImageToActor(){},setFilterForImage(){},
  clearFiltersForImage(){},removeImage(){},moveImageBy(){},moveImageTo(){},recycleActor(){},getCurrentSceneName:()=>'fixture'},
  A:{},ja:{},ka:{},B:{},D:{contains:(xs,x)=>xs.includes(x)},
  n:{__cast:x=>x},h:{string:String},y:{replace:(s,a,b)=>s.split(a).join(b)},
  u:{deepCopyList:x=>JSON.parse(JSON.stringify(x))},
  p:{_customBlock_Dungon:()=>-1,_customBlock_ArcadeBonus:()=>0,_customBlock_Reg_ach_add_status(){},_customBlock_ActionBlock(){}},
  q:{_customBlock_MenagerieStuff:()=>input.roast_floor??0,
   _customBlock_IsXYmouseWithinBounds:(a,b,c,d)=>Number(a===155&&b===215&&c===0&&d===57),
   _customBlock_CommaNotation:String,_customBlock_TotalFoodBonuses:()=>0,_customBlock_DropSomething(){}},
  ba:{remove:(xs,x)=>{const i=xs.indexOf(x);if(i>=0)xs.splice(i,1)}},l:class{constructor(){this.h={}}},
  m:{_customBlock_AtomCollider:()=>0,_customBlock_Windwalker:()=>0,_customBlock_GetSetBonus:()=>0,_customBlock_Bubbastuff:()=>0,_customBlock_Summoning:()=>0},
  x:{_customBlock_DamageDealed:()=>0,_customBlock_skillstats2:key=>key==='WorshipEXPmulti'?1:0,_customBlock_ArbitraryCode:()=>1},
  v:{_customBlock_ProgressStarsign(){},_customBlock_giveEXP(){}},
  k:{_customBlock_DialogueETC:()=>'',_customBlock_TalentCalc:()=>0,_customBlock_AddStatusToMonster(){},
   _customBlock_AdjustImgInst(){},_customBlock_NotateNumber:String,
   _customBlock_CreateMonster(){events.push([self._DummyNumber,self._DummyList.slice(),g[53]])}},t:{linear:0,quadOut:0}};
 vm.createContext(ctx);vm.runInContext(p.constructor+p.prototype+p.registration+p.WorshipInfo+
  p._customBlock_WorshipStuff+p._customBlock_2inputs,ctx);
 for(const key of ['WorshipBASEinfos','WorshipMapType','TDtraits','TowerInfo','_customBlock_TowerStats','_customBlock_Tower2Stats']){
  const part=p[key];ctx[part.owner]??={};vm.runInContext(part.code,ctx);
 }
 const tables=ctx.ja.WorshipInfo(),rows=input.rows??tables[input.native_trial??0];
 attrs.CustomLists.h.WorshipInfo=[rows];g[62]=input.cycle_length??(input.rows?input.rows.length:30);
 for(const key of ['WorshipBASEinfos','TDtraits','TowerInfo'])attrs.CustomLists.h[key]=ctx[p[key].owner][key]();
 const base=input.base_hp??Number(attrs.CustomLists.h.WorshipBASEinfos[input.native_trial??0][0]);
 attrs.CustomLists.h.WorshipBASEinfos[0][0]=base;
 attrs.CustomLists.h.NonDMGLinemonsterTypes=[];attrs.CustomLists.h.PrayerInfo=[];
 attrs.CustomMaps.h.WorshipMapType={h:{26:0}};
 self._customEvent_WorshipStuff=vm.runInContext('('+p.helper+')',ctx);
 const second=vm.runInContext('('+p.second+')',ctx),tenth=vm.runInContext('('+p.tenth+')',ctx),
  send=vm.runInContext('('+p.send+')',ctx),hud=vm.runInContext('('+p.hud+')',ctx),
  phase=vm.runInContext('(function(){var n,t;'+p.phase+'})',ctx);
 ctx.c.runPeriodically(100,tenth.bind(self),actor);ctx.c.runPeriodically(1000,second.bind(self),actor);
 const graphics={alpha:1,font:{getTextWidth:()=>0},setFont(){},drawString(){},drawCircle(){}};
 const snapshots=[];
 function snapshot(){return {wave:g[8],countdown:g[13],queues:g[54],roast:g[85],pending_hp:g[53],
  reached:g[55],credited:attrs.TotemInfo[0][0],events}}
 for(const op of input.operations){
  let bonus;
  if(op[0]==='second')second.call(self);
  else if(op[0]==='tenth')tenth.call(self);
  else if(op[0]==='run')while(now<op[1]){now+=10;phase.call(engine)}
  else if(op[0]==='send'){const before=g[51],enabled=g[13]<999;send.call(self);bonus=enabled?g[51]-before:null}
  else if(op[0]==='draw'){
   monsters.length=0;attrs.MonsterHP=op[1].slice();
   op[1].forEach((hp,id)=>monsters.push({dead:false,recycled:false,
    behaviors:{getBehavior:()=>({_MonsterID:id,_IsWorshipMob:1})}}));
   g[23][1]=op[2];attrs.MenuType2=op[3]?5:0;hud.call(self,graphics);
   snapshots.push({credited:attrs.TotemInfo[0][0],countdown:g[13]});continue;
  }else throw Error('Unknown operation '+op[0]);
  snapshots.push(JSON.parse(JSON.stringify({...snapshot(),...(op[0]==='send'?{bonus}:{} )})));
 }
 return {rows,base_hp:base,snapshots};
}
try{process.stdout.write(JSON.stringify(p.cases.map(world)))}catch(error){process.stderr.write(error.stack);process.exitCode=1}
'''


def modeled(case, original):
    loop = TimerLoop()
    events = []
    clock = SummonClock(loop, tuple(Wave(*row) for row in original['rows']),
                        base_hp=original['base_hp'], roast_floor=case.get('roast_floor', 0),
                        cycle_length=case.get('cycle_length', len(original['rows'])),
                        on_spawn=lambda wave, row: events.append([wave, list(astuple(row)), clock.pending_hp]))
    for name in ('wave', 'countdown', 'pending_hp', 'reached', 'roast', 'credited'):
        if name in case:
            setattr(clock, name, case[name])
    snapshots = []
    for op in case['operations']:
        bonus = None
        if op[0] == 'second':
            clock.advance_second()
        elif op[0] == 'tenth':
            clock.advance_tenth()
        elif op[0] == 'run':
            loop.run_until(op[1])
        elif op[0] == 'send':
            bonus = clock.send()
        elif op[0] == 'draw':
            clock.draw(op[1], lives=op[2], menu_open=op[3])
            snapshots.append(dict(credited=clock.credited, countdown=clock.countdown))
            continue
        row = {key:getattr(clock, key) for key in ('wave', 'countdown', 'roast', 'pending_hp', 'reached', 'credited')}
        row.update(queues=[[q.wave,q.remaining,q.interval,q.countdown] for q in clock.queues], events=events)
        if op[0] == 'send':
            row['bonus'] = bonus
        snapshots.append(json.loads(json.dumps(row)))
    return snapshots


def check(path):
    payload = source_parts(load('client_source').source_from_asar(path))
    inputs = cases()
    payload['cases'] = inputs
    run = subprocess.run(['node', '-e', SCRIPT], input=json.dumps(payload), text=True,
                         capture_output=True, timeout=30)
    if run.returncode:
        raise RuntimeError(run.stderr)
    # Integer-looking JSON tokens still represent client double values.
    originals = json.loads(run.stdout, parse_int=float)
    for case, original in zip(inputs, originals):
        actual = modeled(case, original)
        if actual != original['snapshots']:
            for index, (got, expected) in enumerate(zip(actual, original['snapshots'])):
                if got != expected:
                    raise AssertionError(f"{case['name']} operation {index}: {got} != {expected}")
    return len(inputs)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar', type=Path, required=True)
    args = parser.parse_args()
    print(f'{check(args.asar)} summon control scenarios match original helper/HUD execution.')
