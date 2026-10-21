# AIPE — Electrical Design

`aipe_electrical` is the analytical electrical-design library of the AIPE (AI for Power Engineering) ecosystem. It provides the exact lossless single-phase-shift (SPS) model of the dual active bridge that AIPE-Workflows uses for the 10 kW DAB case, continuous-conduction sizing formulas for basic DC-DC stages and a first-order buck loss estimate, all with explicit SI units and sign conventions. The former experimental "PEA" application (LangChain agent, RAG knowledge base, Streamlit, static and desktop UIs, component and magnetics tables, orchestration prototype) was retired in v0.2.0 and is archived at the Git tag `legacy-pea-v0.1`; its thermal module now lives in AIPE-Thermal-Design (`aipe_thermal`).

## Features

- Lossless SPS DAB analysis: power, maximum power, phase shift or total series inductance for a target power, exact piecewise-linear series current (RMS, peak, value at any instant), switching-instant currents, power-flow direction and sampled waveforms.
- Explicit semantics: turns ratio `N_p/N_s` versus `N_s/N_p`, total primary-referred series inductance composed from external and leakage parts, phase shift in radians with degree helpers, `|phi| <= 90 deg` enforced.
- ZVS reported only as a necessary current-direction condition carrying an evidence label, never as "ZVS confirmed".
- CCM sizing for buck, boost, inverting buck-boost, SEPIC and Cuk; first-order hard-switched buck losses; exact waveform metrics.
- Generic Pareto helpers and an SPS design-space sweep (lossless screening; no loss, magnetic or thermal model).
- JSON in/out helpers and the `aipe-electrical` command line; standard library only.

## Installation

```bash
pip install -e ".[dev]"
python -m pytest
```

## Usage

```bash
aipe-electrical dab-sps design --v1 800 --v2 400 --power 10000 --f-sw 100e3 --phi-deg 22.5
aipe-electrical dab-sps analyse --input examples/dab-10kw-sps.json
aipe-electrical dcdc buck --v-in 12 --v-out 5 --i-out 2 --f-sw 100e3
```

```python
import math
from aipe_electrical.converters import dab_sps

op = dab_sps.SpsOperatingPoint(v1=800, v2=400, turns_ratio_np_ns=2, f_sw=100e3,
                               l_series_total=35e-6, phi_rad=math.radians(22.5))
dab_sps.power(op)        # 10000.0 W (port 1 -> port 2)
dab_sps.current_rms(op)  # 13.6775 A
dab_sps.analyse(op)      # JSON-ready report with SI units and ZVS current-direction conditions
```

## Project Information

- Version: 0.2.0 (from `pyproject.toml`)
- Status: Alpha
- Developer: Fulong Li
- Organisation: Spirit Connect / AIPE Labs
- License: MIT (`LICENSE`)

## Documentation

- [docs/models.md](docs/models.md) — SPS derivation, sign conventions, ZVS condition, limits, CCM and loss formulas
- [docs/migration.md](docs/migration.md) — `pea.*` to `aipe_electrical` mapping, removed modules, archival tag
- [CHANGELOG.md](CHANGELOG.md) — release notes and the 0.2.0 version justification
- [CONTRIBUTING.md](CONTRIBUTING.md) — development setup and pull-request expectations
- [aipe.yaml](aipe.yaml) — AIPE capability manifest (`aipe.electrical-design`)
