"""Replay six planned native-wave summons through the installed original client.

This is a controlled benchmark on one supplied 1000px platform at y300. It
uses the actual trial-zero wave table and explicit account factors; it does
not reproduce a recorded community run or a current live board. Planned input
attempts and integer RNG draws are replayed unchanged, including failed buys.
"""
import argparse
from dataclasses import asdict, replace
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from worship_sim.models import Platform,Board
from worship_sim.battle import PopupProfile
from worship_sim.candidates import candidates
from worship_sim.search import PlanSearch
from worship_sim.summon import Summon
from worship_sim.waves import Wave

HORIZON=60000


def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'devtools'/name)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def native_waves(path):
    client=load('client_source.py')
    source=client.source_from_asar(path)
    owner,code=client.function(source,'WorshipInfo')
    script="""const vm=require('node:vm'),p=JSON.parse(require('node:fs').readFileSync(0,'utf8')),
ctx={[p.owner]:{}};vm.createContext(ctx);vm.runInContext(p.code,ctx);
process.stdout.write(JSON.stringify(ctx[p.owner].WorshipInfo()[0]));"""
    run=subprocess.run(['node','-e',script],input=json.dumps(dict(owner=owner,code=code)),
                       text=True,capture_output=True,check=True,timeout=10)
    return tuple(Wave(*row) for row in json.loads(run.stdout))


def original_script(checker):
    script=checker.script()
    def replace(old,new):
        nonlocal script
        if script.count(old)!=1:raise ValueError('The original replay-host hook changed: '+old[:65])
        script=script.replace(old,new)
    replace("let birthID=0,click=null;","let birthID=0,click=null,rngIndex=0;")
    start=script.index('  randomInt(low,high){const value=')
    end=script.index('  getCurrentSceneName:',start)
    script=script[:start]+r'''
  randomInt(low,high){const expected=test.random_tape[rngIndex++];
   if(!expected||expected[0]!==now||expected[1]!==low||expected[2]!==high)
    throw Error(test.name+' RNG divergence at draw '+(rngIndex-1)+': requested '+JSON.stringify([now,low,high])+' supplied '+JSON.stringify(expected));
   const value=expected[3];if(!Number.isInteger(value)||value<low||value>high)throw Error('Invalid controlled random draw');
   rolls.push([now,low,high,value]);return value},
'''+script[end:]
    replace(' const observations=[];', ' const observations=[],controlResults=[];')
    replace('  observations.push(snapshot());', "  if(command!=='run')controlResults.push([now,command,lastResult]);")
    replace(' return observations;',r'''
 if(rngIndex!==test.random_tape.length)throw Error(test.name+' did not consume its full random input stream');
 const final=snapshot();let outstanding=Math.max(0,gen[53]);
 for(const mob of attrs.MapMonstersList)outstanding+=Math.max(0,ctx.c.asNumber(attrs.MonsterHP[mob.script._MonsterID]));
 return {summary:{now,credited:attrs.TotemInfo[0][test.native],reached:gen[55],wave:gen[8],lives:gen[23][1],
   points:gen[51],hp:final.remaining_hp,pending:gen[53],outstanding},controls:controlResults,
   random_draws:rolls.length};''')
    replace("try{process.stdout.write(JSON.stringify(data.cases.map(execute)))}catch(error){",r'''
const began=process.cpuUsage();
try{const runs=data.cases.map(execute),cpu=process.cpuUsage(began);
 process.stdout.write(JSON.stringify({runs,cpu_seconds:(cpu.user+cpu.system)/1e6}))}catch(error){''')
    return script


def summarize(world):
    return dict(now=world.loop.now_ms,credited=world.clock.credited,reached=world.clock.reached,
                wave=world.wave,lives=world.lives,points=world.points,hp=world.remaining_hp,
                pending=world.clock.pending_hp,outstanding=world.outstanding_hp)


def run(path,streams,draw_interval_ms=20,send_policy=None,advisor_defaults=False):
    waves=native_waves(path)
    state=Board(True,map_id=26,points=1000,hp=20,construction=(50,)*9,
                       platforms=(Platform(0,0,1000,300),),route=(0,))
    hidden=advisor_defaults
    plans=candidates(state,limit=6,max_towers=24 if advisor_defaults else 12,
                     target_level=25 if advisor_defaults else 10)
    if advisor_defaults and send_policy is None:send_policy='clear'
    if send_policy is not None:
        plans=tuple(replace(plan,send=send_policy,name=plan.name.replace('-rush-',f'-{send_policy}-')
                            .replace('-hold-',f'-{send_policy}-')) for plan in plans)
    if len(plans)!=6:raise AssertionError('The controlled fixture did not produce six candidate plans.')
    seeds=(13,71,211) if streams==3 else (13,)
    records=[]
    def factory(random_int):
        record=dict(plan=len(records)//len(seeds),seed=seeds[len(records)%len(seeds)],
                    attempts=[],controls=[],random_tape=[],world=None)
        def draw(low,high):
            value=random_int(low,high)
            now=record['world'].loop.now_ms if record['world'] is not None else 0
            record['random_tape'].append([now,low,high,value]);return value
        world=Summon(state,waves,trial=0,atom_bonus=0,salt_lick=0,meal_points=100,
                     meritoc_points=0,refunds=(),random_int=draw,popup_profile=PopupProfile(0,hidden),
                     draw_interval_ms=draw_interval_ms)
        record['world']=world
        apply,send=world.apply,world.send
        def attempted_purchase(action):
            now=world.loop.now_ms;result=apply(action)
            record['attempts'].append([now,'apply',asdict(action)])
            record['controls'].append([now,'apply',result]);return result
        def attempted_send():
            now=world.loop.now_ms;result=send()
            record['attempts'].append([now,'send'])
            record['controls'].append([now,'send',result]);return result
        world.apply,world.send=attempted_purchase,attempted_send
        records.append(record);return world
    search=PlanSearch(factory,plans,horizon_ms=HORIZON,random_seeds=seeds)
    slices=[];began=time.process_time()
    while not search.complete:
        started=time.process_time();search.advance(.003);slices.append(time.process_time()-started)
    model_cpu=time.process_time()-began
    if len(records)!=6*len(seeds):raise AssertionError('The search did not evaluate every plan/random stream.')
    checker=load('check-worship-summon.py')
    inputs=[]
    for record in records:
        operations=[];cursor=0
        for at,command,*args in record['attempts']:
            if at!=cursor:operations.append(['run',at]);cursor=at
            operations.append([command,*args])
        operations.append(['run',HORIZON])
        case=dict(name=f"{plans[record['plan']].name}/seed{record['seed']}",state=asdict(state),
            waves=[list(asdict(w).values()) for w in waves],trial=0,atom_bonus=0,
            salt=0,meal=100,merit=0,refunds=[],draw=draw_interval_ms,helper_y=0,operations=operations)
        original=checker.inputs(case)
        original['popup_profile']=asdict(PopupProfile(0,hidden))
        original['random_tape']=record['random_tape'];inputs.append(original)
    payload=dict(parts=checker.source_parts(path),cases=inputs)
    began=time.perf_counter()
    process=subprocess.run(['node','-e',original_script(checker)],input=json.dumps(payload),
        text=True,capture_output=True,check=True,timeout=60)
    original_wall=time.perf_counter()-began
    observed=json.loads(process.stdout,parse_int=float)
    for record,original in zip(records,observed['runs'],strict=True):
        name=plans[record['plan']].name
        if record['controls']!=original['controls']:
            for index,(model,source) in enumerate(zip(record['controls'],original['controls'])):
                if model!=source:raise AssertionError(dict(plan=name,seed=record['seed'],control=index,model=model,original=source))
            raise AssertionError(dict(plan=name,seed=record['seed'],message='Control count differs'))
        model=summarize(record['world'])
        if model!=original['summary']:
            raise AssertionError(dict(plan=name,seed=record['seed'],model=model,original=original['summary']))
        if len(record['random_tape'])!=original['random_draws']:
            raise AssertionError('The original random input consumption differs.')
    rankings=[]
    for index,plan in enumerate(plans):
        outcomes=[value['summary'] for record,value in zip(records,observed['runs'],strict=True) if record['plan']==index]
        credited=min(row['credited'] for row in outcomes);lives=min(row['lives'] for row in outcomes)
        outstanding=max(row['outstanding'] for row in outcomes)
        rankings.append((credited,lives,-outstanding))
        result=search.results[index]
        if result.rank!=rankings[-1]:raise AssertionError('The search aggregate rank differs from independently replayed outcomes.')
        print(f'{plan.name}: credited {credited:g}; lives {lives:g}; outstanding HP {outstanding:g}')
    winner=max(range(len(plans)),key=lambda index:rankings[index])
    if search.best.plan!=plans[winner]:raise AssertionError('The independent original outcome winner differs from PlanSearch.')
    print(f'Winner among these six plans: {plans[winner].name}; horizon {HORIZON/1000:g}s; seeds {seeds}.')
    print(f'Exact original replay: {len(records)} runs, {sum(len(record["attempts"]) for record in records)} input attempts, '
          f'{sum(len(record["random_tape"]) for record in records)} integer draws; final credit/reached/lives/points/HP/pending agree.')
    ordered=sorted(slices)
    print(f'Model CPU {model_cpu:.3f}s; {len(slices)} slices; median {statistics.median(slices)*1000:.3f}ms; '
          f'p95 {ordered[min(len(ordered)-1,int(.95*len(ordered)))]*1000:.3f}ms; max {max(slices)*1000:.3f}ms.')
    print(f'Original VM CPU {observed["cpu_seconds"]:.3f}s; wall {original_wall:.3f}s. Horizon outcomes remain lower bounds.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar',type=Path,required=True)
    parser.add_argument('--streams',type=int,choices=(1,3),default=3)
    parser.add_argument('--draw-interval-ms',type=int,choices=(20,30,50),default=20)
    parser.add_argument('--send-policy',choices=('clear','rush','hold'))
    parser.add_argument('--advisor-defaults',action='store_true',help='Use the live level/tower bounds and normalized popup/send settings.')
    args=parser.parse_args()
    try:run(args.asar,args.streams,args.draw_interval_ms,args.send_policy,args.advisor_defaults)
    except subprocess.CalledProcessError as error:raise SystemExit(error.stderr[-2400:])
