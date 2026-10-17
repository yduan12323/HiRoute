"""Exact dominance and deterministic componentwise additive covers."""
import numpy as np


def pareto_indices(z):
    z = np.asarray(z, dtype=float)
    if z.ndim != 2 or not np.isfinite(z).all():
        raise ValueError('Pareto vectors must be a finite matrix')
    if len(z) == 0:
        return np.empty(0, dtype=np.int64)
    # Five structural dimensions have three discrete columns. Within each
    # category exact 2D skyline sorting avoids quadratic candidate comparisons.
    if z.shape[1] == 5:
        _, group = np.unique(z[:, 2:], axis=0, return_inverse=True)
        survivors = []
        for g in np.unique(group):
            ids = np.flatnonzero(group == g)
            order = ids[np.lexsort((ids, z[ids, 1], z[ids, 0]))]
            best_d, best_t = np.inf, np.inf
            for i in order:
                t, d = z[i, :2]
                if d < best_d or (d == best_d and t == best_t):
                    survivors.append(i)
                    best_d, best_t = d, t
        ids = np.array(survivors, dtype=np.int64)
    else:
        ids = np.arange(len(z))
    # Cross-category checks preserve every exact tie (strict inequality required).
    kept = []
    for i in ids:
        other = z[ids]
        if not np.any(np.all(other <= z[i], axis=1) & np.any(other < z[i], axis=1)):
            kept.append(i)
    return np.array(sorted(kept), dtype=np.int64)


def epsilon_cover(z, epsilon):
    """Return retained row indices and a covering representative for every row.

    Lexicographic cost/stop/stable row ordering is independent of utility weights.
    Every removed point has an explicit feasible, componentwise covering witness.
    """
    z, eps = np.asarray(z, float), np.asarray(epsilon, float)
    if z.ndim != 2 or eps.shape != (z.shape[1],) or not np.isfinite(z).all() or not np.isfinite(eps).all() or (eps < 0).any():
        raise ValueError('Invalid additive cover')
    order = np.lexsort((np.arange(len(z)), *[z[:, j] for j in reversed(range(z.shape[1]))]))
    retained, witnesses = [], np.full(len(z), -1, dtype=np.int64)
    for i in order:
        covering = [j for j in retained if np.all(z[j] <= z[i] + eps)]
        if covering:
            witnesses[i] = covering[0]
        else:
            retained.append(int(i)); witnesses[i] = i
    return np.array(retained, dtype=np.int64), witnesses


def random_representatives(count, retained_count, seed):
    if not 0 <= retained_count <= count:
        raise ValueError('Invalid representative count')
    return np.sort(np.random.default_rng(seed).choice(count, retained_count, replace=False))


def load_grouped_pareto(config, cache):
    import ctypes
    import subprocess
    from pathlib import Path
    source = Path(__file__).with_suffix('.cpp').with_name('pareto.cpp')
    binary = Path(cache)/'pareto.so'
    subprocess.run([config['compiler'], *config['compiler_flags'], '-shared', '-fPIC', str(source), '-o', str(binary)],check=True)
    library = ctypes.CDLL(str(binary)); function=library.grouped_pareto
    function.argtypes=[ctypes.c_int64,np.ctypeslib.ndpointer(dtype=np.float64,flags='C_CONTIGUOUS'),
        np.ctypeslib.ndpointer(dtype=np.int64,flags='C_CONTIGUOUS'),
        np.ctypeslib.ndpointer(dtype=np.uint8,flags='C_CONTIGUOUS')]
    function.restype=None
    def grouped(z, groups):
        if np.asarray(z).shape != (len(groups),5) or not np.isfinite(z).all():
            raise ValueError('Grouped structural Pareto needs finite five-dimensional vectors')
        keep=np.empty(len(groups),dtype=np.uint8)
        function(len(groups),np.ascontiguousarray(z,dtype=np.float64),np.ascontiguousarray(groups,dtype=np.int64),keep)
        return np.flatnonzero(keep)
    grouped.library=library
    return grouped


def grouped_epsilon_cover(z, groups, epsilon):
    """Apply the explicit additive cover independently within each region."""
    groups=np.asarray(groups)
    if len(z)!=len(groups):raise ValueError('Cover group/vector mismatch')
    order=np.argsort(groups,kind='stable')
    boundaries=np.r_[0,np.flatnonzero(np.diff(groups[order]))+1,len(order)]
    kept=[];witness=np.empty(len(z),dtype=np.int64)
    for lo,hi in zip(boundaries[:-1],boundaries[1:]):
        ids=order[lo:hi]
        selected,local=epsilon_cover(z[ids],epsilon)
        kept.extend(ids[selected]);witness[ids]=ids[local]
    return np.array(sorted(kept),dtype=np.int64),witness
