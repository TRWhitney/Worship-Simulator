"""Assembled persistent encounters, independently bounded by client callbacks."""
import unittest

from worship_sim.models import Platform
from worship_sim.encounter import CombatTower,EncounterInput
from worship_sim.simulation import Combatant


class PersistentBattleTests(unittest.TestCase):
    def battle(self,*,enemies=None,towers=None,draw=20,points=0,lives=20,random_int=None,helper_y=0,platforms=None,wave=1,reward_bonuses=(0,0,0)):
        from worship_sim.battle import Battle,EnemyProfile,PopupProfile
        scenario=EncounterInput(platforms or (Platform(0,0,10000,100,1),),(0,),
            (CombatTower(0,0,100,75,10,.1,200),) if towers is None else towers,
            (Combatant(1,0,200,20,y=75,width=40),) if enemies is None else enemies,
            wave,points,lives,*reward_bonuses,draw)
        events=[]
        battle=Battle(scenario,enemy_profile=EnemyProfile((100,100),1,50,50),
                      popup_profile=PopupProfile(language=0,hidden=False),
                      random_int=random_int or (lambda low,high:high),helper_y=helper_y,on_event=lambda *event:events.append(event))
        return battle,events

    def test_kraken_prepares_underlings_without_a_target(self):
        from worship_sim.battle import BattleTower
        battle,events=self.battle(towers=(BattleTower(6,0,100,75,10,.1,200),),enemies=())
        battle.run_until(2500)
        underlings=[a for a in battle.actors if a is not None and a.kind=='projectile']
        self.assertEqual(len(underlings),4)
        self.assertEqual([e[0] for e in events if e[1]=='cast'],[500,1000,1500,2000])

    def test_kraken_contact_does_not_use_the_storm_critical_bonus(self):
        from worship_sim.battle import BattleTower
        tower=BattleTower(6,0,100,75,10,100,200,(0,100,0,0,0,0,0,0,0,0))
        battle,events=self.battle(towers=(tower,),
            enemies=(Combatant(1,0,100,100,y=75,width=40),))
        battle.run_until(700)
        self.assertEqual([e for e in events if e[1]=='hit'],[(690,'hit',1,10)])

    def test_kraken_owners_have_separate_underling_caps(self):
        from worship_sim.battle import BattleTower
        battle,_=self.battle(towers=(BattleTower(6,0,100,75,10,.1,200),)*2,enemies=())
        battle.run_until(2500)
        self.assertEqual(sum(a is not None and a.kind=='projectile' for a in battle.actors),8)

    def test_spawn_after_corpse_cleanup_reuses_the_original_actor(self):
        battle,_=self.battle(enemies=(Combatant(1,0,200,10,y=75,width=40),))
        original=battle.monsters.actors[0]
        battle.run_until(1190)
        spawned=battle.spawn(Combatant(2,0,500,30,y=75,width=40))
        self.assertIs(spawned,original)
        self.assertEqual((spawned.source_id,spawned.hp,spawned.x,spawned.y,spawned.velocity),
                         (2,30,500,75,0))
        self.assertTrue(spawned.alive)
        self.assertEqual(battle.monsters.alive(spawned),1)

    def test_spawn_from_a_callback_starts_status_timers_in_the_same_timer_phase(self):
        from worship_sim.battle import BattleEnemy
        from worship_sim.status import TimedStatus
        battle,_=self.battle(towers=(),enemies=())
        enemy=BattleEnemy(2,0,500,100,velocity=1,y=75,width=40,max_hp=100,
            move_speed=1,move_speed_initial=1,moving=True,size=2,
            statuses=(TimedStatus('StatusNoMove',10),TimedStatus('StatusSkull0',36000)))
        battle.loop.schedule(100,lambda task:battle.spawn(enemy))
        battle.run_until(2080)
        self.assertEqual(battle.monsters.actors[0].move_speed,1)
        battle.run_until(2090)
        self.assertEqual(battle.monsters.actors[0].move_speed,0)

    def test_new_moving_enemy_consumes_the_discarded_initial_direction_roll(self):
        rolls=[]
        battle,_=self.battle(towers=(),enemies=(),
            random_int=lambda low,high:(rolls.append((low,high)) or high))
        battle.spawn(Combatant(1,0,200,30,velocity=4,y=75,width=40))
        self.assertEqual(rolls,[(-1,1)])
        self.assertEqual(battle.monsters.actors[0].velocity,4)

    def test_fresh_spawn_truncates_default_sprite_origin_but_pool_reuse_preserves_it(self):
        from worship_sim.battle import Battle,PopupProfile
        from worship_sim.native import trial_profile
        scenario=EncounterInput((Platform(0,0,1000,100),),(0,),(),(),1,0,20,0,0,0,20)
        battle=Battle(scenario,enemy_profile=trial_profile(5).enemy,
                      popup_profile=PopupProfile(0,True),random_int=lambda low,high:high)
        first=battle.spawn(Combatant(1,0,200.5,10,y=277.5,width=45))
        self.assertEqual((first.x,first.y),(200,277))
        first.hp=0;battle.run_until(2000)
        reused=battle.spawn(Combatant(2,0,200.5,10,y=277.5,width=45))
        self.assertIs(reused,first)
        self.assertEqual((reused.x,reused.y),(200.5,277.5))

    def test_sold_and_rebuilt_towers_reuse_the_first_allocated_actors(self):
        battle,_=self.battle(enemies=())
        previous=[a.id for a in battle.actors if a is not None and a.kind in ('base','wizard')]
        battle.remove_tower(0)
        battle.add_tower(CombatTower(4,0,300,75,10,2,200),selection_delay=True)
        current=[a.id for a in battle.actors if a is not None and a.kind in ('base','wizard')]
        self.assertEqual(sorted(current),sorted(previous))

    def test_remaining_health_adds_in_original_monster_order(self):
        battle,_=self.battle(towers=(),enemies=(Combatant(1,0,200,1e16,y=75,width=40),
            Combatant(2,0,210,1,y=75,width=40),Combatant(3,0,220,1,y=75,width=40)))
        self.assertEqual(battle.remaining_hp,1e16)

    def test_enemy_outside_the_worship_route_is_rejected_at_initialization(self):
        with self.assertRaises(ValueError):
            self.battle(towers=(),platforms=(Platform(0,0,1000,100),Platform(1,0,1000,200)),
                enemies=(Combatant(1,1,100,30,y=175,width=40),))

    def test_boulder_cast_hits_after_its_first_registered_contact_tick(self):
        from worship_sim.battle import BattleTower
        battle,events=self.battle(towers=(BattleTower(2,0,100,75,10,100,200),),
            enemies=(Combatant(1,0,130,100,y=75,width=40),))
        battle.run_until(600)
        self.assertEqual([e for e in events if e[1] in ('cast','hit')],
                         [(500,'cast',1,0),(590,'hit',1,10)])

    def test_fireball_cast_has_a_flight_before_damage(self):
        from worship_sim.battle import BattleTower
        battle,events=self.battle(towers=(BattleTower(1,0,22,75,10,100,200),),
            enemies=(Combatant(1,0,100,100,y=75,width=40),))
        battle.run_until(2300)
        self.assertEqual([e for e in events if e[1] in ('cast','hit')],
                         [(500,'cast',1,0),(2290,'hit',1,10)])

    def test_freeze_cast_updates_current_movement_and_status(self):
        from worship_sim.battle import BattleTower
        tower=BattleTower(3,0,100,75,10,100,200,(0,0,0,0,15,2,0,0,0,0))
        battle,events=self.battle(towers=(tower,),
            enemies=(Combatant(1,0,200,100,velocity=7,y=75,width=40),))
        battle.run_until(500)
        enemy=battle.monsters.actors[0]
        self.assertEqual((enemy.hp,enemy.velocity,enemy.move_speed),(90,2,2))
        self.assertEqual([(s.name,s.seconds) for s in enemy.statuses],
                         [('StatusSkull0',36000),('StatusFreeze',8)])
        self.assertEqual([e for e in events if e[1] in ('cast','hit')],
                         [(500,'hit',1,10),(500,'cast',1,0)])

    def test_freeze_holds_when_the_selected_enemy_is_behind_its_facing(self):
        from worship_sim.battle import BattleTower
        battle,events=self.battle(towers=(BattleTower(3,0,100,75,10,100,200),),
            enemies=(Combatant(1,0,50,100,y=75,width=40),))
        battle.run_until(500)
        self.assertEqual(events,[])

    def test_void_half_cooldown_chance_is_strict_and_uses_its_animation_offset(self):
        from worship_sim.battle import BattleTower
        for chance,expected in ((24,[500,2000]),(25,[500])):
            with self.subTest(chance=chance):
                tower=BattleTower(8,0,100,75,0,2,100,(0,0,0,0,25,0,0,0,0,0))
                battle,events=self.battle(towers=(tower,),
                    enemies=(Combatant(1,0,150,100,y=75,width=40),),
                    random_int=lambda low,high:chance if (low,high)==(1,100) else high)
                battle.run_until(2000)
                self.assertEqual([e[0] for e in events if e[1]=='cast'],expected)

    def test_color_one_death_heals_a_nearby_survivor_at_the_next_second(self):
        from worship_sim.battle import BattleEnemy
        from worship_sim.status import TimedStatus
        victim=Combatant(1,0,200,10,y=75,width=40,color=1)
        survivor=BattleEnemy(2,0,190,40,y=75,width=40,max_hp=100,
            move_speed=0,move_speed_initial=0,moving=False,size=2,
            statuses=(TimedStatus('StatusSkull0',36000),))
        battle,_=self.battle(towers=(CombatTower(0,0,100,75,10,100,200),),
                             enemies=(victim,survivor))
        battle.run_until(1000)
        self.assertEqual(battle.monsters.actors[1].hp,48)

    def test_color_four_death_extends_nearby_tower_cooldown(self):
        enemies=(Combatant(1,0,200,10,y=75,width=40,color=4),
                 Combatant(2,0,190,100,y=75,width=40))
        battle,events=self.battle(towers=(CombatTower(0,0,150,75,10,.1,200),),enemies=enemies)
        battle.run_until(1000)
        self.assertEqual([e[0] for e in events if e[1]=='cast'],[500])
        self.assertTrue(any(a is not None and a.kind=='projectile' for a in battle.actors))

    def test_storm_cast_uses_weakened_target_bonus_before_delayed_hit(self):
        from worship_sim.battle import BattleEnemy,BattleTower
        from worship_sim.status import TimedStatus
        enemy=BattleEnemy(1,0,200,20,y=75,width=40,max_hp=100,
            move_speed=0,move_speed_initial=0,moving=False,size=2,
            statuses=(TimedStatus('StatusSkull0',36000),))
        tower=BattleTower(4,0,100,75,10,100,338,(0,0,0,0,200,0,0,0,0,0))
        battle,events=self.battle(towers=(tower,),enemies=(enemy,))
        battle.run_until(740)
        self.assertEqual([e for e in events if e[1] in ('cast','hit','death')],
                         [(500,'cast',1,0),(730,'hit',1,30),(740,'death',1,2)])

    def test_poison_cast_uses_delayed_ticks_and_drawing_phase_death(self):
        from worship_sim.battle import BattleTower
        battle,events=self.battle(towers=(BattleTower(7,0,100,75,10,100,275),))
        battle.run_until(4500)
        self.assertEqual([e for e in events if e[1] in ('cast','hit','death')],
                         [(500,'cast',1,0),(2490,'hit',1,10),
                          (4490,'hit',1,10),(4500,'death',1,2)])

    def test_party_casts_at_its_own_animation_offset_without_damage_or_rng(self):
        from worship_sim.battle import BattleTower
        def unexpected_roll(low,high):raise AssertionError('Party used an attack roll')
        battle,events=self.battle(towers=(BattleTower(5,0,100,75,0,8,250),),
            enemies=(Combatant(1,0,200,100,y=75,width=40),),random_int=unexpected_roll)
        battle.run_until(500)
        self.assertEqual([e for e in events if e[1]=='cast'],[(500,'cast',1,0)])
        self.assertEqual(battle.remaining_hp,100)

    def test_death_uses_the_lowest_matching_skull_once(self):
        from worship_sim.battle import BattleEnemy
        from worship_sim.status import TimedStatus
        enemy=BattleEnemy(1,0,200,10,y=75,width=40,max_hp=10,
            move_speed=0,move_speed_initial=0,moving=False,size=2,
            statuses=(TimedStatus('StatusSkull16',36000),TimedStatus('StatusSkull0',36000)))
        battle,_=self.battle(enemies=(enemy,))
        battle.run_until(500)
        self.assertEqual(battle.points,2)

    def test_death_without_a_skull_status_awards_no_currency(self):
        from worship_sim.battle import BattleEnemy
        enemy=BattleEnemy(1,0,200,10,y=75,width=40,max_hp=10,
            move_speed=0,move_speed_initial=0,moving=False,size=2,statuses=())
        battle,events=self.battle(enemies=(enemy,))
        battle.run_until(500)
        self.assertEqual([e for e in events if e[1]=='death'],[(500,'death',1,0)])
        self.assertEqual(battle.points,0)

    def test_death_reward_uses_size_and_actual_skull_status(self):
        from worship_sim.battle import BattleEnemy
        from worship_sim.status import TimedStatus
        enemy=BattleEnemy(1,0,200,10,y=75,width=40,max_hp=10,
            move_speed=0,move_speed_initial=0,moving=False,size=3,
            statuses=(TimedStatus('StatusSkull5',36000),))
        battle,events=self.battle(enemies=(enemy,),wave=27,reward_bonuses=(25,20,30))
        battle.run_until(500)
        self.assertEqual([e for e in events if e[1]=='death'],[(500,'death',1,690)])
        popup=next(a.popup for a in battle.actors if a is not None and a.kind=='popup')
        self.assertEqual(popup.amount,442)

    def test_size_four_ignores_pulse_knockback(self):
        from worship_sim.battle import BattleEnemy,BattleTower
        from worship_sim.status import TimedStatus
        enemy=BattleEnemy(1,0,200,100,velocity=7,y=75,width=40,max_hp=100,
            move_speed=7,move_speed_initial=7,moving=True,size=4,
            statuses=(TimedStatus('StatusSkull0',36000),))
        tower=BattleTower(0,0,100,75,10,.1,200,(0,0,0,100,0,5,0,0,0,0))
        battle,_=self.battle(enemies=(enemy,),towers=(tower,))
        battle.run_until(500)
        self.assertAlmostEqual(battle.monsters.actors[0].x,235)

    def test_running_point_balance_keeps_client_number_precision(self):
        from worship_sim.battle import BattleEnemy
        from worship_sim.status import TimedStatus
        enemies=tuple(BattleEnemy(i,0,210-i*10,10,y=75,width=40,max_hp=10,
            move_speed=0,move_speed_initial=0,moving=False,size=1,
            statuses=(TimedStatus('StatusSkull0',36000),)) for i in (1,2))
        battle,_=self.battle(enemies=enemies,towers=(CombatTower(0,0,100,75,10,.1,200),)*2,
                            points=9007199254740992.)
        battle.run_until(500)
        self.assertEqual(battle.points,9007199254740992.)

    def test_death_after_lives_reach_zero_awards_no_points_or_popup(self):
        battle,events=self.battle(lives=1,platforms=(Platform(0,0,200,100,1),),
            enemies=(Combatant(1,0,171,20,velocity=7,y=75,width=40),))
        battle.run_until(1000)
        self.assertEqual(battle.lives,0)
        self.assertEqual(battle.points,0)
        self.assertEqual([e for e in events if e[1]=='death'],[(1000,'death',1,0)])
        self.assertFalse(any(a is not None and a.kind=='popup' for a in battle.actors))

    def test_persistent_enemy_status_timers_preserve_movement_before_healing(self):
        from worship_sim.battle import BattleEnemy
        from worship_sim.status import TimedStatus
        enemy=BattleEnemy(1,0,200,100,y=75,width=40,color=3,max_hp=100,
            move_speed=7,move_speed_initial=7,moving=True,size=2,
            statuses=(TimedStatus('StatusBuffHeal',1),TimedStatus('StatusSkull0',36000)))
        battle,_=self.battle(towers=(),enemies=(enemy,))
        battle.run_until(100)
        battle.monsters.actors[0].hp=40
        battle.run_until(1000)
        self.assertEqual(battle.monsters.actors[0].hp,50)
        battle.run_until(2000)
        self.assertEqual(battle.monsters.actors[0].hp,50)
        self.assertEqual([s.name for s in battle.monsters.actors[0].statuses],['StatusSkull0'])

    def test_ordinary_initial_timer_does_not_rescale_maximum_hp(self):
        from worship_sim.battle import BattleEnemy
        enemy=BattleEnemy(1,0,200,40,y=75,width=40,max_hp=100,
            move_speed=0,move_speed_initial=0,moving=False,size=2,statuses=())
        battle,_=self.battle(towers=(),enemies=(enemy,))
        battle.run_until(100)
        self.assertEqual((battle.monsters.actors[0].hp,battle.monsters.actors[0].max_hp),(40,100))

    def test_blue_hit_immunity_counts_each_pulse_hit(self):
        from worship_sim.battle import BattleTower
        tower=BattleTower(0,0,100,75,10,.1,200,(0,0,0,500,0,0,0,0,0,0))
        battle,events=self.battle(towers=(tower,),
            enemies=(Combatant(1,0,200,100,y=75,width=40,color=2),))
        battle.run_until(500)
        self.assertEqual([e for e in events if e[1]=='cast'],[(500,'cast',1,50)])
        self.assertEqual(battle.monsters.actors[0].hit_counter,-3)
        battle.run_until(1000)
        self.assertEqual(battle.monsters.actors[0].hit_counter,-2)

    def test_pulse_multihit_and_crit_rolls_use_strict_thresholds(self):
        from worship_sim.battle import BattleTower
        bonuses=(0,20,0,125,0,0,0,0,0,0)
        tower=BattleTower(0,0,100,75,10,.1,200,bonuses)
        for roll,dealt in ((24,45),(25,30)):
            with self.subTest(roll=roll):
                battle,events=self.battle(towers=(tower,),
                    enemies=(Combatant(1,0,200,100,y=75,width=40),),
                    random_int=lambda low,high:roll if high==100 else 199)
                battle.run_until(500)
                self.assertEqual([e for e in events if e[1]=='cast'],[(500,'cast',1,dealt)])

    def test_pulse_push_uses_rounded_left_position_once_per_hit(self):
        from worship_sim.battle import BattleTower
        bonuses=(0,0,0,100,0,5,0,0,0,0)
        battle,events=self.battle(towers=(BattleTower(0,0,100,75,10,.1,200,bonuses),),
            enemies=(Combatant(1,0,200,100,velocity=7,y=75,width=40),))
        battle.run_until(500)
        self.assertEqual([e for e in events if e[1]=='cast'],[(500,'cast',1,20)])
        self.assertEqual(battle.monsters.actors[0].x,224.7)

    def test_popup_pool_reuses_first_allocated_recycled_actor(self):
        enemies=(Combatant(1,0,200,10,y=75,width=40),
                 Combatant(2,0,190,10,y=75,width=40),
                 Combatant(3,0,600,10,velocity=-7,y=75,width=40))
        towers=(CombatTower(0,0,100,75,10,.1,200),)*2
        battle,_=self.battle(enemies=enemies,towers=towers)
        battle.run_until(500)
        first=next(actor for actor in battle.actors if actor is not None and actor.kind=='popup')
        battle.run_until(4200)
        active=[actor for actor in battle.actors if actor is not None and actor.kind=='popup']
        self.assertEqual(len(active),1)
        self.assertIs(active[0],first)

    def test_helper_y_threshold_uses_the_rounded_actor_getter(self):
        for helper_y in (46.001,53.999):
            with self.subTest(helper_y=helper_y):
                battle,_=self.battle(helper_y=helper_y,
                    enemies=(Combatant(1,0,200,100,y=150,width=40),))
                battle.run_until(100)
                self.assertEqual(battle.monsters.actors[0].y,75)

    def test_helper_normalizes_enemy_y_even_without_a_route_transition(self):
        battle,_=self.battle(enemies=(Combatant(1,0,200,100,y=150,width=40),))
        battle.run_until(100)
        self.assertEqual(battle.monsters.actors[0].y,75)

    def test_two_pulse_towers_choose_next_living_target_in_same_phase(self):
        enemies=(Combatant(1,0,200,10,y=75,width=40),Combatant(2,0,190,10,y=75,width=40))
        towers=(CombatTower(0,0,100,75,10,.1,200),CombatTower(0,0,100,75,10,.1,200))
        battle,events=self.battle(enemies=enemies,towers=towers)
        battle.run_until(500)
        self.assertEqual([(at,kind,who,value) for at,kind,who,value in events if kind in ('cast','death')],
                         [(500,'cast',1,10),(500,'cast',2,10),
                          (500,'death',1,2),(500,'death',2,2)])
        self.assertEqual((battle.points,battle.lives,battle.remaining_hp),(4,20,0))

    def test_corpse_stays_engine_alive_until_cleanup_and_aliases_survivor(self):
        enemies=(Combatant(1,0,200,10,y=75,width=40),Combatant(2,0,1000,100,y=75,width=40))
        battle,events=self.battle(enemies=enemies)
        corpse=battle.monsters.actors[0];survivor=battle.monsters.actors[1]
        battle.run_until(500)
        self.assertTrue(corpse.alive)
        self.assertEqual(battle.monsters.alive(corpse),0)
        battle.run_until(1180)
        self.assertTrue(corpse.alive)
        battle.run_until(1190)
        self.assertFalse(corpse.alive)
        self.assertEqual((corpse.monster_id,survivor.monster_id),(1,1))
        corpse.hp-=10
        self.assertEqual(survivor.hp,90)

    def test_recycled_monster_is_parked_with_its_current_geometry(self):
        battle,_=self.battle(enemies=(Combatant(1,0,200,10,y=75,width=40),))
        corpse=battle.monsters.actors[0]
        battle.run_until(1190)
        self.assertFalse(corpse.alive)
        self.assertEqual((corpse.x,corpse.y,corpse.velocity),(1000020,1000025,0))

    def test_single_pulse_matches_previously_verified_cast_and_reward_trace(self):
        battle,events=self.battle()
        battle.run_until(1000)
        self.assertEqual([e for e in events if e[1] in ('cast','death')],
                         [(500,'cast',1,10),(1000,'cast',1,10),(1000,'death',1,2)])
        self.assertEqual(battle.remaining_hp,0)

    def test_kills_wait_for_draw_and_points_round_after_each_death(self):
        battle,events=self.battle(draw=30,points=.49999999999999994,
                                  enemies=(Combatant(1,0,200,10,y=75,width=40),))
        battle.run_until(500)
        self.assertEqual(battle.points,.49999999999999994)
        battle.run_until(510)
        self.assertEqual(battle.points,3)
        self.assertEqual([e for e in events if e[1]=='death'],[(510,'death',1,3)])

    def test_targeting_uses_shared_alive_flag_separately_from_engine_lifetime(self):
        enemies=(Combatant(1,0,200,10,y=75,width=40),Combatant(2,0,1000,100,y=75,width=40))
        battle,events=self.battle(enemies=enemies)
        corpse=battle.monsters.actors[0]
        battle.run_until(500)
        corpse.hp=100
        battle.run_until(1000)
        self.assertTrue(corpse.alive)
        self.assertEqual([e for e in events if e[1]=='cast'],[(500,'cast',1,10)])

    def test_route_transition_preserves_odd_width_center_rounding(self):
        from worship_sim.battle import Battle,EnemyProfile,PopupProfile
        for node,x,velocity,expected_node,expected_x,lives in (
                (0,380.001,4.146147772912121,1,889.5-0.4146147772912121,20),
                (1,519.999,-4.146147772912121,0,9.5+0.4146147772912121,19)):
            with self.subTest(node=node):
                scenario=EncounterInput((Platform(0,0,400,300,1),Platform(1,500,900,500,-1)),
                    (0,1),(),(Combatant(1,node,x,3,velocity=velocity,
                                      y=275 if node==0 else 475,width=65),),
                    1,0,20,0,0,0,20)
                battle=Battle(scenario,enemy_profile=EnemyProfile((100,)*25,15,50,50),
                              popup_profile=PopupProfile(0,True),random_int=lambda a,b:b)
                battle.run_until(100)
                mob=battle.monsters.actors[0]
                self.assertEqual((mob.node,battle.lives),(expected_node,lives))
                self.assertAlmostEqual(mob.x,expected_x)
                self.assertEqual(mob.y,475 if expected_node==1 else 275)

    def test_battle_input_actors_are_copied(self):
        enemy=Combatant(1,0,200,10,y=75,width=40)
        battle,_=self.battle(enemies=(enemy,))
        battle.run_until(1000)
        self.assertEqual((enemy.hp,enemy.alive),(10,True))


if __name__=='__main__':unittest.main()
