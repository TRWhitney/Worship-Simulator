"""Native trial profiles checked against original definitions and live assets."""
import unittest


class NativeWorshipTests(unittest.TestCase):
    def test_all_native_trials_keep_definition_and_sprite_heights_separate(self):
        from worship_sim.native import trial_profile
        expected=((26,3,4,65,50,50,6,15,25),(63,5,4,52,54,54,7,16,27),
                  (30,9,5,80,44,42,4,13,21),(107,15,6,60,50,50,6,15,28),
                  (155,30,6,50,50,50,7,16,28),(208,55,3,45,45,45,8,19,28),
                  (259,120,3,68,66,66,6,19,35),(308,250,4,60,60,60,8,18,32))
        for trial,row in enumerate(expected):
            with self.subTest(trial=trial):
                p=trial_profile(trial)
                self.assertEqual((p.map_id,p.base_hp,p.base_speed,p.sprite.width,p.sprite.height,
                    p.enemy.definition_height,p.moving_frame,p.enemy.death_frame,len(p.sprite.frames)),row)

    def test_default_and_native_animation_durations_are_preserved(self):
        from worship_sim.native import trial_profile
        self.assertEqual(trial_profile(0).enemy.default_sprite.frames[-1],10000)
        self.assertEqual(trial_profile(0).sprite.frames[-1],10000)
        self.assertEqual(trial_profile(2).sprite.frames[-1],10000)
        self.assertEqual(trial_profile(1).sprite.frames[22:25],(80,80,80))
        self.assertEqual(trial_profile(5).sprite.frames[-1],1000)

    def test_special_map_uses_its_explicit_trial(self):
        from worship_sim.native import trial_profile
        self.assertEqual(trial_profile(7,map_id=100).map_id,100)
        with self.assertRaises(ValueError):trial_profile(7,map_id=26)


if __name__=='__main__':unittest.main()
