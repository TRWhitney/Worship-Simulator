"""Target ordering and eligibility before tower-specific cast checks."""
import unittest
from worship_sim.simulation import Combatant


class WorshipTargetingTests(unittest.TestCase):
    def select(self,enemies,**kwargs):
        from worship_sim.targeting import select_target
        return select_target(enemies,x=100,y=100,radius=200,route=(0,1),directions=(1,-1),**kwargs)

    def test_route_progress_precedes_distance_and_reversed_x_breaks_ties(self):
        enemies=[Combatant(0,0,180,100),Combatant(1,1,180,100),Combatant(2,1,90,100)]
        self.assertIs(self.select(enemies),enemies[2])

    def test_equal_progress_keeps_first_actor_and_range_boundary_is_strict(self):
        first=Combatant(0,0,150,100);second=Combatant(1,0,150,100)
        outside=Combatant(2,1,300,100)
        self.assertIs(self.select([first,second,outside]),first)
        self.assertIsNone(self.select([outside]))

    def test_hitscan_rejects_dead_pet_nonmonster_and_nonworship_candidates(self):
        enemies=[Combatant(0,1,100,0),Combatant(1,1,100,100),Combatant(2,1,100,100),
                 Combatant(3,1,100,100),Combatant(4,1,100,100),Combatant(5,0,120,100)]
        enemies[1].alive=False;enemies[2].pet_status=1;enemies[3].monster_type='Boss'
        enemies[4].worship=False
        self.assertIs(self.select(enemies),enemies[5])

    def test_range_uses_client_distance_approximation_and_strict_boundary(self):
        from worship_sim.targeting import select_target
        enemy=Combatant(0,0,305,100,y=100)
        args=dict(x=100,y=100,route=(0,),directions=(1,))
        self.assertIs(select_target([enemy],radius=200,**args),enemy)
        boundary=Combatant(1,0,300,100,y=100)
        self.assertIsNone(select_target([boundary],radius=200*.9604339,**args))

    def test_radial_hitscan_uses_explicit_shared_alive_flag(self):
        from worship_sim.targeting import can_hit
        enemy=Combatant(0,0,100,100,y=100)
        for flag,want in ((1,True),(0,False),(None,False)):
            self.assertEqual(can_hit(enemy,x=100,y=100,radius=50,alive_flag=flag),want)
        enemy.alive=False
        self.assertTrue(can_hit(enemy,x=100,y=100,radius=50,alive_flag=1))

    def test_map216_excludes_targets_below_y950(self):
        from worship_sim.targeting import select_target
        enemy=Combatant(0,0,100,100);enemy.y=951
        args=dict(x=100,y=950,radius=200,route=(0,),directions=(1,))
        self.assertIsNone(select_target([enemy],map_id=216,**args))
        self.assertIs(select_target([enemy],map_id=26,**args),enemy)

if __name__=='__main__':unittest.main()
