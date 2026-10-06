"""Cross-implementation physical-family negatives and witness contracts."""
from copy import deepcopy
from fractions import Fraction as R
import hashlib, json
from pathlib import Path
import sys, unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'validation'))
sys.path.insert(0,str(ROOT/'experiments/time_cut_v2/family_faithfulness'))
from family5.checker import verify_bundle, check_witness, reconstruct
from make_pilot import build_ancestral, build_open_union, ancestral_case
from timecut5.bounded import Problem
from timecut5.probe import Interval
from timecut5.pwa import drive_pwa, charge_pwa
from timecut5.provenance import Recorder


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def rehash(bundle, changes=None, batch_change=None):
    """Mutate semantic content and consistently remap all cryptographic IDs."""
    changes=changes or {}; old=deepcopy(bundle); nodes={}; mapping={}
    def visit(key):
        if key in mapping:return mapping[key]
        row=deepcopy(old['nodes'][key])
        if key in changes:changes[key](row)
        row['parents']=[visit(k) for k in row['parents']]
        new=digest(row);mapping[key]=new;nodes[new]=row;return new
    for key in old['nodes']:visit(key)
    batches=[]
    for index,row in enumerate(old['batches']):
        row=deepcopy(row)
        if batch_change is not None:batch_change(index,row)
        row['parents']=[mapping[k] for k in row['parents']]
        row['outputs']=[mapping[k] for k in row['outputs']]
        batches.append(row)
    return dict(schema=old['schema'],nodes=nodes,batches=batches,
                batch_ids=[digest(b) for b in batches],roots=[mapping[k] for k in old['roots']]),mapping


class TestIndependentFamilyWitness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=build_ancestral();cls.u=build_open_union();cls.l=build_open_union(R(5,2))
        cls.lc=verify_bundle(cls.l['bundle'],cls.l['case'])
        cls.ac=verify_bundle(cls.a['bundle'],cls.a['case'])
        cls.uc=verify_bundle(cls.u['bundle'],cls.u['case'])

    def check(self,data,ctx,name,contract=None,witness=None):
        row=data['witnesses'][name][0]
        return check_witness(ctx,row['node_id'],witness or row['witness'],contract)

    def test_positive_minimum_membership_and_independent_reconstruction(self):
        for data,ctx,names in ((self.a,self.ac,('A','B')),(self.u,self.uc,('closed','union'))):
            for name in names:
                row=data['witnesses'][name][0]
                with self.subTest(name=name):
                    self.check(data,ctx,name,dict(kind='minimum',energy='3'))
                    out=reconstruct(ctx,row['node_id'],'3',str(R(row['piece']['m'])*3+R(row['piece']['b'])))
                    self.assertIn('receipt',out)
                    check_witness(ctx,row['node_id'],out['witness'],dict(kind='minimum',energy='3'))

    def test_positive_open_approach_and_tiny_budget(self):
        row=self.u['witnesses']['open'][0]
        for eps in (R(1),R(1,10**60)):
            out=reconstruct(self.uc,row['node_id'],'3',str(9+eps/2))
            check_witness(self.uc,row['node_id'],out['witness'],dict(kind='approach',energy='3',epsilon=str(eps)))
            self.assertTrue(R(9)<R(out['witness']['time'])<9+eps)
        with self.assertRaises(ValueError):reconstruct(self.uc,row['node_id'],'3','9')

    def test_M01_foreign_family_same_key(self):
        wa=self.a['witnesses']['A'][0]['witness'];wb=self.a['witnesses']['B'][0]['witness']
        self.assertEqual([wa[k] for k in ('time','energy','rho','pi','state')],
                         [wb[k] for k in ('time','energy','rho','pi','state')])
        with self.assertRaises(ValueError):self.check(self.a,self.ac,'A',witness=wb)
        with self.assertRaises(ValueError):self.check(self.a,self.ac,'B',witness=wa)

    def test_M02_excluded_ancestral_endpoint(self):
        w=deepcopy(self.a['witnesses']['A'][0]['witness'])
        # Valid physical two-C prefix with first departure E=3/2, outside A.
        w['events'][2].update(departure_energy='3/2',departure_time='5/2')
        w['events'][3].update(arrival_energy='3/2',departure_energy='3/2',arrival_time='5/2',departure_time='5/2')
        w['events'][4].update(arrival_energy='3/2',arrival_time='5/2')
        with self.assertRaises(ValueError):self.check(self.a,self.ac,'A',witness=w)

    def test_M03_M04_M05_M06_wrong_output_metadata(self):
        for field,value in (('energy','4'),('rho','0'),('pi',[['c','C'],['wrong-site','C']]),
                            ('state',['elsewhere',0,2]),('state',['c',1,2]),('state',['c',0,3])):
            with self.subTest(field=field,value=value):
                w=deepcopy(self.a['witnesses']['A'][0]['witness']);w[field]=value
                with self.assertRaises(ValueError):self.check(self.a,self.ac,'A',dict(kind='minimum',energy='3'),w)

    def test_M07_intermediate_inventory(self):
        w=deepcopy(self.a['witnesses']['A'][0]['witness'])
        w['events'][2]['departure_energy']='7/5'
        with self.assertRaises(ValueError):self.check(self.a,self.ac,'A',witness=w)

    def test_M09_open_time_infimum_claim(self):
        # The closed-family minimum has the same tau/E/Pi but is outside open ancestry.
        w=deepcopy(self.u['witnesses']['closed'][0]['witness'])
        with self.assertRaises(ValueError):self.check(self.u,self.uc,'open',dict(kind='minimum',energy='3'),w)

    def test_M10_late_closed_minimum(self):
        w=deepcopy(self.l['witnesses']['open'][0]['witness'])
        # Interior guard boundary avoids a separate source-segment singleton.
        # This is physically in this chosen closed family, but not its minimum.
        self.check(self.l,self.lc,'closed',dict(kind='realize_le',energy='3',budget='11'),w)
        with self.assertRaises(ValueError):self.check(self.l,self.lc,'closed',dict(kind='minimum',energy='3'),w)

    def test_M19_zero_charge(self):
        w=deepcopy(self.a['witnesses']['A'][0]['witness'])
        w['events'][2].update(departure_energy='1',departure_time='2')
        w['events'][3].update(arrival_energy='1',departure_energy='1',arrival_time='2',departure_time='2')
        w['events'][4].update(arrival_energy='1',arrival_time='2')
        with self.assertRaises(ValueError):self.check(self.a,self.ac,'A',witness=w)

    def test_M20_free_wait(self):
        w=deepcopy(self.a['witnesses']['A'][0]['witness'])
        for i,event in enumerate(w['events']):
            if i>=2:event['departure_time']=str(R(event['departure_time'])+1)
            if i>=3:event['arrival_time']=str(R(event['arrival_time'])+1)
        w['time']=str(R(w['time'])+1)
        with self.assertRaises(ValueError):self.check(self.a,self.ac,'A',dict(kind='realize_le',energy='3',budget='7'),w)

    def test_M21_wrong_selected_drive(self):
        w=deepcopy(self.a['witnesses']['A'][0]['witness'])
        for i,event in enumerate(w['events']):
            if i>=1:event['departure_time']=str(R(event['departure_time'])+1)
            if i>=2:event['arrival_time']=str(R(event['arrival_time'])+1)
        w['time']=str(R(w['time'])+1)
        with self.assertRaises(ValueError):self.check(self.a,self.ac,'A',dict(kind='realize_le',energy='3',budget='7'),w)

    def test_checked_snapshot_is_detached(self):
        data=deepcopy(self.a);checked=verify_bundle(data['bundle'],data['case'])
        data['bundle']['nodes'].clear()
        self.check(self.a,checked,'A',dict(kind='minimum',energy='3'))
        with self.assertRaises(ValueError):verify_bundle(data['bundle'],data['case'])


class TestIndependentSemanticMutation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.a=build_ancestral();cls.u=build_open_union()

    def reject(self,data,bundle):
        with self.assertRaises(ValueError):verify_bundle(bundle,data['case'])

    def test_M08_open_endpoint_rehashed_closed(self):
        key=next(k for k,n in self.a['bundle']['nodes'].items() if n['kind']=='restrict' and n['params']['domain']==['1','3/2',False,False])
        def mutate(n):n['output']['domain'][2]=True
        bundle,_=rehash(self.a['bundle'],{key:mutate});self.reject(self.a,bundle)

    def test_M11_union_loses_closed_minimizer(self):
        key=self.u['witnesses']['union'][0]['node_id']
        def mutate(n):
            n['parents']=[n['parents'][0]];n['params']['chosen']=0
        bundle,_=rehash(self.u['bundle'],{key:mutate});self.reject(self.u,bundle)

    def test_M12_wrong_union_dispatch(self):
        key=self.u['witnesses']['union'][0]['node_id']
        def mutate(n):n['params']['chosen']=0
        bundle,_=rehash(self.u['bundle'],{key:mutate});self.reject(self.u,bundle)

    def test_M13_restriction_guard_removed(self):
        key=next(k for k,n in self.a['bundle']['nodes'].items() if n['kind']=='restrict' and n['params']['domain']==['1','3/2',False,False])
        def mutate(n):n['params']['domain']=['1','5',False,True]
        bundle,_=rehash(self.a['bundle'],{key:mutate});self.reject(self.a,bundle)

    def test_M15_bridged_energy_gap(self):
        key=next(k for k,n in self.a['bundle']['nodes'].items() if n['kind']=='restrict' and n['params']['domain']==['1','3/2',False,False])
        def mutate(n):n['output']['domain'][1]='5/2'
        bundle,_=rehash(self.a['bundle'],{key:mutate});self.reject(self.a,bundle)

    def test_M16_missing_regime_cell(self):
        index=next(i for i,b in enumerate(self.a['bundle']['batches']) if b['kind']=='stop' and len(b['outputs'])==2)
        def mutate(i,b):
            if i==index:b['outputs']=b['outputs'][1:]
        bundle,_=rehash(self.a['bundle'],batch_change=mutate);self.reject(self.a,bundle)

    def test_M18_wrong_charging_segment(self):
        key=next(k for k,n in self.a['bundle']['nodes'].items() if n['kind']=='stop')
        def mutate(n):n['params']['in_segment'][2]='2'
        bundle,_=rehash(self.a['bundle'],{key:mutate});self.reject(self.a,bundle)

    def test_M24_case_tamper_missing_parent_unknown_kind(self):
        root=next(k for k,n in self.a['bundle']['nodes'].items() if n['kind']=='initial')
        def mutate(n):n['params']['case']['initial_energy_kwh']=3
        bundle,_=rehash(self.a['bundle'],{root:mutate});self.reject(self.a,bundle)
        bundle=deepcopy(self.a['bundle']);del bundle['nodes'][root];self.reject(self.a,bundle)
        def badkind(n):n['kind']='unreviewed-transform'
        bundle,_=rehash(self.a['bundle'],{root:badkind});self.reject(self.a,bundle)

    def test_M25_cycle_and_bad_hash(self):
        bundle=deepcopy(self.a['bundle']);root=next(iter(bundle['nodes']))
        bundle['nodes'][root]['parents']=[root];self.reject(self.a,bundle)

    def test_M26_wrong_affine_output_or_chi(self):
        key=self.a['witnesses']['A'][0]['node_id']
        for field,value in (('m','2'),('b','7'),('chi',False)):
            with self.subTest(field=field):
                def mutate(n):n['output'][field]=value
                bundle,_=rehash(self.a['bundle'],{key:mutate});self.reject(self.a,bundle)

    def test_M22_consecutive_drive_waypoint(self):
        case=ancestral_case();case['initial_energy_kwh']=5
        case['edges']=[dict(source='o',target='a',time_s=1,length_m=1),
                       dict(source='a',target='c',time_s=1,length_m=1),
                       dict(source='o',target='c',time_s=1,length_m=4),
                       dict(source='c',target='z',time_s=1,length_m=1)]
        with Recorder() as recorder:
            p=Problem(case);first=drive_pwa((p.initial_piece(),),'a',R(1),R(1),R(0))
            second=drive_pwa(first,'c',R(1),R(1),R(0));bundle=recorder.export(second)
        self.reject(dict(case=case),bundle)

    def test_M22_terminal_consecutive_drive_waypoint(self):
        case=ancestral_case();case['initial_energy_kwh']=5
        case['edges']=[dict(source='o',target='c',time_s=1,length_m=1),
                       dict(source='c',target='z',time_s=1,length_m=1),
                       dict(source='o',target='z',time_s=1,length_m=4)]
        with Recorder() as recorder:
            p=Problem(case);first=drive_pwa((p.initial_piece(),),'c',R(1),R(1),R(0))
            second=drive_pwa(first,'z',R(1),R(1),R(0));bundle=recorder.export(second)
        self.reject(dict(case=case),bundle)

    def test_M23_terminal_stop(self):
        case=ancestral_case();case['sites']['z']=['C']
        with Recorder() as recorder:
            p=Problem(case);initial=p.initial_piece()
            arrived=drive_pwa((initial,),'z',R(2),R(2),R(0))
            stopped=charge_pwa(arrived,p.curve,p.overhead,'z');bundle=recorder.export(stopped)
        self.reject(dict(case=case),bundle)


class TestIndependentGuardedUnion(unittest.TestCase):
    def test_positive_boundary_dispatch_and_reconstruction(self):
        from make_pilot import build_guarded_union
        data=build_guarded_union();ctx=verify_bundle(data['bundle'],data['case'])
        for row in data['witnesses']:
            receipt=check_witness(ctx,row['node_id'],row['witness'],dict(kind='minimum',energy=row['energy']))
            self.assertIsInstance(receipt,dict)
            value=reconstruct(ctx,row['node_id'],row['energy'],str(R(row['energy'])+2))
            check_witness(ctx,row['node_id'],value['witness'],dict(kind='minimum',energy=row['energy']))

    def test_overlap_does_not_mix_foreign_parent_witness(self):
        from make_pilot import build_guarded_union
        data=build_guarded_union(overlap=True);ctx=verify_bundle(data['bundle'],data['case'])
        key=data['bundle']['roots'][0]
        check_witness(ctx,key,data['parent_witnesses'][0]['witness'],dict(kind='minimum',energy='3'))
        with self.assertRaises(ValueError):
            check_witness(ctx,key,data['parent_witnesses'][1]['witness'],dict(kind='minimum',energy='3'))

    def test_gap_and_widened_parent_guard_rejected(self):
        from make_pilot import build_guarded_union
        data=build_guarded_union(gap=True)
        with self.assertRaises(ValueError):verify_bundle(data['bundle'],data['case'])
        data=build_guarded_union();key=data['bundle']['roots'][0]
        def mutate(n):n['params']['guards'][0][1]='4'
        bundle,_=rehash(data['bundle'],{key:mutate})
        with self.assertRaises(ValueError):verify_bundle(bundle,data['case'])

class TestIndependentGrammarControls(unittest.TestCase):
    def test_redundant_support_is_not_a_semantic_error(self):
        data=build_ancestral()
        i=next(i for i,b in enumerate(data['bundle']['batches']) if b['kind']=='stop')
        def duplicate(index,b):
            if index==i:b['outputs'].append(b['outputs'][0])
        bundle,_=rehash(data['bundle'],batch_change=duplicate)
        checked=verify_bundle(bundle,data['case'])
        self.assertFalse(checked.summary['literal_G8_closed'])
        self.assertIn('separate',checked.summary['trace_invocation_completeness'])

    def test_internal_transit_through_destination_is_legal(self):
        case=ancestral_case();case['initial_energy_kwh']=4
        case['edges']=[dict(source='o',target='z',time_s=1,length_m=1),
                       dict(source='z',target='c',time_s=1,length_m=1),
                       dict(source='c',target='z',time_s=1,length_m=1)]
        with Recorder() as recorder:
            p=Problem(case);final=p.finish(p.advance((p.initial_piece(),),'c','C'))
            bundle=recorder.export(final)
            chosen=next(x for x in final if x.domain.contains(R(2)))
            from timecut5.provenance import witness_dict
            w=witness_dict(chosen.at(R(2)).minimum())
        ctx=verify_bundle(bundle,case)
        check_witness(ctx,chosen._family.node_id,w,dict(kind='minimum',energy='2'))

    def test_site_named_destination_at_another_anchor_is_legal(self):
        case=ancestral_case();case['sites']={'z':['C']};case['site_anchors']={'z':'c'}
        with Recorder() as recorder:
            p=Problem(case);p.site_anchors=case['site_anchors']
            pieces=p.advance((p.initial_piece(),),'z','C')
            bundle=recorder.export(pieces);chosen=next(x for x in pieces if x.domain.contains(R(2)))
            from timecut5.provenance import witness_dict
            w=witness_dict(chosen.at(R(2)).minimum())
        ctx=verify_bundle(bundle,case)
        check_witness(ctx,chosen._family.node_id,w,dict(kind='minimum',energy='2'))

    def test_differently_named_site_at_terminal_anchor_is_forbidden(self):
        case=ancestral_case();case['sites']['terminal-site']=['C']
        case['site_anchors']={'c':'c','terminal-site':'z'}
        with Recorder() as recorder:
            p=Problem(case);p.site_anchors=case['site_anchors'];initial=p.initial_piece()
            self.assertEqual(p.advance((initial,),'terminal-site','C'),())
            arrived=p.finish((initial,))
            bad=charge_pwa(arrived,p.curve,p.overhead,'terminal-site')
            bundle=recorder.export(bad)
        with self.assertRaises(ValueError):verify_bundle(bundle,case)

if __name__=='__main__':unittest.main()
