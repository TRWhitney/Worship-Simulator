"""Plan comparisons use credited combat outcomes and complete spending sequences."""
from dataclasses import replace
import unittest

from worship_sim.models import Tower,Platform,Board
from worship_sim.waves import Wave


class WorshipSearchTests(unittest.TestCase):
    def state(self):
        return Board(True,map_id=26,points=10000,hp=20,
            platforms=(Platform(0,0,400,100),),route=(0,))

    def factory(self,random_int):
        from worship_sim.summon import Summon
        from worship_sim.battle import PopupProfile
        return Summon(self.state(),(Wave(2,0,2,0),)*30,trial=0,atom_bonus=200,
            salt_lick=0,meal_points=0,meritoc_points=0,refunds=(),random_int=random_int,
            popup_profile=PopupProfile(0,True))

    def test_full_damage_layout_beats_full_support_layout_by_credited_clears(self):
        from worship_sim.search import LayoutPlan,PlanSearch,build_order
        layouts=[tuple(Tower(kind,0,x,100) for x in (80,141,202,263)) for kind in (5,0)]
        plans=tuple(LayoutPlan(str(kind),layout,build_order(self.state(),layout))
                    for kind,layout in zip((5,0),layouts))
        search=PlanSearch(self.factory,plans,horizon_ms=30000,random_seeds=(1,))
        while not search.complete:search.advance(.01)
        self.assertEqual(search.best.plan.name,'0')
        self.assertGreaterEqual(search.best.cleared_wave,2)
        self.assertEqual(len(search.best.plan.layout),4)

    def test_orders_include_pending_choices_and_each_target_level(self):
        from worship_sim.search import build_order
        from worship_sim.investments import Investment
        state=replace(self.state(),towers=(Tower(0,0,80,100,5),))
        layout=(Tower(0,0,80,100,6,'A'),Tower(5,0,141,100,5,'B'))
        actions=build_order(state,layout)
        self.assertIn(Investment('choose',index=0,choice='A'),actions)
        self.assertEqual(sum(a.kind=='build' for a in actions),1)
        self.assertEqual(sum(a.kind=='upgrade' and a.index==0 for a in actions),1)
        self.assertEqual(sum(a.kind=='upgrade' and a.index==1 for a in actions),4)
        self.assertEqual(actions[-1],Investment('choose',index=1,choice='B'))

    def test_zero_cpu_budget_does_not_start_a_candidate(self):
        from worship_sim.search import LayoutPlan,PlanSearch
        calls=[]
        search=PlanSearch(lambda rng:calls.append(rng),(LayoutPlan('empty',(),()),),
                          horizon_ms=1000,random_seeds=(1,))
        search.advance(0)
        self.assertEqual(calls,[])
        self.assertFalse(search.complete)

    def test_horizon_with_enemies_remaining_is_reported_as_inconclusive(self):
        from worship_sim.search import LayoutPlan,PlanSearch
        search=PlanSearch(self.factory,(LayoutPlan('empty',(),()),),horizon_ms=8000,random_seeds=(1,))
        while not search.complete:search.advance(.01)
        self.assertTrue(search.best.inconclusive)
        self.assertEqual(search.best.cleared_wave,0)

    def test_claimed_layout_must_match_its_executable_build_order(self):
        from worship_sim.search import LayoutPlan,PlanSearch
        plan=LayoutPlan('unbuilt',(Tower(0,0,80,100),),())
        search=PlanSearch(self.factory,(plan,),horizon_ms=1000,random_seeds=(1,))
        with self.assertRaises(ValueError):search.advance(.01)

    def test_permanently_invalid_trait_order_is_rejected_before_combat(self):
        from worship_sim.search import LayoutPlan,PlanSearch
        from worship_sim.investments import Investment
        tower=Tower(0,0,80,100)
        plan=LayoutPlan('invalid',(tower,),(Investment('build',tower=tower),
            Investment('choose',index=0,choice='A')))
        search=PlanSearch(self.factory,(plan,),horizon_ms=1000,random_seeds=(1,))
        with self.assertRaises(ValueError):search.advance(.01)

    def test_remaining_health_includes_the_unspawned_wave_debt(self):
        from worship_sim.search import LayoutPlan,PlanSearch
        search=PlanSearch(self.factory,(LayoutPlan('empty',(),()),),horizon_ms=8000,random_seeds=(1,))
        while not search.complete:search.advance(.01)
        self.assertEqual(search.best.remaining_hp,6)

    def test_inconclusive_plans_can_be_compared_again_over_a_longer_common_horizon(self):
        from worship_sim.search import LayoutPlan,PlanSearch,build_order
        layout=tuple(Tower(0,0,x,100) for x in (80,141,202,263))
        plan=LayoutPlan('damage',layout,build_order(self.state(),layout))
        search=PlanSearch(self.factory,(plan,),horizon_ms=8000,random_seeds=(1,))
        while not search.complete:search.advance(.01)
        first=search.best
        search.deepen(30000)
        self.assertFalse(search.complete)
        while not search.complete:search.advance(.01)
        self.assertEqual(search.best.horizon_ms,30000)
        self.assertGreater(search.best.cleared_wave,first.cleared_wave)
        self.assertTrue(search.best.inconclusive)


if __name__=='__main__':unittest.main()
