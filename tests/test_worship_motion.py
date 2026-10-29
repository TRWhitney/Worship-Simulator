"""Collision-free client movement and knockback tween composition."""
import unittest


class WorshipMotionTests(unittest.TestCase):
    def test_velocity_units_are_ten_pixels_per_second(self):
        from worship_sim.motion import Motion
        actor=Motion(x=100,y=0,vx=7,vy=-2)
        for _ in range(100):actor.advance_physics(10)
        self.assertAlmostEqual(actor.x,170)
        self.assertAlmostEqual(actor.y,-20)

    def test_knockback_tween_overwrites_previous_physics_displacement(self):
        from worship_sim.motion import Motion
        actor=Motion(x=100,y=0,vx=7)
        actor.move_by(-50,0,600)
        observed=[]
        for i in range(1,62):
            actor.advance_tween(10);actor.advance_physics(10)
            if i in (1,30,60,61):observed.append(actor.x)
        for actual,expected in zip(observed,(99.86666666666666,75.7,50.7,51.4)):
            self.assertAlmostEqual(actual,expected)

    def test_new_knockback_retargets_existing_xy_tween(self):
        from worship_sim.motion import Motion
        actor=Motion(x=100,y=0,vx=7)
        actor.move_by(-50,0,600)
        for _ in range(30):actor.advance_tween(10);actor.advance_physics(10)
        actor.move_by(20,0,200)
        for _ in range(20):actor.advance_tween(10);actor.advance_physics(10)
        self.assertAlmostEqual(actor.x,96.4)

    def test_recycling_cancels_pending_knockback(self):
        from worship_sim.motion import Motion
        actor=Motion(x=100,y=0)
        actor.move_by(-50,0,600)
        actor.advance_tween(300)
        actor.cancel_tween()
        actor.advance_tween(300)
        self.assertEqual(actor.x,75)

    def test_kraken_knockback_uses_quadratic_easing_before_physics(self):
        from worship_sim.motion import Motion
        actor=Motion(x=100,y=0,vx=7)
        actor.move_by(-50,0,600,easing='quad_out')
        for _ in range(30):actor.advance_tween(10);actor.advance_physics(10)
        self.assertAlmostEqual(actor.x,63.2)

if __name__=='__main__':unittest.main()
