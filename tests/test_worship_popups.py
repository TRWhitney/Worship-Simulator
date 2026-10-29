"""Causal clock behavior of original normal POINTS popups."""
import unittest

from worship_sim.simulation import ActorClock,TimerLoop


class PointPopupTests(unittest.TestCase):
    def make(self,*,language=0,hidden=False):
        from worship_sim.popups import PointPopups
        loop=TimerLoop();owner=ActorClock();events=[]
        def allocate():
            clock=ActorClock();events.append(('create',loop.now_ms,clock));return clock
        def recycle(clock):
            events.append(('recycle',loop.now_ms,clock));loop.recycle(clock)
        return loop,events,PointPopups(loop,owner,allocate=allocate,recycle=recycle,
                                      language=language,hidden=hidden)

    def test_points_merge_before_deployment_and_duplicate_recycles_on_update(self):
        loop,events,popups=self.make()
        first=popups.create(10);second=popups.create(20)
        popups.prepare()
        self.assertEqual((first.amount,first.deployment,second.deployment),(30,1,-1))
        popups.update(second)
        self.assertFalse(second.clock.alive)
        popups.draw(first)
        self.assertEqual(first.deployment,2)
        loop.run_until(3090)
        self.assertTrue(first.clock.alive)
        loop.run_until(3100)
        self.assertFalse(first.clock.alive)
        self.assertEqual([(kind,at) for kind,at,_ in events],
                         [('create',0),('create',0),('recycle',0),('recycle',3100)])

    def test_popup_timers_start_at_first_draw_and_preserve_english_fade_slot(self):
        loop,events,popups=self.make()
        first=popups.create(10);popups.prepare()
        loop.run_until(200)
        popups.draw(first)
        self.assertEqual(loop.pending,3)
        loop.run_until(2790)
        self.assertEqual(loop.pending,2)
        loop.run_until(2800)
        self.assertEqual(loop.pending,1)
        loop.run_until(3300)
        self.assertFalse(first.clock.alive)
        self.assertEqual(events[-1][1],3300)

    def test_language_profile_omits_only_fade_timer(self):
        loop,events,popups=self.make(language=2)
        first=popups.create(10);popups.prepare();popups.draw(first)
        self.assertEqual(loop.pending,2)
        loop.run_until(3100)
        self.assertFalse(first.clock.alive)

    def test_default_negative_language_keeps_the_english_fade_slot(self):
        loop,events,popups=self.make(language=-1)
        first=popups.create(10);popups.prepare();popups.draw(first)
        self.assertEqual(loop.pending,3)
        loop.run_until(3100)
        self.assertFalse(first.clock.alive)

    def test_hidden_points_still_allocate_and_recycle_without_queue_timers(self):
        loop,events,popups=self.make(hidden=True)
        popup=popups.create(10);popups.prepare();popups.draw(popup)
        self.assertFalse(popup.clock.alive)
        self.assertEqual(loop.pending,0)
        self.assertEqual([(kind,at) for kind,at,_ in events],[('create',0),('recycle',0)])

    def test_queue_gate_reopens_after_one_second_and_later_points_stay_separate(self):
        loop,events,popups=self.make()
        first=popups.create(10);popups.prepare();popups.draw(first)
        later=popups.create(20);popups.prepare()
        self.assertEqual(later.deployment,0)
        loop.run_until(990);popups.prepare()
        self.assertEqual(later.deployment,0)
        loop.run_until(1000);popups.prepare()
        self.assertEqual((first.amount,later.amount,later.deployment),(10,20,1))


if __name__=='__main__':unittest.main()
