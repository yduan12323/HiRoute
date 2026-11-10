"""Exact, restricted Bool/Int/Real DAG export; never constructs a solver.

Every compound node is a typed nullary SMT-LIB definition. Definitions refer
only to earlier nodes. Atomic publication and a checked completion digest make
partial output distinguishable even when an interruption leaves a scratch file.
"""
import hashlib
import os
from pathlib import Path
import re
import tempfile
import z3

_OPS = {getattr(z3, 'Z3_OP_' + k): v for k, v in (
    ('EQ', '='), ('DISTINCT', 'distinct'), ('ITE', 'ite'), ('AND', 'and'),
    ('OR', 'or'), ('NOT', 'not'), ('IMPLIES', '=>'), ('XOR', 'xor'),
    ('LE', '<='), ('GE', '>='), ('LT', '<'), ('GT', '>'), ('ADD', '+'),
    ('SUB', '-'), ('UMINUS', '-'), ('MUL', '*'), ('DIV', '/'),
    ('TO_REAL', 'to_real'))}
_SORTS = {z3.Z3_BOOL_SORT: 'Bool', z3.Z3_INT_SORT: 'Int', z3.Z3_REAL_SORT: 'Real'}
_SYMBOL = re.compile(r'[a-zA-Z_][a-zA-Z_0-9!?.-]*\Z')
_RESERVED = {'true', 'false', 'Bool', 'Int', 'Real', 'let', 'forall', 'exists',
             'as', 'par', 'match', '_', '!', 'and', 'or', 'not', 'ite',
             'distinct', 'xor', 'to_real'}
_FOOTER = b'; hiroute-dag-complete-sha256 '


def export_dag(assertions, path, check=lambda: None, *, max_nodes=2000000,
               max_bytes=256*1024*1024, objectives=(), _capture=None):
    """Export exact assertions to a NEW file, or fail without publishing it.

    Deliberately rejects arrays, quantifiers, algebraic numbers, applications of
    uninterpreted functions, unsupported operators and unsafe/overloaded names.
    Limits are output resource guards, never a license to truncate a formula.
    """
    if type(max_nodes) is not int or max_nodes < 1 or type(max_bytes) is not int or max_bytes < 1:
        raise ValueError('positive integer resource limits required')
    roots = tuple(assertions)
    if not roots or any(not z3.is_bool(e) for e in roots):
        raise ValueError('nonempty Boolean assertions required')
    objectives=tuple(objectives)
    if any(not z3.is_arith(e) for e in objectives):raise ValueError('arithmetic minimize objectives required')
    ctx = roots[0].ctx
    if any(e.ctx != ctx for e in roots+objectives):raise ValueError('mixed contexts')
    order=[];seen=set();symbols={};leaves={}
    for root in roots+objectives:
        stack=[(root,False)]
        while stack:
            check();node,ready=stack.pop();key=node.get_id()
            if key in seen:continue
            if not z3.is_app(node) or node.sort().kind() not in _SORTS:
                raise ValueError('unsupported AST or sort')
            kind=node.decl().kind()
            if not ready:
                if kind==z3.Z3_OP_UNINTERPRETED:
                    name=str(node.decl().name())
                    if node.num_args() or not _SYMBOL.fullmatch(name) or name in _RESERVED:
                        raise ValueError('unsupported function or symbol')
                    sort=_SORTS[node.sort().kind()]
                    if name in symbols and symbols[name]!=sort:raise ValueError('overloaded symbol')
                    symbols[name]=sort;leaves[key]=name
                elif z3.is_int_value(node) or z3.is_rational_value(node) or z3.is_true(node) or z3.is_false(node):
                    leaves[key]=node.sexpr()  # Atomic only, never recursive printing.
                elif kind not in _OPS:raise ValueError('unsupported operator')
                stack.append((node,True))
                stack.extend((child,False) for child in reversed(node.children()))
            else:
                seen.add(key);order.append(node)
                if len(order)>max_nodes:raise ValueError('node quota exceeded')
    prefix='hiroute_dag_'
    while any(name.startswith(prefix) for name in symbols):prefix='_'+prefix
    names=dict(leaves);definitions=0
    path=Path(path);temporary=None;count=0;digest=hashlib.sha256()
    try:
        with tempfile.NamedTemporaryFile(mode='wb',prefix='.'+path.name+'.partial-',dir=path.parent,delete=False) as stream:
            temporary=Path(stream.name)
            def emit(line,hashed=True):
                nonlocal count
                check();data=(line+'\n').encode('ascii');count+=len(data)
                if count>max_bytes:raise ValueError('byte quota exceeded')
                stream.write(data)
                if hashed:digest.update(data)
            emit('; hiroute exact DAG export v1; no check command')
            for name,sort in sorted(symbols.items()):emit(f'(declare-fun {name} () {sort})')
            for node in order:
                check();key=node.get_id()
                if key in leaves:continue
                name=prefix+str(definitions);definitions+=1
                body='('+_OPS[node.decl().kind()]+' '+ ' '.join(names[c.get_id()] for c in node.children())+')'
                emit(f'(define-fun {name} () {_SORTS[node.sort().kind()]} {body})');names[key]=name
            for root in roots:emit('(assert '+names[root.get_id()]+')')
            for objective in objectives:emit('(minimize '+names[objective.get_id()]+')')
            checksum=digest.hexdigest();emit(_FOOTER.decode('ascii')+checksum,False)
            stream.flush();os.fsync(stream.fileno());check()
        # Same-directory hard link atomically publishes a complete new file and
        # refuses to replace any existing result, including a concurrent writer.
        os.link(temporary,path)
        metadata=dict(unique_nodes=len(order),definitions=definitions,assertions=len(roots),objectives=len(objectives),
                      bytes=count,payload_sha256=checksum)
        if _capture is not None:
            _capture.update(roots=roots,names=names,path=path,metadata=metadata,ctx=ctx)
        return metadata
    finally:
        if temporary is not None:temporary.unlink(missing_ok=True)


def verify_export(path, check=lambda:None, *, max_bytes=256*1024*1024):
    """Verify completion before a caller parses/replays an export, bounded read."""
    if type(max_bytes) is not int or max_bytes < 1:raise ValueError('positive byte quota required')
    digest=hashlib.sha256();total=0;previous=None
    with Path(path).open('rb') as stream:
        while True:
            check();line=stream.readline(max_bytes-total+1)
            if not line:break
            total+=len(line)
            if total>max_bytes:raise ValueError('byte quota exceeded')
            if previous is not None:digest.update(previous)
            previous=line
    expected=_FOOTER+digest.hexdigest().encode('ascii')+b'\n'
    if previous!=expected:raise ValueError('missing or invalid completion digest')
    return dict(bytes=total,payload_sha256=digest.hexdigest())


class AssertionDAGCache:
    """One bounded assertion-only export, never a solver result or parsed AST.

    Roots retain the entire DAG, so retained node IDs cannot be recycled. A hit
    requires identical ordered roots/context and objective roots already in the
    assertion DAG. Otherwise use the original exporter; never guess bindings.
    """
    def __init__(self,max_nodes=500000,max_bytes=64*1024*1024):
        if type(max_nodes) is not int or max_nodes<1 or type(max_bytes) is not int or max_bytes<1:
            raise ValueError('positive cache limits required')
        self.max_nodes=max_nodes;self.max_bytes=max_bytes;self.entry=None

    def export(self,assertions,path,check=lambda:None,*,objectives=()):
        roots=tuple(assertions);objectives=tuple(objectives);entry=self.entry
        check()
        same=(entry is not None and len(roots)==len(entry['roots']) and
              all(a.ctx==entry['ctx'] and z3.eq(a,b) for a,b in zip(roots,entry['roots'])))
        hit=(same and all(z3.is_arith(e) and e.ctx==entry['ctx'] and e.get_id() in entry['names'] for e in objectives))
        if hit:
            try:return self._copy(entry,objectives,Path(path),check)
            except BaseException:
                self.entry=None
                raise
        # A changed assertion set invalidates the one-entry cache. A new
        # objective with the same assertions simply takes the full export path.
        if not same:self.entry=None
        capture={}
        metadata=export_dag(roots,path,check,objectives=objectives,
                            _capture=capture if not objectives else None)
        if not objectives and metadata['unique_nodes']<=self.max_nodes and metadata['bytes']<=self.max_bytes:
            # Names are AST IDs backed by retained roots, not saved across runs.
            self.entry=capture
        return dict(metadata,cache_hit=False)

    def _copy(self,entry,objectives,path,check):
        meta=entry['metadata'];source=entry['path'];temporary=None
        verified=verify_export(source,check,max_bytes=self.max_bytes)
        if verified!={'bytes':meta['bytes'],'payload_sha256':meta['payload_sha256']}:
            raise ValueError('cached assertion audit changed')
        footer=_FOOTER+meta['payload_sha256'].encode('ascii')+b'\n'
        remaining=meta['bytes']-len(footer);digest=hashlib.sha256();size=0
        try:
            with tempfile.NamedTemporaryFile(mode='wb',prefix='.'+path.name+'.partial-',dir=path.parent,delete=False) as stream:
                temporary=Path(stream.name)
                with source.open('rb') as original:
                    while remaining:
                        check();block=original.read(min(1024*1024,remaining))
                        if not block:raise ValueError('truncated cached assertion audit')
                        remaining-=len(block);size+=len(block);digest.update(block);stream.write(block)
                    if original.read(len(footer)+1)!=footer or digest.hexdigest()!=meta['payload_sha256']:
                        raise ValueError('cached assertion audit changed during copy')
                for objective in objectives:
                    check();line=('(minimize '+entry['names'][objective.get_id()]+')\n').encode('ascii')
                    size+=len(line)
                    if size+len(footer)>self.max_bytes:raise ValueError('cached output byte quota')
                    stream.write(line);digest.update(line)
                checksum=digest.hexdigest();tail=_FOOTER+checksum.encode('ascii')+b'\n'
                stream.write(tail);size+=len(tail)
                if size>self.max_bytes:raise ValueError('cached output byte quota')
                stream.flush();os.fsync(stream.fileno());check()
            os.link(temporary,path)
            return dict(meta,objectives=len(objectives),bytes=size,payload_sha256=checksum,cache_hit=True)
        finally:
            if temporary is not None:temporary.unlink(missing_ok=True)
