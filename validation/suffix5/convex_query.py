"""Candidate complete v2 query ledgers; reviewed affine ledgers are unchanged."""
from validation.family5.checker import digest
from .convex_model import query_models
from .query import aggregate, UnresolvedQuery
from .solver import solve_model, SolveBudget, UnresolvedRegime


def solve_query(checked_trace, query_seq, budget=None, on_record=None, on_stage=None):
    budget = budget or SolveBudget()
    query, models = query_models(checked_trace, query_seq)
    records = []
    for index, model in enumerate(models):
        try:
            record = solve_model(model, budget,
                on_stage=(lambda stage: on_stage(index, stage)) if on_stage is not None else None)
        except UnresolvedRegime as error:
            raise UnresolvedQuery(str(error), query_seq, index, models, records,
                                  error.partial_record) from error
        records.append(record)
        if on_record is not None:
            on_record(index, record)
    return dict(schema='family5-suffix-query-ledger-v2', query_seq=query_seq,
                query_sha256=digest(query), trace_sha256=checked_trace.summary['trace_sha256'],
                models=records, result=aggregate(records))
