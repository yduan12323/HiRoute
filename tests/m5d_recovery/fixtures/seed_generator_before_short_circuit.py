"""Frozen pre-change generator only; never imported as production code."""
def iter_constructive_seed_candidates(query: Mapping, table: ImmutableLegTable):
    """Deterministic bounded proposals for an independent replay checker.

    This only constructs candidate sequences and charge quantities from frozen
    selected legs. It does not read REF/FLAT/HIER outputs, solve a continuous
    optimization problem, or certify that a proposal is feasible.
    """
    from .sparse_seed import SparseSeedCatalog
    if not isinstance(table, (ImmutableLegTable, SparseSeedCatalog)) or not isinstance(query, Mapping):
        raise ValueError("Bound selected-leg source and exact query required")
    bindings = (("origin", table.origin_anchor),
                ("destination", table.destination_anchor),
                ("hierarchy_sha256", table.hierarchy_sha256))
    if isinstance(table, ImmutableLegTable):
        bindings += (("leg_payload_sha256", table.payload_sha256),
                     ("selection_certificate_sha256", table.selection_certificate_sha256))
    else:
        bindings += (("sparse_domain_sha256", table.domain_sha256),)
    for key, expected in bindings:
        if query.get(key) != expected:
            raise ValueError(f"Unbound seed query field {key}")
    def exact_field(key: str) -> Fraction:
        value = query.get(key)
        if isinstance(value, bool) or not isinstance(value, (str, int, Fraction)):
            raise ValueError(f"Seed scalar {key} must be exact")
        return Fraction(value)
    initial, capacity = exact_field("initial_energy_kwh"), exact_field("capacity_kwh")
    reserve, floor_energy = exact_field("reserve_kwh"), exact_field("minimum_energy_kwh")
    consumption = exact_field("consumption_kwh_per_m")
    bound = query.get("H_ref")
    if (type(bound) is not int or bound < 0 or not 0 <= floor_energy <= initial <= capacity
            or not floor_energy <= reserve <= capacity or consumption <= 0):
        raise ValueError("Invalid seed battery or diagnostic depth domain")
    has_schedule = query.get("schedule") is not None
    remaining = query.get("initial_remaining_schedule", int(has_schedule))
    if type(remaining) is not int or remaining not in (0, 1) or (remaining and not has_schedule):
        raise ValueError("Invalid initial remaining schedule state")
    direct = table.leg(table.origin_anchor, table.destination_anchor)
    if not remaining and direct.reachable and initial - direct.energy(consumption) >= reserve:
        yield ((), ())
    if bound == 0:
        return
    for site_id in sorted(table.sites):
        site = table.site(site_id)
        if site.anchor_id == table.destination_anchor:
            continue
        inbound = table.leg(table.origin_anchor, site.anchor_id)
        outbound = table.leg(site.anchor_id, table.destination_anchor)
        if not inbound.reachable or not outbound.reachable:
            continue
        arrival = initial - inbound.energy(consumption)
        if arrival < floor_energy:
            continue
        terminal_need = outbound.energy(consumption) + reserve - arrival
        for effect in sorted(site.effects):
            if (effect in ("S", "CS")) != bool(remaining):
                continue
            if effect == "S":
                if terminal_need <= 0:
                    yield (((site_id, effect),), ())
                continue
            if effect not in ("C", "CS"):
                continue
            headroom = capacity - arrival
            if headroom <= 0:
                continue
            amount = max(terminal_need, min(Fraction(1), headroom) / 2)
            if 0 < amount <= headroom:
                yield (((site_id, effect),), (amount,))
    if bound < 2:
        return
    # A small deterministic beam explores physical progress for a feasible
    # multi-charge seed. This is only a proposal generator: independent replay
    # checks the exact service/charge clock and all physical constraints.
    schedule = query.get("schedule")
    overhead = exact_field("overhead_s")
    segments = tuple(tuple(Fraction(value) for value in row)
                     for row in query.get("charging_segments", ()))
    def charge_time(lo: Fraction, hi: Fraction) -> Fraction:
        return sum((max(Fraction(0), min(hi, b) - max(lo, a)) * slope
                    for a, b, slope, _ in segments), Fraction(0))
    frontier = [(table.origin_anchor, initial, exact_field("start_time_s"),
                 remaining, (), ())]
    for depth in range(1, min(bound, 8) + 1):
        expanded = []
        for anchor, energy, clock, pending, sequence, charges in frontier:
            for site_id in sorted(table.sites):
                if site_id in (event[0] for event in sequence):
                    continue
                site = table.site(site_id)
                if site.anchor_id == table.destination_anchor:
                    continue
                inbound = table.leg(anchor, site.anchor_id)
                if not inbound.reachable:
                    continue
                arrival = energy - inbound.energy(consumption)
                if arrival < floor_energy:
                    continue
                release = clock + inbound.time + overhead
                for effect in sorted(site.effects):
                    if effect in ("S", "CS") and not pending:
                        continue
                    amounts = (Fraction(0),) if effect == "S" else (
                        capacity - arrival, min(Fraction(1), capacity - arrival) / 2)
                    for amount in amounts:
                        if effect != "S" and amount <= 0:
                            continue
                        done = release + (charge_time(arrival, arrival + amount)
                                          if effect != "S" else 0)
                        if effect in ("S", "CS"):
                            a, b, duration = (Fraction(schedule[k]) for k in ("a", "b", "D"))
                            service_start = max(a, release)
                            if service_start > b:
                                continue
                            done = max(done, service_start + duration)
                        new_pending = 0 if effect in ("S", "CS") else pending
                        new_sequence = sequence + ((site_id, effect),)
                        new_charges = charges + ((amount,) if effect != "S" else ())
                        new_energy = arrival + amount
                        outbound = table.leg(site.anchor_id, table.destination_anchor)
                        if (not new_pending and outbound.reachable and
                                new_energy - outbound.energy(consumption) >= reserve):
                            yield (new_sequence, new_charges)
                        if depth < bound:
                            progress = (outbound.actual_length if outbound.reachable
                                        else Fraction(10**30))
                            expanded.append(((new_pending, progress, done, -new_energy,
                                              new_sequence, new_charges),
                                             (site.anchor_id, new_energy, done, new_pending,
                                              new_sequence, new_charges)))
        expanded.sort(key=lambda row: row[0])
        frontier = [state for _, state in expanded[:64]]
        if not frontier:
            break
    return
