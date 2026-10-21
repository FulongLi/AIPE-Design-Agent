"""``aipe-electrical`` command line: JSON in (file and/or flags), JSON out (stdout or file).

Examples::

    aipe-electrical dab-sps design --v1 800 --v2 400 --power 10000 --f-sw 100e3 --phi-deg 22.5
    aipe-electrical dab-sps analyse --input examples/dab-10kw-sps.json --output analysis.json
    aipe-electrical dcdc buck --v-in 12 --v-out 5 --i-out 2 --f-sw 100e3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from aipe_electrical import __version__
from aipe_electrical.interfaces import json_io

__all__ = ["build_parser", "main"]

# (flag, JSON key, help)
_SPS_CIRCUIT = [
    ("--v1", "v1_V", "port-1 (primary) DC voltage, V"),
    ("--v2", "v2_V", "port-2 (secondary) DC voltage, V"),
    ("--turns-ratio-np-ns", "turns_ratio_np_ns", "transformer turns ratio N_p/N_s"),
    ("--f-sw", "f_sw_Hz", "switching frequency, Hz"),
    ("--l-series-total", "l_series_total_H", "total primary-referred series inductance, H"),
]
_SPS_PHASE = [
    ("--phi-deg", "phi_deg", "phase shift, degrees (positive: port 1 -> port 2)"),
    ("--phi-rad", "phi_rad", "phase shift, radians"),
    ("--power", "power_W", "signed power, W (the phase shift is solved for it)"),
]
_DCDC = [
    ("--v-in", "v_in_V", "input voltage, V"),
    ("--v-out", "v_out_V", "output voltage magnitude, V"),
    ("--i-out", "i_out_A", "output current, A"),
    ("--f-sw", "f_sw_Hz", "switching frequency, Hz"),
    (
        "--ripple-current-fraction",
        "ripple_current_fraction",
        "peak-to-peak inductor ripple / average inductor current (default 0.3)",
    ),
    (
        "--ripple-voltage-fraction",
        "ripple_voltage_fraction",
        "peak-to-peak output ripple / output voltage (default 0.01)",
    ),
    (
        "--coupling-ripple-fraction",
        "coupling_ripple_fraction",
        "SEPIC/Cuk coupling-capacitor ripple fraction (default 0.05)",
    ),
]
_BUCK_LOSSES = [
    ("--v-in", "v_in_V", "input voltage, V"),
    ("--v-out", "v_out_V", "output voltage, V"),
    ("--i-out", "i_out_A", "output current, A"),
    ("--f-sw", "f_sw_Hz", "switching frequency, Hz"),
    ("--r-ds-on-high", "r_ds_on_high_ohm", "high-side R_DS(on), ohm"),
    ("--r-ds-on-low", "r_ds_on_low_ohm", "low-side R_DS(on), ohm (synchronous rectifier)"),
    ("--v-f-diode", "v_f_diode_V", "freewheeling diode forward voltage, V (diode rectifier)"),
    ("--r-dcr", "r_dcr_ohm", "inductor DC resistance, ohm"),
    ("--t-rise", "t_rise_s", "voltage/current overlap rise time, s"),
    ("--t-fall", "t_fall_s", "voltage/current overlap fall time, s"),
    ("--ripple-current-pp", "ripple_current_pp_A", "peak-to-peak inductor ripple, A (default 0)"),
]


def _add_io(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--input", type=Path, help="JSON file with the input keys (flags override its values)")
    parser.add_argument("--output", type=Path, help="write the JSON result to this file instead of stdout")


def _add_flags(parser: argparse.ArgumentParser, flags: list[tuple[str, str, str]]) -> None:
    for flag, key, help_text in flags:
        parser.add_argument(flag, dest=key, type=float, default=None, help=help_text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aipe-electrical",
        description="AIPE Electrical Design: analytical converter models with explicit SI units (JSON output).",
    )
    parser.add_argument("--version", action="version", version=f"aipe-electrical {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    sps = commands.add_parser("dab-sps", help="lossless single-phase-shift dual-active-bridge analysis")
    sps_cmd = sps.add_subparsers(dest="sps_command", required=True)
    analyse = sps_cmd.add_parser("analyse", help="operating-point report for given circuit and phase shift or power")
    _add_io(analyse)
    _add_flags(analyse, _SPS_CIRCUIT + _SPS_PHASE)
    design = sps_cmd.add_parser("design", help="size the total series inductance for a power at a phase shift")
    _add_io(design)
    _add_flags(design, [f for f in _SPS_CIRCUIT if f[1] != "l_series_total_H"] + _SPS_PHASE)
    waveform = sps_cmd.add_parser("waveform", help="sampled v_ab, n*v_cd, v_L and i_L over one period")
    _add_io(waveform)
    _add_flags(waveform, _SPS_CIRCUIT + _SPS_PHASE)
    waveform.add_argument(
        "--samples", dest="samples_per_period", type=int, default=None, help="samples per period (default 400)"
    )
    waveform.add_argument(
        "--origin", choices=["rising_edge", "centre"], default=None, help="time origin (default rising_edge)"
    )

    dc = commands.add_parser("dcdc", help="continuous-conduction-mode sizing of basic DC-DC converters")
    dc.add_argument("topology", choices=list(json_io.DCDC_TOPOLOGIES))
    _add_io(dc)
    _add_flags(dc, _DCDC)

    buck = commands.add_parser("buck-losses", help="first-order hard-switched buck loss estimate")
    _add_io(buck)
    _add_flags(buck, _BUCK_LOSSES)
    return parser


def _payload(args: argparse.Namespace, keys: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if getattr(args, "input", None) is not None:
        loaded = json.loads(Path(args.input).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("the --input JSON document must be an object")
        payload.update(loaded)
    for key in keys:
        value = getattr(args, key, None)
        if value is not None:
            payload[key] = value
    return payload


def _run(args: argparse.Namespace) -> dict:
    if args.command == "dab-sps":
        keys = [key for _, key, _ in _SPS_CIRCUIT + _SPS_PHASE]
        if args.sps_command == "analyse":
            return json_io.analyse_sps(_payload(args, keys))
        if args.sps_command == "design":
            return json_io.design_sps(_payload(args, keys))
        payload = _payload(args, keys + ["samples_per_period", "origin"])
        return json_io.sps_waveform(payload)
    if args.command == "dcdc":
        return json_io.dcdc_design(args.topology, _payload(args, [key for _, key, _ in _DCDC]))
    return json_io.buck_losses(_payload(args, [key for _, key, _ in _BUCK_LOSSES]))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = _run(args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(result, indent=2)
    if args.output is not None:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
