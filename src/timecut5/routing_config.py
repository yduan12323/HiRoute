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
class RoutingConfig:
    search_mode: str = 'full'

    def __post_init__(self):
        if type(self.search_mode) is not str or self.search_mode not in MODES:
            raise ValueError('Explicit full or destination_target mode required')

    def effective_mode(self, role):
        if type(role) is not str or role not in ROLES:
            raise ValueError('Explicit supported routing role required')
        return self.search_mode if role == 'search' else 'full'

    def router_kwargs(self, role):
        return dict(role=role, mode=self.effective_mode(role))

    def problem_kwargs(self, role):
        return dict(terminal_target_routing=self.effective_mode(role) == 'destination_target')

    def create_router(self, graph, compiler_config, cache, *, role, artifact=None):
        from microplan.routing import ExactRouter
        return ExactRouter(graph, compiler_config, cache, artifact=artifact,
                           **self.router_kwargs(role))

    def create_context(self, graph, compiler_config, cache, *, role, anchor_nodes,
                       nodes_sha256, edges_sha256, anchor_catalog_sha256,
                       artifact=None, source_cache_max_bytes=128 * 1024 * 1024,
                       source_cache_max_sources=2):
        """Construct fresh role-local state; hashes are caller-authenticated inputs.

        This does not read graph files, validate supplied file hashes against
        arrays, or authorize execution. Use fresh full-only contexts for witness
        verification/recovery; never pass the search provider to a verifier.
        """
        from .road_provider import TableFreeRoadSelectedLegProvider
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
            return RoutingContext(self, role, router, provider)
        except BaseException:
            router.close()
            raise


class RoutingContext:
    """Own one native router and provider; lifecycle is not thread-safe."""
    def __init__(self, config, role, router, provider):
        self.config, self.role = config, role
        self.router, self.provider = router, provider
        self._closed = False

    def problem(self, query, sites, *, origin_anchor, destination_anchor,
                site_catalog_sha256):
        from .real_adapter import TableFreeRealProblem
        if self._closed or self.router.role != self.role or self.router.mode != self.config.effective_mode(self.role):
            raise ValueError('Closed or changed routing context')
        return TableFreeRealProblem(
            query, sites, self.provider, origin_anchor=origin_anchor,
            destination_anchor=destination_anchor,
            site_catalog_sha256=site_catalog_sha256,
            **self.config.problem_kwargs(self.role))

    def close(self):
        if not self._closed:
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
