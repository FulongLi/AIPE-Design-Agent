"""Generic Pareto front and weighted ranking (aipe_electrical.optimisation.pareto)."""

import pytest

from aipe_electrical.optimisation import pareto

ITEMS = [
    {"id": "a", "eff": 96.0, "vol": 10.0, "cost": 5.0},  # dominates d
    {"id": "b", "eff": 95.0, "vol": 8.0, "cost": 6.0},
    {"id": "c", "eff": 97.0, "vol": 12.0, "cost": 4.0},
    {"id": "d", "eff": 94.0, "vol": 12.0, "cost": 6.0},  # dominated by a
    {"id": "e", "eff": 96.0, "vol": 10.0, "cost": 5.0},  # duplicate of a
]
OBJ = [lambda x: x["eff"], lambda x: x["vol"], lambda x: x["cost"]]
SENSES = ["max", "min", "min"]


def test_pareto_front_removes_dominated_and_keeps_duplicates():
    front = pareto.pareto_front(ITEMS, OBJ, SENSES)
    assert [x["id"] for x in front] == ["a", "b", "c", "e"]


def test_single_objective_front_is_the_best_value():
    assert [x["id"] for x in pareto.pareto_front(ITEMS, [lambda x: x["cost"]], ["min"])] == ["c"]


def test_weighted_rank_prefers_dominant_item_and_normalises_weights():
    ranked = pareto.weighted_rank(ITEMS[:4], OBJ, SENSES, [0.45, 0.35, 0.20])
    ids = [x["id"] for x, _ in ranked]
    assert ids[-1] == "d"
    assert all(0.0 <= s <= 1.0 for _, s in ranked)
    same = pareto.weighted_rank(ITEMS[:4], OBJ, SENSES, [45, 35, 20])
    assert [round(s, 12) for _, s in same] == [round(s, 12) for _, s in ranked]


def test_constant_objective_scores_one_and_empty_input():
    ranked = pareto.weighted_rank([{"v": 1.0}, {"v": 1.0}], [lambda x: x["v"]], ["min"], [1.0])
    assert [s for _, s in ranked] == [1.0, 1.0]
    assert pareto.weighted_rank([], OBJ, SENSES, [1, 1, 1]) == []


@pytest.mark.parametrize(
    "objectives,senses,weights",
    [
        ([], [], []),
        (OBJ, ["max", "min"], [1, 1, 1]),
        (OBJ, ["max", "min", "up"], [1, 1, 1]),
        (OBJ, SENSES, [0, 0, 0]),
        (OBJ, SENSES, [1, 1]),
    ],
)
def test_invalid_specifications(objectives, senses, weights):
    with pytest.raises(ValueError):
        pareto.weighted_rank(ITEMS, objectives, senses, weights)


def test_non_finite_objective_rejected():
    with pytest.raises(ValueError):
        pareto.pareto_front([{"v": float("nan")}], [lambda x: x["v"]], ["min"])
