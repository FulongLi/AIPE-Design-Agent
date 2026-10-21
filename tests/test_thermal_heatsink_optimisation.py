"""Tests for the Stage A heat-sink screening (needs numpy/scipy and the sibling HeatSinkOptimisation checkout)."""

import json

import pytest

from pea.thermal import _sibling
from pea.thermal import dab_case as dc
from pea.thermal import heatsink_optimisation as ho

pytest.importorskip("numpy")
pytest.importorskip("scipy")
try:
    _sibling.load_heatsink_model()
except _sibling.HeatSinkModelNotFound as exc:  # pragma: no cover - environment dependent
    pytest.skip(f"sibling HeatSinkOptimisation checkout not available: {exc}", allow_module_level=True)

BOUNDS = {"length": (0.10, 0.30), "width": (0.10, 0.30), "fin_height": (0.03, 0.12), "fin_thickness": (0.0015, 0.005),
          "fin_gap": (0.004, 0.015), "base_thickness": (0.004, 0.012)}


def _task(**kwargs):
    base = dict(devices=dc.build_devices("secondary", with_loss_models=False), t_ambient_C=40.0, cooling="natural", tj_limit_C=125.0,
                bounds=BOUNDS, n_weights=3, n_epsilon=2, maxiter=6, popsize=6, seed=11, materials=("Al-6063-T5", "Cu-C11000"))
    base.update(kwargs)
    return ho.StageATask(**base)


def test_stage_a_natural_returns_flagged_non_dominated_candidates():
    res = ho.run_stage_a(_task())
    assert res["stage"] == "A" and res["n_candidates"] >= 2
    rows = res["pareto_set"]
    masses = [r["objectives"]["mass"] for r in rows]
    assert masses == sorted(masses)
    rths = [r["objectives"]["r_th"] for r in rows]
    assert rths == sorted(rths, reverse=True)  # non-dominated two-objective set
    assert set(r["material"] for r in rows) <= {"Al-6063-T5", "Cu-C11000"}
    flagged = [r for r in rows if r["fem_verification_recommended"]]
    assert 1 <= len(flagged) <= 3 and sorted(res["flagged_candidates"]) == sorted(r["candidate_id"] for r in flagged)
    assert all(r["flag_reason"] for r in flagged)
    for r in rows:
        jc = r["junction_check"]
        assert jc["tj_max_C"] > 40.0 and jc["limit_C"] == 125.0 and jc["feasible"] == (jc["tj_max_C"] <= 125.0)
    assert "FEM" in res["next_stage"] and "not performed" in res["next_stage"]
    assert set(res["fronts_by_material"]) == {"Al-6063-T5", "Cu-C11000"}
    json.dumps(res)


def test_stage_a_is_reproducible_for_a_seed():
    a = ho.run_stage_a(_task(materials=("Al-6063-T5",)))
    b = ho.run_stage_a(_task(materials=("Al-6063-T5",)))
    assert [r["objectives"] for r in a["pareto_set"]] == [r["objectives"] for r in b["pareto_set"]]


def test_stage_a_forced_with_flow_variable_and_fan_power_objective():
    task = _task(cooling="forced", flow_bounds=(0.003, 0.03), objectives=("r_th", "mass", "fan_power_W"), n_weights=3, n_epsilon=0,
                 bounds={"length": (0.06, 0.20), "width": (0.06, 0.20), "fin_height": (0.02, 0.08), "fin_thickness": (0.001, 0.004),
                         "fin_gap": (0.002, 0.008), "base_thickness": (0.003, 0.010)}, materials=("Al-6063-T5",))
    res = ho.run_stage_a(task)
    assert res["n_candidates"] >= 1
    for r in res["pareto_set"]:
        assert 0.003 <= r["variables"]["volumetric_flow"] <= 0.03
        assert r["objectives"]["fan_power_W"] > 0 and r["performance_summary"]["regime"].startswith("forced")


def test_task_validation_and_dict_round_trip():
    with pytest.raises(ValueError):
        _task(cooling="forced")  # no flow information
    with pytest.raises(ValueError):
        ho.StageATask(devices=[])
    task = _task()
    d = task.to_dict()
    again = ho.StageATask.from_dict({**d, "devices": [dict(x, loss_model=None) for x in d["devices"]]})
    assert again.bounds == task.bounds and again.materials == task.materials and len(again.devices) == 4
