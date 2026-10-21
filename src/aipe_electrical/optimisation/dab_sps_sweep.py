"""Design-space sweep of the lossless SPS dual-active-bridge model (screening only).

For a required power the sweep evaluates every combination of switching frequency,
turns ratio ``N_p/N_s`` and total primary-referred series inductance with the exact
lossless model of :mod:`aipe_electrical.converters.dab_sps`: the phase shift that
delivers the power, the resulting RMS/peak series currents, the SPS power headroom
and the ZVS current-direction conditions. Combinations whose power exceeds the SPS
maximum are infeasible and skipped.

Only the lossless model is used. Conduction and switching losses, magnetics,
thermal behaviour and cost are NOT modelled, so this is an analytical screening of
the electrical operating point, not a converter optimiser.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from aipe_electrical.converters import dab_sps
from aipe_electrical.optimisation.pareto import Sense, pareto_front

__all__ = ["OBJECTIVES", "SpsSweepPoint", "pareto_sps_designs", "sweep_sps_designs"]


@dataclass(frozen=True)
class SpsSweepPoint:
    """One evaluated operating point of the sweep (SI units)."""

    operating_point: dab_sps.SpsOperatingPoint
    power: float
    max_power: float
    power_headroom: float
    i_rms_primary: float
    i_peak_primary: float
    i_rms_secondary: float
    i_peak_secondary: float
    primary_zvs_current_direction_ok: bool
    secondary_zvs_current_direction_ok: bool

    @property
    def abs_phase_shift_rad(self) -> float:
        return abs(self.operating_point.phi_rad)

    def to_dict(self) -> dict:
        op = self.operating_point
        return {
            "v1_V": op.v1,
            "v2_V": op.v2,
            "turns_ratio_np_ns": op.turns_ratio_np_ns,
            "turns_ratio_ns_np": op.turns_ratio_ns_np,
            "f_sw_Hz": op.f_sw,
            "l_series_total_H": op.l_series_total,
            "phi_rad": op.phi_rad,
            "phi_deg": op.phi_deg,
            "voltage_ratio_d": op.d,
            "power_W": self.power,
            "max_power_W": self.max_power,
            "power_headroom": self.power_headroom,
            "i_rms_primary_A": self.i_rms_primary,
            "i_peak_primary_A": self.i_peak_primary,
            "i_rms_secondary_A": self.i_rms_secondary,
            "i_peak_secondary_A": self.i_peak_secondary,
            "primary_zvs_current_direction_ok": self.primary_zvs_current_direction_ok,
            "secondary_zvs_current_direction_ok": self.secondary_zvs_current_direction_ok,
            "zvs_evidence": dab_sps.ZVS_EVIDENCE_LABEL,
        }


OBJECTIVES: dict[str, tuple[Callable[[SpsSweepPoint], float], Sense]] = {
    "i_rms_primary": (lambda pt: pt.i_rms_primary, "min"),
    "i_peak_primary": (lambda pt: pt.i_peak_primary, "min"),
    "abs_phase_shift": (lambda pt: pt.abs_phase_shift_rad, "max"),
    "power_headroom": (lambda pt: pt.power_headroom, "max"),
}
"""Named objectives: conduction stress (RMS), peak stress, control margin (|phi|) and SPS power headroom."""


def sweep_sps_designs(
    *,
    v1: float,
    v2: float,
    p: float,
    switching_frequencies: Iterable[float],
    turns_ratios_np_ns: Iterable[float],
    series_inductances: Iterable[float],
    require_zvs_current_direction: bool = False,
) -> list[SpsSweepPoint]:
    """Evaluate the lossless SPS model on the Cartesian product of the three parameter lists.

    ``p`` is the signed required power (W); infeasible combinations (``|p|`` above the SPS
    maximum) are skipped. With ``require_zvs_current_direction`` only points meeting both
    bridges' current-direction conditions are returned.
    """
    if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or p == 0:
        raise ValueError("p must be a finite non-zero power in W")
    points: list[SpsSweepPoint] = []
    for f_sw in switching_frequencies:
        for n in turns_ratios_np_ns:
            for l_total in series_inductances:
                p_max = dab_sps.max_power(v1=v1, v2=v2, turns_ratio_np_ns=n, f_sw=f_sw, l_series_total=l_total)
                if abs(p) > p_max:
                    continue
                phi = dab_sps.phase_shift_for_power(
                    v1=v1, v2=v2, turns_ratio_np_ns=n, f_sw=f_sw, l_series_total=l_total, p=p
                )
                op = dab_sps.SpsOperatingPoint(
                    v1=v1, v2=v2, turns_ratio_np_ns=n, f_sw=f_sw, l_series_total=l_total, phi_rad=phi
                )
                sw = dab_sps.switching_currents(op)
                if require_zvs_current_direction and not (
                    sw.primary_zvs_current_direction_ok and sw.secondary_zvs_current_direction_ok
                ):
                    continue
                i_rms = dab_sps.current_rms(op)
                i_pk = dab_sps.current_peak(op)
                points.append(
                    SpsSweepPoint(
                        operating_point=op,
                        power=dab_sps.power(op),
                        max_power=p_max,
                        power_headroom=p_max / abs(p),
                        i_rms_primary=i_rms,
                        i_peak_primary=i_pk,
                        i_rms_secondary=i_rms * n,
                        i_peak_secondary=i_pk * n,
                        primary_zvs_current_direction_ok=sw.primary_zvs_current_direction_ok,
                        secondary_zvs_current_direction_ok=sw.secondary_zvs_current_direction_ok,
                    )
                )
    return points


def pareto_sps_designs(
    points: Sequence[SpsSweepPoint], objectives: Sequence[str] = ("i_rms_primary", "abs_phase_shift")
) -> list[SpsSweepPoint]:
    """Non-dominated sweep points for the named objectives (see :data:`OBJECTIVES`)."""
    unknown = [name for name in objectives if name not in OBJECTIVES]
    if unknown:
        raise ValueError(f"unknown objectives {unknown}; choose from {sorted(OBJECTIVES)}")
    accessors = [OBJECTIVES[name][0] for name in objectives]
    senses = [OBJECTIVES[name][1] for name in objectives]
    return pareto_front(points, accessors, senses)
