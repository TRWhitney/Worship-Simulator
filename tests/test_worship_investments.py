"""Investment amounts from independently executed client purchase callbacks."""
import unittest

from worship_sim.models import Tower,Board


class WorshipInvestmentTests(unittest.TestCase):
    def test_build_upgrade_choice_and_sell_preserve_client_rounding(self):
        from worship_sim.investments import Investment,invest
        state=Board(True,points=10000)
        result=invest(state,(),Investment('build',tower=Tower(0,0,100,300)))
        self.assertEqual((result.state.points,result.refunds),(9996,(3,)))
        for points,refund,level in ((9989,7,2),(9970,18,3),(9928,43,4),(9843,94,5)):
            result=invest(result.state,result.refunds,Investment('upgrade',index=0))
            self.assertEqual((result.state.points,result.refunds[0],result.state.towers[0].level),
                             (points,refund,level))
        self.assertIsNone(invest(result.state,result.refunds,Investment('upgrade',index=0)))
        result=invest(result.state,result.refunds,Investment('choose',index=0,choice='A'))
        self.assertEqual((result.state.points,result.state.towers[0].choices),(9843,'A'))
        result=invest(result.state,result.refunds,Investment('upgrade',index=0))
        self.assertEqual((result.state.points,result.refunds),(9681,(191,)))
        result=invest(result.state,result.refunds,Investment('sell',index=0))
        self.assertEqual((result.state.points,result.refunds,result.state.towers),(9872,(),()))

    def test_upgrade_writes_bare_cooldown_without_recomputing_other_traits(self):
        from worship_sim.investments import Investment,invest
        state=Board(True,points=10000,towers=(Tower(0,0,100,300,5,'A'),))
        result=invest(state,(94,),Investment('upgrade',index=0))
        self.assertFalse(result.recompute)
        self.assertEqual(result.cooldown_override,(0,3.2))

    def test_pending_choice_on_another_tower_does_not_block_upgrade(self):
        from worship_sim.investments import Investment,invest
        state=Board(True,points=10000,towers=(Tower(0,0,100,300,5),Tower(0,0,200,300)))
        result=invest(state,(94,3),Investment('upgrade',index=1))
        self.assertEqual(result.state.towers[1].level,2)

    def test_insufficient_points_and_unearned_choices_do_not_mutate_state(self):
        from worship_sim.investments import Investment,invest
        state=Board(True,points=3,towers=(Tower(0,0,100,300),))
        self.assertIsNone(invest(state,(3,),Investment('upgrade',index=0)))
        self.assertIsNone(invest(state,(3,),Investment('choose',index=0,choice='B')))
        self.assertEqual((state.points,state.towers[0].level),(3,1))


if __name__=='__main__':unittest.main()
