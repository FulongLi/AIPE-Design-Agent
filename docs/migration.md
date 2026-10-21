# Migration: PEA (`pea.*`) to `aipe_electrical` (v0.2.0)

**Archival tag:** `legacy-pea-v0.1` = commit `614ecd5` (upstream `main` before this refactor). It holds
the complete legacy repository; recover any removed file with
`git show legacy-pea-v0.1:<path>` (for example `git show legacy-pea-v0.1:pea/tools/calculator.py`).

**Installation side by side:** `pip install -e .` installs only the `aipe_electrical` import package
(distribution `aipe-electrical`, no runtime dependencies). No `pea` distribution is produced, so an
editable legacy `pea` installed from a frozen *AIPE-Design-Agent* checkout is not affected.

## 1. API mapping

| Legacy (`pea`, 0.1.0) | New (`aipe_electrical`, 0.2.0) | Notes |
| --- | --- | --- |
| `pea.converters.dab_sps.SpsOperatingPoint(v1, v2, n_ratio, f_sw, l_total, phi_rad)` | `aipe_electrical.converters.dab_sps.SpsOperatingPoint(v1, v2, turns_ratio_np_ns, f_sw, l_series_total, phi_rad)` | `n_ratio` was already N_p/N_s; now named so. `from_degrees(...)`, `with_phase_shift()`, `turns_ratio_ns_np`, `phi_deg`, `power_flow`, `v2_primary_referred`, `d`, `period`, `t_phi`. |
| `power(v1, v2, n_ratio, f_sw, l_total, phi_rad)` | `power(op)` | Operating point instead of six positional scalars. |
| `max_power(v1, v2, n_ratio, f_sw, l_total)` | `max_power(*, v1, v2, turns_ratio_np_ns, f_sw, l_series_total)` | Keyword-only (prevents n vs 1/n and L positional mix-ups); validates inputs. |
| `phase_shift_for_power(v1, v2, n_ratio, f_sw, l_total, p)` | `phase_shift_for_power(*, v1, v2, turns_ratio_np_ns, f_sw, l_series_total, p)` | Signed result; raises above `max_power`. |
| `inductance_for_power(v1, v2, n_ratio, f_sw, phi_rad, p)` | `series_inductance_for_power(*, v1, v2, turns_ratio_np_ns, f_sw, phi_rad, p)` | Reverse flow allowed when `p` and `phi_rad` share the sign. |
| — | `design_for_power(*, v1, v2, p, f_sw, phi_rad, turns_ratio_np_ns=None)` | Replaces `pea.tools.calculator.dab_design`; matched ratio V1/V2 when omitted. |
| — | `matched_turns_ratio_np_ns(v1, v2)`, `total_series_inductance_primary(*, turns_ratio_np_ns, l_external_primary, l_leakage_primary, l_external_secondary, l_leakage_secondary)`, `power_flow_direction(phi_rad)`, `phase_shift_limits()` | New semantic helpers. |
| `breakpoints`, `current_at(op, t, origin)`, `current_rms`, `current_peak`, `power_from_waveform`, `sample_waveforms(op, n, origin)` | same names and semantics | `origin` validated. |
| `switching_currents(op) -> dict` | `switching_currents(op) -> SwitchingCurrents` (`.to_dict()`) | Keys `primary_zvs_current_condition` → `primary_zvs_current_direction_ok`, `secondary_zvs_current_condition` → `secondary_zvs_current_direction_ok`, `note` → `evidence`. |
| `zvs_phase_shift_limits(op) -> dict` | `-> ZvsCurrentDirectionLimits` (`.to_dict()`) | `*_min_phi_rad` → `*_min_abs_phi_rad` (valid for both flow directions). |
| `analyse(op)` | `analyse(op)` | Same shape (`model`, `inputs`, `derived`, `assumptions`, `waveform_breakpoints_rising_edge_origin`). Renamed: `zvs_current_conditions` → `zvs_current_direction_conditions` (+ `evidence`), `inputs.series_inductance_primary_referred` → `inputs.series_inductance_total_primary_referred`. Added: `model_version`, `inputs.turns_ratio_ns_np`, `inputs.phase_shift_deg`, `derived.power_flow_direction`, `derived.secondary_switching_current_primary_referred`. |
| `pea.tools.calculator.dab_design(v1, v2, p_rated, f_sw_khz, phi_deg)` | `dab_sps.design_for_power(...)` + `dab_sps.analyse(...)`; JSON: `interfaces.json_io.design_sps({"v1_V", "v2_V", "power_W", "f_sw_Hz", "phi_deg"|"phi_rad", ["turns_ratio_np_ns"]})` | Output keys: `leakage_inductance_uH` → `series_inductance_total_uH` (and `_H`); it always was the total series inductance. `turns_ratio_n` (= N_s/N_p) → `turns_ratio_np_ns` + `turns_ratio_ns_np`. `ZVS_status: "Achievable"` → `zvs_current_direction_conditions` with evidence label. No alias is kept: no consumer remains. |
| `buck_converter_design`, `boost_converter_design`, `buck_boost_design`, `sepic_design`, `cuk_design` (kHz, µH, µF, rounded) | `analysis.dcdc.buck_ccm`, `boost_ccm`, `buck_boost_ccm`, `sepic_ccm`, `cuk_ccm` (keyword-only, SI, `CcmDesign` dataclass) | Buck-boost ripple now relative to the inductor current I_out/(1−D); invalid inputs raise `ValueError` instead of returning `{"error": ...}`. |
| `efficiency_estimate(...)` | `analysis.losses.buck_first_order_losses(*, ...)` | Restricted to the buck stage its equations describe; SI inputs. |
| `pea.optimization.pareto_front`, `rank_candidates` | `optimisation.pareto.pareto_front(items, objectives, senses)`, `weighted_rank(items, objectives, senses, weights)` | Generic objectives with declared senses. |
| `pea.optimization.optimize_converter_design` | not migrated | Fitted loss factors (0.08/0.015 magnetics scaling, constant K/W, 1800 mm³/W heat sink) and reference component tables; `optimisation.dab_sps_sweep` offers a lossless SPS screening instead. |
| `pea.cli` (`pea tool dab ...`) | `aipe-electrical dab-sps analyse|design|waveform`, `aipe-electrical dcdc <topology>`, `aipe-electrical buck-losses` | JSON output; `--input file.json`; see `examples/dab-10kw-sps.json`. |

## 2. AIPE-Workflows adapter (`aipe_workflows.adapters.design_agent.AnalyticSpsTask`)

Replace the sibling-checkout import of `pea.converters.dab_sps` by the installed package:

```python
# before
m = import_from_checkout(repo, "pea.converters.dab_sps")
phi = m.phase_shift_for_power(v1, v2, n, f_sw, l_total, p_nom)
op = m.SpsOperatingPoint(v1=v1, v2=v2, n_ratio=n, f_sw=f_sw, l_total=l_total, phi_rad=phi)
zvs = analysis["zvs_current_conditions"]

# after
from aipe_electrical.converters import dab_sps as m
phi = m.phase_shift_for_power(v1=v1, v2=v2, turns_ratio_np_ns=n, f_sw=f_sw, l_series_total=l_total, p=p_nom)
op = m.SpsOperatingPoint(v1=v1, v2=v2, turns_ratio_np_ns=n, f_sw=f_sw, l_series_total=l_total, phi_rad=phi)
zvs = analysis["zvs_current_direction_conditions"]
```

Unchanged calls: `m.analyse(op)`, `m.current_at(op, 0.0, origin="centre")`, `m.sample_waveforms(op, 400, origin="centre")`,
`derived["power"]["value"]`, `derived["power_from_waveform_integral"]["value"]`,
`derived["series_current_rms_primary"]["value"]`, `derived["series_current_peak_primary"]["value"]`,
`derived["dc_current_port1"]["value"]`, `derived["dc_current_port2"]["value"]`, `analysis["inputs"]`,
`analysis["assumptions"]`, `analysis["model"]`. Evidence `source.locator` becomes
`src/aipe_electrical/converters/dab_sps.py` in repository `FulongLi/AIPE-Electrical-Design`.

## 3. Removed modules and where the responsibility now lives

| Removed | Reason | Authoritative home |
| --- | --- | --- |
| `pea/agent`, `pea/tools/langchain_tools.py`, `scripts/agent_smoke_test.py`, `.env.example` | LLM agent layer with OpenAI dependency; no ecosystem consumer | AIPE-Workflows (orchestration), none for chat |
| `pea/knowledge`, `data/raw/erickson_extracted.txt`, `scripts/extract_pdf.py` | RAG knowledge base; derived textbook text should not be redistributed | — |
| `app.py`, `.streamlit/`, `index.html`, `pea/desktop.py`, `run_pea_desktop.bat` | UIs with JS calculator copies diverging from the Python models | — |
| `pea/components`, `data/spice_models_json/` (412 vendor JSON files), `scripts/spice_to_json.py` | Reference component tables with placeholder ratings; vendor models carry vendor terms and were only consumed by the removed UI | AIPE-Semiconductor-Database |
| `pea/tools/magnetics_data.py`, `inductor_design`, `transformer_design` | Steinmetz coefficients identified as roughly two orders of magnitude too high in the ecosystem audit | AIPE-Magnetics-Database |
| `pea/tools/calculator.py`: `forward_design`, `flyback_design`, `llc_design`, `cascade_design`, `topology_recommendation`, `execute_tool`, `get_available_tools` | Fixed duty assumptions, LLC mixed N_s/N_p vs N_p/N_s conventions, heuristic cascade patterns and efficiencies; no tested reference | — (open for a reviewed re-implementation) |
| `pea/optimization.py`, `pea/cad.py` | Fitted loss factors and component fallback to the whole library; heuristic box geometry | AIPE-CAD-Agent (geometry) |
| `pea/orchestration`, `pea/registry`, `pea/state`, `pea/adapters`, `pea/review`, `docs/ecosystem-orchestration.md`, `examples/ecosystem`, `tests/fixtures`, `requirements-orchestration.txt` | Orchestration prototype | AIPE-Workflows, AIPE-Core, AIPE-Registry |
| `pea/cli.py`, `requirements.txt`, `TESTING.md`, `.github/workflows/test.yml` | Replaced by `aipe-electrical`, `pyproject.toml`, `tests/`, `.github/workflows/ci.yml` | this repository |
| `pea/thermal/` (`network`, `electrothermal`, `cooling`, `heatsink_optimisation`, `dab_case`, `_sibling`, `__main__`), `tests/test_thermal_*.py` | Thermal design is consolidated in one repository; removed here after `aipe_thermal` 0.2.0 was published | AIPE-Thermal-Design (`aipe_thermal`: `cooling`, `screening`, `heatsink`, `network`, `electrothermal`, `cases.dab_10kw`, `aipe-thermal` CLI) |

## 4. `pea.thermal` consumers

`pea.thermal` is no longer in this repository. The AIPE-Workflows thermal adapter
(`aipe_workflows.adapters.thermal_design`) must import `aipe_thermal` instead; the symbol-by-symbol
mapping (for example `pea.thermal.cooling.compare_cooling_options` → `aipe_thermal.cooling.compare_cooling_options`,
`pea.thermal.heatsink_optimisation.run_stage_a` → `aipe_thermal.screening.run_stage_a`,
`pea.thermal._sibling.load_heatsink_model()` → `import aipe_thermal.heatsink`) is documented by
AIPE-Thermal-Design. The last revision of this repository that still contained `pea/thermal` is the
tag `legacy-pea-v0.1`.
