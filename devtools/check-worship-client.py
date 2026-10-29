"""Compare worship tower formulas with the installed client in an isolated VM."""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from worship_sim.models import stats, build_cost, COEFFICIENTS


def check(path):
    spec=importlib.util.spec_from_file_location('client_check',Path(__file__).with_name('client_source.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source=module.source_from_asar(path)
    def function(name):
        i=source.find('.'+name+'=function(')
        if i<0:raise ValueError('Missing client function '+name)
        start=i
        while start>0 and (source[start-1].isalnum() or source[start-1] in '_$'):start-=1
        owner=source[start:i];end=source.find('},'+owner+'.',i)
        if end<0:raise ValueError('Unsupported client function boundary')
        return source[start:end+1]+';'
    functions=''.join(function(n) for n in ('TowerInfo','_customBlock_TowerStats','_customBlock_Tower2Stats','_customBlock_WorshipStuff'))
    match=re.search(r'(\w+)\.TowerInfo=function',functions)
    script=r'''
const fs=require('node:fs'),vm=require('node:vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
const w={_GenINFO:Array(91).fill(0)},attrs={DNSM:{h:{}},Dream:Array(8).fill(0),TowerInfo:Array(30).fill(1),CustomLists:{h:{}},PixelHelperActor:Array(8).fill({behaviors:{getBehavior:()=>w}})};
w._GenINFO[56]=[[0,0,0,0,0,0,0,0,0,0,{h:{9:0}}]];
const ctx={a:{engine:{getGameAttribute:k=>attrs[k]}},c:{asNumber:x=>x==null?0:Number(x)},n:{__cast:x=>x},ka:{},p:{},m:{_customBlock_AtomCollider:()=>0},na:{}};
ctx[input.owner]??={};vm.createContext(ctx);vm.runInContext(input.functions,ctx,{timeout:3000});
attrs.CustomLists.h.TowerInfo=ctx[input.owner].TowerInfo();const cases=[];
for(const construction of [1,25,200])for(let kind=0;kind<9;kind++)for(const level of [1,4,5,10,25,50]){
attrs.TowerInfo.fill(construction);cases.push({construction,kind,level,values:['cost','damage','atkcd','range'].map(k=>ctx.p._customBlock_TowerStats(k,kind,level))});}
const builds=[];for(let kind=0;kind<9;kind++)for(let count=0;count<20;count++){
w._GenINFO[56]=Array(count).fill(0);builds.push({kind,count,value:ctx.p._customBlock_WorshipStuff('NewTowerCost',kind)});}
process.stdout.write(JSON.stringify({cases,builds}));
'''
    run=subprocess.run(['node','-e',script],input=json.dumps({'owner':match[1],'functions':functions}),text=True,capture_output=True,check=True,timeout=15)
    data=json.loads(run.stdout)
    for case in data['cases']:
        actual=stats(case['kind'],case['level'],case['construction'],COEFFICIENTS[case['kind']])
        for got,want in zip(actual,case['values']):
            if not math.isclose(got,want,rel_tol=1e-12,abs_tol=1e-12):raise AssertionError((case,actual))
    for case in data['builds']:
        if build_cost(case['kind'],case['count'])!=case['value']:raise AssertionError(case)
    return len(data['cases'])*4+len(data['builds'])

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--asar',type=Path,required=True)
    args=parser.parse_args()
    print(f'{check(args.asar)} original-client worship formula comparisons passed.')
