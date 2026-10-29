"""Persistent projectiles with independently verified client event timing."""
import unittest
from dataclasses import dataclass,field

from worship_sim.models import Platform
from worship_sim.damage import apply_hits
from worship_sim.simulation import Combatant,TimerLoop,freeze_velocity
from worship_sim.status import TimedStatus,add_status,void_cleanse
from worship_sim.targeting import can_hit


@dataclass
class EffectEnemy(Combatant):
    max_hp: float=100
    move_speed: float=7
    move_speed_initial: float=7
    moving: bool=True
    frozen: bool=False
    statuses: list=field(default_factory=list)

    @property
    def row_alive(self):return int(self.alive)


class WorshipProjectileWorldTests(unittest.TestCase):
    def make(self,enemies,random_int=None,*,effects=False,on_push=None,is_active=None):
        from worship_sim.projectiles import Projectiles
        loop=TimerLoop();actors={};hits=[];allocated=[]
        def allocate_id():
            value=len(allocated);allocated.append(value);return value
        def hit(enemy,damage,critical):
            dealt=apply_hits(enemy,damage=damage,crit_multiplier=critical)
            hits.append((loop.now_ms,enemy.id,dealt))
        extra={}
        if effects:
            def freeze(enemy,slow,seconds):
                enemy.velocity=freeze_velocity(enemy.velocity,slow)
                enemy.move_speed=abs(enemy.velocity)
                add_status(enemy,'StatusFreeze',6+seconds)
            extra=dict(can_hit=lambda enemy,x,y,radius:can_hit(enemy,x=x,y=y,radius=radius,
                alive_flag=int(enemy.alive)),on_freeze=freeze,on_cleanse=void_cleanse)
        if on_push is not None:
            extra.update(on_push=on_push,is_active=is_active or (lambda:True))
        projectiles=Projectiles(loop,enemies=lambda:enemies,
            platforms={0:Platform(0,0,1000,100),1:Platform(1,0,1000,200)},
            random_int=random_int or (lambda a,b:b),allocate_id=allocate_id,
            on_add=lambda actor:actors.__setitem__(actor.id,actor),
            on_remove=lambda actor:actors.pop(actor.id),on_hit=hit,**extra)
        def advance(end):
            while loop.now_ms<end:
                for actor in actors.values():actor.body.motion.advance_tween(10)
                loop.tick()
                for actor in actors.values():
                    actor.body.motion.advance_physics(10);actor.body.animation.update(10)
        return loop,projectiles,hits,advance

    def test_kraken_contact_damages_then_pushes_and_remains_owned(self):
        enemy=EffectEnemy(0,0,100,100,y=75,width=40);pushes=[];owned=[]
        loop,world,hits,advance=self.make([enemy],effects=True,
            on_push=lambda target,dx:pushes.append((target.id,dx)))
        actor=world.kraken(left=81,top=56,node=0,damage=10,origin_x=100,
            contacts=2,push_direction=-1,underlings=owned)
        owned.append(actor)
        advance(200)
        self.assertEqual(hits,[(200,0,10)])
        self.assertEqual(pushes,[(0,-25)])
        self.assertEqual(owned,[actor])
        self.assertAlmostEqual(actor.body.x,103.4)
        self.assertEqual(actor.motion.vx,-3)

    def test_kraken_corpse_contact_uses_remembered_live_target_without_push(self):
        corpse=EffectEnemy(0,0,100,0,y=75,alive=False)
        survivor=EffectEnemy(1,0,100,100,y=75);pushes=[];owned=[]
        loop,world,hits,advance=self.make([corpse,survivor],effects=True,
            on_push=lambda target,dx:pushes.append((target.id,dx)))
        actor=world.kraken(left=81,top=56,node=0,damage=10,origin_x=100,
            contacts=2,push_direction=-1,underlings=owned)
        owned.append(actor)
        advance(200)
        self.assertEqual(hits,[(200,1,10)])
        self.assertEqual(pushes,[])
        self.assertEqual((corpse.hp,survivor.hp),(0,90))

    def test_kraken_releases_ownership_before_fading_when_battle_is_inactive(self):
        owned=[]
        loop,world,hits,advance=self.make([],effects=True,on_push=lambda target,dx:None,
                                         is_active=lambda:False)
        actor=world.kraken(left=81,top=56,node=0,damage=0,origin_x=100,
            contacts=2,push_direction=-1,underlings=owned)
        owned.append(actor)
        advance(200)
        self.assertEqual(owned,[])
        self.assertTrue(actor.alive)
        advance(490);self.assertFalse(actor.alive)

    def test_boulder_finishes_its_contact_loop_after_budget_exhaustion(self):
        enemies=[EffectEnemy(i,0,121,100,y=75) for i in range(6)]
        loop,world,hits,advance=self.make(enemies,effects=True)
        rock=world.boulder(left=100,top=69,direction=1,node=0,damage=10,
                           duration_seconds=2.5,hit_budget=1,crit_percent=0)
        advance(100)
        self.assertEqual(hits,[(100,i,10) for i in range(6)])
        self.assertAlmostEqual(rock.motion.vx,.23328)
        self.assertEqual(rock.motion.vy,-4)
        advance(390);self.assertFalse(rock.alive)

    def test_boulder_remembers_actor_identity_when_its_hp_changes(self):
        enemy=EffectEnemy(0,0,121,100,y=75)
        loop,world,hits,advance=self.make([enemy],effects=True)
        world.boulder(left=100,top=69,direction=1,node=0,damage=10,
                      duration_seconds=2.5,hit_budget=5,crit_percent=0)
        advance(100);enemy.hp=100
        advance(200)
        self.assertEqual(hits,[(100,0,10)])
        self.assertEqual(enemy.hp,100)

    def test_fireball_launches_then_lands_and_hits_only_the_first_five(self):
        enemies=[EffectEnemy(i,0,100,100,y=75) for i in range(6)]
        loop,world,hits,advance=self.make(enemies,effects=True)
        ball=world.fireball(left=0,top=49,direction=1,node=0,aim_x=100,
            damage=10,radius_percent=100,delay_seconds=0,crit_percent=0)
        advance(10)
        self.assertAlmostEqual(ball.body.x,17.415)
        self.assertEqual((ball.body.y,ball.motion.vy),(64,-10))
        advance(1800)
        self.assertEqual(hits,[(1800,i,10) for i in range(5)])
        self.assertEqual((ball.animation.frame,ball.body.top),(7,78))
        advance(2430);self.assertFalse(ball.alive)

    def test_freeze_hits_across_nodes_and_updates_current_speed_after_damage(self):
        enemies=[EffectEnemy(0,0,120,100,velocity=7),EffectEnemy(1,1,130,100,velocity=-7)]
        loop,world,hits,advance=self.make(enemies,effects=True)
        wave=world.freeze(left=83,top=-16,damage=10,slow_percent=15,
                          extra_seconds=2,crit_percent=0,radius=50)
        self.assertEqual(hits,[(0,0,10),(0,1,10)])
        self.assertEqual([(e.velocity,e.move_speed) for e in enemies],[(2,2),(-2,2)])
        self.assertEqual([[(s.name,s.seconds) for s in e.statuses] for e in enemies],
                         [[('StatusFreeze',8)],[('StatusFreeze',8)]])
        advance(880);self.assertFalse(wave.alive)

    def test_void_hits_before_clearing_and_only_shortens_the_first_status(self):
        enemy=EffectEnemy(0,0,140,5,color=3,statuses=[TimedStatus('StatusBuffHeal',8),
            TimedStatus('StatusSkull16',36000),TimedStatus('StatusNoMove',8)])
        loop,world,hits,advance=self.make([enemy],effects=True)
        wave=world.void(left=83,top=-16,damage=10,crit_percent=0,radius=10)
        self.assertEqual(hits,[(0,0,10)])
        self.assertEqual((enemy.hp,enemy.color),(-5,0))
        self.assertEqual([(s.name,s.seconds) for s in enemy.statuses],
                         [('StatusBuffHeal',1),('StatusSkull16',36000),('StatusNoMove',8)])
        advance(880);self.assertFalse(wave.alive)

    def test_stun_visuals_preserve_recycle_iteration_timing(self):
        loop,world,hits,advance=self.make([])
        first=world.stun(left=100,top=0,duration_seconds=5.6)
        second=world.stun(left=200,top=0,duration_seconds=5.6)
        advance(5790)
        self.assertFalse(first.alive);self.assertTrue(second.alive)
        advance(5800);self.assertFalse(second.alive)

    def test_poison_uses_creation_center_and_keeps_ticking_during_fade(self):
        enemies=[Combatant(0,0,171,100),Combatant(1,0,175,100),Combatant(2,1,117,100)]
        loop,world,hits,advance=self.make(enemies)
        cloud=world.poison(left=100,top=0,node=0,damage=10,duration_seconds=1,
                           tick_seconds=.5,crit_percent=0)
        self.assertEqual((cloud.body.x,cloud.body.y),(117,16))
        advance(1800)
        self.assertEqual(hits,[(500,0,10),(1000,0,10),(1500,0,10)])
        self.assertFalse(cloud.alive)

    def test_storm_hits_retained_target_after_it_loses_eligibility(self):
        enemy=Combatant(0,0,200,5)
        loop,world,hits,advance=self.make([enemy],random_int=lambda a,b:999)
        bolt=world.storm(left=200,top=0,target=enemy,damage=10,crit_percent=100)
        enemy.hp=-5;enemy.alive=False
        advance(240)
        self.assertEqual(hits,[(240,0,15)])
        self.assertEqual(enemy.hp,-20)
        advance(1000)
        self.assertFalse(bolt.alive)

    def test_new_projectile_timers_receive_current_phase_step(self):
        enemy=Combatant(0,0,117,100)
        loop,world,hits,advance=self.make([enemy])
        loop.schedule(100,lambda task:world.poison(left=100,top=0,node=0,damage=10,
            duration_seconds=1,tick_seconds=.5,crit_percent=0))
        advance(600)
        self.assertEqual(hits,[(590,0,10)])

    def test_projectile_pool_reuses_first_allocated_actor_across_animations(self):
        enemy=Combatant(0,0,117,100)
        loop,world,hits,advance=self.make([enemy])
        first=world.poison(left=100,top=0,node=0,damage=0,duration_seconds=2,
                           tick_seconds=1,crit_percent=0)
        second=world.storm(left=200,top=0,target=enemy,damage=0,crit_percent=0)
        advance(2800)
        self.assertFalse(first.alive);self.assertFalse(second.alive)
        reused=world.storm(left=200,top=100,target=enemy,damage=0,crit_percent=0)
        self.assertIs(reused,first)
        self.assertEqual((reused.body.x,reused.body.y),(217,116))


if __name__=='__main__':unittest.main()
