"""Persistent Worship effect actors with original timer and pool behavior.

The host supplies ordered enemies, actor IDs/storage, hit eligibility, damage
resolution and post-hit status/movement effects.
Other Actor478 attack types are not implemented here.
"""
from collections.abc import Callable, Mapping, Sequence
import math
from numbers import Real
from typing import Generic, TypeVar

from .models import Platform
from .actor import ActorBody, SpriteProfile
from .simulation import ActorClock, CombatantState, TimedTask, TimerLoop, client_distance, js_round


DEFAULT_PROFILE = SpriteProfile(35, 33, (100,) * 7, True)
POISON_PROFILE = SpriteProfile(66, 18, (100,) * 6, True)
STORM_PROFILE = SpriteProfile(72, 80, (80,) * 3 + (100,) * 7, False)
FREEZE_PROFILE = SpriteProfile(72, 23, (80,) * 12, True)
VOID_PROFILE = SpriteProfile(72, 23, (100,) * 12, True)
STUN_PROFILE = SpriteProfile(50, 34, (100,) * 4, True)
FIREBALL_PROFILE = SpriteProfile(30, 28, (80,) * 6 + (10000,) + (80,) * 8, False)
KRAKEN_PROFILE = SpriteProfile(34, 50, (100,) * 7, True)

Target = TypeVar('Target', bound=CombatantState)


def _number(value, *, minimum=None):
    if not isinstance(value, Real) or isinstance(value, bool):
        raise ValueError('Projectile values must be finite numbers.')
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError('Projectile values must be finite numbers.') from error
    if not math.isfinite(result) or minimum is not None and result < minimum:
        raise ValueError('Projectile values exceed the supported finite range.')
    return result


def _int32(value):
    result = math.trunc(value) & 0xffffffff
    return result - 0x100000000 if result >= 0x80000000 else result


class Projectile(ActorClock):
    """One stable Actor478 identity, reused across supported animations."""
    kind = 'projectile'
    __eq__ = object.__eq__
    __hash__ = object.__hash__

    def __init__(self, ident: int, body: ActorBody):
        super().__init__()
        self.id = ident
        self.body = body
        self.fading = False

    @property
    def motion(self):
        return self.body.motion

    @property
    def animation(self):
        return self.body.animation


class Projectiles(Generic[Target]):
    def __init__(self, loop: TimerLoop, *, enemies: Callable[[], Sequence[Target]],
                 platforms: Mapping[int, Platform], random_int: Callable[[int, int], int],
                 allocate_id: Callable[[], int], on_add: Callable[[Projectile], None],
                 on_remove: Callable[[Projectile], None],
                 on_hit: Callable[[Target, float, float], None],
                 can_hit: Callable[[Target, float, float, float], bool] | None = None,
                 on_freeze: Callable[[Target, float, float], None] | None = None,
                 on_cleanse: Callable[[Target], None] | None = None,
                 on_push: Callable[[Target, float], None] | None = None,
                 is_active: Callable[[], bool] | None = None):
        self.loop = loop
        self._enemies = enemies
        self._platforms = platforms
        self._random_int = random_int
        self._allocate_id = allocate_id
        self._on_add = on_add
        self._on_remove = on_remove
        self._on_hit = on_hit
        self._can_hit = can_hit
        self._on_freeze = on_freeze
        self._on_cleanse = on_cleanse
        self._on_push = on_push
        self._is_active = is_active
        self._pool: list[Projectile] = []

    def _acquire(self, left: float, top: float) -> Projectile:
        left, top = _number(left), _number(top)
        actor = next((actor for actor in self._pool if not actor.alive), None)
        if actor is None:
            ident = self._allocate_id()
            if not isinstance(ident, int) or isinstance(ident, bool) or any(p.id == ident for p in self._pool):
                raise ValueError('Projectile allocation requires a unique integer actor ID.')
            # New ActorInstances coerce coordinates to int32. Engine pool reuse
            # passes unrounded coordinates directly to Actor.setXY instead.
            actor = Projectile(ident, ActorBody(DEFAULT_PROFILE, left=_int32(left), top=_int32(top)))
            self._pool.append(actor)
        else:
            actor.body.set_animation(DEFAULT_PROFILE)
            actor.body.animation.set_frame(0)
            actor.body.set_left(left)
            actor.body.set_top(top)
            actor.alive = True
        actor.fading = False
        self._on_add(actor)
        return actor

    def recycle(self, actor: Projectile) -> None:
        if not any(candidate is actor for candidate in self._pool):
            raise ValueError('The projectile does not belong to this pool.')
        if not actor.alive:
            return
        actor.body.recycle()
        self.loop.recycle(actor)
        self._on_remove(actor)

    def _critical(self, percent: float) -> float:
        return 1.5 if percent > self._random_int(0, 1000) / 10 else 1

    def _universal_timer(self, actor: Projectile,
                         callback: Callable[[TimedTask], None] | None = None) -> None:
        # Actor478 registers this after effect-specific initialization timers.
        self.loop.schedule(100, callback or (lambda task: None), repeat=True, actor=actor)

    def _platform(self, node: int) -> Platform:
        if not isinstance(node, int) or isinstance(node, bool) or node not in self._platforms:
            raise ValueError('The projectile requires a known integer platform node.')
        platform = self._platforms[node]
        for value in (platform.left, platform.right, platform.y):
            _number(value)
        return platform

    @staticmethod
    def _direction(direction: int) -> int:
        if type(direction) is not int or direction not in (-1, 1):
            raise ValueError('Projectile direction must be +1 or -1.')
        return direction

    def kraken(self, *, left: float, top: float, node: int, damage: float,
               origin_x: float, contacts: float, push_direction: int,
               underlings: list[Projectile]) -> Projectile:
        can_hit, on_push, is_active = self._can_hit, self._on_push, self._is_active
        if can_hit is None or on_push is None or is_active is None:
            raise ValueError('Kraken requires hit-eligibility, push and battle-active callbacks.')
        platform = self._platform(node)
        damage = _number(damage, minimum=0)
        origin_x = _number(origin_x)
        contacts = _number(contacts, minimum=0)
        push_direction = self._direction(push_direction)
        if not isinstance(underlings, list):
            raise ValueError('Kraken ownership requires a shared actor list.')
        actor = self._acquire(left, top)
        actor.body.set_animation(KRAKEN_PROFILE)
        actor.motion.vx = 3 * (-1) ** self._random_int(1, 2)
        remembered: Target | None = None

        def boundary(task):
            projected = actor.body.get_x() + actor.motion.vx
            if projected > platform.right:
                actor.motion.vx = -3
                actor.body.set_left(-5 + platform.right)
            elif projected < platform.left:
                actor.motion.vx = 3
                actor.body.set_left(10 + platform.left)

        def random_wander(task):
            if self._random_int(1, 4) == 1:
                actor.motion.vx = 3 * (-1) ** self._random_int(1, 2)
            elif self._random_int(1, 4) == 1:
                actor.motion.vx = 0 * actor.motion.vx

        def wander(task):
            nonlocal remembered
            remembered = None
            projected = actor.body.get_x() + actor.motion.vx
            if projected > origin_x + 140 or projected < origin_x - 140:
                actor.motion.vx = -3 if projected > origin_x + 140 else 3
                self.loop.schedule(1000, lambda task: None, actor=actor)
            else:
                self.loop.schedule(1000, random_wander, actor=actor)

        def retire():
            actor.fading = True
            if actor in underlings:
                underlings.remove(actor)
            self.loop.schedule(300, lambda task: self.recycle(actor), actor=actor)

        def contact(task):
            nonlocal remembered, contacts
            if contacts <= 0:
                return
            if not is_active():
                contacts = -1
                retire()
                return
            if remembered is None:
                enemies = self._enemies()
                for index in range(len(enemies)):
                    enemy = enemies[index]
                    if (enemy.node == node and enemy.worship
                            and can_hit(enemy, actor.body.x, actor.body.y, 250)):
                        remembered = enemy
                        break
            if remembered is None:
                return
            remembered_left = js_round(remembered.x - math.floor(remembered.width / 2))
            actor.motion.vx = -3 if actor.body.get_x() > remembered_left else 3
            enemies = self._enemies()
            for index in range(len(enemies)):
                enemy = enemies[index]
                if (enemy.node == node and enemy.worship
                        and client_distance(actor.body.x, 1, enemy.x, 1) < 20):
                    self._on_hit(remembered, max(1, damage), self._critical(contacts))
                    remembered = enemy
                    actor.motion.move_by(-1 * push_direction * (25 + 5 * enemy.size), 0, 600,
                                         easing='quad_out')
                    if enemy.hp > 0:
                        on_push(enemy, push_direction * (50 / enemy.size))
                    contacts = js_round(contacts - 1)
                    if contacts <= 0:
                        retire()
                    break

        self.loop.schedule(100, boundary, repeat=True, actor=actor)
        self.loop.schedule(2000, wander, repeat=True, actor=actor)
        self.loop.schedule(200, contact, repeat=True, actor=actor)
        self._universal_timer(actor)
        return actor

    def boulder(self, *, left: float, top: float, direction: int, node: int,
                damage: float, duration_seconds: float, hit_budget: float,
                crit_percent: float) -> Projectile:
        can_hit = self._can_hit
        if can_hit is None:
            raise ValueError('Boulder requires a hit-eligibility callback.')
        platform = self._platform(node)
        direction = self._direction(direction)
        damage = _number(damage, minimum=0)
        duration_seconds = _number(duration_seconds, minimum=0)
        hit_budget = _number(hit_budget, minimum=0)
        crit_percent = _number(crit_percent, minimum=0)
        if not math.isfinite(1000 * duration_seconds):
            raise ValueError('Projectile timer delays must remain finite.')
        actor = self._acquire(left, top)
        actor.motion.vx = 5 * direction
        contacted: list[Target] = []

        def fade():
            actor.fading = True
            self.loop.schedule(300, lambda task: self.recycle(actor), actor=actor)

        def expire(task):
            if not actor.fading:
                fade()

        def contact(task):
            nonlocal hit_budget
            if actor.fading:
                return
            # The client checks the budget once, before traversing the list.
            if hit_budget > 0:
                enemies = self._enemies()
                for index in range(len(enemies)):
                    enemy = enemies[index]
                    if (not any(previous is enemy for previous in contacted)
                            and enemy.worship and can_hit(enemy, actor.body.x, actor.body.y, 35)):
                        self._on_hit(enemy, damage, self._critical(crit_percent))
                        contacted.append(enemy)
                        hit_budget -= 1
                        if hit_budget <= 0:
                            fade()
                            actor.motion.vx = -.6 * actor.motion.vx
                            actor.motion.vy = -4
            if actor.body.x < platform.left - 5 or actor.body.x > platform.right + 5:
                actor.motion.vx = 0
                actor.motion.vy = -7
                fade()

        self.loop.schedule(1000 * duration_seconds, expire, actor=actor)
        self._universal_timer(actor, contact)
        return actor

    def fireball(self, *, left: float, top: float, direction: int, node: int,
                 aim_x: float, damage: float, radius_percent: float,
                 delay_seconds: float, crit_percent: float) -> Projectile:
        can_hit = self._can_hit
        if can_hit is None:
            raise ValueError('Fireball requires a hit-eligibility callback.')
        platform = self._platform(node)
        self._direction(direction)
        aim_x = _number(aim_x)
        damage = _number(damage, minimum=0)
        radius_percent = _number(radius_percent, minimum=0)
        delay_seconds = _number(delay_seconds, minimum=0)
        crit_percent = _number(crit_percent, minimum=0)
        if not math.isfinite(1000 * delay_seconds):
            raise ValueError('Projectile timer delays must remain finite.')
        actor = self._acquire(left, top)
        actor.body.set_animation(FIREBALL_PROFILE)
        ready = -1

        def allow_landing(task):
            nonlocal ready
            ready = 0

        def accelerate(task):
            if actor.animation.frame < 7:
                actor.motion.vy += 3

        def launch(task):
            actor.motion.vx = (aim_x - actor.body.x) / 20
            actor.motion.vy = -10
            self.loop.schedule(200, allow_landing, actor=actor)
            for index in range(8):
                self.loop.schedule(200 * (1 + index), accelerate, actor=actor)

        def reset_frame(task):
            if actor.animation.frame < 7:
                actor.animation.set_frame(0)

        def land(task):
            nonlocal ready
            if ready != 0 or actor.body.get_y() < platform.y - 22:
                return
            self.loop.schedule(640, lambda task: self.recycle(actor), actor=actor)
            ready = 1
            actor.body.set_top(platform.y - 22)
            actor.motion.vx = actor.motion.vy = 0
            actor.animation.set_frame(7)
            hits = 0
            enemies = self._enemies()
            for index in range(len(enemies)):
                enemy = enemies[index]
                # The original contains() receives numeric aim_x here and
                # returns false; no target identity is excluded by that field.
                if (enemy.worship and can_hit(enemy, actor.body.x, actor.body.y,
                                              radius_percent / 100 * 40) and hits < 5):
                    hits += 1
                    self._on_hit(enemy, damage, self._critical(crit_percent))

        self.loop.schedule(1000 * delay_seconds, launch, actor=actor)
        for index in range(9):
            self.loop.schedule(.56 * (1 + index) * 1000, reset_frame, actor=actor)
        self._universal_timer(actor, land)
        return actor

    def poison(self, *, left: float, top: float, node: int, damage: float,
               duration_seconds: float, tick_seconds: float, crit_percent: float) -> Projectile:
        if not isinstance(node, int) or isinstance(node, bool):
            raise ValueError('A projectile node must be an integer.')
        damage = _number(damage, minimum=0)
        duration_seconds = _number(duration_seconds, minimum=0)
        tick_seconds = _number(tick_seconds, minimum=0)
        crit_percent = _number(crit_percent, minimum=0)
        if not math.isfinite(1000 * tick_seconds) or not math.isfinite(1000 * duration_seconds):
            raise ValueError('Projectile timer delays must remain finite.')
        actor = self._acquire(left, top)
        actor.body.set_animation(POISON_PROFILE)

        def pulse(task):
            enemies = self._enemies()
            for index in range(len(enemies)):
                enemy = enemies[index]
                if (enemy.node == node and enemy.worship and enemy.hp > 0
                        and client_distance(actor.body.x, 1, enemy.x, 1) < 55):
                    self._on_hit(enemy, damage, self._critical(crit_percent))

        def fade(task):
            actor.fading = True
            self.loop.schedule(800, lambda task: self.recycle(actor), actor=actor)

        self.loop.schedule(1000 * tick_seconds, pulse, repeat=True, actor=actor)
        self.loop.schedule(1000 * duration_seconds, fade, actor=actor)
        self._universal_timer(actor)
        return actor

    def storm(self, *, left: float, top: float, target: Target,
              damage: float, crit_percent: float) -> Projectile:
        damage = _number(damage, minimum=0)
        crit_percent = _number(crit_percent, minimum=0)
        actor = self._acquire(left, top)
        actor.body.set_animation(STORM_PROFILE)
        self.loop.schedule(240, lambda task: self._on_hit(target, damage, self._critical(crit_percent)), actor=actor)
        self.loop.schedule(1000, lambda task: self.recycle(actor), actor=actor)
        self._universal_timer(actor)
        return actor

    def _wave(self, *, left: float, top: float, damage: float, crit_percent: float,
              radius: float, profile: SpriteProfile,
              effect: Callable[[Target], None]) -> Projectile:
        if self._can_hit is None:
            raise ValueError('Freeze and Void require a hit-eligibility callback.')
        damage = _number(damage, minimum=0)
        crit_percent = _number(crit_percent, minimum=0)
        radius = _number(radius, minimum=0)
        actor = self._acquire(left, top)
        actor.body.set_animation(profile)
        enemies = self._enemies()
        for index in range(len(enemies)):
            enemy = enemies[index]
            if enemy.worship and self._can_hit(enemy, actor.body.x, actor.body.y, radius):
                self._on_hit(enemy, damage, self._critical(crit_percent))
                effect(enemy)
        self.loop.schedule(880, lambda task: self.recycle(actor), actor=actor)
        self._universal_timer(actor)
        return actor

    def freeze(self, *, left: float, top: float, damage: float, slow_percent: float,
               extra_seconds: float, crit_percent: float, radius: float) -> Projectile:
        on_freeze = self._on_freeze
        if on_freeze is None:
            raise ValueError('Freeze requires a status/movement callback.')
        slow_percent = _number(slow_percent, minimum=0)
        extra_seconds = _number(extra_seconds, minimum=0)
        return self._wave(left=left, top=top, damage=damage, crit_percent=crit_percent,
                          radius=radius, profile=FREEZE_PROFILE,
                          effect=lambda enemy: on_freeze(enemy, slow_percent, extra_seconds))

    def void(self, *, left: float, top: float, damage: float, crit_percent: float,
             radius: float) -> Projectile:
        if self._on_cleanse is None:
            raise ValueError('Void requires a status/color callback.')
        radius = _number(radius, minimum=0)
        return self._wave(left=left, top=top, damage=damage, crit_percent=crit_percent,
                          radius=radius + 40, profile=VOID_PROFILE, effect=self._on_cleanse)

    def stun(self, *, left: float, top: float, duration_seconds: float) -> Projectile:
        duration_seconds = _number(duration_seconds, minimum=0)
        if not math.isfinite(1000 * duration_seconds):
            raise ValueError('Projectile timer delays must remain finite.')
        actor = self._acquire(left, top)
        actor.body.set_animation(STUN_PROFILE)

        def fade(task):
            actor.fading = True
            self.loop.schedule(200, lambda task: self.recycle(actor), actor=actor)

        self.loop.schedule(1000 * duration_seconds, fade, actor=actor)
        self._universal_timer(actor)
        return actor
