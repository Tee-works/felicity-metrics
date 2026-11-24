"""A/B readout helpers. Standard library only.

two_proportion_test: pooled z-test for the difference in two rates, with an
unpooled 95% confidence interval for the difference.
srm_check: sample ratio mismatch, chi-square with 1 degree of freedom against 50/50.
"""
import math
from dataclasses import dataclass


def _norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2))


@dataclass
class PropTest:
    n_a: int
    x_a: int
    n_b: int
    x_b: int
    rate_a: float
    rate_b: float
    diff: float
    ci_low: float
    ci_high: float
    z: float
    p_value: float


def two_proportion_test(x_a: int, n_a: int, x_b: int, n_b: int, z_crit: float = 1.959964) -> PropTest:
    pa, pb = x_a / n_a, x_b / n_b
    pooled = (x_a + x_b) / (n_a + n_b)
    se_pooled = math.sqrt(pooled * (1 - pooled) * (1 / n_a + 1 / n_b))
    z = (pb - pa) / se_pooled if se_pooled else 0.0
    p = 2 * _norm_sf(abs(z))
    se = math.sqrt(pa * (1 - pa) / n_a + pb * (1 - pb) / n_b)
    d = pb - pa
    return PropTest(n_a, x_a, n_b, x_b, pa, pb, d, d - z_crit * se, d + z_crit * se, z, p)


def srm_check(n_a: int, n_b: int) -> float:
    """p-value that a 50/50 split produced these arm sizes."""
    exp = (n_a + n_b) / 2
    chi2 = ((n_a - exp) ** 2 + (n_b - exp) ** 2) / exp
    return math.erfc(math.sqrt(chi2 / 2))  # chi-square(1) survival function


def required_n_per_arm(p_base: float, mde: float, z_alpha: float = 1.959964, z_beta: float = 0.841621) -> int:
    """Sample size per arm to detect an absolute lift of `mde` at 5% two-sided, 80% power."""
    p2 = p_base + mde
    pbar = (p_base + p2) / 2
    num = (z_alpha * math.sqrt(2 * pbar * (1 - pbar)) + z_beta * math.sqrt(p_base * (1 - p_base) + p2 * (1 - p2))) ** 2
    return math.ceil(num / mde ** 2)
