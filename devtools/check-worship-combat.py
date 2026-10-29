"""Check selected original worship projectile events on synthetic actors.

This is a mechanics oracle for simulator development. It does not validate
layout rankings, physical movement, complete battles, or achieved waves.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess


def projectile_init(source):
    registry='A["scripts.ActorEvents_478"]='
    start=source.find(registry)
    if start<0:
        raise ValueError('The worship projectile behavior is missing.')
    match=re.match(r'[A-Za-z_$][\w$]*',source[start+len(registry):])
    if match is None:
        raise ValueError('The worship projectile registry changed.')
    owner=match[0]
    start=source.find(owner+'.prototype=',start)
    end=source.find('__class__:'+owner,start)
    if start<0 or end<start:
        raise ValueError('The worship projectile behavior boundary changed.')
    behavior=source[start:end]
    start=behavior.find('init:function')
    end=behavior.find('},forwardMessage',start)
    if start<0 or end<start:
        raise ValueError('The worship projectile initialization changed.')
    return behavior[start+len('init:'):end+1]


def check(path):
    spec=importlib.util.spec_from_file_location('client_check',Path(__file__).with_name('client_source.py'))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source=module.source_from_asar(path)
    initialization=projectile_init(source)
    spec=importlib.util.spec_from_file_location('target_check',Path(__file__).with_name('check-worship-targeting.py'))
    target=importlib.util.module_from_spec(spec);spec.loader.exec_module(target)
    parts=target.source_parts(source)
    payload=json.dumps({'initialization':initialization,'distance':parts['distance'],'hitscan':parts['hitscan']})
    run=subprocess.run(['node','-e',SCRIPT],input=payload,text=True,capture_output=True,check=True,timeout=15)
    return json.loads(run.stdout)['checks']


SCRIPT=r'''const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const parts=JSON.parse(fs.readFileSync(0,'utf8')),init=parts.initialization;
let attrs,periodic,later,hits,statuses,monsters,ctx;
function mob(x,node=0,hp=100,velocity=7){
 const script={_IsWorshipMob:1,_MonsterNODE:node,_MonsterID:monsters.length,_SizeMulti:1,_PetStatus:0,_MonsterType:'synthetic'};
 const m={x,node,velocity,script,getX(){return this.x},moveBy(dx,dy,seconds){this.lastMove={dx,dy,seconds}},getXCenter(){return this.x},getYCenter(){return 0},getXVelocity(){return this.velocity},setXVelocity(v){this.velocity=v},clearFilters(){},setFilter(){},behaviors:{getBehavior:()=>script}};
 monsters.push(m);attrs.MonsterHP.push(hp);attrs.MonsterAlive.push(1);return m;
}
function reset(){
 periodic=[];later=[];hits=[];statuses=[];monsters=[];
 attrs={CurrentMap:26,MapMonstersList:monsters,MonsterHP:[],MonsterAlive:[0],MonsterDefinitionsGET:{h:{synthetic:{h:{Type:'Monster'}}}},WeaponType:6,DummyList:[],PixelHelperActor:Array(8).fill({behaviors:{getBehavior:()=>({_GenINFO:Array(9).fill(0)})}})};
 ctx={a:{engine:{getGameAttribute:k=>attrs[k],gameAttributes:{h:attrs}}},c:{engine:{getLayerByName:()=>0},asNumber:x=>x==null?0:Number(x),runPeriodically:(ms,f)=>periodic.push({ms,f}),runLater:(ms,f)=>later.push({ms,f}),randomInt:(low,high)=>high,recycleActor(){}},n:{__cast:x=>x},B:{},ka:{},p:{_customBlock_WorshipStuff:()=>1.5},ba:{remove:(list,item)=>{const i=list.indexOf(item);if(i>=0)list.splice(i,1)}},k:{_customBlock_AddStatusToMonster:(name,m,seconds)=>statuses.push({name,id:m.script._MonsterID,seconds}),_customBlock_CreateDmgPixel:(_,m)=>hits.push(m.script._MonsterID)},q:{},t:{linear:0},w:(self,f)=>f.bind(self),h:{string:String}};
 vm.createContext(ctx);
 ctx.k._customBlock_DistanceEqn=vm.runInContext('('+parts.distance+')',ctx);
 ctx.q._customBlock_Hitscanning=vm.runInContext('('+parts.hitscan+')',ctx);
 ctx.init=vm.runInContext('('+init+')',ctx,{timeout:2000});
}
function cast(type,data,x=100){
 attrs.WeaponType=type;attrs.DummyList=data;
 const actor={lastMove:null,getX:()=>x,getXVelocity:()=>3,setXVelocity(){},setX(){},moveBy(dx,dy,seconds){this.lastMove={dx,dy,seconds}},getAnimation:()=>String(type),getXCenter:()=>x,getYCenter:()=>0,setAnimation(){},makeAlwaysSimulate(){},moveToLayer(){},growTo(){},fadeTo(){}};
 const self={actor,_event_01(){}};ctx.init.call(self);return self;
}
reset();mob(155);mob(158);mob(100,1);mob(100,0,0);
cast(6,[10,0,20,2,0]);assert.equal(periodic[0].ms,2000);periodic[0].f();assert.deepEqual(hits,[0]);assert.equal(later[0].ms,20000);
reset();const enemy=mob(100);cast(3,[0,0,0,0,100]);assert.equal(enemy.velocity,3);cast(3,[0,0,0,0,100]);assert.equal(enemy.velocity,1);assert.equal(statuses[0].seconds,6);
reset();const slow=mob(100);cast(3,[0,15,2,0,100]);assert.equal(slow.velocity,2);assert.equal(statuses[0].seconds,8);
reset();mob(100);cast(6,[10,0,10,2/1.3,0]);assert.equal(periodic[0].ms,1000*2/1.3);
reset();const k0=mob(100);const a=cast(5,[10,100,2,0,1,[],10]);periodic.find(t=>t.ms===200).f();assert.equal(a._Plist[2],1);assert.equal(k0.lastMove.dx,50);
reset();const k1=mob(100);const b=cast(5,[10,100,27,0,1,[],10]);periodic.find(t=>t.ms===200).f();assert.equal(b._Plist[2],26);assert.equal(k1.lastMove.dx,50);
process.stdout.write(JSON.stringify({checks:13}));
'''

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar',type=Path,required=True)
    args=parser.parse_args()
    print(f'{check(args.asar)} original-client projectile checks passed. Full battles remain unverified.')
