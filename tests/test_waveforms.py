"""Exact piecewise-linear waveform metrics (aipe_electrical.analysis.waveforms)."""

import math

import pytest

from aipe_electrical.analysis import waveforms as w


def test_constant_waveform():
    pts = [(0.0, 3.0), (2.0, 3.0)]
    assert w.piecewise_linear_mean(pts) == pytest.approx(3.0)
    assert w.piecewise_linear_rms(pts) == pytest.approx(3.0)
    assert w.piecewise_linear_peak(pts) == pytest.approx(3.0)


def test_symmetric_triangle_has_zero_mean_and_rms_over_sqrt3():
    pts = [(0.0, -1.0), (0.5, 1.0), (1.0, -1.0)]
    assert w.piecewise_linear_mean(pts) == pytest.approx(0.0, abs=1e-15)
    assert w.piecewise_linear_rms(pts) == pytest.approx(1 / math.sqrt(3), rel=1e-12)
    assert w.piecewise_linear_peak(pts) == 1.0


def test_sawtooth_mean_and_rms():
    pts = [(0.0, 0.0), (1.0, 2.0)]
    assert w.piecewise_linear_mean(pts) == pytest.approx(1.0)
    assert w.piecewise_linear_rms(pts) == pytest.approx(2 / math.sqrt(3), rel=1e-12)


def test_zero_length_segments_are_tolerated():
    pts = [(0.0, 1.0), (0.0, 1.0), (1.0, 1.0)]
    assert w.piecewise_linear_rms(pts) == pytest.approx(1.0)


@pytest.mark.parametrize("pts", [[], [(0.0, 1.0)], [(0.0, 1.0), (0.0, 2.0)], [(1.0, 0.0), (0.0, 1.0)]])
def test_invalid_breakpoints_rejected(pts):
    with pytest.raises(ValueError):
        w.piecewise_linear_rms(pts)


def test_triangular_ripple_rms():
    assert w.triangular_ripple_rms(2.0, 0.6) == pytest.approx(math.sqrt(4.03), rel=1e-12)
    assert w.triangular_ripple_rms(0.0, 2.0) == pytest.approx(1 / math.sqrt(3), rel=1e-12)
    assert w.triangular_ripple_rms(5.0, 0.0) == 5.0
    with pytest.raises(ValueError):
        w.triangular_ripple_rms(1.0, -0.1)
