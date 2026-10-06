"""Generate deterministic physical ancestry pilots; no oracle optimization."""
from dataclasses import replace
from fractions import Fraction as R
from pathlib import Path
import argparse, json
from timecut5.bounded import Problem
from timecut5.probe import Interval
from timecut5.provenance import Recorder, restrict, signature, witness_dict, guarded_union
from timecut5.pwa import lower_envelope


def ancestral_case():
    return dict(case_id="family-ancestral-interval-v1", H_ref=4, origin="o", destination="z",
                start_time_s=0, initial_energy_kwh=2, capacity_kwh=5,
                minimum_energy_kwh=0, reserve_kwh=0, consumption_kwh_per_m=1,
                overhead_s=1, lambda_stop_s=0, schedule=None,
                sites={"c":["C"]}, charging_segments=[[0,5,1,0]],
                edges=[dict(source="o",target="c",time_s=1,length_m=1),
                       dict(source="c",target="z",time_s=1,length_m=1)])


def clip(pieces, domain):
    result=[]
    for piece in pieces:
        d=piece.domain.intersect(domain)
        if d is not None:
            result.append(restrict(piece,d,"pilot_ancestral_energy_guard"))
    return tuple(result)


def build_ancestral():
    case=ancestral_case();problem=Problem(case)
    with Recorder() as recorder:
        first=problem.advance((problem.initial_piece(),),"c","C")
        families={}
        for name, guard in (("A",Interval(1,R(3,2),False,False)),
                            ("B",Interval(2,R(5,2),False,False))):
            first_restricted=clip(first,guard)
            second=problem.advance(first_restricted,"c","C")
            final=clip(second,Interval(3,4))
            families[name]=final
        roots=families["A"]+families["B"]
        bundle=recorder.export(roots)
        witnesses={name:[dict(node_id=p._family.node_id, piece=signature(p),
                       witness=witness_dict(p.at(R(3)).minimum()))
                       for p in pieces if p.domain.contains(R(3))]
                   for name,pieces in families.items()}
    return dict(case=case,bundle=bundle,witnesses=witnesses,
                expectations=dict(final_energy="3",time="5",rho="-1",pi=[["c","C"],["c","C"]],
                                  foreign_family_swap="reject",excluded_first_energy="3/2"))



def build_open_union(boundary=R(2)):
    case=ancestral_case()
    case.update(case_id="family-open-union-v1-boundary-"+str(boundary),sites={"a":["C"],"b":["C"]},
                charging_segments=[[0,2,1,0],[2,5,3,-4]],
                edges=[dict(source="o",target="a",time_s=1,length_m=1),
                       dict(source="a",target="b",time_s=1,length_m=1),
                       dict(source="b",target="z",time_s=1,length_m=1)])
    problem=Problem(case)
    with Recorder() as recorder:
        first=problem.advance((problem.initial_piece(),),"a","C")
        families={}
        for name,guard in (("open",Interval(boundary,3,False,False)),
                           ("closed",Interval(boundary,3,True,False))):
            first_restricted=clip(first,guard)
            second=problem.advance(first_restricted,"b","C")
            families[name]=clip(second,Interval(3,3))
        # Each family can have multiple adjacent first-operator regimes at E=2.
        families={name:lower_envelope(pieces) for name,pieces in families.items()}
        union=lower_envelope(families["open"]+families["closed"])
        families["union"]=union
        roots=tuple(p for ps in families.values() for p in ps)
        bundle=recorder.export(roots)
        witnesses={name:[dict(node_id=p._family.node_id,piece=signature(p),
                       witness=witness_dict(p.at(R(3)).approach(R(1,10**30))))
                       for p in pieces] for name,pieces in families.items()}
    return dict(case=case,bundle=bundle,witnesses=witnesses,
                expectations=dict(final_energy="3",tau=str(2*boundary+5),open_chi=False,
                                  closed_chi=True,union_chi=True))


def build_guarded_union(overlap=False, gap=False):
    case=ancestral_case();case["case_id"]="family-guarded-union-v1"
    problem=Problem(case)
    with Recorder() as recorder:
        first=problem.advance((problem.initial_piece(),),"c","C")
        parents=[]
        for name,guard in (("A",Interval(1,R(3,2),False,False)),
                           ("B",Interval(2,R(5,2),False,False))):
            second=problem.advance(clip(first,guard),"c","C")
            final_domain=(Interval(3,4) if overlap else
                          Interval(3,R(13,4) if gap else R(7,2),True,False) if name=="A" else
                          Interval(R(7,2),4))
            parent=clip(second,final_domain)
            if len(parent)!=1:
                raise ValueError('guarded pilot requires exactly one original parent')
            parents.extend(parent)
        def dispatch(energy):
            return next(p for p in parents if p.domain.contains(energy)).at(energy)
        output=replace(parents[0],domain=Interval(3,4),_point=dispatch)
        output=guarded_union(output,parents)
        bundle=recorder.export((output,))
        witnesses=[dict(node_id=output._family.node_id,energy=str(e),
                        witness=witness_dict(output.at(e).minimum()))
                   for e in (R(3),R(7,2),R(4))]
        parent_witnesses=[dict(node_id=p._family.node_id,
                              witness=witness_dict(p.at(R(3) if overlap else (p.domain.lo+p.domain.hi)/2).minimum()))
                          for p in parents]
    return dict(case=case,bundle=bundle,witnesses=witnesses,parent_witnesses=parent_witnesses,
                expectations=dict(connected_union=not gap,overlap_dispatch="first_original_parent"))

def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);parser.add_argument("--kind",choices=("ancestral","open_union"),default="ancestral")
    args=parser.parse_args();value=build_ancestral() if args.kind=="ancestral" else build_open_union()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(value,sort_keys=True,indent=2)+"\n")
    print(json.dumps(dict(nodes=len(value["bundle"]["nodes"]),batches=len(value["bundle"]["batches"]),
                         roots=len(value["bundle"]["roots"]),path=str(args.output))))

if __name__=="__main__":main()
