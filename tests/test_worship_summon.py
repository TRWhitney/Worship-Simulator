"""Complete controlled summons combine wave, income and purchase clocks."""
import unittest

from worship_sim.models import Tower,Platform,Board
from worship_sim.waves import Wave


class WorshipSummonTests(unittest.TestCase):
    def summon(self,**kwargs):
        from worship_sim.summon import Summon
        from worship_sim.battle import PopupProfile
        state=Board(True,map_id=26,points=10000,hp=20,
            towers=(Tower(0,0,100,100),),platforms=(Platform(0,0,1000,100),),route=(0,))
        return Summon(state,(Wave(2,0,2,0),)*30,trial=0,atom_bonus=200,
            salt_lick=0,meal_points=0,meritoc_points=0,refunds=(3,),
            random_int=lambda low,high:high,popup_profile=PopupProfile(0,False),**kwargs)

    def test_live_wave_cycle_is_used_for_spawn_extension(self):
        summon=self.summon(cycle_length=1)
        summon.clock.wave=summon.wave=30
        summon.clock.countdown=0
        summon.run_until(1100)
        # Last row repeats with extension1: ceil(2*4/3)=3, tier0+2.
        self.assertEqual(summon.clock.queues[0].remaining,2)
        self.assertAlmostEqual(summon.monsters.actors[0].max_hp,38.88)

    def test_complete_wave_clear_credits_score_and_earns_points(self):
        summon=self.summon()
        summon.run_until(15000)
        self.assertEqual((summon.clock.reached,summon.clock.credited,summon.points),(1,1,10004))
        self.assertEqual(summon.remaining_hp,0)

    def test_send_overlaps_spawn_queues_and_adds_the_client_bonus(self):
        summon=self.summon()
        summon.run_until(7100)
        before=summon.points
        self.assertEqual(summon.send(),4)
        self.assertEqual(summon.points,before+4)
        summon.run_until(8100)
        self.assertEqual((summon.clock.wave,summon.clock.reached,summon.clock.credited),(2,2,0))
        self.assertEqual(len(summon.monsters.actors),2)

    def test_send_retains_the_release_callback_until_its_hundred_ms_delay(self):
        summon=self.summon()
        before=summon.loop.pending
        summon.send()
        self.assertEqual(summon.loop.pending,before+1)
        summon.run_until(90)
        self.assertEqual(summon.loop.pending,before+1)
        summon.run_until(100)
        self.assertEqual(summon.loop.pending,before)

    def test_upgrade_and_choice_apply_to_the_active_combat_tower(self):
        from worship_sim.investments import Investment
        summon=self.summon()
        for _ in range(4):self.assertTrue(summon.apply(Investment('upgrade',index=0)))
        self.assertFalse(summon.apply(Investment('upgrade',index=0)))
        self.assertTrue(summon.apply(Investment('choose',index=0,choice='A')))
        self.assertEqual((summon.investment_state.towers[0].level,
                          summon.investment_state.towers[0].choices,summon.points),(5,'A',9847))
        summon.run_until(15000)
        self.assertEqual(summon.clock.credited,1)

    def test_sliced_execution_matches_a_continuous_summon(self):
        direct=self.summon();sliced=self.summon()
        direct.run_until(15000)
        for at in range(10,15001,10):sliced.run_until(at)
        self.assertEqual((direct.points,direct.lives,direct.remaining_hp,direct.clock.credited),
                         (sliced.points,sliced.lives,sliced.remaining_hp,sliced.clock.credited))

    def test_selling_a_kraken_preserves_its_existing_underlings(self):
        from worship_sim.investments import Investment
        summon=self.summon()
        self.assertTrue(summon.apply(Investment('build',tower=Tower(6,0,200,100))))
        summon.run_until(500)
        self.assertEqual(sum(a is not None and a.kind=='projectile' for a in summon.actors),1)
        self.assertTrue(summon.apply(Investment('sell',index=1)))
        summon.run_until(1000)
        self.assertEqual(sum(a is not None and a.kind=='projectile' for a in summon.actors),1)

    def test_build_rejects_a_position_that_overlaps_an_existing_tower(self):
        from worship_sim.investments import Investment
        summon=self.summon()
        self.assertFalse(summon.apply(Investment('build',tower=Tower(6,0,110,100))))
        self.assertEqual(summon.points,10000)

    def test_build_rejects_a_height_inconsistent_with_the_platform(self):
        from worship_sim.investments import Investment
        summon=self.summon()
        self.assertFalse(summon.apply(Investment('build',tower=Tower(6,0,200,1000))))
        self.assertEqual(summon.points,10000)

    def test_defeat_retains_the_pending_fade_and_cleanup_callbacks(self):
        summon=self.summon()
        summon.lives=0
        summon.run_until(20)
        self.assertEqual(summon.wave,-5)
        delays=[t.interval_ms for t in summon.loop._tasks]
        self.assertIn(2500,delays)
        self.assertIn(3200,delays)


if __name__=='__main__':unittest.main()
