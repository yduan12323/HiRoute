"""Explicit opt-in native routing contexts; no solver, graph loader or admission.

Callers authenticate graph input files and preserve immutable array ownership.
Every context owns a fresh native handle and provider caches. A single prepared
package-native artifact can be shared across contexts, but caches cannot.
"""
from dataclasses import dataclass

MODES = ('full', 'destination_target')
ROLES = ('search', 'generation', 'verification', 'durable_verification',
         'recovery', 'landmark')


@dataclass(frozen=True)
class TerminalEnergyConfig:
    """Explicit finite certificate policy; absence on RoutingConfig means off."""
    quantum_exponent: int = 20
    cap: int = 2**62-1
    unsupported: str = 'reject'

    def __post_init__(self):
        if (type(self.quantum_exponent) is not int or not 0 <= self.quantum_exponent <= 30
                or type(self.cap) is not int or not 1 <= self.cap <= 2**62-1
                or type(self.unsupported) is not str or self.unsupported not in ('reject', 'zero')):
            raise ValueError('Explicit bounded terminal-energy policy required')


@dataclass(frozen=True)
class RoutingConfig:
    search_mode: str = 'full'
    terminal_energy: TerminalEnergyConfig | None = None

    def __post_init__(self):
        if type(self.search_mode) is not str or self.search_mode not in MODES:
            raise ValueError('Explicit full or destination_target mode required')
        if self.terminal_energy is not None and type(self.terminal_energy) is not TerminalEnergyConfig:
            raise ValueError('Explicit immutable TerminalEnergyConfig required')

    def effective_mode(self, role):
        if type(role) is not str or role not in ROLES:
            raise ValueError('Explicit supported routing role required')
        return self.search_mode if role == 'search' else 'full'

    def router_kwargs(self, role):
        return dict(role=role, mode=self.effective_mode(role))

    def problem_kwargs(self, role):
        return dict(terminal_target_routing=self.effective_mode(role) == 'destination_target')

    def create_router(self, graph, compiler_config, cache, *, role, artifact=None):
        # This low-level method never installs an energy screen or cache guard.
        from microplan.routing import ExactRouter
        return ExactRouter(graph, compiler_config, cache, artifact=artifact,
                           **self.router_kwargs(role))

    def create_context(self, graph, compiler_config, cache, *, role, anchor_nodes,
                       nodes_sha256, edges_sha256, anchor_catalog_sha256,
                       artifact=None, source_cache_max_bytes=128 * 1024 * 1024,
                       source_cache_max_sources=2, energy_artifact=None, observation=None):
        """Construct fresh role-local state; hashes are caller-authenticated inputs.

        This does not read graph files, validate supplied file hashes against
        arrays, or authorize execution. Use fresh full-only contexts for witness
        verification/recovery; never pass the search provider to a verifier.
        """
        from .road_provider import TableFreeRoadSelectedLegProvider
        self.effective_mode(role)  # reject invalid role before builds/copies
        policy, kernel, owned = None, None, None
        if self.terminal_energy is not None:
            from .terminal_energy import OwnedRoutingGraph, Kernel, policy_binding
            from .terminal_energy_artifact import build_artifact as build_energy
            if energy_artifact is None:
                energy_artifact = build_energy(dict(compiler=compiler_config['compiler'],
                    compiler_flags=['-O3','-std=c++17','-fno-fast-math','-frounding-math']),cache)
            policy = policy_binding(self.terminal_energy,energy_artifact)
            if role == 'search':
                owned=OwnedRoutingGraph.capture(graph,nodes_sha256=nodes_sha256,edges_sha256=edges_sha256)
                graph=owned
                kernel=Kernel(energy_artifact,cache)
        elif energy_artifact is not None:
            raise ValueError('Energy artifact requires an explicit energy policy')
        if observation is not None:observation.bind_context(self,role,policy,owned)
        router = self.create_router(graph, compiler_config, cache, role=role,
                                    artifact=artifact)
        try:
            provider = TableFreeRoadSelectedLegProvider(
                graph, router, anchor_nodes, nodes_sha256=nodes_sha256,
                edges_sha256=edges_sha256,
                router_sha256=router.provenance['source_sha256'],
                anchor_catalog_sha256=anchor_catalog_sha256,
                source_cache_max_bytes=source_cache_max_bytes,
                source_cache_max_sources=source_cache_max_sources)
            if policy is not None:
                from .terminal_energy import canonical,digest,RoutingHistoryGuard
                # Stable policy belongs to source identity for every role. Only
                # search constructs/uses a certificate; selected legs unchanged.
                provider.source_sha256['terminal_energy_policy']=digest(canonical(policy))
                if role == 'search':
                    guard=RoutingHistoryGuard(provider,kernel,self.terminal_energy.unsupported)
                    if observation is not None:
                        guard.failure_check=observation.check
                        observation.bind_guard(guard)
            return RoutingContext(self, role, router, provider, energy_policy=policy,
                                  energy_kernel=kernel, observation=observation)
        except BaseException:
            router.close()
            raise


class RoutingContext:
    """Own one native router and provider; lifecycle is not thread-safe."""
    def __init__(self, config, role, router, provider, *, energy_policy=None, energy_kernel=None, observation=None):
        self.config, self.role = config, role
        self.router, self.provider = router, provider
        self._closed = False
        self._verified_close = False
        self._initial_config = config
        self.energy_policy, self._energy_kernel = energy_policy, energy_kernel
        self.observation = observation
        self._policy_bytes = None
        if energy_policy is not None:
            from .terminal_energy import canonical
            self._policy_bytes = canonical(energy_policy)
            if role == 'search':
                provider._terminal_energy_route_guard.failure_check=self.check_policy

    def check_policy(self):
        if self.config != self._initial_config:
            raise ValueError('Routing policy changed')
        if self.observation is not None:self.observation.check()
        if self._policy_bytes is not None:
            from .terminal_energy import canonical,digest
            if (canonical(self.energy_policy) != self._policy_bytes or
                    self.provider.source_sha256.get('terminal_energy_policy') != digest(self._policy_bytes)):
                raise ValueError('Energy policy binding changed')

    def problem(self, query, sites, *, origin_anchor, destination_anchor,
                site_catalog_sha256):
        from .real_adapter import TableFreeRealProblem
        self.check_policy()
        if self._closed or self.router.role != self.role or self.router.mode != self.config.effective_mode(self.role):
            raise ValueError('Closed or changed routing context')
        problem = TableFreeRealProblem(
            query, sites, self.provider, origin_anchor=origin_anchor,
            destination_anchor=destination_anchor,
            site_catalog_sha256=site_catalog_sha256,
            **self.config.problem_kwargs(self.role))
        if self.config.terminal_energy is not None and self.role == 'search':
            from .terminal_energy import activate
            activate(problem,self.provider,self.config.terminal_energy,
                     kernel=self._energy_kernel,observation=self.observation)
        elif self.observation is not None:
            self.observation.inactive_problem(problem)
        return problem

    def close(self):
        if not self._closed:
            try:
                # Errors still release native resources, but cannot authenticate
                # a normal completion or relabel changed policy as original.
                if self.config != self._initial_config:
                    raise ValueError('Routing policy changed before closure')
                if self._policy_bytes is not None:
                    from .terminal_energy import canonical,digest
                    if (canonical(self.energy_policy)!=self._policy_bytes or
                            self.provider.source_sha256.get('terminal_energy_policy')!=digest(self._policy_bytes)):
                        raise ValueError('Energy policy changed before closure')
                if self.energy_policy is not None or self.observation is not None:
                    self.router.verify_artifact()
                    if self._energy_kernel is not None:self._energy_kernel.artifact.authenticate()
                self._verified_close = True
            finally:
                self.router.close()
                self._closed = True

    def __enter__(self):
        if self._closed:
            raise ValueError('Closed routing context')
        return self

    def __exit__(self, *exc):
        self.close()


def require_full_verifier(provider, *, fresh):
    """Guard new explicit contexts at independent replay trust boundaries.

    Legacy full-only providers keep their existing contract. Explicit contexts
    may never use a search router as an independent verifier, even if its current
    mode is full. This is a supported-API guard, not a hostile Python sandbox.
    """
    router = getattr(provider, 'router', None)
    role = getattr(router, 'role', None)
    if role is None:
        return
    if (role not in ('verification', 'durable_verification', 'recovery') or
            router.mode != 'full' or router.target_calls != 0 or
            provider.target_run_count != 0):
        raise ValueError('Independent full-only verification context required')
    router.verify_artifact()
    router.validate_binding()
    if fresh and (router.full_calls or provider.source_run_count or provider.legs or
                  provider.edge_witnesses or provider._source_labels):
        raise ValueError('Fresh independent verification context required')
