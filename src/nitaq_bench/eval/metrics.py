"""Statistics used by every report: Wilson interval and exact McNemar test."""
from __future__ import annotations

import math

Z95 = 1.959963984540054


def wilson(k: int, n: int, z: float = Z95) -> tuple[float | None, float | None]:
    """Wilson score interval for a binomial proportion k/n (no continuity correction)."""
    if n <= 0:
        return None, None
    if not 0 <= k <= n:
        raise ValueError("need 0 <= k <= n")
    p = k / n
    z2 = z * z
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denom
    lo = 0.0 if k == 0 else max(0.0, centre - half)
    hi = 1.0 if k == n else min(1.0, centre + half)
    return lo, hi


def cell(k: int, n: int) -> dict:
    lo, hi = wilson(k, n)
    return {
        "k": k, "n": n,
        "rate": (k / n) if n else None,
        "ci_lo": lo, "ci_hi": hi,
    }


def mcnemar_exact(b: int, c: int) -> float | None:
    """Two-sided exact McNemar p-value from the discordant counts b and c.

    b = cases where A succeeded and B did not; c = the reverse.  Under H0 the
    discordant pairs are Binomial(b+c, 0.5).  Returns None when b+c == 0
    (no discordant pair: the test is undefined, not "p = 1").
    """
    n = b + c
    if n == 0:
        return None
    m = min(b, c)
    tail = sum(math.comb(n, i) for i in range(m + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def intervals_overlap(a: dict, b: dict) -> bool | None:
    """Do two Wilson intervals overlap?  None if either cell is empty."""
    if a.get("ci_lo") is None or b.get("ci_lo") is None:
        return None
    return not (a["ci_lo"] > b["ci_hi"] or b["ci_lo"] > a["ci_hi"])


MIN_CLUSTERS = 5


def cluster_bootstrap(clusters: list[tuple[int, int]], seed: int, b: int = 1000,
                      alpha: float = 0.05) -> tuple[float | None, float | None]:
    """Percentile cluster-bootstrap CI for a pooled rate.

    clusters = [(k_i, n_i)] per authored base text.  Variants generated from the
    same base text are correlated; resampling whole base texts gives an interval
    that does not pretend they are independent.  Returns (None, None) when there
    are fewer than MIN_CLUSTERS base texts (an interval would be meaningless).
    """
    m = len(clusters)
    if m < MIN_CLUSTERS:
        return None, None
    # Pure-Python RNG on purpose: the result must not depend on which optional
    # packages are installed (an earlier numpy fast path gave different digests
    # on machines without numpy; found by CI, see CHANGELOG).
    import random
    rng = random.Random(seed)
    ks = [c[0] for c in clusters]
    ns = [c[1] for c in clusters]
    rates = []
    for _ in range(b):
        k = n = 0
        for _ in range(m):
            i = rng.randrange(m)
            k += ks[i]
            n += ns[i]
        rates.append(k / n)
    rates.sort()
    return rates[int(alpha / 2 * b)], rates[min(b - 1, int((1 - alpha / 2) * b))]
