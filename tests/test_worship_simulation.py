"""Client timer contracts for the future combat simulator."""
import unittest
from worship_sim.simulation import ActorClock,TimerLoop


class WorshipTimerTests(unittest.TestCase):
    def test_fractional_delays_are_truncated_before_ticking(self):
        loop=TimerLoop();fired=[]
        loop.schedule(2000/1.3,lambda task:fired.append(loop.now_ms),repeat=True)
        loop.run_until(4620)
        self.assertEqual(fired,[1540,3080,4620])

    def test_new_timer_receives_the_current_timer_phase_step(self):
        loop=TimerLoop();fired=[]
        def parent(task):
            loop.schedule(10,lambda task:fired.append(('child',loop.now_ms)))
        loop.schedule(10,parent)
        loop.run_until(10)
        self.assertEqual(fired,[('child',10)])

    def test_actor_pause_and_death_control_timer_lifetime(self):
        actor=ActorClock(paused=True);loop=TimerLoop();fired=[]
        loop.schedule(20,lambda task:fired.append(loop.now_ms),repeat=True,actor=actor)
        loop.run_until(30);self.assertEqual(fired,[])
        actor.paused=False;loop.run_until(50);self.assertEqual(fired,[50])
        actor.alive=False;loop.run_until(100);self.assertEqual(fired,[50])
        self.assertEqual(loop.pending,0)

    def test_large_update_does_not_catch_up_multiple_callbacks(self):
        loop=TimerLoop(step_ms=100);fired=[]
        loop.schedule(10,lambda task:fired.append(loop.now_ms),repeat=True)
        loop.run_until(100)
        self.assertEqual(fired,[100])

    def test_engine_pause_applies_to_unowned_tasks(self):
        loop=TimerLoop();loop.paused=True;fired=[]
        loop.schedule(10,lambda task:fired.append('unowned'))
        loop.schedule(10,lambda task:fired.append('actor'),actor=ActorClock())
        loop.run_until(10);self.assertEqual(fired,['actor'])
        loop.paused=False;loop.run_until(20);self.assertEqual(fired,['actor','unowned'])

    def test_recycling_removes_owned_tasks_during_current_phase(self):
        loop=TimerLoop();actor=ActorClock();events=[]
        loop.schedule(10,lambda task:(events.append('recycle'),loop.recycle(actor)),
                      repeat=True,actor=actor)
        loop.schedule(10,lambda task:events.append('other'))
        loop.run_until(10);events.append('boundary');loop.run_until(20)
        self.assertEqual(events,['recycle','boundary','other'])
        self.assertFalse(actor.alive)
        self.assertEqual(loop.pending,0)

    def test_recycling_an_earlier_owned_task_skips_shifted_timer_once(self):
        loop=TimerLoop();actor=ActorClock();events=[]
        loop.schedule(100,lambda task:events.append('owned'),actor=actor)
        loop.schedule(10,lambda task:(events.append('recycle'),loop.recycle(actor)),actor=actor)
        loop.schedule(10,lambda task:events.append('other'))
        loop.run_until(10);events.append('boundary');loop.run_until(20)
        self.assertEqual(events,['recycle','boundary','other'])


class WorshipProjectileTests(unittest.TestCase):
    def test_poison_ticks_stay_on_node_and_continue_during_fade(self):
        from worship_sim.simulation import Combatant,PoisonPuddle
        loop=TimerLoop();hits=[]
        enemies=[Combatant(0,0,154,100),Combatant(1,0,158,100),
                 Combatant(2,1,100,100),Combatant(3,0,100,0)]
        cloud=PoisonPuddle(loop,node=0,x=100,damage=10,duration_seconds=1,
                           tick_seconds=.5,crit_percent=0,enemies=enemies,
                           random_int=lambda a,b:b,on_hit=lambda e,d:hits.append((loop.now_ms,e.id,d)))
        self.assertEqual(hits,[])
        loop.run_until(2000)
        self.assertEqual(hits,[(500,0,10),(1000,0,10),(1500,0,10)])
        self.assertTrue(cloud.fading)
        self.assertFalse(cloud.clock.alive)

    def test_poison_radius_uses_the_client_distance_approximation(self):
        from worship_sim.simulation import Combatant,PoisonPuddle
        loop=TimerLoop();hits=[]
        enemies=[Combatant(0,0,155,100),Combatant(1,0,158,100)]
        PoisonPuddle(loop,node=0,x=100,damage=10,duration_seconds=1,
                     tick_seconds=.5,crit_percent=0,enemies=enemies,
                     random_int=lambda a,b:b,on_hit=lambda e,d:hits.append(e.id))
        loop.run_until(500)
        self.assertEqual(hits,[0])

    def test_poison_ignores_nonworship_actors_with_positive_hp(self):
        from worship_sim.simulation import Combatant,PoisonPuddle
        loop=TimerLoop();hits=[]
        PoisonPuddle(loop,node=0,x=100,damage=10,duration_seconds=1,
                     tick_seconds=.5,crit_percent=0,
                     enemies=[Combatant(0,0,100,100,worship=False)],
                     random_int=lambda a,b:b,on_hit=lambda e,d:hits.append(e.id))
        loop.run_until(500)
        self.assertEqual(hits,[])

    def test_poison_fraction_just_below_half_matches_client_rounding(self):
        from worship_sim.simulation import Combatant,PoisonPuddle
        loop=TimerLoop();hits=[]
        PoisonPuddle(loop,node=0,x=100,damage=.49999999999999994,duration_seconds=1,
                     tick_seconds=.5,crit_percent=0,enemies=[Combatant(0,0,100,100)],
                     random_int=lambda a,b:b,on_hit=lambda e,d:hits.append(d))
        loop.run_until(500)
        self.assertEqual(hits,[0])

    def test_freeze_uses_current_signed_velocity_and_replaces_duration(self):
        from worship_sim.simulation import Combatant,apply_freeze
        enemy=Combatant(0,0,100,100,velocity=7)
        apply_freeze(enemy,0,0);self.assertEqual((enemy.velocity,enemy.freeze_seconds),(3,6))
        apply_freeze(enemy,0,2);self.assertEqual((enemy.velocity,enemy.freeze_seconds),(1,8))
        enemy.velocity=-7
        apply_freeze(enemy,15,0);self.assertEqual(enemy.velocity,-2)

    def test_freeze_multiplies_by_the_reciprocal_factor_before_rounding(self):
        from worship_sim.simulation import Combatant,apply_freeze
        for initial,expected in ((19,3),(-19,-3)):
            enemy=Combatant(0,0,100,100,velocity=initial)
            apply_freeze(enemy,90,0)
            self.assertEqual(enemy.velocity,expected)

class WorshipAnimationTests(unittest.TestCase):
    def test_frame_boundary_is_strict_and_large_step_advances_once(self):
        from worship_sim.simulation import AnimationClock
        animation=AnimationClock((100,100,100),looping=True)
        animation.update(100)
        self.assertEqual((animation.frame,animation.elapsed_ms),(0,100))
        animation.update(250)
        self.assertEqual((animation.frame,animation.elapsed_ms),(1,250))
        animation.update(0)
        self.assertEqual((animation.frame,animation.elapsed_ms),(2,150))
        animation.update(0)
        self.assertEqual((animation.frame,animation.elapsed_ms),(0,50))

    def test_finished_frame_holds_and_setting_same_frame_resets_clock(self):
        from worship_sim.simulation import AnimationClock
        animation=AnimationClock((100,100),looping=False)
        animation.update(201);animation.update(1)
        self.assertEqual((animation.frame,animation.finished),(1,True))
        animation.set_frame(1)
        self.assertEqual((animation.frame,animation.elapsed_ms,animation.finished),(1,0,False))
        animation.set_frame(99)
        self.assertEqual(animation.frame,0)


if __name__=='__main__':unittest.main()
