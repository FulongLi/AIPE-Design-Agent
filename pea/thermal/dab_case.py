"""AIPE 10 kW DAB (800 V -> 400 V, 100 kHz) thermal case study: inputs, assumptions and runner.

Sources (see ``SOURCES``):

* AIPE executed waveform summary ``runs/dab-l1-nominal-ic/summary.json`` -- per-switch
  RMS and turn-off currents, ZVS current condition (AIPE result).
* TI TIDA-010054 fact sheet (TIDUES0) -- reference design figures used only as
  sourced reference values: C3M0075120K 75 mOhm / Rth,JC 1.1 K/W, C3M0030090K
  30 mOhm / Rth,JC 0.48 K/W, Ohmite CR201-50VE 0.5 K/W, pads 0.1 K/W, 40 degC
  ambient, calculated 54 W turn-off loss at 10 kW.
* SiC shortlist -- C3M0040120K datasheet R_DS(on) 40 mOhm (25 degC) / 68 mOhm
  (175 degC), the only same-family hot/cold pair available in the reference files.

Everything derived from these numbers is labelled either an AIPE analytical
estimate or an explicit assumption; the 54 W / 8 turn-off placeholder is a
reference-design figure to be replaced by the semiconductor-database evaluator.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pea.thermal import electrothermal as et
from pea.thermal import network as net
from pea.thermal.cooling import (CoolingDevice, ForcedAirOption, LiquidColdPlateOption, NaturalConvectionOption,
                                 PlateFinGeometry, compare_cooling_options)
from pea.thermal.heatsink_optimisation import StageATask, run_stage_a

SOURCES = {
    "aipe_waveforms": "runs/dab-l1-nominal-ic/summary.json (AIPE executed ngspice waveforms, steady state, dataset sha256 f1d558d0...)",
    "ti_fact_sheet": "AIPE-Workflows/examples/dab-10kw/references/tida-010054-fact-sheet.md (TIDUES0 Rev F, BOM TIDRZW1B)",
    "sic_shortlist": "AIPE-Workflows/examples/dab-10kw/references/sic-device-shortlist.md (manufacturer datasheets)",
}

# AIPE waveform results (per switch), from summary.json
PRIMARY_I_RMS_A = 9.67  # S1-S4 current_rms 9.669-9.675 A
PRIMARY_I_OFF_A = 14.26  # turn_off_current mean_abs 14.256-14.261 A at 800 V
SECONDARY_I_RMS_A = 19.75  # S5-S8 current_rms 19.742-19.755 A
SECONDARY_I_OFF_A = 32.5  # turn_off_current mean_abs 32.50-32.52 A at 400 V
F_SW_HZ = 100e3
V_PRIMARY_V = 800.0
V_SECONDARY_V = 400.0
ZVS_TURN_ON = True  # zvs_overview: all eight switches meet the current-direction condition

# TI reference values (sourced, not AIPE results)
TI_RDS_PRIMARY_25C_OHM = 0.075  # C3M0075120K typ
TI_RDS_SECONDARY_25C_OHM = 0.030  # C3M0030090K typ
TI_RTH_JC_PRIMARY = 1.1
TI_RTH_JC_SECONDARY = 0.48
TI_PAD_K_PER_W = 0.1  # CD-02-05-247
TI_SINK_K_PER_W = 0.5  # Ohmite CR201-50VE catalogue value (rating condition not stated in the fact sheet)
TI_TURN_OFF_LOSS_W = 54.0  # calculated at 10 kW, TI operating point, all eight devices
TI_AMBIENT_C = 40.0
TI_DEVICES = 8

# Same-family hot/cold R_DS(on) pair from the shortlist (C3M0040120K): 40 mOhm at 25 degC, 68 mOhm typ at 175 degC
FAMILY_HOT_FACTOR_175C = 68.0 / 40.0
TJ_EVAL_C = 125.0
TJ_DESIGN_C = 125.0  # design target (assumption: common derating for SiC)
TJ_MAX_C = 175.0  # Wolfspeed Gen 3 datasheet maximum (shortlist parts); applied to the TI parts as a family assumption
TO247_FOOTPRINT_M2 = 16e-3 * 20e-3  # generic TO-247 contact outline (assumption)

ASSUMPTIONS = [
    "Primary switch conduction loss = I_rms^2 R_DS(on): I_rms = 9.67 A from the AIPE waveform summary; R_DS(on) 75 mOhm typ at 25 degC "
    "for C3M0075120K from the TI fact sheet.",
    f"No R_DS(on) temperature factor for C3M0075120K or C3M0030090K exists in the reference files. The same-family Wolfspeed Gen 3 "
    f"ratio 68/40 = {FAMILY_HOT_FACTOR_175C:.2f} at 175 degC (C3M0040120K datasheet, shortlist) is used as a proxy and interpolated "
    f"linearly: factor {1 + (FAMILY_HOT_FACTOR_175C - 1) * (TJ_EVAL_C - 25) / 150:.3f} at 125 degC. ASSUMPTION to be replaced by the "
    "device's own datasheet curve.",
    f"Turn-off loss per device = TI's calculated {TI_TURN_OFF_LOSS_W:.0f} W / {TI_DEVICES} = {TI_TURN_OFF_LOSS_W / TI_DEVICES:.2f} W: "
    "reference-design figure (TI operating point 800 V -> 500 V, n = 1.6), temperature independent here, to be replaced by the "
    "semiconductor-database evaluator (E_off at 14.26 A / 32.5 A, Tj).",
    "Turn-on loss = 0: all eight switches satisfy the ZVS current-direction condition in the executed AIPE waveform; a charge-based "
    "ZVS check (Coss, dead time) is still pending.",
    "Secondary switches: C3M0030090K 30 mOhm typ (TI fact sheet) with the same proxy temperature factor; I_rms = 19.75 A (AIPE).",
    f"Rth,JC 1.1 / 0.48 K/W and 0.1 K/W pads from the TI fact sheet; TO-247 footprint {TO247_FOOTPRINT_M2 * 1e6:.0f} mm^2 (generic outline).",
    f"Junction limits: design target {TJ_DESIGN_C:.0f} degC (assumption), absolute {TJ_MAX_C:.0f} degC (Gen 3 family datasheet value).",
    f"Ambient {TI_AMBIENT_C:.0f} degC as in the TI design guide; one heat sink per bridge (four devices) for the cooling comparison.",
    "Cooling option geometries (natural: Al 200 x 200 mm base, 80 mm fins; forced: Al 100 x 100 mm, 40 mm fins, two 60 mm fans; liquid: "
    "Al 100 x 100 mm plate with 16 mini-channels 3 x 5 mm, water 2 L/min), the generic 60 mm fan curve, the fan efficiency 0.25, the "
    "coolant inlet 45 degC (ambient + 5 K radiator approach) and the pump efficiency 0.3 are assumptions for the comparison; fan/pump "
    "datasheets replace them.",
    "Gate-drive, Coss and body-diode losses are not included.",
]


def hot_factor(tj_C: float) -> float:
    """Linear interpolation of the same-family proxy factor between 25 degC (1.0) and 175 degC (1.70)."""
    return 1.0 + (FAMILY_HOT_FACTOR_175C - 1.0) * (tj_C - 25.0) / 150.0


def rds_on_models() -> dict[str, et.RdsOnModel]:
    return {
        "primary": et.RdsOnModel(TI_RDS_PRIMARY_25C_OHM, 25.0, TI_RDS_PRIMARY_25C_OHM * FAMILY_HOT_FACTOR_175C, 175.0, "linear",
                                 source="C3M0075120K 75 mOhm typ (TI fact sheet); hot factor 68/40 at 175 degC from C3M0040120K (shortlist) -- family proxy assumption"),
        "secondary": et.RdsOnModel(TI_RDS_SECONDARY_25C_OHM, 25.0, TI_RDS_SECONDARY_25C_OHM * FAMILY_HOT_FACTOR_175C, 175.0, "linear",
                                   source="C3M0030090K 30 mOhm typ (TI fact sheet); same proxy hot factor"),
    }


def loss_estimates(tj_C: float = TJ_EVAL_C) -> dict[str, Any]:
    """Per-switch loss estimates at ``tj_C`` with the stated placeholders."""
    models = rds_on_models()
    off_placeholder = TI_TURN_OFF_LOSS_W / TI_DEVICES
    out = {}
    for bridge, i_rms in (("primary", PRIMARY_I_RMS_A), ("secondary", SECONDARY_I_RMS_A)):
        r25 = models[bridge].r_ref_ohm
        cond25 = i_rms ** 2 * r25
        cond = i_rms ** 2 * models[bridge](tj_C)
        out[bridge] = {"i_rms_A": i_rms, "rds_on_25C_ohm": r25, "rds_on_factor": models[bridge].factor(tj_C), "rds_on_ohm": models[bridge](tj_C),
                       "conduction_25C_W": cond25, "conduction_W": cond, "turn_off_W": off_placeholder, "turn_on_W": 0.0,
                       "total_W": cond + off_placeholder, "tj_C": tj_C,
                       "turn_off_note": "reference-design figure (TI 54 W / 8 devices), to be replaced by the semiconductor-database evaluator"}
    out["bridge_totals_W"] = {b: 4 * out[b]["total_W"] for b in ("primary", "secondary")}
    out["converter_total_W"] = sum(out["bridge_totals_W"].values())
    return out


def build_devices(bridge: str, with_loss_models: bool = True) -> list[CoolingDevice]:
    """Four devices of one bridge as ``CoolingDevice`` objects with datasheet-default loss models."""
    models = rds_on_models()
    est = loss_estimates()
    if bridge == "primary":
        i_rms, r_jc, names = PRIMARY_I_RMS_A, TI_RTH_JC_PRIMARY, ("S1", "S2", "S3", "S4")
        desc = "C3M0075120K-class primary switch: I_rms^2 R_DS(on)(Tj) + 6.75 W turn-off placeholder"
    elif bridge == "secondary":
        i_rms, r_jc, names = SECONDARY_I_RMS_A, TI_RTH_JC_SECONDARY, ("S5", "S6", "S7", "S8")
        desc = "C3M0030090K-class secondary switch: I_rms^2 R_DS(on)(Tj) + 6.75 W turn-off placeholder"
    else:
        raise ValueError("bridge must be 'primary' or 'secondary'")
    devices = []
    for n in names:
        model = et.DeviceLossModel.datasheet_default(n, i_rms, models[bridge], F_SW_HZ, fixed_switching_W=TI_TURN_OFF_LOSS_W / TI_DEVICES,
                                                     description=desc, sources=[SOURCES["aipe_waveforms"], SOURCES["ti_fact_sheet"]])
        devices.append(CoolingDevice(n, est[bridge]["total_W"], r_jc, TI_PAD_K_PER_W, TO247_FOOTPRINT_M2, TJ_MAX_C, TJ_DESIGN_C,
                                     model if with_loss_models else None, note=desc))
    return devices


def cooling_options() -> list[Any]:
    """Representative cooling options for one bridge (assumed geometries; see ASSUMPTIONS)."""
    natural = NaturalConvectionOption(PlateFinGeometry(0.20, 0.20, 0.08, 0.002, 0.008, 0.008, "Al-6063-T5"), name="natural-convection-Al-200x200x88")
    fan_curve = [(0.0, 50.0), (0.005, 35.0), (0.009, 15.0), (0.011, 0.0)]  # generic 60 mm axial fan (assumption)
    forced = ForcedAirOption(PlateFinGeometry(0.10, 0.10, 0.04, 0.0015, 0.003, 0.006, "Al-6063-T5"), name="forced-air-Al-100x100x46-2-fans",
                             fan_curve=fan_curve, n_fans=2, fan_efficiency=0.25)
    liquid = LiquidColdPlateOption(length=0.10, width=0.10, base_thickness=0.004, n_channels=16, channel_width=0.003, channel_height=0.005,
                                   wall_thickness=0.0025, coolant_inlet_C=45.0, volumetric_flow=2.0 / 60000.0, name="liquid-cold-plate-Al-100x100-16-minichannels-water-2lpm",
                                   lid_thickness=0.003, material="Al-6063-T5", coolant="water", pump_efficiency=0.3)
    return [natural, forced, liquid]


def ti_reference_network(est: dict[str, Any]) -> dict[str, Any]:
    """Cross-check with TI's reference resistances (0.5 K/W sink, 2 FETs per sink, 0.1 K/W pads) and the AIPE loss estimates."""
    out = {}
    for bridge in ("primary", "secondary"):
        p = est[bridge]["total_W"]
        r_jc = TI_RTH_JC_PRIMARY if bridge == "primary" else TI_RTH_JC_SECONDARY
        paths = [net.DeviceThermalPath(f"{bridge}-{i}", p, r_jc, TI_PAD_K_PER_W, 0.0, TJ_MAX_C, TJ_DESIGN_C) for i in range(2)]
        res = net.solve_steady_state(paths, net.SharedHeatSink(TI_SINK_K_PER_W, TI_AMBIENT_C, "Ohmite CR201-50VE (0.5 K/W catalogue)"))
        out[bridge] = {"devices_per_sink": 2, "power_per_device_W": p, "t_sink_C": res["t_sink_C"], "t_j_C": res["t_j_max_C"],
                       "allowable_power_per_device_W_at_125C": net.allowable_power(paths[0], net.SharedHeatSink(TI_SINK_K_PER_W, TI_AMBIENT_C), p, TJ_DESIGN_C)}
    out["note"] = ("Uses TI's catalogue heat-sink and pad resistances with the AIPE loss estimates; the 0.5 K/W rating condition "
                   "(airflow) is not stated in the fact sheet, so this is a reference cross-check, not an AIPE cooling result.")
    return out


def run_dab_case(quick: bool = False, output_dir: str | Path | None = None) -> dict[str, Any]:
    """Run losses -> cooling comparison (both bridges) -> Stage A heat-sink Pareto screening for the secondary bridge."""
    est = loss_estimates()
    comparison = {bridge: compare_cooling_options(build_devices(bridge), cooling_options(), TI_AMBIENT_C, electrothermal=True)
                  for bridge in ("primary", "secondary")}
    sec_devices = build_devices("secondary", with_loss_models=False)
    common = dict(devices=sec_devices, t_ambient_C=TI_AMBIENT_C, tj_limit_C=TJ_DESIGN_C)
    if quick:
        knobs = dict(n_weights=3, n_epsilon=2, maxiter=8, popsize=6)
    else:
        knobs = dict(n_weights=9, n_epsilon=7, maxiter=60, popsize=12)
    natural_task = StageATask(cooling="natural", label="secondary-bridge-natural-convection",
                              bounds={"length": (0.10, 0.30), "width": (0.10, 0.30), "fin_height": (0.03, 0.12), "fin_thickness": (0.0015, 0.005),
                                      "fin_gap": (0.004, 0.015), "base_thickness": (0.004, 0.012)}, seed=11, **common, **knobs)
    forced_task = StageATask(cooling="forced", label="secondary-bridge-forced-air-variable-flow",
                             bounds={"length": (0.06, 0.20), "width": (0.06, 0.20), "fin_height": (0.02, 0.08), "fin_thickness": (0.001, 0.004),
                                     "fin_gap": (0.002, 0.008), "base_thickness": (0.003, 0.010)}, flow_bounds=(0.003, 0.03),
                             objectives=("r_th", "mass", "fan_power_W"), seed=21, n_weights=(6 if quick else 24), n_epsilon=0,
                             maxiter=knobs["maxiter"], popsize=knobs["popsize"], devices=sec_devices, t_ambient_C=TI_AMBIENT_C, tj_limit_C=TJ_DESIGN_C)
    stage_a = {"natural": run_stage_a(natural_task), "forced": run_stage_a(forced_task)}
    result = {"schema": "aipe-dab-thermal-case/0.1", "case": "AIPE 10 kW DAB 800 V -> 400 V, 100 kHz, nominal operating point",
              "sources": SOURCES, "assumptions": ASSUMPTIONS,
              "aipe_waveform_inputs": {"primary_i_rms_A": PRIMARY_I_RMS_A, "primary_turn_off_A": PRIMARY_I_OFF_A, "secondary_i_rms_A": SECONDARY_I_RMS_A,
                                       "secondary_turn_off_A": SECONDARY_I_OFF_A, "f_sw_Hz": F_SW_HZ, "zvs_turn_on_all_switches": ZVS_TURN_ON},
              "loss_estimates": est, "ti_reference_network_cross_check": ti_reference_network(est),
              "cooling_comparison": comparison, "heat_sink_stage_a": stage_a, "quick_mode": quick,
              "disclaimer": "Analytical screening (correlations with stated validity, shared-sink network, electrothermal loop). No CFD, FEM or "
                            "measured results; the turn-off placeholder and the R_DS(on) temperature factor are assumptions listed above."}
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        result["written_to"] = str(out / "dab-thermal-case.json")
        (out / "dab-thermal-case.json").write_text(json.dumps(result, indent=2, default=_json_default), encoding="utf-8")
    return result


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "item"):
        return obj.item()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    return str(obj)


__all__ = ["SOURCES", "ASSUMPTIONS", "hot_factor", "rds_on_models", "loss_estimates", "build_devices", "cooling_options",
           "ti_reference_network", "run_dab_case"]
