"""Mock-only real input contract tests. No graph load or Stage C optimization."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from fractions import Fraction as R
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from timecut5.probe import State
from timecut5.real_legs import (
    ImmutableLegTable,NUMERICS,SCHEMA,TIE_POLICY,decode_binary64,encode_binary64,
    restrict_frozen_tree,verify_source_files,weak_action_bound,
)


def sha(data):return hashlib.sha256(data).hexdigest()
def blob(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


def payload():
    anchors=['o','x','z']
    return dict(schema=SCHEMA,numerical_contract=NUMERICS,anchors=anchors,
        origin_anchor='o',destination_anchor='z',
        sites=[dict(site_id='A',anchor_id='x',effects=['C','S','CS']),
               dict(site_id='B',anchor_id='x',effects=['C']),
               dict(site_id='at_destination',anchor_id='z',effects=['S']),
               dict(site_id='z',anchor_id='x',effects=['S'])],
        backend=dict(name='mock accepted ExactRouter.full',tie_policy=TIE_POLICY,
                     direction_policy='forward_per_source_v1',
                     source_sha256={'src/microplan/routing.cpp':sha(b'router')}),
        source_sha256={'data/graph.parquet':sha(b'graph')},
        selection_certificate_sha256=sha(b'mock selection'),hierarchy_sha256=sha(b'mock tree'),
        legs=[dict(source_anchor=a,target_anchor=b,reachable=True,
                   time_s=encode_binary64(0.0 if a==b else 10.0),
                   actual_length_m=encode_binary64(0.0 if a==b else 10.0),
                   label_direction='identity' if a==b else 'forward_from_source')
              for a in anchors for b in anchors])


def row(p,a,b):return next(r for r in p['legs'] if (r['source_anchor'],r['target_anchor'])==(a,b))
def load(p):
    data=blob(p)
    return ImmutableLegTable.from_bytes(data,sha(data))


class TestBinary64Contract(unittest.TestCase):
    def test_exact_roundtrip_and_subnormal(self):
        for value in (0.0,-0.0,0.1,0.1+0.2,float.fromhex('0x0.0000000000001p-1022'),1e200):
            encoded=encode_binary64(value)
            self.assertEqual(decode_binary64(encoded),R(*value.as_integer_ratio()))
            self.assertEqual(float.fromhex(encoded['hex']).hex(),value.hex())
        self.assertNotEqual(encode_binary64(-0.0)['hex'],encode_binary64(0.0)['hex'])

    def test_rejects_tampered_ratio_nonfinite_negative_and_bool(self):
        bad=encode_binary64(0.1);bad['ratio']=['1','10']
        with self.assertRaises(ValueError):decode_binary64(bad)
        for value in (float('nan'),float('inf'),-1.0,True,1):
            with self.assertRaises(ValueError):encode_binary64(value)
        bad=encode_binary64(1.0);bad['ratio']=[True,'1']
        with self.assertRaises(ValueError):decode_binary64(bad)


class TestImmutableSelectedLegs(unittest.TestCase):
    def test_selected_length_is_preserved_without_graph_rerouting(self):
        p=payload()
        for a,b,t,length in [('o','z',2.0,9.0),('o','x',1.0,1.0),('x','z',1.0,1.0)]:
            row(p,a,b).update(time_s=encode_binary64(t),actual_length_m=encode_binary64(length))
        table=load(p)
        self.assertEqual(table.leg('o','z').time,2)
        self.assertEqual(table.leg('o','z').actual_length,9)
        self.assertEqual(table.leg('o','z').energy(R(1,10)),R(9,10))
        # The serialized selected primitive is authoritative to this loader;
        # an equal-time composition of table rows is never a new route choice.
        self.assertEqual(table.leg('o','x').actual_length+table.leg('x','z').actual_length,2)

    def test_rounded_totals_need_not_obey_triangle_inequality(self):
        p=payload()
        for a,b,t in [('o','x',0.1),('x','z',0.2),('o','z',0.1+0.2)]:
            row(p,a,b)['time_s']=encode_binary64(t)
        table=load(p)
        self.assertGreater(table.leg('o','z').time,table.leg('o','x').time+table.leg('x','z').time)
        bound=weak_action_bound(table,State('o',1,0),['A'],'C',0,0,1,0)
        self.assertEqual(bound.value,1+table.leg('o','x').time)
        self.assertEqual(bound.onward_lower_bound,0)

    def test_coattached_sites_remain_distinct_actions(self):
        table=load(payload())
        candidates=table.action_sites('x','C',1,['A','B'])
        self.assertEqual(tuple(s.site_id for s in candidates),('A','B'))
        self.assertEqual(tuple(s.anchor_id for s in candidates),('x','x'))
        self.assertEqual((table.leg('x','x').time,table.leg('x','x').actual_length),(0,0))
        bound=weak_action_bound(table,State('x',1,2),['A','B'],'C',5,0,3,2)
        self.assertEqual((bound.value,bound.site_ids,bound.inbound_minimum),(14,('A','B'),0))

    def test_destination_policy_uses_road_anchor_not_site_text(self):
        table=load(payload())
        self.assertEqual(tuple(s.site_id for s in table.action_sites('o','S',1)),('A','z'))
        self.assertEqual(table.action_sites('z','C',1),())
        self.assertEqual(table.action_sites('o','S',0),())
        p=payload();p['origin_anchor']='z'
        self.assertEqual(load(p).action_sites('z','S',1),())

    def test_direct_terminal_energy_does_not_delete_charging_continuation(self):
        p=payload()
        row(p,'o','z').update(time_s=encode_binary64(1.0),actual_length_m=encode_binary64(100.0))
        for a,b in [('o','x'),('x','z')]:row(p,a,b)['actual_length_m']=encode_binary64(1.0)
        table=load(p)
        self.assertGreater(table.leg('o','z').energy(R(1)),10) # even capacity10 cannot use direct leg
        self.assertEqual(table.leg('o','x').energy(R(1)),1)
        bound=weak_action_bound(table,State('o',1,0),['A'],'C',0,0,1,0)
        self.assertEqual(bound.site_ids,('A',))
        self.assertIsNotNone(bound.value)

    def test_complete_rows_explicit_unreachable_and_consistency(self):
        p=payload();p['legs'].pop()
        with self.assertRaises(ValueError):load(p)
        p=payload();p['legs'].append(deepcopy(p['legs'][0]))
        with self.assertRaises(ValueError):load(p)
        p=payload()
        for target in ('o','x'):
            row(p,'z',target).update(reachable=False,time_s=None,actual_length_m=None)
        table=load(p)
        self.assertFalse(table.leg('z','o').reachable)
        self.assertIsNone(table.leg('z','o').energy(R(1)))
        p=payload();row(p,'o','z').update(reachable=False,time_s=None,actual_length_m=None)
        with self.assertRaisesRegex(ValueError,'transitively'):load(p)

    def test_no_finite_unreachable_substitute_or_fake_zero_edge(self):
        p=payload();row(p,'o','x')['reachable']=False
        with self.assertRaises(ValueError):load(p)
        p=payload();row(p,'o','x')['time_s']=encode_binary64(0.0)
        with self.assertRaises(ValueError):load(p)
        p=payload();row(p,'x','x')['time_s']=encode_binary64(-0.0)
        self.assertEqual(load(p).leg('x','x').time_hex,(-0.0).hex())

    def test_forward_reverse_direction_is_not_silently_mixed(self):
        p=payload();row(p,'o','x')['label_direction']='reverse_from_target'
        with self.assertRaises(ValueError):load(p)
        p['backend']['direction_policy']='explicit_per_leg_v1'
        self.assertEqual(load(p).leg('o','x').label_direction,'reverse_from_target')

    def test_integrity_and_deep_immutability(self):
        p=payload();data=blob(p)
        with self.assertRaises(ValueError):ImmutableLegTable.from_bytes(data,'0'*64)
        table=load(p)
        p['sites'][0]['anchor_id']='z';row(p,'o','x')['time_s']=encode_binary64(999.0)
        self.assertEqual(table.site('A').anchor_id,'x')
        self.assertEqual(table.leg('o','x').time,10)
        with self.assertRaises(TypeError):table.sites['other']=table.site('A')
        with self.assertRaises(FrozenInstanceError):table.site('A').anchor_id='z'
        with self.assertRaises(FrozenInstanceError):table.leg('o','x').time=R(0)

    def test_graph_shape_and_synthetic_tie_policy_rejected(self):
        p=payload();p['edges']=[]
        with self.assertRaises(ValueError):load(p)

    def test_schema_arrays_cannot_silently_become_character_lists(self):
        for key in ('anchors','sites','legs'):
            p=payload();p[key]='oxz'
            with self.assertRaises(ValueError):load(p)
        p=payload();p['sites'][0]['effects']='CS'
        with self.assertRaises(ValueError):load(p)
        table=load(payload())
        with self.assertRaises(ValueError):table.action_sites('o','C',1,'A')

    def test_duplicate_json_keys_are_rejected(self):
        data=blob(payload()).replace(b'"origin_anchor":"o"',b'"origin_anchor":"x","origin_anchor":"o"')
        with self.assertRaisesRegex(ValueError,'Duplicate JSON'):ImmutableLegTable.from_bytes(data,sha(data))
        p=payload();p['backend']['tie_policy']='time_then_node_path'
        with self.assertRaises(ValueError):load(p)

    def test_source_claims_are_not_verified_implicitly(self):
        table=load(payload())
        empty=verify_source_files(table,{})
        self.assertFalse(empty['complete']);self.assertEqual(len(empty['missing']),2)
        with tempfile.TemporaryDirectory() as temp:
            graph,router=Path(temp)/'graph',Path(temp)/'router'
            graph.write_bytes(b'graph');router.write_bytes(b'router')
            paths={'data/graph.parquet':graph,'src/microplan/routing.cpp':router}
            self.assertTrue(verify_source_files(table,paths)['complete'])
            graph.write_bytes(b'changed')
            result=verify_source_files(table,paths)
            self.assertFalse(result['complete']);self.assertEqual(result['mismatched'],('data/graph.parquet',))

    def test_schedule_bound_is_weak_and_penalty_counts_next_action(self):
        table=load(payload())
        b=weak_action_bound(table,State('x',1,2),['A'],'CS',5,2,3,7,(20,30,4))
        self.assertEqual(b.value,43) # max(20,5+0+3)+4-2+7*3
        with self.assertRaises(ValueError):weak_action_bound(table,State('x',1,2),['A'],'C',5,0,3,-1)


class TestActualTreeRestriction(unittest.TestCase):
    def mock_tree(self):
        return dict(site_ids=['A','B','C'],regions=[
            dict(parent=-1,children=[1,2],members=[0,1,2]),
            dict(parent=0,children=[],members=[0]),
            dict(parent=0,children=[3,4],members=[1,2]),
            dict(parent=2,children=[],members=[1]),
            dict(parent=2,children=[],members=[2])])

    def test_ids_topology_and_empty_children_are_retained(self):
        data=blob(self.mock_tree());tree=restrict_frozen_tree(data,sha(data),['B'])
        self.assertEqual([r.region_id for r in tree.regions],list(range(5)))
        self.assertEqual(tree.regions[0].child_ids,(1,2))
        self.assertEqual(tree.regions[1].site_ids,())
        self.assertEqual(tree.regions[2].child_ids,(3,4))
        self.assertEqual(tree.regions[3].site_ids,('B',))
        self.assertEqual(tree.regions[4].site_ids,())

    def test_rejects_changed_hash_partition_and_unknown_selection(self):
        tree=self.mock_tree();data=blob(tree)
        with self.assertRaises(ValueError):restrict_frozen_tree(data,'0'*64,['A'])
        with self.assertRaises(ValueError):restrict_frozen_tree(data,sha(data),['missing'])
        tree['regions'][4]['members']=[1];data=blob(tree)
        with self.assertRaises(ValueError):restrict_frozen_tree(data,sha(data),['A'])

    def test_rejects_disconnected_regions_and_wrong_parent(self):
        tree=self.mock_tree();tree['regions'].append(dict(parent=-1,children=[],members=[]));data=blob(tree)
        with self.assertRaises(ValueError):restrict_frozen_tree(data,sha(data),[])

    def test_tree_arrays_and_scalar_types_are_explicit(self):
        for key in ('site_ids','regions'):
            tree=self.mock_tree();tree[key]='ABC';data=blob(tree)
            with self.assertRaises(ValueError):restrict_frozen_tree(data,sha(data),[])
        for key in ('children','members'):
            tree=self.mock_tree();tree['regions'][0][key]='12';data=blob(tree)
            with self.assertRaises(ValueError):restrict_frozen_tree(data,sha(data),[])
        data=blob(self.mock_tree())
        with self.assertRaises(ValueError):restrict_frozen_tree(data,sha(data),'A')
        tree=self.mock_tree();tree['regions'][3]['parent']=1;data=blob(tree)
        with self.assertRaises(ValueError):restrict_frozen_tree(data,sha(data),[])


if __name__=='__main__':unittest.main()
