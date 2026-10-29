from dataclasses import replace
from fractions import Fraction as Q
import unittest
from hiroute.exact import AffineCutPiece, Interval, terminal_optimize
from timecut5.probe import AffineFamily, Interval as OldInterval, State, terminal


def pair(domain=Interval(0,1), slope=0, intercept=10, attained=True, rho=0, prefix=()):
    state=State("z",0,len(prefix))
    old_domain=OldInterval(domain.lo,domain.hi,domain.left_closed,domain.right_closed)
    old=AffineFamily(old_domain,Q(slope),Q(intercept),attained,Q(rho),prefix,state)
    new=AffineCutPiece(domain,Q(slope),Q(intercept),attained,Q(rho),prefix,
                       ("z",0,len(prefix)))
    return old,new


def compare(old_families,new_pieces,*,reserve=0,start=0,penalty=0):
    old=terminal(old_families,"z",reserve,start,penalty)
    new=terminal_optimize(new_pieces,"z",reserve,start,penalty)
    mapped={"infeasible":"infeasible","infimum_unattained":"primary_unattained" if old.unattained_component=="J" else "secondary_unattained","attained_optimum":"attained_optimum"}
    assert new.status==mapped[old.status],(old,new)
    if old.status=="infeasible": return old,new
    if old.status=="infimum_unattained":
        assert new.primary_infimum==old.primary_infimum
        if old.unattained_component=="Q":
            assert new.primary_value==old.primary_infimum
            assert new.secondary_infimum==old.secondary_infimum
        return old,new
    assert new.key==old.key,(old.key,new.key)
    assert new.witness.energy==old.witness.energy
    return old,new


class TestExactTerminal(unittest.TestCase):
    def test_primary_open_does_not_report_later_plan(self):
        a,an=pair(attained=False); b,bn=pair(intercept=11)
        compare((a,b),(an,bn))

    def test_attained_j_with_open_best_q_preserves_j(self):
        a,an=pair(Interval(7,8,False,True),intercept=12,rho=-7,
                  prefix=(("s","C"),("g","S")))
        compare((a,),(an,),penalty=1)

    def test_tie_and_reserve_clipping(self):
        a,an=pair(Interval(0,2,False,True),prefix=(("2","C"),))
        b,bn=pair(Interval(0,2,False,True),prefix=(("1","C"),))
        compare((a,b),(an,bn),reserve=1,penalty=3)
        x,xn=pair(Interval(0,2,False,True))
        old,new=compare((x,),(xn,),reserve=3)
        self.assertEqual(old.status,"infeasible")

    def test_nonconstant_primary_and_attained_tie(self):
        a,an=pair(slope=-1)
        compare((a,),(an,))
        o,on=pair(attained=False,rho=0)
        c,cn=pair(Interval(1,1),rho=3)
        compare((o,c),(on,cn))

    def test_open_q_and_closed_tie_and_prefix_tiebreak(self):
        a,an=pair(Interval(0,1,False,True))
        b,bn=pair(Interval(2,2))
        compare((a,b),(an,bn))
        c,cn=pair(Interval(0,1,False,True))
        d,dn=pair(Interval(0,0))
        compare((c,d),(cn,dn))
        s,sn=pair(Interval(1,1),prefix=(("9","C"),))
        l,ln=pair(Interval(1,1),prefix=(("1","C"),("2","S")))
        compare((l,s),(ln,sn))


if __name__=="__main__": unittest.main()
