import math

import pytest

from nitaq_bench.eval.metrics import cell, intervals_overlap, mcnemar_exact, wilson


@pytest.mark.parametrize("k,n,lo,hi", [
    (81, 263, 0.2553, 0.3662),    # Newcombe (1998), method 3 (Wilson, no continuity correction)
    (15, 148, 0.0624, 0.1605),    # Newcombe (1998)
    (5, 10, 0.2366, 0.7634),
    (0, 10, 0.0, 0.2775),
    (10, 10, 0.7225, 1.0),
    (1, 1, 0.2065, 1.0),
])
def test_wilson_known_values(k, n, lo, hi):
    a, b = wilson(k, n)
    assert a == pytest.approx(lo, abs=5e-4)
    assert b == pytest.approx(hi, abs=5e-4)


def test_wilson_edges():
    assert wilson(0, 0) == (None, None)
    with pytest.raises(ValueError):
        wilson(3, 2)
    lo, hi = wilson(0, 5)
    assert lo == 0.0 and 0 < hi < 1


def test_wilson_is_symmetric():
    lo1, hi1 = wilson(3, 20)
    lo2, hi2 = wilson(17, 20)
    assert lo1 == pytest.approx(1 - hi2) and hi1 == pytest.approx(1 - lo2)


@pytest.mark.parametrize("b,c,p", [
    (1, 9, 22 / 1024),
    (0, 5, 2 / 32),
    (3, 3, 1.0),
    (0, 1, 1.0),
    (2, 10, 2 * (1 + 12 + 66) / 4096),
])
def test_mcnemar_exact_known_values(b, c, p):
    assert mcnemar_exact(b, c) == pytest.approx(p)
    assert mcnemar_exact(c, b) == pytest.approx(p)


def test_mcnemar_undefined_without_discordant_pairs():
    assert mcnemar_exact(0, 0) is None


def test_cell_and_overlap():
    a, b = cell(0, 40), cell(40, 40)
    assert a["rate"] == 0 and b["rate"] == 1
    assert intervals_overlap(a, b) is False
    assert intervals_overlap(cell(5, 10), cell(6, 10)) is True
    assert intervals_overlap(cell(0, 0), b) is None
    assert math.isclose(cell(1, 4)["rate"], 0.25)


def test_cluster_bootstrap_needs_enough_clusters_and_is_deterministic():
    from nitaq_bench.eval.metrics import MIN_CLUSTERS, cluster_bootstrap
    assert cluster_bootstrap([(1, 2)] * (MIN_CLUSTERS - 1), seed=1) == (None, None)
    cl = [(0, 10), (10, 10), (5, 10), (2, 10), (8, 10), (1, 10)]
    a = cluster_bootstrap(cl, seed=3)
    assert a == cluster_bootstrap(cl, seed=3)
    lo, hi = a
    assert 0 <= lo < 25 / 60 < hi <= 1


def test_cluster_interval_is_wider_than_wilson_for_correlated_clusters():
    from nitaq_bench.eval.metrics import cluster_bootstrap
    cl = [(10, 10)] * 3 + [(0, 10)] * 3        # all-or-nothing per base text
    lo, hi = cluster_bootstrap(cl, seed=0)
    wlo, whi = wilson(30, 60)
    assert (hi - lo) > (whi - wlo)


def test_paired_table_reports_text_level_mcnemar():
    from nitaq_bench.eval.runner import paired_table
    rows = []
    for b in range(6):
        for v in range(10):
            cid = f"t{b}__v{v}"
            rows.append({"case_id": cid, "base_id": f"t{b}", "defense": "A", "success": True})
            rows.append({"case_id": cid, "base_id": f"t{b}", "defense": "B", "success": b >= 3})
    p = paired_table(rows, "success", ["A", "B"])[0]
    assert (p["n_pairs"], p["only_a"], p["only_b"]) == (60, 30, 0)
    assert (p["text_pairs"], p["text_only_a"], p["text_only_b"]) == (6, 3, 0)
    assert p["text_mcnemar_exact_p"] == 0.25 and p["mcnemar_exact_p"] < 1e-8


def test_cluster_bootstrap_does_not_depend_on_optional_packages(monkeypatch):
    """Regression (found by CI): results must be identical with and without numpy."""
    import builtins
    from nitaq_bench.eval.metrics import cluster_bootstrap
    cl = [(k, 37) for k in (0, 3, 9, 14, 22, 30, 37, 5, 11, 19)]
    a = cluster_bootstrap(cl, seed=123, b=500)
    real = builtins.__import__
    def blocked(name, *args, **kw):
        if name.split(".")[0] == "numpy":
            raise ImportError("blocked")
        return real(name, *args, **kw)
    monkeypatch.setattr(builtins, "__import__", blocked)
    assert cluster_bootstrap(cl, seed=123, b=500) == a
    assert a[0] < a[1]
