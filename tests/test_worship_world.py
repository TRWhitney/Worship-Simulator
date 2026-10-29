"""Persistent actor and monster-index behavior from original client execution."""
from dataclasses import dataclass
import unittest


@dataclass(eq=False)
class Monster:
    monster_id: int = -1


class WorshipWorldTests(unittest.TestCase):
    def table(self,capacity=4):
        from worship_sim.world import ActorTable
        return ActorTable(capacity=capacity)

    def monsters(self):
        from worship_sim.world import MonsterTable
        return MonsterTable(hp_sentinel=0,alive_sentinel=0,will_die_sentinel=0)

    def test_draw_slots_reuse_last_freed_slot(self):
        table=self.table()
        table.add(1,'A');table.add(2,'GUI');table.add(3,'B')
        table.remove(1);table.add(4,'C');table.add(5,'D')
        self.assertEqual(list(table),['C','GUI','B','D'])
        table=self.table()
        table.add(1,'A');table.add(2,'GUI');table.add(3,'B')
        table.remove(1);table.remove(2);table.add(4,'C');table.add(5,'D')
        self.assertEqual(list(table),['D','C','B'])

    def test_growth_preserves_occupied_drawing_slots(self):
        table=self.table()
        for key in range(20):table.add(key,key)
        for key in range(1,19):table.remove(key)
        self.assertEqual(list(table),[0,19])
        table.add(21,'new')
        self.assertEqual(list(table),[0,'new',19])

    def test_iterator_keeps_original_backing_when_table_grows(self):
        table=self.table(capacity=2)
        table.add(1,'A');table.add(2,'B')
        drawing=iter(table)
        self.assertEqual(next(drawing),'A')
        table.add(3,'C')
        table.remove(2)
        self.assertEqual(list(drawing),['B'])
        self.assertEqual(list(table),['A','C'])

    def test_engine_reuses_iterator_and_nested_iteration_resets_it(self):
        from worship_sim.world import ActorTable
        table=ActorTable(capacity=4,reuse_iterator=True)
        table.add(1,'A');table.add(2,'B');table.add(3,'C')
        outer=iter(table)
        self.assertEqual(next(outer),'A')
        inner=iter(table)
        self.assertIs(inner,outer)
        self.assertEqual((next(inner),next(outer)),('A','B'))

    def test_hp_reference_aliases_survivor_after_corpse_removal(self):
        table=self.monsters();corpse=Monster();survivor=Monster()
        table.add(corpse,hp=-5);table.add(survivor,hp=100)
        table.set_alive(corpse,0);table.remove(corpse)
        self.assertEqual((corpse.monster_id,survivor.monster_id),(1,1))
        table.set_hp(corpse,table.hp(corpse)-10)
        self.assertEqual(table.hp(survivor),90)
        self.assertEqual(table.actors,[survivor])
        self.assertEqual(table.alive(corpse),1)

    def test_missing_hp_converts_to_zero_but_alive_stays_missing(self):
        table=self.monsters();corpse=Monster();table.add(corpse,hp=10)
        table.remove(corpse)
        self.assertEqual(table.hp(corpse),0)
        self.assertIsNone(table.alive(corpse))
        table.set_hp(corpse,table.hp(corpse)-10)
        self.assertEqual(table.hp(corpse),-10)
        self.assertIsNone(table.alive(corpse))

    def test_reused_actor_keeps_identity_and_receives_new_index(self):
        table=self.monsters();reused=Monster();other=Monster()
        table.add(reused,hp=10);table.add(other,hp=100)
        reference=reused;table.remove(reused);table.add(reused,hp=200)
        self.assertIs(reference,reused)
        self.assertEqual(reference.monster_id,2)
        self.assertEqual(table.hp(reference),200)
        self.assertEqual(table.hp(other),100)
        self.assertEqual(table.actors,[other,reused])


if __name__=='__main__':unittest.main()
