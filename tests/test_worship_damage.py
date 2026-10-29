"""Per-hit tower damage and color effects, separate from death processing."""
import unittest
from worship_sim.simulation import Combatant


class WorshipDamageTests(unittest.TestCase):
    def hit(self,enemy,**kw):
        from worship_sim.damage import apply_hits
        return apply_hits(enemy,damage=10,**kw)

    def test_rounds_each_hit_and_continues_after_hp_crosses_zero(self):
        from worship_sim.damage import apply_hits
        enemy=Combatant(0,0,100,25)
        self.assertEqual(apply_hits(enemy,damage=10.5,crit_multiplier=1.5,hits=2),32)
        self.assertEqual(enemy.hp,-7)
        self.assertTrue(enemy.alive)

    def test_blue_sixth_hit_starts_immunity_and_later_hits_are_zero(self):
        enemy=Combatant(0,0,100,100,color=2)
        self.assertEqual(self.hit(enemy,hits=8),50)
        self.assertEqual((enemy.hp,enemy.hit_counter),(50,-3))
        self.assertEqual(self.hit(enemy),0)

    def test_orange_teleports_each_hit_clamps_left_edge_and_preserves_center(self):
        enemy=Combatant(0,0,180.4,100,velocity=7,color=5,width=40)
        self.assertEqual(self.hit(enemy,hits=3,bounds=(0,200)),30)
        self.assertEqual(enemy.x,210)
        enemy.velocity=-7
        self.hit(enemy,hits=30,bounds=(0,200))
        self.assertEqual(enemy.x,30)

    def test_orange_requires_explicit_bounds(self):
        enemy=Combatant(0,0,100,100,color=5)
        with self.assertRaises(ValueError):self.hit(enemy)

    def test_player_damage_is_one_but_still_triggers_color_effects(self):
        from worship_sim.damage import apply_hits
        enemy=Combatant(0,0,100,100,color=2)
        self.assertEqual(apply_hits(enemy,damage=1e12,hits=6,player=True),5)
        self.assertEqual(enemy.hit_counter,-3)

    def test_value_just_below_half_does_not_round_up(self):
        from worship_sim.damage import apply_hits
        enemy=Combatant(0,0,100,100)
        self.assertEqual(apply_hits(enemy,damage=.49999999999999994),0)
        self.assertEqual(enemy.hp,100)

    def test_unsupported_hit_count_is_rejected_before_mutating_enemy(self):
        from worship_sim.damage import apply_hits
        enemy=Combatant(0,0,100,100)
        with self.assertRaises(ValueError):apply_hits(enemy,damage=10,hits=2147483648)
        self.assertEqual(enemy.hp,100)

if __name__=='__main__':unittest.main()
