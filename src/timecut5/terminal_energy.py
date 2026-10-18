"""Default-off certified immediate-finish screen; full routing remains default.

Only explicit search-role problems may activate. Owned graph bytes, original
native router provenance, exact physical identity and current thread/FP flags
are checked before every nonzero screen. Independent recovery remains off.
"""
from dataclasses import dataclass
from fractions import Fraction as F
import ctypes
import hashlib
import json
import os
import stat
from pathlib import Path
import sys
import threading
import time
from types import MappingProxyType
import numpy as np


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    return digest(Path(path).read_bytes())


def exact(value):
    if type(value) not in (int, F):
        raise TypeError("Exact rational required")
    return F(value)


def hash_id(value):
    if type(value) is not str or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Complete SHA-256 identity required")
    return value


@dataclass(frozen=True)
class OwnedRoutingGraph:
    """Private immutable byte buffers shared by original router and bound.

    NumPy views of immutable bytes cannot be made writeable. The frozen object
    owns all four arrays until every router is closed. Caller arrays are never
    retained. Arbitrary unsafe native writes are outside this process contract.
    """
    node_count: int
    edge_count: int
    source: object
    target: object
    weights: object
    _arrays: tuple
    _layouts: tuple
    identity_bytes: bytes
    copy_cpu_ns: int
    copy_wall_ns: int

    @classmethod
    def capture(cls, graph, *, nodes_sha256, edges_sha256):
        cpu, wall = time.process_time_ns(), time.monotonic_ns()
        n, m = graph.node_count, graph.edge_count
        if type(n) is not int or type(m) is not int or not 1 <= n <= 2**32-1 or not 0 <= m <= 2**32-1:
            raise ValueError("Unsupported native graph index domain")
        arrays = []
        for name, array, dtype in (("source",graph.source,np.dtype("int64")),
                ("target",graph.target,np.dtype("int64")),
                ("travel_time",graph.weights["travel_time"],np.dtype("float64")),
                ("distance",graph.weights["distance"],np.dtype("float64"))):
            if type(array) is not np.ndarray or array.shape != (m,) or array.dtype != dtype or not array.flags.c_contiguous:
                raise ValueError("Exact original packed array format required")
            # One immutable bytes copy; no writeable array with a surviving alias.
            arrays.append(np.frombuffer(array.tobytes(order="C"), dtype=dtype))
        s,t,dt,dl=arrays
        if (m and (s.min()<0 or t.min()<0 or s.max()>=n or t.max()>=n) or
                not np.isfinite(dt).all() or not np.isfinite(dl).all() or
                (dt<0).any() or (dl<0).any()):
            raise ValueError("Original endpoint/time/distance contract invalid")
        identity=dict(schema="hiroute.owned_terminal_graph.v1",node_count=n,edge_count=m,
            nodes_sha256=hash_id(nodes_sha256),edges_sha256=hash_id(edges_sha256),
            arrays={name:digest(memoryview(a).cast("B")) for name,a in zip(
                ("source","target","travel_time","distance"),arrays)},
            packed_bytes=sum(a.nbytes for a in arrays))
        layouts=tuple((a.dtype.str,a.strides,int(a.ctypes.data),a.shape) for a in arrays)
        return cls(n,m,s,t,MappingProxyType(dict(travel_time=dt,distance=dl)),tuple(arrays),layouts,
                   canonical(identity),time.process_time_ns()-cpu,time.monotonic_ns()-wall)

    def check_owned(self):
        if (self.source is not self._arrays[0] or self.target is not self._arrays[1] or
                self.weights["travel_time"] is not self._arrays[2] or
                self.weights["distance"] is not self._arrays[3] or
                any(a.flags.writeable or type(a.base) is not bytes or
                    (a.dtype.str,a.strides,int(a.ctypes.data),a.shape)!=layout
                    for a,layout in zip(self._arrays,self._layouts))):
            raise ValueError("Owned graph storage replaced or made mutable")


class UnsupportedEnvironment(RuntimeError):
    pass


def mapped_library(library,path,symbols):
    """Linux mapping + symbol ownership, including same-path replacement defense."""
    path=Path(path).resolve();info=path.stat()
    if not stat.S_ISREG(info.st_mode):raise ValueError('Regular native artifact required')
    rows=[]
    for line in Path('/proc/self/maps').read_text().splitlines():
        fields=line.split(maxsplit=5)
        if len(fields)==6 and fields[5]==str(path):
            span,permissions,_,device,inode,_=fields
            if int(inode)!=info.st_ino or device!=f'{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}':
                raise ValueError('Mapped native inode/device differs')
            rows.append((span,permissions))
    if not any('x' in permissions for _,permissions in rows):raise ValueError('Exact executable mapping missing')
    class Info(ctypes.Structure):
        _fields_=[('name',ctypes.c_char_p),('base',ctypes.c_void_p),('symbol',ctypes.c_char_p),('address',ctypes.c_void_p)]
    libc=ctypes.CDLL(None);libc.dladdr.argtypes=[ctypes.c_void_p,ctypes.POINTER(Info)];libc.dladdr.restype=ctypes.c_int
    for symbol in symbols:
        address=ctypes.cast(getattr(library,symbol),ctypes.c_void_p).value;record=Info()
        if (not libc.dladdr(address,ctypes.byref(record)) or not record.name or
                Path(os.fsdecode(record.name)).resolve()!=path or
                not any('x' in permissions and int(span.split('-')[0],16)<=address<int(span.split('-')[1],16)
                        for span,permissions in rows)):
            raise ValueError('Native symbol owner differs')
    return dict(path=str(path),inode=info.st_ino,device=info.st_dev,symbols=list(symbols))


class Kernel:
    """Load an explicitly pinned local build receipt; never compile at activation."""
    def __init__(self, artifact, cache):
        from .terminal_energy_artifact import EnergyArtifact
        if type(artifact) is not EnergyArtifact:
            raise ValueError('Package-owned EnergyArtifact required')
        receipt=artifact.authenticate()
        binary=artifact.load_copy(cache)
        self.lib=ctypes.CDLL(str(binary))
        mapping=mapped_library(self.lib,binary,('energy_build','energy_validate','energy_labels','energy_environment_supported','energy_destroy'))
        if file_digest(binary)!=receipt['artifact_sha256']:
            raise ValueError('Energy load copy changed')
        self.artifact=artifact
        self.identity_bytes=canonical(dict(artifact_identity_sha256=artifact.identity_sha256,
            mapping=mapping,receipt=receipt))
        self.lib.energy_environment_supported.restype=ctypes.c_int
        self.lib.energy_last_error.restype=ctypes.c_char_p
        ints=np.ctypeslib.ndpointer(dtype=np.int64,ndim=1,flags="C_CONTIGUOUS")
        doubles=np.ctypeslib.ndpointer(dtype=np.float64,ndim=1,flags="C_CONTIGUOUS")
        self.lib.energy_build.argtypes=[ctypes.c_uint64,ctypes.c_uint64,ints,ints,doubles,
            ctypes.c_uint64,ctypes.c_uint,ctypes.c_uint64]
        self.lib.energy_build.restype=ctypes.c_void_p
        self.lib.energy_validate.argtypes=[ctypes.c_void_p,ints,ints,doubles]
        self.lib.energy_validate.restype=ctypes.c_int
        self.lib.energy_labels.argtypes=[ctypes.c_void_p]
        self.lib.energy_labels.restype=ctypes.POINTER(ctypes.c_uint64)
        for name in ("energy_checked_edges","energy_heap_peak"):
            getattr(self.lib,name).argtypes=[ctypes.c_void_p]
            getattr(self.lib,name).restype=ctypes.c_uint64
        self.lib.energy_destroy.argtypes=[ctypes.c_void_p]

    def supported(self):
        return bool(self.lib.energy_environment_supported())

    def require_supported(self):
        if not self.supported():raise UnsupportedEnvironment("Unsupported current binary64/thread environment")


def _physical_identity(problem,provider):
    return (problem.rate,problem.reserve,problem.destination,problem.origin,
            problem.capacity,problem.floor,tuple(sorted(problem.site_anchors.items())),
            tuple(sorted(provider.anchor_nodes.items())))


def _native_identity(router, expected_source):
    """Use the installed router's actual artifact and mapped-object boundary."""
    from microplan.routing import ExactRouter
    if (type(router) is not ExactRouter or router.role != 'search' or
            router.mode not in ('full', 'destination_target')):
        raise ValueError('Explicit package full or destination-target search router required')
    receipt=router.verify_artifact()
    if receipt['source_sha256'] != expected_source:
        raise ValueError('Original routing source differs')
    # The target routine is the same native relaxation/settlement prefix as
    # full routing. Its finalized destination path has the same binary64 sums,
    # so the path-energy certificate applies unchanged. Record the actual mode
    # without making the role-neutral provider source binding mode-dependent.
    return dict(source_sha256=expected_source, routing_mode=router.mode,
        artifact_identity_sha256=receipt['artifact_identity_sha256'],
        artifact_sha256=receipt['artifact_sha256'],
        build_spec=receipt['build_spec'],mapping=router._mapped_identity)


class RoutingHistoryGuard:
    """Bind each provider cache production to checked RN arithmetic history.

    The supported API is single-threaded. The original reviewed native call
    never changes FP controls internally. Entry/exit probes cannot detect a
    hostile signal handler that changes and restores controls inside one call.
    Such asynchronous control mutation is outside this contract.
    """
    def __init__(self, provider, kernel, unsupported):
        cpu,wall=time.process_time_ns(),time.monotonic_ns()
        if (type(kernel) is not Kernel or unsupported not in ('reject','zero') or
                type(provider.graph) is not OwnedRoutingGraph or
                provider.router.graph is not provider.graph):
            raise ValueError('Owned provider and explicit arithmetic guard required')
        if (getattr(provider, '_terminal_energy_route_guard', None) is not None or
                provider.legs or provider.edge_witnesses or provider._source_labels or
                provider.source_run_count or provider.target_run_count or
                provider.router.target_calls or provider.source_cache_bytes or
                provider.route_wall_ns or provider.route_process_cpu_ns):
            raise ValueError('Unguarded prior selected-routing history cannot be adopted')
        self.provider=provider;self.graph=provider.graph;self.router=provider.router
        self.anchors=tuple(sorted(provider.anchor_nodes.items()))
        if digest(canonical(dict(self.anchors)))!=provider.source_sha256['anchors']:
            raise ValueError('Selected-routing initial anchor digest differs')
        self.native_handle=provider.router.handle;self.native_library=provider.router.lib
        self.native_object=provider.router._native_lib
        self.failure_check=None
        self.cache_policy=(provider.source_cache_max_bytes,provider.source_cache_max_sources)
        if any(type(v) is not int or v<0 for v in self.cache_policy):
            raise ValueError('Selected-routing cache policy invalid')
        self.kernel=kernel;self.unsupported=unsupported
        self.pid=os.getpid();self.thread=threading.get_ident()
        self.native=_native_identity(provider.router,provider.source_sha256['router'])
        self.sources=canonical(provider.source_sha256)
        self.provenance=canonical(provider.router.provenance)
        self.status='guarded';self.pending=0;self.completed=0
        self._observation_state=(self.status,self.pending,self.completed)
        self.check(provider)
        provider._terminal_energy_route_guard=self
        self.install_cpu_ns=time.process_time_ns()-cpu;self.install_wall_ns=time.monotonic_ns()-wall

    def check(self,provider):
        if self.failure_check is not None:self.failure_check()
        self.router.validate_binding()
        if (provider is not self.provider or provider.graph is not self.graph or
                provider.router is not self.router or self.router.graph is not self.graph or
                not self.native_handle or self.router.handle!=self.native_handle or
                self.router.lib is not self.native_library or
                self.router._native_lib is not self.native_object or
                tuple(sorted(provider.anchor_nodes.items()))!=self.anchors or
                (provider.source_cache_max_bytes,provider.source_cache_max_sources)!=self.cache_policy or
                canonical(provider.source_sha256)!=self.sources or
                canonical(self.router.provenance)!=self.provenance):
            raise ValueError('Selected-routing history owner/source changed')
        self.graph.check_owned()
        if self.status=='invalid':raise ValueError('Selected-routing history interrupted or invalid')
        if self.status=='disabled_unsupported':return False
        if self.pid!=os.getpid() or self.thread!=threading.get_ident() or not self.kernel.supported():
            if self.unsupported=='reject':raise UnsupportedEnvironment('Selected-routing arithmetic environment unsupported')
            self.status='disabled_unsupported';self._observation_state=(self.status,self.pending,self.completed);return False
        return True

    def begin(self,provider):
        self.check(provider)
        self.pending+=1
        self._observation_state=(self.status,self.pending,self.completed)

    def end(self,provider):
        self.check(provider)
        if self.pending<=0:raise ValueError('Selected-routing history nesting invalid')
        self.pending-=1;self.completed+=1
        self._observation_state=(self.status,self.pending,self.completed)

    def abort(self):
        self.status='invalid';self.pending=max(0,self.pending-1)
        self._observation_state=(self.status,self.pending,self.completed)

    def admitted(self,provider,kernel,unsupported):
        if (kernel.identity_bytes!=self.kernel.identity_bytes or unsupported!=self.unsupported or
                getattr(provider,'_terminal_energy_route_guard',None) is not self or self.pending):
            raise ValueError('Selected-routing guard identity or completed history differs')
        return self.check(provider)

    @property
    def receipt(self):
        return dict(schema='hiroute.selected_routing_arithmetic_history.v1',status=self.status,
            installed_before_first_route=True,installation_cpu_ns=self.install_cpu_ns,installation_wall_ns=self.install_wall_ns,
            completed_guarded_operations=self.completed,
            pending_operations=self.pending,kernel_sha256=digest(self.kernel.identity_bytes),
            original_native=self.native,anchors_sha256=digest(canonical(dict(self.anchors))),cache_policy=list(self.cache_policy),check_scope='selected leg cached/miss and source labels entry/exit including Python selected-edge replay')




class TerminalEnergyScreen:
    """Owned certificate, no graph-sized scans on finish calls.

    Construction errors fail closed. Only an explicitly unsupported FP/thread
    environment may select the declared zero fallback; it never activates a
    nonzero certificate. A fallback disables the object permanently.
    """
    def __init__(self,problem,provider,*,kernel,quantum_exponent,cap,unsupported="reject"):
        if getattr(problem,"routing_role",None)!="search":raise ValueError("Only explicit search role may activate")
        if type(provider.graph) is not OwnedRoutingGraph or provider.router.graph is not provider.graph:
            raise ValueError("Original router and bound must share the owned graph snapshot")
        if type(kernel) is not Kernel or type(quantum_exponent) is not int or not 0<=quantum_exponent<=30:
            raise ValueError("Supported pinned kernel and dyadic quantum required")
        if type(cap) is not int or not 1<=cap<=2**62-1 or unsupported not in ("reject","zero"):
            raise ValueError("Invalid finite cap or fallback policy")
        self.provider,self.graph,self.kernel=provider,provider.graph,kernel
        history=getattr(provider,'_terminal_energy_route_guard',None)
        if history is None:history=RoutingHistoryGuard(provider,kernel,unsupported)
        if type(history) is not RoutingHistoryGuard:
            raise ValueError('Authenticated selected-routing history guard required')
        self.history=history
        history.admitted(provider,kernel,unsupported)
        if (exact(problem.rate)<0 or exact(problem.reserve)<0 or problem.reserve>problem.capacity or
                problem.rate!=F(problem.case['consumption_kwh_per_m']) or
                problem.reserve!=F(problem.case['reserve_kwh']) or
                problem.destination!=problem.case['destination'] or problem.origin!=problem.case['origin'] or
                digest(canonical(provider.anchor_nodes))!=provider.source_sha256['anchors']):
            raise ValueError('Problem/query or original anchor binding differs before activation')
        graph_identity=json.loads(self.graph.identity_bytes)
        if any(graph_identity[name+'_sha256']!=provider.source_sha256[name] for name in ('nodes','edges')):
            raise ValueError('Owned graph file bindings differ from original provider')
        self.physical=_physical_identity(problem,provider)
        self.anchors=dict(provider.anchor_nodes)
        self.thread=threading.get_ident();self.pid=os.getpid()
        self.unsupported=unsupported;self.status="constructing";self.calls=0;self.skipped=0;self.completed=0
        self.router_provenance=canonical(provider.router.provenance)
        self.original_native=_native_identity(provider.router,provider.source_sha256['router'])
        self.provider_sources=canonical(provider.source_sha256)
        self.query_sha256=digest(canonical(problem.case))
        self._lower=MappingProxyType({})
        self.graph.check_owned()
        cpu,wall=time.process_time_ns(),time.monotonic_ns()
        n=self.graph.node_count;m=self.graph.edge_count;k=n-1;u=F(1,2**53)
        self.beta=max(F(0),1-k*u);quantum=F(1,2**quantum_exponent)
        # Exact upper-rounding overflow guard; reject unsupported construction,
        # rather than quietly treating it as an activated zero certificate.
        largest=F.from_float(float(self.graph.weights["distance"].max())) if m else F(0)
        if k*u>=1 or F(k)*largest/(1-k*u)>F.from_float(sys.float_info.max):
            raise ValueError("Unsupported possible accumulation overflow")
        identity=dict(schema="hiroute.certified_terminal_energy.v1",query_sha256=self.query_sha256,
            graph_sha256=digest(self.graph.identity_bytes),graph=json.loads(self.graph.identity_bytes),
            provider_sources_sha256=digest(self.provider_sources),
            router_provenance_sha256=digest(self.router_provenance),
            original_native=self.original_native,routing_history=self.history.receipt,
            kernel=json.loads(kernel.identity_bytes),python_source_sha256=file_digest(__file__),
            destination=problem.destination,anchors_sha256=digest(canonical(self.anchors)),
            rate=str(problem.rate),reserve=str(problem.reserve),quantum_exponent=quantum_exponent,
            cap=cap,beta=str(self.beta),unsupported_policy=unsupported,
            graph_copy_cpu_ns=self.graph.copy_cpu_ns,graph_copy_wall_ns=self.graph.copy_wall_ns,
            graph_copy_retained_bytes=32*m,construction_packed_scratch_bytes=16*n+8+4*m,
            construction_potential_bytes=8*n)
        if not self._environment():
            identity.update(status=self.status,certificate_validated=False,checked_edges=0)
        else:
            build_cpu,build_wall=time.process_time_ns(),time.monotonic_ns()
            handle=kernel.lib.energy_build(n,m,self.graph.source,self.graph.target,
                self.graph.weights["distance"],self.anchors[problem.destination],quantum_exponent,cap)
            identity.update(build_with_first_validation_cpu_ns=time.process_time_ns()-build_cpu,
                build_with_first_validation_wall_ns=time.monotonic_ns()-build_wall)
            if not handle:raise RuntimeError(kernel.lib.energy_last_error().decode())
            try:
                validation_cpu,validation_wall=time.process_time_ns(),time.monotonic_ns()
                # Independent second scan at the Python ownership transition.
                if not kernel.lib.energy_validate(handle,self.graph.source,self.graph.target,self.graph.weights["distance"]):
                    raise ValueError(kernel.lib.energy_last_error().decode())
                identity.update(second_validation_cpu_ns=time.process_time_ns()-validation_cpu,
                    second_validation_wall_ns=time.monotonic_ns()-validation_wall)
                labels=kernel.lib.energy_labels(handle)
                view=np.ctypeslib.as_array(labels,shape=(n,))
                potentials={a:int(labels[node]) for a,node in self.anchors.items()}
                self._lower=MappingProxyType({a:exact(problem.rate)*self.beta*quantum*p for a,p in potentials.items()})
                self.status="active"
                identity.update(status=self.status,certificate_validated=True,
                    checked_edges=int(kernel.lib.energy_checked_edges(handle)),
                    full_edge_validation_passes=2,heap_peak_nodes=int(kernel.lib.energy_heap_peak(handle)),
                    potential_sha256=digest(memoryview(view).cast("B")),anchor_potentials=potentials)
                del view
            finally:kernel.lib.energy_destroy(handle)
        identity.update(setup_cpu_ns=time.process_time_ns()-cpu,setup_wall_ns=time.monotonic_ns()-wall,
            retained_full_potential_bytes=0,retained_anchor_count=len(self._lower))
        self._receipt_bytes=canonical(identity)
        # Separately versioned multi-leg access pins construction evidence.
        # The immediate-finish API and its private lower map stay unchanged.
        self._suffix_energy_certificate_bytes=self._receipt_bytes
        self._observation_state=(self.calls,self.completed,self.skipped,self.status)

    def _environment(self):
        history_supported=self.history.admitted(self.provider,self.kernel,self.unsupported)
        if not history_supported:
            self.status="disabled_unsupported";self._lower=MappingProxyType({});return False
        if self.status=="disabled_unsupported":return False
        if self.pid!=os.getpid() or self.thread!=threading.get_ident() or not self.kernel.supported():
            if self.unsupported=="reject":raise UnsupportedEnvironment("Current thread/process/FP flags differ")
            self.status="disabled_unsupported";self._lower=MappingProxyType({});return False
        return True

    @property
    def receipt(self):
        value=json.loads(self._receipt_bytes)
        value['activation_status']=value['status']
        value.update(status=self.status,calls=self.calls,skipped_immediate_finishes=self.skipped,routing_history=self.history.receipt)
        return value

    def certified_suffix_energy_v1(self, problem, anchor):
        """Guarded multi-leg potential; never an unguarded prefix-pruning API.

        Signed per-leg potential differences telescope under the same native
        binary64/history contract. This accessor certifies route consumption,
        not charging curves, arbitrary frontier clocks, or a pruning decision.
        An explicit unsupported-zero policy returns a disabled None value.
        """
        from .remaining_charge_runtime import SuffixPotentialV1
        from .real_adapter import _TableFreeRealLegs
        if type(anchor) is not str or anchor not in self.anchors:
            raise ValueError('Unknown suffix-energy anchor')
        if (getattr(problem, '_terminal_energy_screen', None) is not self or
                getattr(problem, 'routing_role', None) != 'search' or
                problem.provider is not self.provider or
                type(getattr(problem, 'legs', None)) is not _TableFreeRealLegs or
                problem.legs.provider is not self.provider or
                type(problem.rate) is not F or type(problem.legs.rate) is not F or
                problem.legs.rate != problem.rate or
                self.provider.graph is not self.graph or
                self.provider.router.graph is not self.graph or
                _physical_identity(problem, self.provider) != self.physical or
                canonical(self.provider.source_sha256) != self.provider_sources or
                canonical(self.provider.router.provenance) != self.router_provenance):
            raise ValueError('Suffix-energy problem/source/history binding changed')
        receipt = json.loads(self._receipt_bytes)
        construction = {k:v for k,v in receipt.items()
                        if k not in ('activation_cpu_ns', 'activation_wall_ns')}
        if canonical(construction) != self._suffix_energy_certificate_bytes:
            raise ValueError('Suffix-energy construction certificate changed')
        binding = digest(canonical(dict(schema='hiroute.suffix_energy_potential.v1',
            construction_sha256=digest(self._suffix_energy_certificate_bytes))))
        self.graph.check_owned()
        if not self._environment():
            return SuffixPotentialV1('energy', 'disabled_unsupported', None, binding)
        if self.status != 'active' or receipt.get('certificate_validated') is not True:
            raise ValueError('Validated suffix-energy certificate required')
        potentials = receipt['anchor_potentials']
        exponent, cap = receipt['quantum_exponent'], receipt['cap']
        if (set(potentials) != set(self.anchors) or
                any(type(value) is not int or not 0 <= value <= cap
                    for value in potentials.values()) or
                potentials[problem.destination] != 0 or
                F(receipt['rate']) != problem.rate or
                F(receipt['beta']) != max(F(0), F(1)-F(self.graph.node_count-1, 2**53))):
            raise ValueError('Invalid suffix-energy certificate quantities')
        lower = problem.rate * F(receipt['beta']) * F(potentials[anchor], 2**exponent)
        return SuffixPotentialV1('energy', 'active', lower, binding)

    def reject(self,problem,pieces):
        # Atomic immutable tuples are observational only. No clocks, locks, I/O
        # or extra route calls at this decision boundary.
        self.calls+=1
        self._observation_state=(self.calls,self.completed,self.skipped,self.status)
        try:decision=self._reject(problem,pieces)
        except BaseException:
            self._observation_state=(self.calls,self.completed,self.skipped,'error')
            raise
        self.completed+=1
        self._observation_state=(self.calls,self.completed,self.skipped,self.status)
        return decision

    def _reject(self,problem,pieces):
        if (getattr(problem,"routing_role",None)!="search" or
                self.provider is not problem.provider or self.provider.graph is not self.graph or
                self.provider.router.graph is not self.graph or
                not getattr(self.provider.router,'handle',None) or
                _physical_identity(problem,self.provider)!=self.physical or
                canonical(self.provider.source_sha256)!=self.provider_sources or
                canonical(self.provider.router.provenance)!=self.router_provenance):
            raise ValueError("Active screen physical/source/native binding changed")
        self.graph.check_owned()
        if not self._environment() or not pieces or pieces[0].state.remaining_schedule:
            return False
        anchor=pieces[0].state.anchor
        if any(p.state.anchor!=anchor for p in pieces):raise ValueError("Mixed anchor family")
        threshold=problem.reserve+self._lower[anchor]
        reject=all(p.domain.hi<threshold or p.domain.hi==threshold and not p.domain.right_closed for p in pieces)
        if reject:self.skipped+=1
        return reject


def activate(problem,provider,configuration,*,kernel,observation=None):
    """Construct and publish before attachment; verification never calls here."""
    cpu,wall=time.process_time_ns(),time.monotonic_ns()
    screen=TerminalEnergyScreen(problem,provider,kernel=kernel,
        quantum_exponent=configuration.quantum_exponent,cap=configuration.cap,
        unsupported=configuration.unsupported)
    receipt=json.loads(screen._receipt_bytes)
    receipt.update(activation_cpu_ns=time.process_time_ns()-cpu,
        activation_wall_ns=time.monotonic_ns()-wall)
    screen._receipt_bytes=canonical(receipt)
    if observation is not None:observation.activated(screen)
    problem._terminal_energy_screen=screen
    return screen


def policy_binding(configuration,artifact):
    from .terminal_energy_artifact import EnergyArtifact
    if type(artifact) is not EnergyArtifact:raise ValueError('Package-owned EnergyArtifact required')
    receipt=artifact.authenticate()
    return dict(schema='hiroute.package_terminal_energy_policy.v1',
        configuration=dict(quantum_exponent=configuration.quantum_exponent,
            cap=configuration.cap,unsupported=configuration.unsupported),
        kernel_artifact_identity_sha256=receipt['artifact_identity_sha256'],
        kernel_semantic_contract_sha256=receipt['semantic_contract_sha256'],
        python_source_sha256=file_digest(__file__),
        arithmetic='exact_binary64_floor_dyadic_all_edge_certificate_Bernoulli_beta_v1',
        beta='max(0,1-(node_count-1)/2^53)',
        use='immediate_finish_only_strict_or_open_equality_preserve_expansion',
        history='owned_arrays_anchor_cache_native_binding_RN_FTZ_DAZ_x87_before_first_route_entry_exit',
        verification='independent_full_only_inactive_screen')
