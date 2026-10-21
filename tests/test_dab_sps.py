"""Regression tests for the lossless SPS dual-active-bridge model (aipe_electrical.converters.dab_sps).

The AIPE 10 kW benchmark (800 V -> 400 V, N_p/N_s = 2, 100 kHz, 35 uH total primary-referred
series inductance) must reproduce the textbook SPS results exactly: phi = 22.5 deg for 10 kW,
P_max = 22 857 W, 12.5 A / 25 A DC port currents, 14.2857 A peak and 13.6775 A RMS series current.
Ported from the legacy ``tests/test_dab_sps.py`` (pea.converters.dab_sps) and extended with the
semantic checks of v0.2 (turns-ratio direction, inductance composition, rad/deg, power-flow
direction, ZVS evidence labelling, phase-shift limits, invalid inputs).
"""

import math

import pytest

from aipe_electrical.converters import dab_sps as m

NOMINAL = dict(v1=800.0, v2=400.0, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, phi_rad=math.radians(22.5))
I_PEAK_NOMINAL = 100 / 7  # (V1 + V2') t_phi / (2 L) with t_phi = T/16 -> 14.2857 A


@pytest.fixture
def op():
    return m.SpsOperatingPoint(**NOMINAL)


# ------------------------------------------------------------------ benchmark


def test_nominal_power_is_exactly_10kw(op):
    assert m.power(op) == pytest.approx(10000.0, rel=1e-12)
    assert m.power_from_waveform(op) == pytest.approx(10000.0, rel=1e-12)


def test_nominal_phase_shift_solves_to_22_5_degrees():
    phi = m.phase_shift_for_power(v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, p=10000)
    assert math.degrees(phi) == pytest.approx(22.5, abs=1e-12)


def test_nominal_max_power():
    p_max = m.max_power(v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6)
    assert p_max == pytest.approx(22857.142857, rel=1e-9)
    assert p_max == pytest.approx(800 * 800 / (8 * 100e3 * 35e-6), rel=1e-12)


def test_nominal_dc_currents(op):
    a = m.analyse(op)["derived"]
    assert a["dc_current_port1"] == {"value": pytest.approx(12.5, rel=1e-12), "unit": "A"}
    assert a["dc_current_port2"] == {"value": pytest.approx(25.0, rel=1e-12), "unit": "A"}


def test_nominal_peak_and_rms_current(op):
    # Matched case d = 1: ramp of (V1+V2') t_phi / L between -I_pk and +I_pk, flat top otherwise.
    t_phi = op.period * 22.5 / 360
    i_pk = (op.v1 + op.v2_primary_referred) * t_phi / op.l_series_total / 2
    assert i_pk == pytest.approx(I_PEAK_NOMINAL, rel=1e-12)
    assert m.current_peak(op) == pytest.approx(14.2857, abs=5e-5)
    a, b = t_phi, op.period / 2 - t_phi
    i_rms = i_pk * math.sqrt((a / 3 + b) / (a + b))
    assert m.current_rms(op) == pytest.approx(i_rms, rel=1e-12)
    assert m.current_rms(op) == pytest.approx(13.6775, abs=5e-5)
    assert m.current_rms(op) == pytest.approx(I_PEAK_NOMINAL * math.sqrt(11 / 12), rel=1e-12)


def test_nominal_inverse_functions_round_trip():
    l_total = m.series_inductance_for_power(
        v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, phi_rad=math.radians(22.5), p=10000
    )
    assert l_total == pytest.approx(35e-6, rel=1e-12)
    design = m.design_for_power(v1=800, v2=400, p=10000, f_sw=100e3, phi_rad=math.radians(22.5))
    assert design.turns_ratio_np_ns == pytest.approx(2.0)
    assert design.l_series_total == pytest.approx(35e-6, rel=1e-12)
    assert m.power(design) == pytest.approx(10000.0, rel=1e-12)


# ---------------------------------------------------------------- semantics


def test_turns_ratio_direction_is_explicit(op):
    assert op.turns_ratio_np_ns == 2.0
    assert op.turns_ratio_ns_np == pytest.approx(0.5)
    assert op.v2_primary_referred == pytest.approx(800.0)
    assert op.d == pytest.approx(1.0)
    assert m.matched_turns_ratio_np_ns(800, 400) == pytest.approx(2.0)
    # Using N_s/N_p where N_p/N_s is expected gives a different (mismatched) operating point.
    wrong = m.SpsOperatingPoint(**{**NOMINAL, "turns_ratio_np_ns": 0.5})
    assert wrong.d == pytest.approx(0.25)
    assert m.power(wrong) == pytest.approx(0.25 * m.power(op), rel=1e-12)


def test_total_series_inductance_composition_refers_secondary_parts_by_n_squared():
    total = m.total_series_inductance_primary(
        turns_ratio_np_ns=2.0, l_external_primary=30e-6, l_leakage_primary=1e-6, l_leakage_secondary=1e-6
    )
    assert total == pytest.approx(35e-6, rel=1e-12)  # 30 + 1 + 2^2 * 1 uH
    assert m.total_series_inductance_primary(turns_ratio_np_ns=0.5, l_external_secondary=40e-6) == pytest.approx(10e-6)
    with pytest.raises(ValueError):
        m.total_series_inductance_primary(turns_ratio_np_ns=2.0)
    with pytest.raises(ValueError):
        m.total_series_inductance_primary(turns_ratio_np_ns=2.0, l_external_primary=-1e-6)


def test_phase_shift_degrees_and_radians_are_distinguished(op):
    from_deg = m.SpsOperatingPoint.from_degrees(
        v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, phi_deg=22.5
    )
    assert from_deg == op
    assert op.phi_deg == pytest.approx(22.5)
    assert op.t_phi == pytest.approx(op.period / 16)
    with pytest.raises(ValueError):
        m.SpsOperatingPoint(**{**NOMINAL, "phi_rad": 22.5})  # degrees passed as radians exceed pi/2


def test_power_flow_direction_follows_sign_of_phase_shift(op):
    assert op.power_flow == "port1_to_port2"
    assert op.with_phase_shift(-op.phi_rad).power_flow == "port2_to_port1"
    assert op.with_phase_shift(0.0).power_flow == "none"
    assert m.power_flow_direction(-0.1) == "port2_to_port1"
    assert m.analyse(op)["derived"]["power_flow_direction"] == "port1_to_port2"


def test_reverse_power_flow_is_antisymmetric(op):
    rev = op.with_phase_shift(-op.phi_rad)
    assert m.power(rev) == pytest.approx(-10000.0, rel=1e-12)
    assert m.power_from_waveform(rev) == pytest.approx(-10000.0, rel=1e-12)
    assert m.current_rms(rev) == pytest.approx(m.current_rms(op), rel=1e-12)
    assert m.current_peak(rev) == pytest.approx(m.current_peak(op), rel=1e-12)
    sw = m.switching_currents(rev)
    assert sw.primary_zvs_current_direction_ok and sw.secondary_zvs_current_direction_ok
    phi = m.phase_shift_for_power(v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, p=-10000)
    assert math.degrees(phi) == pytest.approx(-22.5, abs=1e-12)
    l_rev = m.series_inductance_for_power(
        v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, phi_rad=-math.radians(22.5), p=-10000
    )
    assert l_rev == pytest.approx(35e-6, rel=1e-12)


def test_design_for_power_rejects_inconsistent_direction():
    with pytest.raises(ValueError):
        m.series_inductance_for_power(
            v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, phi_rad=math.radians(22.5), p=-10000
        )
    with pytest.raises(ValueError):
        m.series_inductance_for_power(v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, phi_rad=0.0, p=10000)
    with pytest.raises(ValueError):
        m.design_for_power(v1=800, v2=400, p=0.0, f_sw=100e3, phi_rad=0.3)


def test_design_for_power_with_explicit_turns_ratio():
    design = m.design_for_power(v1=800, v2=400, p=10000, f_sw=100e3, phi_rad=math.radians(22.5), turns_ratio_np_ns=1.8)
    assert design.turns_ratio_np_ns == 1.8
    assert design.d == pytest.approx(0.9)
    assert m.power(design) == pytest.approx(10000.0, rel=1e-12)
    assert design.l_series_total == pytest.approx(0.9 * 35e-6, rel=1e-12)


# ------------------------------------------------------------- waveform exactness


def test_half_wave_antisymmetry_and_periodicity(op):
    T = op.period
    for t in (0.0, 0.3e-6, 1.7e-6, 4.9e-6):
        assert m.current_at(op, t + T / 2) == pytest.approx(-m.current_at(op, t), abs=1e-9)
        assert m.current_at(op, t + T) == pytest.approx(m.current_at(op, t), abs=1e-9)


def test_breakpoints_span_one_period_and_match_current_at(op):
    pts = m.breakpoints(op)
    assert pts[0][0] == 0.0
    assert pts[-1][0] == pytest.approx(op.period)
    assert pts[-1][1] == pytest.approx(pts[0][1], abs=1e-9)
    for t, i in pts[:-1]:
        assert m.current_at(op, t) == pytest.approx(i, abs=1e-9)


@pytest.mark.parametrize("d", [0.6, 1.0, 1.4])
@pytest.mark.parametrize("phi_deg", [-80.0, -22.5, -5.0, 0.0, 5.0, 22.5, 80.0])
def test_closed_form_power_equals_waveform_integral_for_any_ratio_and_shift(d, phi_deg):
    op = m.SpsOperatingPoint(
        v1=800, v2=400 * d, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, phi_rad=math.radians(phi_deg)
    )
    assert op.d == pytest.approx(d)
    assert m.power_from_waveform(op) == pytest.approx(m.power(op), abs=1e-6)


@pytest.mark.parametrize("d,phi_deg", [(1.0, 22.5), (0.75, 30.0), (1.3, -40.0), (0.9, 0.0)])
def test_exact_rms_matches_fine_numerical_sampling(d, phi_deg):
    op = m.SpsOperatingPoint(
        v1=800, v2=400 * d, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, phi_rad=math.radians(phi_deg)
    )
    n = 20000
    samples = [m.current_at(op, k * op.period / n) for k in range(n)]
    numeric_rms = math.sqrt(sum(s * s for s in samples) / n)
    assert m.current_rms(op) == pytest.approx(numeric_rms, rel=1e-3)
    assert m.current_peak(op) == pytest.approx(max(abs(s) for s in samples), rel=1e-3)


def test_centre_origin_matches_simulation_convention(op):
    # Centre of the positive half-cycle lies on the flat top for d = 1.
    assert m.current_at(op, 0.0, origin="centre") == pytest.approx(I_PEAK_NOMINAL, rel=1e-12)
    assert m.current_at(op, -op.period / 4, origin="centre") == pytest.approx(-I_PEAK_NOMINAL, rel=1e-12)
    with pytest.raises(ValueError):
        m.current_at(op, 0.0, origin="edge")


def test_sample_waveforms_shape_and_consistency(op):
    w = m.sample_waveforms(op, 8, origin="centre")
    assert len(w["time_s"]) == 9 and w["origin"] == "centre"
    assert w["i_L_A"][0] == pytest.approx(I_PEAK_NOMINAL, rel=1e-12)
    assert set(w) >= {"time_s", "v_ab_V", "v_cd_referred_V", "v_L_V", "i_L_A"}
    assert all(abs(v) == pytest.approx(800.0) for v in w["v_ab_V"])
    with pytest.raises(ValueError):
        m.sample_waveforms(op, 1)


# -------------------------------------------------------------------- limits


def test_zero_phase_shift_transfers_no_power(op):
    zero = op.with_phase_shift(0.0)
    assert m.power(zero) == 0.0
    assert m.current_rms(zero) == pytest.approx(0.0, abs=1e-12)  # matched: no circulating current
    mismatched = m.SpsOperatingPoint(
        v1=800, v2=300, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, phi_rad=0.0
    )
    assert m.power(mismatched) == 0.0
    assert m.current_rms(mismatched) > 0.0  # reactive circulating current only
    assert (
        m.phase_shift_for_power(v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, p=0.0) == 0.0
    )


@pytest.mark.parametrize("sign", [1.0, -1.0])
def test_ninety_degrees_gives_maximum_power(op, sign):
    limit = op.with_phase_shift(sign * math.pi / 2)
    p_max = m.max_power(v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6)
    assert m.power(limit) == pytest.approx(sign * p_max, rel=1e-12)
    assert m.power_from_waveform(limit) == pytest.approx(sign * p_max, rel=1e-9)
    phi = m.phase_shift_for_power(
        v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, p=sign * p_max
    )
    assert phi == pytest.approx(sign * math.pi / 2, rel=1e-6)
    assert m.phase_shift_limits() == (-math.pi / 2, math.pi / 2)


def test_power_above_maximum_is_rejected():
    with pytest.raises(ValueError, match="exceeds"):
        m.phase_shift_for_power(v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, p=30000)
    with pytest.raises(ValueError, match="exceeds"):
        m.phase_shift_for_power(v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, p=-22858)


@pytest.mark.parametrize(
    "overrides",
    [
        {"v1": 0.0},
        {"v2": -400.0},
        {"turns_ratio_np_ns": 0.0},
        {"f_sw": 0.0},
        {"l_series_total": 0.0},
        {"l_series_total": float("nan")},
        {"phi_rad": math.radians(95)},
        {"phi_rad": -math.radians(90.001)},
        {"phi_rad": float("inf")},
        {"v1": True},
    ],
)
def test_invalid_operating_points_are_rejected(overrides):
    with pytest.raises(ValueError):
        m.SpsOperatingPoint(**{**NOMINAL, **overrides})


def test_scalar_functions_validate_inputs():
    with pytest.raises(ValueError):
        m.max_power(v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=0.0, l_series_total=35e-6)
    with pytest.raises(ValueError):
        m.phase_shift_for_power(v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=0.0, p=1000)
    with pytest.raises(ValueError):
        m.series_inductance_for_power(
            v1=800, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, phi_rad=math.radians(120), p=1000
        )
    with pytest.raises(ValueError):
        m.power_flow_direction(float("nan"))
    with pytest.raises(TypeError):
        m.max_power(800, 400, 2.0, 100e3, 35e-6)  # keyword-only: positional n vs 1/n mix-ups are refused


# ---------------------------------------------------------------------- ZVS


def test_switching_currents_and_current_direction_conditions(op):
    sw = m.switching_currents(op)
    assert sw.primary_switching_current == pytest.approx(-I_PEAK_NOMINAL, rel=1e-12)
    assert sw.secondary_switching_current_primary_referred == pytest.approx(I_PEAK_NOMINAL, rel=1e-12)
    assert sw.secondary_switching_current == pytest.approx(2 * I_PEAK_NOMINAL, rel=1e-12)
    assert sw.primary_zvs_current_direction_ok and sw.secondary_zvs_current_direction_ok
    d = sw.to_dict()
    assert d["primary_switching_current_A"] == pytest.approx(-I_PEAK_NOMINAL)
    assert "necessary" in d["evidence"] and "confirm" not in d["evidence"].lower().replace(
        "not a charge-based zvs verification", ""
    )


def test_unmatched_voltage_ratio_changes_current_direction_boundary():
    # Lower secondary voltage (d < 1): the secondary bridge loses the condition at light load.
    op = m.SpsOperatingPoint(
        v1=800, v2=300, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, phi_rad=math.radians(5)
    )
    limits = m.zvs_phase_shift_limits(op)
    assert limits.d == pytest.approx(0.75)
    assert limits.secondary_min_abs_phi_rad == pytest.approx(math.pi * 0.25 / 2)
    assert limits.primary_min_abs_phi_rad == 0.0
    assert limits.both_bridges_min_abs_phi_rad == pytest.approx(math.pi * 0.25 / 2)
    sw = m.switching_currents(op)
    assert not sw.secondary_zvs_current_direction_ok and sw.primary_zvs_current_direction_ok
    op2 = op.with_phase_shift(math.radians(30))
    assert m.switching_currents(op2).secondary_zvs_current_direction_ok
    # Mirror case d > 1: the primary bridge is the critical one; the boundary also holds for reverse flow.
    op3 = m.SpsOperatingPoint(
        v1=600, v2=400, turns_ratio_np_ns=2.0, f_sw=100e3, l_series_total=35e-6, phi_rad=math.radians(5)
    )
    lim3 = m.zvs_phase_shift_limits(op3)
    assert lim3.primary_min_abs_phi_rad == pytest.approx(math.pi * (1 - 1 / lim3.d) / 2)
    assert not m.switching_currents(op3).primary_zvs_current_direction_ok
    assert not m.switching_currents(op3.with_phase_shift(-math.radians(5))).primary_zvs_current_direction_ok
    assert m.switching_currents(op3.with_phase_shift(math.radians(40))).primary_zvs_current_direction_ok


def test_zvs_is_labelled_as_necessary_condition_not_confirmation(op):
    report = m.analyse(op)
    zvs = report["zvs_current_direction_conditions"]
    assert zvs["primary"] is True and zvs["secondary"] is True
    assert "necessary" in zvs["evidence"] and "not a charge-based ZVS verification" in zvs["evidence"]
    assert zvs["limits"]["evidence"] == m.ZVS_EVIDENCE_LABEL
    assert "zvs_current_conditions" not in report  # legacy key retired
    assert not any("ZVS confirmed" in a or "Achievable" in a for a in report["assumptions"])


# ------------------------------------------------------------------ analyse


def test_analyse_reports_si_units_assumptions_and_explicit_names(op):
    a = m.analyse(op)
    assert a["model"] == m.MODEL_ID
    assert a["inputs"]["series_inductance_total_primary_referred"] == {"value": 35e-6, "unit": "H"}
    assert a["inputs"]["turns_ratio_np_ns"] == {"value": 2.0, "unit": "1"}
    assert a["inputs"]["turns_ratio_ns_np"]["value"] == pytest.approx(0.5)
    assert a["inputs"]["phase_shift"]["unit"] == "rad" and a["inputs"]["phase_shift_deg"]["unit"] == "deg"
    assert a["derived"]["power"]["unit"] == "W"
    assert a["derived"]["max_power_sps"]["value"] == pytest.approx(22857.142857, rel=1e-9)
    assert a["derived"]["series_current_rms_primary"]["value"] == pytest.approx(13.6775, abs=5e-5)
    assert a["derived"]["series_current_peak_primary"]["value"] == pytest.approx(14.2857, abs=5e-5)
    assert a["derived"]["secondary_current_peak"]["value"] == pytest.approx(2 * I_PEAK_NOMINAL, rel=1e-12)
    assert any("Ideal switches" in s for s in a["assumptions"])
    assert a["waveform_breakpoints_rising_edge_origin"][0]["t"] == 0.0
    import json

    json.dumps(a)  # JSON-ready without a custom encoder
