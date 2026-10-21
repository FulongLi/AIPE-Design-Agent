# Models, derivations and conventions

All quantities are SI (V, A, Hz, H, F, s, rad, W) unless a name carries a unit suffix
(JSON keys such as `series_inductance_total_uH`). Every result is an exact consequence of
the stated idealised model; none is a simulated or measured value.

## 1. Lossless single-phase-shift dual active bridge — `aipe_electrical.converters.dab_sps`

### 1.1 Circuit, symbols and sign conventions

| Symbol / field | Meaning |
| --- | --- |
| `v1`, `v2` | Port-1 (primary-side) and port-2 (secondary-side) DC voltages, stiff. |
| `turns_ratio_np_ns` = n | Transformer turns ratio N_p/N_s. `turns_ratio_ns_np` = 1/n is derived, never an input. |
| V2' = n·V2 | Port-2 voltage referred to the primary (`v2_primary_referred`). |
| d = V2'/V1 | Voltage conversion ratio (`d`); d = 1 is the matched case. `matched_turns_ratio_np_ns(v1, v2)` = V1/V2. |
| `l_series_total` = L | **Total** series inductance referred to the primary: L = L_ext,p + L_lk,p + n²·(L_ext,s + L_lk,s). Build it with `total_series_inductance_primary(...)`. The transformer leakage alone is only part of L. |
| `f_sw`, T = 1/f_sw | Switching frequency and period. |
| `phi_rad` = φ | Phase shift of the secondary bridge voltage v_cd relative to the primary v_ab, electrical radians; t_φ = φ·T/(2π). `phi_deg` is derived; `SpsOperatingPoint.from_degrees` converts. |
| i_L | Series-inductor current flowing from bridge-1 node *a* towards the transformer primary; the secondary current is i_s = n·i_L. |

Both bridges apply 50 % duty square waves: v_ab = ±V1, v_cd = ±V2. **φ > 0 means the secondary lags and
power flows from port 1 to port 2 (P > 0); φ < 0 reverses the flow** (`power_flow_direction`). The
admissible range is |φ| ≤ π/2 (`phase_shift_limits`); larger values are rejected because SPS power is
not monotonic beyond it.

Two time origins are offered: `"rising_edge"` puts t = 0 at the −V1 → +V1 transition of v_ab;
`"centre"` puts t = 0 at the centre of the positive v_ab half-cycle (convention of the AIPE ngspice
DAB generator), i.e. a shift of T/4.

### 1.2 Power

The inductor voltage is v_L = v_ab − n·v_cd, so i_L is piecewise linear. Averaging v_ab·i_L over
one period gives the classical result

    P(φ) = V1·V2'·φ·(π − |φ|)·sgn(φ) / (2·π²·f_sw·L),      |φ| ≤ π/2
    P_max = V1·V2' / (8·f_sw·L)                              at |φ| = π/2

Inverse relations used by the package:

* `phase_shift_for_power`: with c = 2π²·f_sw·L·|P| / (V1·V2'), the smaller root of φ(π − φ) = c is
  φ = (π − √(π² − 4c)) / 2, signed like P. |P| > P_max raises `ValueError`.
* `series_inductance_for_power`: L = V1·V2'·|φ|·(π − |φ|) / (2π²·f_sw·|P|); φ and P must share the sign.
* `design_for_power` sizes L for a power at a phase shift, using the matched turns ratio V1/V2 when
  none is given (replacement of the historical `dab_design`).

### 1.3 Exact current waveform

With the rising-edge origin and 0 ≤ t_φ ≤ T/2 the first half period has two linear segments:

| Interval | v_ab | n·v_cd | di_L/dt |
| --- | --- | --- | --- |
| 0 ≤ t < t_φ | +V1 | −V2' | (V1 + V2') / L |
| t_φ ≤ t < T/2 | +V1 | +V2' | (V1 − V2') / L |

Half-wave antisymmetry i(t + T/2) = −i(t) fixes the starting value
i(0) = −½·[(V1 + V2')·t_φ + (V1 − V2')·(T/2 − t_φ)] / L. Negative φ is handled by the same periodic
construction (`breakpoints`). RMS, mean and peak are exact integrals of the linear segments
(`analysis.waveforms`: a segment from a to b over Δt contributes Δt·(a² + ab + b²)/3 to ∫i²; the peak
lies on a breakpoint). `power_from_waveform` recomputes P as V1 times the mean of i_L over the
positive v_ab half and must equal the closed form (checked in the tests for d ∈ {0.6, 1, 1.4} and seven
phase shifts).

Matched case (d = 1) closed forms: I_peak = V1·t_φ / L, I_rms = I_peak·√[(t_φ/3 + T/2 − t_φ) / (T/2)].

### 1.4 Switching-instant currents and the ZVS current-direction condition

The primary bridge switches at the rising edge of v_ab (t = 0); zero-voltage turn-on of the incoming
devices requires current flowing into node *a*, i.e. **i_L(0) < 0**. The secondary bridge switches at
t = t_φ and needs **n·i_L(t_φ) > 0**. Substituting the waveform gives the classical boundaries, valid
for both power-flow directions (`zvs_phase_shift_limits`, minimum |φ|):

    primary:   |φ| > π·(1 − 1/d)/2   (binding for d > 1)
    secondary: |φ| > π·(1 − d)/2     (binding for d < 1)

These are **necessary current-direction conditions of the lossless model only**. A real ZVS
verification needs the device output charge (non-linear C_oss), the dead time and the magnetising
current, none of which is modelled. Therefore every ZVS output carries the evidence label
`ZVS_EVIDENCE_LABEL` and the fields are called `*_zvs_current_direction_ok`; the package never reports
"ZVS confirmed" or "achievable".

### 1.5 Assumptions and validity

Ideal switches, zero dead time, no conduction or switching loss, stiff DC ports, ideal transformer
(L_m → ∞, magnetising current neglected), all series inductance lumped and referred to the primary,
|φ| ≤ π/2. Results are analytical references that executed circuit simulations are compared against;
they are not validations of a hardware design.

### 1.6 Benchmark (AIPE 10 kW DAB)

800 V → 400 V, N_p/N_s = 2 (d = 1), 100 kHz, L = 35 µH total primary-referred:

| Quantity | Value |
| --- | --- |
| φ for 10 kW | 22.5° exactly (t_φ = T/16) |
| P_max | 22 857.14 W |
| I_DC port 1 / port 2 | 12.5 A / 25 A |
| I_L peak (primary) | 100/7 A = 14.2857 A |
| I_L rms (primary) | (100/7)·√(11/12) A = 13.6775 A |
| Switching currents | i_L(0) = −14.2857 A, i_L(t_φ) = +14.2857 A: both current-direction conditions met |

Reproduced by `tests/test_dab_sps.py`, `tests/test_json_io.py` and `tests/test_cli.py`.

## 2. CCM DC-DC sizing — `aipe_electrical.analysis.dcdc`

Ideal lossless converters in steady-state continuous conduction with the small-ripple approximation;
ESR/ESL neglected. ΔI is the peak-to-peak ripple of the *inductor's own* average current
(`ripple_current_fraction`, default 0.3), ΔV the peak-to-peak output ripple (`ripple_voltage_fraction`,
default 0.01). Inductor RMS = √(I_avg² + ΔI²/12), peak = I_avg + ΔI/2.

| Topology | Duty D | Inductor average | Inductance | Output capacitance | Coupling capacitor |
| --- | --- | --- | --- | --- | --- |
| Buck | V_o/V_in | I_o | V_o(1−D)/(f·ΔI) | ΔI/(8·f·ΔV) | — |
| Boost | 1 − V_in/V_o | I_o·V_o/V_in | V_in·D/(f·ΔI) | I_o·D/(f·ΔV) | — |
| Inverting buck-boost | V_o/(V_in+V_o) | I_o/(1−D) | V_in·D/(f·ΔI) | I_o·D/(f·ΔV) | — |
| SEPIC | V_o/(V_in+V_o) | L1: I_o·V_o/V_in, L2: I_o | V_in·D/(f·ΔI) each | I_o·D/(f·ΔV) | at V_in, I_o·D/(f·ΔV_c) |
| Cuk (inverting) | V_o/(V_in+V_o) | L1: I_o·V_o/V_in, L2: I_o | V_in·D/(f·ΔI) each (= V_o(1−D)/(f·ΔI₂)) | ΔI₂/(8·f·ΔV) | at V_in+V_o, I_o·D/(f·ΔV_c) |

V_o is the output magnitude; `output_polarity` marks the inverting topologies. ΔV_c =
`coupling_ripple_fraction` (default 0.05) times the coupling-capacitor DC voltage.

## 3. First-order buck losses — `aipe_electrical.analysis.losses`

Hard-switched buck in CCM: D = V_o/V_in, I_L,rms = √(I_o² + ΔI²/12) (ΔI = `ripple_current_pp`, 0 by
default), P_hs = D·I_L,rms²·R_DS(on),hs, P_ls = (1−D)·I_L,rms²·R_DS(on),ls (synchronous) or
(1−D)·I_o·V_f (diode), P_dcr = I_L,rms²·R_dcr, P_sw = ½·V_in·I_o·(t_rise + t_fall)·f_sw (linear
voltage/current overlap at the high-side switch), η = P_o/(P_o + ΣP). Not modelled: gate drive, C_oss
energy, reverse recovery, dead-time conduction, core loss, temperature dependence.

## 4. SPS design-space sweep and Pareto helpers — `aipe_electrical.optimisation`

`dab_sps_sweep.sweep_sps_designs` evaluates the lossless SPS model on every combination of switching
frequency, N_p/N_s and total series inductance for a required signed power, skipping combinations
with |P| > P_max. Each point records φ, RMS/peak currents on both sides, the SPS power headroom
P_max/|P| and the two ZVS current-direction flags. `pareto_sps_designs` applies the generic
`pareto.pareto_front` to named objectives (`i_rms_primary` min, `i_peak_primary` min,
`abs_phase_shift` max as a control-margin proxy, `power_headroom` max). This is an analytical
screening of electrical operating points; losses, magnetics, thermal behaviour and cost are not
modelled, so it is not a converter optimiser.

## References

- R. W. De Doncker, D. M. Divan, M. H. Kheraluwala, "A three-phase soft-switched high-power-density
  DC/DC converter for high-power applications," *IEEE Trans. Ind. Appl.*, vol. 27, no. 1, 1991.
- M. N. Kheraluwala, R. W. Gascoigne, D. M. Divan, E. D. Baumann, "Performance characterization of a
  high-power dual active bridge DC-to-DC converter," *IEEE Trans. Ind. Appl.*, vol. 28, no. 6, 1992.
- R. W. Erickson, D. Maksimović, *Fundamentals of Power Electronics*, 3rd ed., Springer, 2020
  (CCM analysis of buck, boost, buck-boost, SEPIC and Cuk converters).
