import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from preflight_real_road_certificate import memory_units,positive_parts,preflight,scan,validate_domain


class PreflightTests(unittest.TestCase):
    def fixtures(self,root):
        candidates=[dict(site_id='Site/'+str(i),access_node='anchor-'+str(i)) for i in range(64)]
        endpoints=dict(origin=dict(access_node='origin'),destination=dict(access_node='terminal'))
        config=dict(model=dict(capacity='unchanged'))
        manifest=dict(config=config,queries=[dict(query_id='WD01',endpoints=endpoints,scenario_candidate_domains=dict(schedule={'64':candidates}))])
        paths={}
        for name,value in [('config',config),('preflight',manifest),('bindings',{}),('catalog',{})]:
            path=root/(name+'.json');path.write_text(json.dumps(value));paths[name]=str(path)
        graph=root/'road.tsv';nodes=['origin',*[r['access_node'] for r in candidates],'terminal']
        graph.write_text(''.join(f'{a}\t{b}\tedge-{i}\t1/3\t7/5\n' for i,(a,b) in enumerate(zip(nodes,nodes[1:]))));paths['graph']=str(graph)
        sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
        S=sorted(nodes[:-1]);T=sorted(nodes[1:]);domain=dict(endpoints=endpoints,candidates=candidates)
        return dict(query_id='WD01',initial_energy_kwh='18',scenario='schedule',N=64,domain=domain,
            candidate_domain_sha256=hashlib.sha256(json.dumps(domain,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            physical_sources=S,physical_targets=T,pairs=[dict(source=s,target=t) for s in S for t in T],
            config_path=paths['config'],config_sha256=sha(paths['config']),preflight_path=paths['preflight'],
            preflight_sha256=sha(paths['preflight']),physical_model=config['model'],
            input_paths={k:paths[k] for k in ('bindings','catalog','graph')},
            expected_input_sha256={k:sha(paths[k]) for k in ('bindings','catalog','graph')})

    def test_complete_scan_never_becomes_certificate_or_safe_upper_bound(self):
        with tempfile.TemporaryDirectory() as d:
            f=self.fixtures(Path(d))
            for allowance in (2*1024**3,16*1024**3):
                r=preflight(f,allowance)
                self.assertFalse(r['source_work_released']);self.assertFalse(r['whole_table_certified'])
                self.assertFalse(r['upper_witness_independently_replayed']);self.assertFalse(r['relevant_depth_certified'])
                self.assertEqual(len(r['pairs']),4225);self.assertEqual(len(r['source_statuses']),65)
                self.assertEqual(r['zero_pairs'],64);self.assertEqual(r['observed']['observed_edge_rows'],65)
                self.assertFalse(r['observed']['global_edge_ID_uniqueness_checked'])
            self.assertEqual(r['decision'],'NO_GO_SAFE_COMPACT_BRIDGE_NOT_ESTABLISHED')

    def test_low_memory_is_distinct_from_physical_infeasibility(self):
        with tempfile.TemporaryDirectory() as d:
            r=preflight(self.fixtures(Path(d)),2*1024**3)
            self.assertEqual(r['decision'],'NO_GO_CURRENT_LOADER_MEMORY')
            self.assertTrue(r['memory_lower_bound_exceeds_admission'])
            self.assertTrue(all(v['status']=='unrun_preflight_blocked' for v in r['pairs']))

    def test_full_pair_and_literal_source_identity_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            f=self.fixtures(Path(d))
            for kind in ('pair','duplicate','source','site','domain'):
                b=copy.deepcopy(f)
                if kind=='pair':b['pairs'].pop()
                if kind=='duplicate':b['pairs'][-1]=b['pairs'][0]
                if kind=='source':b['physical_sources'][0]='substitute'
                if kind=='site':b['domain']['candidates'].pop()
                if kind=='domain':b['domain']['candidates'][0]['access_node']='substitute'
                with self.assertRaises(ValueError):validate_domain(b)

    def test_input_and_manifest_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            f=self.fixtures(Path(d))
            for key in ('graph','catalog','bindings'):
                b=copy.deepcopy(f);b['expected_input_sha256'][key]='0'*64
                with self.assertRaises(ValueError):preflight(b,8*1024**3)
            b=copy.deepcopy(f);b['physical_model']['capacity']='changed'
            with self.assertRaises(ValueError):preflight(b,8*1024**3)

    def test_missing_terminal_anchor_and_bad_row_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'g';p.write_text('origin\tnode\tedge\t1/3\t7/5\n')
            r=scan(p,{'origin','terminal'},memory_units())
            self.assertEqual(r['missing_anchors'],['terminal'])
            p.write_text('origin\tnode\tedge\t1/3\t7/5\textra\n')
            with self.assertRaises(ValueError):scan(p,set(),memory_units())

    def test_zero_negative_float_and_invalid_fraction_unsupported(self):
        for value in ('0','-1','0/3','1/0','1.5','01/2','1/-2','True'):
            with self.subTest(value=value),self.assertRaises(ValueError):positive_parts(value)
        self.assertEqual(positive_parts('123/456'),(123,456))

    def test_memory_identity_values_not_interned_by_JSON_decoder(self):
        rows=json.loads('[{"x":"same-value"},{"x":"same-value"}]')
        self.assertIsNot(rows[0]['x'],rows[1]['x'])
        units=memory_units();self.assertGreater(units['fractions'],0)


if __name__=='__main__':unittest.main()
