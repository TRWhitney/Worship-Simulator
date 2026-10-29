"""Wave credit, Slow Roast and pending HP from original helper/HUD execution."""
import unittest

from worship_sim.waves import Wave


class WorshipControlTests(unittest.TestCase):
    def clock(self,**kwargs):
        from worship_sim.controls import SummonClock
        return SummonClock(None,(Wave(2,0,2,0),)*30,base_hp=3,
                           on_spawn=lambda wave,row:None,**kwargs)

    def test_advancing_wave_resets_roast_after_its_floor_tick(self):
        clock=self.clock(roast_floor=600)
        clock.wave=clock.reached=9;clock.countdown=0;clock.roast=123
        clock.advance_second()
        self.assertEqual((clock.wave,clock.reached,clock.countdown,clock.roast,clock.pending_hp),
                         (10,10,9999,-10,6))
        clock.advance_second()
        self.assertEqual(clock.roast,600)

    def test_spawns_subtract_pending_hp_in_their_original_birth_wave(self):
        clock=self.clock()
        clock.countdown=0;clock.advance_second()
        clock.advance_tenth()
        self.assertEqual(clock.pending_hp,3)
        clock.send();clock.advance_second();clock.advance_tenth()
        self.assertEqual((clock.wave,clock.pending_hp),(2,6))

    def test_credit_waits_for_both_live_enemies_and_pending_hp_to_drain(self):
        clock=self.clock();clock.wave=clock.reached=11;clock.countdown=9999
        clock.pending_hp=.5000001;clock.draw((),lives=20)
        self.assertEqual(clock.credited,0)
        clock.pending_hp=.5;clock.draw((.1,),lives=20)
        self.assertEqual(clock.credited,0)
        clock.draw((0,),lives=20)
        self.assertEqual((clock.credited,clock.countdown),(11,9999))
        clock.pending_hp=0;clock.draw((0,),lives=20)
        self.assertEqual(clock.countdown,20)

    def test_overlapping_sends_do_not_immediately_credit_a_wave(self):
        clock=self.clock();clock.wave=clock.reached=9;clock.countdown=20
        self.assertEqual(clock.send(),15)
        self.assertEqual(clock.wave,9)
        clock.advance_second()
        clock.draw((),lives=20)
        self.assertEqual((clock.reached,clock.credited),(10,0))

    def test_defeat_and_an_open_menu_prevent_wave_credit(self):
        clock=self.clock();clock.wave=clock.reached=10;clock.countdown=9999
        clock.draw((),lives=0)
        self.assertEqual(clock.credited,0)
        clock.draw((),lives=20,menu_open=True)
        self.assertEqual(clock.credited,0)


if __name__=='__main__':unittest.main()
