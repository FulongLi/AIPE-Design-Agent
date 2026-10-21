"""JSON-friendly dictionaries in and out of the analytical models.

Input keys carry explicit SI unit suffixes (``v1_V``, ``f_sw_Hz``, ``l_series_total_H``,
``phi_rad`` / ``phi_deg`` / ``power_W``). Outputs are plain ``dict`` objects that
``json.dumps`` accepts without a custom encoder.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

from aipe_electrical.analysis import dcdc, losses
from aipe_electrical.converters import dab_sps

__all__ = [
    "DCDC_TOPOLOGIES",
    "analyse_sps",
    "buck_losses",
    "dcdc_design",
    "design_sps",
    "sps_operating_point_from_dict",
    "sps_waveform",
]

SPS_CIRCUIT_KEYS = ("v1_V", "v2_V", "turns_ratio_np_ns", "f_sw_Hz", "l_series_total_H")
SPS_PHASE_KEYS = ("phi_rad", "phi_deg", "power_W")


def _number(payload: Mapping[str, Any], key: str) -> float:
    if key not in payload:
        raise ValueError(f"missing required key '{key}'")
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"'{key}' must be a finite number, got {value!r}")
    return float(value)


def _optional_number(payload: Mapping[str, Any], key: str, default: float) -> float:
    return _number(payload, key) if payload.get(key) is not None else default


def sps_operating_point_from_dict(payload: Mapping[str, Any]) -> tuple[dab_sps.SpsOperatingPoint, str]:
    """Build an operating point; the phase shift comes from exactly one of ``phi_rad``, ``phi_deg`` or ``power_W``.

    Returns ``(operating_point, phase_shift_source)`` where the source is ``"phi_rad"``,
    ``"phi_deg"`` or ``"solved for power_W"``.
    """
    given = [key for key in SPS_PHASE_KEYS if payload.get(key) is not None]
    if len(given) != 1:
        raise ValueError(f"give exactly one of {', '.join(SPS_PHASE_KEYS)}; got {given or 'none'}")
    circuit = {
        "v1": _number(payload, "v1_V"),
        "v2": _number(payload, "v2_V"),
        "turns_ratio_np_ns": _number(payload, "turns_ratio_np_ns"),
        "f_sw": _number(payload, "f_sw_Hz"),
        "l_series_total": _number(payload, "l_series_total_H"),
    }
    key = given[0]
    if key == "phi_rad":
        return dab_sps.SpsOperatingPoint(**circuit, phi_rad=_number(payload, key)), "phi_rad"
    if key == "phi_deg":
        return dab_sps.SpsOperatingPoint(**circuit, phi_rad=math.radians(_number(payload, key))), "phi_deg"
    phi = dab_sps.phase_shift_for_power(**circuit, p=_number(payload, "power_W"))
    return dab_sps.SpsOperatingPoint(**circuit, phi_rad=phi), "solved for power_W"


def analyse_sps(payload: Mapping[str, Any]) -> dict:
    """Full :func:`aipe_electrical.converters.dab_sps.analyse` report plus ``phase_shift_source``."""
    op, source = sps_operating_point_from_dict(payload)
    report = dab_sps.analyse(op)
    report["phase_shift_source"] = source
    return report


def design_sps(payload: Mapping[str, Any]) -> dict:
    """Size the total series inductance for ``power_W`` at ``phi_deg``/``phi_rad`` (replaces ``dab_design``).

    Keys: ``v1_V``, ``v2_V``, ``power_W``, ``f_sw_Hz``, one of ``phi_deg``/``phi_rad``, optional
    ``turns_ratio_np_ns`` (default: voltage-matching ratio ``V1/V2``).
    """
    given = [key for key in ("phi_rad", "phi_deg") if payload.get(key) is not None]
    if len(given) != 1:
        raise ValueError("give exactly one of phi_rad, phi_deg")
    phi = _number(payload, "phi_rad") if given[0] == "phi_rad" else math.radians(_number(payload, "phi_deg"))
    n = _number(payload, "turns_ratio_np_ns") if payload.get("turns_ratio_np_ns") is not None else None
    op = dab_sps.design_for_power(
        v1=_number(payload, "v1_V"),
        v2=_number(payload, "v2_V"),
        p=_number(payload, "power_W"),
        f_sw=_number(payload, "f_sw_Hz"),
        phi_rad=phi,
        turns_ratio_np_ns=n,
    )
    report = dab_sps.analyse(op)
    derived = report["derived"]
    return {
        "model": report["model"],
        "model_version": report["model_version"],
        "turns_ratio_np_ns": op.turns_ratio_np_ns,
        "turns_ratio_ns_np": op.turns_ratio_ns_np,
        "turns_ratio_source": "given" if n is not None else "voltage-matching V1/V2 (d = 1)",
        "voltage_ratio_d": op.d,
        "series_inductance_total_H": op.l_series_total,
        "series_inductance_total_uH": op.l_series_total * 1e6,
        "series_inductance_note": (
            "total primary-referred series inductance (external inductor plus transformer leakage), "
            "not the transformer leakage alone"
        ),
        "phase_shift_rad": op.phi_rad,
        "phase_shift_deg": op.phi_deg,
        "f_sw_Hz": op.f_sw,
        "power_W": derived["power"]["value"],
        "power_flow_direction": derived["power_flow_direction"],
        "max_power_W": derived["max_power_sps"]["value"],
        "series_current_rms_primary_A": derived["series_current_rms_primary"]["value"],
        "series_current_peak_primary_A": derived["series_current_peak_primary"]["value"],
        "secondary_current_rms_A": derived["secondary_current_rms"]["value"],
        "secondary_current_peak_A": derived["secondary_current_peak"]["value"],
        "dc_current_port1_A": derived["dc_current_port1"]["value"],
        "dc_current_port2_A": derived["dc_current_port2"]["value"],
        "zvs_current_direction_conditions": report["zvs_current_direction_conditions"],
        "assumptions": report["assumptions"],
    }


def sps_waveform(payload: Mapping[str, Any]) -> dict:
    """Sampled one-period waveforms; optional ``samples_per_period`` (default 400) and ``origin``."""
    op, source = sps_operating_point_from_dict(payload)
    samples = payload.get("samples_per_period", 400)
    origin = payload.get("origin", "rising_edge")
    result = dab_sps.sample_waveforms(op, samples_per_period=int(samples), origin=origin)
    result["phase_shift_source"] = source
    result["phi_rad"] = op.phi_rad
    return result


DCDC_TOPOLOGIES = ("buck", "boost", "buck-boost", "sepic", "cuk")


def dcdc_design(topology: str, payload: Mapping[str, Any]) -> dict:
    """CCM sizing for one of :data:`DCDC_TOPOLOGIES`.

    Keys: ``v_in_V``, ``v_out_V`` (magnitude for inverting topologies), ``i_out_A``, ``f_sw_Hz``,
    optional ``ripple_current_fraction`` (0.3), ``ripple_voltage_fraction`` (0.01) and, for
    SEPIC/Cuk, ``coupling_ripple_fraction`` (0.05).
    """
    if topology not in DCDC_TOPOLOGIES:
        raise ValueError(f"unknown topology {topology!r}; choose from {DCDC_TOPOLOGIES}")
    common = {
        "v_in": _number(payload, "v_in_V"),
        "i_out": _number(payload, "i_out_A"),
        "f_sw": _number(payload, "f_sw_Hz"),
        "ripple_current_fraction": _optional_number(payload, "ripple_current_fraction", 0.3),
        "ripple_voltage_fraction": _optional_number(payload, "ripple_voltage_fraction", 0.01),
    }
    v_out = _number(payload, "v_out_V")
    if topology == "buck":
        design = dcdc.buck_ccm(v_out=v_out, **common)
    elif topology == "boost":
        design = dcdc.boost_ccm(v_out=v_out, **common)
    elif topology == "buck-boost":
        design = dcdc.buck_boost_ccm(v_out_magnitude=abs(v_out), **common)
    else:
        coupling = _optional_number(payload, "coupling_ripple_fraction", 0.05)
        if topology == "sepic":
            design = dcdc.sepic_ccm(v_out=v_out, coupling_ripple_fraction=coupling, **common)
        else:
            design = dcdc.cuk_ccm(v_out_magnitude=abs(v_out), coupling_ripple_fraction=coupling, **common)
    return design.to_dict()


def buck_losses(payload: Mapping[str, Any]) -> dict:
    """First-order buck losses; keys ``v_in_V``, ``v_out_V``, ``i_out_A``, ``f_sw_Hz``, ``r_ds_on_high_ohm``,
    ``r_dcr_ohm``, ``t_rise_s``, ``t_fall_s``, one of ``r_ds_on_low_ohm``/``v_f_diode_V``,
    optional ``ripple_current_pp_A``.
    """
    return losses.buck_first_order_losses(
        v_in=_number(payload, "v_in_V"),
        v_out=_number(payload, "v_out_V"),
        i_out=_number(payload, "i_out_A"),
        f_sw=_number(payload, "f_sw_Hz"),
        r_ds_on_high=_number(payload, "r_ds_on_high_ohm"),
        r_dcr=_number(payload, "r_dcr_ohm"),
        t_rise=_number(payload, "t_rise_s"),
        t_fall=_number(payload, "t_fall_s"),
        r_ds_on_low=_number(payload, "r_ds_on_low_ohm") if payload.get("r_ds_on_low_ohm") is not None else None,
        v_f_diode=_number(payload, "v_f_diode_V") if payload.get("v_f_diode_V") is not None else None,
        ripple_current_pp=_optional_number(payload, "ripple_current_pp_A", 0.0),
    ).to_dict()
