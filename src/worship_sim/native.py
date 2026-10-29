"""Native enemy definitions and animation profiles for the eight Worship trials."""
from dataclasses import dataclass, replace

from .actor import SpriteProfile
from .battle import EnemyProfile


@dataclass(frozen=True)
class TrialProfile:
    map_id: int
    base_hp: float
    base_speed: float
    moving_frame: int
    sprite: SpriteProfile
    enemy: EnemyProfile


def _frames(count, exceptions=()):
    values = [100] * count
    for frame, duration in exceptions:
        values[frame] = duration
    return tuple(values)


_DEFAULT = SpriteProfile(50, 50, _frames(16, ((15, 10000),)), False)


def _profile(map_id, hp, speed, width, height, definition_height, moving, death,
             count, exceptions=()):
    sprite = SpriteProfile(width, height, _frames(count, exceptions), False)
    enemy = EnemyProfile(_frames(count, exceptions), death, height, definition_height, _DEFAULT)
    return TrialProfile(map_id, hp, speed, moving, sprite, enemy)


_TRIALS = (
    _profile(26, 3, 4, 65, 50, 50, 6, 15, 25, ((24, 10000),)),
    _profile(63, 5, 4, 52, 54, 54, 7, 16, 27, ((22, 80), (23, 80), (24, 80))),
    _profile(30, 9, 5, 80, 44, 42, 4, 13, 21, ((20, 10000),)),
    _profile(107, 15, 6, 60, 50, 50, 6, 15, 28),
    _profile(155, 30, 6, 50, 50, 50, 7, 16, 28),
    _profile(208, 55, 3, 45, 45, 45, 8, 19, 28, ((27, 1000),)),
    _profile(259, 120, 3, 68, 66, 66, 6, 19, 35),
    _profile(308, 250, 4, 60, 60, 60, 8, 18, 32),
)


def trial_profile(trial: int, map_id: int | None = None) -> TrialProfile:
    """Return a native trial, or its explicit map100 variant.

    Route geometry and timer phase are supplied separately by the host.
    Profiles reuse their animation identities across calls.
    """
    if isinstance(trial, bool) or not isinstance(trial, int) or not 0 <= trial < len(_TRIALS):
        raise ValueError('A Worship trial from 0 through 7 is required.')
    profile = _TRIALS[trial]
    if map_id is None:
        return profile
    if (isinstance(map_id, bool) or not isinstance(map_id, int)
            or map_id not in (profile.map_id, 100)):
        raise ValueError('The map must match the trial or be the explicit map100 trial.')
    return profile if map_id == profile.map_id else replace(profile, map_id=map_id)
