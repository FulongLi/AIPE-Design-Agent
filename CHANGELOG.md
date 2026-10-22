# Changelog

## 0.2.0 — 2026-10-21

Refactor of the repository (formerly *AIPE-Design-Agent*, distribution `pea` 0.1.0) into the
installable package `aipe_electrical` (distribution `aipe-electrical`).

**Why 0.2.0 and not a patch:** the import package, the distribution name, the public API
(dataclass fields, keyword-only functions, output keys) and the dependency set all changed, and
the legacy `pea` application is no longer shipped. The version stays below 1.0 because the models
are idealised analytical references without measured validation (status: Alpha).

**Archive:** the complete pre-refactor repository (upstream `main` = `614ecd5`) is tagged
`legacy-pea-v0.1`. Everything listed under *Removed* can be recovered from that tag.

### Added

- `aipe_electrical.converters.dab_sps`: lossless SPS dual-active-bridge model migrated from
  `pea.converters.dab_sps` with explicit semantics — `SpsOperatingPoint(v1, v2, turns_ratio_np_ns,
  f_sw, l_series_total, phi_rad)`, `from_degrees`, `with_phase_shift`, `turns_ratio_ns_np`,
  `power_flow_direction`, `matched_turns_ratio_np_ns`, `total_series_inductance_primary`
  (external + leakage, secondary parts scaled by `(N_p/N_s)^2`), keyword-only `max_power`,
  `phase_shift_for_power`, `series_inductance_for_power`, `design_for_power` (replaces
  `pea.tools.calculator.dab_design`), `SwitchingCurrents` and `ZvsCurrentDirectionLimits`
  dataclasses with an evidence label, `phase_shift_limits`.
- `aipe_electrical.analysis.waveforms` (exact piecewise-linear mean/RMS/peak, triangular ripple RMS),
  `analysis.dcdc` (CCM sizing: buck, boost, inverting buck-boost, SEPIC, Cuk; SI units, dataclasses),
  `analysis.losses` (first-order hard-switched buck losses).
- `aipe_electrical.optimisation.pareto` (generic non-dominated filter and min-max weighted ranking)
  and `optimisation.dab_sps_sweep` (lossless SPS design-space sweep with named objectives).
- `aipe_electrical.interfaces.json_io` and the `aipe-electrical` CLI (`dab-sps analyse|design|waveform`,
  `dcdc <topology>`, `buck-losses`); `examples/dab-10kw-sps.json`.
- `pyproject.toml` (src layout, no runtime dependencies, `dev` extra), GitHub Actions matrix
  (Python 3.10/3.11/3.12, `pip install -e .[dev]`, ruff, pytest, CLI smoke), `docs/models.md`,
  `docs/migration.md`, `aipe.yaml` with id `aipe.electrical-design`.

### Changed (semantics)

- Turns ratio is always named by direction: `turns_ratio_np_ns` (`N_p/N_s`) with `turns_ratio_ns_np`
  derived; the legacy `dab_design` output `turns_ratio_n` (which was `N_s/N_p`) is gone.
- The sized DAB inductance is reported as `series_inductance_total_H` / `series_inductance_total_uH`
  (total primary-referred series inductance); the legacy key `leakage_inductance_uH` was a misnomer and
  has no alias because no consumer remains.
- Phase shift: `phi_rad` fields, `phi_deg` helpers; `|phi| <= pi/2` enforced everywhere; reverse power
  flow (`phi < 0`, `p < 0`) supported by the inverse functions.
- ZVS: `analyse()["zvs_current_direction_conditions"]` with `evidence` text; the legacy
  `ZVS_status: "Achievable"` and `zvs_current_conditions` keys are retired.
- `analyse()` adds `model_version`, `inputs.turns_ratio_ns_np`, `inputs.phase_shift_deg`,
  `derived.power_flow_direction`, `derived.secondary_switching_current_primary_referred`; renames
  `inputs.series_inductance_primary_referred` to `inputs.series_inductance_total_primary_referred`.
- `switching_currents()` / `zvs_phase_shift_limits()` return dataclasses (`.to_dict()`), keys
  `*_zvs_current_direction_ok` and `*_min_abs_phi_rad`.
- CCM buck-boost ripple is defined relative to the inductor current `I_out/(1-D)` (the legacy code
  used the input current); all `analysis` functions take SI inputs and return unrounded values.

### Removed (archived at `legacy-pea-v0.1`)

LangChain agent (`pea/agent`, `pea/tools/langchain_tools.py`), knowledge/RAG (`pea/knowledge`,
`data/raw`, `scripts/extract_pdf.py`, `.env.example`), Streamlit `app.py` and `.streamlit/`,
static `index.html`, desktop shell (`pea/desktop.py`, `run_pea_desktop.bat`), component catalogue
(`pea/components`) and vendor SPICE JSON library (`data/spice_models_json`, `scripts/spice_to_json.py`),
magnetics tables (`pea/tools/magnetics_data.py`), calculators not migrated (`pea/tools/calculator.py`:
forward, flyback, LLC, cascade, inductor/transformer design, topology recommendation, `execute_tool`),
Pareto candidate optimiser (`pea/optimization.py`), CAD envelope (`pea/cad.py`), orchestration
prototype (`pea/orchestration`, `pea/registry`, `pea/state`, `pea/adapters`, `pea/review`,
`docs/ecosystem-orchestration.md`, `examples/ecosystem`, `tests/fixtures`), `pea/cli.py`,
`scripts/agent_smoke_test.py`, `requirements*.txt`, `TESTING.md`, the old `test.yml` workflow and
the legacy tests `test_calculator.py`, `test_optimizer.py`, `test_orchestration.py`.

### Moved to another repository

- `pea/thermal/` (thermal networks, electrothermal loop, cooling comparison, Stage A heat-sink screening,
  10 kW DAB thermal case) and `tests/test_thermal_*.py` now live in AIPE-Thermal-Design as the
  `aipe_thermal` package (distribution `aipe-thermal` 0.2.0); they were removed here once that package
  was published. The symbol-by-symbol mapping is in AIPE-Thermal-Design's documentation.

### Retained

- `LICENSE` (MIT, Fulong Li).

### Tests

116 tests for `aipe_electrical`, all passing on Python 3.10 (CI: 3.10, 3.11, 3.12). The 10 kW benchmark
(800 V -> 400 V, `N_p/N_s = 2`, 100 kHz, 35 uH) reproduces phi = 22.5 deg, P_max = 22 857 W,
I_rms = 13.6775 A, I_peak = 14.2857 A.

## 0.1.0

Legacy "PEA" Power Electronics AI Agent application (see tag `legacy-pea-v0.1`).
