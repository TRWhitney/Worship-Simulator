"""Compare complete-board statistics with the installed client's original functions."""
import argparse
from dataclasses import asdict
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from worship_sim.models import COEFFICIENTS, TRAITS, Tower, Board
from worship_sim.board import board_stats


def fixtures():
    cases=[]

    def add(name,towers,atom=0,**account):
        state=Board(True,towers=tuple(towers),**account)
        cases.append((name,state,atom))

    add('empty',[])
    for construction in (1,25,200):
        for kind in range(9):
            for level,choices in ((1,''),(5,'A'),(10,'BA'),(100,'AB'*10)):
                for double in (False,True):
                    add(f'single-{kind}-{level}-{construction}-{double}',
                        [Tower(kind,0,0,0,level,choices)],
                        construction=(construction,)*9,double_first=double)
    mixed=(Tower(0,0,0,0,10,'AB'),Tower(5,0,100,0,10,'AB'),
           Tower(4,0,200,0,10,'BA'),Tower(8,0,1000,0,10,'BA'))
    add('mixed',mixed)
    construction=[1]*9
    for kind,level in ((0,7),(4,8),(5,4),(8,9)):
        construction[kind]=level
    add('mixed-account',mixed,37,construction=tuple(construction),
        double_first=True,roast_level=2,roast=25)
    for double in (False,True):
        add(f'all-kinds-{double}',
            [Tower(kind,0,kind*65,kind%2*100,10,'AB' if kind%2 else 'BA')
             for kind in range(9)],37,construction=(25,)*9,
            double_first=double,roast_level=2,roast=25)
    add('globals-out-of-range',[Tower(0,0,0,0,5,'A'),
        Tower(5,0,10000,0,5,'B'),Tower(8,0,20000,0,5,'B')])
    add('doubled-choice-order',[Tower(5,0,0,0,10,'BA'),
        Tower(5,0,100,0,10,'AB')],double_first=True)
    bound=260/.9604339
    add('strict-party-boundary',[Tower(5,0,0,0,10,'A'),
        Tower(0,0,190,190,10),Tower(0,0,bound,0,10),
        Tower(0,0,bound-1e-7,0,10),Tower(0,0,bound+1e-7,0,10)])
    storm_bound=348/.9604339
    add('strict-storm-boundary',[Tower(4,0,0,0,10,'B'),
        Tower(0,0,storm_bound,0,10),Tower(0,0,storm_bound-1e-7,0,10)])
    add('before-account-floor',[Tower(0,0,0,0,10)],35)
    add('negative-roast',[Tower(0,0,0,0,5,'A')],37,roast_level=2,roast=-10)
    add('current-roast-before-future-floor',[Tower(0,0,0,0,10)],37,
        roast_level=2,roast=0,roast_floor=1000)
    add('large-fractional-damage',[Tower(0,0,0,0,100,'A'*20)],1e8,
        construction=(1000,)*9,roast_level=100,roast=1000)
    for construction,level in ((3,43),(5,8),(21,68)):
        add(f'kraken-expression-{construction}-{level}',
            [Tower(6,0,0,0,level)],construction=(construction,)*9)
    add('zero-client-cooldown',[Tower(6,0,0,0,10)],construction=(1000000,)*9)
    add('normalized-after-upgrade',[Tower(0,0,0,0,2),Tower(5,0,100,0,5,'A')])
    return cases


SCRIPT=r'''
const fs=require('node:fs'),vm=require('node:vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
let atom=0,double=false;
const actor={_GenINFO:[],_TRIGGEREDtext:'z'};
const attrs={CustomLists:{h:{}},DNSM:{h:{}},TowerInfo:Array(30).fill(1),Dream:Array(8).fill(0),PixelHelperActor:Array(8).fill(null)};
attrs.PixelHelperActor[7]={behaviors:{getBehavior:key=>{
 if(key!=='ActorEvents_340')throw Error('Unexpected actor '+key);return actor;
}}};
const ctx={actor,a:{engine:{getGameAttribute:key=>attrs[key]}},c:{},p:{},k:{},
 m:{_customBlock_AtomCollider:(key,index,zero)=>{
  if(key!=='AtomBonuses'||index!==5||zero!==0)throw Error('Unexpected Atom lookup');return atom;
 }},q:{_customBlock_MenagerieStuff:(key,index,zero)=>{
  if(key!=='UnlockOwned'||index!==18||zero!==0)throw Error('Unexpected Menagerie lookup');return double?1:0;
 }},l:class{constructor(){this.h={}}},h:{string:String},n:{__cast:value=>value},
 ka:{},Tu:{},Di:{},Uu:{}};
for(const owner of input.owners)ctx[owner]??={};
vm.createContext(ctx);vm.runInContext(input.code,ctx,{timeout:3000});
attrs.CustomLists.h.TDtraits=ctx[input.traitsOwner].TDtraits();
attrs.CustomLists.h.TowerInfo=ctx[input.towerOwner].TowerInfo();
const cases=[];
for(const fixture of input.cases){
 atom=fixture.atom;double=fixture.double_first;
 attrs.Dream[7]=fixture.roast_level;actor._GenINFO[85]=fixture.roast;
 attrs.TowerInfo.fill(1);fixture.construction.forEach((value,kind)=>attrs.TowerInfo[9+kind]=value);
 actor._GenINFO[56]=fixture.towers.map(t=>[t.kind,t.node,t.x,0,0,t.level,
  {getXCenter:()=>t.x,getYCenter:()=>t.y},null,999,t.choices,{h:{0:999,9:999}},0]);
 const read=()=>actor._GenINFO[56].map(t=>({
  bonuses:Array.from({length:10},(_,slot)=>ctx.c.asNumber(t[10].h[slot])),
  damage:ctx.p._customBlock_TowerStats('damage',t[0],t[5]),
  base_cooldown:ctx.p._customBlock_TowerStats('atkcd',t[0],t[5]),cooldown:t[8],
  radius:ctx.p._customBlock_TowerStats('range',t[0],t[5]),
  cost:ctx.p._customBlock_TowerStats('cost',t[0],t[5])}));
 actor._customEvent_WorshipStuff();const first=read();
 actor._customEvent_WorshipStuff();
 if(JSON.stringify(first)!==JSON.stringify(read()))throw Error('Non-idempotent recomputation '+fixture.name);
 cases.push(first);
}
process.stdout.write(JSON.stringify({cases,
 coefficients:attrs.CustomLists.h.TowerInfo.slice(9,18).map(row=>[Number(row[2]),Number(row[3])]),
 traits:attrs.CustomLists.h.TDtraits.map(row=>[Number(row[2]),Number(row[1]),Number(row[5]),Number(row[4])])}));
'''


def check(path):
    spec=importlib.util.spec_from_file_location('client_check',Path(__file__).with_name('client_source.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source=module.source_from_asar(path)
    names=('TDtraits','TowerInfo','asNumber','_customBlock_TowerStats',
           '_customBlock_Tower2Stats','_customBlock_WorshipStuff','_customBlock_DistanceEqn')
    functions=[module.function(source,name) for name in names]
    marker='_customEvent_WorshipStuff:function('
    start=source.find(marker)
    end=source.find('},_customEvent_',start)
    if start<0 or end<0:
        raise ValueError('Missing original worship event boundary')
    event='actor._customEvent_WorshipStuff='+source[start:end+1].split(':',1)[1]+';'
    cases=fixtures()
    payload={'code':''.join(code for _,code in functions)+event,
             'owners':[owner for owner,_ in functions],
             'traitsOwner':functions[0][0],'towerOwner':functions[1][0],
             'cases':[dict(name=name,atom=atom,towers=[asdict(t) for t in state.towers],
                           construction=state.construction,double_first=state.double_first,
                           roast=state.roast,roast_level=state.roast_level)
                      for name,state,atom in cases]}
    run=subprocess.run(['node','-e',SCRIPT],input=json.dumps(payload),text=True,
                       capture_output=True,check=True,timeout=30)
    data=json.loads(run.stdout)
    if data['coefficients']!=[list(row) for row in COEFFICIENTS]:
        raise AssertionError('Original construction coefficients changed')
    if data['traits']!=[list(row) for row in TRAITS]:
        raise AssertionError('Original trait table changed')
    if len(data['cases'])!=len(cases):
        raise AssertionError('Original board result count differs')
    comparisons=0
    for (name,state,atom),expected in zip(cases,data['cases']):
        actual=board_stats(state,atom_bonus=atom)
        if len(actual)!=len(expected):
            raise AssertionError(f'{name}: tower count differs')
        for index,(got,want) in enumerate(zip(actual,expected)):
            if list(got.bonuses)!=want['bonuses']:
                raise AssertionError(f'{name} tower {index}: effective traits differ')
            for field in ('damage','base_cooldown','cooldown','radius','cost'):
                value=getattr(got,field)
                target=want[field]
                # JSON serializes client Number costs above the exact-integer range
                # with a rounded decimal spelling, unlike Python's integer floor.
                exact=(field=='radius' or (field=='cost' and target<=2**53)
                       or (field=='damage' and target<1e9))
                if (value!=target if exact else
                        not math.isclose(value,target,rel_tol=1e-12,abs_tol=1e-12)):
                    raise AssertionError(f'{name} tower {index} {field}: overlay {value}, client {target}')
            comparisons+=1
    return len(cases),comparisons


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar',type=Path,required=True)
    args=parser.parse_args()
    try:
        boards,towers=check(args.asar)
        print(f'{boards} original-client boards and {towers} tower rows matched.')
    except (AssertionError,ValueError,OSError,subprocess.SubprocessError) as error:
        if isinstance(error,subprocess.CalledProcessError):
            print(error.stderr[-1000:],file=sys.stderr)
        raise SystemExit(str(error))
