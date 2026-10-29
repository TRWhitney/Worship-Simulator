"""Complete candidate arrangements preserve known packing capacity."""
from dataclasses import replace
import unittest
from worship_sim.models import Tower,Platform,Board
from worship_sim.layout import completion_plan


class WorshipCandidateTests(unittest.TestCase):
    def state(self):
        return Board(True,map_id=26,platforms=(Platform(0,0,400,300),),route=(0,))

    def test_every_new_placement_preserves_the_full_packing_capacity(self):
        from worship_sim.candidates import candidates
        state=self.state();capacity=len(completion_plan(state))
        plans=candidates(state,limit=12,max_towers=4,target_level=10)
        self.assertGreater(len(plans),1)
        for plan in plans:
            built=state
            for tower in plan.layout:
                built=replace(built,towers=built.towers+(tower,))
                self.assertEqual(len(built.towers)+len(completion_plan(built)),capacity)
            self.assertEqual(len(plan.layout),capacity)

    def test_existing_towers_and_choices_remain_the_prefix_of_each_plan(self):
        from worship_sim.candidates import candidates
        tower=Tower(7,0,80,300,15,'ABA')
        state=replace(self.state(),towers=(tower,))
        for plan in candidates(state,limit=6,max_towers=4,target_level=20):
            fixed=plan.layout[0]
            self.assertEqual((fixed.kind,fixed.node,fixed.x,fixed.y),(7,0,80,300))
            self.assertTrue(fixed.choices.startswith('ABA'))
            self.assertGreaterEqual(fixed.level,15)

    def test_locked_towers_are_replaced_by_available_damage(self):
        from worship_sim.candidates import candidates
        state=replace(self.state(),construction=(1,0,0,0,0,0,0,0,0))
        plans=candidates(state,limit=6,max_towers=4,target_level=10)
        self.assertTrue(plans)
        self.assertTrue(all(t.kind==0 for p in plans for t in p.layout))


if __name__=='__main__':unittest.main()
