"""Compare Wizard target acquisition with original installed client execution.

The original Wizard event and Hitscanning helper run on synthetic actors.
Boulder casts are rejected by a different tower node after target selection.
This checks acquisition only, not successful casts or battle outcomes.
"""
import argparse
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from worship_sim.simulation import Combatant
from worship_sim.targeting import select_target


def source_parts(source):
    registry = 'A["scripts.ActorEvents_358"]='
    registration = source.find(registry)
    if registration < 0:
        raise ValueError('The original Wizard behavior is missing.')
    match = re.match(r'[A-Za-z_$][\w$]*', source[registration+len(registry):])
    if match is None:
        raise ValueError('The original Wizard behavior registry changed.')
    owner = match[0]
    prototype = source.find(owner+'.prototype=', registration)
    start = source.find('_event_01sec:function', prototype)
    end = source.find('},_event_01secsailing:', start)
    boundary = source.find('__class__:'+owner, prototype)
    if min(prototype, start, end, boundary) < 0 or end > boundary:
        raise ValueError('The original Wizard event boundary changed.')
    event = source[start+len('_event_01sec:'):end+1]
    start = source.find('._customBlock_Hitscanning=function')
    end = source.find('},', start)
    if start < 0 or end < start:
        raise ValueError('The original Hitscanning helper boundary changed.')
    hitscan = source[start+len('._customBlock_Hitscanning='):end+1]
    start = source.find('._customBlock_DistanceEqn=function')
    end = source.find('},', start)
    if start < 0 or end < start:
        raise ValueError('The original distance helper boundary changed.')
    distance = source[start+len('._customBlock_DistanceEqn='):end+1]
    return dict(event=event, hitscan=hitscan, distance=distance)


def scenarios():
    def case(name, enemies, **kwargs):
        data = dict(x=100, y=100, radius=200, route=[0, 1], directions=[1, -1], map_id=0)
        data.update(kwargs)
        data['name'] = name
        data['enemies'] = [asdict(Combatant(i, **enemy)) for i, enemy in enumerate(enemies)]
        return data

    def enemy(node=0, x=100, y=100, hp=100, **kwargs):
        return dict(node=node, x=x, y=y, hp=hp, **kwargs)

    cases = [
        case('route progress then reversed x', [enemy(x=180), enemy(node=1, x=180), enemy(node=1, x=90)]),
        case('first list tie', [enemy(x=150), enemy(x=150)]),
        case('approximate horizontal distance', [enemy(node=1, x=300)]),
        case('strict approximate boundary', [enemy(node=1, x=300)], radius=192.08678),
        case('empty wave', []),
        case('rightward x', [enemy(x=120), enemy(x=180)]),
        case('leftward x', [enemy(node=1, x=180), enemy(node=1, x=120)]),
        case('route progress before distance', [enemy(x=100), enemy(node=1, x=220)]),
        case('diagonal approximate distance', [enemy(node=1, x=220, y=260), enemy(x=110)]),
        case('inside approximate distance', [enemy(node=1, x=220, y=259), enemy(x=110)]),
        case('map216 below cutoff', [enemy(y=951)], map_id=216, y=950),
        case('map216 cutoff included', [enemy(y=950)], map_id=216, y=950),
        case('other map below cutoff', [enemy(y=951)], map_id=26, y=950),
        case('unknown nodes compare leftward', [enemy(node=9, x=120), enemy(node=8, x=80)]),
        case('known node precedes unknown', [enemy(node=9, x=180), enemy(x=100)]),
    ]
    for name, fields in [('not worship', dict(worship=False)), ('not alive', dict(alive=False)),
                         ('zero hp', dict(hp=0)), ('negative hp', dict(hp=-10)),
                         ('pet', dict(pet_status=1)), ('nonmonster type', dict(monster_type='Boss'))]:
        cases.append(case(name, [enemy(node=1, **fields), enemy(x=120)]))
    return cases


SCRIPT = r'''
const fs=require('node:fs'),vm=require('node:vm'),parts=JSON.parse(fs.readFileSync(0,'utf8'));
const results=[];
for(const input of parts.cases){
 const monsters=input.enemies.map((m,i)=>({
  getXCenter:()=>m.x,getYCenter:()=>m.y,
  behaviors:{getBehavior:()=>({_IsWorshipMob:Number(m.worship),_MonsterNODE:m.node,
   _MonsterID:i,_PetStatus:m.pet_status,_MonsterType:String(i)})},id:m.id
 }));
 const row=Array(11).fill(0);row[1]=-9999;row[5]=1;
 const gen=Array(57).fill(0);gen[56]=[row];
 const definitions={h:{}};
 input.enemies.forEach((m,i)=>{definitions.h[String(i)]={h:{Type:m.monster_type}}});
 const attrs={CurrentMap:input.map_id,MapMonstersList:monsters,
  MonsterHP:input.enemies.map(m=>m.hp),MonsterAlive:[0,...input.enemies.map(m=>Number(m.alive))],
  MonsterDefinitionsGET:definitions,
  PixelHelperActor:Array(8).fill({behaviors:{getBehavior:()=>({_GenINFO:gen})}}),
  CustomLists:{h:{WorshipNODESnETC:[[input.route,input.directions.map(d=>d===1?0:1)]]}}
 };
 const ctx={a:{engine:{getGameAttribute:k=>attrs[k],gameAttributes:{h:attrs}}},
  c:{asNumber:x=>x==null?0:Number(x)},n:{__cast:x=>x},B:{},ka:{},rc:{},q:{},
  p:{_customBlock_WorshipStuff:(name)=>{
   if(name!=='TrialType')throw Error('Unexpected worship query '+name);return 0
  },_customBlock_TowerStats:(name)=>{
   if(name!=='range')throw Error('Unexpected tower query '+name);return input.radius
  }},k:{}
 };
 vm.createContext(ctx);
 ctx.k._customBlock_DistanceEqn=vm.runInContext('('+parts.distance+')',ctx,{timeout:2000});
 ctx.q._customBlock_Hitscanning=vm.runInContext('('+parts.hitscan+')',ctx,{timeout:2000});
 const event=vm.runInContext('('+parts.event+')',ctx,{timeout:2000});
 let frame=34;
 const actor={getAnimation:()=>'Wizard',getCurrentFrame:()=>frame,
  setCurrentFrame:f=>{frame=f},getXCenter:()=>input.x,getYCenter:()=>input.y};
 const self={wrapper:{enabled:true},actor,_PersonalNUM:2,_PersonalLIST:[2,0]};
 event.call(self,0);
 if(frame!==34)throw Error('A cast unexpectedly succeeded');
 results.push(self._PersonalLIST[3]===0?null:self._PersonalLIST[2].id);
}
process.stdout.write(JSON.stringify(results));
'''


def check(path):
    spec = importlib.util.spec_from_file_location('client_check', Path(__file__).with_name('client_source.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parts = source_parts(module.source_from_asar(path))
    cases = scenarios()
    parts['cases'] = cases
    run = subprocess.run(['node', '-e', SCRIPT], input=json.dumps(parts), text=True,
                         capture_output=True, check=True, timeout=15)
    originals = json.loads(run.stdout)
    for case, original in zip(cases, originals, strict=True):
        args = {key: value for key, value in case.items() if key not in ('name', 'enemies')}
        selected = select_target([Combatant(**enemy) for enemy in case['enemies']], **args)
        actual = selected.id if selected is not None else None
        if actual != original:
            raise AssertionError(dict(scenario=case['name'], model=actual, original=original))
    return len(cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar', type=Path, required=True)
    args = parser.parse_args()
    print(f'{check(args.asar)} target-acquisition scenarios match the original client. Complete battles remain unverified.')
