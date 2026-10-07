"""
Power electronics design calculator.

Implements design equations for common converter topologies:
- Buck (step-down)
- Boost (step-up)
- Buck-Boost (inverting)
- SEPIC (non-inverting buck-boost)
- Cuk (inverting, continuous input/output current)
- Forward (isolated, single-ended)
- Flyback (isolated, coupled inductor)
- LLC resonant (isolated, high efficiency)
- DAB (Dual Active Bridge, bidirectional isolated)

Also provides:
- Topology recommendation (including DAB and cascade patterns)
- Efficiency estimation
- Cascade / multi-stage design helper
- Inductor and transformer magnetic design (Steinmetz core loss)
"""
from __future__ import annotations

import math
from typing import Optional


# ── Basic Topologies ─────────────────────────────────────────────────────


def buck_converter_design(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    ripple_current_pct: float = 0.3,
    ripple_voltage_pct: float = 0.01,
) -> dict:
    """Design a Buck (step-down) converter."""
    if v_out >= v_in:
        return {"error": "Buck converter requires V_out < V_in (step-down)"}

    duty = v_out / v_in
    f_sw_hz = f_sw_khz * 1000

    delta_i = i_out * ripple_current_pct
    l_uH = (v_out * (1 - duty) / (f_sw_hz * delta_i)) * 1e6

    delta_v = v_out * ripple_voltage_pct
    c_uF = (delta_i / (8 * f_sw_hz * delta_v)) * 1e6

    return {
        "topology": "Buck",
        "duty_cycle": round(duty, 3),
        "inductance_uH": round(l_uH, 2),
        "capacitance_uF": round(c_uF, 2),
        "switching_frequency_kHz": f_sw_khz,
        "ripple_current_A": round(delta_i, 3),
        "ripple_voltage_V": round(delta_v, 4),
        "notes": "Step-down converter. Use synchronous rectification for high efficiency.",
    }


def boost_converter_design(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    ripple_current_pct: float = 0.3,
    ripple_voltage_pct: float = 0.01,
) -> dict:
    """Design a Boost (step-up) converter."""
    if v_out <= v_in:
        return {"error": "Boost converter requires V_out > V_in (step-up)"}

    duty = 1 - (v_in / v_out)
    f_sw_hz = f_sw_khz * 1000
    i_in = i_out * (v_out / v_in)

    delta_i = i_in * ripple_current_pct
    l_uH = (v_in * duty / (f_sw_hz * delta_i)) * 1e6

    delta_v = v_out * ripple_voltage_pct
    c_uF = (i_out * duty / (f_sw_hz * delta_v)) * 1e6

    return {
        "topology": "Boost",
        "duty_cycle": round(duty, 3),
        "inductance_uH": round(l_uH, 2),
        "capacitance_uF": round(c_uF, 2),
        "switching_frequency_kHz": f_sw_khz,
        "ripple_current_A": round(delta_i, 3),
        "ripple_voltage_V": round(delta_v, 4),
        "notes": "Step-up converter. Watch for right-half-plane zero at high duty cycle.",
    }


def buck_boost_design(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    ripple_current_pct: float = 0.3,
    ripple_voltage_pct: float = 0.01,
) -> dict:
    """Design a Buck-Boost (inverting) converter. v_out is treated as magnitude."""
    duty = abs(v_out) / (v_in + abs(v_out))
    f_sw_hz = f_sw_khz * 1000
    i_in = i_out * (abs(v_out) / v_in)

    delta_i = i_in * ripple_current_pct
    l_uH = (v_in * duty / (f_sw_hz * delta_i)) * 1e6

    delta_v = abs(v_out) * ripple_voltage_pct
    c_uF = (i_out * duty / (f_sw_hz * delta_v)) * 1e6

    return {
        "topology": "Buck-Boost",
        "duty_cycle": round(duty, 3),
        "inductance_uH": round(l_uH, 2),
        "capacitance_uF": round(c_uF, 2),
        "switching_frequency_kHz": f_sw_khz,
        "ripple_current_A": round(delta_i, 3),
        "ripple_voltage_V": round(delta_v, 4),
        "notes": "Inverting topology. Output polarity is reversed. Good for wide input range.",
    }


# ── New Topologies ───────────────────────────────────────────────────────


def sepic_design(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    ripple_current_pct: float = 0.3,
    ripple_voltage_pct: float = 0.01,
) -> dict:
    """
    Design a SEPIC (Single-Ended Primary-Inductor Converter).

    Non-inverting topology that can step up or step down.
    Requires two inductors (or a coupled inductor) and a coupling capacitor.
    """
    duty = v_out / (v_in + v_out)
    f_sw_hz = f_sw_khz * 1000
    i_in = i_out * v_out / v_in

    delta_i = i_in * ripple_current_pct
    # Each inductor carries the input or output current respectively
    l1_uH = (v_in * duty / (f_sw_hz * delta_i)) * 1e6
    l2_uH = l1_uH  # Matched inductors for coupled-inductor designs

    delta_v = v_out * ripple_voltage_pct
    # Output capacitor sized for charge delivered during switch-on interval
    c_out_uF = (i_out * duty / (f_sw_hz * delta_v)) * 1e6
    # Coupling capacitor carries full load current; size for ~5% V_in ripple
    c_couple_uF = (i_out * duty / (f_sw_hz * v_in * 0.05)) * 1e6

    return {
        "topology": "SEPIC",
        "duty_cycle": round(duty, 3),
        "L1_inductance_uH": round(l1_uH, 2),
        "L2_inductance_uH": round(l2_uH, 2),
        "output_capacitance_uF": round(c_out_uF, 2),
        "coupling_capacitance_uF": round(c_couple_uF, 2),
        "switching_frequency_kHz": f_sw_khz,
        "ripple_current_A": round(delta_i, 3),
        "ripple_voltage_V": round(delta_v, 4),
        "notes": (
            "Non-inverting buck-boost. Same ground for input and output. "
            "L1 and L2 can be wound on the same core (coupled inductor). "
            "Higher component count than Buck or Boost alone."
        ),
    }


def cuk_design(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    ripple_current_pct: float = 0.3,
    ripple_voltage_pct: float = 0.01,
) -> dict:
    """
    Design a Cuk converter.

    Inverting topology with continuous input and output currents.
    Requires two inductors and a coupling capacitor.
    """
    vo_mag = abs(v_out)
    duty = vo_mag / (v_in + vo_mag)
    f_sw_hz = f_sw_khz * 1000
    i_in = i_out * vo_mag / v_in

    delta_i_in = i_in * ripple_current_pct
    delta_i_out = i_out * ripple_current_pct

    l1_uH = (v_in * duty / (f_sw_hz * delta_i_in)) * 1e6
    l2_uH = (vo_mag * (1 - duty) / (f_sw_hz * delta_i_out)) * 1e6

    delta_v = vo_mag * ripple_voltage_pct
    c_out_uF = (delta_i_out / (8 * f_sw_hz * delta_v)) * 1e6
    # Coupling cap carries full load; size for ~5% ripple on V_in + V_out
    c_couple_uF = (i_out * duty / (f_sw_hz * (v_in + vo_mag) * 0.05)) * 1e6

    return {
        "topology": "Cuk",
        "duty_cycle": round(duty, 3),
        "L1_input_inductance_uH": round(l1_uH, 2),
        "L2_output_inductance_uH": round(l2_uH, 2),
        "output_capacitance_uF": round(c_out_uF, 2),
        "coupling_capacitance_uF": round(c_couple_uF, 2),
        "switching_frequency_kHz": f_sw_khz,
        "ripple_current_input_A": round(delta_i_in, 3),
        "ripple_current_output_A": round(delta_i_out, 3),
        "ripple_voltage_V": round(delta_v, 4),
        "notes": (
            "Inverting topology with continuous input and output currents (low EMI). "
            "Output polarity is negative. L1/L2 can share a coupled core. "
            "Coupling capacitor must handle high ripple current."
        ),
    }


def forward_design(
    v_in_min: float,
    v_in_max: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    n_ratio: Optional[float] = None,
) -> dict:
    """
    Design a Forward converter (isolated single-ended).

    Suitable for ~50-300 W. Requires a reset winding or active clamp.
    """
    f_sw_hz = f_sw_khz * 1000
    v_in_nom = (v_in_min + v_in_max) / 2

    # Max duty limited to 0.5 for voltage-second reset with 1:1 reset winding
    d_max = 0.5
    if n_ratio is None:
        n_ratio = v_out / (v_in_min * d_max)

    duty_nom = v_out / (n_ratio * v_in_nom)
    duty_nom = min(duty_nom, d_max)

    # Output inductor (same as Buck post-rectifier)
    delta_i = i_out * 0.3
    v_sec = n_ratio * v_in_nom
    l_uH = ((v_sec * duty_nom - v_out) / (f_sw_hz * delta_i)) * 1e6
    l_uH = max(l_uH, 0.1)

    delta_v = v_out * 0.01
    c_uF = (delta_i / (8 * f_sw_hz * delta_v)) * 1e6

    # Peak switch voltage = V_in + V_reset ≈ 2*V_in for 1:1 reset
    v_switch_peak = 2 * v_in_max

    return {
        "topology": "Forward",
        "duty_cycle": round(duty_nom, 3),
        "turns_ratio_Ns_Np": round(n_ratio, 3),
        "output_inductance_uH": round(l_uH, 2),
        "output_capacitance_uF": round(c_uF, 2),
        "switching_frequency_kHz": f_sw_khz,
        "peak_switch_voltage_V": round(v_switch_peak, 1),
        "ripple_current_A": round(delta_i, 3),
        "notes": (
            "Isolated single-ended topology. Max D ≈ 0.5 with 1:1 reset winding. "
            "Good for 50-300 W. MOSFET sees ~2x V_in. "
            "Active clamp allows D > 0.5 and recovers leakage energy."
        ),
    }


def flyback_design(
    v_in_min: float,
    v_in_max: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    n_ratio: Optional[float] = None,
) -> dict:
    """Design a Flyback (isolated) converter - simplified first-pass design."""
    f_sw_hz = f_sw_khz * 1000
    v_in_nom = (v_in_min + v_in_max) / 2

    duty = 0.45
    if n_ratio is None:
        n_ratio = (v_out / v_in_nom) * (1 - duty) / duty

    p_out = v_out * i_out
    l_primary_uH = (v_in_min**2 * duty**2 / (2 * p_out * f_sw_hz)) * 1e6

    return {
        "topology": "Flyback",
        "duty_cycle": round(duty, 3),
        "turns_ratio_Ns_Np": round(n_ratio, 2),
        "primary_inductance_uH": round(l_primary_uH, 2),
        "switching_frequency_kHz": f_sw_khz,
        "notes": "Isolated converter. Add snubber for MOSFET protection. Consider LLC for higher power.",
    }


def llc_design(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    q_factor: float = 0.5,
    n_ratio: Optional[float] = None,
) -> dict:
    """
    Design an LLC resonant converter - first-pass resonant tank sizing.

    The LLC uses a series resonant inductor (Lr), magnetizing inductor (Lm),
    and resonant capacitor (Cr).  Frequency modulation around the resonant
    frequency controls the output.

    Args:
        v_in: DC input voltage (V) — typically from a PFC front-end
        v_out: Output voltage (V)
        i_out: Output current (A)
        f_sw_khz: Nominal switching frequency ≈ resonant frequency (kHz)
        q_factor: Loaded quality factor (0.3-0.8 typical; lower = wider gain range)
        n_ratio: Transformer turns ratio Ns/Np (auto-calculated if None)
    """
    f_r_hz = f_sw_khz * 1000
    p_out = v_out * i_out
    if p_out <= 0:
        return {"error": "Output power must be positive"}

    if n_ratio is None:
        # At resonance, gain = 1 → V_out = n * V_in / 2  (full-bridge)
        n_ratio = 2 * v_out / v_in

    r_ac = 8 * (n_ratio ** 2) * (v_out ** 2) / (math.pi ** 2 * p_out)

    # Cr from Q = 1/(2*pi*fr*Cr*R_ac)  →  Cr = 1/(2*pi*fr*Q*R_ac)
    c_r_nF = 1e9 / (2 * math.pi * f_r_hz * q_factor * r_ac)

    # Lr from fr = 1/(2*pi*sqrt(Lr*Cr))
    c_r_f = c_r_nF * 1e-9
    l_r_uH = (1 / ((2 * math.pi * f_r_hz) ** 2 * c_r_f)) * 1e6

    # Lm typically 3-7x Lr for good gain range; use 5x as starting point
    lm_ratio = 5.0
    l_m_uH = l_r_uH * lm_ratio

    return {
        "topology": "LLC Resonant",
        "turns_ratio_Ns_Np": round(n_ratio, 3),
        # High-power / low-gain designs can yield sub-0.01 µH Lr; keep extra digits.
        "resonant_inductance_Lr_uH": round(l_r_uH, 4),
        "magnetizing_inductance_Lm_uH": round(l_m_uH, 4),
        "resonant_capacitance_Cr_nF": round(c_r_nF, 2),
        "Lm_Lr_ratio": lm_ratio,
        "resonant_frequency_kHz": f_sw_khz,
        "Q_factor": q_factor,
        "equivalent_ac_resistance_ohm": round(r_ac, 2),
        "notes": (
            "LLC resonant converter (full-bridge primary, center-tap secondary assumed). "
            "Achieves ZVS over full load range when operated near or above resonance. "
            "Lm/Lr ratio of 5 is a starting point — decrease for wider gain range, "
            "increase for lower circulating current. Verify gain curves for V_in range."
        ),
    }


# ── Dual Active Bridge (DAB) ─────────────────────────────────────────────


def dab_design(
    v1: float,
    v2: float,
    p_rated: float,
    f_sw_khz: float = 100,
    phi_deg: float = 30,
) -> dict:
    """
    Design a Dual Active Bridge (DAB) converter.

    Bidirectional isolated topology using two full-bridge legs with
    phase-shift control.  Single phase-shift (SPS) modulation is assumed.

    Args:
        v1: Port-1 DC voltage (V)
        v2: Port-2 DC voltage (V)
        p_rated: Rated transfer power (W)
        f_sw_khz: Switching frequency (kHz)
        phi_deg: Phase shift between bridges (degrees, 0-90)
    """
    if p_rated <= 0:
        return {"error": "Rated power must be positive"}
    if not 0 < phi_deg < 180:
        return {"error": "Phase shift must be between 0 and 180 degrees"}

    f_sw_hz = f_sw_khz * 1000
    phi = math.radians(phi_deg)
    n = v2 / v1

    # Required leakage inductance for rated power at given phase shift
    # P = V1 * n * V1 * phi * (pi - phi) / (2 * pi^2 * f_sw * L)
    l_h = v1 * n * v1 * phi * (math.pi - phi) / (2 * math.pi**2 * f_sw_hz * p_rated)
    l_uH = l_h * 1e6

    # Peak and RMS inductor current (primary side)
    i_l_pk = v1 * (math.pi - phi) / (2 * math.pi * f_sw_hz * l_h)
    i_l_rms = v1 * math.sqrt(
        phi * (math.pi - phi) * (2 * math.pi - phi) / (3 * math.pi)
    ) / (2 * math.pi * f_sw_hz * l_h)

    # Secondary-side reflected currents
    i_sec_pk = i_l_pk / n
    i_sec_rms = i_l_rms / n

    zvs_status = "Achievable" if i_l_pk > 0 else "Check dead-time"

    return {
        "topology": "DAB",
        "turns_ratio_n": round(n, 4),
        "leakage_inductance_uH": round(l_uH, 2),
        "phase_shift_deg": phi_deg,
        "transferred_power_W": round(p_rated, 1),
        "I_L_peak_A": round(i_l_pk, 2),
        "I_L_rms_A": round(i_l_rms, 2),
        "I_sec_peak_A": round(i_sec_pk, 2),
        "I_sec_rms_A": round(i_sec_rms, 2),
        "switching_frequency_kHz": f_sw_khz,
        "ZVS_status": zvs_status,
        "notes": (
            "Dual Active Bridge: bidirectional isolated converter with ZVS at "
            "moderate to full load. SPS (single phase-shift) modulation assumed. "
            "Use EPS/TPS for extended ZVS range at light load. "
            "Ideal for EV charging, energy storage, and V2G applications."
        ),
    }


# ── Cascade / Multi-Stage Design ────────────────────────────────────────


def cascade_design(
    v_in: float,
    v_out: float,
    i_out: float,
    stages: Optional[list[dict]] = None,
    f_sw_khz: float = 100,
) -> dict:
    """
    Design a cascade (multi-stage) converter.

    Common patterns: PFC front-end + isolated DC-DC, Buck + Boost for wide
    conversion ratio, etc.  If *stages* is not supplied, an appropriate
    two-stage cascade is auto-selected.

    Each element of *stages* is ``{"topology": "<name>", ...}`` with
    optional overrides for the per-stage calculator.
    """
    p_out = v_out * i_out
    if p_out <= 0:
        return {"error": "Output power must be positive"}

    if stages is not None:
        return _cascade_from_explicit_stages(v_in, v_out, i_out, stages, f_sw_khz)

    # Auto-select cascade pattern
    ratio = v_out / v_in
    isolated = v_out * i_out > 200 or abs(v_out - v_in) > 200

    if isolated and p_out >= 200:
        # PFC Boost (to ~400 V DC bus) + LLC
        v_bus = 400.0
        stage1 = boost_converter_design(v_in=v_in, v_out=v_bus, i_out=p_out / v_bus, f_sw_khz=f_sw_khz)
        stage2 = llc_design(v_in=v_bus, v_out=v_out, i_out=i_out, f_sw_khz=f_sw_khz)
        pattern = "PFC Boost + LLC"
    elif ratio < 0.1:
        # Very large step-down: Buck + Buck
        v_mid = math.sqrt(v_in * v_out)
        i_mid = p_out / v_mid
        stage1 = buck_converter_design(v_in=v_in, v_out=v_mid, i_out=i_mid, f_sw_khz=f_sw_khz)
        stage2 = buck_converter_design(v_in=v_mid, v_out=v_out, i_out=i_out, f_sw_khz=f_sw_khz)
        pattern = "Buck + Buck (cascaded step-down)"
    elif ratio > 10:
        # Very large step-up: Boost + Boost
        v_mid = math.sqrt(v_in * v_out)
        i_mid = p_out / v_mid
        stage1 = boost_converter_design(v_in=v_in, v_out=v_mid, i_out=i_mid, f_sw_khz=f_sw_khz)
        stage2 = boost_converter_design(v_in=v_mid, v_out=v_out, i_out=i_out, f_sw_khz=f_sw_khz)
        pattern = "Boost + Boost (cascaded step-up)"
    else:
        # Moderate ratio: Buck front-end + Boost output
        v_mid = min(v_in, v_out)
        i_mid = p_out / v_mid
        if v_in > v_out:
            stage1 = buck_converter_design(v_in=v_in, v_out=v_mid, i_out=i_mid, f_sw_khz=f_sw_khz)
            stage2 = {"topology": "pass-through", "notes": "Single-stage Buck sufficient"}
            pattern = "Single-stage Buck sufficient (cascade not needed)"
        else:
            stage1 = {"topology": "pass-through", "notes": "Single-stage Boost sufficient"}
            stage2 = boost_converter_design(v_in=v_mid, v_out=v_out, i_out=i_out, f_sw_khz=f_sw_khz)
            pattern = "Single-stage Boost (cascade not needed)"

    eta_est = 0.92 if "LLC" in pattern else 0.95
    return {
        "topology": "Cascade",
        "pattern": pattern,
        "stage_1": stage1,
        "stage_2": stage2,
        "overall_efficiency_est_pct": round(eta_est * 100, 1),
        "output_power_W": round(p_out, 1),
        "notes": (
            f"Auto-selected cascade: {pattern}. "
            "Overall efficiency is the product of stage efficiencies. "
            "Intermediate bus voltage chosen for balanced conversion ratios."
        ),
    }


def _cascade_from_explicit_stages(
    v_in: float, v_out: float, i_out: float,
    stages: list[dict], f_sw_khz: float,
) -> dict:
    """Build cascade from user-specified stage list."""
    results = []
    v_current = v_in
    p_out = v_out * i_out

    for i, stage_spec in enumerate(stages):
        topo = stage_spec.get("topology", "").lower()
        is_last = i == len(stages) - 1
        i_stage = i_out if is_last else p_out / (stage_spec.get("v_out", v_out))
        v_stage_out = stage_spec.get("v_out", v_out if is_last else v_current)

        fn = _TOOL_REGISTRY.get(f"{topo}_converter_design") or _TOOL_REGISTRY.get(f"{topo}_design")
        if fn:
            kwargs = {"v_in": v_current, "v_out": v_stage_out, "i_out": i_stage, "f_sw_khz": f_sw_khz}
            if topo in ("forward", "flyback"):
                kwargs = {"v_in_min": v_current * 0.9, "v_in_max": v_current * 1.1,
                          "v_out": v_stage_out, "i_out": i_stage, "f_sw_khz": f_sw_khz}
            results.append(fn(**kwargs))
        else:
            results.append({"topology": topo, "note": "No calculator available for this topology"})

        v_current = v_stage_out

    return {
        "topology": "Cascade",
        "pattern": " + ".join(s.get("topology", "?") for s in results),
        "stages": results,
        "output_power_W": round(p_out, 1),
        "notes": "User-specified cascade. Overall efficiency = product of stage efficiencies.",
    }


# ── Inductor Design (Magnetics) ─────────────────────────────────────────


def inductor_design(
    inductance_uH: float,
    i_peak: float,
    i_rms: float,
    f_sw_khz: float = 100,
    core_shape: str = "EE",
    material: str = "N87",
    b_max_mT: float = 300,
    j_current_density: float = 5.0,
) -> dict:
    """
    Design a filter inductor given electrical requirements.

    Selects a core from the built-in library, computes turns, wire gauge,
    air gap, window fill, and loss breakdown (Steinmetz core + copper).

    Args:
        inductance_uH: Required inductance (µH)
        i_peak: Peak inductor current (A)
        i_rms: RMS inductor current (A)
        f_sw_khz: Switching frequency (kHz)
        core_shape: Core geometry (EE, PQ, RM, ETD, EFD, EP, toroid, EI)
        material: Ferrite material (N87, N97, 3C90, 3C95, 3F3, PC40, PC95)
        b_max_mT: Max flux density target (mT)
        j_current_density: Winding current density (A/mm²)
    """
    from pea.tools.magnetics_data import CORE_DATA, MAT_DATA

    L = inductance_uH * 1e-6
    f_sw_hz = f_sw_khz * 1000
    b_max = b_max_mT / 1000  # T

    mat_info = MAT_DATA.get(material)
    if mat_info is None:
        return {"error": f"Unknown material: {material}. Available: {list(MAT_DATA.keys())}"}
    shape_info = CORE_DATA.get(core_shape)
    if shape_info is None:
        return {"error": f"Unknown core shape: {core_shape}. Available: {list(CORE_DATA.keys())}"}

    # Window utilization factor
    Ku = 0.4
    # Required area product Ap = Ae * Aw >= L * I_pk * I_rms / (B_max * J * Ku)  [m^4]
    # Convert to mm^4 for comparison with core data
    Ap_min_mm4 = L * i_peak * i_rms / (b_max * j_current_density * 1e6 * Ku) * 1e12

    cores = shape_info["sizes"]
    selected = None
    for c in cores:
        if c["Ae"] * c["Aw"] >= Ap_min_mm4:
            selected = c
            break
    if selected is None:
        selected = cores[-1]

    Ae_mm2 = selected["Ae"]
    Ae_m2 = Ae_mm2 * 1e-6

    # Turns
    N = max(math.ceil(L * i_peak / (b_max * Ae_m2)), 1)
    B_actual_mT = L * i_peak / (N * Ae_m2) * 1000

    # Wire sizing
    Aw_wire_mm2 = i_rms / j_current_density
    d_wire_mm = math.sqrt(4 * Aw_wire_mm2 / math.pi)
    awg = round(math.log(d_wire_mm / 8.251) / math.log(0.890526))
    fill = N * Aw_wire_mm2 / selected["Aw"]

    # Air gap
    mu0 = 4 * math.pi * 1e-7
    mu_r = mat_info["mu_i"]
    le_m = selected["le"] * 1e-3
    lg_mm = (mu0 * N**2 * Ae_m2 / L - le_m / mu_r) * 1e3

    # Steinmetz core loss: Pv = k * f^alpha * B^beta  (W/m^3)
    st = mat_info["steinmetz"]
    delta_B = B_actual_mT * 0.3  # AC ripple component ~30% of peak
    Pv = st["k"] * f_sw_hz**st["alpha"] * delta_B**st["beta"]
    Ve_m3 = selected["Ve"] * 1e-9  # mm^3 to m^3
    P_core_W = Pv * Ve_m3

    # Copper loss
    rho_cu = 1.72e-8  # Ω·m
    MLT_m = 2 * (math.sqrt(Ae_mm2) * 2 + 5) * 1e-3  # approx mean length per turn
    R_dc = rho_cu * N * MLT_m / (Aw_wire_mm2 * 1e-6)
    P_cu_W = i_rms**2 * R_dc

    warnings = []
    if B_actual_mT > mat_info["bsat"] * 0.9:
        warnings.append(
            f"B_peak ({B_actual_mT:.0f} mT) near saturation ({mat_info['bsat']} mT). "
            "Increase core size or turns."
        )
    if fill > 0.5:
        warnings.append(f"Window fill {fill*100:.0f}% > 50%. Consider larger core.")

    return {
        "design": "Inductor",
        "core": selected["name"],
        "core_shape": core_shape,
        "material": material,
        "turns": N,
        "wire_AWG": awg,
        "wire_diameter_mm": round(d_wire_mm, 2),
        "B_peak_mT": round(B_actual_mT, 1),
        "air_gap_mm": round(max(lg_mm, 0), 2),
        "window_fill_pct": round(fill * 100, 1),
        "energy_uJ": round(0.5 * L * i_peak**2 * 1e6, 2),
        "Ae_mm2": Ae_mm2,
        "core_loss_mW": round(P_core_W * 1000, 2),
        "copper_loss_mW": round(P_cu_W * 1000, 2),
        "total_loss_mW": round((P_core_W + P_cu_W) * 1000, 1),
        "warnings": warnings,
        "notes": (
            f"Inductor design on {selected['name']} ({core_shape}) with {material}. "
            "Core loss via Steinmetz equation. Verify thermal limits for total loss."
        ),
    }


# ── Transformer Design (Magnetics) ──────────────────────────────────────


def transformer_design(
    v_pri: float,
    v_sec: float,
    power_W: float,
    f_sw_khz: float = 100,
    duty_cycle: float = 0.45,
    core_shape: str = "EE",
    material: str = "N87",
    b_max_mT: float = 250,
) -> dict:
    """
    Design a power transformer given electrical requirements.

    Selects a core, computes primary/secondary turns, wire sizes,
    flux density, and loss breakdown.

    Args:
        v_pri: Primary voltage (V)
        v_sec: Secondary voltage (V)
        power_W: Rated power (W)
        f_sw_khz: Switching frequency (kHz)
        duty_cycle: Duty cycle (0-1)
        core_shape: Core geometry
        material: Ferrite material
        b_max_mT: Max flux density target (mT)
    """
    from pea.tools.magnetics_data import CORE_DATA, MAT_DATA

    if power_W <= 0:
        return {"error": "Power must be positive"}

    f_sw_hz = f_sw_khz * 1000
    b_max = b_max_mT / 1000
    n = v_sec / v_pri
    I_pri = power_W / v_pri
    I_sec = power_W / v_sec

    mat_info = MAT_DATA.get(material)
    if mat_info is None:
        return {"error": f"Unknown material: {material}. Available: {list(MAT_DATA.keys())}"}
    shape_info = CORE_DATA.get(core_shape)
    if shape_info is None:
        return {"error": f"Unknown core shape: {core_shape}. Available: {list(CORE_DATA.keys())}"}

    Ku = 0.3
    J = 5.0  # A/mm²
    # Ap_min = P / (2 * B_max * f_sw * J * Ku) [m^4] → mm^4
    Ap_min_mm4 = power_W / (2 * b_max * f_sw_hz * J * 1e6 * Ku) * 1e12

    cores = shape_info["sizes"]
    selected = None
    for c in cores:
        if c["Ae"] * c["Aw"] >= Ap_min_mm4:
            selected = c
            break
    if selected is None:
        selected = cores[-1]

    Ae_m2 = selected["Ae"] * 1e-6
    N_pri = max(math.ceil(v_pri * duty_cycle / (b_max * Ae_m2 * f_sw_hz)), 1)
    N_sec = max(math.ceil(N_pri * n), 1)
    n_actual = N_sec / N_pri
    B_actual_mT = v_pri * duty_cycle / (N_pri * Ae_m2 * f_sw_hz) * 1000

    # Wire sizing
    Aw_pri = I_pri * math.sqrt(duty_cycle) / J
    Aw_sec = I_sec * math.sqrt(1 - duty_cycle) / J
    d_pri = math.sqrt(4 * Aw_pri / math.pi)
    d_sec = math.sqrt(4 * Aw_sec / math.pi)
    awg_pri = round(math.log(d_pri / 8.251) / math.log(0.890526))
    awg_sec = round(math.log(d_sec / 8.251) / math.log(0.890526))
    fill = (N_pri * Aw_pri + N_sec * Aw_sec) / selected["Aw"]

    # Steinmetz core loss
    st = mat_info["steinmetz"]
    Pv = st["k"] * f_sw_hz**st["alpha"] * B_actual_mT**st["beta"]
    Ve_m3 = selected["Ve"] * 1e-9
    P_core_W = Pv * Ve_m3

    # Copper loss (approx)
    rho_cu = 1.72e-8
    MLT_m = 2 * (math.sqrt(selected["Ae"]) * 2 + 5) * 1e-3
    R_pri = rho_cu * N_pri * MLT_m / (Aw_pri * 1e-6) if Aw_pri > 0 else 0
    R_sec = rho_cu * N_sec * MLT_m / (Aw_sec * 1e-6) if Aw_sec > 0 else 0
    P_cu_W = I_pri**2 * duty_cycle * R_pri + I_sec**2 * (1 - duty_cycle) * R_sec

    warnings = []
    if B_actual_mT > mat_info["bsat"] * 0.9:
        warnings.append(
            f"B_peak ({B_actual_mT:.0f} mT) near saturation ({mat_info['bsat']} mT). "
            "Increase N_pri or core size."
        )
    if fill > 0.5:
        warnings.append(f"Window fill {fill*100:.0f}% > 50%. Consider larger core.")

    return {
        "design": "Transformer",
        "core": selected["name"],
        "core_shape": core_shape,
        "material": material,
        "N_primary": N_pri,
        "N_secondary": N_sec,
        "turns_ratio_actual": round(n_actual, 3),
        "primary_wire_AWG": awg_pri,
        "secondary_wire_AWG": awg_sec,
        "B_peak_mT": round(B_actual_mT, 1),
        "window_fill_pct": round(fill * 100, 1),
        "core_loss_mW": round(P_core_W * 1000, 2),
        "copper_loss_mW": round(P_cu_W * 1000, 2),
        "total_loss_mW": round((P_core_W + P_cu_W) * 1000, 1),
        "warnings": warnings,
        "notes": (
            f"Transformer design on {selected['name']} ({core_shape}) with {material}. "
            f"Turns ratio {N_pri}:{N_sec} (target {n:.3f}, actual {n_actual:.3f}). "
            "Core loss via Steinmetz equation."
        ),
    }


# ── Efficiency Estimation ────────────────────────────────────────────────


def efficiency_estimate(
    v_in: float,
    v_out: float,
    i_out: float,
    f_sw_khz: float = 100,
    rds_on_mohm: float = 50.0,
    dcr_mohm: float = 30.0,
    vf_diode: float = 0.5,
    t_rise_ns: float = 20.0,
    t_fall_ns: float = 20.0,
    sync_rect: bool = False,
) -> dict:
    """
    Estimate converter efficiency from component-level loss parameters.

    Provides a first-order breakdown of conduction and switching losses
    for a generic non-isolated converter (Buck-like model).  The estimate
    is conservative and intended for initial component selection.

    Args:
        v_in: Input voltage (V)
        v_out: Output voltage (V)
        i_out: Output current (A)
        f_sw_khz: Switching frequency (kHz)
        rds_on_mohm: High-side MOSFET Rds(on) in milliohms
        dcr_mohm: Inductor DC resistance in milliohms
        vf_diode: Freewheeling diode forward voltage (V); ignored if sync_rect
        t_rise_ns: MOSFET turn-on rise time (ns)
        t_fall_ns: MOSFET turn-off fall time (ns)
        sync_rect: True if using synchronous rectification (MOSFET instead of diode)
    """
    p_out = v_out * i_out
    if p_out <= 0:
        return {"error": "Output power must be positive"}

    f_sw_hz = f_sw_khz * 1000
    rds = rds_on_mohm / 1000
    dcr = dcr_mohm / 1000
    duty = min(v_out / v_in, 0.99) if v_out < v_in else max(1 - v_in / v_out, 0.01)

    i_rms_sw = i_out * math.sqrt(duty)

    # Conduction losses
    p_cond_fet = i_rms_sw ** 2 * rds
    p_cond_inductor = i_out ** 2 * dcr

    if sync_rect:
        p_cond_diode = i_out ** 2 * (1 - duty) * rds  # low-side FET
    else:
        p_cond_diode = vf_diode * i_out * (1 - duty)

    p_conduction = p_cond_fet + p_cond_inductor + p_cond_diode

    # Switching losses (overlap model)
    t_rise = t_rise_ns * 1e-9
    t_fall = t_fall_ns * 1e-9
    p_sw_on = 0.5 * v_in * i_out * t_rise * f_sw_hz
    p_sw_off = 0.5 * v_in * i_out * t_fall * f_sw_hz
    p_switching = p_sw_on + p_sw_off

    p_total_loss = p_conduction + p_switching
    p_in = p_out + p_total_loss
    eta = p_out / p_in if p_in > 0 else 0

    return {
        "output_power_W": round(p_out, 2),
        "estimated_efficiency_pct": round(eta * 100, 1),
        "total_loss_W": round(p_total_loss, 3),
        "conduction_loss_W": round(p_conduction, 3),
        "switching_loss_W": round(p_switching, 3),
        "breakdown": {
            "MOSFET_conduction_W": round(p_cond_fet, 3),
            "inductor_DCR_W": round(p_cond_inductor, 3),
            "diode_or_SR_conduction_W": round(p_cond_diode, 3),
            "turn_on_loss_W": round(p_sw_on, 3),
            "turn_off_loss_W": round(p_sw_off, 3),
        },
        "notes": (
            f"{'Synchronous rectification' if sync_rect else 'Diode rectification'}. "
            "First-order estimate; does not include gate-drive, quiescent, or core losses. "
            "Actual efficiency may differ by 1-3%."
        ),
    }


# ── Topology Recommendation ─────────────────────────────────────────────


def topology_recommendation(
    v_in: float, v_out: float, i_out: float,
    isolated: bool = False, bidirectional: bool = False,
) -> dict:
    """Recommend suitable converter topology based on specifications."""
    v_ratio = v_out / v_in
    p_out = v_out * i_out

    if bidirectional and isolated:
        return {
            "recommended": "DAB",
            "alternatives": ["LLC Resonant (unidirectional)", "Phase-shifted Full Bridge"],
            "rationale": (
                "DAB (Dual Active Bridge) is optimal for bidirectional isolated "
                "applications: EV charging (V2G), battery energy storage, "
                "solid-state transformers. ZVS achievable with phase-shift control."
            ),
            "output_power_W": round(p_out, 1),
        }

    if isolated:
        if p_out > 500:
            return {
                "recommended": "DAB" if bidirectional else "LLC Resonant",
                "alternatives": ["DAB", "Phase-shifted Full Bridge", "PFC Boost + LLC cascade"],
                "rationale": (
                    "High-power isolated: LLC resonant for highest unidirectional "
                    "efficiency with ZVS. DAB if bidirectional flow needed. "
                    "Consider PFC Boost + LLC cascade for AC-DC applications."
                ),
                "output_power_W": round(p_out, 1),
            }
        if p_out < 50:
            return {
                "recommended": "Flyback",
                "alternatives": ["Forward"],
                "rationale": "Flyback is cost-effective for low-power isolated applications.",
                "output_power_W": round(p_out, 1),
            }
        elif p_out < 200:
            return {
                "recommended": "Flyback",
                "alternatives": ["Forward", "Push-Pull"],
                "rationale": "Flyback or Forward suitable for medium power. Flyback simpler.",
                "output_power_W": round(p_out, 1),
            }
        else:
            return {
                "recommended": "LLC Resonant",
                "alternatives": ["Forward", "Phase-shifted Full Bridge", "DAB (if bidirectional)"],
                "rationale": (
                    "LLC resonant offers highest efficiency at higher power with ZVS. "
                    "Forward converter is simpler but less efficient."
                ),
                "output_power_W": round(p_out, 1),
            }

    # Very large conversion ratios suggest cascade
    if v_ratio < 0.1:
        rec = {
            "recommended": "Buck + Buck cascade",
            "alternatives": ["Buck", "Forward"],
            "rationale": (
                "Very large step-down ratio (>10:1). Cascaded Buck stages with "
                "geometric-mean intermediate voltage balance conversion stress."
            ),
        }
    elif v_ratio > 10:
        rec = {
            "recommended": "Boost + Boost cascade",
            "alternatives": ["Boost", "Flyback"],
            "rationale": (
                "Very large step-up ratio (>10:1). Cascaded Boost stages reduce "
                "duty cycle stress on each stage."
            ),
        }
    elif v_ratio < 0.9:
        rec = {
            "recommended": "Buck",
            "alternatives": ["Buck-Boost"],
            "rationale": "Buck is optimal for step-down (V_out < V_in). Highest efficiency.",
        }
    elif v_ratio > 1.1:
        rec = {
            "recommended": "Boost",
            "alternatives": ["SEPIC", "Buck-Boost"],
            "rationale": "Boost is optimal for step-up (V_out > V_in).",
        }
    else:
        rec = {
            "recommended": "SEPIC",
            "alternatives": ["Cuk", "Buck-Boost", "Buck + Boost cascade"],
            "rationale": (
                "Input and output voltages are close. SEPIC provides non-inverting "
                "buck-boost capability with common ground. Cuk alternative if "
                "continuous I/O current is needed."
            ),
        }

    rec["output_power_W"] = round(p_out, 1)
    return rec


# ── Tool dispatch ────────────────────────────────────────────────────────


_TOOL_REGISTRY: dict[str, callable] = {
    "buck_converter_design": buck_converter_design,
    "boost_converter_design": boost_converter_design,
    "buck_boost_design": buck_boost_design,
    "sepic_design": sepic_design,
    "cuk_design": cuk_design,
    "forward_design": forward_design,
    "flyback_design": flyback_design,
    "llc_design": llc_design,
    "dab_design": dab_design,
    "cascade_design": cascade_design,
    "inductor_design": inductor_design,
    "transformer_design": transformer_design,
    "topology_recommendation": topology_recommendation,
    "efficiency_estimate": efficiency_estimate,
}


def execute_tool(tool_name: str, **kwargs) -> str:
    """Execute a design tool and return result as JSON string."""
    import json

    fn = _TOOL_REGISTRY.get(tool_name)
    if fn is None:
        return json.dumps({"error": f"Unknown tool: {tool_name}"})
    try:
        result = fn(**kwargs)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_available_tools() -> list[dict]:
    """Return list of available calculation tools for the agent."""
    return [
        {
            "name": "buck_converter_design",
            "description": "Design a Buck (step-down) converter. Use when V_out < V_in.",
            "parameters": ["v_in", "v_out", "i_out", "f_sw_khz", "ripple_current_pct", "ripple_voltage_pct"],
        },
        {
            "name": "boost_converter_design",
            "description": "Design a Boost (step-up) converter. Use when V_out > V_in.",
            "parameters": ["v_in", "v_out", "i_out", "f_sw_khz", "ripple_current_pct", "ripple_voltage_pct"],
        },
        {
            "name": "buck_boost_design",
            "description": "Design a Buck-Boost converter. Use for inverting or wide input range.",
            "parameters": ["v_in", "v_out", "i_out", "f_sw_khz", "ripple_current_pct", "ripple_voltage_pct"],
        },
        {
            "name": "sepic_design",
            "description": "Design a SEPIC converter. Non-inverting buck-boost with common ground.",
            "parameters": ["v_in", "v_out", "i_out", "f_sw_khz", "ripple_current_pct", "ripple_voltage_pct"],
        },
        {
            "name": "cuk_design",
            "description": "Design a Cuk converter. Inverting with continuous input/output currents.",
            "parameters": ["v_in", "v_out", "i_out", "f_sw_khz", "ripple_current_pct", "ripple_voltage_pct"],
        },
        {
            "name": "forward_design",
            "description": "Design a Forward isolated converter. Good for 50-300 W.",
            "parameters": ["v_in_min", "v_in_max", "v_out", "i_out", "f_sw_khz", "n_ratio"],
        },
        {
            "name": "flyback_design",
            "description": "Design a Flyback isolated converter. Use when isolation is required.",
            "parameters": ["v_in_min", "v_in_max", "v_out", "i_out", "f_sw_khz", "n_ratio"],
        },
        {
            "name": "llc_design",
            "description": "Design an LLC resonant converter. High efficiency isolated topology with ZVS.",
            "parameters": ["v_in", "v_out", "i_out", "f_sw_khz", "q_factor", "n_ratio"],
        },
        {
            "name": "dab_design",
            "description": "Design a DAB (Dual Active Bridge) bidirectional isolated converter.",
            "parameters": ["v1", "v2", "p_rated", "f_sw_khz", "phi_deg"],
        },
        {
            "name": "cascade_design",
            "description": "Design a cascade (multi-stage) converter. Auto-selects stages or accepts explicit list.",
            "parameters": ["v_in", "v_out", "i_out", "stages", "f_sw_khz"],
        },
        {
            "name": "inductor_design",
            "description": "Design a filter inductor: core selection, turns, wire, air gap, losses.",
            "parameters": [
                "inductance_uH", "i_peak", "i_rms", "f_sw_khz",
                "core_shape", "material", "b_max_mT", "j_current_density",
            ],
        },
        {
            "name": "transformer_design",
            "description": "Design a power transformer: core selection, turns, wire, losses.",
            "parameters": [
                "v_pri", "v_sec", "power_W", "f_sw_khz", "duty_cycle",
                "core_shape", "material", "b_max_mT",
            ],
        },
        {
            "name": "topology_recommendation",
            "description": "Recommend suitable converter topology based on specs.",
            "parameters": ["v_in", "v_out", "i_out", "isolated", "bidirectional"],
        },
        {
            "name": "efficiency_estimate",
            "description": "Estimate converter efficiency and loss breakdown.",
            "parameters": [
                "v_in", "v_out", "i_out", "f_sw_khz",
                "rds_on_mohm", "dcr_mohm", "vf_diode",
                "t_rise_ns", "t_fall_ns", "sync_rect",
            ],
        },
    ]
