"""SPS design-space sweep (aipe_electrical.optimisation.dab_sps_sweep)."""

import math

import pytest

from aipe_electrical.optimisation import dab_sps_sweep as sweep

BENCH = dict(v1=800.0, v2=400.0, p=10000.0)


def test_sweep_contains_the_benchmark_point_and_skips_infeasible_inductances():
    pts = sweep.sweep_sps_designs(
        **BENCH,
        switching_frequencies=[100e3],
        turns_ratios_np_ns=[2.0],
        series_inductances=[20e-6, 35e-6, 50e-6, 100e-6],
    )
    # 100 uH gives P_max = 8 kW < 10 kW and is dropped.
    assert [p.operating_point.l_series_total for p in pts] == pytest.approx([20e-6, 35e-6, 50e-6])
    bench = pts[1]
    assert bench.operating_point.phi_deg == pytest.approx(22.5, abs=1e-9)
    assert bench.i_rms_primary == pytest.approx(13.6775, abs=5e-5)
    assert bench.i_peak_primary == pytest.approx(14.2857, abs=5e-5)
    assert bench.max_power == pytest.approx(22857.142857, rel=1e-9)
    assert bench.power_headroom == pytest.approx(2.2857142857, rel=1e-9)
    assert bench.i_rms_secondary == pytest.approx(2 * bench.i_rms_primary)
    assert bench.primary_zvs_current_direction_ok and bench.secondary_zvs_current_direction_ok
    d = bench.to_dict()
    assert d["turns_ratio_ns_np"] == pytest.approx(0.5) and "necessary" in d["zvs_evidence"]


def test_matched_case_trade_off_rms_rises_with_phase_shift():
    pts = sweep.sweep_sps_designs(
        **BENCH,
        switching_frequencies=[100e3],
        turns_ratios_np_ns=[2.0],
        series_inductances=[10e-6, 20e-6, 35e-6, 50e-6],
    )
    phis = [p.abs_phase_shift_rad for p in pts]
    rms = [p.i_rms_primary for p in pts]
    assert phis == sorted(phis) and rms == sorted(rms)
    # Every matched point is non-dominated for (min RMS, max |phi|).
    assert sweep.pareto_sps_designs(pts) == pts
    # With RMS alone only the smallest inductance survives.
    assert sweep.pareto_sps_designs(pts, objectives=("i_rms_primary",)) == [pts[0]]


def test_zvs_filter_and_mismatched_ratio():
    kwargs = dict(
        v1=800.0,
        v2=300.0,
        p=3000.0,
        switching_frequencies=[100e3],
        turns_ratios_np_ns=[2.0],
        series_inductances=[10e-6, 35e-6, 60e-6],
    )
    all_points = sweep.sweep_sps_designs(**kwargs)
    filtered = sweep.sweep_sps_designs(**kwargs, require_zvs_current_direction=True)
    assert len(filtered) < len(all_points)
    assert all(p.secondary_zvs_current_direction_ok for p in filtered)
    assert any(not p.secondary_zvs_current_direction_ok for p in all_points)


def test_reverse_power_and_invalid_inputs():
    pts = sweep.sweep_sps_designs(
        v1=800.0,
        v2=400.0,
        p=-10000.0,
        switching_frequencies=[100e3],
        turns_ratios_np_ns=[2.0],
        series_inductances=[35e-6],
    )
    assert pts[0].operating_point.phi_rad == pytest.approx(-math.radians(22.5))
    assert pts[0].power == pytest.approx(-10000.0)
    with pytest.raises(ValueError):
        sweep.sweep_sps_designs(
            v1=800.0,
            v2=400.0,
            p=0.0,
            switching_frequencies=[100e3],
            turns_ratios_np_ns=[2.0],
            series_inductances=[35e-6],
        )
    with pytest.raises(ValueError):
        sweep.pareto_sps_designs(pts, objectives=("cost",))
