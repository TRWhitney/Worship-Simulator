"""Compare per-hit worship damage with the original installed damage function.

Synthetic monsters have no unrelated combat statuses or account modifiers.
Non-worship account calculations and damage-number rendering are isolated;
unexpected service accesses fail. Death processing and battles are not checked.
"""
import argparse
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from worship_sim.damage import apply_hits
from worship_sim.simulation import Combatant


def damage_function(source):
    marker = '._customBlock_CreateDmgPixel='
    start = source.find(marker)
    following = source.find('._customBlock_AddStatusToMonster=', start)
    end = source.rfind('},', start, following)
    if min(start, following, end) < 0:
        raise ValueError('The original damage function boundary changed.')
    return source[start+len(marker):end+1]


def scenarios():
    def case(name, *, color=0, x=100, hp=100, velocity=7, width=40,
             counter=0, alive=True, damage=10, crit=1, hits=1, player=False):
        return dict(name=name,
                    enemy=asdict(Combatant(0, 0, x, hp, velocity=velocity,
                                          color=color, hit_counter=counter,
                                          width=width, alive=alive)),
                    args=dict(damage=damage, crit_multiplier=crit, hits=hits,
                              player=player, bounds=[0, 200]))

    cases = [case('round each hit and continue below zero', hp=25, damage=10.5, crit=1.5, hits=2),
             case('already nonliving actor', alive=False),
             case('zero hits', color=5, hits=0),
             case('half point rounds up', damage=.5),
             case('just below half does not round up', damage=.49999999999999994),
             case('zero critical multiplier', crit=0),
             case('unset critical multiplier sentinel', crit=-1)]
    for color in range(6):
        cases.append(case(f'color {color}', color=color, hp=25, x=180.4, hits=8))
        cases.append(case(f'player color {color}', color=color, hp=4, damage=1e12, hits=8, player=True))
    for counter in (-3, -1, 0, 1, 4, 5):
        for hits in (1, 2, 6, 8):
            cases.append(case(f'blue counter {counter} hits {hits}', color=2, counter=counter, hits=hits))
    for velocity in (-7, 0, 7):
        for x in (-20.5, 20.6, 180.4):
            for width in (40, 41):
                cases.append(case(f'orange velocity {velocity} x {x} width {width}',
                                  color=5, velocity=velocity, x=x, width=width, hits=4))
    cases.extend([case('zero-damage orange still moves', color=5, damage=0),
                  case('zero-damage blue counts hit', color=2, damage=0, counter=5),
                  case('fractional critical damage', damage=.5, crit=1.5, hits=3)])
    return cases


SCRIPT = r'''
const fs=require('node:fs'),vm=require('node:vm'),parts=JSON.parse(fs.readFileSync(0,'utf8'));
const results=[];
function services(name,allowed){
 return new Proxy(allowed,{get(target,key){
  if(Object.prototype.hasOwnProperty.call(target,key))return target[key];
  throw Error('Unexpected '+name+' service: '+String(key));
 }});
}
for(const input of parts.cases){
 const enemy=input.enemy,args=input.args,halfWidth=Math.floor(enemy.width/2);
 let center=enemy.x;
 const script={_PetStatus:0,_MonsterType:'synthetic',_MonsterID:0,
  _IsWorshipMob:1,_StatusList:[],_WorshipMOD:enemy.color,
  _PersNum:enemy.hit_counter,_MonsterNODE:0};
 const actor={alive:enemy.alive,
  behaviors:{getBehavior(name){if(name!=='ActorEvents_1')throw Error('Unexpected monster behavior');return script}},
  getX(){return Math.round(center-halfWidth)},getXVelocity:()=>enemy.velocity,
  setX(x){center=x+halfWidth},set_alpha(){}
 };
 const gen=Array(85).fill(0);gen[84]=1;
 const attrs={CustomLists:{h:{NonDMGLinemonsterTypes:[]}},
  MonsterDefinitionsGET:{h:{synthetic:{h:{Type:'Monster',DeathFrame:1,SpecialType:'',Defence:0}}}},
  MonsterHP:[enemy.hp],DummyList:[],dummyCritDmgMulti:args.crit_multiplier,
  DummyText:args.player?'player':'WorshipTowerDMG'+String(args.damage),
  CurrentMap:26,DNSM:{h:{}},QuestComplete:{h:{Royal_Worm5:1}},
  Tasks:[[0,[1e300]]],NodeX:[args.bounds[0]],NodeLength:[args.bounds[1]],
  PixelHelperActor:Array(8).fill({behaviors:{getBehavior(name){
   if(name!=='ActorEvents_340')throw Error('Unexpected helper behavior');return {_GenINFO:gen}
  }}})
 };
 const engine={gameAttributes:{h:attrs},getGameAttribute(name){
  if(!Object.prototype.hasOwnProperty.call(attrs,name))throw Error('Unexpected attribute '+name);
  return attrs[name];
 }};
 const ctx={a:{engine},n:{__cast:x=>x},B:{},ka:{},
  D:{contains:(xs,x)=>xs.includes(x)},h:{string:String},y:{replace:(s,from,to)=>s.split(from).join(to)},
  c:services('client',{asNumber:x=>x==null?0:Number(x),getCurrentSceneName:()=>'Acorn'}),
  p:services('worship',{_customBlock_Dungon:()=>-1}),
  m:services('account',{_customBlock_Windwalker:(name)=>{
   if(name!=='CompassTempest')throw Error('Unexpected Windwalker query');return 0
  }}),
  x:services('player',{_customBlock_DamageDealed:(name)=>{
   if(name!=='RNG')throw Error('Unexpected player damage query');return 0
  }}),
  k:services('damage',{}),q:services('map',{}),v:services('progress',{}),u:services('party',{})
 };
 vm.createContext(ctx);
 const damage=vm.runInContext('('+parts.damage+')',ctx,{timeout:2000});
 damage(args.hits,actor,[]);
 results.push({total:enemy.hp-attrs.MonsterHP[0],hp:attrs.MonsterHP[0],
  counter:script._PersNum,x:center,alive:actor.alive});
}
process.stdout.write(JSON.stringify(results));
'''


def check(path):
    spec = importlib.util.spec_from_file_location('client_check', Path(__file__).with_name('client_source.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    cases = scenarios()
    payload = dict(damage=damage_function(module.source_from_asar(path)), cases=cases)
    run = subprocess.run(['node', '-e', SCRIPT], input=json.dumps(payload), text=True,
                         capture_output=True, check=True, timeout=15)
    originals = json.loads(run.stdout)
    for case, original in zip(cases, originals, strict=True):
        enemy = Combatant(**case['enemy'])
        total = apply_hits(enemy, **case['args'])
        actual = dict(total=total, hp=enemy.hp, counter=enemy.hit_counter, x=enemy.x, alive=enemy.alive)
        if actual != original:
            raise AssertionError(dict(scenario=case['name'], model=actual, original=original))
    return len(cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar', type=Path, required=True)
    args = parser.parse_args()
    print(f'{check(args.asar)} per-hit damage scenarios match the original client. Complete battles remain unverified.')
