"""Command line for pea.thermal (JSON in, JSON out).

    python -m pea.thermal dab-case [--quick] [--output DIR]
    python -m pea.thermal cooling-compare --input spec.json [--output out.json] [--no-electrothermal]
    python -m pea.thermal heatsink-pareto --input task.json [--output out.json]
    python -m pea.thermal network --input spec.json [--output out.json]
    python -m pea.thermal electrothermal --input spec.json [--output out.json]

Input layouts (all SI):

cooling-compare: {"t_ambient_C": 40, "devices": [{"name", "power_W", "r_jc", "r_cs", "footprint_area_m2", "tj_max_C", "tj_design_C"}],
                  "options": [{"kind": "natural"|"forced"|"liquid", ...}]}
heatsink-pareto: StageATask fields (see pea.thermal.heatsink_optimisation.StageATask.from_dict)
network:         {"sink": {"r_sa", "t_ambient_C"}, "devices": [{"name", "power_W", "r_jc", "r_cs", "r_spread", "tj_max_C", "tj_design_C",
                  "zth_jc": {"type": "foster", "stages": [{"resistance", "time_constant"}]}}], "transient": {"device", "power_steps": [[t, P]], "times": [...]}}
electrothermal:  {"sink": {...}, "devices": [{"name", "i_rms_A", "f_sw_Hz", "r_jc", "r_cs", "r_spread", "tj_max_C", "tj_design_C",
                  "rds_on": {"r_ref_ohm", "t_ref_C", "r_hot_ohm", "t_hot_C", "kind"}, "fixed_switching_W",
                  "e_off": {"e_ref_J", "t_ref_C", "v_ref_V", "i_ref_A", "t_coeff_per_K"}, "v_off_V", "i_off_A"}], "settings": {...}}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pea.thermal import electrothermal as et
from pea.thermal import network as net


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(data: dict[str, Any], output: Path | None) -> None:
    text = json.dumps(data, indent=2, default=_json_default, allow_nan=False)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text + "\n", encoding="utf-8")
        print(f"written {output}")
    else:
        print(text)


def _json_default(obj: Any) -> Any:
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if hasattr(obj, "item"):
        return obj.item()
    if hasattr(obj, "tolist"):
        return obj.tolist()
    return str(obj)


def cmd_dab_case(args: argparse.Namespace) -> int:
    from pea.thermal.dab_case import run_dab_case

    result = run_dab_case(quick=args.quick, output_dir=args.output)
    print(json.dumps({"loss_estimates": result["loss_estimates"],
                      "cooling_summary": {b: result["cooling_comparison"][b]["summary_table"] for b in result["cooling_comparison"]},
                      "stage_a_flagged": {k: v["flagged_candidates"] for k, v in result["heat_sink_stage_a"].items()},
                      "written_to": result.get("written_to")}, indent=2, default=_json_default))
    return 0


def cmd_cooling_compare(args: argparse.Namespace) -> int:
    from pea.thermal.cooling import CoolingDevice, compare_cooling_options, option_from_dict

    spec = _load(args.input)
    devices = [CoolingDevice.from_dict(d) for d in spec["devices"]]
    options = [option_from_dict(o) for o in spec["options"]]
    result = compare_cooling_options(devices, options, float(spec.get("t_ambient_C", 40.0)), electrothermal=not args.no_electrothermal)
    _dump(result, args.output)
    return 0


def cmd_heatsink_pareto(args: argparse.Namespace) -> int:
    from pea.thermal.heatsink_optimisation import StageATask, run_stage_a

    task = StageATask.from_dict(_load(args.input))
    _dump(run_stage_a(task), args.output)
    return 0


def cmd_network(args: argparse.Namespace) -> int:
    spec = _load(args.input)
    sink = net.SharedHeatSink.from_dict(spec["sink"])
    devices = [net.DeviceThermalPath.from_dict(d) for d in spec["devices"]]
    result: dict[str, Any] = {"steady_state": net.solve_steady_state(devices, sink)}
    if spec.get("transient"):
        tr = spec["transient"]
        device = next(d for d in devices if d.name == tr["device"])
        others = sum(d.power_W for d in devices if d.name != device.name)
        result["transient"] = net.transient_junction_temperature(device, sink, tr["power_steps"], tr["times"], others)
    _dump(result, args.output)
    return 0


def cmd_electrothermal(args: argparse.Namespace) -> int:
    spec = _load(args.input)
    sink = net.SharedHeatSink.from_dict(spec["sink"])
    paths, models = [], []
    for d in spec["devices"]:
        rds = et.RdsOnModel(float(d["rds_on"]["r_ref_ohm"]), float(d["rds_on"]["t_ref_C"]), float(d["rds_on"]["r_hot_ohm"]),
                            float(d["rds_on"]["t_hot_C"]), str(d["rds_on"].get("kind", "linear")))
        e_off = et.SwitchingEnergyModel(**{k: v for k, v in d["e_off"].items()}) if d.get("e_off") else None
        models.append(et.DeviceLossModel.datasheet_default(d["name"], float(d["i_rms_A"]), rds, float(d["f_sw_Hz"]), e_off,
                                                           float(d.get("v_off_V", 0.0)), float(d.get("i_off_A", 0.0)),
                                                           fixed_switching_W=float(d.get("fixed_switching_W", 0.0)),
                                                           extra_W=float(d.get("extra_W", 0.0))))
        paths.append(net.DeviceThermalPath(d["name"], 0.0, float(d["r_jc"]), float(d.get("r_cs", 0.0)), float(d.get("r_spread", 0.0)),
                                           d.get("tj_max_C"), d.get("tj_design_C")))
    settings = et.ElectrothermalSettings(**spec.get("settings", {}))
    result = et.iterate(models, net.make_network_solver(paths, sink), float(spec.get("tj_initial_C", 25.0)), settings)
    final = net.solve_steady_state(paths, sink, {n: v["total_W"] for n, v in result.losses_W.items()})
    _dump({"electrothermal": result.to_dict(), "network_at_converged_losses": final}, args.output)
    return 0 if result.converged else 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m pea.thermal", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    d = sub.add_parser("dab-case", help="run the AIPE 10 kW DAB thermal case study")
    d.add_argument("--quick", action="store_true")
    d.add_argument("--output", type=Path, default=None, help="directory for dab-thermal-case.json")
    d.set_defaults(func=cmd_dab_case)
    for name, func, help_text in (("cooling-compare", cmd_cooling_compare, "compare natural / forced / liquid options"),
                                  ("heatsink-pareto", cmd_heatsink_pareto, "Stage A heat-sink Pareto screening"),
                                  ("network", cmd_network, "steady-state (and transient) shared-sink network"),
                                  ("electrothermal", cmd_electrothermal, "loss(Tj) <-> Tj iteration with datasheet defaults")):
        s = sub.add_parser(name, help=help_text)
        s.add_argument("--input", type=Path, required=True)
        s.add_argument("--output", type=Path, default=None)
        if name == "cooling-compare":
            s.add_argument("--no-electrothermal", action="store_true")
        s.set_defaults(func=func)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, KeyError, OSError, TypeError, ImportError, StopIteration) as exc:
        parser.exit(1, f"error: {exc}\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
