"""Worship spawn values independently observed in original initialization."""
import unittest

from worship_sim.waves import Wave


class WorshipSpawningTests(unittest.TestCase):
    def calculate(self,wave,**changes):
        from worship_sim.spawning import spawn_stats
        inputs=dict(base_hp=3,base_speed=4,map_id=26)
        inputs.update(changes)
        return spawn_stats(wave,**inputs)

    def test_first_goblin_uses_trial_hp_and_wave_speed_instead_of_native_hp(self):
        result=self.calculate(Wave(2,0,2,0))
        self.assertEqual((result.hp,result.skull),(3,0))
        self.assertEqual(result.speed,4.146147772912121)

    def test_size_and_tier_multiply_hp_before_status_tier_is_capped(self):
        result=self.calculate(Wave(1,2,3,0))
        self.assertEqual(result.hp,116.64000000000001)
        self.assertEqual(result.skull,2)
        result=self.calculate(Wave(1,20,2,0))
        self.assertEqual(result.hp,3.647299637717079e19)
        self.assertEqual(result.skull,16)

    def test_color_does_not_change_spawn_hp_or_speed(self):
        baseline=self.calculate(Wave(5,2,3,0))
        for color in range(1,6):
            self.assertEqual(self.calculate(Wave(5,2,3,color)),baseline)

    def test_actual_map_308_divides_speed_factor_before_multiplying_base_speed(self):
        result=self.calculate(Wave(2,0,2,0),map_id=308)
        self.assertEqual(result.speed,3.4551231440934345)
        self.assertEqual(result.hp,3)

    def test_account_values_must_be_finite_and_wave_values_valid(self):
        for key,value in (('base_hp',float('nan')),('base_hp',-1),
                          ('base_speed',float('inf')),('base_speed',-1)):
            with self.subTest(key=key),self.assertRaises(ValueError):
                self.calculate(Wave(1,0,2,0),**{key:value})
        for wave in (Wave(1,-1,2,0),Wave(1,0,0,0),Wave(1,0,2,6)):
            with self.subTest(wave=wave),self.assertRaises(ValueError):self.calculate(wave)


if __name__=='__main__':unittest.main()
