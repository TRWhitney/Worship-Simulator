"""Isolated Pulse encounters verified against original client callbacks.

This evaluator supports one fresh Pulse tower and one normal enemy with size 2
and skull 0 on a single platform. It does not evaluate general boards or live
battles. Defeat reports the life-zero condition at drawing time; HUD cleanup
and the subsequent rewards screen are outside the model.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
import math
from typing import Literal

from .models import Platform
from .damage import apply_hits
from .simulation import ActorClock, AnimationClock, Combatant, TimerLoop, js_round
from .targeting import select_target


@dataclass(frozen=True)
class CombatTower:
    kind: int
    node: int
    x: float
    y: float
    damage: float
    cooldown: float
    radius: float


@dataclass(frozen=True)
class EncounterInput:
    """Controlled initial state: fresh tower, zero traits, size-2 skull-0 enemy."""
    platforms: tuple[Platform, ...]
    route: tuple[int, ...]
    towers: tuple[CombatTower, ...]
    enemies: tuple[Combatant, ...]
    wave: int
    points: float
    lives: int
    salt_lick: float
    meal_points: float
    meritoc_points: float
    draw_interval_ms: int


@dataclass(frozen=True)
class EncounterResult:
    reason: Literal['cleared', 'defeated', 'horizon']
    elapsed_ms: int
    points: float
    lives: int
    remaining_hp: float


def _validate(scenario: EncounterInput, horizon_ms: int) -> None:
    if len(scenario.platforms) != 1 or len(scenario.towers) != 1 or len(scenario.enemies) != 1:
        raise ValueError('This encounter supports one platform, one Pulse tower and one enemy.')
    platform, tower, enemy = scenario.platforms[0], scenario.towers[0], scenario.enemies[0]
    if (scenario.route != (platform.node,) or tower.node != platform.node
            or enemy.node != platform.node or tower.kind != 0 or platform.direction not in (-1, 1)):
        raise ValueError('Only a single-node Pulse encounter is supported.')
    values = (platform.left, platform.right, platform.y, tower.x, tower.y, tower.damage,
              tower.cooldown, tower.radius, enemy.x, enemy.y, enemy.hp, enemy.width, enemy.velocity,
              scenario.points, scenario.salt_lick, scenario.meal_points, scenario.meritoc_points)
    if not all(math.isfinite(value) for value in values):
        raise ValueError('Encounter inputs must be finite.')
    if (not platform.left+20 <= enemy.x <= platform.right-20
            or not platform.left <= tower.x <= platform.right or platform.right <= platform.left):
        raise ValueError('The encounter must start inside its platform route margins.')
    if (enemy.size != 2 or enemy.freeze_seconds != 0 or enemy.color != 0
            or enemy.hit_counter != 0 or not enemy.alive or not enemy.worship
            or enemy.pet_status != 0 or enemy.monster_type != 'Monster'):
        raise ValueError('Only a living normal worship enemy without effects is supported.')
    if enemy.hp <= 0 or enemy.width < 0 or tower.damage < 0 or tower.cooldown <= 0 or tower.radius <= 0:
        raise ValueError('Enemy geometry, HP and tower statistics must be valid.')
    if (not isinstance(scenario.wave, int) or isinstance(scenario.wave, bool) or scenario.wave < 0
            or not isinstance(scenario.lives, int) or isinstance(scenario.lives, bool) or scenario.lives < 1
            or min(scenario.points, scenario.salt_lick, scenario.meal_points, scenario.meritoc_points) < 0):
        raise ValueError('Wave, points, lives and reward bonuses must be valid.')
    for value in (horizon_ms, scenario.draw_interval_ms):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value % 10:
            raise ValueError('Horizon and draw interval must be whole multiples of 10ms.')
    if scenario.draw_interval_ms == 0:
        raise ValueError('A positive draw interval is required.')
    if horizon_ms >= 36000000:
        raise ValueError('This encounter does not model expiry of the initial skull status.')


def run_encounter(scenario: EncounterInput, *, horizon_ms: int,
                  random_int: Callable[[int, int], int],
                  on_event: Callable[[int, str, int, float], None] | None = None) -> EncounterResult:
    """Run the supported initial state through damage and drawing-phase death.

    Cast events report the selected enemy ID and resolved damage. Death events
    report the enemy ID and change in the rounded point balance. Leak events
    report remaining lives.
    Input actors are copied before use.
    """
    _validate(scenario, horizon_ms)
    enemy = replace(scenario.enemies[0])
    tower, platform = scenario.towers[0], scenario.platforms[0]
    durations = tuple(10000 if frame in (4, 14, 19, 29, 34, 44, 49, 64, 79, 94, 109)
                      else 100 for frame in range(136))
    animation = AnimationClock(durations, looping=True)
    loop = TimerLoop()
    cooldown_remaining = -1.
    points = scenario.points
    lives = scenario.lives
    initial_speed = abs(enemy.velocity)

    def set_center(x):
        # Actor.setXCenter delegates through setX, whose origin uses floor(width/2).
        enemy.x += (x-enemy.width/2+math.floor(enemy.width/2))-enemy.x

    def cooldown_tick(task):
        nonlocal cooldown_remaining, lives
        passed_end = (enemy.x > platform.right-20 if platform.direction == 1
                      else enemy.x < platform.left+20)
        if passed_end:
            if enemy.hp > 0:
                lives -= 1
                if on_event is not None:
                    on_event(loop.now_ms, 'leak', enemy.id, lives)
            else:
                enemy.hp = 0
            set_center(platform.left+10 if platform.direction == 1 else platform.right-10)
            enemy.y = platform.y-25
            left = js_round(enemy.x-math.floor(enemy.width/2))
            enemy.velocity = -initial_speed if left > (platform.left+platform.right)/2 else initial_speed
        if cooldown_remaining > 0:
            cooldown_remaining -= .1
            if cooldown_remaining <= 0:
                animation.set_frame(1)

    def cast_tick(task):
        nonlocal cooldown_remaining
        if animation.frame in (4, 14):
            animation.set_frame(animation.frame)
        if animation.frame != 4:
            return
        target = select_target((enemy,), x=tower.x, y=tower.y, radius=tower.radius,
                               route=scenario.route, directions=(platform.direction,))
        if target is None:
            return
        # The original Pulse consumes both rolls even when the traits are zero.
        random_int(0, 100)
        random_int(0, 1000)
        dealt = apply_hits(target, damage=tower.damage)
        if on_event is not None:
            on_event(loop.now_ms, 'cast', target.id, dealt)
        animation.set_frame(5)
        cooldown_remaining = tower.cooldown

    loop.schedule(100, cooldown_tick, repeat=True, actor=ActorClock())
    loop.schedule(100, cast_tick, repeat=True, actor=ActorClock())
    while loop.now_ms < horizon_ms:
        loop.tick()
        animation.update(loop.step_ms)
        enemy.x += enemy.velocity*loop.step_ms*.01
        if loop.now_ms % scenario.draw_interval_ms != 0:
            continue
        if lives <= 0:
            return EncounterResult('defeated', loop.now_ms, points, lives, max(0, enemy.hp))
        if initial_speed > 0:
            if enemy.x < platform.left:
                set_center(platform.left+1)
                enemy.velocity = -enemy.velocity
            if enemy.x > platform.right:
                set_center(platform.right-1)
                enemy.velocity = -enemy.velocity
        if enemy.hp <= 0:
            enemy.alive = False
            currency = js_round((2+math.floor(scenario.wave/5))*(1+scenario.salt_lick/100))
            reward = math.ceil(currency*(1+scenario.meal_points/100)*(1+scenario.meritoc_points/100))
            previous = js_round(points)
            points = js_round(points+reward)
            if on_event is not None:
                on_event(loop.now_ms, 'death', enemy.id, points-previous)
            return EncounterResult('cleared', loop.now_ms, points, lives, 0)
    return EncounterResult('horizon', loop.now_ms, points, lives, max(0, enemy.hp))
