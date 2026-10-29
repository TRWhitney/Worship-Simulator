"""The public simulator runs without the overlay, GUI or live client."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class IndependenceTests(unittest.TestCase):
    def test_controlled_summon_runs_with_overlay_and_process_imports_forbidden(self):
        source=Path(__file__).resolve().parents[1]/'src'
        script='''
import sys
from importlib.abc import MetaPathFinder
sys.path.insert(0,sys.argv[1])
class Guard(MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('idleon_overlay','PySide6','psutil','gi'):
            raise AssertionError('Forbidden simulator dependency: '+fullname)
sys.meta_path.insert(0,Guard())
from worship_sim.headless import Board,Tower,Platform,Summon,PopupProfile,Wave
state=Board(True,map_id=26,points=10000,hp=20,towers=(Tower(0,0,100,100),),
            platforms=(Platform(0,0,1000,100),),route=(0,))
world=Summon(state,(Wave(2,0,2,0),)*30,trial=0,atom_bonus=200,salt_lick=0,
             meal_points=0,meritoc_points=0,refunds=(3,),
             random_int=lambda low,high:high,popup_profile=PopupProfile(0,False))
world.run_until(15000)
assert (world.clock.credited,world.points,world.remaining_hp)==(1,10004,0)
'''
        with tempfile.TemporaryDirectory() as directory:
            result=subprocess.run([sys.executable,'-I','-S','-c',script,str(source)],
                                  cwd=directory,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':unittest.main()
