"""JSON dict interface (aipe_electrical.interfaces.json_io)."""

import json
import math

import pytest

from aipe_electrical.interfaces import json_io

CIRCUIT = {"v1_V": 800, "v2_V": 400, "turns_ratio_np_ns": 2, "f_sw_Hz": 100e3, "l_series_total_H": 35e-6}


def test_analyse_with_power_solves_the_phase_shift():
    report = json_io.analyse_sps({**CIRCUIT, "power_W": 10000})
    assert report["phase_shift_source"] == "solved for power_W"
    assert report["inputs"]["phase_shift_deg"]["value"] == pytest.approx(22.5, abs=1e-9)
    assert report["derived"]["power"]["value"] == pytest.approx(10000.0)
    json.dumps(report)


def test_analyse_with_degrees_or_radians():
    deg = json_io.analyse_sps({**CIRCUIT, "phi_deg": 22.5})
    rad = json_io.analyse_sps({**CIRCUIT, "phi_rad": math.radians(22.5)})
    assert deg["phase_shift_source"] == "phi_deg" and rad["phase_shift_source"] == "phi_rad"
    assert deg["derived"]["power"]["value"] == pytest.approx(rad["derived"]["power"]["value"])


@pytest.mark.parametrize(
    "payload",
    [
        CIRCUIT,  # no phase information
        {**CIRCUIT, "phi_deg": 22.5, "power_W": 10000},  # ambiguous
        {**CIRCUIT, "phi_deg": 95},
        {**CIRCUIT, "power_W": 30000},
        {k: v for k, v in CIRCUIT.items() if k != "f_sw_Hz"} | {"phi_deg": 10},
        {**CIRCUIT, "v1_V": "800", "phi_deg": 10},
    ],
)
def test_analyse_rejects_invalid_payloads(payload):
    with pytest.raises(ValueError):
        json_io.analyse_sps(payload)


def test_design_report_names_the_total_series_inductance():
    report = json_io.design_sps({"v1_V": 800, "v2_V": 400, "power_W": 10000, "f_sw_Hz": 100e3, "phi_deg": 22.5})
    assert report["series_inductance_total_uH"] == pytest.approx(35.0, rel=1e-9)
    assert report["series_inductance_total_H"] == pytest.approx(35e-6, rel=1e-9)
    assert "leakage_inductance_uH" not in report
    assert report["turns_ratio_np_ns"] == pytest.approx(2.0) and report["turns_ratio_ns_np"] == pytest.approx(0.5)
    assert report["turns_ratio_source"].startswith("voltage-matching")
    assert report["series_current_rms_primary_A"] == pytest.approx(13.6775, abs=5e-5)
    assert report["series_current_peak_primary_A"] == pytest.approx(14.2857, abs=5e-5)
    assert report["dc_current_port1_A"] == pytest.approx(12.5) and report["dc_current_port2_A"] == pytest.approx(25.0)
    assert report["power_flow_direction"] == "port1_to_port2"
    zvs = report["zvs_current_direction_conditions"]
    assert zvs["primary"] is True and "necessary" in zvs["evidence"]
    assert "ZVS_status" not in report
    explicit = json_io.design_sps(
        {
            "v1_V": 800,
            "v2_V": 400,
            "power_W": 10000,
            "f_sw_Hz": 100e3,
            "phi_rad": math.radians(22.5),
            "turns_ratio_np_ns": 1.8,
        }
    )
    assert explicit["turns_ratio_source"] == "given" and explicit["voltage_ratio_d"] == pytest.approx(0.9)
    with pytest.raises(ValueError):
        json_io.design_sps({"v1_V": 800, "v2_V": 400, "power_W": 10000, "f_sw_Hz": 100e3})


def test_waveform_payload():
    w = json_io.sps_waveform({**CIRCUIT, "power_W": 10000, "samples_per_period": 16, "origin": "centre"})
    assert len(w["time_s"]) == 17 and w["origin"] == "centre"
    assert w["phi_rad"] == pytest.approx(math.radians(22.5))
    assert w["i_L_A"][0] == pytest.approx(100 / 7, rel=1e-9)


def test_dcdc_designs_and_buck_losses():
    buck = json_io.dcdc_design("buck", {"v_in_V": 12, "v_out_V": 5, "i_out_A": 2, "f_sw_Hz": 100e3})
    assert buck["inductors"][0]["inductance"] == pytest.approx(48.6111e-6, rel=1e-5)
    inverting = json_io.dcdc_design(
        "cuk", {"v_in_V": 12, "v_out_V": -5, "i_out_A": 2, "f_sw_Hz": 100e3, "coupling_ripple_fraction": 0.1}
    )
    assert inverting["output_polarity"] == "negative" and inverting["capacitors"][1][
        "voltage_ripple_pp"
    ] == pytest.approx(1.7)
    with pytest.raises(ValueError):
        json_io.dcdc_design("flyback", {})
    loss = json_io.buck_losses(
        {
            "v_in_V": 12,
            "v_out_V": 5,
            "i_out_A": 2,
            "f_sw_Hz": 100e3,
            "r_ds_on_high_ohm": 0.05,
            "r_dcr_ohm": 0.03,
            "t_rise_s": 20e-9,
            "t_fall_s": 20e-9,
            "v_f_diode_V": 0.5,
        }
    )
    assert loss["total_loss"] == pytest.approx(0.834667, abs=1e-6)
