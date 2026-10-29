"""Compare purchases with original client input, placement and tower callbacks.

Runs original Actor340 press/release and Worship commands, Actor131 placement
click, full Actor358 initialization, and original tower/account tables. The host
supplies legal placement coordinates, image/actor services and an idle active
battle; no combat or graphics clocks run. This checks investment accounting,
ordered rows and upgrade cooldown writes, not layout legality or combat stats.
"""
import argparse
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from worship_sim.models import Tower,Board
from worship_sim.investments import Investment,invest


def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'devtools'/name)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def source_parts(source):
    client=load('client_source.py')
    parts=load('check-worship-waves.py').source_parts(source)
    parts['distance']=load('check-worship-targeting.py').source_parts(source)['distance']
    def method(number,name,following):
        registry=source.index('A["scripts.ActorEvents_'+str(number)+'"]=')
        start=source.index(name+':function',registry)+len(name)+1
        return source[start:source.index('},'+following+':',start)+1]
    parts['press']=method(340,'_event_press','_event_3')
    parts['placement']=method(131,'_event_Click','_event_Updating')
    for key in ('WorshipBASEinfos','WorshipMapType','TDtraits','TowerInfo',
                '_customBlock_TowerStats','_customBlock_Tower2Stats','WorshipNODESnETC'):
        owner,code=client.function(source,key);parts[key]=dict(owner=owner,code=code)
    marker='A["scripts.ActorEvents_358"]='
    registry=source.index(marker)
    owner=re.match(r'[A-Za-z_$][\w$]*',source[registry+len(marker):])[0]
    start=source.rfind('var '+owner+'=function',0,registry)
    proto=source.index(owner+'.prototype=',registry)
    suffix=',__class__:'+owner+'});'
    end=source.index(suffix,proto)+len(suffix)
    parts['baseclass']=dict(owner=owner,code=source[start:registry]+source[proto:end])
    return parts


def scenarios():
    def build(kind,x=100,node=0):
        return dict(kind='build',tower=dict(kind=kind,node=node,x=x,y=300,level=1,choices=''))
    def upgrade(index=0,**fields):return dict(kind='upgrade',index=index,**fields)
    def choose(choice,index=0):return dict(kind='choose',index=index,choice=choice)
    def sell(index=0):return dict(kind='sell',index=index)
    def seed(kind,level=1,choices='',x=100,refund=3):
        return dict(kind=kind,node=0,x=x,y=300,level=level,choices=choices,refund=refund)
    cases=[]
    for construction in (1,7,1000):
        for kind in range(9):
            actions=[build(kind)]
            for level in range(1,12):
                if level%5==0:
                    actions.extend((upgrade(),choose('A' if level==5 else 'B')))
                actions.append(upgrade())
            actions.extend((sell(),build((kind+1)%9,200),sell()))
            cases.append(dict(name=f'kind {kind} construction {construction}',points=1e20,
                              construction=[construction]*9,towers=[],actions=actions))
    cases.append(dict(name='ordered mixed rows and pending choice on another row',points=1e12,
        towers=[seed(0,5,x=100,refund=94),seed(5,10,'A',200,250),seed(7,1,x=300,refund=50)],
        actions=[upgrade(2),upgrade(0),choose('B',1),upgrade(1),sell(0),upgrade(1),choose('A',0),sell(1),sell(0)]))
    for points in (10000.49,10000.5,10000.51,2**53+1,2**53+2,1e24):
        cases.append(dict(name=f'binary64 balance {points}',points=points,towers=[],
            actions=[build(0),upgrade(),upgrade(),sell(),build(8),sell()]))
    for kind in range(9):
        for level in (1,4,5,99,100):
            choices='A'*(level//5)
            for construction in (1,17):
                cases.append(dict(name=f'upgrade thresholds {kind}/{level}/{construction}',points=0,
                    construction=[construction]*9,towers=[seed(kind,level,choices,refund=2**53+2)],
                    actions=[upgrade(price_neighbor=-1),upgrade(price_delta=0),sell()]))
        cases.append(dict(name=f'build thresholds kind {kind}',points=0,towers=[],
            actions=[dict(**build(kind),price_neighbor=-1),dict(**build(kind),price_delta=0),sell()]))
    cases.append(dict(name='locked construction',points=1e6,construction=[0]*9,towers=[],
                      actions=[build(0),build(8)]))
    for count in (2,3,4,8,12):
        cases.append(dict(name=f'build scaling count {count}',points=1e20,
            towers=[seed(i%9,x=100+100*i,refund=i+.5) for i in range(count)],
            actions=[dict(**build(8,100+100*count),price_neighbor=-1),
                     dict(**build(8,100+100*count),price_delta=0),sell(count//2),build(3,1200),sell(0)]))
    return cases


SCRIPT=r'''
const vm=require('node:vm'),d=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
try{
const out=[];
for(const input of d.cases){
 let click=null,lastCreated=null,ghostCreated=false;const built=[],commands=[];
 const engine={tasks:[],isPaused:()=>false,addTask(task){this.tasks.push(task)},gameAttributes:{h:{}}};
 const attrs={CurrentMap:26,CustomLists:{h:{}},CustomMaps:{h:{}},PixelHelperActor:[],
  Refinery:[[-3]],OptionsList:Array(30).fill(0),OptionsListAccount:Array(700).fill(0),
  NodeX:Array(100).fill(0),NodeLength:Array(100).fill(10000),NodeY:Array(100).fill(300),
  MenuType:0,MenuType2:0,TowerInfo:Array(30).fill(1),MapMonstersList:[{getZIndex:()=>100}],
  MonsterDefinitionsGET:{h:{}},MonsterRespawnTime:[],MonsterHP:[],MonsterAlive:[],
  Tasks:[[0,[1e300]]],Dream:Array(10).fill(0),DNSM:{h:{}},DummyNumbersStatManager:{h:{}},
  TotemInfo:Array.from({length:3},()=>Array(8).fill(0)),OriginPixelActor:Array(7).fill({getZIndex:()=>0}),
  QuestComplete:{h:{Royal_Worm5:1,Hoggindaz4:1}},Number2Letter:Array(27).fill('').concat(['A','B']),
  DummyList:[],SceneEvents_n:0};
 engine.gameAttributes.h=attrs;
 engine.getGameAttribute=key=>{if(!(key in attrs))throw Error('Missing attribute '+key);return attrs[key]};
 const image={get_y:()=>0,get_x:()=>0,get_alpha:()=>1,get_width:()=>10,get_height:()=>10,set_alpha(){}};
 const actor={isAlive:()=>true,isPaused:()=>false};
 const self={actor,wrapper:{enabled:true},_GenINFO:Array(100).fill(0),_UIinventoryOn8:Array(100).fill(0),
  _UIinventory8:Array(100).fill(image),_customEvent_RefineryStuff(){}};
 for(const index of [7,41,42,43,46])self._UIinventory8[index]=Array(30).fill(image);
 self._UIinventoryOn8[8]=1;self._UIinventoryOn8[46]=Array(30).fill(0);
 const g=self._GenINFO;Object.assign(g,{6:0,8:1,10:[0,0],11:-1,13:9999,14:{},16:[0],17:[0],
  23:[20,20],24:[1,1,1,1,2,0],27:'Blank',51:0,52:Array(10).fill('Mob'),53:0,54:[],55:1,
  56:[],57:0,59:0,61:Array(9).fill(-1),62:30,64:-1,65:-1,74:0,84:1,85:0,88:1,89:0});
 attrs.PixelHelperActor[7]={behaviors:{getBehavior:()=>self},shout:()=>self._customEvent_WorshipStuff()};
 const ctx={a:{engine,STEP_SIZE:10,SCALE:1},c:{engine,asNumber:x=>x==null?0:Number(x),getActorType:x=>x,
  getActorsOfType:type=>type===358?built:[],getScreenX:()=>0,getScreenY:()=>0,
  getMouseX:()=>click?.[0]??100,getMouseY:()=>click?.[1]??20,getValueForScene:()=>0,
  getLastCreatedActor:()=>lastCreated,createHueFilter:()=>0,createSaturationFilter:()=>0,createBrightnessFilter:()=>0,
  attachImageToActor(){},setFilterForImage(){},clearFiltersForImage(){},removeImage(){},moveImageBy(){},moveImageTo(){},
  recycleActor(a){if(a)a.recycled=true},randomFloat:()=>1,randomInt:(a,b)=>b,getCurrentSceneName:()=>'fixture'},
  A:{},ja:{},ka:{},B:{},D:{contains:(xs,x)=>xs.includes(x)},
  oa:function(){this.nameMap={h:{}};this.wrapper={enabled:true}},E:(base,props)=>Object.assign({},base,props),
  w:(self,fn)=>fn.bind(self),n:{__cast:x=>x},h:{string:String},y:{replace:(s,a,b)=>s.split(a).join(b)},
  u:{deepCopyList:x=>JSON.parse(JSON.stringify(x))},
  p:{_customBlock_Dungon:()=>-1,_customBlock_ArcadeBonus:()=>0,_customBlock_Reg_ach_add_status(){},_customBlock_ActionBlock(){}},
  q:{_customBlock_MenagerieStuff:()=>0,_customBlock_TotalFoodBonuses:()=>0,
   _customBlock_IsXYmouseWithinBounds:(x1,x2,y1,y2)=>Number(click!==null&&click[0]>=x1&&click[0]<=x2&&click[1]>=y1&&click[1]<=y2)},
  ba:{remove:(xs,x)=>{const i=xs.indexOf(x);if(i>=0)xs.splice(i,1)}},l:class{constructor(){this.h={}}},
  m:{_customBlock_AtomCollider:()=>0,_customBlock_Windwalker:()=>0,_customBlock_GetSetBonus:()=>0,
   _customBlock_Bubbastuff:()=>0,_customBlock_Summoning:()=>0},
  x:{_customBlock_DamageDealed:()=>0,_customBlock_skillstats2:()=>1,_customBlock_ArbitraryCode:()=>1},
  v:{_customBlock_ProgressStarsign(){},_customBlock_giveEXP(){}},
  k:{_customBlock_DialogueETC:()=>'',_customBlock_TalentCalc:()=>0,_customBlock_AddStatusToMonster(){},
   _customBlock_AdjustImgInst(){},_customBlock_NotateNumber:String},t:{linear:0,quadOut:0}};
 vm.createContext(ctx);
 vm.runInContext(d.constructor+d.prototype+d.registration+d.WorshipInfo+d._customBlock_WorshipStuff+d._customBlock_2inputs,ctx);
 for(const key of ['WorshipBASEinfos','WorshipMapType','TDtraits','TowerInfo','_customBlock_TowerStats','_customBlock_Tower2Stats','WorshipNODESnETC']){
  const part=d[key];ctx[part.owner]??={};vm.runInContext(part.code,ctx);
 }
 attrs.CustomLists.h.WorshipInfo=ctx.ja.WorshipInfo();
 for(const key of ['WorshipBASEinfos','TDtraits','TowerInfo','WorshipNODESnETC'])attrs.CustomLists.h[key]=ctx[d[key].owner][key]();
 attrs.CustomLists.h.NonDMGLinemonsterTypes=[];attrs.CustomLists.h.PrayerInfo=[];
 attrs.CustomMaps.h.WorshipMapType=ctx[d.WorshipMapType.owner].WorshipMapType();
 for(let kind=0;kind<9;kind++)attrs.TowerInfo[9+kind]=(input.construction??Array(9).fill(1))[kind];
 vm.runInContext(d.baseclass.code,ctx);
 const original=key=>vm.runInContext('('+d[key]+')',ctx);
 ctx.k._customBlock_DistanceEqn=original('distance');
 const command=original('helper');self._customEvent_WorshipStuff=function(){commands.push(self._TRIGGEREDtext);return command.call(self)};
 const press=original('press'),send=original('send'),place=original('placement');
 function spawnBase(x,y){
  const a={name:attrs.DummyText3,frame:0,z:0,recycled:false,dead:false,
   getAnimation(){return this.name},setAnimation(name){this.name=name},getCurrentFrame(){return this.frame},
   setCurrentFrame(frame){this.frame=frame},getXCenter:()=>x+35,getYCenter:()=>y+25,
   getX:()=>x,getY:()=>y,getZIndex(){return this.z},setZIndex(value){this.z=value},isAlive(){return !this.recycled},isPaused:()=>false};
  for(const name of ['makeAlwaysSimulate','sendToBack','setXY','cancelTweens','clearFilters','set_alpha',
                    'disableActorDrawing','growTo','fadeTo'])a[name]=()=>{};
  const script=new ctx[d.baseclass.owner](null,null,null);script.actor=a;script.addListener=()=>{};
  a.behaviors={getBehavior:()=>script};script.init();built.push(a);lastCreated=a;return a;
 }
 ctx.c.createRecycledActor=(type,x,y)=>{if(type===131){ghostCreated=true;return null}
  if(type===358)return spawnBase(x,y);throw Error('Unexpected actor type '+type)};
 function build(tower){
  ghostCreated=false;g[64]=-1;g[57]=0;click=[261+49*tower.kind+20,85];press.call(self);click=null;
  if(!ghostCreated)return;
  const controller={wrapper:{enabled:true},_PixelType:2,_PersonalList1:[1,0,0,tower.kind,Array(12).fill(0)],
   actor:{getX:()=>tower.x}};controller._PersonalList1[4][1]=tower.node;place.call(controller);
 }
 function button(action){
  const base=g[56][action.index][6];g[64]=action.index;g[59]=action.kind==='sell'?1:0;
  const x=Math.min(action.kind==='choose'?738:768,Math.max(5,base.getXCenter()-(action.kind==='choose'?106:93))),
   y=Math.min(375,Math.max(5,base.getYCenter()-165));
  click=action.kind==='upgrade'?[x+150,y+65]:action.kind==='sell'?[x+30,y+50]:[x+190,y+(action.choice==='A'?20:60)];
  send.call(self);click=null;
 }
 function rows(){return g[56].map(row=>[row[0],row[1],row[2],row[5],row[9],row[11]])}
 g[51]=1e300;
 for(const tower of input.towers){build(tower);const row=g[56].at(-1);if(!row)throw Error('Initial tower unavailable');
  row[5]=tower.level;row[9]=tower.choices;row[11]=tower.refund;
 }
 if(g[56].length){self._TRIGGEREDtext='z';self._customEvent_WorshipStuff()}
 g[51]=input.points;const observations=[];
 for(const action of input.actions){
  if('price_delta' in action||'price_neighbor' in action){
   const cost=action.kind==='build'?ctx.p._customBlock_WorshipStuff('NewTowerCost',action.tower.kind)
    :ctx.p._customBlock_TowerStats('cost',g[56][action.index][0],g[56][action.index][5]);
   if('price_neighbor' in action){
    if(!(cost>0))throw Error('Adjacent affordability probes require a positive source price');
    const bits=new DataView(new ArrayBuffer(8));bits.setFloat64(0,cost);
    bits.setBigUint64(0,bits.getBigUint64(0)+BigInt(action.price_neighbor));g[51]=bits.getFloat64(0);
   }else g[51]=cost+action.price_delta;
  }
  const inputPoints=g[51],before=JSON.stringify(rows()),pointBefore=g[51],commandStart=commands.length;
  if(action.kind==='build')build(action.tower);else button(action);
  const accepted=before!==JSON.stringify(rows())||pointBefore!==g[51];
  observations.push({input_points:inputPoints,accepted,points:g[51],rows:rows(),
   recompute:commands.slice(commandStart).includes('z'),cooldown_override:accepted&&action.kind==='upgrade'?[action.index,g[56][action.index][8]]:null});
 }
 out.push(observations);
}
process.stdout.write(JSON.stringify(out));
}catch(error){process.stderr.write(error.stack);process.exitCode=1;}
'''


def modeled(case,original):
    towers=tuple(Tower(**{key:value for key,value in tower.items() if key!='refund'}) for tower in case['towers'])
    state=Board(True,points=case['points'],construction=tuple(case.get('construction',[1]*9)),towers=towers)
    refunds=tuple(tower['refund'] for tower in case['towers'])
    observations=[]
    for action,source in zip(case['actions'],original,strict=True):
        if 'price_delta' in action or 'price_neighbor' in action:
            state=replace(state,points=source['input_points'])
        investment=Investment(action['kind'],index=action.get('index',-1),
                              tower=Tower(**action['tower']) if 'tower' in action else None,
                              choice=action.get('choice',''))
        input_points=float(state.points)
        result=invest(state,refunds,investment)
        if result is not None:state,refunds=result.state,result.refunds
        observations.append(dict(input_points=input_points,accepted=result is not None,points=state.points,
            rows=[[tower.kind,tower.node,tower.x,tower.level,tower.choices,refund]
                  for tower,refund in zip(state.towers,refunds,strict=True)],
            recompute=result.recompute if result else False,
            cooldown_override=list(result.cooldown_override) if result and result.cooldown_override else None))
    return observations


def check(path):
    source=load('client_source.py').source_from_asar(path)
    payload=source_parts(source);cases=scenarios();payload['cases']=cases
    run=subprocess.run(['node','-e',SCRIPT],input=json.dumps(payload),text=True,capture_output=True,check=True,timeout=30)
    originals=json.loads(run.stdout,parse_int=float)
    count=0
    for case,original in zip(cases,originals,strict=True):
        model=modeled(case,original)
        for step,(client,projection) in enumerate(zip(original,model,strict=True)):
            if client!=projection:
                raise AssertionError(dict(case=case['name'],step=step,action=case['actions'][step],client=client,model=projection))
            count+=1
    return len(cases),count


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar',type=Path,required=True)
    args=parser.parse_args()
    try:
        cases,steps=check(args.asar)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr[-1600:])
    print(f'{cases} investment sequences and {steps} purchase decisions match original callbacks.')
