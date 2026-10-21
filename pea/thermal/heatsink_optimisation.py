"""Stage A analytical heat-sink geometry screening for a given device heat load.

Design variables: fin length, width, fin height, fin thickness, fin gap, base
thickness (continuous, from ``heatsink_model.DesignBounds``), material (discrete,
one Pareto run per material) and, for forced air, the volumetric flow (either a
fixed value / fan curve or a bounded design variable). Objectives: thermal
resistance to the hottest footprint, mass, optionally fan power and volume.

The optimiser (seeded differential evolution, weight sweep plus epsilon-
constraint, non-dominated filter) is the corrected HeatSinkOptimisation module;
this layer adds the device network (junction temperatures and feasibility
against the design/absolute limits), merges the per-material fronts and flags
the top candidates for Stage B FEM/CFD verification, which is not performed here.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from pea.thermal import network as net
from pea.thermal._sibling import load_heatsink_model
from pea.thermal.cooling import CoolingDevice

DEFAULT_MATERIALS = ("Al-6063-T5", "Cu-C11000")


@dataclass
class StageATask:
    devices: list[CoolingDevice]
    t_ambient_C: float = 40.0
    cooling: str = "natural"
    materials: tuple[str, ...] = DEFAULT_MATERIALS
    bounds: dict[str, tuple[float, float]] = field(default_factory=dict)
    volumetric_flow: float | None = None
    fan_curve: list[tuple[float, float]] | None = None
    n_fans: int = 1
    fan_efficiency: float = 0.25
    flow_bounds: tuple[float, float] | None = None
    objectives: tuple[str, ...] = ("r_th", "mass")
    seed: int = 1
    n_weights: int = 9
    n_epsilon: int = 7
    maxiter: int = 60
    popsize: int = 12
    n_flag: int = 3
    tj_limit_C: float | None = None  # feasibility limit when a device has no tj_design_C
    emissivity: float = 0.0
    label: str = "stage-A-heat-sink-screening"

    def __post_init__(self) -> None:
        if not self.devices:
            raise ValueError("StageATask needs at least one device")
        if self.cooling not in ("natural", "forced"):
            raise ValueError("cooling must be 'natural' or 'forced'")
        if self.cooling == "forced" and self.volumetric_flow is None and not self.fan_curve and self.flow_bounds is None:
            raise ValueError("forced cooling needs volumetric_flow, fan_curve or flow_bounds")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StageATask":
        devices = [CoolingDevice.from_dict(x) for x in d["devices"]]
        bounds = {k: (float(v[0]), float(v[1])) for k, v in (d.get("bounds") or {}).items()}
        curve = [(float(q), float(p)) for q, p in d["fan_curve"]] if d.get("fan_curve") else None
        fb = d.get("flow_bounds")
        return cls(devices=devices, t_ambient_C=float(d.get("t_ambient_C", 40.0)), cooling=str(d.get("cooling", "natural")),
                   materials=tuple(d.get("materials", DEFAULT_MATERIALS)), bounds=bounds, volumetric_flow=d.get("volumetric_flow"),
                   fan_curve=curve, n_fans=int(d.get("n_fans", 1)), fan_efficiency=float(d.get("fan_efficiency", 0.25)),
                   flow_bounds=(float(fb[0]), float(fb[1])) if fb else None, objectives=tuple(d.get("objectives", ("r_th", "mass"))),
                   seed=int(d.get("seed", 1)), n_weights=int(d.get("n_weights", 9)), n_epsilon=int(d.get("n_epsilon", 7)),
                   maxiter=int(d.get("maxiter", 60)), popsize=int(d.get("popsize", 12)), n_flag=int(d.get("n_flag", 3)),
                   tj_limit_C=d.get("tj_limit_C"), emissivity=float(d.get("emissivity", 0.0)),
                   label=str(d.get("label", "stage-A-heat-sink-screening")))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["devices"] = [x.to_dict() for x in self.devices]
        return d


def _design_bounds(hm: Any, task: StageATask) -> Any:
    kwargs = dict(task.bounds)
    if task.flow_bounds is not None:
        kwargs["volumetric_flow"] = task.flow_bounds
    return hm.DesignBounds(**kwargs)


def _operating_point(hm: Any, task: StageATask) -> Any:
    sources = [hm.HeatSource(d.footprint_area_m2, d.power_W, d.name) for d in task.devices]
    p_tot = sum(s.power for s in sources)
    if task.cooling == "natural":
        return hm.OperatingPoint(t_ambient_C=task.t_ambient_C, cooling="natural", heat_W=p_tot, sources=sources,
                                 emissivity=task.emissivity)
    flow = task.volumetric_flow
    if flow is None and task.flow_bounds is not None:
        flow = task.flow_bounds[1]
    return hm.OperatingPoint(t_ambient_C=task.t_ambient_C, cooling="forced", heat_W=p_tot, sources=sources,
                             volumetric_flow=flow, fan_curve=None if task.flow_bounds else task.fan_curve,
                             n_fans=task.n_fans, fan_efficiency=task.fan_efficiency)


def _junction_check(task: StageATask, perf: dict[str, Any]) -> dict[str, Any]:
    base_by_name = {s["name"]: s["r_base_total"] for s in perf.get("sources", [])}
    sink = net.SharedHeatSink(r_sa=perf["r_convective"], t_ambient_C=task.t_ambient_C)
    paths = [net.DeviceThermalPath(d.name, d.power_W, d.r_jc, d.r_cs, base_by_name.get(d.name, 0.0), d.tj_max_C,
                                   d.tj_design_C if d.tj_design_C is not None else task.tj_limit_C) for d in task.devices]
    result = net.solve_steady_state(paths, sink)
    limit = min((p.tj_design_C for p in paths if p.tj_design_C is not None), default=None)
    feasible = result["all_within_design_limit"] if limit is not None else result["all_within_absolute_limit"]
    return {"tj_max_C": result["t_j_max_C"], "t_sink_C": result["t_sink_C"], "hottest_device": result["hottest_device"],
            "feasible": bool(feasible), "limit_C": limit,
            "margin_K": (limit - result["t_j_max_C"]) if limit is not None else None}


def run_stage_a(task: StageATask) -> dict[str, Any]:
    """Run the Stage A screening and return a JSON-ready dictionary with the merged Pareto set and flagged candidates."""
    hm = load_heatsink_model()
    settings = hm.ParetoSettings(objectives=task.objectives, seed=task.seed, n_weights=task.n_weights,
                                 n_epsilon=task.n_epsilon, maxiter=task.maxiter, popsize=task.popsize)
    bounds = _design_bounds(hm, task)
    op = _operating_point(hm, task)
    fronts: dict[str, Any] = {}
    pooled = []
    for i, material in enumerate(task.materials):
        mat_settings = hm.ParetoSettings(**{**asdict(settings), "seed": task.seed + 1000 * i})
        front = hm.optimise_pareto(op, bounds, material, mat_settings)
        fronts[material] = {"n_points": len(front.points), "n_evaluations": front.n_evaluations, "utopia": front.utopia,
                            "nadir": front.nadir, "scale": front.scale}
        for p in front.points:
            pooled.append((material, p))
    objectives = list(task.objectives)
    merged_points = hm.pareto_filter([p for _, p in pooled], objectives)
    material_of = {id(p): m for m, p in pooled}
    utopia = {o: min(p.objectives[o] for p in merged_points) for o in objectives}
    nadir = {o: max(p.objectives[o] for p in merged_points) for o in objectives}
    scale = {o: (nadir[o] - utopia[o]) if nadir[o] - utopia[o] > 1e-12 else max(abs(utopia[o]), 1e-12) for o in objectives}
    rows = []
    for idx, p in enumerate(merged_points):
        check = _junction_check(task, p.performance)
        distance = sum(((p.objectives[o] - utopia[o]) / scale[o]) ** 2 for o in objectives) ** 0.5
        rows.append({"candidate_id": f"A-{idx:03d}", "material": material_of[id(p)], "variables": p.variables,
                     "objectives": p.objectives, "method": p.method, "junction_check": check,
                     "distance_to_utopia": distance, "fem_verification_recommended": False, "flag_reason": None,
                     "performance_summary": {k: p.performance.get(k) for k in ("delta_T_base_K", "h", "fin_efficiency", "regime",
                                                                                 "pressure_drop_Pa", "fan_electrical_power_W",
                                                                                 "r_convective", "r_spreading_max", "mass_kg",
                                                                                 "envelope_volume_m3", "volumetric_flow")},
                     "warnings": p.performance.get("warnings", [])})
    feasible_rows = [r for r in rows if r["junction_check"]["feasible"]]
    flagged: list[dict[str, Any]] = []

    def flag(row: dict[str, Any] | None, reason: str) -> None:
        if row is None or row["fem_verification_recommended"] or len(flagged) >= task.n_flag:
            return
        row["fem_verification_recommended"] = True
        row["flag_reason"] = reason
        flagged.append(row)

    pool = feasible_rows or rows
    flag(min(pool, key=lambda r: r["distance_to_utopia"]), "knee point (closest to utopia among feasible designs)" if feasible_rows else "knee point (no design met the junction limit)")
    flag(min(pool, key=lambda r: r["objectives"].get("mass", 0.0)), "lightest feasible design" if feasible_rows else "lightest design")
    flag(min(pool, key=lambda r: r["objectives"].get("r_th", 0.0)), "lowest thermal resistance")
    for r in sorted(pool, key=lambda r: r["distance_to_utopia"]):
        flag(r, "next closest to utopia")
    return {"schema": "pea-thermal-stage-a/0.1", "label": task.label, "stage": "A", "method": "analytical screening: HeatSinkOptimisation "
            "heatsink_model Pareto (seeded DE, weight sweep + epsilon-constraint) per material, merged non-dominated set, shared-sink network check",
            "task": task.to_dict(), "fronts_by_material": fronts, "utopia": utopia, "nadir": nadir, "objectives": objectives,
            "n_candidates": len(rows), "n_feasible": len(feasible_rows), "pareto_set": rows,
            "flagged_candidates": [r["candidate_id"] for r in flagged],
            "next_stage": "B: FEM/CFD verification of the flagged candidates (not performed; no FEM or CFD result is claimed here)",
            "disclaimer": "Analytical correlations with the validity notes recorded in each heat-sink evaluation; device powers are the fixed "
                          "values of the task (no electrothermal closure in the screening)."}


__all__ = ["StageATask", "run_stage_a", "DEFAULT_MATERIALS"]
