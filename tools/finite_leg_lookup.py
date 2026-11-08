"""Development-only exact finite lookup, with full integer-domain defaults.

The original validated GroundedLookup owns input and replay. This view changes
only Select expressions into balanced finite If expressions. No solver called.
"""
from exact_leg_table import GroundedLookup


class FiniteGroundedLookup(GroundedLookup):
    def __init__(self,original,check=lambda:None):
        if not isinstance(original,GroundedLookup) or not getattr(original.table,'_validated',False):
            raise TypeError('validated owned lookup required')
        self.__dict__.update(original.__dict__)
        self._check=check;z=self.z3
        count=len(self.source_index)*self.width
        times=[None]*count;lengths=[None]*count;reachable=[None]*count
        for n,((s,t),pair) in enumerate(self.table.pairs.items()):
            if n%128==0:check()
            k=self.source_index[s]*self.width+self.target_index[t]
            times[k]=z.RealVal(str(pair.time if pair.reachable else 0))
            lengths[k]=z.RealVal(str(pair.length if pair.reachable else 0))
            reachable[k]=z.BoolVal(pair.reachable)
        if any(v is None for row in (times,lengths,reachable) for v in row):raise ValueError('complete Cartesian lookup required')
        source=[z.IntVal(0)];target=[z.IntVal(0)];charge=[z.BoolVal(False)];service=[z.BoolVal(False)]
        for site,effect in self.actions:
            anchor=self.table.aliases[site]
            source.append(z.IntVal(self.source_index[anchor]));target.append(z.IntVal(self.target_index[anchor]))
            charge.append(z.BoolVal(effect in ('C','CS')));service.append(z.BoolVal(effect in ('S','CS')))
        self._finite={name:(tuple(values),default) for name,values,default in (
            ('T',times,z.RealVal(0)),('L',lengths,z.RealVal(0)),('R',reachable,z.BoolVal(False)),
            ('AS',source,z.IntVal(0)),('AT',target,z.IntVal(0)),('C',charge,z.BoolVal(False)),('S',service,z.BoolVal(False)))}

    def _select(self,array,index):
        z=self.z3
        if type(index) is int:index=z.IntVal(index)
        if not isinstance(index,z.ArithRef) or index.sort().kind()!=z.Z3_INT_SORT:raise TypeError('integer index required')
        names=[name for name in self._finite if z.eq(array,getattr(self,name))]
        if not names:raise ValueError('unknown owned array')
        # Structurally identical arrays are the same total function (e.g. C/S
        # when every action is CS); either exact finite expansion is valid.
        values,default=self._finite[names[0]]
        def tree(lo,hi):
            self._check()
            if hi-lo==1:return values[lo]
            mid=(lo+hi)//2
            left,right=tree(lo,mid),tree(mid,hi)
            # Structural equality is a total-function identity, independent of
            # index bounds or reachability. Recurse first to expose new matches.
            return left if z.eq(left,right) else z.If(index<mid,left,right)
        if not values:return default
        return z.If(z.And(index>=0,index<len(values)),tree(0,len(values)),default)
