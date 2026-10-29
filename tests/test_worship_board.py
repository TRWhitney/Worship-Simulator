"""Normalized mixed-board values observed from original client execution."""
import unittest
from dataclasses import replace

from worship_sim.models import Tower,Board,stats,COEFFICIENTS


class WorshipBoardTests(unittest.TestCase):
    def mixed(self,**kwargs):
        return Board(True,towers=(Tower(0,0,0,0,10,'AB'),Tower(5,0,100,0,10,'AB'),
            Tower(4,0,200,0,10,'BA'),Tower(8,0,1000,0,10,'BA')),**kwargs)

    def calculate(self,state,atom=0):
        from worship_sim.board import board_stats
        return board_stats(state,atom_bonus=atom)

    def test_mixed_board_aura_maps_damage_and_cooldown_match_client(self):
        rows=self.calculate(self.mixed())
        self.assertEqual([{i:v for i,v in enumerate(row.bonuses) if v} for row in rows],
            [{0:25,1:20,3:25,5:5,9:35},{0:50,1:20,9:35},
             {0:25,1:20,4:200,9:35},{4:25,9:35}])
        self.assertEqual([row.damage for row in rows],[42,0,303,134])
        self.assertEqual([row.base_cooldown for row in rows],[2.87,8.23,8.23,11.64])
        self.assertEqual([row.cooldown for row in rows],
                         [2.2960000000000003,5.486666666666667,6.5840000000000005,11.64])
        self.assertEqual([row.radius for row in rows],[168,250,338,64])

    def test_account_multipliers_and_first_choice_doubling_precede_damage_floor(self):
        construction=[1]*9
        for kind,level in ((0,7),(5,4),(4,8),(8,9)):construction[kind]=level
        rows=self.calculate(self.mixed(construction=tuple(construction),double_first=True,
                                       roast_level=2,roast=25),atom=37)
        self.assertEqual([row.damage for row in rows],[192,0,2220,318])
        self.assertEqual([row.cooldown for row in rows],
                         [1.9133333333333333,4.115,5.486666666666667,11.64])
        self.assertEqual([row.radius for row in rows],[168,280,338,70])
        self.assertEqual(rows[1].bonuses[0],100)

    def test_damage_is_not_floored_before_account_boost(self):
        state=Board(True,towers=(Tower(0,0,100,300,10),))
        self.assertEqual(self.calculate(state,atom=35)[0].damage,42)

    def test_party_aura_uses_approximation_and_strict_range_plus_ten(self):
        bound=260/.9604339
        state=Board(True,towers=(Tower(5,0,0,0,10,'A'),
            Tower(0,0,190,190,10),Tower(0,0,bound,0,10),Tower(0,0,bound-1e-7,0,10)))
        rows=self.calculate(state)
        self.assertEqual([row.bonuses[0] for row in rows],[50,25,0,25])

    def test_normalized_cooldown_is_distinct_from_transient_upgrade_value(self):
        state=Board(True,towers=(Tower(0,0,0,0,2),Tower(5,0,100,0,5,'A')))
        row=self.calculate(state)[0]
        self.assertEqual((row.base_cooldown,row.cooldown),(3.75,3.0))

    def test_empty_layout_and_invalid_inputs(self):
        self.assertEqual(self.calculate(Board(True)),())
        state=Board(True,towers=(Tower(7,0,100,300),))
        for bad in (replace(state,construction=(0,)*9),
                    replace(state,towers=(Tower(9,0,100,300),)),
                    replace(state,towers=(Tower(7,0,100,300,1,'A'),))):
            with self.subTest(state=bad),self.assertRaises(ValueError):self.calculate(bad)
        with self.assertRaises(ValueError):self.calculate(state,atom=float('nan'))

    def test_kraken_base_cooldown_preserves_original_expression_order(self):
        for construction,level,expected in ((3,43,6.99),(5,8,7.5),(21,68,4.55)):
            with self.subTest(construction=construction,level=level):
                self.assertEqual(stats(6,level,construction,COEFFICIENTS[6])[2],expected)

if __name__=='__main__':unittest.main()
