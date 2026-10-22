"""Generic non-dominated (Pareto) filtering and min-max weighted ranking for small candidate sets.

Migrated from the explicit parts of the historical ``pea.optimization`` module
(``pareto_front`` and ``rank_candidates``) and generalised to arbitrary objectives
with declared optimisation senses. The candidate generation of that module, which
relied on fitted loss factors and reference component tables, was not migrated.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from typing import Literal, TypeVar

__all__ = ["Sense", "pareto_front", "weighted_rank"]

T = TypeVar("T")
Sense = Literal["min", "max"]


def _check(objectives: Sequence[Callable[[T], float]], senses: Sequence[Sense]) -> None:
    if not objectives:
        raise ValueError("at least one objective is required")
    if len(objectives) != len(senses):
        raise ValueError("objectives and senses must have the same length")
    for sense in senses:
        if sense not in ("min", "max"):
            raise ValueError(f"sense must be 'min' or 'max', got {sense!r}")


def _values(
    items: Sequence[T], objectives: Sequence[Callable[[T], float]], senses: Sequence[Sense]
) -> list[list[float]]:
    """Objective values oriented so that larger is always better."""
    table: list[list[float]] = []
    for item in items:
        row = []
        for objective, sense in zip(objectives, senses, strict=True):
            value = float(objective(item))
            if not math.isfinite(value):
                raise ValueError("objective values must be finite")
            row.append(value if sense == "max" else -value)
        table.append(row)
    return table


def pareto_front(items: Sequence[T], objectives: Sequence[Callable[[T], float]], senses: Sequence[Sense]) -> list[T]:
    """Return the non-dominated items in their original order.

    An item is dominated when another item is at least as good in every objective and
    strictly better in at least one. Exact duplicates in objective space are all kept.
    """
    _check(objectives, senses)
    table = _values(items, objectives, senses)
    front: list[T] = []
    for i, row in enumerate(table):
        dominated = False
        for j, other in enumerate(table):
            if i == j:
                continue
            if all(o >= r for o, r in zip(other, row, strict=True)) and any(
                o > r for o, r in zip(other, row, strict=True)
            ):
                dominated = True
                break
        if not dominated:
            front.append(items[i])
    return front


def weighted_rank(
    items: Sequence[T],
    objectives: Sequence[Callable[[T], float]],
    senses: Sequence[Sense],
    weights: Sequence[float],
) -> list[tuple[T, float]]:
    """Rank items by a weighted sum of min-max normalised objectives (1 = best in the set).

    Returns ``[(item, score), ...]`` sorted by descending score (stable for ties). When an
    objective is constant over the set every item gets 1 for it. Weights must be non-negative
    and not all zero; they are normalised to sum to one.
    """
    _check(objectives, senses)
    if len(weights) != len(objectives):
        raise ValueError("weights and objectives must have the same length")
    if any(w < 0 or not math.isfinite(w) for w in weights) or sum(weights) <= 0:
        raise ValueError("weights must be finite, non-negative and not all zero")
    if not items:
        return []
    table = _values(items, objectives, senses)
    total_weight = float(sum(weights))
    scored: list[tuple[T, float]] = []
    columns = list(zip(*table, strict=True))
    for item, row in zip(items, table, strict=True):
        score = 0.0
        for value, column, weight in zip(row, columns, weights, strict=True):
            low, high = min(column), max(column)
            normalised = 1.0 if math.isclose(low, high) else (value - low) / (high - low)
            score += weight / total_weight * normalised
        scored.append((item, score))
    scored.sort(key=lambda pair: -pair[1])
    return scored
