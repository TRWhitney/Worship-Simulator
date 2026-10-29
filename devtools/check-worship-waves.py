"""Compare wave scheduling with original installed actor340 callbacks.

Physical enemy creation, UI and unrelated skill services are stubbed. Original
wave, send, spawn-queue and timer methods execute unchanged. Combat and layout
quality are outside this check.
"""
import argparse
from dataclasses import astuple
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from worship_sim.simulation import TimerLoop
from worship_sim.waves import Wave, WaveTimeline, next_wave_countdown, resolve_wave, send_bonus


def load_check(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_parts(source):
    formulas = load_check('client_source')
    timers = load_check('check-worship-simulation').source_parts(source)
    registry = 'A["scripts.ActorEvents_340"]='
    reg = source.find(registry)
    if reg < 0:
        raise ValueError('Original worship actor registry is unavailable.')
    owner = re.match(r'[A-Za-z_$][\w$]*', source[reg + len(registry):])[0]
    prototype = source.find(owner + '.prototype=', reg)
    if prototype < 0:
        raise ValueError('Original worship actor prototype is unavailable.')
    def method(name, following):
        marker = name + ':function('
        start = source.find(marker, prototype)
        end = source.find('},' + following + ':', start)
        if min(start, end) < 0:
            raise ValueError('Original worship callback boundaries changed: ' + name)
        return source[start + len(name) + 1:end + 1]
    timers.update(tenth=method('_event_01sec', '_event_Trapping'),
                  second=method('_event_1sec', '_event_10sec'),
                  helper=method('_customEvent_WorshipStuff', '_customEvent_TrapStuff'),
                  send=method('_event_3', '_event_4'))
    for name in ('WorshipInfo', '_customBlock_WorshipStuff', '_customBlock_2inputs'):
        _, timers[name] = formulas.function(source, name)
    # The modeled order must remain the actual initialization order.
    start = source.find('init:function(', prototype)
    a = source.find('c.runPeriodically(100,w(this,this._event_01sec),this.actor)', start)
    b = source.find('c.runPeriodically(1e3,w(this,this._event_1sec),this.actor)', start)
    if not start < a < b:
        raise ValueError('Original worship timer registration order changed.')
    return timers


SCRIPT = r'''
const vm=require('node:vm'),d=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
function create(rows,cycle=30){
 const engine={tasks:[],isPaused:()=>false,addTask(task){this.tasks.push(task)},gameAttributes:{h:{}}};
 const attrs={CurrentMap:26,CustomLists:{h:{WorshipInfo:[rows,rows,rows],WorshipBASEinfos:[[3],[3],[3]],PrayerInfo:[]}},
  CustomMaps:{h:{WorshipMapType:{h:{26:2}}}},PixelHelperActor:[],Refinery:[[-3]],OptionsList:Array(19).fill(0),
  NodeX:[0],NodeLength:[400]};
 engine.getGameAttribute=k=>attrs[k];
 const actor={isAlive:()=>true,isPaused:()=>false};
 const self={actor,wrapper:{enabled:true},_GenINFO:Array(91).fill(0),_UIinventoryOn8:[],_UIinventory8:[],_customEvent_RefineryStuff(){}};
 const g=self._GenINFO;Object.assign(g,{8:0,13:6,16:[0],17:[0],23:[20,20],24:Array(6).fill(1),27:'Blank',51:0,53:0,54:[],56:[],62:cycle,64:-1,74:0,88:0});
 self._UIinventoryOn8[46]=Array(30).fill(0);
 attrs.PixelHelperActor[7]={behaviors:{getBehavior:()=>self}};
 const events=[];let now=0;const created={setFilter(){}};
 const ctx={a:{engine,STEP_SIZE:10},c:{engine,asNumber:x=>x==null?0:Number(x),getActorType:x=>x,getActorsOfType:()=>[],
  getLastCreatedActor:()=>created,createHueFilter:()=>0,createSaturationFilter:()=>0,setFilterForImage(){},createBrightnessFilter:()=>0,clearFiltersForImage(){}},
  A:{},ka:{},n:{__cast:x=>x},h:{string:String},y:{replace:(s,a,b)=>s.split(a).join(b)},
  u:{deepCopyList:x=>JSON.parse(JSON.stringify(x))},p:{},q:{_customBlock_MenagerieStuff:()=>0,
   _customBlock_IsXYmouseWithinBounds:(a,b,c,d)=>Number(a===155&&b===215&&c===0&&d===57)},
  ba:{remove:(xs,x)=>{const i=xs.indexOf(x);if(i>=0)xs.splice(i,1)}},
  k:{_customBlock_AddStatusToMonster(){},_customBlock_CreateMonster(){events.push([now,self._DummyNumber,self._DummyList.slice()])}}};
 vm.createContext(ctx);vm.runInContext(d.constructor+d.prototype+d.registration+d._customBlock_WorshipStuff+d._customBlock_2inputs,ctx,{timeout:2000});
 const phase=vm.runInContext('(function(){var n,t;'+d.phase+'})',ctx,{timeout:2000});
 self._customEvent_WorshipStuff=vm.runInContext('('+d.helper+')',ctx,{timeout:2000});
 const tenth=vm.runInContext('('+d.tenth+')',ctx,{timeout:2000}).bind(self),second=vm.runInContext('('+d.second+')',ctx,{timeout:2000}).bind(self),send=vm.runInContext('('+d.send+')',ctx,{timeout:2000}).bind(self);
 ctx.c.runPeriodically(100,tenth,actor);ctx.c.runPeriodically(1000,second,actor);
 return {ctx,self,events,runTo(end){while(now<end){now+=10;phase.call(engine)}},send(){let before=g[51],enabled=g[13]<999;send();return enabled?g[51]-before:null},
  snapshot(){return [g[8],g[13],JSON.parse(JSON.stringify(g[54]))]},spawn(wave){self._TRIGGEREDtext='f'+wave;self._customEvent_WorshipStuff()}};
}
const rows=[[2,0,2,0],[1,1,3,2]],results=[];
for(const sends of [[],[7100,11100]]){
 const world=create(rows,2),bonuses=[],states=[];for(const at of [6000,7000,7100,8000,8100,10600,11100,12000,12100,16900,18000]){
  world.runTo(at);if(sends.includes(at))bonuses.push([at,world.send()]);
  states.push([at,world.snapshot()]);
 }results.push([world.events,bonuses,states]);
}
const button=[];for(const [wave,countdown] of [[0,6],[1,15],[9,20],[10,9999],[10,999],[10,998],[10,2],[201,120],[1500,998]]){
 const world=create(rows,2);world.self._GenINFO[8]=wave;world.self._GenINFO[13]=countdown;
 button.push([world.send(),world.self._GenINFO[13]]);
}results.push(button);
const tableWorld=create(rows,2),tableCtx=tableWorld.ctx;tableCtx.ja={};vm.runInContext(d.WorshipInfo,tableCtx,{timeout:2000});
const actualTables=tableCtx.ja.WorshipInfo(),resolved=[];
for(const table of [[[2,0,2,0],[3,1,3,2]],...actualTables]){
 const cycle=table.length===2?2:30,world=create(table,cycle),selected=[];
 for(const index of [0,1,2,3,29,30,31,60,94,250]){world.spawn(index+1);selected.push(world.events.at(-1)[2])}
 resolved.push(selected);
}results.push(resolved);
const countdownWorld=create(rows,2);results.push([0,1,5,10,11,199,200,201].map(w=>countdownWorld.ctx.p._customBlock_WorshipStuff('NextWaveCountdown',w)));
process.stdout.write(JSON.stringify({results,tables:actualTables}));
'''


def modeled_cases(tables):
    results = []
    waves = (Wave(2, 0, 2, 0), Wave(1, 1, 3, 2))
    for sends in ((), (7100, 11100)):
        loop = TimerLoop()
        events, bonuses, states = [], [], []
        timeline = WaveTimeline(loop, waves, cycle_length=2,
                                on_spawn=lambda wave, row: events.append([loop.now_ms, wave, list(astuple(row))]))
        for at in (6000, 7000, 7100, 8000, 8100, 10600, 11100, 12000, 12100, 16900, 18000):
            loop.run_until(at)
            if at in sends:
                bonuses.append([at, timeline.send()])
            queues = [[q.wave, q.remaining, q.interval, q.countdown] for q in timeline.queues]
            states.append([at, [timeline.wave, timeline.countdown, queues]])
        results.append([events, bonuses, states])
    buttons = []
    for wave, countdown in ((0, 6), (1, 15), (9, 20), (10, 9999), (10, 999),
                            (10, 998), (10, 2), (201, 120), (1500, 998)):
        bonus = send_bonus(wave, countdown)
        buttons.append([bonus, countdown if bonus is None else 0])
    results.append(buttons)
    results.append([[list(astuple(resolve_wave(tuple(Wave(*row) for row in table), index,
                                               cycle_length=2 if len(table) == 2 else 30)))
                     for index in (0, 1, 2, 3, 29, 30, 31, 60, 94, 250)]
                    for table in ([[2, 0, 2, 0], [3, 1, 3, 2]], *tables)])
    results.append([next_wave_countdown(w) for w in (0, 1, 5, 10, 11, 199, 200, 201)])
    return results


def check(path):
    source = load_check('client_source').source_from_asar(path)
    run = subprocess.run(['node', '-e', SCRIPT], input=json.dumps(source_parts(source)),
                         text=True, capture_output=True, check=True, timeout=20)
    original = json.loads(run.stdout)
    modeled = modeled_cases(original['tables'])
    if modeled != original['results']:
        raise AssertionError({'model': modeled, 'original': original['results']})
    return len(modeled)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar', type=Path, required=True)
    args = parser.parse_args()
    try:
        count = check(args.asar)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr[-1500:])
    print(f'{count} wave scheduling groups match the original client. Combat remains unverified.')
