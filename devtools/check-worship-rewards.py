"""Compare Skull rewards with original currency and full monster KILL callbacks.

Each controlled death has one explicit Skull status, normal color, live engine
actor, zero HP and positive lives. Account reward inputs are supplied per case.
The checker measures immediate rewards, not death animation or whole battles.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from worship_sim.rewards import skull_reward
from worship_sim.simulation import js_round


def load(filename):
    spec=importlib.util.spec_from_file_location(filename,Path(__file__).with_name(filename))
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_parts(source):
    client=load('client_source.py')
    parts=load('check-worship-simulation.py').source_parts(source)
    parts['currency']=client.function(source,'_customBlock_WorshipStuff')[1]
    parts['number']=client.function(source,'asNumber')[1]
    start=source.index('_event_KILL:function',source.index('A["scripts.ActorEvents_1"]='))
    end=source.index('},_event_Corrections:',start)
    parts['kill']=source[start+len('_event_KILL:'):end+1]
    return parts


def scenarios():
    cases=[]

    def add(skull,size,wave,salt,meal,merit,balance=0):
        cases.append(dict(skull=skull,size=size,wave=wave,salt_lick=salt,
                          meal_points=meal,meritoc_points=merit,balance=balance))

    waves=(0,1,2,3,4,5,6,7,8,9,10,14,15,19,20,24,25,26,27,28,29,30,99,100)
    bonuses=((0,0,0),(25,20,30),(100,50,50),(12.5,33.3,77.7))
    for skull in range(17):
        for size in range(1,5):
            for wave in waves:
                for salt,meal,merit in bonuses:
                    add(skull,size,wave,salt,meal,merit)
    for skull in range(17):
        for salt in (24.999999999999996,25,25.000000000000004):
            add(skull,2,0,salt,0,0)
        for balance in (.49999999999999994,.5,1.5,1e12+.5):
            add(skull,2,27,25,20,30,balance)
    return cases


SCRIPT=r'''
const fs=require('node:fs'),vm=require('node:vm'),input=JSON.parse(fs.readFileSync(0,'utf8'));
let current=null;
const ctx={a:{},c:{},A:{},B:{},ka:{},ma:{},z:{},Tu:{},Di:{},Uu:{},
 n:{__cast:x=>x},D:{contains:(xs,x)=>xs.includes(x)},h:{string:String},
 t:{linear:0},va:{antialias:false},
 ba:{remove:(xs,x)=>{const index=xs.indexOf(x);if(index>=0)xs.splice(index,1)}},
 p:{_customBlock_Dungon:()=>-1,_customBlock_Shrine:()=>0,_customBlock_SaltLick:id=>{
  if(id!==6)throw Error('Unexpected Salt Lick query '+id);return current.salt_lick;
 }},m:{_customBlock_Windwalker:()=>0,_customBlock_Summoning:()=>0,
  _customBlock_ArcaneType:()=>0,_customBlock_Summoning2:(name,id,zero)=>{
   if(name!=='MeritocBonusz'||id!==16||zero!==0)throw Error('Unexpected Meritoc query');
   return current.meritoc_points;
  }},x:{_customBlock_DamageDealed:()=>0,_customBlock_ExpMulti:()=>1,_customBlock_GetBuffBonuses:()=>0},
 v:{_customBlock_CardBonusREAL:()=>0,_customBlock_giveEXP(){}},
 q:{_customBlock_MealBonus:name=>{if(name!=='TDpts')throw Error('Unexpected meal query');return current.meal_points}},
 k:{_customBlock_killmonsterQuest(){}}};
vm.createContext(ctx);const parts=input.parts;
vm.runInContext(parts.constructor+parts.prototype+parts.registration+parts.currency+parts.number,ctx);
const kill=vm.runInContext('('+parts.kill+')',ctx);
function run(fixture){
 current=fixture;const popups=[];
 const gen=Array(100).fill(0);gen[8]=fixture.wave;gen[19]=[];gen[23]=[5,5];gen[51]=fixture.balance;gen[56]=[];
 const helper={_GenINFO:gen},gen8=Array(150).fill(0);
 const script={wrapper:{enabled:true},_MonsterID:1,_MonsterNODE:0,_MonsterType:'synthetic',
  _IsWorshipMob:1,_PetStatus:0,_IsCardDisp:0,_TempMonster:1,_MonsterMoving:0,
  _WorshipMOD:0,_PersNum:0,_SizeMulti:fixture.size,_MoveSPEED:0,
  _StatusList:['StatusSkull'+fixture.skull],_StatusActive:[['StatusSkull'+fixture.skull,36000]],
  _StatusImgInst:[{}],_DeathFrame:1,_Monster0ffsetX:20};
 const actor={recycled:false,getX:()=>100,getXCenter:()=>120,getYCenter:()=>75,
  getXVelocity:()=>0,setXVelocity(){},getAnimation:()=>'synthetic',getNumFrames:()=>2,
  setCurrentFrame(){},growTo(){},isAlive:()=>true,isPaused:()=>false,
  behaviors:{getBehavior:()=>script}};
 script.actor=actor;
 const pixels=Array(9).fill({behaviors:{getBehavior:()=>helper}});
 pixels[8]={behaviors:{getBehavior:()=>({_GenINFO:gen8})}};
 const attrs={CurrentMap:26,MapMonstersList:[actor],MonsterHP:[0,0],MonsterAlive:[0,1],
  MonsterRespawnTime:[0,0],MonsterDefinitionsGET:{h:{synthetic:{h:{Type:'Monster',HeightOfMonster:50,
   Defence:0,DeathFrame:1,SpecialType:'',Name:'Synthetic',ExpType:0,ExpGiven:0}}}},
  PixelHelperActor:pixels,CustomMaps:{h:{WorshipMapType:{h:{26:0}}}},
  DNSM:{h:{FamBonusQTYs:{h:{40:0}},StarSigns:{h:{ExpActive:0}}}},
  QuestComplete:{h:{Royal_Worm5:1,Capital_P3:1,Bellows2:1}},NONdummies:Array(50).fill(0),
  OptionsListAccount:Array(700).fill(0),OtherPlayers:{h:{'0':{behaviors:{getBehavior:()=>({_TargetEnemy:null})}}}},
  UserInfo:['0'],PlayerAutoMoveTOGGLE:1,SceneEvents_n:0,InventoryOrder:[],Lv0:Array(10).fill(0)};
 attrs.OptionsListAccount[327]=1;
 const engine={tasks:[],addTask(task){this.tasks.push(task)},gameAttributes:{h:attrs},
  getGameAttribute:key=>{if(!(key in attrs))throw Error('Unexpected attribute '+key);return attrs[key]}};
 ctx.a.engine=engine;ctx.c.engine=engine;
 Object.assign(ctx.c,{randomInt:(a,b)=>b,randomFloat:()=>.9999999999999999,
  getCurrentSceneName:()=>'Acorn',getActorType:id=>id,removeImage(){},
  getActorsOfType:id=>id===1?[actor]:[],getValueForScene:(scene,key)=>{
   if(key!=='_NumberOfEnemies')throw Error('Unexpected scene query '+key);return 0;
  },createRecycledActor:type=>{
   if(type!==34)throw Error('Unexpected creation '+type);
   if(attrs.dummyDisplayPopup!=='POINTS')throw Error('Unexpected popup type');
   popups.push(attrs.dummyDamageDealt);
  }});
 const currency=ctx.p._customBlock_WorshipStuff('SkullCurrency',fixture.skull);
 kill.call(script);
 if(popups.length!==1||gen[19].length!==1||gen[19][0]!==fixture.skull)
  throw Error('Expected one actual Skull reward and POINTS allocation');
 return {currency,points:gen[51],popup:popups[0]};
}
process.stdout.write(JSON.stringify(input.cases.map(run)));
'''


def check(path):
    source=load('client_source.py').source_from_asar(path)
    cases=scenarios()
    payload=dict(parts=source_parts(source),cases=cases)
    run=subprocess.run(['node','-e',SCRIPT],input=json.dumps(payload),text=True,
                       capture_output=True,check=True,timeout=30)
    original=json.loads(run.stdout)
    if len(original)!=len(cases):
        raise AssertionError('Original reward result count differs')
    for case,want in zip(cases,original):
        reward=skull_reward(**{key:value for key,value in case.items() if key!='balance'})
        balance=js_round(case['balance']+reward.points)
        if (balance,reward.popup)!=(want['points'],want['popup']):
            raise AssertionError(f'{case}: overlay {(balance,reward.popup)}, original {want}')
        if case['size']==2 and reward.popup!=want['currency']:
            raise AssertionError(f'{case}: currency disagrees with size-2 popup')
    return len(cases)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar',type=Path,required=True)
    args=parser.parse_args()
    try:
        print(f'{check(args.asar)} original-client currency and full-KILL reward scenarios matched.')
    except (AssertionError,ValueError,OSError,subprocess.SubprocessError) as error:
        if isinstance(error,subprocess.CalledProcessError):
            print(error.stderr[-1500:],file=sys.stderr)
        raise SystemExit(str(error))
