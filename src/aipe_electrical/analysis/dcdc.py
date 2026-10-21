"""Continuous-conduction-mode (CCM) sizing formulas for basic non-isolated DC-DC converters (SI units).

Model: ideal lossless converter in steady-state CCM with the small-ripple approximation.
The duty cycle follows from inductor volt-second balance, each inductance from the chosen
peak-to-peak inductor-current ripple, each capacitance from the chosen peak-to-peak voltage
ripple with ESR/ESL neglected. These are exact first-pass sizing values for that model; they
are not component selections and include no loss, saturation or stability information.

Migrated from the historical ``pea.tools.calculator`` buck/boost/buck-boost/SEPIC/Cuk
functions with the units made SI and the inductor ripple always defined relative to the
inductor's own average current (the legacy buck-boost referred it to the input current).
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

from aipe_electrical.analysis.waveforms import triangular_ripple_rms

__all__ = [
    "CcmCapacitor",
    "CcmDesign",
    "CcmInductor",
    "boost_ccm",
    "buck_boost_ccm",
    "buck_ccm",
    "cuk_ccm",
    "sepic_ccm",
]

SMALL_RIPPLE = "Small-ripple CCM steady state, ideal lossless components, ESR/ESL neglected."


def _positive(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number, got {value!r}")
    return float(value)


def _fraction(name: str, value: float) -> float:
    value = _positive(name, value)
    if value >= 1:
        raise ValueError(f"{name} must be smaller than 1 (peak-to-peak ripple as a fraction of the DC value)")
    return value


@dataclass(frozen=True)
class CcmInductor:
    """One inductor: value (H), average current (A), peak-to-peak ripple (A), peak and RMS current (A)."""

    name: str
    inductance: float
    current_avg: float
    current_ripple_pp: float
    current_peak: float
    current_rms: float


@dataclass(frozen=True)
class CcmCapacitor:
    """One capacitor: value (F), DC voltage (V) and peak-to-peak ripple voltage (V)."""

    name: str
    capacitance: float
    voltage_dc: float
    voltage_ripple_pp: float


@dataclass(frozen=True)
class CcmDesign:
    """Result of a CCM sizing: duty cycle plus the sized inductors and capacitors."""

    topology: str
    v_in: float
    v_out_magnitude: float
    output_polarity: Literal["positive", "negative"]
    i_out: float
    f_sw: float
    duty: float
    inductors: tuple[CcmInductor, ...]
    capacitors: tuple[CcmCapacitor, ...]
    assumptions: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def _inductor(name: str, inductance: float, i_avg: float, ripple_pp: float) -> CcmInductor:
    return CcmInductor(
        name=name,
        inductance=inductance,
        current_avg=i_avg,
        current_ripple_pp=ripple_pp,
        current_peak=i_avg + ripple_pp / 2,
        current_rms=triangular_ripple_rms(i_avg, ripple_pp),
    )


def buck_ccm(
    *,
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw: float,
    ripple_current_fraction: float = 0.3,
    ripple_voltage_fraction: float = 0.01,
) -> CcmDesign:
    """Buck (step-down): ``D = V_out/V_in``, ``L = V_out (1-D) / (f dI)``, ``C = dI / (8 f dV)``."""
    v_in, v_out, i_out, f_sw = (
        _positive("v_in", v_in),
        _positive("v_out", v_out),
        _positive("i_out", i_out),
        _positive("f_sw", f_sw),
    )
    if v_out >= v_in:
        raise ValueError("buck converter requires V_out < V_in")
    duty = v_out / v_in
    i_l = i_out
    d_i = _fraction("ripple_current_fraction", ripple_current_fraction) * i_l
    inductance = v_out * (1 - duty) / (f_sw * d_i)
    d_v = _fraction("ripple_voltage_fraction", ripple_voltage_fraction) * v_out
    capacitance = d_i / (8 * f_sw * d_v)
    return CcmDesign(
        topology="buck",
        v_in=v_in,
        v_out_magnitude=v_out,
        output_polarity="positive",
        i_out=i_out,
        f_sw=f_sw,
        duty=duty,
        inductors=(_inductor("L", inductance, i_l, d_i),),
        capacitors=(CcmCapacitor("C_out", capacitance, v_out, d_v),),
        assumptions=(
            SMALL_RIPPLE,
            "Output capacitor carries the triangular inductor ripple current (dV = dI / (8 f C)).",
        ),
    )


def boost_ccm(
    *,
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw: float,
    ripple_current_fraction: float = 0.3,
    ripple_voltage_fraction: float = 0.01,
) -> CcmDesign:
    """Boost (step-up): ``D = 1 - V_in/V_out``, ``I_L = I_out V_out/V_in``.

    ``L = V_in D / (f dI)``, ``C = I_out D / (f dV)``.
    """
    v_in, v_out, i_out, f_sw = (
        _positive("v_in", v_in),
        _positive("v_out", v_out),
        _positive("i_out", i_out),
        _positive("f_sw", f_sw),
    )
    if v_out <= v_in:
        raise ValueError("boost converter requires V_out > V_in")
    duty = 1 - v_in / v_out
    i_l = i_out * v_out / v_in
    d_i = _fraction("ripple_current_fraction", ripple_current_fraction) * i_l
    inductance = v_in * duty / (f_sw * d_i)
    d_v = _fraction("ripple_voltage_fraction", ripple_voltage_fraction) * v_out
    capacitance = i_out * duty / (f_sw * d_v)
    return CcmDesign(
        topology="boost",
        v_in=v_in,
        v_out_magnitude=v_out,
        output_polarity="positive",
        i_out=i_out,
        f_sw=f_sw,
        duty=duty,
        inductors=(_inductor("L", inductance, i_l, d_i),),
        capacitors=(CcmCapacitor("C_out", capacitance, v_out, d_v),),
        assumptions=(
            SMALL_RIPPLE,
            "Output capacitor alone supplies the load during the on-time (dV = I_out D / (f C)).",
        ),
    )


def buck_boost_ccm(
    *,
    v_in: float,
    v_out_magnitude: float,
    i_out: float,
    f_sw: float,
    ripple_current_fraction: float = 0.3,
    ripple_voltage_fraction: float = 0.01,
) -> CcmDesign:
    """Inverting buck-boost: ``D = |V_out| / (V_in + |V_out|)``, ``I_L = I_out / (1-D)``.

    ``L = V_in D / (f dI)``, ``C = I_out D / (f dV)``.
    """
    v_in, v_o, i_out, f_sw = (
        _positive("v_in", v_in),
        _positive("v_out_magnitude", v_out_magnitude),
        _positive("i_out", i_out),
        _positive("f_sw", f_sw),
    )
    duty = v_o / (v_in + v_o)
    i_l = i_out / (1 - duty)  # inductor carries input plus output current
    d_i = _fraction("ripple_current_fraction", ripple_current_fraction) * i_l
    inductance = v_in * duty / (f_sw * d_i)
    d_v = _fraction("ripple_voltage_fraction", ripple_voltage_fraction) * v_o
    capacitance = i_out * duty / (f_sw * d_v)
    return CcmDesign(
        topology="buck-boost",
        v_in=v_in,
        v_out_magnitude=v_o,
        output_polarity="negative",
        i_out=i_out,
        f_sw=f_sw,
        duty=duty,
        inductors=(_inductor("L", inductance, i_l, d_i),),
        capacitors=(CcmCapacitor("C_out", capacitance, v_o, d_v),),
        assumptions=(
            SMALL_RIPPLE,
            "Inductor average current is I_in + I_out = I_out / (1 - D); output voltage is inverted.",
        ),
    )


def sepic_ccm(
    *,
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw: float,
    ripple_current_fraction: float = 0.3,
    ripple_voltage_fraction: float = 0.01,
    coupling_ripple_fraction: float = 0.05,
) -> CcmDesign:
    """SEPIC (non-inverting): ``D = V_out/(V_in+V_out)``; ``L1``, ``L2`` from ``V_in D / (f dI)``.

    ``C_out = I_out D/(f dV)``.

    The coupling capacitor sits at ``V_in`` and is sized for ``coupling_ripple_fraction * V_in`` ripple:
    ``C_c = I_out D / (f dV_c)``.
    """
    v_in, v_out, i_out, f_sw = (
        _positive("v_in", v_in),
        _positive("v_out", v_out),
        _positive("i_out", i_out),
        _positive("f_sw", f_sw),
    )
    duty = v_out / (v_in + v_out)
    frac = _fraction("ripple_current_fraction", ripple_current_fraction)
    i_l1 = i_out * v_out / v_in  # input inductor carries the input current
    i_l2 = i_out  # output inductor carries the output current
    d_i1, d_i2 = frac * i_l1, frac * i_l2
    l1 = v_in * duty / (f_sw * d_i1)
    l2 = v_in * duty / (f_sw * d_i2)
    d_v = _fraction("ripple_voltage_fraction", ripple_voltage_fraction) * v_out
    c_out = i_out * duty / (f_sw * d_v)
    d_vc = _fraction("coupling_ripple_fraction", coupling_ripple_fraction) * v_in
    c_couple = i_out * duty / (f_sw * d_vc)
    return CcmDesign(
        topology="sepic",
        v_in=v_in,
        v_out_magnitude=v_out,
        output_polarity="positive",
        i_out=i_out,
        f_sw=f_sw,
        duty=duty,
        inductors=(_inductor("L1", l1, i_l1, d_i1), _inductor("L2", l2, i_l2, d_i2)),
        capacitors=(CcmCapacitor("C_out", c_out, v_out, d_v), CcmCapacitor("C_couple", c_couple, v_in, d_vc)),
        assumptions=(
            SMALL_RIPPLE,
            "Both inductors see V_in during the on-time; coupling capacitor voltage equals V_in.",
            "Output capacitor alone supplies the load during the on-time.",
        ),
    )


def cuk_ccm(
    *,
    v_in: float,
    v_out_magnitude: float,
    i_out: float,
    f_sw: float,
    ripple_current_fraction: float = 0.3,
    ripple_voltage_fraction: float = 0.01,
    coupling_ripple_fraction: float = 0.05,
) -> CcmDesign:
    """Cuk (inverting, continuous input and output current): ``D = |V_out|/(V_in+|V_out|)``.

    ``L1 = L2 = V_in D / (f dI)`` for the respective ripples, ``C_out = dI_L2 / (8 f dV)`` (triangular
    output-inductor ripple), coupling capacitor at ``V_in + |V_out|`` sized for
    ``coupling_ripple_fraction * (V_in + |V_out|)`` ripple: ``C_c = I_out D / (f dV_c)``.
    """
    v_in, v_o, i_out, f_sw = (
        _positive("v_in", v_in),
        _positive("v_out_magnitude", v_out_magnitude),
        _positive("i_out", i_out),
        _positive("f_sw", f_sw),
    )
    duty = v_o / (v_in + v_o)
    frac = _fraction("ripple_current_fraction", ripple_current_fraction)
    i_l1 = i_out * v_o / v_in
    i_l2 = i_out
    d_i1, d_i2 = frac * i_l1, frac * i_l2
    l1 = v_in * duty / (f_sw * d_i1)
    l2 = v_in * duty / (f_sw * d_i2)  # equals |V_out| (1-D) / (f dI2) by volt-second balance
    d_v = _fraction("ripple_voltage_fraction", ripple_voltage_fraction) * v_o
    c_out = d_i2 / (8 * f_sw * d_v)
    v_couple = v_in + v_o
    d_vc = _fraction("coupling_ripple_fraction", coupling_ripple_fraction) * v_couple
    c_couple = i_out * duty / (f_sw * d_vc)
    return CcmDesign(
        topology="cuk",
        v_in=v_in,
        v_out_magnitude=v_o,
        output_polarity="negative",
        i_out=i_out,
        f_sw=f_sw,
        duty=duty,
        inductors=(_inductor("L1", l1, i_l1, d_i1), _inductor("L2", l2, i_l2, d_i2)),
        capacitors=(CcmCapacitor("C_out", c_out, v_o, d_v), CcmCapacitor("C_couple", c_couple, v_couple, d_vc)),
        assumptions=(
            SMALL_RIPPLE,
            "Coupling capacitor voltage equals V_in + |V_out|; it discharges with I_L2 during the on-time.",
            "Output capacitor carries the triangular L2 ripple current; output voltage is inverted.",
        ),
    )
