"""Persistent actor slots and shared monster indices for worship simulation.

Actor identity, actor iteration order and monster-array indices are distinct.
Removed monster references retain their old array index, including its aliases.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Generic, Protocol, TypeVar


T = TypeVar('T')


class _ActorIterator(Iterator[T | None]):
    def __init__(self, keys: list[int | None], values: list[T | None]):
        self.reset(keys, values)

    def reset(self, keys: list[int | None], values: list[T | None]) -> None:
        self._keys = keys
        self._values = values
        self._limit = len(keys)
        self._index = 0
        self._scan()

    def _scan(self) -> None:
        while self._index < self._limit and self._keys[self._index] is None:
            self._index += 1

    def __next__(self) -> T | None:
        if self._index >= self._limit:
            raise StopIteration
        value = self._values[self._index]
        self._index += 1
        self._scan()
        return value


class ActorTable(Generic[T]):
    """Unique actor keys in original IntHashTable slot and iterator order.

    Removal pushes a free slot onto a stack. Growth doubles capacity and
    replaces the backing arrays while preserving every occupied slot. An
    iterator keeps its original arrays and preselects its next occupied slot;
    deleting that selected slot before next() therefore yields None. With
    reuse_iterator=True, each iteration resets the same cached iterator, as
    Engine.allActors does, including when an outer iteration is still active.
    """
    def __init__(self, capacity: int = 256, reuse_iterator: bool = False):
        if (not isinstance(capacity, int) or isinstance(capacity, bool)
                or capacity < 2 or capacity & (capacity-1)):
            raise ValueError('Actor capacity must be a power of two of at least two.')
        self._keys: list[int | None] = [None]*capacity
        self._values: list[T | None] = [None]*capacity
        self._next = list(range(1, capacity))+[-1]
        self._free = 0
        self._indices: dict[int, int] = {}
        self._reuse_iterator = reuse_iterator
        self._iterator: _ActorIterator[T] | None = None

    @property
    def capacity(self) -> int:
        return len(self._keys)

    def add(self, key: int, value: T) -> None:
        if (not isinstance(key, int) or isinstance(key, bool)
                or not -0x80000000 < key <= 0x7fffffff):
            raise ValueError('Actor keys must be supported signed 32-bit integers.')
        if key in self._indices:
            raise ValueError('An actor key cannot be registered twice.')
        if self._free == -1:
            capacity = self.capacity
            self._keys = self._keys+[None]*capacity
            self._values = self._values+[None]*capacity
            self._next = self._next+list(range(capacity+1, capacity*2))+[-1]
            self._next[capacity-1] = capacity
            self._free = capacity
        index = self._free
        self._free = self._next[index]
        self._keys[index] = key
        self._values[index] = value
        self._indices[key] = index

    def remove(self, key: int) -> bool:
        index = self._indices.pop(key, None)
        if index is None:
            return False
        self._keys[index] = None
        self._values[index] = None
        self._next[index] = self._free
        self._free = index
        return True

    def __iter__(self) -> Iterator[T | None]:
        if self._reuse_iterator:
            if self._iterator is None:
                self._iterator = _ActorIterator(self._keys, self._values)
            else:
                self._iterator.reset(self._keys, self._values)
            return self._iterator
        return _ActorIterator(self._keys, self._values)


class MonsterActor(Protocol):
    monster_id: int


M = TypeVar('M', bound=MonsterActor)


class MonsterTable(Generic[M]):
    """Ordered actors and 1-based shared arrays with explicitly supplied slot 0.

    Numeric HP access converts missing entries to zero. Alive and will-die
    access preserve missing entries as None. Writes through stale references
    can extend an array or change a survivor at the removed actor's old index.
    """
    def __init__(self, *, hp_sentinel: float | None, alive_sentinel: int | None,
                 will_die_sentinel: int | None):
        self.actors: list[M] = []
        self._hp: list[float | None] = [hp_sentinel]
        self._alive: list[int | None] = [alive_sentinel]
        self._will_die: list[int | None] = [will_die_sentinel]

    def add(self, actor: M, hp: float, *, alive: int = 1, will_die: int = 0) -> None:
        if any(existing is actor for existing in self.actors):
            raise ValueError('A monster actor cannot be registered twice.')
        actor.monster_id = len(self.actors)+1
        self.actors.append(actor)
        self.set_hp(actor, hp)
        self.set_alive(actor, alive)
        self.set_will_die(actor, will_die)

    def remove(self, actor: M) -> None:
        index = next((i for i, existing in enumerate(self.actors) if existing is actor), None)
        if index is None:
            raise ValueError('The monster actor is not registered.')
        if actor.monster_id != index+1:
            raise ValueError('The registered monster index is inconsistent.')
        self.actors.pop(index)
        self._hp.pop(index+1)
        self._alive.pop(index+1)
        self._will_die.pop(index+1)
        for following in self.actors[index:]:
            following.monster_id -= 1

    def hp(self, actor: MonsterActor) -> float:
        index = actor.monster_id
        value = self._hp[index] if 0 <= index < len(self._hp) else None
        return 0 if value is None else value

    def set_hp(self, actor: MonsterActor, value: float) -> None:
        self._write(self._hp, actor.monster_id, value)

    def alive(self, actor: MonsterActor) -> int | None:
        index = actor.monster_id
        return self._alive[index] if 0 <= index < len(self._alive) else None

    def set_alive(self, actor: MonsterActor, value: int) -> None:
        self._write(self._alive, actor.monster_id, value)

    def will_die(self, actor: MonsterActor) -> int | None:
        index = actor.monster_id
        return self._will_die[index] if 0 <= index < len(self._will_die) else None

    def set_will_die(self, actor: MonsterActor, value: int) -> None:
        self._write(self._will_die, actor.monster_id, value)

    @staticmethod
    def _write(values: list[T | None], index: int, value: T) -> None:
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ValueError('Shared array writes need a nonnegative integer index.')
        if index >= len(values):
            values.extend([None]*(index-len(values)+1))
        values[index] = value
