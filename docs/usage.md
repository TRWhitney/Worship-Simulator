# Worship simulator

`worship_sim` is a Python 3.12+ library for controlled Worship battles and
comparisons of complete tower layouts and purchase sequences. Runtime uses only
Python's standard library. The simulator takes explicit board, wave, account,
randomness and clock inputs.

## Run a controlled battle

Install the package from this checkout with `python3 -m pip install -e .`, then:

```python
from worship_sim.headless import Board, Tower, Platform, Summon, PopupProfile, Wave

board = Board(
    True, map_id=26, points=10000, hp=20,
    towers=(Tower(0, 0, 100, 100),),
    platforms=(Platform(0, 0, 1000, 100),), route=(0,),
)
world = Summon(
    board, (Wave(2, 0, 2, 0),) * 30,
    trial=0, atom_bonus=200, salt_lick=0, meal_points=0,
    meritoc_points=0, refunds=(3,),
    random_int=lambda low, high: high,
    popup_profile=PopupProfile(0, False),
)
world.run_until(15000)
print(world.clock.credited, world.points, world.remaining_hp)
# 1 10004.0 0
```

This example uses a synthetic repeated wave table and a controlled random stream.
The board uses placement anchors; Summon derives base and Wizard centers.
`run_until` accepts forward 10ms boundaries. Native monster profiles are included.
Account bonuses and refund balances must be supplied explicitly.

## Compare complete plans

`candidates(board)` returns bounded, legal complete layouts and their investment
orders. `PlanSearch(factory, plans, horizon_ms=60000)` compares them under common
random streams. Its factory takes an integer-random callback and returns a fresh
`Summon` with the same comparison inputs. Call `advance(.003)` until `complete`;
`best` and `results` contain outcomes. Budgets are cooperative between simulation
phases. `deepen` reevaluates every plan over a longer common horizon.

Ranking uses worst credited cleared wave, then lives and remaining health.
Horizon outcomes are lower bounds, not maximum-wave predictions. Community
compositions seed candidate generation after fitting them to current geometry;
historical creator runs are not reproduced by those refits. Existing towers and
earned choices stay fixed, and new placements preserve reserved packing capacity.
Invalid or unsupported placement geometry raises `LayoutUnavailable`.

A normalized forecast starts with an empty current cohort and initialized clocks.
It does not resume arbitrary projectiles, enemy statuses or UI timers from an
active game. The consuming application decides when to create a forecast, how to
follow its purchase sequence and how to present its assumptions.

## Verify the implementation

Run the pure suite without installing the package:

```sh
PYTHONPATH=src python3 -m unittest discover -s tests
```

The independence test runs the public API in a subprocess that forbids overlay,
process-access and GUI imports. Other tests cover packing, native assets,
combat, purchases and complete-plan search.

Development comparison tools extract unchanged functions from an installed
client archive and run them offline in Node. Supply your archive explicitly:

```sh
python3 devtools/check-worship-summon.py --asar /path/to/resources/app.asar
python3 devtools/benchmark-worship-search.py --asar /path/to/resources/app.asar --advisor-defaults
```

The remaining `check-worship-*.py` tools cover individual mechanics. They need no
running client. Live account-cache and asset-memory checks belong to the overlay.

## Publish and consume

After creating the GitHub repository, publish this checkout with:

```sh
git remote add origin https://github.com/TRWhitney/Worship-Simulator.git
git branch -M main
git push -u origin main
```

Idleon-Overlays consumes a pinned commit at `vendor/worship-simulator`, using
`https://github.com/TRWhitney/Worship-Simulator.git` in `.gitmodules`. Push the
simulator commit before publishing the overlay commit that pins it. Fresh overlay
checkouts use `git submodule update --init --recursive`. GNOME and Windows bundles
contain only the runtime package, so installed overlays need no simulator repo.
