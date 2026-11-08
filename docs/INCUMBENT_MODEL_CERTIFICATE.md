# Exact incumbent-to-model nonemptiness certificate

This optional development path replaces only the first supported-disjunction
existence search. It independently replays the already frozen incumbent, checks
its original grounded route, and constructs an exact total assignment for all
action ranks, inactive slots, charging-piece indices, maximum branches and both
continuous copies. Continuous variables are exposed as metadata; equations and
objectives are unchanged. Ties choose the first valid closed charging interval
and first maximizing branch. Both copies use the same attained strict-positive
charges, so the support copy's strict constraints hold.

A nonrecursive closed-expression interpreter evaluates EVERY node and assertion
of the exact ordered m.G+x.P+y.P+y.strict roots. It uses integer/Fraction/Boolean
values only and rejects unbound constants, unused/duplicate bindings, arrays,
quantifiers, unsupported operators, undefined division and false assertions.
Even unselected ITE branches are checked. A digest binds structural formula
operators/sorts/constants/children and ordered roots; another binds the complete
assignment. Table and physics identities accompany both. Outer run receipts bind
clean source and runtime. This is a positive exact model certificate, not a
solver SAT result or proof of optimality. No certificate is accepted from disk.

No assignment enters optimization. Original objectives, full domain/H, strict
better/face and attainment tests, lexicographic checks and independent returned
witness replay remain unchanged. Failed certificate checking returns UNKNOWN
without fallback search. The public defaults remain unchanged. The interpreter
currently supports finite arithmetic formulas only; unsupported array encodings
fail closed. All construction/checking/receipt overhead consumes the same
end-to-end deadline and external resource limits. No full-size work is admitted
by this development stage, and no solver-speed claim is made.
