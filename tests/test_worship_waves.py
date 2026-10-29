"""Wave table, spawn timing and send rules for simulated build orders."""
import unittest
from worship_sim.simulation import TimerLoop


class WorshipWaveTests(unittest.TestCase):
    def timeline(self,**kw):
        from worship_sim.waves import WaveTimeline,Wave
        loop=TimerLoop()
        waves=(Wave(2,0,2,0),Wave(1,1,3,2))
        events=[]
        timeline=WaveTimeline(loop,waves,cycle_length=2,on_spawn=lambda wave,definition:events.append((loop.now_ms,wave,definition)))
        return loop,timeline,events

    def test_first_wave_starts_after_negative_countdown_and_spawns_next_tenth(self):
        loop,timeline,events=self.timeline()
        loop.run_until(6000)
        self.assertEqual(timeline.wave,0);self.assertEqual(events,[])
        loop.run_until(7000)
        self.assertEqual(timeline.wave,1);self.assertEqual(events,[])
        loop.run_until(10600)
        self.assertEqual([(t,w) for t,w,d in events],[(7100,1),(10600,1)])

    def test_early_send_adds_points_then_starts_on_next_second(self):
        loop,timeline,events=self.timeline()
        loop.run_until(7100)
        self.assertEqual(timeline.send(),4)
        self.assertEqual(timeline.wave,1)
        loop.run_until(8100)
        self.assertEqual(timeline.wave,2)
        self.assertEqual([(t,w) for t,w,d in events],[(7100,1),(8100,2)])

    def test_boss_countdown_disables_send_until_enabled(self):
        from worship_sim.waves import next_wave_countdown,send_bonus
        self.assertEqual([next_wave_countdown(w) for w in (0,1,5,10,11,199,200,201)],
                         [6,15,20,9999,25,25,9999,120])
        self.assertIsNone(send_bonus(10,9999))
        self.assertEqual(send_bonus(9,20),15)
        self.assertEqual(send_bonus(10,2),0)

    def test_cycle_extension_preserves_rows_and_increases_count_and_tier(self):
        from worship_sim.waves import Wave,resolve_wave
        waves=(Wave(2,0,2,0),Wave(3,1,3,2))
        self.assertEqual(resolve_wave(waves,2,cycle_length=2),Wave(3,2,2,0))
        self.assertEqual(resolve_wave(waves,3,cycle_length=2),Wave(4,3,3,2))
        self.assertEqual(waves[0],Wave(2,0,2,0))

if __name__=='__main__':unittest.main()
