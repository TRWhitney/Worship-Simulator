"""Unrounded zero-angle actor geometry for Worship simulation.

Motion exposes unrounded top-left coordinates while physical translations
accumulate in the actor's raw origin anchor. Centers remove the origin offset.
Animation switches retain the client's anchor conversion and existing XY
tween targets keep their original top-left coordinates.
Collisions, gravity and rotated sprite origins are outside this component.
"""
from dataclasses import dataclass
import math
from numbers import Real

from .motion import Motion
from .simulation import AnimationClock, js_round


def _finite(value, label):
    if not isinstance(value, Real) or isinstance(value, bool):
        raise ValueError(f'{label} must be finite numbers.')
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise ValueError(f'{label} must be finite numbers.') from error
    if not math.isfinite(result):
        raise ValueError(f'{label} must be finite numbers.')
    return result


def _int32(value):
    integer = math.trunc(value) & 0xffffffff
    return integer - 0x100000000 if integer >= 0x80000000 else integer


@dataclass(frozen=True)
class SpriteProfile:
    """One animation identity with cached dimensions and frame durations.

    Reuse the same profile object for the same named animation. Distinct
    objects represent separate animations, even when all metadata matches.
    """
    width: float
    height: float
    frames: tuple[float, ...]
    looping: bool
    origin_x: float | None = None
    origin_y: float | None = None

    def __post_init__(self):
        width = _finite(self.width, 'Sprite dimensions')
        height = _finite(self.height, 'Sprite dimensions')
        try:
            frames = tuple(_finite(value, 'Frame durations') for value in self.frames)
        except TypeError as error:
            raise ValueError('Positive finite frame durations are required.') from error
        if width <= 0 or height <= 0 or not frames or any(value <= 0 for value in frames):
            raise ValueError('Positive finite sprite dimensions and frame durations are required.')
        if not isinstance(self.looping, bool):
            raise ValueError('The animation looping flag must be Boolean.')
        object.__setattr__(self, 'width', width)
        object.__setattr__(self, 'height', height)
        object.__setattr__(self, 'frames', frames)
        object.__setattr__(self, 'origin_x', _finite(
            math.floor(width / 2) if self.origin_x is None else self.origin_x, 'Sprite origins'))
        object.__setattr__(self, 'origin_y', _finite(
            height if self.origin_y is None else self.origin_y, 'Sprite origins'))


class _ActorMotion(Motion):
    def __init__(self, body, left, top):
        self._body = body
        super().__init__(left, top)

    @property
    def x(self):
        return self._body.left

    @x.setter
    def x(self, value):
        self._body.set_left(value)

    @property
    def y(self):
        return self._body.top

    @y.setter
    def y(self, value):
        self._body.set_top(value)

    def _translate(self, dx, dy):
        self._body._translate(dx, dy)

    def _apply_tween(self, x, y):
        self._translate(x - self.x, y - self.y)


class ActorBody:
    def __init__(self, default_profile: SpriteProfile, *, left: float, top: float):
        self._require_profile(default_profile)
        self.default_profile = default_profile
        self._profile = default_profile
        left = _finite(left, 'Actor positions')
        top = _finite(top, 'Actor positions')
        self._offset_x, self._offset_y = self._offsets(default_profile)
        self._real_x, self._real_y = left, top
        self.motion = _ActorMotion(self, left, top)
        self.animation = AnimationClock(default_profile.frames, looping=default_profile.looping)

    @staticmethod
    def _require_profile(profile):
        if not isinstance(profile, SpriteProfile):
            raise ValueError('A validated sprite profile is required.')

    @staticmethod
    def _offsets(profile):
        return (_int32(_int32(profile.origin_x) - profile.width / 2),
                _int32(_int32(profile.origin_y) - profile.height / 2))

    def _translate(self, dx, dy):
        if dx != 0 or dy != 0:
            x = _finite(self._real_x + dx, 'Actor anchors')
            y = _finite(self._real_y + dy, 'Actor anchors')
            self._real_x, self._real_y = x, y

    @property
    def real_x(self):
        return self._real_x

    @property
    def real_y(self):
        return self._real_y

    @property
    def offset_x(self):
        return self._offset_x

    @property
    def offset_y(self):
        return self._offset_y

    @property
    def profile(self) -> SpriteProfile:
        return self._profile

    @property
    def width(self) -> float:
        return self._profile.width

    @property
    def height(self) -> float:
        return self._profile.height

    @property
    def x(self) -> float:
        return self._real_x - self._offset_x

    @property
    def y(self) -> float:
        return self._real_y - self._offset_y

    @property
    def left(self) -> float:
        return (self._real_x - math.floor(self.width / 2)) - self._offset_x

    @property
    def top(self) -> float:
        return (self._real_y - math.floor(self.height / 2)) - self._offset_y

    def get_x(self) -> int:
        return js_round(self.left)

    def get_y(self) -> int:
        return js_round(self.top)

    def set_left(self, value: float) -> None:
        value = _finite(value, 'Actor positions')
        delta = _finite(value + math.floor(self.width / 2) + self._offset_x - self._real_x,
                        'Actor positions')
        self._translate(delta, self._real_y - self._real_y)

    def set_top(self, value: float) -> None:
        value = _finite(value, 'Actor positions')
        delta = _finite(value + math.floor(self.height / 2) + self._offset_y - self._real_y,
                        'Actor positions')
        self._translate(self._real_x - self._real_x, delta)

    def set_x_center(self, value: float) -> None:
        self.set_left(_finite(value, 'Actor centers') - self.width / 2)

    def set_y_center(self, value: float) -> None:
        self.set_top(_finite(value, 'Actor centers') - self.height / 2)

    def set_animation(self, profile: SpriteProfile) -> None:
        """Switch named animation; the same profile object is a no-op."""
        self._require_profile(profile)
        if profile is self._profile:
            return
        self._reset_animation(profile)

    def _reset_animation(self, profile: SpriteProfile) -> None:
        offset_x, offset_y = self._offsets(profile)
        x = _finite((self._real_x / 10 + (offset_x - self._offset_x) / 10) * 10, 'Actor anchors')
        y = _finite((self._real_y / 10 + (offset_y - self._offset_y) / 10) * 10, 'Actor anchors')
        self._profile = profile
        self._offset_x, self._offset_y = offset_x, offset_y
        self._real_x, self._real_y = x, y
        self.animation = AnimationClock(profile.frames, looping=profile.looping)

    def recycle(self) -> None:
        # Engine recycling parks the actor with its current cached dimensions
        # before restoring the default animation and its cached dimensions.
        self.set_left(1e6)
        self.set_top(1e6)
        self.motion.cancel_tween()
        self.motion.vx = 0
        self.motion.vy = 0
        self._reset_animation(self.default_profile)
