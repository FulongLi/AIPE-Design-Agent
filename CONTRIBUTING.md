# Contributing to AIPE Electrical Design

**Last updated:** 2026-10-21

## Development setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
```

Python 3.10 or newer; the package itself has no runtime dependencies.

## Layout

| Area | Files |
| --- | --- |
| Lossless SPS dual-active-bridge model | `src/aipe_electrical/converters/dab_sps.py`, `tests/test_dab_sps.py` |
| Waveform metrics, CCM sizing, first-order losses | `src/aipe_electrical/analysis/`, `tests/test_waveforms.py`, `tests/test_dcdc.py`, `tests/test_losses.py` |
| Pareto helpers and SPS sweep | `src/aipe_electrical/optimisation/`, `tests/test_pareto.py`, `tests/test_dab_sps_sweep.py` |
| JSON interface and CLI | `src/aipe_electrical/interfaces/`, `tests/test_json_io.py`, `tests/test_cli.py`, `examples/` |
| Derivations and conventions | `docs/models.md` |
| Legacy mapping | `docs/migration.md`, tag `legacy-pea-v0.1` |

## Rules for changes

- SI units everywhere; a unit suffix in a name (`..._uH`, `..._Hz`) is reserved for JSON keys and CLI output.
- Name direction-dependent quantities explicitly (`turns_ratio_np_ns`, `l_series_total`, `phi_rad`).
- Every formula needs a derivation or a reference in `docs/models.md` and a test with hand-derived
  expected values; the 10 kW benchmark in `tests/test_dab_sps.py` must keep reproducing exactly.
- Do not label a necessary condition as a confirmation (ZVS, saturation, thermal limits); state the
  model assumptions in the returned `assumptions`.
- No new runtime dependencies without discussion; optional features go in extras.
- Update `CHANGELOG.md` and, when user-facing behaviour changes, `README.md` in the same pull request.

## Pull requests

Keep changes focused, match the existing style (ruff configuration in `pyproject.toml`), and run the
full test suite on at least one supported Python version. CI runs ruff, pytest and a CLI smoke test on
Python 3.10, 3.11 and 3.12. By contributing you agree that your contributions are licensed under the
MIT licence of this repository.
