"""Exact pure-C min-plus transform and rational, restricted fiber lifting."""
from fractions import Fraction

from .interval import Interval
from .pwa import AffineCutPiece, _affine_half_interval, _actual_time
from .scalar import exact


def charge_pair(source, incoming, outgoing, overhead, site):
    """Return one affine-segment pair's cuts; never build a projection.

    For D_y = support intersect {x < y}, minimize (alpha-m_i)*x.
    Only the negative-delta branch changes formula at support.hi.
    """
    from .pwa_partition import TransitionWitness, _cells, _sample

    il, ih, im, ic = incoming
    ol, oh, om, oc = outgoing
    support = source.domain.intersect(Interval(il, ih))
    if support is None:
        return ()
    output = _affine_half_interval(Interval(ol, oh), Fraction(1), 0,
                                   support.lo, upper=False, inclusive=False)
    if output is None:
        return ()
    delta = source.slope - im
    base = overhead + oc + source.intercept - ic
    result = []
    for cell in _cells(output, (support.hi,) if delta < 0 else ()):
        y = _sample(cell)
        if delta > 0:
            slope, intercept = om, base + delta * support.lo
            attained = source.attained and support.left_closed
        elif delta < 0:
            if y <= support.hi:
                slope, intercept, attained = om + delta, base, False
            else:
                slope, intercept = om, base + delta * support.hi
                attained = source.attained and support.right_closed
        else:
            slope, intercept, attained = om, base, source.attained

        def lift(energy, budget, cell=cell):
            energy, budget = exact(energy), exact(budget)
            if not cell.contains(energy):
                raise ValueError("Output outside represented C cell")
            fiber = _affine_half_interval(support, Fraction(1), 0, energy,
                                          upper=True, inclusive=False)
            if fiber is not None:
                fiber = _affine_half_interval(fiber, delta, 0,
                    budget - (om * energy + base), upper=True,
                    inclusive=source.attained)
            if fiber is None:
                raise ValueError("Empty analytic C witness fiber")
            x = (fiber.lo + fiber.hi) / 2
            input_budget = budget - overhead - (om * energy + oc) + (im * x + ic)
            predecessor = (source.witness_lifter(x, input_budget)
                           if source.witness_lifter else None)
            # Callbacks take upper budgets; their actual realization may be earlier.
            actual = _actual_time(predecessor, input_budget)
            lower = source.cut_time_at(x)
            if actual > input_budget or actual < lower or (actual == lower and not source.attained):
                raise ValueError("Source realization violates restricted C cut/budget")
            output_time = actual + overhead + (om * energy + oc) - (im * x + ic)
            if output_time > budget or not x < energy:
                raise AssertionError("Analytic C realization violates transition")
            return TransitionWitness("C", site, x, actual, energy, output_time,
                predecessor, ((incoming, outgoing), overhead, 0, 0, 0))

        result.append(AffineCutPiece(cell, slope, intercept, attained, source.rho,
            source.prefix + ((site, "C"),),
            (site, source.state_key[1], source.state_key[2] + 1), lift))
    return tuple(result)
