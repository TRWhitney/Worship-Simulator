"""Check proposed tower slots with the installed original placement callback.

Runs ActorEvents_131._event_Updating on fabricated placement ghosts. UI image
services, mouse/camera readings and scene data are supplied by the host. The
original callback performs node selection, snapping and legality checks.
Geometry checks do not establish combat or strategy quality.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from worship_sim.models import Platform, Tower, Board
from worship_sim.layout import completion_plan, LayoutUnavailable


def source_parts(source):
    marker = 'A["scripts.ActorEvents_131"]='
    reg = source.find(marker)
    if reg < 0:
        raise ValueError('Original placement actor registry is unavailable.')
    owner = re.match(r'[A-Za-z_$][\w$]*', source[reg + len(marker):])[0]
    prototype = source.find(owner + '.prototype=', reg)
    name = '_event_Updating:'
    start = source.find(name + 'function(', prototype)
    end = source.find('},_event_Drawing:', start)
    if min(prototype, start, end) < 0:
        raise ValueError('Original placement update boundaries changed.')
    helper_start = source.find('p._customBlock_WorshipStuff=function(')
    helper_end = source.find('},p.', helper_start)
    if helper_start < 0 or helper_end < 0:
        raise ValueError('Original Worship helper boundaries changed.')
    return dict(update=source[start + len(name):end + 1],
                helper=source[helper_start:helper_end + 1] + ';')


def board(label, platforms, route=(), *, towers=(), portals=(), screen=(0, 0), probes=(),
          selection_nodes=(), upper_bound=None, unsupported=None):
    state = Board(True, platforms=tuple(platforms), route=tuple(route),
                         towers=tuple(towers), portals=tuple(portals),
                         placement_offset_x=screen[0], selection_nodes=tuple(selection_nodes))
    if unsupported is not None:
        try:
            completion_plan(state)
        except LayoutUnavailable as error:
            if unsupported not in str(error):
                raise AssertionError(f'Unexpected unsupported reason for {label}.') from error
        else:
            raise AssertionError(f'The planner accepted unsupported fixture {label}.')
        if upper_bound is None:
            raise ValueError('Unsupported diagnostics require independent proposed slots.')
        plan = upper_bound
    else:
        plan = completion_plan(state)
    return dict(label=label,
                platforms=[[p.node, p.left, p.right, p.y, p.direction] for p in state.platforms],
                selection_nodes=[[p.node, p.left, p.right, p.y, p.direction]
                                 for p in (state.selection_nodes or state.platforms)],
                route=list(state.route), towers=[[t.kind, t.node, t.x] for t in state.towers],
                portals=list(state.portals), screen=screen, plan=plan, probes=probes)


def fixtures():
    return [
        board('single route', [Platform(0, 0, 400, 300)], (0,),
              probes=((0, 79, False), (0, 80, True), (0, 320, True), (0, 321, False))),
        board('reversed route', [Platform(0, 0, 400, 300, -1)], (0,)),
        board('fixed tower', [Platform(0, 0, 400, 300)], (0,), towers=(Tower(7, 0, 200, 300),),
              probes=((0, 139, True), (0, 140, False), (0, 260, False), (0, 261, True))),
        board('portal', [Platform(0, 0, 400, 300)], (0,), portals=((0, 200),),
              probes=((0, 140, True), (0, 141, False), (0, 259, False), (0, 260, True))),
        board('one off-route slot', [Platform(0, 0, 60, 300)],
              probes=((0, 29, False), (0, 30, True), (0, 31, False))),
        board('one route slot', [Platform(0, 0, 160, 300)], (0,)),
        board('exact fixed spacing', [Platform(0, 0, 200, 300)],
              towers=(Tower(7, 0, 91, 300), Tower(7, 0, 152, 300))),
        board('multiple platforms and off-route support',
              [Platform(0, 0, 400, 100), Platform(1, 0, 400, 250, -1),
               Platform(2, 0, 400, 400), Platform(3, 0, 400, 550)], (0, 1, 2),
              portals=((1, 200),)),
        board('vertical camera', [Platform(0, 0, 400, 300)], (0,), screen=(0, 100)),
        board('overlapping windows with a free click height',
              [Platform(0, 0, 400, 300), Platform(1, 0, 400, 350)]),
    ]


def diagnostic_fixtures():
    return [
        board('horizontal camera +100', [Platform(0, 200, 600, 300)], (0,), screen=(100, 0),
              upper_bound=((0, 280), (0, 341), (0, 402), (0, 463)), unsupported='camera'),
        board('horizontal camera -100', [Platform(0, 200, 600, 300)], (0,), screen=(-100, 0),
              upper_bound=((0, 280), (0, 341), (0, 402), (0, 463)), unsupported='camera'),
        board('overlapping identical nodes', [Platform(0, 0, 400, 300), Platform(1, 0, 400, 300)], (0,),
              upper_bound=tuple((0, x) for x in (80, 141, 202, 263))
                          + tuple((1, x) for x in (30, 91, 152, 213, 274, 335)), unsupported='select'),
        board('short scene node intercepts a direct click', [Platform(1, 0, 200, 300)],
              selection_nodes=(Platform(0, 29, 31, 300), Platform(1, 0, 200, 300)),
              upper_bound=((1, 30), (1, 91), (1, 152)), unsupported='select'),
    ]


SCRIPT = r'''
const vm=require('node:vm'),d=JSON.parse(require('node:fs').readFileSync(0,'utf8'));
function run(board,node,x,rows,dy=-29){
 const [screenX,screenY]=board.screen,platform=board.platforms.find(p=>p[0]===node),mouseX=x-screenX,mouseY=platform[3]-screenY+dy;
 const nodeCount=Math.max(...board.selection_nodes.map(p=>p[0]))+1,
  attrs={CurrentMap:26,SceneEvents_n:'fixture',NodeX:Array(nodeCount).fill(0),NodeLength:Array(nodeCount).fill(0),NodeY:Array(nodeCount).fill(100000),
   CustomLists:{h:{WorshipNODESnETC:[[board.route,board.route.map(n=>board.platforms.find(p=>p[0]===n)[4]===1?0:1)]]}},
   CustomMaps:{h:{WorshipMapType:{h:{26:0}}}},NodeNeighbors:board.portals.map(p=>[p[0]]),PixelHelperActor:[]},
  scene={_NumberOfNodes:nodeCount,_PortalsXY:board.portals.map(([n,x],i)=>[x-20,0,i])};
 for(const [n,left,right,y] of board.selection_nodes){attrs.NodeX[n]=left;attrs.NodeLength[n]=right;attrs.NodeY[n]=y}
 const worship={_GenINFO:[]};worship._GenINFO[56]=rows;attrs.PixelHelperActor[7]={behaviors:{getBehavior:()=>worship}};
 const actor={x:mouseX,y:mouseY,getX(){return this.x},getY(){return this.y},setX(x){this.x=x},setY(y){this.y=y}};
 const ctx={a:{engine:{getGameAttribute:k=>attrs[k],gameAttributes:{h:attrs}}},
  c:{asNumber:x=>x==null?0:Number(x),getMouseX:()=>mouseX,getMouseY:()=>mouseY,getScreenX:()=>screenX,getScreenY:()=>screenY,
   getValueForScene:(_,key)=>scene[key],removeImage(){},attachImageToActor(){}},
  p:{},n:{__cast:x=>x},ka:{},k:{_customBlock_addImgInst:()=>({set_alpha(){}})},h:{string:String}};
 vm.createContext(ctx);vm.runInContext(d.helper,ctx,{timeout:2000});
 const self={actor,wrapper:{enabled:true},_PixelType:2,_PersonalList1:[2,2,{},7,Array(12).fill('Filler'),1]};self._PersonalList1[4][1]=-1;
 vm.runInContext('('+d.update+')',ctx,{timeout:2000}).call(self);
 return {valid:self._PersonalList1[0]===1,node:self._PersonalList1[4][1],x:actor.x+screenX};
}
function unchanged(result,node,x){return result.valid&&result.node===node&&result.x===x}
function selectable(board,node,x,rows){
 // Exhaust the full integer mouse-height selection strip, so overlapping
 // platforms are checked at every available direct click height.
 for(let dy=-79;dy<40;dy++)if(unchanged(run(board,node,x,rows,dy),node,x))return true;
 return false;
}
const supported=[];
for(const board of d.boards){
 const rows=board.towers.map(row=>row.slice()),placements=[],probes=[];
 for(const [node,x] of board.plan){let accepted=selectable(board,node,x,rows);placements.push(accepted);
  if(accepted)rows.push([7,node,x]);
 }
 for(const [node,x,expected] of board.probes)probes.push(selectable(board,node,x,board.towers)===expected);
 supported.push({label:board.label,placements,probes});
}
const diagnostics=[];
for(const board of d.diagnostics){
 const rows=board.towers.map(row=>row.slice());let rejected=0;
 for(const [node,x] of board.plan){
  if(selectable(board,node,x,rows))rows.push([7,node,x]);else rejected++;
 }diagnostics.push({label:board.label,proposed:board.plan.length,rejected});
}
process.stdout.write(JSON.stringify({supported,diagnostics}));
'''


def check(path):
    spec = importlib.util.spec_from_file_location('client_check', Path(__file__).with_name('client_source.py'))
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    payload = source_parts(client.source_from_asar(path))
    payload.update(boards=fixtures(), diagnostics=diagnostic_fixtures())
    run = subprocess.run(['node', '-e', SCRIPT], input=json.dumps(payload), text=True,
                         capture_output=True, check=True, timeout=30)
    result = json.loads(run.stdout)
    slots = probes = 0
    for case in result['supported']:
        if not all(case['placements']) or not all(case['probes']):
            raise AssertionError(f'Original placement disagrees on supported fixture: {case["label"]}.')
        slots += len(case['placements'])
        probes += len(case['probes'])
    return len(result['supported']), slots, probes, result['diagnostics']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--asar', type=Path, required=True)
    args = parser.parse_args()
    try:
        boards, slots, probes, diagnostics = check(args.asar)
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.stderr[-1500:])
    print(f'Original placement agrees: {boards} boards, {slots} sequential slots and {probes} boundary probes.')
    for case in diagnostics:
        print(f'Diagnostic, {case["label"]}: {case["rejected"]}/{case["proposed"]} proposed slots cannot be selected unchanged.')
