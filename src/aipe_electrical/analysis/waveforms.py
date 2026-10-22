"""Exact metrics of piecewise-linear periodic waveforms and standard ripple formulas.

A waveform is given as breakpoints ``[(t0, x0), (t1, x1), ...]`` with
non-decreasing times; the signal is linear between consecutive points. Mean,
RMS and peak are evaluated exactly (no sampling) over the span ``t_last - t0``.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

__all__ = [
    "piecewise_linear_mean",
    "piecewise_linear_rms",
    "piecewise_linear_peak",
    "triangular_ripple_rms",
]

Breakpoints = Sequence[tuple[float, float]]


def _validated(points: Breakpoints) -> list[tuple[float, float]]:
    pts = [(float(t), float(x)) for t, x in points]
    if len(pts) < 2:
        raise ValueError("at least two breakpoints are required")
    for (t0, _), (t1, _) in zip(pts[:-1], pts[1:], strict=True):
        if t1 < t0:
            raise ValueError("breakpoint times must be non-decreasing")
    if pts[-1][0] - pts[0][0] <= 0:
        raise ValueError("the waveform span must be positive")
    return pts


def piecewise_linear_mean(points: Breakpoints) -> float:
    """Exact mean over the span: sum of trapezoid areas divided by the span."""
    pts = _validated(points)
    area = sum((x0 + x1) / 2 * (t1 - t0) for (t0, x0), (t1, x1) in zip(pts[:-1], pts[1:], strict=True))
    return area / (pts[-1][0] - pts[0][0])


def piecewise_linear_rms(points: Breakpoints) -> float:
    """Exact RMS over the span; a linear segment contributes ``dt (a^2 + a b + b^2) / 3``."""
    pts = _validated(points)
    integral = sum(
        (x0 * x0 + x0 * x1 + x1 * x1) / 3 * (t1 - t0) for (t0, x0), (t1, x1) in zip(pts[:-1], pts[1:], strict=True)
    )
    return math.sqrt(integral / (pts[-1][0] - pts[0][0]))


def piecewise_linear_peak(points: Breakpoints) -> float:
    """Largest absolute value; a piecewise-linear signal attains its extrema at breakpoints."""
    pts = _validated(points)
    return max(abs(x) for _, x in pts)


def triangular_ripple_rms(i_avg: float, delta_i_pp: float) -> float:
    """RMS of a DC value with a superimposed symmetric triangular ripple of peak-to-peak ``delta_i_pp``.

    ``I_rms = sqrt(I_avg^2 + delta_i_pp^2 / 12)`` (exact for a triangular waveform of any duty).
    """
    if delta_i_pp < 0:
        raise ValueError("delta_i_pp must be non-negative")
    return math.sqrt(i_avg * i_avg + delta_i_pp * delta_i_pp / 12.0)
