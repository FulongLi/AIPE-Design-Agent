"""Analytical regression tests for the SPS dual-active-bridge model (pea.converters.dab_sps).

The nominal AIPE 10 kW benchmark (800 V -> 400 V, n = 2, 100 kHz, 35 uH, 22.5 deg)
must reproduce the textbook SPS results exactly: 10 kW, 12.5 A / 25 A DC
currents, 14.2857 A peak and 13.6775 A RMS series current.
"""

import math

import pytest

from pea.converters import dab_sps as m

NOMINAL = dict(v1=800.0, v2=400.0, n_ratio=2.0, f_sw=100e3, l_total=35e-6, phi_rad=math.radians(22.5))


@pytest.fixture
def op():
    return m.SpsOperatingPoint(**NOMINAL)


def test_nominal_power_is_exactly_10kw(op):
    p = m.power(op.v1, op.v2, op.n_ratio, op.f_sw, op.l_total, op.phi_rad)
    assert p == pytest.approx(10000.0, rel=1e-12)
    assert m.power_from_waveform(op) == pytest.approx(p, rel=1e-12)


def test_nominal_dc_currents(op):
    a = m.analyse(op)["derived"]
    assert a["dc_current_port1"]["value"] == pytest.approx(12.5, rel=1e-12)
    assert a["dc_current_port2"]["value"] == pytest.approx(25.0, rel=1e-12)
    assert a["dc_current_port1"]["unit"] == "A"


def test_nominal_peak_and_rms_current(op):
    # Matched case d = 1: ramp of (V1+V2') t_phi / L between -I_pk and +I_pk, flat top otherwise.
    t_phi = op.period * 22.5 / 360
    i_pk = (op.v1 + op.v2_referred) * t_phi / op.l_total / 2
    assert m.current_peak(op) == pytest.approx(i_pk, rel=1e-12)
    assert i_pk == pytest.approx(100 / 7, rel=1e-12)  # 14.2857 A
    a, b = t_phi, op.period / 2 - t_phi
    i_rms = i_pk * math.sqrt((a / 3 + b) / (a + b))
    assert m.current_rms(op) == pytest.approx(i_rms, rel=1e-12)
    assert i_rms == pytest.approx(13.6775, abs=5e-4)


def test_half_wave_antisymmetry_and_periodicity(op):
    T = op.period
    for t in (0.0, 0.3e-6, 1.7e-6, 4.9e-6):
        assert m.current_at(op, t + T / 2) == pytest.approx(-m.current_at(op, t), abs=1e-9)
        assert m.current_at(op, t + T) == pytest.approx(m.current_at(op, t), abs=1e-9)


def test_switching_currents_and_zvs_conditions(op):
    sw = m.switching_currents(op)
    assert sw["primary_switching_current_A"] == pytest.approx(-100 / 7, rel=1e-12)
    assert sw["secondary_switching_current_primary_referred_A"] == pytest.approx(100 / 7, rel=1e-12)
    assert sw["primary_zvs_current_condition"] and sw["secondary_zvs_current_condition"]


def test_centre_origin_matches_simulation_convention(op):
    # Centre of the positive half-cycle lies on the flat top for d = 1.
    assert m.current_at(op, 0.0, origin="centre") == pytest.approx(100 / 7, rel=1e-12)
    assert m.current_at(op, -op.period / 4, origin="centre") == pytest.approx(-100 / 7, rel=1e-12)


def test_inverse_functions_round_trip():
    phi = m.phase_shift_for_power(800, 400, 2.0, 100e3, 35e-6, 10000)
    assert math.degrees(phi) == pytest.approx(22.5, rel=1e-12)
    assert m.inductance_for_power(800, 400, 2.0, 100e3, math.radians(22.5), 10000) == pytest.approx(35e-6, rel=1e-12)
    assert m.max_power(800, 400, 2.0, 100e3, 35e-6) == pytest.approx(22857.142857, rel=1e-9)
    with pytest.raises(ValueError):
        m.phase_shift_for_power(800, 400, 2.0, 100e3, 35e-6, 30000)


def test_reverse_power_flow_is_antisymmetric():
    fwd = m.SpsOperatingPoint(**NOMINAL)
    rev = m.SpsOperatingPoint(**{**NOMINAL, "phi_rad": -NOMINAL["phi_rad"]})
    assert m.power(rev.v1, rev.v2, rev.n_ratio, rev.f_sw, rev.l_total, rev.phi_rad) == pytest.approx(-10000.0, rel=1e-12)
    assert m.current_rms(rev) == pytest.approx(m.current_rms(fwd), rel=1e-12)
    sw = m.switching_currents(rev)
    assert sw["primary_zvs_current_condition"] and sw["secondary_zvs_current_condition"]


def test_unmatched_voltage_ratio_changes_zvs_boundary():
    # Lower secondary voltage (d < 1): secondary bridge loses ZVS at light load.
    op = m.SpsOperatingPoint(v1=800, v2=300, n_ratio=2.0, f_sw=100e3, l_total=35e-6, phi_rad=math.radians(5))
    limits = m.zvs_phase_shift_limits(op)
    assert limits["d"] == pytest.approx(0.75)
    assert limits["secondary_min_phi_rad"] == pytest.approx(math.pi * 0.25 / 2)
    assert not m.switching_currents(op)["secondary_zvs_current_condition"]
    assert m.switching_currents(op)["primary_zvs_current_condition"]
    op2 = m.SpsOperatingPoint(v1=800, v2=300, n_ratio=2.0, f_sw=100e3, l_total=35e-6, phi_rad=math.radians(30))
    assert m.switching_currents(op2)["secondary_zvs_current_condition"]


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        m.SpsOperatingPoint(v1=0, v2=400, n_ratio=2, f_sw=1e5, l_total=35e-6, phi_rad=0.1)
    with pytest.raises(ValueError):
        m.SpsOperatingPoint(v1=800, v2=400, n_ratio=2, f_sw=1e5, l_total=35e-6, phi_rad=2.0)


def test_analyse_reports_si_units_and_assumptions(op):
    a = m.analyse(op)
    assert a["inputs"]["series_inductance_primary_referred"] == {"value": 35e-6, "unit": "H"}
    assert a["derived"]["power"]["unit"] == "W"
    assert any("Ideal switches" in s for s in a["assumptions"])
    assert a["waveform_breakpoints_rising_edge_origin"][0]["t"] == 0.0
