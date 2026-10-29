"""Death point and popup amounts from original Worship kill callbacks."""
import unittest


class WorshipRewardTests(unittest.TestCase):
    def reward(self,skull,size,/,wave=27,**changes):
        from worship_sim.rewards import skull_reward
        values=dict(skull=skull,size=size,wave=wave,salt_lick=25,meal_points=20,meritoc_points=30)
        values.update(changes)
        return skull_reward(**values)

    def test_size_tier_and_reward_bonuses_match_full_original_kills(self):
        for skull,size,points,popup in ((0,1,5,4),(3,2,74,47),(5,3,690,442),
                                       (16,4,61870,39660),(16,2,15468,9915)):
            with self.subTest(skull=skull,size=size):
                reward=self.reward(skull,size)
                self.assertEqual((reward.points,reward.popup),(points,popup))

    def test_points_use_current_wave_and_popup_omits_meal_and_merit_bonuses(self):
        first=self.reward(0,2,wave=1,salt_lick=0,meal_points=0,meritoc_points=0)
        later=self.reward(0,2,wave=27,salt_lick=0,meal_points=0,meritoc_points=0)
        self.assertEqual((first.points,first.popup,later.points,later.popup),(2,2,7,7))
        boosted=self.reward(0,2,wave=27,salt_lick=0)
        self.assertEqual((boosted.points,boosted.popup),(11,7))

    def test_skull_six_can_create_a_zero_amount_popup(self):
        reward=self.reward(6,2,wave=0,salt_lick=0,meal_points=0,meritoc_points=0)
        self.assertEqual((reward.points,reward.popup),(0,0))

    def test_invalid_inputs_and_nonfinite_account_bonuses_are_rejected(self):
        for change in ({'skull':17},{'size':0},{'wave':-1},{'salt_lick':float('nan')},
                       {'meal_points':-1},{'meritoc_points':float('inf')}):
            with self.subTest(change=change),self.assertRaises(ValueError):self.reward(0,2,**change)


if __name__=='__main__':unittest.main()
