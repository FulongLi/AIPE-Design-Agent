"""Lossless single-phase-shift (SPS) analysis of the dual active bridge (DAB).

Model (classical lossless SPS analysis, e.g. De Doncker et al., IEEE Trans. Ind.
Appl. 27(1), 1991)
---------------------------------------------------------------------------
* Two full bridges apply 50 % duty square waves ``v_ab = +/-V1`` (port 1,
  transformer primary) and ``v_cd = +/-V2`` (port 2, secondary). The secondary
  wave lags the primary by the phase shift ``phi`` (electrical radians of the
  switching period, ``|phi| <= pi/2``).
* The transformer is ideal with turns ratio ``n = N_p / N_s``
  (``turns_ratio_np_ns``). The primary-referred port-2 voltage is
  ``V2' = n V2`` and the voltage ratio is ``d = V2' / V1`` (``d = 1``: matched).
* ``L`` (``l_series_total``) is the TOTAL series inductance referred to the
  primary: external inductor(s) plus transformer leakage, secondary-side parts
  multiplied by ``n^2``. Use :func:`total_series_inductance_primary` to build it.
* Switches are ideal (no dead time, no conduction or switching loss), the DC
  ports are stiff and the magnetising current is neglected.

Closed forms::

    P(phi) = V1 V2' phi (pi - |phi|) sgn(phi) / (2 pi^2 f_sw L)
    P_max  = V1 V2' / (8 f_sw L)                 at |phi| = pi/2

The piecewise-linear series current is constructed exactly from the inductor
voltage in each interval and half-wave antisymmetry ``i(t + T/2) = -i(t)``;
RMS, mean and peak are exact integrals of the linear segments.

Sign conventions
----------------
* ``phi > 0``: the secondary lags, power flows from port 1 to port 2 (``P > 0``);
  ``phi < 0`` reverses the flow (``P < 0``). See :func:`power_flow_direction`.
* ``i_L`` is the series-inductor current flowing from bridge-1 node ``a`` towards
  the transformer primary; the secondary current is ``i_s = n i_L``.
* Time origin ``"rising_edge"``: ``t = 0`` at the ``-V1 -> +V1`` transition of
  ``v_ab``. ``"centre"``: ``t = 0`` at the centre of the positive ``v_ab``
  half-cycle (convention of the AIPE ngspice DAB generator).

Zero-voltage switching
----------------------
:func:`switching_currents` reports whether the series current has the direction
required for zero-voltage turn-on at each bridge's switching instant. This is a
NECESSARY current-direction condition of the lossless model only; it is not a
charge-based ZVS verification (which needs the device output capacitance, the
dead time and the magnetising current) and is never reported as "ZVS confirmed".

All quantities are SI (V, A, Hz, H, s, rad) unless a name carries a unit suffix.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Literal

from aipe_electrical.analysis.waveforms import piecewise_linear_mean, piecewise_linear_peak, piecewise_linear_rms

__all__ = [
    "MODEL_ID",
    "PHASE_SHIFT_LIMIT_RAD",
    "ZVS_EVIDENCE_LABEL",
    "Origin",
    "PowerFlowDirection",
    "SpsOperatingPoint",
    "SwitchingCurrents",
    "ZvsCurrentDirectionLimits",
    "analyse",
    "breakpoints",
    "current_at",
    "current_peak",
    "current_rms",
    "design_for_power",
    "matched_turns_ratio_np_ns",
    "max_power",
    "phase_shift_for_power",
    "phase_shift_limits",
    "power",
    "power_flow_direction",
    "power_from_waveform",
    "sample_waveforms",
    "series_inductance_for_power",
    "switching_currents",
    "total_series_inductance_primary",
    "zvs_phase_shift_limits",
]

MODEL_ID = "sps-lossless-ideal-transformer"
PHASE_SHIFT_LIMIT_RAD = math.pi / 2
ZVS_EVIDENCE_LABEL = (
    "necessary current-direction condition of the lossless SPS model at the switching instant; "
    "not a charge-based ZVS verification (needs Coss, dead time and magnetising current)"
)

Origin = Literal["rising_edge", "centre"]
PowerFlowDirection = Literal["port1_to_port2", "port2_to_port1", "none"]


# ----------------------------------------------------------------- validation


def _finite_number(name: str, value: float, unit: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number ({unit}), got {value!r}")
    return float(value)


def _positive(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number, got {value!r}")
    return float(value)


def _non_negative(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number, got {value!r}")
    return float(value)


def _phase_shift(phi_rad: float) -> float:
    phi = _finite_number("phi_rad", phi_rad, "radians")
    if abs(phi) > PHASE_SHIFT_LIMIT_RAD * (1 + 1e-12):
        raise ValueError(
            f"|phi_rad| must not exceed pi/2 (90 deg) for SPS power transfer, got {phi!r} rad "
            f"({math.degrees(phi):.3f} deg)"
        )
    return phi


def phase_shift_limits() -> tuple[float, float]:
    """Admissible SPS phase-shift range in radians: ``(-pi/2, +pi/2)`` inclusive."""
    return (-PHASE_SHIFT_LIMIT_RAD, PHASE_SHIFT_LIMIT_RAD)


def power_flow_direction(phi_rad: float) -> PowerFlowDirection:
    """Direction of average power for a signed phase shift (``phi > 0``: port 1 -> port 2)."""
    phi = _phase_shift(phi_rad)
    if phi > 0:
        return "port1_to_port2"
    if phi < 0:
        return "port2_to_port1"
    return "none"


# --------------------------------------------------------------- turns ratio


def matched_turns_ratio_np_ns(v1: float, v2: float) -> float:
    """Turns ratio ``N_p/N_s = V1/V2`` that makes the primary-referred port-2 voltage equal V1 (``d = 1``)."""
    return _positive("v1", v1) / _positive("v2", v2)


def total_series_inductance_primary(
    *,
    turns_ratio_np_ns: float,
    l_external_primary: float = 0.0,
    l_leakage_primary: float = 0.0,
    l_external_secondary: float = 0.0,
    l_leakage_secondary: float = 0.0,
) -> float:
    """Total series inductance referred to the primary (H).

    ``L_total = L_ext,p + L_lk,p + n^2 (L_ext,s + L_lk,s)`` with ``n = N_p/N_s``.
    This is the ``l_series_total`` quantity used by the SPS model; the transformer
    leakage alone is only a part of it unless no external inductor is used.
    """
    n = _positive("turns_ratio_np_ns", turns_ratio_np_ns)
    primary = _non_negative("l_external_primary", l_external_primary) + _non_negative(
        "l_leakage_primary", l_leakage_primary
    )
    secondary = _non_negative("l_external_secondary", l_external_secondary) + _non_negative(
        "l_leakage_secondary", l_leakage_secondary
    )
    total = primary + n * n * secondary
    if total <= 0:
        raise ValueError("the total series inductance must be positive; give at least one inductance component")
    return total


# ------------------------------------------------------------ operating point


@dataclass(frozen=True)
class SpsOperatingPoint:
    """One SPS operating point in SI units.

    Attributes
    ----------
    v1, v2 : port-1 and port-2 DC voltages (V), positive.
    turns_ratio_np_ns : transformer turns ratio ``N_p/N_s`` (dimensionless, positive).
    f_sw : switching frequency (Hz).
    l_series_total : total primary-referred series inductance (H), external plus leakage.
    phi_rad : signed phase shift (rad) of the secondary bridge relative to the primary, ``|phi| <= pi/2``.
    """

    v1: float
    v2: float
    turns_ratio_np_ns: float
    f_sw: float
    l_series_total: float
    phi_rad: float

    def __post_init__(self) -> None:
        for name in ("v1", "v2", "turns_ratio_np_ns", "f_sw", "l_series_total"):
            object.__setattr__(self, name, _positive(name, getattr(self, name)))
        object.__setattr__(self, "phi_rad", _phase_shift(self.phi_rad))

    @classmethod
    def from_degrees(
        cls,
        *,
        v1: float,
        v2: float,
        turns_ratio_np_ns: float,
        f_sw: float,
        l_series_total: float,
        phi_deg: float,
    ) -> SpsOperatingPoint:
        """Construct from a phase shift given in degrees."""
        return cls(
            v1, v2, turns_ratio_np_ns, f_sw, l_series_total, math.radians(_finite_number("phi_deg", phi_deg, "degrees"))
        )

    def with_phase_shift(self, phi_rad: float) -> SpsOperatingPoint:
        """Same circuit at another signed phase shift (rad)."""
        return replace(self, phi_rad=phi_rad)

    @property
    def turns_ratio_ns_np(self) -> float:
        """``N_s/N_p``, the reciprocal of :attr:`turns_ratio_np_ns`."""
        return 1.0 / self.turns_ratio_np_ns

    @property
    def phi_deg(self) -> float:
        return math.degrees(self.phi_rad)

    @property
    def period(self) -> float:
        return 1.0 / self.f_sw

    @property
    def v2_primary_referred(self) -> float:
        """``V2' = (N_p/N_s) V2``."""
        return self.turns_ratio_np_ns * self.v2

    @property
    def d(self) -> float:
        """Voltage conversion ratio ``d = V2'/V1`` (1 means matched)."""
        return self.v2_primary_referred / self.v1

    @property
    def t_phi(self) -> float:
        """Signed phase-shift time ``phi / (2 pi) * T`` (s)."""
        return self.phi_rad / (2 * math.pi) * self.period

    @property
    def power_flow(self) -> PowerFlowDirection:
        return power_flow_direction(self.phi_rad)


# -------------------------------------------------------------------- power


def power(op: SpsOperatingPoint) -> float:
    """Average transferred power (W); positive from port 1 to port 2, negative for reverse flow."""
    phi = op.phi_rad
    # The sign of phi carries the direction; (pi - |phi|) keeps the magnitude symmetric.
    return op.v1 * op.v2_primary_referred * phi * (math.pi - abs(phi)) / (2 * math.pi**2 * op.f_sw * op.l_series_total)


def max_power(*, v1: float, v2: float, turns_ratio_np_ns: float, f_sw: float, l_series_total: float) -> float:
    """Maximum SPS power magnitude ``V1 V2' / (8 f_sw L)`` reached at ``|phi| = pi/2`` (W)."""
    v1 = _positive("v1", v1)
    v2p = _positive("turns_ratio_np_ns", turns_ratio_np_ns) * _positive("v2", v2)
    return v1 * v2p / (8 * _positive("f_sw", f_sw) * _positive("l_series_total", l_series_total))


def phase_shift_for_power(
    *, v1: float, v2: float, turns_ratio_np_ns: float, f_sw: float, l_series_total: float, p: float
) -> float:
    """Signed phase shift (rad, ``|phi| <= pi/2``) that transfers the power ``p`` (W, sign = direction).

    Solves ``phi (pi - phi) = 2 pi^2 f_sw L |p| / (V1 V2')`` for the smaller root and
    applies the sign of ``p``. Raises ``ValueError`` when ``|p|`` exceeds :func:`max_power`.
    """
    p = _finite_number("p", p, "W")
    pmax = max_power(v1=v1, v2=v2, turns_ratio_np_ns=turns_ratio_np_ns, f_sw=f_sw, l_series_total=l_series_total)
    if abs(p) > pmax * (1 + 1e-12):
        raise ValueError(f"requested power {p:.6g} W exceeds the SPS maximum {pmax:.6g} W for this inductance")
    if p == 0:
        return 0.0
    c = 2 * math.pi**2 * f_sw * l_series_total * abs(p) / (v1 * turns_ratio_np_ns * v2)
    disc = max(math.pi**2 - 4 * c, 0.0)
    phi = (math.pi - math.sqrt(disc)) / 2
    return math.copysign(phi, p)


def series_inductance_for_power(
    *, v1: float, v2: float, turns_ratio_np_ns: float, f_sw: float, phi_rad: float, p: float
) -> float:
    """Total primary-referred series inductance (H) that transfers ``p`` at ``phi_rad``.

    ``p`` and ``phi_rad`` must be non-zero and of the same sign (same power-flow direction).
    """
    phi = _phase_shift(phi_rad)
    p = _finite_number("p", p, "W")
    if p == 0 or phi == 0 or math.copysign(1.0, phi) != math.copysign(1.0, p):
        raise ValueError("phase shift and power must be non-zero and have the same sign (same flow direction)")
    v1 = _positive("v1", v1)
    v2p = _positive("turns_ratio_np_ns", turns_ratio_np_ns) * _positive("v2", v2)
    return v1 * v2p * abs(phi) * (math.pi - abs(phi)) / (2 * math.pi**2 * _positive("f_sw", f_sw) * abs(p))


def design_for_power(
    *,
    v1: float,
    v2: float,
    p: float,
    f_sw: float,
    phi_rad: float,
    turns_ratio_np_ns: float | None = None,
) -> SpsOperatingPoint:
    """Operating point whose total series inductance transfers ``p`` at ``phi_rad``.

    Replaces the historical ``pea.tools.calculator.dab_design``: when ``turns_ratio_np_ns``
    is omitted the voltage-matching ratio ``N_p/N_s = V1/V2`` (``d = 1``) is used, and the
    sized quantity is the TOTAL primary-referred series inductance (formerly mislabelled
    ``leakage_inductance_uH``). Use :func:`analyse` on the result for currents and the
    ZVS current-direction conditions.
    """
    n = (
        matched_turns_ratio_np_ns(v1, v2)
        if turns_ratio_np_ns is None
        else _positive("turns_ratio_np_ns", turns_ratio_np_ns)
    )
    l_total = series_inductance_for_power(v1=v1, v2=v2, turns_ratio_np_ns=n, f_sw=f_sw, phi_rad=phi_rad, p=p)
    return SpsOperatingPoint(v1=v1, v2=v2, turns_ratio_np_ns=n, f_sw=f_sw, l_series_total=l_total, phi_rad=phi_rad)


# ---------------------------------------------------------------- waveforms


def _v_cd_referred(op: SpsOperatingPoint, t: float) -> float:
    """Primary-referred secondary bridge voltage at time t (rising-edge origin)."""
    T = op.period
    return op.v2_primary_referred if ((t - op.t_phi) % T) < T / 2 else -op.v2_primary_referred


def _v_ab(op: SpsOperatingPoint, t: float) -> float:
    T = op.period
    return op.v1 if (t % T) < T / 2 else -op.v1


def breakpoints(op: SpsOperatingPoint) -> list[tuple[float, float]]:
    """Exact piecewise-linear series current over one period, rising-edge origin.

    Returns ``[(t0, i0), (t1, i1), ...]`` with ``t0 = 0`` and the last point at
    ``t = T``; the current is linear between consecutive points.
    """
    T = op.period
    half = T / 2
    inner = op.t_phi % half  # secondary switching instant inside the first half period
    bounds = sorted({0.0, inner, half})
    segments: list[tuple[float, float, float]] = []
    for lo, hi in zip(bounds[:-1], bounds[1:], strict=True):
        if hi - lo <= 0:
            continue
        mid = (lo + hi) / 2
        slope = (_v_ab(op, mid) - _v_cd_referred(op, mid)) / op.l_series_total
        segments.append((lo, hi, slope))
    delta_half = sum(slope * (hi - lo) for lo, hi, slope in segments)
    i0 = -delta_half / 2  # half-wave antisymmetry: i(T/2) = -i(0)
    points = [(0.0, i0)]
    current = i0
    for lo, hi, slope in segments:
        current += slope * (hi - lo)
        points.append((hi, current))
    for lo, hi, slope in segments:  # second half: mirror image
        current -= slope * (hi - lo)
        points.append((hi + half, current))
    return points


def current_at(op: SpsOperatingPoint, t: float, origin: Origin = "rising_edge") -> float:
    """Series inductor current (A) at time ``t`` (s), periodic extension, for the chosen time origin."""
    if origin not in ("rising_edge", "centre"):
        raise ValueError("origin must be 'rising_edge' or 'centre'")
    T = op.period
    if origin == "centre":
        t = t + T / 4
    tau = t % T
    pts = breakpoints(op)
    for (t0, i0), (t1, i1) in zip(pts[:-1], pts[1:], strict=True):
        if t0 - 1e-18 <= tau <= t1 + 1e-18:
            if t1 == t0:
                return i1
            return i0 + (i1 - i0) * (tau - t0) / (t1 - t0)
    return pts[-1][1]


def current_rms(op: SpsOperatingPoint) -> float:
    """Exact RMS of the primary-side series current (A)."""
    return piecewise_linear_rms(breakpoints(op))


def current_peak(op: SpsOperatingPoint) -> float:
    """Exact peak magnitude of the primary-side series current (A)."""
    return piecewise_linear_peak(breakpoints(op))


def power_from_waveform(op: SpsOperatingPoint) -> float:
    """Average of ``v_ab * i_L`` over one period (W); equals :func:`power` and serves as a self-check."""
    half = op.period / 2
    first_half = [(t, i) for t, i in breakpoints(op) if t <= half + 1e-18]
    # mean(v_ab i_L) = V1 * mean of i_L over the positive v_ab half (antisymmetry supplies the other half)
    return op.v1 * piecewise_linear_mean(first_half)


# ---------------------------------------------------------- switching / ZVS


@dataclass(frozen=True)
class SwitchingCurrents:
    """Series current at the two bridge switching instants and the ZVS current-direction conditions.

    ``primary_switching_current``: ``i_L`` at the rising edge of ``v_ab`` (A, primary side).
    ``secondary_switching_current_primary_referred``: ``i_L`` at the rising edge of ``v_cd`` (A, primary side).
    ``secondary_switching_current``: ``n i_L`` at the rising edge of ``v_cd`` (A, secondary side).
    ``primary_zvs_current_direction_ok``: ``i_L < 0`` at the primary edge (current into node ``a``).
    ``secondary_zvs_current_direction_ok``: ``n i_L > 0`` at the secondary edge (current into node ``c``).
    ``evidence``: label stating that these are necessary conditions, not a ZVS confirmation.
    """

    primary_switching_current: float
    secondary_switching_current_primary_referred: float
    secondary_switching_current: float
    primary_zvs_current_direction_ok: bool
    secondary_zvs_current_direction_ok: bool
    evidence: str = ZVS_EVIDENCE_LABEL

    def to_dict(self) -> dict:
        return {
            "primary_switching_current_A": self.primary_switching_current,
            "secondary_switching_current_primary_referred_A": self.secondary_switching_current_primary_referred,
            "secondary_switching_current_A": self.secondary_switching_current,
            "primary_zvs_current_direction_ok": self.primary_zvs_current_direction_ok,
            "secondary_zvs_current_direction_ok": self.secondary_zvs_current_direction_ok,
            "evidence": self.evidence,
        }


def switching_currents(op: SpsOperatingPoint) -> SwitchingCurrents:
    """Series current at the bridge switching instants and the ZVS current-direction conditions.

    The primary bridge switches at the rising edge of ``v_ab`` (``t = 0``); zero-voltage
    turn-on of the incoming primary devices requires ``i_L(0) < 0`` (current into node ``a``).
    The secondary bridge switches at ``t = t_phi``; its incoming devices need ``n i_L(t_phi) > 0``.
    Both rules hold for either power-flow direction. They are necessary current-direction
    conditions of the lossless model, not a complete charge-based ZVS analysis.
    """
    i_pri = current_at(op, 0.0)
    i_sec = current_at(op, op.t_phi)
    return SwitchingCurrents(
        primary_switching_current=i_pri,
        secondary_switching_current_primary_referred=i_sec,
        secondary_switching_current=i_sec * op.turns_ratio_np_ns,
        primary_zvs_current_direction_ok=i_pri < 0,
        secondary_zvs_current_direction_ok=i_sec > 0,
    )


@dataclass(frozen=True)
class ZvsCurrentDirectionLimits:
    """Minimum ``|phi|`` (rad) for the current-direction conditions as a function of ``d = V2'/V1``.

    For ``d <= 1`` the primary bridge always meets its condition and the secondary needs
    ``|phi| > pi (1 - d) / 2``; for ``d >= 1`` the roles swap and the primary needs
    ``|phi| > pi (1 - 1/d) / 2``. Valid for both power-flow directions.
    """

    d: float
    primary_min_abs_phi_rad: float
    secondary_min_abs_phi_rad: float
    both_bridges_min_abs_phi_rad: float
    evidence: str = ZVS_EVIDENCE_LABEL

    def to_dict(self) -> dict:
        return {
            "d": self.d,
            "primary_min_abs_phi_rad": self.primary_min_abs_phi_rad,
            "secondary_min_abs_phi_rad": self.secondary_min_abs_phi_rad,
            "both_bridges_min_abs_phi_rad": self.both_bridges_min_abs_phi_rad,
            "evidence": self.evidence,
        }


def zvs_phase_shift_limits(op: SpsOperatingPoint) -> ZvsCurrentDirectionLimits:
    """Classical SPS current-direction boundaries (minimum ``|phi|``) for the operating point's ``d``."""
    d = op.d
    sec_limit = math.pi * (1 - d) / 2 if d < 1 else 0.0
    pri_limit = math.pi * (1 - 1 / d) / 2 if d > 1 else 0.0
    return ZvsCurrentDirectionLimits(
        d=d,
        primary_min_abs_phi_rad=pri_limit,
        secondary_min_abs_phi_rad=sec_limit,
        both_bridges_min_abs_phi_rad=max(pri_limit, sec_limit),
    )


# ------------------------------------------------------------------ summary


def _q(value: float, unit: str) -> dict:
    return {"value": value, "unit": unit}


def analyse(op: SpsOperatingPoint) -> dict:
    """Complete JSON-ready description of the operating point (quantities as ``{"value", "unit"}``)."""
    from aipe_electrical import __version__

    p = power(op)
    p_wave = power_from_waveform(op)
    i_rms = current_rms(op)
    i_pk = current_peak(op)
    sw = switching_currents(op)
    limits = zvs_phase_shift_limits(op)
    p_max = max_power(
        v1=op.v1, v2=op.v2, turns_ratio_np_ns=op.turns_ratio_np_ns, f_sw=op.f_sw, l_series_total=op.l_series_total
    )
    return {
        "model": MODEL_ID,
        "model_version": __version__,
        "inputs": {
            "v1": _q(op.v1, "V"),
            "v2": _q(op.v2, "V"),
            "turns_ratio_np_ns": _q(op.turns_ratio_np_ns, "1"),
            "turns_ratio_ns_np": _q(op.turns_ratio_ns_np, "1"),
            "switching_frequency": _q(op.f_sw, "Hz"),
            "series_inductance_total_primary_referred": _q(op.l_series_total, "H"),
            "phase_shift": _q(op.phi_rad, "rad"),
            "phase_shift_deg": _q(op.phi_deg, "deg"),
        },
        "derived": {
            "v2_primary_referred": _q(op.v2_primary_referred, "V"),
            "voltage_ratio_d": _q(op.d, "1"),
            "period": _q(op.period, "s"),
            "phase_shift_time": _q(op.t_phi, "s"),
            "power": _q(p, "W"),
            "power_flow_direction": op.power_flow,
            "power_from_waveform_integral": _q(p_wave, "W"),
            "max_power_sps": _q(p_max, "W"),
            "dc_current_port1": _q(p / op.v1, "A"),
            "dc_current_port2": _q(p / op.v2, "A"),
            "series_current_rms_primary": _q(i_rms, "A"),
            "series_current_peak_primary": _q(i_pk, "A"),
            "secondary_current_rms": _q(i_rms * op.turns_ratio_np_ns, "A"),
            "secondary_current_peak": _q(i_pk * op.turns_ratio_np_ns, "A"),
            "primary_switching_current": _q(sw.primary_switching_current, "A"),
            "secondary_switching_current": _q(sw.secondary_switching_current, "A"),
            "secondary_switching_current_primary_referred": _q(sw.secondary_switching_current_primary_referred, "A"),
        },
        "zvs_current_direction_conditions": {
            "primary": sw.primary_zvs_current_direction_ok,
            "secondary": sw.secondary_zvs_current_direction_ok,
            "evidence": ZVS_EVIDENCE_LABEL,
            "limits": limits.to_dict(),
        },
        "assumptions": [
            "Ideal switches, zero dead time, stiff DC ports, ideal transformer, magnetising current neglected.",
            "All series inductance (external plus leakage) lumped and referred to the primary "
            "with (N_p/N_s)^2 scaling.",
            "Currents are exact piecewise-linear results of the lossless model, not simulated or measured values.",
            "ZVS entries are necessary current-direction conditions only, not a charge-based ZVS confirmation.",
        ],
        "waveform_breakpoints_rising_edge_origin": [{"t": t, "i_L": i} for t, i in breakpoints(op)],
    }


def sample_waveforms(op: SpsOperatingPoint, samples_per_period: int = 400, origin: Origin = "rising_edge") -> dict:
    """Uniformly sampled ``v_ab``, ``n v_cd``, ``v_L`` and ``i_L`` over one period for comparison or plotting."""
    if origin not in ("rising_edge", "centre"):
        raise ValueError("origin must be 'rising_edge' or 'centre'")
    if isinstance(samples_per_period, bool) or not isinstance(samples_per_period, int) or samples_per_period < 2:
        raise ValueError("samples_per_period must be an integer >= 2")
    T = op.period
    shift = T / 4 if origin == "centre" else 0.0
    t = [k * T / samples_per_period for k in range(samples_per_period + 1)]
    v_ab = [_v_ab(op, tk + shift) for tk in t]
    v_cd = [_v_cd_referred(op, tk + shift) for tk in t]
    return {
        "time_s": t,
        "v_ab_V": v_ab,
        "v_cd_referred_V": v_cd,
        "v_L_V": [a - b for a, b in zip(v_ab, v_cd, strict=True)],
        "i_L_A": [current_at(op, tk, origin) for tk in t],
        "origin": origin,
    }
