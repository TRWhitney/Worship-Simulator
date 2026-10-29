"""Actor geometry needed by mixed Worship projectiles."""
import unittest


class WorshipActorTests(unittest.TestCase):
    def test_physics_accumulates_in_the_raw_anchor_before_spawn_truncation(self):
        from worship_sim.actor import ActorBody,SpriteProfile
        body=ActorBody(SpriteProfile(65,50,(100,),False),left=-7,top=250)
        body.motion.vx=2
        for _ in range(750):body.motion.advance_physics(10)
        self.assertEqual(body.real_x,174.99999999999866)
        self.assertEqual(body.left,142.99999999999866)
        self.assertEqual((body.x,body.real_y,body.offset_y),(body.real_x,300,25))

    def body(self):
        from worship_sim.actor import ActorBody,SpriteProfile
        return ActorBody(SpriteProfile(35,33,(100,)*7,True),left=0,top=0)

    def test_creation_uses_default_sprite_before_switching_projectile_animation(self):
        from worship_sim.actor import SpriteProfile
        body=self.body()
        self.assertEqual((body.x,body.y),(17,16))
        body.set_animation(SpriteProfile(66,18,(100,)*6,True))
        self.assertEqual((body.x,body.y,body.left,body.top),(17,16,-16,7))

    def test_setting_center_subtracts_half_width_before_floored_origin(self):
        body=self.body()
        body.set_x_center(100)
        self.assertEqual((body.x,body.left,body.get_x()),(99.5,82.5,83))
        body.set_left(-.5)
        self.assertEqual((body.x,body.get_x()),(16.5,0))

    def test_animation_switch_preserves_center_and_resets_frame_clock(self):
        from worship_sim.actor import SpriteProfile
        body=self.body()
        body.animation.update(110)
        body.set_animation(SpriteProfile(72,80,(80,80,80,100),False))
        self.assertEqual((body.x,body.y,body.animation.frame,body.animation.elapsed_ms),(17,16,0,0))

    def test_animation_identity_distinguishes_same_name_from_equal_metadata(self):
        from worship_sim.actor import SpriteProfile
        body=self.body()
        first=SpriteProfile(66,18,(100,)*6,True)
        body.set_animation(first);body.animation.update(110)
        body.set_animation(first)
        self.assertEqual((body.animation.frame,body.animation.elapsed_ms),(1,10))
        body.set_animation(SpriteProfile(66,18,(100,)*6,True))
        self.assertEqual((body.animation.frame,body.animation.elapsed_ms),(0,0))

    def test_recycle_uses_old_geometry_then_default_animation_and_cancels_motion(self):
        from worship_sim.actor import SpriteProfile
        body=self.body()
        body.set_animation(SpriteProfile(66,18,(100,)*6,True))
        body.motion.move_by(50,0,600)
        body.motion.vx=5
        body.recycle()
        body.motion.advance_tween(600);body.motion.advance_physics(10)
        self.assertEqual((body.x,body.y,body.width,body.height,body.motion.vx),
                         (1000033,1000009,35,33,0))
        self.assertEqual((body.left,body.top),(1000016,999993))


if __name__=='__main__':unittest.main()
