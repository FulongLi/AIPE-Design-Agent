"""Cooling-concept comparison: natural convection, forced air and liquid cold plate (SI units).

The air-side models (Elenbaas/Bar-Cohen natural convection, Teertstra-Yovanovich-
Culham channel flow, pressure drop, fan operating point, fin efficiency, Lee et
al. spreading) are imported from the corrected ``heatsink_model`` of the sibling
HeatSinkOptimisation checkout (CC BY 4.0; located through ``HEATSINK_OPT_DIR`` or
``../HeatSinkOptimisation``). The liquid cold plate uses the same fin, spreading
and duct correlations (laminar Shah-London Nusselt, Gnielinski or Dittus-Boelter
when turbulent) with coolant properties, coolant temperature rise, pressure drop
and pumping power implemented here.

Every option is evaluated the same way: sink model -> shared-sink thermal
network (``pea.thermal.network``) -> junction temperatures, optionally closed
with the electrothermal loop (``pea.thermal.electrothermal``) when the devices
carry loss models. Quantitative outputs: max Tj, resistances, volume, mass,
auxiliary (fan/pump) power, pressure drop. Qualitative criteria (acoustic,
reliability, isolation, leakage, condensation, ...) are returned as explicit
review items, not as numbers. Nothing here is a CFD or FEM result.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Sequence

from pea.thermal import electrothermal as et
from pea.thermal import network as net
from pea.thermal._sibling import load_heatsink_model

T0_K = 273.15


# ------------------------------------------------------------------- devices


@dataclass
class CoolingDevice:
    """A power device mounted on the cooling solution."""

    name: str
    power_W: float  # loss at the evaluation junction temperature when no loss model is attached
    r_jc: float  # K/W junction-to-case
    r_cs: float  # K/W case-to-sink interface (pad, grease)
    footprint_area_m2: float  # contact area on the base plate
    tj_max_C: float | None = None
    tj_design_C: float | None = None
    loss_model: et.DeviceLossModel | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.power_W < 0 or self.r_jc < 0 or self.r_cs < 0 or self.footprint_area_m2 <= 0:
            raise ValueError("CoolingDevice needs power >= 0, resistances >= 0 and a positive footprint")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CoolingDevice":
        return cls(name=str(d["name"]), power_W=float(d["power_W"]), r_jc=float(d["r_jc"]), r_cs=float(d.get("r_cs", 0.0)),
                   footprint_area_m2=float(d["footprint_area_m2"]), tj_max_C=d.get("tj_max_C"), tj_design_C=d.get("tj_design_C"),
                   note=str(d.get("note", "")))

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in asdict(self).items() if k != "loss_model"}
        d["loss_model"] = self.loss_model.description if self.loss_model else None
        return d


# ------------------------------------------------------------------- options


@dataclass
class PlateFinGeometry:
    """Plate-fin heat sink dimensions (m) mirroring ``heatsink_model.PlateFinHeatSink``."""

    length: float
    width: float
    fin_height: float
    fin_thickness: float
    fin_gap: float
    base_thickness: float
    material: str = "Al-6063-T5"

    def to_sink(self, hm: Any) -> Any:
        return hm.PlateFinHeatSink(self.length, self.width, self.fin_height, self.fin_thickness, self.fin_gap,
                                   self.base_thickness, self.material)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PlateFinGeometry":
        return cls(**{k: (float(v) if k != "material" else str(v)) for k, v in d.items()})


@dataclass
class NaturalConvectionOption:
    geometry: PlateFinGeometry
    name: str = "natural-convection"
    emissivity: float = 0.0
    orientation: str = "vertical base plate, vertical fins, open channel ends"
    kind: str = field(default="natural", init=False)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "NaturalConvectionOption":
        return cls(geometry=PlateFinGeometry.from_dict(d["geometry"]), name=str(d.get("name", "natural-convection")),
                   emissivity=float(d.get("emissivity", 0.0)), orientation=str(d.get("orientation", cls.orientation)))


@dataclass
class ForcedAirOption:
    geometry: PlateFinGeometry
    name: str = "forced-air"
    volumetric_flow: float | None = None  # m^3/s through the channels (fixed flow)
    fan_curve: list[tuple[float, float]] | None = None  # [(Q m^3/s, dp Pa)] per fan
    n_fans: int = 1
    fan_efficiency: float = 0.25
    fan_volume_m3_each: float = 0.06 * 0.06 * 0.015
    fan_mass_kg_each: float = 0.03
    fan_rated_power_W_each: float | None = None  # nameplate electrical power, if known
    kind: str = field(default="forced", init=False)

    def __post_init__(self) -> None:
        if self.volumetric_flow is None and not self.fan_curve:
            raise ValueError("ForcedAirOption needs volumetric_flow or fan_curve")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ForcedAirOption":
        curve = [(float(q), float(p)) for q, p in d["fan_curve"]] if d.get("fan_curve") else None
        return cls(geometry=PlateFinGeometry.from_dict(d["geometry"]), name=str(d.get("name", "forced-air")),
                   volumetric_flow=d.get("volumetric_flow"), fan_curve=curve, n_fans=int(d.get("n_fans", 1)),
                   fan_efficiency=float(d.get("fan_efficiency", 0.25)),
                   fan_volume_m3_each=float(d.get("fan_volume_m3_each", 0.06 * 0.06 * 0.015)),
                   fan_mass_kg_each=float(d.get("fan_mass_kg_each", 0.03)),
                   fan_rated_power_W_each=d.get("fan_rated_power_W_each"))


@dataclass(frozen=True)
class CoolantProperties:
    name: str
    temperature_C: float
    density: float  # kg/m^3
    specific_heat: float  # J/(kg K)
    viscosity: float  # Pa s
    conductivity: float  # W/(m K)
    note: str = ""

    @property
    def prandtl(self) -> float:
        return self.viscosity * self.specific_heat / self.conductivity


# Water: Incropera & DeWitt Table A.6 (saturated liquid) at 300, 320, 340 K.
_WATER_TABLE = [(26.85, 997.0, 4179.0, 855e-6, 0.613), (46.85, 989.1, 4180.0, 577e-6, 0.640), (66.85, 979.4, 4188.0, 420e-6, 0.660)]
# 50/50 vol% ethylene glycol / water: typical handbook values (+/-10 %); override with CoolantProperties when the mixture is known.
_EG50_TABLE = [(20.0, 1073.0, 3290.0, 3.9e-3, 0.37), (40.0, 1063.0, 3340.0, 2.3e-3, 0.38), (60.0, 1052.0, 3400.0, 1.5e-3, 0.39)]


def coolant_properties(name: str, temperature_C: float) -> CoolantProperties:
    """Liquid properties by linear interpolation of a small table (``"water"`` or ``"eg50"``)."""
    key = name.lower()
    if key == "water":
        table, note = _WATER_TABLE, "Incropera & DeWitt Table A.6, linear interpolation 27-67 C"
    elif key in ("eg50", "glycol50", "water-glycol-50"):
        table, note = _EG50_TABLE, "typical 50/50 EG-water handbook values (+/-10 %), 20-60 C"
    else:
        raise KeyError(f"unknown coolant {name!r}; use 'water', 'eg50' or pass CoolantProperties")
    t = min(max(temperature_C, table[0][0]), table[-1][0])
    for (t0, *a), (t1, *b) in zip(table[:-1], table[1:]):
        if t0 <= t <= t1:
            w = (t - t0) / (t1 - t0)
            rho, cp, mu, k = (x + (y - x) * w for x, y in zip(a, b))
            break
    else:  # pragma: no cover - clamped above
        rho, cp, mu, k = table[-1][1:]
    if not (table[0][0] <= temperature_C <= table[-1][0]):
        note += f"; requested {temperature_C} C clamped to the table range"
    return CoolantProperties(key, temperature_C, rho, cp, mu, k, note)


@dataclass
class LiquidColdPlateOption:
    """Single-phase liquid cold plate with ``n_channels`` parallel rectangular channels along ``length``."""

    length: float
    width: float
    base_thickness: float  # device side
    n_channels: int
    channel_width: float
    channel_height: float
    wall_thickness: float
    coolant_inlet_C: float
    volumetric_flow: float  # m^3/s total
    name: str = "liquid-cold-plate"
    lid_thickness: float = 0.003
    material: str = "Al-6063-T5"
    coolant: str | CoolantProperties = "water"
    pump_efficiency: float = 0.3
    minor_loss_coefficient: float = 1.5  # manifold/inlet/outlet losses in velocity heads
    correlation: str = "auto"  # auto: laminar Shah-London / Gnielinski; "dittus_boelter" forces DB when Re >= 1e4
    external_loop_volume_m3: float = 0.0
    external_loop_mass_kg: float = 0.0
    external_loop_power_W: float = 0.0
    kind: str = field(default="liquid", init=False)

    def __post_init__(self) -> None:
        if min(self.length, self.width, self.base_thickness, self.channel_width, self.channel_height, self.wall_thickness,
               self.lid_thickness, self.volumetric_flow) <= 0 or self.n_channels < 1:
            raise ValueError("cold plate dimensions, flow and channel count must be positive")
        needed = self.n_channels * self.channel_width + (self.n_channels + 1) * self.wall_thickness
        if needed > self.width + 1e-12:
            raise ValueError(f"{self.n_channels} channels of {self.channel_width} m with {self.wall_thickness} m walls need {needed:.4f} m > width {self.width} m")
        if not (0 < self.pump_efficiency <= 1):
            raise ValueError("pump_efficiency must lie in (0, 1]")

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "LiquidColdPlateOption":
        allowed = {f for f in cls.__dataclass_fields__ if f != "kind"}
        kwargs = {k: v for k, v in d.items() if k in allowed}
        return cls(**kwargs)

    @property
    def total_thickness(self) -> float:
        return self.base_thickness + self.channel_height + self.lid_thickness


CoolingOption = Any  # NaturalConvectionOption | ForcedAirOption | LiquidColdPlateOption


def option_from_dict(d: dict[str, Any]) -> CoolingOption:
    kind = d.get("kind")
    if kind == "natural":
        return NaturalConvectionOption.from_dict(d)
    if kind == "forced":
        return ForcedAirOption.from_dict(d)
    if kind == "liquid":
        return LiquidColdPlateOption.from_dict(d)
    raise ValueError("option needs kind 'natural', 'forced' or 'liquid'")


def option_to_dict(option: CoolingOption) -> dict[str, Any]:
    d = asdict(option)
    if isinstance(option.__dict__.get("coolant"), CoolantProperties):
        d["coolant"] = asdict(option.coolant)
    return d


# ------------------------------------------------------------- review items

REVIEW_ITEMS: dict[str, list[dict[str, str]]] = {
    "common": [
        {"topic": "interface material", "item": "TIM/pad thermal resistance, pump-out and dry-out over temperature cycling; mounting pressure and flatness", "action": "specify pad part, thickness, clamp force; qualify by thermal cycling"},
        {"topic": "isolation", "item": "heat sink potential (floating vs. earthed), creepage/clearance from device tabs to the sink, isolation pad withstand voltage at 800 V bus", "action": "define sink potential; verify pad isolation rating and creepage per the applicable safety standard"},
        {"topic": "verification", "item": "all values here are analytical correlations", "action": "FEM/CFD verification of the shortlisted geometry; thermocouple/IR measurement on hardware"},
    ],
    "natural": [
        {"topic": "orientation", "item": "performance depends on vertical fin orientation and free inflow/outflow; enclosure or horizontal mounting degrades it", "action": "confirm mounting orientation and enclosure openings"},
        {"topic": "altitude/ambient", "item": "buoyancy-driven flow weakens with air density (altitude) and high ambient", "action": "derate for the installation altitude and worst-case ambient"},
        {"topic": "radiation", "item": "surface finish (anodised vs. bare) changes the radiative share", "action": "specify finish; evaluate with emissivity set"},
        {"topic": "reliability", "item": "no moving parts; large mass may stress the PCB/mounting under vibration", "action": "mechanical mounting review"},
        {"topic": "acoustic", "item": "silent", "action": "none"},
    ],
    "forced": [
        {"topic": "acoustic", "item": "fan noise rises with speed and static pressure; tonal components", "action": "check fan datasheet sound level at the operating point; consider speed control"},
        {"topic": "reliability", "item": "fan bearing life derates strongly with temperature; single-fan failure removes most of the cooling", "action": "fan MTTF at bearing temperature; tachometer monitoring; redundancy or thermal shutdown"},
        {"topic": "dust/filter", "item": "dust loading increases pressure drop and fin fouling", "action": "filter or maintenance interval; design margin on flow"},
        {"topic": "bypass", "item": "the model assumes fully ducted flow; unducted fans lose a large share through bypass", "action": "duct the fins; verify with CFD/measurement"},
        {"topic": "EMI/supply", "item": "fan motor and PWM speed control add EMI and auxiliary supply load", "action": "filter the fan supply; include in the auxiliary power budget"},
    ],
    "liquid": [
        {"topic": "leakage", "item": "fittings, hoses and gaskets near 800 V electronics", "action": "leak test; drip routing away from live parts; leak sensor"},
        {"topic": "condensation", "item": "coolant below the local dew point condenses on the cold plate and devices", "action": "keep inlet above dew point or control humidity; conformal coating"},
        {"topic": "isolation", "item": "coolant conductivity and wetted-path creepage if the plate is at a different potential; deionised water needs resistivity control", "action": "specify coolant and insulating hose length; isolation pads"},
        {"topic": "corrosion/compatibility", "item": "galvanic couples (Al/Cu) and inhibitor depletion", "action": "single wetted metal or inhibited coolant; material compatibility list"},
        {"topic": "reliability/maintenance", "item": "pump wear, coolant ageing, air locks, freeze protection", "action": "pump MTTF, flow/pressure monitoring, service interval, glycol fraction for the climate"},
        {"topic": "external loop", "item": "radiator, pump and fans (noise, volume, mass, power) are outside the cold plate unless specified", "action": "size the heat rejection loop at the assumed inlet temperature"},
    ],
}


def review_items(kind: str) -> list[dict[str, str]]:
    return [dict(x) for x in REVIEW_ITEMS["common"]] + [dict(x) for x in REVIEW_ITEMS.get(kind, [])]


# ------------------------------------------------------------- evaluation


@dataclass
class CoolingResult:
    option_name: str
    kind: str
    t_ambient_C: float
    fluid_inlet_C: float
    total_power_W: float
    r_sink_to_fluid: float  # shared node -> fluid (K/W)
    r_hottest_total: float  # (T_hottest base spot - T_fluid) / sum P including spreading
    t_sink_C: float
    tj_max_C: float
    hottest_device: str
    devices: list[dict[str, Any]]
    mass_kg: float
    volume_m3: float
    auxiliary_power_W: float
    pressure_drop_Pa: float | None
    volumetric_flow: float | None
    details: dict[str, Any]
    electrothermal: dict[str, Any] | None
    validity: list[str]
    warnings: list[str]
    review_items: list[dict[str, str]]
    all_within_design_limit: bool
    all_within_absolute_limit: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _OptionEvaluator:
    """Callable ``powers_by_name -> {tj_by_name, network, physics}`` for one option."""

    def __init__(self, option: CoolingOption, devices: Sequence[CoolingDevice], t_ambient_C: float):
        self.option, self.devices, self.t_ambient_C = option, list(devices), t_ambient_C
        self.hm = load_heatsink_model()

    def __call__(self, powers: dict[str, float]) -> dict[str, Any]:
        physics = self._physics(powers)
        fluid_in = physics["fluid_inlet_C"]
        sink = net.SharedHeatSink(r_sa=physics["r_sink_to_fluid"], t_ambient_C=fluid_in, name=self.option.name)
        paths = []
        for d in self.devices:
            spread = physics["base_by_device"].get(d.name, 0.0)
            paths.append(net.DeviceThermalPath(d.name, powers[d.name], d.r_jc, d.r_cs, spread, d.tj_max_C, d.tj_design_C))
        network = net.solve_steady_state(paths, sink)
        return {"tj_by_name": {r["name"]: r["t_j_C"] for r in network["devices"]}, "network": network, "physics": physics}

    # -- physics per option kind -------------------------------------------------
    def _physics(self, powers: dict[str, float]) -> dict[str, Any]:
        hm = self.hm
        sources = [hm.HeatSource(d.footprint_area_m2, max(powers[d.name], 0.0), d.name) for d in self.devices]
        p_tot = sum(s.power for s in sources)
        if p_tot <= 0:
            raise ValueError("total device power must be positive")
        opt = self.option
        if opt.kind in ("natural", "forced"):
            sink = opt.geometry.to_sink(hm)
            if opt.kind == "natural":
                op = hm.OperatingPoint(t_ambient_C=self.t_ambient_C, cooling="natural", heat_W=p_tot, sources=sources,
                                       emissivity=opt.emissivity)
            else:
                op = hm.OperatingPoint(t_ambient_C=self.t_ambient_C, cooling="forced", heat_W=p_tot, sources=sources,
                                       volumetric_flow=opt.volumetric_flow, fan_curve=opt.fan_curve, n_fans=opt.n_fans,
                                       fan_efficiency=opt.fan_efficiency)
            perf = hm.evaluate(sink, op)
            base_by_device = {s["name"]: s["r_base_total"] for s in perf.sources}
            if opt.kind == "forced":
                if opt.fan_rated_power_W_each is not None:
                    aux = opt.n_fans * opt.fan_rated_power_W_each
                    aux_note = "fan nameplate power"
                else:
                    aux = perf.fan_electrical_power_W or 0.0
                    aux_note = f"Q dp / eta_fan with eta_fan = {opt.fan_efficiency}"
                mass = sink.mass + opt.n_fans * opt.fan_mass_kg_each
                volume = sink.envelope_volume + opt.n_fans * opt.fan_volume_m3_each
            else:
                aux, aux_note = 0.0, "no auxiliary power"
                mass, volume = sink.mass, sink.envelope_volume
            return {"fluid_inlet_C": self.t_ambient_C, "r_sink_to_fluid": perf.r_convective, "r_hottest_total": perf.r_total,
                    "base_by_device": base_by_device, "t_sink_C": self.t_ambient_C + p_tot * perf.r_convective,
                    "mass_kg": mass, "volume_m3": volume, "auxiliary_power_W": aux, "auxiliary_note": aux_note,
                    "pressure_drop_Pa": perf.pressure_drop_Pa, "volumetric_flow": perf.volumetric_flow,
                    "validity": list(perf.validity), "warnings": list(perf.warnings),
                    "details": {"heat_sink": perf.sink, "h": perf.h, "fin_efficiency": perf.fin_efficiency,
                                "effective_area_m2": perf.effective_area_m2, "delta_T_base_K": perf.delta_T_base_K,
                                "elenbaas": perf.elenbaas, "reynolds_dh": perf.reynolds_dh, "reynolds_b_star": perf.reynolds_b_star,
                                "regime": perf.regime, "channel_velocity": perf.channel_velocity,
                                "pressure_drop_breakdown": perf.pressure_drop_breakdown, "fan_air_power_W": perf.fan_power_W,
                                "solver": {k: v for k, v in perf.solver.items() if k != "history"},
                                "sources": perf.sources}}
        if opt.kind == "liquid":
            return self._cold_plate(sources, p_tot)
        raise ValueError(f"unknown option kind {opt.kind!r}")

    def _cold_plate(self, sources: Sequence[Any], p_tot: float) -> dict[str, Any]:
        hm = self.hm
        opt: LiquidColdPlateOption = self.option
        material = hm.get_material(opt.material)
        k = material.conductivity
        validity: list[str] = []
        warnings: list[str] = []
        # coolant properties at the mean coolant temperature (iterate once: rise depends on cp only weakly)
        props = opt.coolant if isinstance(opt.coolant, CoolantProperties) else coolant_properties(opt.coolant, opt.coolant_inlet_C)
        m_dot = props.density * opt.volumetric_flow
        rise = p_tot / (m_dot * props.specific_heat)
        if not isinstance(opt.coolant, CoolantProperties):
            props = coolant_properties(opt.coolant, opt.coolant_inlet_C + 0.5 * rise)
            m_dot = props.density * opt.volumetric_flow
            rise = p_tot / (m_dot * props.specific_heat)
        w, h, L, n = opt.channel_width, opt.channel_height, opt.length, opt.n_channels
        area_flow = n * w * h
        v = opt.volumetric_flow / area_flow
        dh = 2 * w * h / (w + h)
        re = props.density * v * dh / props.viscosity
        pr = props.prandtl
        aspect = min(w, h) / max(w, h)
        if re < 2300.0:
            nu = hm.laminar_duct_nusselt(aspect, "H")
            regime = "laminar"
            f_fanning = hm.developing_laminar_fanning_friction(re, L, dh, aspect)
            f_darcy = 4.0 * f_fanning
            validity.append("cold plate: fully developed laminar Shah-London Nusselt (uniform heat flux), Re_Dh < 2300; "
                            "entrance enhancement neglected (conservative); Muzychka-Yovanovich developing friction")
        else:
            if opt.correlation == "dittus_boelter" and re >= 1e4:
                nu = hm.dittus_boelter_nusselt(re, pr, heating=True)
                validity.append("cold plate: Dittus-Boelter Nu = 0.023 Re^0.8 Pr^0.4 (Re >= 1e4, 0.6 <= Pr <= 160, L/D >= 10)")
            else:
                nu = hm.gnielinski_nusselt(re, pr)
                validity.append("cold plate: Gnielinski with Petukhov friction (3000 <= Re <= 5e6, 0.5 <= Pr <= 2000)")
                if re < 3000:
                    warnings.append(f"Re_Dh = {re:.0f} transitional; Gnielinski extrapolated below 3000")
            regime = "turbulent"
            f_darcy = hm.petukhov_friction_factor(re)
        if L / dh < 10:
            warnings.append(f"L/D_h = {L / dh:.1f} < 10: duct correlations assume long channels")
        h_coeff = nu * props.conductivity / dh
        eta_wall = hm.fin_efficiency(h_coeff, k, h, opt.wall_thickness, L)
        wetted_eff = n * L * (w + 2.0 * h * eta_wall)  # channel floor + two walls as fins; lid treated adiabatic
        r_conv = 1.0 / (h_coeff * wetted_eff)
        r_caloric = 1.0 / (2.0 * m_dot * props.specific_heat)
        r_sink = r_conv + r_caloric
        a_base = opt.length * opt.width
        h_eff = 1.0 / (r_sink * a_base)
        base_by_device: dict[str, float] = {}
        worst = 0.0
        src_rows = []
        for s in sources:
            cell = a_base * s.power / p_tot if s.power > 0 else a_base / len(sources)
            if s.area >= cell:
                tot = opt.base_thickness / (k * cell)
                spread = {"one_d": tot, "spreading_max": 0.0, "total_max": tot}
            else:
                spread = hm.spreading_resistance(s.area, cell, opt.base_thickness, k, h_eff)
            base_by_device[s.name] = spread["total_max"]
            worst = max(worst, s.power * spread["total_max"])
            src_rows.append({"name": s.name, "power": s.power, "cell_area": cell, "r_base_total": spread["total_max"],
                             "r_spreading_max": spread["spreading_max"]})
        dyn = 0.5 * props.density * v ** 2
        dp = (f_darcy * L / dh + opt.minor_loss_coefficient) * dyn
        pump_hydraulic = opt.volumetric_flow * dp
        pump_electrical = pump_hydraulic / opt.pump_efficiency
        solid_volume = a_base * (opt.base_thickness + opt.lid_thickness) + (n + 1) * opt.wall_thickness * h * L
        coolant_volume = area_flow * L
        mass = material.density * solid_volume + props.density * coolant_volume + opt.external_loop_mass_kg
        volume = a_base * opt.total_thickness + opt.external_loop_volume_m3
        validity.append("cold plate: single-phase coolant, uniform flow split between channels, lid adiabatic, properties at the "
                        "mean coolant temperature; resistance referenced to the coolant inlet (caloric term 1/(2 m_dot c_p))")
        validity.append("cold plate: 1-D base conduction plus Lee-Song-Au-Moran spreading per footprint cell")
        if opt.external_loop_power_W == 0.0 and opt.external_loop_volume_m3 == 0.0:
            warnings.append("external loop (pump, radiator, hoses) not included: inlet temperature is an assumption to be met by the loop")
        return {"fluid_inlet_C": opt.coolant_inlet_C, "r_sink_to_fluid": r_sink, "r_hottest_total": r_sink + worst / p_tot,
                "base_by_device": base_by_device, "t_sink_C": opt.coolant_inlet_C + p_tot * r_sink, "mass_kg": mass,
                "volume_m3": volume, "auxiliary_power_W": pump_electrical + opt.external_loop_power_W,
                "auxiliary_note": f"pump Q dp / eta_pump with eta_pump = {opt.pump_efficiency}" + (" plus external loop power" if opt.external_loop_power_W else ""),
                "pressure_drop_Pa": dp, "volumetric_flow": opt.volumetric_flow, "validity": validity, "warnings": warnings,
                "details": {"coolant": asdict(props), "mass_flow_kg_s": m_dot, "coolant_rise_K": rise, "coolant_outlet_C": opt.coolant_inlet_C + rise,
                            "channel_velocity": v, "hydraulic_diameter": dh, "reynolds_dh": re, "prandtl": pr, "nusselt": nu,
                            "regime": regime, "h": h_coeff, "wall_fin_efficiency": eta_wall, "wetted_area_effective_m2": wetted_eff,
                            "r_convective": r_conv, "r_caloric": r_caloric, "darcy_friction_factor": f_darcy,
                            "pump_hydraulic_power_W": pump_hydraulic, "solid_volume_m3": solid_volume, "coolant_volume_m3": coolant_volume,
                            "sources": src_rows, "t_ambient_room_C": self.t_ambient_C}}


def evaluate_option(option: CoolingOption, devices: Sequence[CoolingDevice], t_ambient_C: float,
                    electrothermal: bool = True, et_settings: et.ElectrothermalSettings | None = None) -> CoolingResult:
    """Evaluate one cooling option for the given devices (optionally closing the electrothermal loop)."""
    if not devices:
        raise ValueError("at least one device is required")
    evaluator = _OptionEvaluator(option, devices, t_ambient_C)
    powers = {d.name: d.power_W for d in devices}
    state = evaluator(powers)
    et_summary = None
    if electrothermal and all(d.loss_model is not None for d in devices):
        models = [d.loss_model for d in devices]  # type: ignore[misc]

        def solver(p: dict[str, float]) -> dict[str, float]:
            return evaluator(p)["tj_by_name"]

        result = et.iterate(models, solver, state["tj_by_name"], et_settings)
        final_powers = {n: v["total_W"] for n, v in result.losses_W.items()}
        if result.converged:
            state = evaluator(final_powers)
        et_summary = {"converged": result.converged, "iterations": result.iterations, "reason": result.reason,
                      "tj_C": result.tj_C, "losses_W": result.losses_W, "total_loss_W": result.total_loss_W,
                      "history": [{"iteration": h["iteration"], "total_loss_W": h["total_loss_W"], "max_change_K": h["max_change_K"],
                                   "tj_out_C": h["tj_out_C"]} for h in result.history]}
    physics, network = state["physics"], state["network"]
    return CoolingResult(
        option_name=option.name, kind=option.kind, t_ambient_C=t_ambient_C, fluid_inlet_C=physics["fluid_inlet_C"],
        total_power_W=network["total_power_W"], r_sink_to_fluid=physics["r_sink_to_fluid"], r_hottest_total=physics["r_hottest_total"],
        t_sink_C=network["t_sink_C"], tj_max_C=network["t_j_max_C"], hottest_device=network["hottest_device"],
        devices=network["devices"], mass_kg=physics["mass_kg"], volume_m3=physics["volume_m3"],
        auxiliary_power_W=physics["auxiliary_power_W"], pressure_drop_Pa=physics["pressure_drop_Pa"],
        volumetric_flow=physics["volumetric_flow"], details={**physics["details"], "auxiliary_note": physics["auxiliary_note"]},
        electrothermal=et_summary, validity=physics["validity"], warnings=physics["warnings"], review_items=review_items(option.kind),
        all_within_design_limit=network["all_within_design_limit"], all_within_absolute_limit=network["all_within_absolute_limit"])


def compare_cooling_options(devices: Sequence[CoolingDevice], options: Sequence[CoolingOption], t_ambient_C: float,
                            electrothermal: bool = True, et_settings: et.ElectrothermalSettings | None = None) -> dict[str, Any]:
    """Evaluate every option for the same devices and rank them by maximum junction temperature."""
    results = [evaluate_option(o, devices, t_ambient_C, electrothermal, et_settings) for o in options]
    ranked = sorted(results, key=lambda r: r.tj_max_C)
    table = [{"option": r.option_name, "kind": r.kind, "tj_max_C": r.tj_max_C, "t_sink_C": r.t_sink_C,
              "r_sink_to_fluid_K_per_W": r.r_sink_to_fluid, "r_hottest_total_K_per_W": r.r_hottest_total,
              "mass_kg": r.mass_kg, "volume_L": r.volume_m3 * 1e3, "auxiliary_power_W": r.auxiliary_power_W,
              "pressure_drop_Pa": r.pressure_drop_Pa, "total_power_W": r.total_power_W,
              "within_design_limit": r.all_within_design_limit, "within_absolute_limit": r.all_within_absolute_limit}
             for r in ranked]
    return {"schema": "pea-thermal-cooling-comparison/0.1", "t_ambient_C": t_ambient_C,
            "devices": [d.to_dict() for d in devices], "ranking_by_tj": [r.option_name for r in ranked],
            "summary_table": table, "results": [r.to_dict() for r in results],
            "method": "analytical correlations (HeatSinkOptimisation heatsink_model + pea.thermal cold-plate model) -> shared-sink network"
                      + (" -> electrothermal loop" if electrothermal else ""),
            "disclaimer": "Screening estimates with stated validity ranges; not CFD, FEM or measured results. Qualitative criteria are listed as review items."}


__all__ = ["CoolingDevice", "PlateFinGeometry", "NaturalConvectionOption", "ForcedAirOption", "CoolantProperties",
           "coolant_properties", "LiquidColdPlateOption", "option_from_dict", "option_to_dict", "review_items",
           "CoolingResult", "evaluate_option", "compare_cooling_options", "REVIEW_ITEMS"]
