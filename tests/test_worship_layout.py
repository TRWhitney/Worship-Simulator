"""Geometry acceptance independent of combat scoring."""
import itertools
import math
import unittest
from worship_sim.models import Platform,Tower,Board
from worship_sim.layout import completion_plan,LayoutUnavailable


class WorshipLayoutTests(unittest.TestCase):
    def state(self,**kw):
        return Board(True,platforms=(Platform(0,0,400,300),),route=(0,),**kw)

    def test_complete_plan_preserves_four_slots(self):
        plan=completion_plan(self.state())
        self.assertEqual(tuple((n,x) for n,x in plan),((0,80),(0,141),(0,202),(0,263)))

    def test_fixed_center_records_the_existing_capacity_loss(self):
        plan=completion_plan(self.state(towers=(Tower(7,0,200,300),)))
        self.assertEqual(len(plan)+1,3)
        self.assertTrue(all(abs(x-200)>=61 for _,x in plan))

    def test_portal_splits_are_respected(self):
        plan=completion_plan(self.state(portals=((0,200),)))
        self.assertEqual(tuple(x for _,x in plan),(80,260))

    def test_reversed_route_has_the_same_reserved_ends(self):
        s=Board(True,platforms=(Platform(0,0,400,300,-1),),route=(0,))
        self.assertEqual(completion_plan(s),completion_plan(self.state()))

    def test_overlapping_fixed_towers_are_reported(self):
        with self.assertRaises(LayoutUnavailable):
            completion_plan(self.state(towers=(Tower(0,0,150,300),Tower(0,0,200,300))))

    def test_small_platform_results_match_exhaustive_combinations(self):
        for width in (70,90,123,150):
            for portal in ((),((0,60),)):
                # A non-route platform has 30px margins but no route-end reserves.
                s=Board(True,platforms=(Platform(0,0,width,300),),portals=portal)
                allowed=tuple(x for x in range(30,width-29) if all(abs(x-px)>=60 for _,px in portal))
                expected=0
                for count in range(1+(width-60)//61+1):
                    if any(all(b-a>=61 for a,b in zip(xs,xs[1:])) for xs in itertools.combinations(allowed,count)):
                        expected=count
                self.assertEqual(len(completion_plan(s)),expected)

    def test_leftmost_completion_matches_exhaustive_fixed_and_route_cases(self):
        for width, route in ((122,()),(183,()),(260,(0,))):
            for direction in (-1,1):
                for portals in ((),((0,91),)):
                    for fixed_x in (None,90):
                        towers=() if fixed_x is None else (Tower(0,0,fixed_x,300),)
                        s=Board(True,platforms=(Platform(0,0,width,300,direction),),
                                       route=route,portals=portals,towers=towers)
                        lo,hi=(80,width-80) if route else (30,width-30)
                        fixed_valid=fixed_x is None or (
                            lo<=fixed_x<=hi and all(abs(fixed_x-px)>=60 for _,px in portals))
                        if not fixed_valid:
                            with self.subTest(width=width,route=route,direction=direction,
                                              portals=portals,fixed_x=fixed_x):
                                with self.assertRaises(LayoutUnavailable):
                                    completion_plan(s)
                            continue
                        allowed=tuple(x for x in range(lo,hi+1)
                                      if all(abs(x-px)>=60 for _,px in portals)
                                      and all(abs(x-t.x)>=61 for t in towers))
                        expected=()
                        for count in range(1+max(0,hi-lo)//61,-1,-1):
                            match=next((xs for xs in itertools.combinations(allowed,count)
                                        if all(b-a>=61 for a,b in zip(xs,xs[1:]))),None)
                            if match is not None:
                                expected=tuple((0,x) for x in match)
                                break
                        with self.subTest(width=width,route=route,direction=direction,
                                          portals=portals,fixed_x=fixed_x):
                            self.assertEqual(completion_plan(s),expected)

    def test_strict_portal_boundaries_are_legal(self):
        s=Board(True,platforms=(Platform(0,0,200,300),),portals=((0,100),))
        self.assertEqual(completion_plan(s),((0,30),(0,160)))

    def test_fixed_towers_at_exact_spacing_are_legal(self):
        s=Board(True,platforms=(Platform(0,0,200,300),),
                       towers=(Tower(0,0,91,300),Tower(0,0,152,300)))
        self.assertEqual(completion_plan(s),((0,30),))

    def test_boxed_integer_coordinates_are_supported(self):
        s=Board(True,platforms=(Platform(0,0.,400.,300.),),route=(0,),
                       towers=(Tower(0,0,200.,300.),),portals=((0,79.),))
        self.assertEqual(completion_plan(s),((0,139),(0,261)))

    def test_nonintegral_geometry_is_explicitly_unsupported(self):
        cases=(
            Board(True,platforms=(Platform(0,.25,200,300),)),
            Board(True,platforms=(Platform(0,0,200,300.5),)),
            self.state(portals=((0,math.nextafter(60,math.inf)),)),
            self.state(towers=(Tower(0,0,100.5,300),)),
            self.state(towers=(Tower(0,0,100,300.5),)),
        )
        for s in cases:
            with self.subTest(state=s),self.assertRaisesRegex(LayoutUnavailable,'integer-valued'):
                completion_plan(s)

    def test_route_ends_and_off_route_platforms_are_independent(self):
        s=Board(True,platforms=(Platform(9,0,200,300),Platform(1,0,300,200,-1),
                                       Platform(0,0,300,100)),route=(0,1))
        self.assertEqual(completion_plan(s),((0,80),(0,141),(0,202),(0,263),
                                             (1,80),(1,141),(1,202),(1,263),
                                             (9,30),(9,91),(9,152)))

    def test_single_slot_empty_platform_and_runtime_coordinate_bounds(self):
        self.assertEqual(completion_plan(Board(True)),())
        for width,expected in ((59,()),(60,((0,30),))):
            s=Board(True,platforms=(Platform(0,0,width,300),))
            self.assertEqual(completion_plan(s),expected)
        for left in (-10000,99800):
            s=Board(True,platforms=(Platform(0,left,left+200,300),))
            self.assertEqual(completion_plan(s),tuple((0,left+x) for x in (30,91,152)))
        self.assertEqual(completion_plan(self.state(portals=((0,-9980.),(0,100020.)))),
                         completion_plan(self.state()))

    def test_geometry_outside_runtime_coordinate_bounds_is_unsupported(self):
        cases=(
            Board(True,platforms=(Platform(0,-10001,200,300),)),
            Board(True,platforms=(Platform(0,0,100001,300),)),
            self.state(portals=((0,-9981),)),
            self.state(portals=((0,100021),)),
            self.state(towers=(Tower(0,0,10**30,300),)),
        )
        for s in cases:
            with self.subTest(state=s),self.assertRaisesRegex(LayoutUnavailable,'runtime bounds'):
                completion_plan(s)

    def test_fixed_towers_at_current_forbidden_edges_are_unsupported(self):
        for x in (30,79,321,370):
            with self.subTest(x=x),self.assertRaisesRegex(LayoutUnavailable,'edge margins'):
                completion_plan(self.state(towers=(Tower(0,0,x,300),)))
        with self.assertRaisesRegex(LayoutUnavailable,'portal exclusion'):
            completion_plan(self.state(portals=((0,200),),towers=(Tower(0,0,200,300),)))

    def test_horizontal_camera_offset_is_explicitly_unsupported(self):
        from dataclasses import replace
        for offset in (-100,100):
            with self.subTest(offset=offset),self.assertRaisesRegex(LayoutUnavailable,'camera'):
                completion_plan(replace(self.state(),placement_offset_x=offset))

    def test_earlier_coincident_node_blocks_direct_completion(self):
        s=Board(True,platforms=(Platform(0,0,400,300),Platform(1,0,400,300)))
        with self.assertRaisesRegex(LayoutUnavailable,'select'):
            completion_plan(s)

    def test_overlapping_selection_windows_with_free_click_height_are_supported(self):
        s=Board(True,platforms=(Platform(0,0,400,300),Platform(1,0,400,350)))
        self.assertEqual(len(completion_plan(s)),12)

    def test_short_scene_node_can_intercept_a_completion_slot(self):
        nodes=(Platform(0,29,31,300),Platform(1,0,200,300))
        s=Board(True,platforms=(nodes[1],),selection_nodes=nodes)
        with self.assertRaisesRegex(LayoutUnavailable,'select'):
            completion_plan(s)

    def test_selection_geometry_must_match_the_buildable_platforms(self):
        s=Board(True,platforms=(Platform(0,0,400,300),),
                       selection_nodes=(Platform(0,0,400,301),))
        with self.assertRaises(LayoutUnavailable):completion_plan(s)

    def test_malformed_geometry_is_reported(self):
        cases=(
            Board(True,platforms=(Platform(0,0,200,300),Platform(0,200,400,300))),
            Board(True,platforms=(Platform(0,200,0,300),)),
            Board(True,platforms=(Platform(0,0,0,300),)),
            Board(True,platforms=(Platform(0,0,math.inf,300),)),
            Board(True,platforms=(Platform(0,0,200,math.nan),)),
            Board(True,platforms=(Platform(0,0,200,300,0),)),
            self.state(towers=(Tower(0,99,100,300),)),
            self.state(towers=(Tower(0,0,math.nan,300),)),
            self.state(towers=(Tower(0,0,100,math.inf),)),
            self.state(portals=((0,math.inf),)),
        )
        for s in cases:
            with self.subTest(state=s),self.assertRaises(LayoutUnavailable):
                completion_plan(s)

if __name__=='__main__':unittest.main()
