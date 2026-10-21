"""Tests for pea.thermal.cooling and the sibling HeatSinkOptimisation locator (needs numpy/scipy and the sibling checkout)."""

import json
from pathlib import Path

import pytest

from pea.thermal import _sibling
from pea.thermal import cooling as cl
from pea.thermal import dab_case as dc

pytest.importorskip("numpy")
pytest.importorskip("scipy")

try:
    HM = _sibling.load_heatsink_model()
except _sibling.HeatSinkModelNotFound as exc:  # pragma: no cover - environment dependent
    pytest.skip(f"sibling HeatSinkOptimisation checkout not available: {exc}", allow_module_level=True)


def test_sibling_locator_reports_clear_errors(monkeypatch, tmp_path):
    monkeypatch.setattr(_sibling, "candidate_directories", lambda: [tmp_path / "nowhere"])
    with pytest.raises(_sibling.HeatSinkModelNotFound, match="HEATSINK_OPT_DIR"):
        _sibling.load_heatsink_model(force_reload=True)
    outdated = tmp_path / "old"
    outdated.mkdir()
    (outdated / "heatsink_model.py").write_text("K_COPPER = 380\n", encoding="utf-8")
    monkeypatch.setattr(_sibling, "candidate_directories", lambda: [outdated])
    with pytest.raises(_sibling.HeatSinkModelNotFound, match="not the corrected"):
        _sibling.load_heatsink_model(force_reload=True)
    monkeypatch.setenv(_sibling.ENV_VAR, str(tmp_path / "env-dir"))
    monkeypatch.undo()
    assert _sibling.load_heatsink_model() is HM  # cache untouched by the failed reloads
    monkeypatch.setenv(_sibling.ENV_VAR, str(tmp_path / "env-dir"))
    assert _sibling.candidate_directories()[0] == tmp_path / "env-dir"


def test_coolant_properties_table_and_prandtl():
    w = cl.coolant_properties("water", 46.85)
    assert w.density == pytest.approx(989.1) and w.conductivity == pytest.approx(0.640)
    assert w.prandtl == pytest.approx(577e-6 * 4180.0 / 0.640, rel=1e-6)
    mid = cl.coolant_properties("water", 36.85)
    assert 989.1 < mid.density < 997.0
    clamped = cl.coolant_properties("water", 90.0)
    assert "clamped" in clamped.note
    assert cl.coolant_properties("eg50", 40.0).prandtl > w.prandtl
    with pytest.raises(KeyError):
        cl.coolant_properties("oil", 40.0)


def test_cold_plate_option_validation():
    with pytest.raises(ValueError):
        cl.LiquidColdPlateOption(0.1, 0.05, 0.004, 16, 0.003, 0.005, 0.0025, 45.0, 3e-5)  # channels do not fit
    with pytest.raises(ValueError):
        cl.ForcedAirOption(cl.PlateFinGeometry(0.1, 0.1, 0.04, 0.0015, 0.003, 0.006))  # no flow


def _devices(power=23.9, with_models=True):
    return dc.build_devices("secondary", with_loss_models=with_models)


def test_compare_cooling_options_ranks_and_reports_review_items():
    comp = cl.compare_cooling_options(_devices(), dc.cooling_options(), 40.0, electrothermal=True)
    assert comp["ranking_by_tj"][0] != comp["ranking_by_tj"][-1]
    kinds = {r["kind"]: r for r in comp["results"]}
    assert set(kinds) == {"natural", "forced", "liquid"}
    assert kinds["natural"]["tj_max_C"] > kinds["forced"]["tj_max_C"]
    assert kinds["natural"]["auxiliary_power_W"] == 0.0 and kinds["forced"]["auxiliary_power_W"] > 0 and kinds["liquid"]["auxiliary_power_W"] > 0
    assert kinds["natural"]["mass_kg"] > kinds["forced"]["mass_kg"] > 0
    assert kinds["liquid"]["fluid_inlet_C"] == 45.0 and kinds["natural"]["fluid_inlet_C"] == 40.0
    topics = {kind: {item["topic"] for item in r["review_items"]} for kind, r in kinds.items()}
    assert "acoustic" in topics["forced"] and "leakage" in topics["liquid"] and "condensation" in topics["liquid"]
    assert "orientation" in topics["natural"] and all("isolation" in t for t in topics.values())
    for r in comp["results"]:
        assert r["electrothermal"]["converged"] and r["validity"]
        assert all(d["t_j_C"] > 40.0 for d in r["devices"])
    assert "not CFD" in comp["disclaimer"]
    json.dumps(comp)


def test_electrothermal_closure_lowers_losses_when_tj_below_evaluation_point():
    devices = _devices()
    forced = cl.evaluate_option(dc.cooling_options()[1], devices, 40.0, electrothermal=True)
    fixed = cl.evaluate_option(dc.cooling_options()[1], devices, 40.0, electrothermal=False)
    assert forced.tj_max_C < dc.TJ_EVAL_C
    assert forced.total_power_W < fixed.total_power_W  # R_DS(on) falls with the lower junction temperature
    assert forced.electrothermal["iterations"] >= 2
    without_models = cl.evaluate_option(dc.cooling_options()[1], _devices(with_models=False), 40.0, electrothermal=True)
    assert without_models.electrothermal is None and without_models.total_power_W == pytest.approx(fixed.total_power_W)


def test_cold_plate_physics_details():
    liquid = dc.cooling_options()[2]
    res = cl.evaluate_option(liquid, _devices(with_models=False), 40.0, electrothermal=False)
    d = res.details
    m_dot = d["coolant"]["density"] * liquid.volumetric_flow
    assert d["coolant_rise_K"] == pytest.approx(res.total_power_W / (m_dot * d["coolant"]["specific_heat"]), rel=1e-6)
    assert d["r_caloric"] == pytest.approx(1.0 / (2.0 * m_dot * d["coolant"]["specific_heat"]), rel=1e-6)
    assert res.r_sink_to_fluid == pytest.approx(d["r_convective"] + d["r_caloric"])
    assert d["regime"] in {"laminar", "turbulent"} and d["reynolds_dh"] > 0 and 0 < d["wall_fin_efficiency"] <= 1
    assert res.pressure_drop_Pa > 0 and res.auxiliary_power_W == pytest.approx(liquid.volumetric_flow * res.pressure_drop_Pa / 0.3 + 0.0)
    assert res.volume_m3 == pytest.approx(0.1 * 0.1 * liquid.total_thickness)
    assert any("Shah-London" in v or "Gnielinski" in v for v in res.validity)
    # more flow: lower caloric term and higher pressure drop
    faster = cl.LiquidColdPlateOption(**{**{k: v for k, v in liquid.__dict__.items() if k != "kind"}, "volumetric_flow": 2 * liquid.volumetric_flow})
    res2 = cl.evaluate_option(faster, _devices(with_models=False), 40.0, electrothermal=False)
    assert res2.details["r_caloric"] < d["r_caloric"] and res2.pressure_drop_Pa > res.pressure_drop_Pa


def test_option_dict_round_trip():
    for opt in dc.cooling_options():
        d = cl.option_to_dict(opt)
        again = cl.option_from_dict(d)
        assert again.kind == opt.kind and again.name == opt.name
    with pytest.raises(ValueError):
        cl.option_from_dict({"kind": "cryogenic"})


def test_dab_loss_estimates_and_reference_cross_check():
    est = dc.loss_estimates()
    assert est["primary"]["conduction_25C_W"] == pytest.approx(9.67 ** 2 * 0.075)
    assert est["primary"]["rds_on_factor"] == pytest.approx(1 + 0.7 * 100 / 150)
    assert est["primary"]["total_W"] == pytest.approx(9.67 ** 2 * 0.075 * (1 + 0.7 * 100 / 150) + 54.0 / 8)
    assert est["secondary"]["total_W"] == pytest.approx(19.75 ** 2 * 0.030 * (1 + 0.7 * 100 / 150) + 54.0 / 8)
    assert est["converter_total_W"] == pytest.approx(4 * est["primary"]["total_W"] + 4 * est["secondary"]["total_W"])
    assert "reference-design figure" in est["primary"]["turn_off_note"]
    ti = dc.ti_reference_network(est)
    p = est["primary"]["total_W"]
    assert ti["primary"]["t_j_C"] == pytest.approx(40.0 + 2 * p * 0.5 + p * (0.1 + 1.1))
    assert any("proxy" in a for a in dc.ASSUMPTIONS) and any("placeholder" in a or "reference-design" in a for a in dc.ASSUMPTIONS)
