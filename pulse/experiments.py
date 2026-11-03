import hashlib
import json
import math
from pathlib import Path

import numpy as np

from pulse.models import Experiment


class ExperimentStore:
    def __init__(self, data_dir: Path):
        # Keep experiments inside the data folder, next to the event files.
        # (Going "up" from data_dir could write outside the folder the user chose.)
        self._path = data_dir / "experiments.json"

    def _load(self) -> dict:
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def _save(self, data: dict) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2, default=str))

    def create(self, experiment: Experiment) -> Experiment:
        data = self._load()
        if experiment.name in data:
            raise ValueError(f"Experiment '{experiment.name}' already exists")
        data[experiment.name] = experiment.model_dump()
        self._save(data)
        return experiment

    def list_all(self) -> list[Experiment]:
        return [Experiment(**v) for v in self._load().values()]

    def get(self, name: str) -> Experiment | None:
        data = self._load()
        return Experiment(**data[name]) if name in data else None

    def assign(self, experiment: Experiment, user_id: str) -> str:
        digest = int(hashlib.md5(f"{experiment.name}:{user_id}".encode()).hexdigest(), 16)
        return experiment.variants[digest % len(experiment.variants)]


# ---- Analysis: who is winning, and how sure are we? ----

# Below this many users in a variant, results are mostly luck
MIN_USERS_PER_VARIANT = 30

# How many times we "replay" the experiment to measure how much luck is involved
BOOTSTRAP_ROUNDS = 2000


def analyze_results(experiment: Experiment, rows: list[dict]) -> dict:
    """Turn per-variant counts into a difference, a 95% range and a summary.

    rows look like {"variant": "red", "users": 1000, "conversions": 200}.
    The first variant of the experiment is the "control" that the others are
    compared with.
    """
    variants = _in_experiment_order(experiment, rows)
    for v in variants:
        v["conversion_rate"] = round(v["conversions"] / v["users"], 4) if v["users"] else 0.0

    control = variants[0] if variants else None
    comparisons = []
    if control and control["variant"] == experiment.variants[0]:
        # Fixed starting point for the random replays, so reloading the
        # results page always shows the same numbers
        rng = np.random.default_rng(_seed(experiment.name))
        comparisons = [_compare(v, control, rng) for v in variants[1:]]

    winner = _pick_winner(variants, comparisons)
    p_value = None
    if len(variants) == 2:
        a, b = variants
        p_value = _z_test_p_value(a["users"], a["conversions"], b["users"], b["conversions"])

    return {
        "variants": variants,
        "comparisons": comparisons,
        "winner": winner,
        "significant": winner is not None,
        "p_value": round(p_value, 4) if p_value is not None else None,
        "summary": _summary(experiment, variants, comparisons, winner),
    }


def _in_experiment_order(experiment: Experiment, rows: list[dict]) -> list[dict]:
    """Put the variants in the order the experiment lists them (control first)."""
    by_name = {r["variant"]: r for r in rows}
    return [
        {"variant": name, "users": by_name[name]["users"], "conversions": by_name[name]["conversions"]}
        for name in experiment.variants
        if name in by_name
    ]


def _compare(variant: dict, control: dict, rng) -> dict:
    """Difference in conversion rate (variant - control) with a 95% bootstrap range.

    Bootstrap = pretend to rerun the experiment many times by re-drawing users at
    random from what we saw, and look at how much the difference jumps around.
    For yes/no outcomes, re-drawing n users is the same as one "binomial" draw,
    so numpy can do all 2,000 replays in a fraction of a second.
    """
    def replays(group):
        n = group["users"]
        rate = group["conversions"] / n if n else 0.0
        return rng.binomial(n, rate, BOOTSTRAP_ROUNDS) / n if n else np.zeros(BOOTSTRAP_ROUNDS)

    differences = replays(variant) - replays(control)
    low, high = np.percentile(differences, [2.5, 97.5])
    difference = _rate(variant) - _rate(control)
    return {
        "variant": variant["variant"],
        "vs": control["variant"],
        "difference": difference,
        "ci_low": float(low),
        "ci_high": float(high),
    }


def _pick_winner(variants: list[dict], comparisons: list[dict]) -> str | None:
    """A winner only when we're 95% sure: the whole range is above (or below) zero."""
    if not comparisons or _too_few(variants):
        return None
    better = [c for c in comparisons if c["ci_low"] > 0]
    if better:
        return max(better, key=lambda c: c["difference"])["variant"]
    if all(c["ci_high"] < 0 for c in comparisons):
        return variants[0]["variant"]  # control beats every other variant
    return None


def _too_few(variants: list[dict]) -> bool:
    return any(v["users"] < MIN_USERS_PER_VARIANT for v in variants)


def _summary(experiment, variants, comparisons, winner) -> str:
    """One plain-English sentence about the result."""
    if not variants:
        return "No users in this experiment yet."
    if not comparisons:
        return f"Only '{variants[0]['variant']}' has users so far. Wait until every variant has users."

    smallest = min(v["users"] for v in variants)
    if smallest < MIN_USERS_PER_VARIANT:
        return (f"Too few users so far (smallest group: {smallest}). "
                f"Wait until each variant has at least {MIN_USERS_PER_VARIANT} users.")

    rates = {v["variant"]: _rate(v) for v in variants}
    if winner and winner != variants[0]["variant"]:
        c = next(c for c in comparisons if c["variant"] == winner)
        return (f"{winner} converts better than {c['vs']}: "
                f"{_pct(rates[winner])} vs {_pct(rates[c['vs']])} ({_points(c['difference'])}). "
                f"We're 95% sure the real difference is between "
                f"{_points(c['ci_low'])} and {_points(c['ci_high'])}.")
    if winner:
        c = comparisons[0]
        others = ", ".join(x["variant"] for x in comparisons)
        return (f"{winner} converts better than {others}: "
                f"{_pct(rates[winner])} vs {_pct(rates[c['variant']])} ({_points(-c['difference'])}). "
                f"We're 95% sure the real difference is between "
                f"{_points(-c['ci_high'])} and {_points(-c['ci_low'])}.")

    c = max(comparisons, key=lambda x: abs(x["difference"]))
    return (f"No clear winner yet. {c['variant']} vs {c['vs']}: {_points(c['difference'])}, "
            f"but the real difference could be anywhere from {_points(c['ci_low'])} "
            f"to {_points(c['ci_high'])}. Keep the test running.")


def _rate(group: dict) -> float:
    return group["conversions"] / group["users"] if group["users"] else 0.0


def _pct(rate: float) -> str:
    return f"{rate * 100:.1f}%"


def _points(diff: float) -> str:
    """0.06 -> '+6.0 points' (percentage points)."""
    return f"{diff * 100:+.1f} points"


def _seed(name: str) -> int:
    return int(hashlib.md5(name.encode()).hexdigest()[:8], 16)


def _z_test_p_value(n1: int, c1: int, n2: int, c2: int) -> float | None:
    """Classic two-proportion z-test p-value (kept for people who want it)."""
    if n1 < 1 or n2 < 1 or (c1 + c2) == 0:
        return None
    p_pool = (c1 + c2) / (n1 + n2)
    if p_pool in (0.0, 1.0):
        return None
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    if se == 0:
        return None
    z = abs(c1 / n1 - c2 / n2) / se
    return float(math.erfc(z / math.sqrt(2)))
