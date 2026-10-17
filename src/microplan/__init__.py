"""Microplan primitives; generation dependencies load only when requested."""
from .models import Gateway, RegionGateways, MicroPlan, Task, OpportunityArrays, LocalPairs, PlanBatch
from .compression import pareto_indices, epsilon_cover

__all__ = ['Gateway', 'RegionGateways', 'MicroPlan', 'Task', 'OpportunityArrays',
           'LocalPairs', 'PlanBatch', 'generate_plans', 'pareto_indices', 'epsilon_cover']


def __getattr__(name):
    if name == 'generate_plans':
        from .generation import generate_plans
        globals()[name] = generate_plans
        return generate_plans
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def __dir__():
    return sorted(set(globals()) | set(__all__))
