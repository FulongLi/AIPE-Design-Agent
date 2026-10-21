"""First-order loss estimate for a hard-switched buck converter (SI units).

Migrated from the historical ``pea.tools.calculator.efficiency_estimate`` and restricted
to the topology its equations actually describe (a buck stage). Terms::

    D        = V_out / V_in
    I_L,rms  = sqrt(I_out^2 + dI_pp^2 / 12)                 (dI_pp = 0 neglects the ripple)
    P_hs     = D I_L,rms^2 R_ds(on),high                    high-side MOSFET conduction
    P_ls     = (1 - D) I_L,rms^2 R_ds(on),low               synchronous rectifier, or
             = (1 - D) I_out V_f                            freewheeling diode
    P_dcr    = I_L,rms^2 R_dcr                               inductor winding
    P_sw     = 1/2 V_in I_out (t_rise + t_fall) f_sw          linear voltage/current overlap at the
                                                              high-side switch (hard switching)

Not modelled: gate drive, output-capacitance (Coss) energy, reverse recovery, dead-time
body-diode conduction, core loss, controller/quiescent power, temperature dependence.
The result is a first-order screening value only.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Literal

from aipe_electrical.analysis.waveforms import triangular_ripple_rms

__all__ = ["BuckLossEstimate", "buck_first_order_losses"]


def _positive(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a finite positive number, got {value!r}")
    return float(value)


def _non_negative(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number, got {value!r}")
    return float(value)


@dataclass(frozen=True)
class BuckLossEstimate:
    """Loss breakdown (W) and efficiency (0..1) of the first-order buck model."""

    rectifier: Literal["synchronous", "diode"]
    output_power: float
    duty: float
    inductor_current_rms: float
    high_side_conduction: float
    low_side_conduction: float
    inductor_conduction: float
    switching: float
    total_loss: float
    efficiency: float
    assumptions: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def buck_first_order_losses(
    *,
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw: float,
    r_ds_on_high: float,
    r_dcr: float,
    t_rise: float,
    t_fall: float,
    r_ds_on_low: float | None = None,
    v_f_diode: float | None = None,
    ripple_current_pp: float = 0.0,
) -> BuckLossEstimate:
    """First-order hard-switched buck losses; give exactly one of ``r_ds_on_low`` (synchronous) or ``v_f_diode``.

    Resistances in ohm, times in seconds, frequency in Hz, currents in A, voltages in V.
    """
    v_in, v_out, i_out, f_sw = (
        _positive("v_in", v_in),
        _positive("v_out", v_out),
        _positive("i_out", i_out),
        _positive("f_sw", f_sw),
    )
    if v_out >= v_in:
        raise ValueError("buck converter requires V_out < V_in")
    if (r_ds_on_low is None) == (v_f_diode is None):
        raise ValueError("give exactly one of r_ds_on_low (synchronous rectifier) or v_f_diode (diode rectifier)")
    r_hs = _non_negative("r_ds_on_high", r_ds_on_high)
    r_l = _non_negative("r_dcr", r_dcr)
    t_r, t_f = _non_negative("t_rise", t_rise), _non_negative("t_fall", t_fall)
    ripple = _non_negative("ripple_current_pp", ripple_current_pp)

    duty = v_out / v_in
    i_rms = triangular_ripple_rms(i_out, ripple)
    p_hs = duty * i_rms * i_rms * r_hs
    if r_ds_on_low is not None:
        rectifier: Literal["synchronous", "diode"] = "synchronous"
        p_ls = (1 - duty) * i_rms * i_rms * _non_negative("r_ds_on_low", r_ds_on_low)
    else:
        rectifier = "diode"
        p_ls = (1 - duty) * i_out * _non_negative("v_f_diode", v_f_diode)  # type: ignore[arg-type]
    p_dcr = i_rms * i_rms * r_l
    p_sw = 0.5 * v_in * i_out * (t_r + t_f) * f_sw
    total = p_hs + p_ls + p_dcr + p_sw
    p_out = v_out * i_out
    return BuckLossEstimate(
        rectifier=rectifier,
        output_power=p_out,
        duty=duty,
        inductor_current_rms=i_rms,
        high_side_conduction=p_hs,
        low_side_conduction=p_ls,
        inductor_conduction=p_dcr,
        switching=p_sw,
        total_loss=total,
        efficiency=p_out / (p_out + total),
        assumptions=(
            "Hard-switched buck in CCM; linear voltage/current overlap switching loss at the high-side device only.",
            "Not modelled: gate drive, Coss energy, reverse recovery, dead-time conduction, core loss, "
            "temperature dependence.",
            "Ripple contribution to RMS current is included only through ripple_current_pp (default 0 neglects it).",
        ),
    )
