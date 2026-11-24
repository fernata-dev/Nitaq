"""D0: no defense (baseline)."""
from nitaq_bench.defenses.base import Defense


class D0None(Defense):
    name = "D0"
    kind = "none"
    description = "No defense (baseline)."
