"""Electrothermal fixed-point iteration: losses(Tj) -> Tj -> updated R_DS(on)(Tj), E_off(Tj) (standard library only).

The loop is agnostic of the loss physics: each device supplies callables
``conduction(tj_C) -> W`` and ``switching(tj_C) -> W`` so the AIPE semiconductor
database evaluator can plug in. Datasheet-based defaults are provided:

* ``RdsOnModel`` -- two-point temperature dependence (linear in Tj, or a power
  law in absolute temperature) fitted through ``(T_ref, R_ref)`` and ``(T_hot, R_hot)``;
* ``SwitchingEnergyModel`` -- energy per event scaled by ``(V/V_ref)^a (I/I_ref)^b``
  and linear in Tj through two points (or a stated coefficient).

The thermal side is any callable ``powers_by_name -> tj_by_name`` such as
``pea.thermal.network.make_network_solver`` or the cooling-option solvers.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Sequence

LossFunction = Callable[[float], float]
ThermalSolver = Callable[[dict[str, float]], dict[str, float]]

T0_K = 273.15


# ------------------------------------------------------------ datasheet defaults


@dataclass(frozen=True)
class RdsOnModel:
    """On-resistance versus junction temperature from two datasheet points.

    ``kind="linear"``: ``R(T) = R_ref [1 + alpha (T - T_ref)]`` with
    ``alpha = (R_hot/R_ref - 1)/(T_hot - T_ref)``;
    ``kind="power_law"``: ``R(T) = R_ref (T_K/T_ref_K)^gamma`` with
    ``gamma = ln(R_hot/R_ref)/ln(T_hot_K/T_ref_K)``.
    Both reproduce the two points exactly.
    """

    r_ref_ohm: float
    t_ref_C: float
    r_hot_ohm: float
    t_hot_C: float
    kind: str = "linear"
    source: str = ""

    def __post_init__(self) -> None:
        if self.r_ref_ohm <= 0 or self.r_hot_ohm <= 0:
            raise ValueError("on-resistances must be positive")
        if self.t_hot_C == self.t_ref_C:
            raise ValueError("the two temperature points must differ")
        if self.kind not in ("linear", "power_law"):
            raise ValueError("kind must be 'linear' or 'power_law'")

    @property
    def alpha_per_K(self) -> float:
        return (self.r_hot_ohm / self.r_ref_ohm - 1.0) / (self.t_hot_C - self.t_ref_C)

    @property
    def gamma(self) -> float:
        return math.log(self.r_hot_ohm / self.r_ref_ohm) / math.log((self.t_hot_C + T0_K) / (self.t_ref_C + T0_K))

    def __call__(self, tj_C: float) -> float:
        if self.kind == "linear":
            return self.r_ref_ohm * (1.0 + self.alpha_per_K * (tj_C - self.t_ref_C))
        return self.r_ref_ohm * ((tj_C + T0_K) / (self.t_ref_C + T0_K)) ** self.gamma

    def factor(self, tj_C: float) -> float:
        return self(tj_C) / self.r_ref_ohm

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.update(alpha_per_K=self.alpha_per_K, model="RdsOnModel")
        return d


@dataclass(frozen=True)
class SwitchingEnergyModel:
    """Switching energy per event: ``E = E_ref (V/V_ref)^a (I/I_ref)^b [1 + k_T (Tj - T_ref)]``."""

    e_ref_J: float
    t_ref_C: float
    v_ref_V: float
    i_ref_A: float
    t_coeff_per_K: float = 0.0
    v_exponent: float = 1.0
    i_exponent: float = 1.0
    source: str = ""

    def __post_init__(self) -> None:
        if self.e_ref_J < 0 or self.v_ref_V <= 0 or self.i_ref_A <= 0:
            raise ValueError("reference energy must be >= 0 and reference voltage/current positive")

    @classmethod
    def from_two_points(cls, e_a_J: float, t_a_C: float, e_b_J: float, t_b_C: float, v_ref_V: float, i_ref_A: float,
                        **kwargs: Any) -> "SwitchingEnergyModel":
        """Linear-in-Tj model through ``(t_a, e_a)`` and ``(t_b, e_b)`` at the same test voltage/current."""
        if t_a_C == t_b_C:
            raise ValueError("the two temperature points must differ")
        if e_a_J <= 0:
            raise ValueError("e_a must be positive to define a relative temperature coefficient")
        k = (e_b_J / e_a_J - 1.0) / (t_b_C - t_a_C)
        return cls(e_ref_J=e_a_J, t_ref_C=t_a_C, v_ref_V=v_ref_V, i_ref_A=i_ref_A, t_coeff_per_K=k, **kwargs)

    def energy(self, tj_C: float, v_V: float, i_A: float) -> float:
        scale = (v_V / self.v_ref_V) ** self.v_exponent * (abs(i_A) / self.i_ref_A) ** self.i_exponent
        return max(self.e_ref_J * scale * (1.0 + self.t_coeff_per_K * (tj_C - self.t_ref_C)), 0.0)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["model"] = "SwitchingEnergyModel"
        return d


def conduction_loss_W(i_rms_A: float, rds_on_ohm: float) -> float:
    """``P = I_rms^2 R_DS(on)``."""
    return i_rms_A ** 2 * rds_on_ohm


def switching_loss_W(energy_J: float, f_sw_Hz: float, events_per_period: float = 1.0) -> float:
    """``P = E f_sw n`` for ``n`` events per switching period."""
    return energy_J * f_sw_Hz * events_per_period


# ------------------------------------------------------------------ device model


@dataclass
class DeviceLossModel:
    """Loss model of one device as temperature-dependent callables (W as a function of Tj in degrees C)."""

    name: str
    conduction: LossFunction
    switching: LossFunction
    extra_W: float = 0.0
    description: str = ""
    sources: list[str] = field(default_factory=list)

    def losses(self, tj_C: float) -> dict[str, float]:
        cond = float(self.conduction(tj_C))
        sw = float(self.switching(tj_C))
        return {"conduction_W": cond, "switching_W": sw, "extra_W": self.extra_W, "total_W": cond + sw + self.extra_W}

    def total(self, tj_C: float) -> float:
        return self.losses(tj_C)["total_W"]

    @classmethod
    def datasheet_default(cls, name: str, i_rms_A: float, rds_on: RdsOnModel, f_sw_Hz: float,
                          e_off: SwitchingEnergyModel | None = None, v_off_V: float = 0.0, i_off_A: float = 0.0,
                          e_on: SwitchingEnergyModel | None = None, v_on_V: float = 0.0, i_on_A: float = 0.0,
                          events_per_period: float = 1.0, fixed_switching_W: float = 0.0, extra_W: float = 0.0,
                          description: str = "", sources: Sequence[str] = ()) -> "DeviceLossModel":
        """Conduction ``I_rms^2 R(Tj)`` plus ``f_sw`` times the (Tj-scaled) turn-off/turn-on energies.

        ``fixed_switching_W`` adds a temperature-independent switching term (for
        example a reference-design placeholder when no energy model is available).
        """
        if i_rms_A < 0 or f_sw_Hz <= 0:
            raise ValueError("i_rms must be >= 0 and f_sw positive")

        def conduction(tj_C: float) -> float:
            return conduction_loss_W(i_rms_A, rds_on(tj_C))

        def switching(tj_C: float) -> float:
            p = fixed_switching_W
            if e_off is not None:
                p += switching_loss_W(e_off.energy(tj_C, v_off_V, i_off_A), f_sw_Hz, events_per_period)
            if e_on is not None:
                p += switching_loss_W(e_on.energy(tj_C, v_on_V, i_on_A), f_sw_Hz, events_per_period)
            return p

        return cls(name=name, conduction=conduction, switching=switching, extra_W=extra_W,
                   description=description, sources=list(sources))


# --------------------------------------------------------------------- iteration


@dataclass
class ElectrothermalSettings:
    tol_K: float = 0.01
    tol_power_rel: float = 1e-4
    max_iterations: int = 50
    relaxation: float = 1.0
    t_abort_C: float = 400.0
    adaptive_relaxation: bool = True

    def __post_init__(self) -> None:
        if not (0 < self.relaxation <= 1):
            raise ValueError("relaxation must lie in (0, 1]")
        if self.max_iterations < 1 or self.tol_K <= 0:
            raise ValueError("max_iterations >= 1 and tol_K > 0 required")


@dataclass
class ElectrothermalResult:
    converged: bool
    iterations: int
    reason: str
    tj_C: dict[str, float]
    losses_W: dict[str, dict[str, float]]
    total_loss_W: float
    history: list[dict[str, Any]]
    settings: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def iterate(devices: Sequence[DeviceLossModel], thermal_solver: ThermalSolver,
            tj_initial_C: float | Mapping[str, float] = 25.0,
            settings: ElectrothermalSettings | None = None) -> ElectrothermalResult:
    """Fixed-point iteration ``Tj_k -> P(Tj_k) -> Tj_{k+1} = (1-w) Tj_k + w T(P)``.

    Convergence: ``max |Tj_{k+1} - Tj_k| < tol_K`` and relative total-loss change
    below ``tol_power_rel``. Divergence: any non-finite temperature or a
    temperature above ``t_abort_C`` stops the loop with ``converged=False``
    ("thermal runaway suspected"). With ``adaptive_relaxation`` the relaxation
    factor is halved whenever the temperature change grows two steps in a row.
    Every iteration (temperatures, per-device losses, change) is recorded.
    """
    settings = settings or ElectrothermalSettings()
    if not devices:
        raise ValueError("at least one device is required")
    names = [d.name for d in devices]
    if len(set(names)) != len(names):
        raise ValueError("device names must be unique")
    if isinstance(tj_initial_C, Mapping):
        tj = {n: float(tj_initial_C.get(n, 25.0)) for n in names}
    else:
        tj = {n: float(tj_initial_C) for n in names}
    w = settings.relaxation
    history: list[dict[str, Any]] = []
    previous_total = None
    previous_change = None
    growth_count = 0
    converged = False
    reason = "max_iterations reached"
    losses: dict[str, dict[str, float]] = {}
    for k in range(settings.max_iterations):
        losses = {d.name: d.losses(tj[d.name]) for d in devices}
        powers = {n: losses[n]["total_W"] for n in names}
        total = sum(powers.values())
        tj_new_raw = thermal_solver(powers)
        tj_new = {n: (1.0 - w) * tj[n] + w * float(tj_new_raw[n]) for n in names}
        change = max(abs(tj_new[n] - tj[n]) for n in names)
        record = {"iteration": k, "relaxation": w, "tj_in_C": dict(tj), "losses_W": losses, "total_loss_W": total,
                  "tj_out_C": tj_new, "max_change_K": change}
        history.append(record)
        if any(not math.isfinite(v) for v in tj_new.values()) or max(tj_new.values()) > settings.t_abort_C:
            reason = f"thermal runaway suspected: junction temperature exceeded {settings.t_abort_C} C or became non-finite"
            tj = tj_new
            break
        power_ok = previous_total is None or abs(total - previous_total) <= settings.tol_power_rel * max(abs(total), 1e-12)
        if change < settings.tol_K and power_ok:
            tj = tj_new
            converged = True
            reason = "converged"
            break
        if settings.adaptive_relaxation and previous_change is not None and change > previous_change:
            growth_count += 1
            if growth_count >= 2:
                w = max(w / 2.0, 0.05)
                growth_count = 0
                record["relaxation_reduced_to"] = w
        else:
            growth_count = 0
        previous_change = change
        previous_total = total
        tj = tj_new
    if converged:
        losses = {d.name: d.losses(tj[d.name]) for d in devices}
    return ElectrothermalResult(converged=converged, iterations=len(history), reason=reason, tj_C=tj,
                                losses_W=losses, total_loss_W=sum(v["total_W"] for v in losses.values()),
                                history=history, settings=asdict(settings))


def linear_fixed_point(t_ambient_C: float, r_total: float, p0_W: float, alpha_per_K: float, t_ref_C: float = 25.0) -> float:
    """Closed-form fixed point for ``P = P0 [1 + alpha (Tj - T_ref)]`` and ``Tj = T_amb + R P`` (test helper).

    ``Tj* = (T_amb + R P0 (1 - alpha T_ref)) / (1 - R P0 alpha)``; raises when ``R P0 alpha >= 1`` (no stable point).
    """
    loop_gain = r_total * p0_W * alpha_per_K
    if loop_gain >= 1.0:
        raise ValueError("loop gain R P0 alpha >= 1: no finite steady state (thermal runaway)")
    return (t_ambient_C + r_total * p0_W * (1.0 - alpha_per_K * t_ref_C)) / (1.0 - loop_gain)


__all__ = ["LossFunction", "ThermalSolver", "RdsOnModel", "SwitchingEnergyModel", "conduction_loss_W", "switching_loss_W",
           "DeviceLossModel", "ElectrothermalSettings", "ElectrothermalResult", "iterate", "linear_fixed_point"]
