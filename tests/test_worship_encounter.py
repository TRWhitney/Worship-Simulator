"""Complete isolated fights, with expectations from original client execution."""
import unittest
from worship_sim.models import Platform
from worship_sim.simulation import Combatant


class WorshipEncounterTests(unittest.TestCase):
    def run_fight(self,hp,damage,cooldown,draw=20,points=0):
        from worship_sim.encounter import CombatTower,EncounterInput,run_encounter
        scenario=EncounterInput(
            platforms=(Platform(0,0,10000,100),),route=(0,),
            towers=(CombatTower(kind=0,node=0,x=100,y=75,damage=damage,cooldown=cooldown,radius=200),),
            enemies=(Combatant(1,0,200,hp,y=75,width=40),),
            wave=1,points=points,lives=20,salt_lick=0,meal_points=0,meritoc_points=0,
            draw_interval_ms=draw)
        events=[]
        result=run_encounter(scenario,horizon_ms=100000,random_int=lambda a,b:b,
                             on_event=lambda time,kind,subject,value:events.append((time,kind,subject,value)))
        return result,events

    def test_first_cast_cooldown_rearm_kill_and_reward_agree_with_client(self):
        result,events=self.run_fight(20,10,.1)
        self.assertEqual([t for t,k,s,v in events if k=='cast'],[500,1000])
        self.assertEqual((result.reason,result.elapsed_ms,result.points,result.lives),('cleared',1000,2,20))
        self.assertEqual(result.remaining_hp,0)

    def test_sustained_fight_includes_animation_time_after_each_cooldown(self):
        result,events=self.run_fight(1000,20,1)
        self.assertEqual([t for t,k,s,v in events if k=='cast'],list(range(500,74001,1500)))
        self.assertEqual((result.reason,result.elapsed_ms,result.points),('cleared',74000,2))

    def test_death_and_reward_wait_for_draw_phase(self):
        result,events=self.run_fight(10,10,.1,draw=30)
        self.assertEqual([t for t,k,s,v in events if k=='cast'],[500])
        self.assertEqual((result.elapsed_ms,result.points), (510,2))

    def test_death_reports_point_balance_change_after_client_rounding(self):
        result,events=self.run_fight(10,10,.1,points=.49999999999999994)
        self.assertEqual(result.points,3)
        self.assertEqual([v for t,k,s,v in events if k=='death'],[3])

    def moving_fight(self,direction,lives,horizon):
        from worship_sim.encounter import CombatTower,EncounterInput,run_encounter
        enemy=Combatant(1,0,171 if direction==1 else 29,20,velocity=7*direction,y=75,width=40)
        scenario=EncounterInput(platforms=(Platform(0,0,200,100,direction),),route=(0,),
            towers=(CombatTower(0,0,100,75,0,.1,200),),enemies=(enemy,),
            wave=1,points=0,lives=lives,salt_lick=0,meal_points=0,meritoc_points=0,draw_interval_ms=20)
        events=[]
        result=run_encounter(scenario,horizon_ms=horizon,random_int=lambda a,b:b,
                             on_event=lambda *event:events.append(event))
        return result,events

    def test_moving_enemy_leaks_after_strict_boundary_check_before_physics(self):
        result,events=self.moving_fight(1,1,1000)
        self.assertEqual((result.reason,result.elapsed_ms,result.lives),('defeated',200,0))
        self.assertEqual([t for t,k,s,v in events if k=='leak'],[200])

    def test_reversed_route_has_same_leak_timing(self):
        result,events=self.moving_fight(-1,1,1000)
        self.assertEqual((result.reason,result.elapsed_ms,result.lives),('defeated',200,0))

    def test_surviving_leak_returns_enemy_to_start_without_awarding_points(self):
        result,events=self.moving_fight(1,2,300)
        self.assertEqual((result.reason,result.lives,result.remaining_hp,result.points),('horizon',1,20,0))

if __name__=='__main__':unittest.main()
