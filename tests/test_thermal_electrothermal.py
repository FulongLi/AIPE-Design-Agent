"""Tests for pea.thermal.electrothermal: datasheet defaults and the loss(Tj) <-> Tj iteration."""

import json

import pytest

from pea.thermal import electrothermal as et
from pea.thermal import network as net


def test_rds_on_two_point_models_reproduce_datasheet_points():
    lin = et.RdsOnModel(0.075, 25.0, 0.075 * 1.7, 175.0, "linear")
    pw = et.RdsOnModel(0.075, 25.0, 0.075 * 1.7, 175.0, "power_law")
    for m in (lin, pw):
        assert m(25.0) == pytest.approx(0.075)
        assert m(175.0) == pytest.approx(0.075 * 1.7)
        assert m(125.0) > m(75.0) > m(25.0)
    assert lin.factor(125.0) == pytest.approx(1 + 0.7 * 100 / 150)
    assert lin.alpha_per_K == pytest.approx(0.7 / 150)
    assert json.dumps(lin.to_dict())
    with pytest.raises(ValueError):
        et.RdsOnModel(0.075, 25.0, 0.1, 25.0)
    with pytest.raises(ValueError):
        et.RdsOnModel(0.075, 25.0, 0.1, 175.0, "cubic")


def test_switching_energy_scaling_and_two_point_fit():
    e = et.SwitchingEnergyModel.from_two_points(100e-6, 25.0, 150e-6, 175.0, v_ref_V=800.0, i_ref_A=20.0)
    assert e.energy(25.0, 800.0, 20.0) == pytest.approx(100e-6)
    assert e.energy(175.0, 800.0, 20.0) == pytest.approx(150e-6)
    assert e.energy(25.0, 400.0, 10.0) == pytest.approx(25e-6)  # linear in V and I by default
    assert e.energy(-1000.0, 800.0, 20.0) == 0.0  # clamped
    assert et.switching_loss_W(100e-6, 100e3) == pytest.approx(10.0)
    assert et.conduction_loss_W(9.67, 0.075) == pytest.approx(9.67 ** 2 * 0.075)


def test_datasheet_default_device_losses():
    rds = et.RdsOnModel(0.075, 25.0, 0.075 * 1.7, 175.0)
    dev = et.DeviceLossModel.datasheet_default("S1", 9.67, rds, 100e3, fixed_switching_W=6.75)
    losses = dev.losses(125.0)
    assert losses["conduction_W"] == pytest.approx(9.67 ** 2 * 0.075 * (1 + 0.7 * 100 / 150))
    assert losses["switching_W"] == 6.75 and losses["total_W"] == pytest.approx(losses["conduction_W"] + 6.75)
    e_off = et.SwitchingEnergyModel(100e-6, 25.0, 800.0, 20.0, t_coeff_per_K=0.002)
    dev2 = et.DeviceLossModel.datasheet_default("S2", 9.67, rds, 100e3, e_off=e_off, v_off_V=800.0, i_off_A=14.26)
    assert dev2.losses(25.0)["switching_W"] == pytest.approx(100e-6 * 14.26 / 20.0 * 100e3)
    assert dev2.losses(125.0)["switching_W"] > dev2.losses(25.0)["switching_W"]


def test_iteration_converges_to_closed_form_fixed_point():
    R, P0, alpha, Ta = 1.0, 10.0, 0.005, 40.0
    dev = et.DeviceLossModel("D", conduction=lambda tj: P0 * (1 + alpha * (tj - 25.0)), switching=lambda tj: 0.0)
    res = et.iterate([dev], lambda p: {"D": Ta + R * p["D"]}, 25.0, et.ElectrothermalSettings(tol_K=1e-6))
    assert res.converged and res.reason == "converged"
    assert res.tj_C["D"] == pytest.approx(et.linear_fixed_point(Ta, R, P0, alpha), abs=1e-4)
    assert len(res.history) == res.iterations and res.history[0]["iteration"] == 0
    assert res.history[-1]["max_change_K"] < 1e-6
    assert json.dumps(res.to_dict())


def test_iteration_detects_thermal_runaway():
    dev = et.DeviceLossModel("D", conduction=lambda tj: 50.0 * (1 + 0.03 * (tj - 25.0)), switching=lambda tj: 0.0)
    res = et.iterate([dev], lambda p: {"D": 40.0 + 1.0 * p["D"]}, 25.0, et.ElectrothermalSettings(max_iterations=200))
    assert not res.converged and "runaway" in res.reason
    with pytest.raises(ValueError):
        et.linear_fixed_point(40.0, 1.0, 50.0, 0.03)


def test_iteration_with_shared_sink_network_and_plugin_callables():
    rds = et.RdsOnModel(0.075, 25.0, 0.075 * 1.7, 175.0)
    models = [et.DeviceLossModel.datasheet_default(n, 9.67, rds, 100e3, fixed_switching_W=6.75) for n in ("S1", "S2")]
    paths = [net.DeviceThermalPath(n, 0.0, 1.1, 0.1) for n in ("S1", "S2")]
    solver = net.make_network_solver(paths, net.SharedHeatSink(0.5, 40.0))
    res = et.iterate(models, solver, 25.0)
    assert res.converged and res.iterations <= 20
    p = res.losses_W["S1"]["total_W"]
    assert res.tj_C["S1"] == pytest.approx(40.0 + 2 * p * 0.5 + p * 1.2, abs=0.05)
    # plug-in callables (e.g. a semiconductor-database evaluator) are accepted directly
    custom = et.DeviceLossModel("X", conduction=lambda tj: 5.0, switching=lambda tj: 1.0, extra_W=0.5)
    res2 = et.iterate([custom], lambda pw: {"X": 40.0 + pw["X"]}, 25.0)
    assert res2.converged and res2.tj_C["X"] == pytest.approx(46.5)


def test_settings_validation_and_relaxation():
    with pytest.raises(ValueError):
        et.ElectrothermalSettings(relaxation=0.0)
    dev = et.DeviceLossModel("D", conduction=lambda tj: 10.0 * (1 + 0.005 * (tj - 25.0)), switching=lambda tj: 0.0)
    res = et.iterate([dev], lambda p: {"D": 40.0 + p["D"]}, 25.0, et.ElectrothermalSettings(relaxation=0.5, tol_K=1e-4))
    assert res.converged and res.tj_C["D"] == pytest.approx(et.linear_fixed_point(40.0, 1.0, 10.0, 0.005), abs=1e-2)
