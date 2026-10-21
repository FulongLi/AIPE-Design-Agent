"""Tests for pea.thermal.network: shared-sink steady state and Foster/Cauer transients (standard library only)."""

import json
import math

import pytest

from pea.thermal import network as net


def _two_devices():
    return [net.DeviceThermalPath("S1", 17.0, 1.1, 0.1, 0.02, tj_max_C=175.0, tj_design_C=125.0),
            net.DeviceThermalPath("S2", 17.0, 1.1, 0.1, 0.02, tj_max_C=175.0, tj_design_C=125.0)]


def test_shared_sink_steady_state_matches_hand_calculation():
    sink = net.SharedHeatSink(0.5, 40.0)
    res = net.solve_steady_state(_two_devices(), sink)
    assert res["t_sink_C"] == pytest.approx(40.0 + 34.0 * 0.5)
    assert res["t_j_max_C"] == pytest.approx(57.0 + 17.0 * (0.02 + 0.1 + 1.1))
    assert res["hottest_device"] in {"S1", "S2"}
    assert res["all_within_design_limit"] and res["all_within_absolute_limit"]
    row = res["devices"][0]
    assert row["margin_to_tj_design_K"] == pytest.approx(125.0 - row["t_j_C"])
    json.dumps(res)


def test_coupling_through_shared_node_and_power_override():
    sink = net.SharedHeatSink(0.5, 40.0)
    devices = _two_devices()
    base = net.solve_steady_state(devices, sink)
    hotter = net.solve_steady_state(devices, sink, {"S2": 34.0})  # only S2 changes power
    s1_base = next(r for r in base["devices"] if r["name"] == "S1")["t_j_C"]
    s1_hot = next(r for r in hotter["devices"] if r["name"] == "S1")["t_j_C"]
    assert s1_hot - s1_base == pytest.approx(17.0 * 0.5)  # S1 only sees the sink-node rise
    assert hotter["hottest_device"] == "S2"


def test_allowable_power_and_required_resistance():
    sink = net.SharedHeatSink(0.5, 40.0)
    devices = _two_devices()
    p = net.allowable_power(devices[0], sink, other_devices_power_W=17.0, tj_limit_C=125.0)
    check = net.solve_steady_state(devices, sink, {"S1": p, "S2": 17.0})
    assert next(r for r in check["devices"] if r["name"] == "S1")["t_j_C"] == pytest.approx(125.0)
    r_req = net.required_sink_resistance(devices, 40.0, 125.0)
    at_limit = net.solve_steady_state(devices, net.SharedHeatSink(r_req, 40.0))
    assert at_limit["t_j_max_C"] == pytest.approx(125.0)
    with pytest.raises(ValueError):
        net.solve_steady_state([devices[0], devices[0]], sink)  # duplicate names
    with pytest.raises(ValueError):
        net.DeviceThermalPath("x", -1.0, 1.0)


def test_network_solver_callable_for_electrothermal():
    solver = net.make_network_solver(_two_devices(), net.SharedHeatSink(0.5, 40.0))
    tj = solver({"S1": 10.0, "S2": 10.0})
    assert tj["S1"] == pytest.approx(40.0 + 20.0 * 0.5 + 10.0 * 1.22)


def test_foster_zth_limits_and_superposition():
    f = net.FosterNetwork.from_pairs([(0.1, 1e-3), (0.2, 1e-2), (0.3, 1e-1)])
    assert f.zth(0.0) == 0.0
    assert f.zth(100.0) == pytest.approx(f.r_static, rel=1e-9)
    assert f.zth(1e-3) == pytest.approx(0.1 * (1 - math.exp(-1)) + 0.2 * (1 - math.exp(-0.1)) + 0.3 * (1 - math.exp(-0.01)))
    pulse = f.response_to_power_steps([(0.0, 10.0), (1.0, 0.0)], 1.5)
    assert pulse == pytest.approx(10.0 * (f.zth(1.5) - f.zth(0.5)))
    assert f.response_to_power_steps([(0.0, 10.0)], 50.0) == pytest.approx(10.0 * f.r_static, rel=1e-9)


def test_foster_to_cauer_is_exact_and_simulation_matches_analytic():
    f = net.FosterNetwork.from_pairs([(0.1, 1e-3), (0.2, 1e-2), (0.3, 1e-1), (0.5, 2.0)])
    c = f.to_cauer()
    assert len(c.resistances) == 4 and all(r > 0 for r in c.resistances) and all(x > 0 for x in c.capacitances)
    assert c.r_static == pytest.approx(f.r_static, rel=1e-12)
    times = [3e-4, 3e-3, 3e-2, 0.3, 3.0, 30.0]
    for t, z in zip(times, c.step_response_samples(times)):
        assert z == pytest.approx(f.zth(t), rel=5e-3)
    assert c.zth(0.0) == 0.0
    d = c.to_dict()
    assert d["type"] == "cauer" and json.dumps(d)


def test_transient_junction_temperature_uses_zth_and_static_sink():
    f = net.FosterNetwork.from_pairs([(0.5, 0.01), (0.6, 0.5)])
    dev = net.DeviceThermalPath("S1", 20.0, 1.1, 0.1, 0.0, zth_jc=f)
    sink = net.SharedHeatSink(0.5, 40.0)
    hist = net.transient_junction_temperature(dev, sink, [(0.0, 20.0)], [0.0, 0.01, 100.0], other_devices_power_W=20.0)
    assert hist[0]["t_j_C"] == pytest.approx(40.0 + 40.0 * 0.5 + 20.0 * 0.1)  # zth(0) = 0, static sink and TIM
    assert hist[-1]["t_j_C"] == pytest.approx(40.0 + 40.0 * 0.5 + 20.0 * (0.1 + 1.1), rel=1e-6)
    assert hist[0]["t_j_C"] < hist[1]["t_j_C"] < hist[-1]["t_j_C"]


def test_from_dict_round_trip():
    d = {"name": "S1", "power_W": 17.0, "r_jc": 1.1, "r_cs": 0.1, "tj_max_C": 175, "zth_jc": {"type": "foster", "stages": [{"resistance": 0.5, "time_constant": 0.01}]}}
    dev = net.DeviceThermalPath.from_dict(d)
    assert dev.zth_jc is not None and dev.zth_jc.r_static == 0.5
    assert dev.to_dict()["zth_jc"]["type"] == "foster"
    sink = net.SharedHeatSink.from_dict({"r_sa": 0.5, "t_ambient_C": 40.0})
    assert sink.to_dict()["r_sa"] == 0.5
