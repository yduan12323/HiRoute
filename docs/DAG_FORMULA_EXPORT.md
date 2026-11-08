# Development-only exact DAG export

This exporter changes serialization only. It does not simplify or rebuild the
reviewed physical formula, invoke a solver, or alter grounding/replay. It accepts
quantifier-free Bool/Int/Real expressions with an explicit operator whitelist.
Arrays, quantifiers, algebraic numbers, uninterpreted function applications and
unsupported or ambiguous symbols fail closed. It is not a general SMT exporter.

A nonrecursive postorder traversal assigns each compound AST node one typed,
nullary define-fun abbreviation. Every reference points to a preceding node.
Induction on that topological order shows each abbreviation equals its original
subexpression for every assignment to the original free constants. Original
assertions refer to their exact corresponding root. This is definitional
abbreviation, not additional unconstrained variables or quantified axioms.
Exact rational leaf spellings, Boolean structure and integer/real casts remain.
Name prefixes avoid collision with all original free constants.

Traversal and output are linear in unique nodes and edges, apart from name and
literal lengths and sorting declarations. Parsing may expand definitions again;
this exporter therefore provides no solver-speed or real-scale size claim.
It does not introduce query commands or change support/attainment semantics.

Output uses a same-directory temporary file, checked resource/deadline callbacks,
flush/fsync and exclusive atomic publication. A digest footer marks completion;
call verify_export before any future parse/replay. Truncation, changed content,
extra bytes, quota exhaustion and unsupported ASTs are errors. A killed exporter
may leave a .partial scratch file, which is not a published result. The digest
is integrity/completion evidence, not authentication against malicious rewriting.

Tiny tests round-trip complete supported-disjunction formulas and objective
constraints for all eight fixtures and both existing strict-support/primary-face
traps, prove Boolean equivalence with bounded tiny UNSAT checks, and cover exact
rationals, typed nodes, sharing, collision, rejection and partial output. The
existing finite outcome and support/attainment regressions remain in the suite.
The new stage admits no full-size construction, diagnostic or real query.
