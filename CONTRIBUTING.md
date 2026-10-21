# Contributing to PEA

**Last updated:** 2026-10-21

Thank you for helping improve PEA (Power Electronics AI Agent). This document is for anyone who will maintain or extend the project.

## Project overview

PEA assists with power electronics design: topology recommendation, DC-DC parameter calculations, efficiency estimation, optional RAG over curated knowledge, and multi-turn chat via LangChain + OpenAI.

- **Core logic** lives in Python under `pea/`; the **single source of truth** for design equations is `pea/tools/calculator.py`.
- **Pareto optimization** lives in `pea/optimization.py`: it generates DC-DC candidates, ranks efficiency/volume/cost trade-offs, uses optional `pymoo` NSGA-II when installed, and otherwise falls back to a deterministic screening backend.
- **3D envelope export** lives in `pea/cad.py` and requires the optional `[cad]` extra (`cadquery`). The first version exports mechanical envelope STEP models, not detailed PCB layout.
- **Thermal design** lives in `pea/thermal/` (pure Python, no LangChain/Streamlit imports): `network.py` (junction -> case -> TIM -> shared heat sink -> ambient for several devices, Foster/Cauer `Zth`), `electrothermal.py` (loss(Tj) <-> Tj iteration with pluggable loss callables and datasheet defaults), `cooling.py` (natural convection / forced air / liquid cold plate comparison with qualitative review items), `heatsink_optimisation.py` (Stage A Pareto screening with FEM-verification flags), `dab_case.py` (the AIPE 10 kW DAB case) and `__main__.py` (`python -m pea.thermal`). The air-side correlations are imported from the **sibling checkout** `../HeatSinkOptimisation/heatsink_model.py` (CC BY 4.0; override the location with `HEATSINK_OPT_DIR`); `network`/`electrothermal` need only the standard library, the rest needs `pip install -e ".[thermal]"` (numpy, scipy). Results are analytical correlations, never CFD/FEM claims.
- **`app.py`** is the Streamlit UI; it calls the same calculator tools as the CLI.
- **`index.html`** is a **standalone** UI (browser or **`pea/desktop.py`**). **User-visible copy is English.** The sidebar **pins** **Topology Advisor** (auto topology recommendation) and **Efficiency estimate** above the DC-DC / DC-AC / AC-DC / AC-AC tabs so they are always visible. Also: SPICE / components / magnetics and a **Cursor-style agent** (model picker, optional OpenAI in ⚙, rules fallback). It does **not** call Python for calculators. **DAB**, magnetics (inductor/transformer), and efficiency calculators are now implemented in both `index.html` (JS) and `calculator.py` (Python)—keep both sides aligned when you extend features.

### Desktop app and static UI behavior

- **`pea/desktop.py`** + **`run_pea_desktop.bat`**: native **pywebview** window (`pip install -e ".[desktop]"` or the `.bat` auto-install).
- The desktop shell **does not** open `index.html` as `file://`. It starts a small **HTTP server on 127.0.0.1** (random port) rooted at the repo so the **SPICE** tab can `fetch()` under `data/spice_models_json/` (device index + per-part JSON).
- **LTspice (Windows)**: the SPICE tab can call **`pywebview.api.ltspice_launch`** to write a temp `.lib` + `PEA_sim.cir` and start **LTspice.exe**. Auto-detect may fail; set **`LTSPICE_EXE`** to the full path of `LTspice.exe` if needed.
- **Browser-only preview**: from the repo root, `python -m http.server <port>` then open `/index.html`—the SPICE library and catalog load, but **Open in LTspice** requires the desktop app.

### Vendor SPICE data (`data/spice_models_json/`)

- The repo stores vendor models as **JSON** (`raw_spice` / `raw_text`, parsed `.subckt` index, `.model` lines). The original vendor directory tree is **not** kept in git.
- **`ui_catalog.json`** powers the SPICE tab device picker; refresh it after bulk edits to JSON:

  ```bash
  python scripts/spice_to_json.py build-ui-catalog
  ```

- To **re-import** from a local vendor folder you have on disk:

  ```bash
  python scripts/spice_to_json.py export --source "path/to/vendor_libs" --out data/spice_models_json
  ```

  Optional: `--include-asy`, `--full-subckt-body` (see `scripts/spice_to_json.py --help`).

- To **emit** a single `.lib` from one JSON file:

  ```bash
  python scripts/spice_to_json.py write-spice path/to/file.lib.json --dest out.lib
  ```

- Details and licensing reminders: [`data/spice_models_json/README.md`](data/spice_models_json/README.md) and [`data/README.md`](data/README.md).

## Development setup

Requirements: **Python 3.9+** (3.11 or 3.12 recommended if you hit wheel issues on very new Python releases).

```bash
cd PEA
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -e ".[dev]"
```

For desktop / SPICE-LTspice work, also install the desktop extra:

```bash
pip install -e ".[desktop]"
```

For Pareto optimization and STEP export:

```bash
pip install -e ".[optimize]"  # optional pymoo NSGA-II backend
pip install -e ".[cad]"       # optional CadQuery STEP export
```

Copy `.env.example` to `.env` and set `OPENAI_API_KEY` when working on the agent, Streamlit chat, or `scripts/agent_smoke_test.py`.

## Running tests

```bash
pytest tests/ -v
```

`tests/test_calculator.py` covers calculators and `execute_tool`. There are currently **no** automated tests for `PEAAgent`, RAG, or Streamlit; use `python scripts/agent_smoke_test.py "your prompt"` for manual agent checks (requires API key).

For broader manual checks, see `TESTING.md` and `README.md`.

## Optional linting

The `dev` extra includes Ruff:

```bash
ruff check .
ruff format .
```

## Where to change what

| Area | Primary files |
|------|----------------|
| Design equations & tool dispatch | `pea/tools/calculator.py` |
| Magnetics data (core shapes, materials) | `pea/tools/magnetics_data.py` |
| Component schema & search | `pea/components/schema.py` |
| Pareto optimization | `pea/optimization.py` |
| Thermal networks, electrothermal loop, cooling comparison, heat-sink Stage A screening, DAB thermal case | `pea/thermal/` (+ sibling `HeatSinkOptimisation/heatsink_model.py`); tests `tests/test_thermal_*.py` |
| STEP envelope export | `pea/cad.py` |
| LangChain tools exposed to the LLM | `pea/tools/langchain_tools.py` |
| Agent behavior, prompts, chat loop | `pea/agent/runner.py` |
| RAG documents | `pea/knowledge/documents.py` |
| Vector / keyword retrieval | `pea/knowledge/retriever.py` |
| CLI (`pea` command) | `pea/cli.py` |
| Streamlit UI | `app.py` |
| Static web UI (Design / SPICE / Components / ...) | `index.html` (CSS/JS inline) |
| Desktop: HTTP server, LTspice bridge | `pea/desktop.py`, `run_pea_desktop.bat`; optional `[desktop]` -> `pywebview` |
| Vendor SPICE -> JSON, UI catalog | `scripts/spice_to_json.py`; data under `data/spice_models_json/` |
| PDF extraction (not in default deps) | `scripts/extract_pdf.py` -- requires `pypdf`; outputs under `data/raw/` |
| Manual agent smoke test (OpenAI) | `scripts/agent_smoke_test.py` |
| Streamlit first-run / project defaults | `.streamlit/config.toml` (tracked; see `.gitignore` rules) |

## RAG and local data

- With ChromaDB + Sentence Transformers available, embeddings persist under the user profile (default `~/.pea/chroma_db`). First run may download models.
- If vector setup fails, the retriever falls back to simple keyword matching over `KNOWLEDGE_DOCUMENTS`.

## Documentation maintenance (README + CONTRIBUTING)

Whenever a change affects **how users install, run, or understand** the project, **update both** [`README.md`](README.md) and this file in the **same PR / commit** (or same release), for example:

- New scripts, entry points (`pea-desktop`), optional dependencies (`[desktop]`, `[dev]`), or run commands.
- New or renamed UI surfaces (`index.html`, Streamlit, desktop).
- Data layout (`data/spice_models_json/`, export scripts).
- Behavior that contradicts what the docs claim.

After you **materially edit** `CONTRIBUTING.md`, bump the **Last updated** date at the top. Keep `README.md` and `CONTRIBUTING.md` free of drift (one source of truth per topic; cross-link where useful).

## Guidelines for pull requests

- Keep changes **focused** on the issue or feature; avoid unrelated refactors.
- **Match existing style** in the files you touch (imports, naming, typing).
- Add or extend **pytest** coverage when you change `calculator.py` or `execute_tool` behavior.
- Add or extend optimizer tests when you change Pareto ranking, candidate feasibility, cost/volume/loss estimates, optional dependency behavior, or CAD export boundaries.
- Follow **Documentation maintenance** above: sync **README.md** and **CONTRIBUTING.md** with user-facing changes.
- If you add or redistribute **vendor SPICE models**, respect the vendor's license and keep disclaimers in `raw_spice`; prefer documenting re-import steps over committing huge proprietary drops unless the project explicitly allows it.

## Completed handoff items

All items from the original handoff checklist have been implemented:

### 1. Project hygiene

- Reviewed codebase and docs: full trace from UI/CLI to tools to calculator/knowledge is documented.
- Consolidated duplication: `calculator.py` now includes DAB, cascade, inductor, and transformer calculators, aligned with `index.html` JS implementations.
- Updated README.md and CONTRIBUTING.md to reflect all new features.

### 2. Topologies: cascades and solid-state transformer (SST)

- **Cascade / multi-stage patterns**: `cascade_design()` auto-selects PFC Boost + LLC, Buck + Buck, Boost + Boost, or accepts explicit stage list. LangChain tool `design_cascade` exposed to the agent.
- **DAB (Dual Active Bridge)**: `dab_design()` ported from `index.html` JS with full SPS model.
- **SST architecture**: knowledge documents covering building blocks, DAB-based SST design notes, ISOP modular designs.
- **Topology recommendation** updated for DAB, bidirectional, and cascade scenarios.
- **English** user-facing strings consistent across all surfaces.

### 3. Magnetic materials data

- **Built-in library**: `pea/tools/magnetics_data.py` with 8 core shapes (EE, PQ, RM, ETD, EFD, EP, toroid, EI) and 7 ferrite materials (N87, N97, 3C90, 3C95, 3F3, PC40, PC95) with Steinmetz parameters.
- **Inductor and transformer design calculators** in `calculator.py`.
- **Knowledge documents**: magnetic materials, design procedures, external data sources.

**Future**: for detailed B-H curves or FEM data, consider `pip install materialdatabase` ([upb-lea](https://github.com/upb-lea/materialdatabase), GPL-3.0) as an optional runtime dependency. Also see [MagNet (Princeton)](https://mag-net.princeton.edu/).

### 4. Component library management

- **Schema**: `pea/components/schema.py` with `MOSFET`, `Diode`, `Capacitor` dataclasses (pattern inspired by [transistordatabase](https://github.com/upb-lea/transistordatabase); independent MIT implementation).
- **Reference library**: curated Si/GaN/SiC MOSFETs, Schottky/SiC diodes, MLCC/polymer/electrolytic/film capacitors.
- **Search + auto-recommend**: `search_mosfets()`, `search_diodes()`, `search_capacitors()`, `recommend_components()`.
- **SPICE integration**: `load_spice_catalog()` reads `data/spice_models_json/ui_catalog.json`.

**Future**: extend the reference library, add versioning, link component recommendations into the agent's tool-call flow for end-to-end design.

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (MIT). See `LICENSE`.
