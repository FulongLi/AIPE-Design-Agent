"""Thermal networks for power devices sharing a heat sink (SI units, standard library only).

Steady state
------------
Each device ``i`` has its own path junction -> case (``r_jc``) -> interface
material (``r_cs``) -> local base region (optional spreading ``r_spread``) into
the shared heat-sink node, which is cooled to ambient through ``r_sa``. The
coupling is through the shared node::

    T_sink   = T_amb + (sum_i P_i) r_sa
    T_case,i = T_sink + P_i (r_spread,i + r_cs,i)
    T_j,i    = T_case,i + P_i r_jc,i

``r_sa`` must be the resistance from the sink reference node (fin root / base
mean temperature) to the fluid; per-device spreading belongs in ``r_spread``.

Transient
---------
``FosterNetwork`` holds a datasheet Foster ladder ``Zth(t) = sum R_i (1 - exp(-t/tau_i))``.
``FosterNetwork.to_cauer()`` performs the exact continued-fraction conversion
with rational arithmetic; ``CauerNetwork.zth(t)`` integrates the physical RC
ladder (Crank-Nicolson on a geometric time grid). Both support piecewise-
constant power profiles by superposition.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from typing import Any, Callable, Sequence

# ------------------------------------------------------------------- transient


@dataclass(frozen=True)
class FosterStage:
    resistance: float  # K/W
    time_constant: float  # s

    def __post_init__(self) -> None:
        if not (self.resistance > 0 and self.time_constant > 0):
            raise ValueError("Foster stage needs positive resistance and time constant")

    @property
    def capacitance(self) -> float:
        return self.time_constant / self.resistance


@dataclass(frozen=True)
class FosterNetwork:
    """Foster (partial-fraction) thermal impedance as printed in datasheets."""

    stages: tuple[FosterStage, ...]

    def __post_init__(self) -> None:
        if not self.stages:
            raise ValueError("FosterNetwork needs at least one stage")

    @classmethod
    def from_pairs(cls, pairs: Sequence[Sequence[float]]) -> "FosterNetwork":
        """``[(R_i, tau_i), ...]``."""
        return cls(tuple(FosterStage(float(r), float(tau)) for r, tau in pairs))

    @classmethod
    def from_rc(cls, resistances: Sequence[float], capacitances: Sequence[float]) -> "FosterNetwork":
        if len(resistances) != len(capacitances):
            raise ValueError("R and C lists must have equal length")
        return cls(tuple(FosterStage(float(r), float(r) * float(c)) for r, c in zip(resistances, capacitances)))

    @property
    def r_static(self) -> float:
        return sum(s.resistance for s in self.stages)

    def zth(self, t: float) -> float:
        """Step response (K/W) at time ``t`` >= 0."""
        if t <= 0:
            return 0.0
        return sum(s.resistance * (1.0 - math.exp(-t / s.time_constant)) for s in self.stages)

    def response_to_power_steps(self, steps: Sequence[Sequence[float]], t: float) -> float:
        """Temperature rise (K) at ``t`` for piecewise-constant power ``[(t_k, P_k), ...]`` (P before t_0 is 0)."""
        return _superpose(self.zth, steps, t)

    def to_cauer(self) -> "CauerNetwork":
        """Exact Foster -> Cauer (junction-side ladder) conversion by continued-fraction expansion.

        ``Z(s) = sum R_i/(1 + s tau_i) = N(s)/D(s)``; ``Y = D/N = s C_1 + 1/(R_1 + 1/(s C_2 + ...))``.
        Uses ``fractions.Fraction`` so the expansion is exact for the given floats.
        """
        taus = [Fraction(s.time_constant) for s in self.stages]
        rs = [Fraction(s.resistance) for s in self.stages]
        denominator = [Fraction(1)]
        for tau in taus:
            denominator = _poly_mul(denominator, [Fraction(1), tau])
        numerator = [Fraction(0)]
        for i, r in enumerate(rs):
            term = [r]
            for j, tau in enumerate(taus):
                if j != i:
                    term = _poly_mul(term, [Fraction(1), tau])
            numerator = _poly_add(numerator, term)
        num, den = _trim(denominator), _trim(numerator)  # Y = D / N
        caps: list[float] = []
        res: list[float] = []
        for _ in range(len(self.stages)):
            if len(num) != len(den) + 1:
                raise ArithmeticError("Foster->Cauer expansion lost a degree; stages may be degenerate")
            c = num[-1] / den[-1]
            caps.append(float(c))
            rem = _trim(_poly_sub(num, _poly_mul([Fraction(0), c], den)))
            if len(rem) != len(den):
                raise ArithmeticError("Foster->Cauer expansion degenerate (coincident time constants?)")
            r = den[-1] / rem[-1]
            res.append(float(r))
            rem2 = _trim(_poly_sub(den, _poly_scale(rem, r)))
            num, den = rem, rem2
            if not den or den == [Fraction(0)]:
                break
        return CauerNetwork(tuple(res), tuple(caps))

    def to_dict(self) -> dict[str, Any]:
        return {"type": "foster", "stages": [asdict(s) for s in self.stages], "r_static": self.r_static}


@dataclass(frozen=True)
class CauerNetwork:
    """Physical RC ladder from the junction: ``C_1`` to ambient reference, ``R_1`` in series, ``C_2``, ``R_2``, ...

    The last resistance connects to the ambient (reference) node.
    """

    resistances: tuple[float, ...]
    capacitances: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.resistances) != len(self.capacitances) or not self.resistances:
            raise ValueError("Cauer ladder needs equal, non-empty R and C tuples")
        if min(self.resistances) <= 0 or min(self.capacitances) <= 0:
            raise ValueError("Cauer elements must be positive")

    @property
    def r_static(self) -> float:
        return sum(self.resistances)

    def _time_constants(self) -> tuple[float, float]:
        tau_min = min(r * c for r, c in zip(self.resistances, self.capacitances))
        tau_max = sum(self.resistances) * sum(self.capacitances)
        return tau_min, tau_max

    def zth(self, t: float, growth: float = 1.01, initial_fraction: float = 0.005) -> float:
        """Unit-step junction response at ``t`` by Crank-Nicolson integration of the ladder.

        The time step starts at ``initial_fraction * tau_min`` and grows geometrically
        by ``growth`` per step; accuracy is better than 0.5 % against the analytic
        Foster form for well-separated time constants (see tests).
        """
        if t <= 0:
            return 0.0
        return self.step_response_samples([t], growth, initial_fraction)[0]

    def step_response_samples(self, times: Sequence[float], growth: float = 1.01,
                              initial_fraction: float = 0.005) -> list[float]:
        """Junction rise (K/W) at each requested time for a unit power step."""
        times = sorted(float(x) for x in times)
        n = len(self.resistances)
        tau_min, _ = self._time_constants()
        dt = initial_fraction * tau_min
        theta = [0.0] * n
        t_now = 0.0
        out: list[float] = []
        idx = 0
        while idx < len(times):
            if times[idx] <= 0:
                out.append(0.0)
                idx += 1
                continue
            target = times[idx]
            step = min(dt, target - t_now)
            if step <= 0:
                out.append(theta[0])
                idx += 1
                continue
            theta = self._cn_step(theta, step, 1.0)
            t_now += step
            if abs(t_now - target) <= 1e-12 * max(1.0, target):
                out.append(theta[0])
                idx += 1
            dt *= growth
        return out

    def _cn_step(self, theta: list[float], dt: float, power: float) -> list[float]:
        """One Crank-Nicolson step of ``C dtheta/dt = -A theta + b`` for the ladder."""
        n = len(theta)
        R, C = self.resistances, self.capacitances
        # conductances between node i and i+1 (node n -> ambient)
        g = [1.0 / r for r in R]
        # explicit part: rhs = theta + dt/2 * (b - A theta)/C
        def a_theta(th: list[float]) -> list[float]:
            out = []
            for i in range(n):
                left = g[i - 1] * (th[i] - th[i - 1]) if i > 0 else 0.0
                right = g[i] * (th[i] - (th[i + 1] if i + 1 < n else 0.0))
                out.append((left + right) / C[i])
            return out
        b = [power / C[0]] + [0.0] * (n - 1)
        at = a_theta(theta)
        rhs = [theta[i] + 0.5 * dt * (b[i] - at[i]) + 0.5 * dt * b[i] for i in range(n)]
        # implicit tridiagonal system: (I + dt/2 A) theta_new = rhs
        lower = [0.0] * n
        diag = [0.0] * n
        upper = [0.0] * n
        for i in range(n):
            gl = g[i - 1] if i > 0 else 0.0
            gr = g[i]
            diag[i] = 1.0 + 0.5 * dt * (gl + gr) / C[i]
            if i > 0:
                lower[i] = -0.5 * dt * gl / C[i]
            if i + 1 < n:
                upper[i] = -0.5 * dt * gr / C[i]
        return _thomas(lower, diag, upper, rhs)

    def response_to_power_steps(self, steps: Sequence[Sequence[float]], t: float) -> float:
        return _superpose(self.zth, steps, t)

    def to_dict(self) -> dict[str, Any]:
        return {"type": "cauer", "resistances": list(self.resistances), "capacitances": list(self.capacitances),
                "r_static": self.r_static}


def _superpose(zth: Callable[[float], float], steps: Sequence[Sequence[float]], t: float) -> float:
    ordered = sorted((float(tk), float(pk)) for tk, pk in steps)
    rise = 0.0
    previous = 0.0
    for tk, pk in ordered:
        if tk > t:
            break
        rise += (pk - previous) * zth(t - tk)
        previous = pk
    return rise


def _thomas(lower: list[float], diag: list[float], upper: list[float], rhs: list[float]) -> list[float]:
    n = len(diag)
    c = [0.0] * n
    d = [0.0] * n
    c[0] = upper[0] / diag[0] if n > 1 else 0.0
    d[0] = rhs[0] / diag[0]
    for i in range(1, n):
        denom = diag[i] - lower[i] * c[i - 1]
        c[i] = upper[i] / denom if i + 1 < n else 0.0
        d[i] = (rhs[i] - lower[i] * d[i - 1]) / denom
    x = [0.0] * n
    x[-1] = d[-1]
    for i in range(n - 2, -1, -1):
        x[i] = d[i] - c[i] * x[i + 1]
    return x


def _poly_mul(a: list[Fraction], b: list[Fraction]) -> list[Fraction]:
    out = [Fraction(0)] * (len(a) + len(b) - 1)
    for i, ai in enumerate(a):
        for j, bj in enumerate(b):
            out[i + j] += ai * bj
    return out


def _poly_add(a: list[Fraction], b: list[Fraction]) -> list[Fraction]:
    n = max(len(a), len(b))
    return [(a[i] if i < len(a) else Fraction(0)) + (b[i] if i < len(b) else Fraction(0)) for i in range(n)]


def _poly_sub(a: list[Fraction], b: list[Fraction]) -> list[Fraction]:
    return _poly_add(a, [-x for x in b])


def _poly_scale(a: list[Fraction], k: Fraction) -> list[Fraction]:
    return [x * k for x in a]


def _trim(a: list[Fraction]) -> list[Fraction]:
    out = list(a)
    while len(out) > 1 and out[-1] == 0:
        out.pop()
    return out


# ---------------------------------------------------------------- steady state


@dataclass
class DeviceThermalPath:
    """One device on the shared sink. Resistances in K/W, power in W, temperatures in degrees C."""

    name: str
    power_W: float
    r_jc: float
    r_cs: float = 0.0
    r_spread: float = 0.0
    tj_max_C: float | None = None
    tj_design_C: float | None = None
    zth_jc: FosterNetwork | CauerNetwork | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.power_W < 0 or self.r_jc < 0 or self.r_cs < 0 or self.r_spread < 0:
            raise ValueError("DeviceThermalPath needs non-negative power and resistances")

    @property
    def r_path(self) -> float:
        """Series resistance of the private path junction -> shared sink node."""
        return self.r_jc + self.r_cs + self.r_spread

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceThermalPath":
        zth = None
        if data.get("zth_jc"):
            z = data["zth_jc"]
            if z.get("type", "foster") == "foster":
                zth = FosterNetwork.from_pairs([(s["resistance"], s["time_constant"]) for s in z["stages"]])
            else:
                zth = CauerNetwork(tuple(z["resistances"]), tuple(z["capacitances"]))
        return cls(name=str(data["name"]), power_W=float(data["power_W"]), r_jc=float(data["r_jc"]),
                   r_cs=float(data.get("r_cs", 0.0)), r_spread=float(data.get("r_spread", 0.0)),
                   tj_max_C=data.get("tj_max_C"), tj_design_C=data.get("tj_design_C"), zth_jc=zth,
                   note=str(data.get("note", "")))

    def to_dict(self) -> dict[str, Any]:
        d = {k: v for k, v in asdict(self).items() if k != "zth_jc"}
        d["zth_jc"] = self.zth_jc.to_dict() if self.zth_jc else None
        d["r_path"] = self.r_path
        return d


@dataclass
class SharedHeatSink:
    """Sink reference node -> fluid resistance ``r_sa`` (K/W) at ambient ``t_ambient_C``."""

    r_sa: float
    t_ambient_C: float
    name: str = "heat-sink"
    note: str = ""
    zth_sa: FosterNetwork | CauerNetwork | None = None

    def __post_init__(self) -> None:
        if self.r_sa < 0:
            raise ValueError("r_sa must be non-negative")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SharedHeatSink":
        return cls(r_sa=float(data["r_sa"]), t_ambient_C=float(data["t_ambient_C"]), name=str(data.get("name", "heat-sink")),
                   note=str(data.get("note", "")))

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "r_sa": self.r_sa, "t_ambient_C": self.t_ambient_C, "note": self.note}


def solve_steady_state(devices: Sequence[DeviceThermalPath], sink: SharedHeatSink,
                       powers_W: dict[str, float] | None = None) -> dict[str, Any]:
    """Steady-state temperatures of all devices sharing ``sink``.

    ``powers_W`` overrides the device powers by name (used by the electrothermal loop).
    """
    if not devices:
        raise ValueError("at least one device is required")
    names = [d.name for d in devices]
    if len(set(names)) != len(names):
        raise ValueError("device names must be unique")
    p = {d.name: (powers_W.get(d.name, d.power_W) if powers_W else d.power_W) for d in devices}
    p_tot = sum(p.values())
    t_sink = sink.t_ambient_C + p_tot * sink.r_sa
    rows = []
    for d in devices:
        pi = p[d.name]
        t_base_local = t_sink + pi * d.r_spread
        t_case = t_base_local + pi * d.r_cs
        t_j = t_case + pi * d.r_jc
        row = {"name": d.name, "power_W": pi, "t_base_local_C": t_base_local, "t_case_C": t_case, "t_j_C": t_j,
               "rise_above_ambient_K": t_j - sink.t_ambient_C,
               "margin_to_tj_max_K": (d.tj_max_C - t_j) if d.tj_max_C is not None else None,
               "margin_to_tj_design_K": (d.tj_design_C - t_j) if d.tj_design_C is not None else None,
               "within_design_limit": (t_j <= d.tj_design_C) if d.tj_design_C is not None else None,
               "within_absolute_limit": (t_j <= d.tj_max_C) if d.tj_max_C is not None else None}
        rows.append(row)
    hottest = max(rows, key=lambda r: r["t_j_C"])
    return {"model": "steady-state shared-sink network",
            "coupling": "all devices share one sink node: T_sink = T_amb + sum(P) r_sa; each device adds P_i (r_spread + r_cs + r_jc)",
            "t_ambient_C": sink.t_ambient_C, "total_power_W": p_tot, "t_sink_C": t_sink, "r_sa": sink.r_sa,
            "devices": rows, "t_j_max_C": hottest["t_j_C"], "hottest_device": hottest["name"],
            "all_within_design_limit": all(r["within_design_limit"] is not False for r in rows),
            "all_within_absolute_limit": all(r["within_absolute_limit"] is not False for r in rows)}


def allowable_power(device: DeviceThermalPath, sink: SharedHeatSink, other_devices_power_W: float, tj_limit_C: float) -> float:
    """Power ``P`` for which ``T_j = tj_limit`` given the other devices' total power on the same sink."""
    denom = sink.r_sa + device.r_path
    if denom <= 0:
        raise ValueError("network has zero resistance")
    return (tj_limit_C - sink.t_ambient_C - other_devices_power_W * sink.r_sa) / denom


def required_sink_resistance(devices: Sequence[DeviceThermalPath], t_ambient_C: float, tj_limit_C: float) -> float:
    """Largest ``r_sa`` for which every device stays at or below ``tj_limit_C``."""
    p_tot = sum(d.power_W for d in devices)
    if p_tot <= 0:
        raise ValueError("total power must be positive")
    return min((tj_limit_C - t_ambient_C - d.power_W * d.r_path) / p_tot for d in devices)


def make_network_solver(devices: Sequence[DeviceThermalPath], sink: SharedHeatSink) -> Callable[[dict[str, float]], dict[str, float]]:
    """Return ``powers -> junction temperatures`` for the electrothermal iteration."""

    def solve(powers_W: dict[str, float]) -> dict[str, float]:
        result = solve_steady_state(devices, sink, powers_W)
        return {row["name"]: row["t_j_C"] for row in result["devices"]}

    return solve


def transient_junction_temperature(device: DeviceThermalPath, sink: SharedHeatSink, power_steps: Sequence[Sequence[float]],
                                   times: Sequence[float], other_devices_power_W: float = 0.0) -> list[dict[str, float]]:
    """Junction temperature history for a piecewise-constant power profile.

    The junction-to-case part uses ``device.zth_jc`` when present (Foster or
    Cauer) and the static ``r_jc`` otherwise; the sink uses ``sink.zth_sa`` when
    present and otherwise its static resistance (sink thermal mass neglected,
    conservative for short pulses). Other devices are taken as constant power.
    """
    out = []
    for t in times:
        p_now = 0.0
        for tk, pk in sorted((float(a), float(b)) for a, b in power_steps):
            if tk <= t:
                p_now = pk
        if device.zth_jc is not None:
            rise_jc = device.zth_jc.response_to_power_steps(power_steps, t)
        else:
            rise_jc = p_now * device.r_jc
        rise_private = p_now * (device.r_cs + device.r_spread)
        if sink.zth_sa is not None:
            rise_sink = sink.zth_sa.response_to_power_steps(power_steps, t) + other_devices_power_W * sink.r_sa
        else:
            rise_sink = (p_now + other_devices_power_W) * sink.r_sa
        out.append({"t_s": float(t), "power_W": p_now, "t_j_C": sink.t_ambient_C + rise_sink + rise_private + rise_jc,
                    "rise_jc_K": rise_jc, "rise_sink_K": rise_sink})
    return out


__all__ = ["FosterStage", "FosterNetwork", "CauerNetwork", "DeviceThermalPath", "SharedHeatSink", "solve_steady_state",
           "allowable_power", "required_sink_resistance", "make_network_solver", "transient_junction_temperature"]
