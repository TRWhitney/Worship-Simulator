"""Check zero-angle actor geometry with original Actor and recycler methods.

Image resources use declared numeric profiles. Original animation switching,
origin adjustment, position methods, frame clocks, XY tweens and Engine
recycling execute unchanged. Collision, gravity, rotation and complete combat
are outside this check.
"""
import argparse
import importlib.util
import json
import math
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from worship_sim.actor import ActorBody, SpriteProfile


def load(file, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'devtools' / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_parts(source):
    parts = load('check-worship-motion.py', 'motion').source_parts(source)
    marker = 'A["com.stencyl.models.Actor"]='
    registry = source.index(marker)
    owner = re.match(r'[A-Za-z_$][\w$]*', source[registry + len(marker):])[0]
    constructor = source[source.rfind('var ' + owner + '=function', 0, registry):registry]
    if 'this.switchToDefaultAnimation(),null!=m?this.setLocation(n,s)' not in constructor:
        raise ValueError('Original default-animation/initial-location order changed.')
    prototype = source.index(owner + '.prototype=', registry)
    for name in ('getWidth', 'getHeight', 'getAngle', 'getXCenter', 'getYCenter',
                 'getXVelocity', 'getYVelocity', 'setXVelocity', 'setYVelocity',
                 'setXCenter', 'setYCenter', 'setX', 'setY', 'setXY', 'setLocation',
                 'setAnimation', 'switchAnimation', 'setOriginPoint',
                 'switchToDefaultAnimation', 'defaultShapeChanged', 'cancelTweens',
                 'getCurrentFrame', 'setCurrentFrame'):
        start = source.index(name + ':function(', prototype)
        end = re.search(r'},[A-Za-z_$][\w$]*:', source[start:])
        if end is None:
            raise ValueError('Original Actor method boundary changed: ' + name)
        parts['methods'][name] = source[start + len(name) + 1:start + end.start() + 1]
    for key, name in (('float', 'com.stencyl.utils.motion.TweenFloat'),
                      ('properties', 'com.stencyl.models.actor.ActorTweenProperties')):
        marker = 'A["' + name + '"]='
        registry = source.index(marker)
        owner = re.match(r'[A-Za-z_$][\w$]*', source[registry + len(marker):])[0]
        start = source.rfind('var ' + owner + '=function', 0, registry)
        end = source.index(';var ', registry)
        parts[key] = source[start:end] + ';'
        parts[key + '_owner'] = owner
    start = source.index('recycleActor:function(') + len('recycleActor:')
    parts['recycle'] = source[start:source.index('},getRecycledActorOfType:', start) + 1]
    marker = 'A["com.stencyl.graphics.BitmapAnimation"]='
    registry = source.index(marker)
    for key, name, following in (('anim_update', 'update', 'getCurrentFrame'),
                                 ('anim_set', 'setFrame', 'isFinished')):
        start = source.index(name + ':function', registry)
        parts[key] = source[start + len(name) + 1:source.index('},' + following + ':', start) + 1]
    return parts


def profiles():
    wizard = [100] * 136
    for frame in (4, 14, 19, 29, 34, 44, 49, 64, 79, 94, 109):
        wizard[frame] = 10000
    box = [1000] * 51
    for frame in (6, 13, 21, 29, 36, 50):
        box[frame] = 10000
    return [
        dict(width=35, height=33, frames=[100] * 7, looping=True, origin=[17, 33]),
        dict(width=66, height=18, frames=[100] * 6, looping=True, origin=[33, 18]),
        dict(width=70, height=50, frames=box, looping=True, origin=[35, 25]),
        dict(width=51, height=73, frames=wizard, looping=True, origin=[25, 73]),
        dict(width=50, height=50, frames=[100] * 15 + [10000], looping=False, origin=[25, 50]),
        dict(width=65, height=50, frames=[100] * 24 + [10000], looping=False, origin=[32, 50]),
        dict(width=72, height=80, frames=[80, 80, 80] + [100] * 7, looping=False, origin=[36, 80]),
        # Separate animation with the same metadata verifies object identity.
        dict(width=66, height=18, frames=[100] * 6, looping=True, origin=[33, 18]),
    ]


def cases():
    return [
        dict(default=0, left=0, top=0, actions=[['switch', 1], ['set_x_center', 100],
             ['set_y_center', 100], ['set_left', -.5], ['set_top', -.5]]),
        dict(default=0, left=0, top=0, actions=[['animation', 110], ['switch', 0],
             ['switch', 1], ['animation', 110], ['switch', 1], ['switch', 7]]),
        dict(default=2, left=517, top=765, actions=[['switch', 3], ['animation', 350],
             ['frame', 4], ['switch', 3], ['switch', 2], ['switch', 3]]),
        dict(default=4, left=0, top=250, actions=[['switch', 5], ['set_x_center', 890],
             ['set_top', 450], ['set_x_center', 10], ['set_top', 250]]),
        dict(default=0, left=100, top=200, actions=[['switch', 1], ['velocity', 5, -2],
             ['tween', -50, 10, 600, 'linear'], ['advance', 10], ['recycle'],
             ['advance', 600], ['advance', 10]]),
        dict(default=0, left=100, top=200, actions=[['animation', 220], ['velocity', 7, 1],
             ['tween', 50, -10, 600, 'quad_out'], ['advance', 10], ['recycle'],
             ['advance', 600], ['advance', 10]]),
        dict(default=2, left=-10.125, top=20.375, actions=[['switch', 3], ['switch', 6],
             ['velocity', -3.2, 1.75], ['tween', 20.25, -15.5, 100, 'quad_out'],
             ['advance', 10], ['advance', 30], ['switch', 1], ['advance', 60],
             ['recycle'], ['advance', 100]]),
    ]


SCRIPT = r'''
const vm=require('node:vm'),p=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
try{
 const engine={tasks:[],whenTypeGroupKilledEvents:{h:{}},removeActorFromLayer(){},allActors:{unset(){}}};
 const ctx={A:{},E:(base,props)=>Object.assign(Object.create(base),props),
   a:{engine,STEP_SIZE:10,NO_PHYSICS:false,SCALE:1,physicsScale:10,toPhysicalUnits:x=>x/10,toPixelUnits:x=>x*10},
   t:{linear:{apply:x=>x}},n:{__cast:x=>x},va:{antialias:false},V:function(x,y){this.x=x;this.y=y},
   ba:{remove:(xs,x)=>{const i=xs.indexOf(x);if(i>=0)xs.splice(i,1)}}};
 vm.createContext(ctx);
 vm.runInContext(p.object+p.float+p.float2+p.manager+p.properties,ctx,{timeout:2000});
 const original=key=>vm.runInContext('('+p[key]+')',ctx,{timeout:2000}),methods={};
 for(const [name,body] of Object.entries(p.methods))methods[name]=vm.runInContext('('+body+')',ctx,{timeout:2000});
 engine.recycleActor=original('recycle');ctx.t.quad_out={apply:original('quad_out')};
 const Manager=ctx[p.manager_owner],Properties=ctx[p.properties_owner],results=[];
 function animation(profile){
  const anim={model:{sync:false,looping:profile.looping,frames:Array(profile.frames.length).fill(0)},
   frameIndex:0,timer:0,finished:false,numFrames:profile.frames.length,durations:profile.frames,filter:null,
   set_bitmapData(){},set_filter(){},set_visible(){},get_width:()=>profile.width,get_height:()=>profile.height};
  anim.update=original('anim_update');anim.setFrame=original('anim_set');anim.getCurrentFrame=()=>anim.frameIndex;return anim;
 }
 for(const test of p.cases){
  Manager.resetStatics();const actor={...methods,physicsMode:1,body:null,
   currAnimation:null,currAnimationName:null,defaultAnim:'p'+test.default,cacheWidth:0,cacheHeight:0,
   currOffset:{x:0,y:0},currOrigin:{x:0,y:0},realX:0,realY:0,realAngle:0,
   realScaleX:1,realScaleY:1,lastScale:{x:1,y:1},xSpeed:0,ySpeed:0,rSpeed:0,
   fixedRotation:false,paused:false,isHUD:false,ignoreGravity:true,continuousCollision:false,
   snapOnSet:false,collidable:false,shapeMap:{h:{}},bitmapFilters:null,drawActor:true,
   animationMap:{h:Object.fromEntries(p.profiles.map((profile,i)=>['p'+i,animation(profile)]))},
   originMap:{h:Object.fromEntries(p.profiles.map((profile,i)=>['p'+i,{x:profile.origin[0],y:profile.origin[1]}]))},
   addChild(){},removeChild(){},updateChildrenPositions(){},clearCollisionInfoList(){},
   whenKilled:{length:0},getType:()=>({__id__:0}),getGroup:()=>({__id__:0}),
   clearFilters(){},resetBlendMode(){},set_alpha(){},disableActorDrawing(){this.drawActor=false},
   removeAttachedImages(){},removeAllListeners(){},resetListeners(){}};
  actor.tweenProps=new Properties();actor.tweenProps.xy.doOnUpdate(()=>actor.updateTweenXY());
  actor.switchToDefaultAnimation();actor.setLocation(test.left,test.top);
  const samples=[];
  function sample(){samples.push([actor.getXCenter(),actor.getYCenter(),actor.getX(false),actor.getY(false),
   actor.getX(),actor.getY(),actor.cacheWidth,actor.cacheHeight,Number(actor.currAnimationName.slice(1)),
   actor.currAnimation.frameIndex,actor.currAnimation.timer,actor.currAnimation.finished,actor.xSpeed,actor.ySpeed])}
  sample();
  for(const [action,...args] of test.actions){
   if(action==='switch')actor.setAnimation('p'+args[0]);
   else if(action==='animation')actor.currAnimation.update(args[0]);
   else if(action==='frame')actor.setCurrentFrame(args[0]);
   else if(action==='set_left')actor.setX(args[0]);
   else if(action==='set_top')actor.setY(args[0]);
   else if(action==='set_x_center')actor.setXCenter(args[0]);
   else if(action==='set_y_center')actor.setYCenter(args[0]);
   else if(action==='velocity'){actor.setXVelocity(args[0]);actor.setYVelocity(args[1])}
   else if(action==='tween')actor.moveBy(args[0],args[1],args[2]/1000,ctx.t[args[3]]);
   else if(action==='advance'){Manager.update(args[0]);actor.internalUpdate(args[0],true)}
   else if(action==='recycle')engine.recycleActor(actor);
   else throw Error('Unknown actor action '+action);
   sample();
  }results.push(samples);
 }
 process.stdout.write(JSON.stringify(results));
}catch(error){process.stderr.write(error.stack);process.exitCode=1;}
'''


def modeled_cases(data, inputs):
    sprites = [SpriteProfile(row['width'], row['height'], tuple(row['frames']), row['looping']) for row in data]
    results = []
    for case in inputs:
        actor = ActorBody(sprites[case['default']], left=case['left'], top=case['top'])
        samples = []
        def sample():
            index = next(i for i, profile in enumerate(sprites) if actor.profile is profile)
            samples.append([actor.x, actor.y, actor.left, actor.top, actor.get_x(), actor.get_y(),
                            actor.width, actor.height, index, actor.animation.frame,
                            actor.animation.elapsed_ms, actor.animation.finished,
                            actor.motion.vx, actor.motion.vy])
        sample()
        for action, *args in case['actions']:
            if action == 'switch':
                actor.set_animation(sprites[args[0]])
            elif action == 'animation':
                actor.animation.update(args[0])
            elif action == 'frame':
                actor.animation.set_frame(args[0])
            elif action in ('set_left', 'set_top', 'set_x_center', 'set_y_center'):
                getattr(actor, action)(args[0])
            elif action == 'velocity':
                actor.motion.vx, actor.motion.vy = args
            elif action == 'tween':
                actor.motion.move_by(*args[:3], easing=args[3])
            elif action == 'advance':
                actor.motion.advance_tween(args[0])
                actor.motion.advance_physics(args[0])
                actor.animation.update(args[0])
            elif action == 'recycle':
                actor.recycle()
            else:
                raise AssertionError('Unknown actor action: ' + action)
            sample()
        results.append(samples)
    return results


def check(path):
    source = load('client_source.py', 'loader').source_from_asar(path)
    payload = source_parts(source)
    inputs, data = cases(), profiles()
    payload.update(cases=inputs, profiles=data)
    run = subprocess.run(['node', '-e', SCRIPT], input=json.dumps(payload), text=True,
                         capture_output=True, check=True, timeout=15)
    originals = json.loads(run.stdout)
    models = modeled_cases(data, inputs)
    count = 0
    for case, (expected, actual) in enumerate(zip(originals, models, strict=True)):
        for step, (client_state, model_state) in enumerate(zip(expected, actual, strict=True)):
            for field, (client_value, model_value) in enumerate(zip(client_state, model_state, strict=True)):
                # The original zero-angle origin code divides by physicsScale
                # then multiplies back. Motion stores unrounded top-left
                # coordinates, permitting only floating roundoff here.
                matches = (math.isclose(client_value, model_value, rel_tol=1e-12, abs_tol=1e-9)
                           if field < 4 else client_value == model_value)
                if not matches:
                    raise AssertionError(dict(case=case, step=step, field=field,
                                              client=client_value, model=model_value))
            count += 1
    return len(inputs), count


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar', type=Path, required=True)
    args = parser.parse_args()
    try:
        count, samples = check(args.asar)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr[-2000:])
    print(f'{count} actor geometry scenarios and {samples} states match original switching, position and recycling methods.')
