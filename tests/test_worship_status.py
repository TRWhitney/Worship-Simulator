"""Worship status state independently observed in original callbacks."""
from dataclasses import dataclass,field
import unittest


@dataclass
class Target:
    statuses: list=field(default_factory=list)
    move_speed: float=3
    move_speed_initial: float=7
    velocity: float=0
    moving: bool=True
    row_alive: int|None=1
    color: int=0
    hit_counter: int=0
    hp: float=40
    max_hp: float=100
    frozen: bool=False


class WorshipStatusTests(unittest.TestCase):
    def target(self,rows=(),**kwargs):
        from worship_sim.status import TimedStatus
        return Target([TimedStatus(name,seconds) for name,seconds in rows],**kwargs)

    def rows(self,target):return [(row.name,row.seconds) for row in target.statuses]

    def test_reapplying_status_replaces_duration_without_changing_order(self):
        from worship_sim.status import add_status,tick_movement
        target=self.target()
        for name,seconds in [('StatusFreeze',6),('StatusSkull16',36000),
                             ('StatusFreeze',2),('StatusBuffHeal',3)]:
            add_status(target,name,seconds)
        self.assertEqual(self.rows(target),[('StatusFreeze',2),('StatusSkull16',36000),('StatusBuffHeal',3)])
        tick_movement(target,direction=1)
        self.assertEqual(self.rows(target),[('StatusSkull16',35998),('StatusBuffHeal',1)])

    def test_freeze_expiration_restores_negative_speed_from_zero_velocity(self):
        from worship_sim.status import tick_movement
        target=self.target([('StatusFreeze',2),('StatusNoMove',4)])
        tick_movement(target,direction=1)
        self.assertEqual((target.move_speed,target.velocity,self.rows(target)),
                         (7,-7,[('StatusNoMove',2)]))
        tick_movement(target,direction=1)
        self.assertEqual((target.move_speed,target.velocity,self.rows(target)),(7,7,[]))

    def test_no_move_keeps_velocity_until_expiration_then_uses_route_direction(self):
        from worship_sim.status import tick_movement
        for direction,velocity in ((1,7),(-1,-7)):
            target=self.target([('StatusNoMove',4)],velocity=3)
            tick_movement(target,direction=direction)
            self.assertEqual((target.move_speed,target.velocity,self.rows(target)),
                             (0,3,[('StatusNoMove',2)]))
            tick_movement(target,direction=direction)
            self.assertEqual((target.move_speed,target.velocity,self.rows(target)),(7,velocity,[]))

    def test_frozen_gate_and_nonpositive_durations_do_not_age(self):
        from worship_sim.status import tick_movement
        target=self.target([('StatusFreeze',0),('StatusNoMove',-1)])
        tick_movement(target,direction=1)
        self.assertEqual((target.move_speed,target.velocity,self.rows(target)),
                         (0,0,[('StatusFreeze',0),('StatusNoMove',-1)]))
        target=self.target([('StatusFreeze',2)],frozen=True)
        tick_movement(target,direction=1)
        self.assertEqual((target.move_speed,target.velocity,self.rows(target)),(3,0,[('StatusFreeze',2)]))

    def test_dead_shared_flag_prevents_expiry_from_changing_velocity(self):
        from worship_sim.status import tick_movement
        for alive in (0,None):
            target=self.target([('StatusFreeze',2)],row_alive=alive)
            tick_movement(target,direction=1)
            self.assertEqual((target.move_speed,target.velocity,self.rows(target)),(7,0,[]))

    def test_color_regeneration_precedes_healing_and_blue_recovery_ignores_hp(self):
        from worship_sim.status import tick_second
        for hp,expected in ((0,0),(.5,10),(49,59),(50,58),(99,100)):
            target=self.target([('StatusBuffHeal',0)],color=3,hp=hp)
            tick_second(target)
            self.assertEqual(target.hp,expected)
        target=self.target(color=2,hp=0,hit_counter=-1)
        tick_second(target)
        self.assertEqual(target.hit_counter,0)

    def test_void_only_shortens_the_first_status_and_empty_list_keeps_color(self):
        from worship_sim.status import void_cleanse
        target=self.target(color=3)
        void_cleanse(target);self.assertEqual(target.color,3)
        for rows,want in (([('StatusFreeze',8),('StatusBuffHeal',8)],
                           [('StatusFreeze',8),('StatusBuffHeal',8)]),
                          ([('StatusBuffHeal',8),('StatusSkull16',8),('StatusNoMove',8)],
                           [('StatusBuffHeal',1),('StatusSkull16',8),('StatusNoMove',8)])):
            target=self.target(rows,color=3,hit_counter=-1)
            void_cleanse(target)
            self.assertEqual((target.color,target.hit_counter,self.rows(target)),(0,-1,want))

    def test_player_poison_is_outside_the_worship_status_contract(self):
        from worship_sim.status import add_status
        with self.assertRaises(ValueError):add_status(self.target(),'StatusPoison',6)


if __name__=='__main__':unittest.main()
