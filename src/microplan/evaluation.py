"""Fixed positive linear evaluation family, separate from region/cover construction."""
import numpy as np


def utility_family(config, seed):
    archetypes = config['archetypes']
    names = list(archetypes)
    weights = np.array(list(archetypes.values()), float)
    rng = np.random.default_rng(seed)
    samples = rng.dirichlet(np.full(weights.shape[1], config['dirichlet_alpha']),
                            size=config['simplex_samples'])
    names += [f'simplex_{i:02d}' for i in range(len(samples))]
    weights = np.vstack([weights, samples])
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError('Evaluation weights must be strictly positive')
    weights /= weights.sum(axis=1)[:, None]
    return names, weights


def normalize_objectives(z, scales):
    scales = np.asarray(scales, float)
    if not np.isfinite(scales).all() or (scales <= 0).any() or np.asarray(z).shape[-1] != len(scales):
        raise ValueError('Invalid fixed normalization scales')
    return np.asarray(z) / scales


def regret(flat_costs, selected_costs, eta, k=1):
    if eta <= 0 or k < 1:
        raise ValueError('Invalid regret parameters')
    if not len(flat_costs):
        return None, None
    if not len(selected_costs):
        return np.inf, np.inf
    # TopK ranked with the same known scalar objective always contains Top1.
    top = np.sort(selected_costs)[:k]
    best = float(np.min(flat_costs))
    absolute = max(0.0, float(top.min()) - best)
    return absolute, absolute / (abs(best) + eta)
