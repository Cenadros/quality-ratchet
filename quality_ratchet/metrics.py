# name -> (better, default tolerance)
METRIC_SPECS: dict[str, tuple[str, float]] = {
    "ccn_over_15": ("lower", 0.0),
    "max_ccn": ("lower", 0.0),
    "long_functions": ("lower", 0.0),
    "duplication_pct": ("lower", 0.1),
    "lint_warnings": ("lower", 0.0),
    "tests_per_kloc": ("higher", 0.2),
}

GROUPS: dict[str, list[str]] = {
    "complexity": ["ccn_over_15", "max_ccn", "long_functions"],
    "duplication": ["duplication_pct"],
    "lint": ["lint_warnings"],
    "tests": ["tests_per_kloc"],
}
