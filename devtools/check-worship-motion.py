"""Compare collision-free motion with installed Actor and tween methods.

The checker extracts original methods at runtime. It executes simple physics,
Actor XY movement and original tween classes. Collisions, gravity, pause,
actor lifecycle and complete battles are outside this check.
"""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from worship_sim.motion import Motion


def source_parts(source):
    def owner(name):
        marker = f'A["com.stencyl.{name}"]='
        start = source.find(marker)
        if start < 0:
            raise ValueError('Original registry is unavailable: ' + name)
        return re.match(r'[A-Za-z_$][\w$]*', source[start + len(marker):])[0], start

    actor_owner, actor_registry = owner('models.Actor')
    prototype = source.find(actor_owner + '.prototype=', actor_registry)
    if prototype < 0:
        raise ValueError('Original Actor prototype is unavailable.')
    methods = {}
    for name in ('getX', 'getY', 'moveBy', 'moveTo', 'resetReal', 'moveActorBy',
                 'updateTweenXY', 'internalUpdate'):
        marker = name + ':function('
        start = source.find(marker, prototype)
        if start < 0:
            raise ValueError('Original Actor method is unavailable: ' + name)
        end = re.search(r'},[A-Za-z_$][\w$]*:', source[start:])
        if end is None:
            raise ValueError('Original Actor method boundary changed: ' + name)
        methods[name] = source[start + len(name) + 1:start + end.start() + 1]

    parts = {'methods': methods}
    for key, name in (('object', 'utils.motion.TweenObject'),
                      ('float2', 'utils.motion.TweenFloat2'),
                      ('manager', 'utils.motion.TweenManager')):
        symbol, registry = owner(name)
        start = source.rfind('var ' + symbol + '=function', 0, registry)
        end = source.find(';var ', registry)
        if start < 0 or end < 0:
            raise ValueError('Original tween class boundary changed: ' + name)
        parts[key] = source[start:end] + ';'
        parts[key + '_owner'] = symbol

    manager_call = parts['manager_owner'] + '.update(0|e)'
    if source.find('update:function(e){if(null!=this.scene){if(' + manager_call) < 0:
        raise ValueError('Original engine tween phase changed.')
    _,registry=owner('utils.motion.QuadOut')
    start=source.find('apply:function(',registry)+len('apply:')
    end=source.find('},__class__:',start)
    if end<start:
        raise ValueError('Original quadratic easing changed.')
    parts['quad_out']=source[start:end+1]
    return parts


def scenarios():
    return [
        dict(start=[100, 0, 7, -2], steps=100, step=10, actions=[]),
        dict(start=[100, 0, 7, 0], steps=61, step=10, actions=[[0, -50, 0, 600]]),
        dict(start=[100, 0, 7, 0], steps=61, step=10,
             actions=[[0, -50, 0, 600], [30, 20, 0, 200]]),
        dict(start=[-25.25, 42.5, -3.2, 1.75], steps=80, step=10,
             actions=[[0, 81.5, -17.25, 370], [12, -8.25, 43.5, 170]]),
        dict(start=[20, 40, 0, 0], steps=12, step=33,
             actions=[[0, 100, -25, 100], [3, -50, 10, 0]]),
        dict(start=[2.5, -10.25, 2, -4], steps=4, step=100,
             actions=[[0, -50, 30, 250], [1, 0, 0, 90]]),
        dict(start=[100, 0, 7, 0], steps=61, step=10, easing='quad_out',
             actions=[[0, -50, 0, 600]]),
        dict(start=[-25.25, 42.5, -3.2, 1.75], steps=80, step=10, easing='quad_out',
             actions=[[0, 81.5, -17.25, 370], [12, -8.25, 43.5, 170]]),
    ]


SCRIPT = r'''
const vm=require('node:vm'),d=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
const ctx={A:{},E:(base,props)=>Object.assign(Object.create(base),props),
 a:{STEP_SIZE:10,NO_PHYSICS:false},t:{linear:{apply:x=>x}}};
vm.createContext(ctx);vm.runInContext(d.object+d.float2+d.manager,ctx,{timeout:2000});
ctx.t.quad_out={apply:vm.runInContext('('+d.quad_out+')',ctx)};
const Manager=ctx[d.manager_owner],Tween=ctx[d.float2_owner],methods={};
for(const [name,body] of Object.entries(d.methods))methods[name]=vm.runInContext('('+body+')',ctx,{timeout:2000});
const result=[];
for(const test of d.scenarios){
 Manager.resetStatics();const [x,y,vx,vy]=test.start;
 const actor={...methods,physicsMode:1,ignoreGravity:true,isHUD:false,paused:false,collidable:false,
  cacheWidth:51,cacheHeight:73,currOffset:{x:3,y:-4},realX:x+28,realY:y+32,xSpeed:vx,ySpeed:vy,
  rSpeed:0,realAngle:0,fixedRotation:false,lastScale:{x:1,y:1},realScaleX:1,realScaleY:1,
  currAnimation:null,clearCollisionInfoList(){},tweenProps:{}};
 actor.tweenProps.xy=new Tween().doOnUpdate(()=>actor.updateTweenXY());
 const observed=[];
 for(let tick=0;tick<test.steps;tick++){
  for(const [at,dx,dy,duration] of test.actions)if(at===tick)actor.moveBy(dx,dy,duration/1000,ctx.t[test.easing??'linear']);
  Manager.update(test.step);actor.internalUpdate(test.step,false);
  observed.push([actor.getX(false),actor.getY(false)]);
 }result.push(observed);
}
process.stdout.write(JSON.stringify(result));
'''


def modeled_cases(cases):
    results = []
    for case in cases:
        actor = Motion(*case['start'])
        observed = []
        for tick in range(case['steps']):
            for at, dx, dy, duration in case['actions']:
                if at == tick:
                    actor.move_by(dx, dy, duration, easing=case.get('easing','linear'))
            actor.advance_tween(case['step'])
            actor.advance_physics(case['step'])
            observed.append([actor.x, actor.y])
        results.append(observed)
    return results


def check(path):
    spec = importlib.util.spec_from_file_location('client_check', Path(__file__).with_name('client_source.py'))
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    parts = source_parts(client.source_from_asar(path))
    parts['scenarios'] = scenarios()
    run = subprocess.run(['node', '-e', SCRIPT], input=json.dumps(parts), text=True,
                         capture_output=True, check=True, timeout=15)
    original = json.loads(run.stdout)
    modeled = modeled_cases(parts['scenarios'])
    count = 0
    for case, (expected, actual) in enumerate(zip(original, modeled)):
        if len(expected) != len(actual):
            raise AssertionError('Motion sample count differs.')
        for tick, (client_xy, model_xy) in enumerate(zip(expected, actual)):
            for axis, (client_value, model_value) in enumerate(zip(client_xy, model_xy)):
                # The client stores a translated center, while Motion stores
                # top-left coordinates, causing sub-pixel floating roundoff.
                if not math.isclose(client_value, model_value, rel_tol=1e-12, abs_tol=1e-10):
                    raise AssertionError(dict(case=case, tick=tick, axis=axis,
                                              client=client_value, model=model_value))
            count += 1
    if len(original) != len(modeled):
        raise AssertionError('Motion scenario count differs.')
    return len(modeled), count


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar', type=Path, required=True)
    args = parser.parse_args()
    try:
        cases, samples = check(args.asar)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr[-1500:])
    print(f'{cases} motion scenarios and {samples} XY samples match original client methods. Collisions and battles remain unverified.')
