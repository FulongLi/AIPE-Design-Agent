"""Analytical single-phase-shift (SPS) model of the dual active bridge (DAB).

Model assumptions (classical lossless SPS analysis)
---------------------------------------------------
* Two full bridges produce 50 % duty square waves ``v_ab = +/-V1`` and
  ``v_cd = +/-V2``; the secondary wave lags the primary by the phase shift
  ``phi`` (electrical radians of the switching period).
* The transformer is ideal with turns ratio ``n = N_p / N_s``; the complete
  series inductance ``L`` (external inductor plus leakage) is referred to the
  primary. ``V2' = n V2`` is the primary-referred port-2 voltage, ``d = V2'/V1``.
* Switches are ideal (no dead time, no conduction or switching loss), DC
  voltages are stiff and the magnetising current is neglected.

Sign conventions
----------------
* ``phi > 0``: secondary lags, power flows from port 1 to port 2 (``P > 0``).
* ``i_L`` is the series inductor current flowing from bridge-1 node ``a``
  towards the transformer.
* Time origin for ``current_at`` is selectable: ``"rising_edge"`` places
  ``t = 0`` at the ``-V1 -> +V1`` transition of ``v_ab``; ``"centre"`` places it
  at the centre of the positive ``v_ab`` half-cycle (the convention used by the
  AIPE ngspice DAB generator).

Reference formulas (any textbook on DAB converters, e.g. De Doncker et al.,
IEEE Trans. Ind. Appl. 27(1), 1991):

    P(phi) = V1 V2' phi (pi - |phi|) sgn(phi) / (2 pi^2 f_sw L)
    P_max  = V1 V2' / (8 f_sw L)              at |phi| = pi/2

The piecewise-linear current waveform is constructed exactly from the inductor
voltage in each interval and half-wave antisymmetry ``i(t + T/2) = -i(t)``; RMS
and mean values are exact integrals of the piecewise-linear segments.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Origin = Literal["rising_edge", "centre"]


@dataclass(frozen=True)
class SpsOperatingPoint:
    """One SPS operating point in SI units."""

    v1: float  # V
    v2: float  # V
    n_ratio: float  # N_p / N_s
    f_sw: float  # Hz
    l_total: float  # H, primary-referred total series inductance
    phi_rad: float  # rad, signed

    def __post_init__(self) -> None:
        for name in ("v1", "v2", "n_ratio", "f_sw", "l_total"):
            value = getattr(self, name)
            if not (isinstance(value, (int, float)) and math.isfinite(value) and value > 0):
                raise ValueError(f"{name} must be a finite positive number")
        if not (math.isfinite(self.phi_rad) and -math.pi / 2 <= self.phi_rad <= math.pi / 2):
            raise ValueError("phi_rad must lie within [-pi/2, pi/2]")

    @property
    def period(self) -> float:
        return 1.0 / self.f_sw

    @property
    def v2_referred(self) -> float:
        return self.n_ratio * self.v2

    @property
    def d(self) -> float:
        """Voltage conversion ratio V2'/V1 (1 means matched)."""
        return self.v2_referred / self.v1

    @property
    def t_phi(self) -> float:
        return self.phi_rad / (2 * math.pi) * self.period


# --------------------------------------------------------------------------- power

def power(v1: float, v2: float, n_ratio: float, f_sw: float, l_total: float, phi_rad: float) -> float:
    """Transferred power in W (positive from port 1 to port 2)."""
    if l_total <= 0 or f_sw <= 0:
        raise ValueError("inductance and frequency must be positive")
    # The sign of phi carries the power direction; (pi - |phi|) keeps the magnitude symmetric.
    return v1 * n_ratio * v2 * phi_rad * (math.pi - abs(phi_rad)) / (2 * math.pi ** 2 * f_sw * l_total)


def max_power(v1: float, v2: float, n_ratio: float, f_sw: float, l_total: float) -> float:
    """Maximum SPS power at |phi| = pi/2."""
    return v1 * n_ratio * v2 / (8 * f_sw * l_total)


def phase_shift_for_power(v1: float, v2: float, n_ratio: float, f_sw: float, l_total: float, p: float) -> float:
    """Signed phase shift (rad, |phi| <= pi/2) delivering power ``p``.

    Solves ``phi (pi - phi) = 2 pi^2 f L |p| / (V1 V2')`` for the smaller root.
    """
    pmax = max_power(v1, v2, n_ratio, f_sw, l_total)
    if abs(p) > pmax * (1 + 1e-12):
        raise ValueError(f"requested power {p:.6g} W exceeds SPS maximum {pmax:.6g} W")
    c = 2 * math.pi ** 2 * f_sw * l_total * abs(p) / (v1 * n_ratio * v2)
    disc = max(math.pi ** 2 - 4 * c, 0.0)
    phi = (math.pi - math.sqrt(disc)) / 2
    return math.copysign(phi, p) if p != 0 else 0.0


def inductance_for_power(v1: float, v2: float, n_ratio: float, f_sw: float, phi_rad: float, p: float) -> float:
    """Primary-referred series inductance (H) that transfers ``p`` at ``phi_rad``."""
    if p <= 0 or phi_rad <= 0:
        raise ValueError("power and phase shift must be positive for inductance sizing")
    return v1 * n_ratio * v2 * phi_rad * (math.pi - phi_rad) / (2 * math.pi ** 2 * f_sw * p)


# ---------------------------------------------------------------- current waveform

def _v_cd_referred(op: SpsOperatingPoint, t: float) -> float:
    """Primary-referred secondary bridge voltage at time t (rising-edge origin)."""
    T = op.period
    return op.v2_referred if ((t - op.t_phi) % T) < T / 2 else -op.v2_referred


def _v_ab(op: SpsOperatingPoint, t: float) -> float:
    T = op.period
    return op.v1 if (t % T) < T / 2 else -op.v1


def breakpoints(op: SpsOperatingPoint) -> list[tuple[float, float]]:
    """Exact piecewise-linear current over one period, rising-edge origin.

    Returns ``[(t0, i0), (t1, i1), ...]`` with ``t0 = 0`` and the last point at
    ``t = T``; the current is linear between consecutive points.
    """
    T = op.period
    half = T / 2
    # Interval boundaries inside the first half period.
    inner = op.t_phi % half
    bounds = sorted({0.0, inner, half})
    # Slopes in each sub-interval of the first half period.
    seg = []
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        if hi - lo <= 0:
            continue
        mid = (lo + hi) / 2
        slope = (_v_ab(op, mid) - _v_cd_referred(op, mid)) / op.l_total
        seg.append((lo, hi, slope))
    delta_half = sum(slope * (hi - lo) for lo, hi, slope in seg)
    i0 = -delta_half / 2  # half-wave antisymmetry: i(T/2) = -i(0)
    points = [(0.0, i0)]
    current = i0
    for lo, hi, slope in seg:
        current += slope * (hi - lo)
        points.append((hi, current))
    # Second half: mirror image.
    for lo, hi, slope in seg:
        current -= slope * (hi - lo)
        points.append((hi + half, current))
    return points


def current_at(op: SpsOperatingPoint, t: float, origin: Origin = "rising_edge") -> float:
    """Series inductor current at time ``t`` (periodic extension)."""
    T = op.period
    if origin == "centre":
        t = t + T / 4
    tau = t % T
    pts = breakpoints(op)
    for (t0, i0), (t1, i1) in zip(pts[:-1], pts[1:]):
        if t0 - 1e-18 <= tau <= t1 + 1e-18:
            if t1 == t0:
                return i1
            return i0 + (i1 - i0) * (tau - t0) / (t1 - t0)
    return pts[-1][1]


def _segment_integrals(op: SpsOperatingPoint) -> tuple[float, float, float]:
    """Return (integral of i over the positive v_ab half, integral of i^2 over T, max |i|)."""
    pts = breakpoints(op)
    half = op.period / 2
    int_pos = 0.0
    int_sq = 0.0
    peak = 0.0
    for (t0, i0), (t1, i1) in zip(pts[:-1], pts[1:]):
        dt = t1 - t0
        if dt <= 0:
            continue
        int_sq += (i0 * i0 + i0 * i1 + i1 * i1) / 3 * dt
        if t1 <= half + 1e-18:
            int_pos += (i0 + i1) / 2 * dt
        peak = max(peak, abs(i0), abs(i1))
    return int_pos, int_sq, peak


def current_rms(op: SpsOperatingPoint) -> float:
    _, int_sq, _ = _segment_integrals(op)
    return math.sqrt(int_sq / op.period)


def current_peak(op: SpsOperatingPoint) -> float:
    return _segment_integrals(op)[2]


def power_from_waveform(op: SpsOperatingPoint) -> float:
    """Power computed as the average of v_ab * i_L; equals the closed form."""
    int_pos, _, _ = _segment_integrals(op)
    return op.v1 * 2 * int_pos / op.period


# ------------------------------------------------------------- switching / ZVS

def switching_currents(op: SpsOperatingPoint) -> dict:
    """Inductor current at the bridge switching instants and the ZVS current conditions.

    Primary bridge switches at the rising edge of ``v_ab`` (``t = 0``); zero-
    voltage turn-on of the incoming primary devices requires ``i_L(0) < 0`` (the
    current must flow into node ``a``, discharging the incoming high-side
    output capacitance). The secondary bridge switches at ``t = t_phi``; its
    incoming devices need ``n i_L(t_phi) > 0``. Both rules hold for either
    power-flow direction. These are necessary current-direction conditions of
    the lossless model, not a complete charge-based ZVS analysis.
    """
    i_pri = current_at(op, 0.0)
    i_sec = current_at(op, op.t_phi)
    # Physical current-direction rules, independent of the power-flow direction:
    # the incoming primary high-side device needs current flowing into node a
    # (i_L < 0) and the incoming secondary high-side device needs current flowing
    # into node c (i_s = n i_L > 0) at the respective rising edge.
    primary_ok = i_pri < 0
    secondary_ok = i_sec > 0
    return {
        "primary_switching_current_A": i_pri,
        "secondary_switching_current_primary_referred_A": i_sec,
        "secondary_switching_current_A": i_sec * op.n_ratio,
        "primary_zvs_current_condition": primary_ok,
        "secondary_zvs_current_condition": secondary_ok,
        "note": "current-direction conditions of the lossless SPS model; charge-based ZVS needs Coss and dead time",
    }


def zvs_phase_shift_limits(op: SpsOperatingPoint) -> dict:
    """Classical SPS ZVS boundaries as a function of d = V2'/V1.

    For d <= 1 the primary bridge always meets the current condition and the
    secondary requires ``phi > pi (1 - d) / 2``; for d >= 1 the roles swap and
    the primary requires ``phi > pi (1 - 1/d) / 2``. Returned in radians for
    forward power flow.
    """
    d = op.d
    sec_limit = math.pi * (1 - d) / 2 if d < 1 else 0.0
    pri_limit = math.pi * (1 - 1 / d) / 2 if d > 1 else 0.0
    return {"d": d, "primary_min_phi_rad": pri_limit, "secondary_min_phi_rad": sec_limit,
            "both_bridges_min_phi_rad": max(pri_limit, sec_limit)}


# ------------------------------------------------------------------- summary

def analyse(op: SpsOperatingPoint) -> dict:
    """Complete analytical description of the operating point with SI units."""
    p = power(op.v1, op.v2, op.n_ratio, op.f_sw, op.l_total, op.phi_rad)
    p_wave = power_from_waveform(op)
    i_rms = current_rms(op)
    i_pk = current_peak(op)
    sw = switching_currents(op)
    return {
        "model": "sps-lossless-ideal-transformer",
        "inputs": {
            "v1": {"value": op.v1, "unit": "V"}, "v2": {"value": op.v2, "unit": "V"},
            "turns_ratio_np_ns": {"value": op.n_ratio, "unit": "1"},
            "switching_frequency": {"value": op.f_sw, "unit": "Hz"},
            "series_inductance_primary_referred": {"value": op.l_total, "unit": "H"},
            "phase_shift": {"value": op.phi_rad, "unit": "rad"},
        },
        "derived": {
            "v2_primary_referred": {"value": op.v2_referred, "unit": "V"},
            "voltage_ratio_d": {"value": op.d, "unit": "1"},
            "period": {"value": op.period, "unit": "s"},
            "phase_shift_time": {"value": op.t_phi, "unit": "s"},
            "power": {"value": p, "unit": "W"},
            "power_from_waveform_integral": {"value": p_wave, "unit": "W"},
            "max_power_sps": {"value": max_power(op.v1, op.v2, op.n_ratio, op.f_sw, op.l_total), "unit": "W"},
            "dc_current_port1": {"value": p / op.v1, "unit": "A"},
            "dc_current_port2": {"value": p / op.v2, "unit": "A"},
            "series_current_rms_primary": {"value": i_rms, "unit": "A"},
            "series_current_peak_primary": {"value": i_pk, "unit": "A"},
            "secondary_current_rms": {"value": i_rms * op.n_ratio, "unit": "A"},
            "secondary_current_peak": {"value": i_pk * op.n_ratio, "unit": "A"},
            "primary_switching_current": {"value": sw["primary_switching_current_A"], "unit": "A"},
            "secondary_switching_current": {"value": sw["secondary_switching_current_A"], "unit": "A"},
        },
        "zvs_current_conditions": {
            "primary": sw["primary_zvs_current_condition"],
            "secondary": sw["secondary_zvs_current_condition"],
            "limits": zvs_phase_shift_limits(op),
        },
        "assumptions": [
            "Ideal switches, zero dead time, stiff DC ports, ideal transformer, magnetising current neglected.",
            "All series inductance (external plus leakage) lumped and referred to the primary.",
            "Currents are exact piecewise-linear results of the lossless model, not simulated or measured values.",
        ],
        "waveform_breakpoints_rising_edge_origin": [{"t": t, "i_L": i} for t, i in breakpoints(op)],
    }


def sample_waveforms(op: SpsOperatingPoint, samples_per_period: int = 400, origin: Origin = "rising_edge") -> dict:
    """Uniformly sampled v_ab, n*v_cd, v_L and i_L over one period for comparison or plotting."""
    T = op.period
    shift = T / 4 if origin == "centre" else 0.0
    t = [k * T / samples_per_period for k in range(samples_per_period + 1)]
    v_ab = [_v_ab(op, tk + shift) for tk in t]
    v_cd = [_v_cd_referred(op, tk + shift) for tk in t]
    return {"time_s": t, "v_ab_V": v_ab, "v_cd_referred_V": v_cd,
            "v_L_V": [a - b for a, b in zip(v_ab, v_cd)],
            "i_L_A": [current_at(op, tk, origin) for tk in t], "origin": origin}
