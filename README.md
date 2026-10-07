# AIPE Design Agent

An AI assistant for power electronics design: topology selection, parameter calculation, efficiency estimation, and component guidance.

AIPE means **AI for Power Engineering**. The existing `pea` package and interfaces
remain available. The new [Core/Registry orchestration path](docs/ecosystem-orchestration.md)
adds explicit suitability and fidelity assessment, open-source preference among
suitable tools, and evidence-linked state proposals. Its minimal offline workflow
needs Python and JSON Schema validation; no commercial solver or API key is required.
See the [capability manifest](aipe.yaml) and [review boundary](pea/review/README.md).

## Features

- **Topology recommendation**: Suggests the best converter topology based on your specs (including DAB, cascade patterns)
- **11 converter calculators**: Buck, Boost, Buck-Boost, SEPIC, Cuk, Forward, Flyback, LLC Resonant, **DAB** (bidirectional), plus **Cascade** (multi-stage) auto-design
- **Magnetics design**: Inductor and transformer sizing with core selection (EE, PQ, RM, ETD, EFD, EP, toroid, EI), ferrite material library (N87, N97, 3C90, 3C95, 3F3, PC40, PC95), Steinmetz core loss
- **Component library**: Reference MOSFETs (Si, GaN, SiC), diodes (Schottky, SiC, Ultrafast), and capacitors with auto-recommendation from operating point
- **Efficiency estimation**: First-order loss breakdown (conduction + switching) with component parameters
- **Pareto optimizer**: Generates DC-DC design candidates across topology, switching frequency, semiconductors, magnetics, efficiency, volume, and estimated BOM cost
- **STEP envelope export**: Optional CadQuery-based 3D envelope model for the recommended optimized design (PCB, magnetics, semiconductors, capacitors, heatsink blocks)
- **RAG knowledge base**: Answers questions using curated power electronics knowledge — topologies, SST (solid-state transformers), cascade architectures, magnetics, and component selection (Erickson & Maksimovic)
- **Multi-turn AI chat**: Conversational agent that remembers context across messages
- **CLI & Web UI**: Terminal (`pea`) or Streamlit (`app.py`)
- **Static UI (`index.html`)**: English UI. **Topology Advisor** (auto recommendation) and **Efficiency estimate** are **pinned at the top** of the sidebar (always visible). Below that, tabs list **DC-DC / DC-AC / AC-DC / AC-AC**. Design calculators, SPICE/components/magnetics, and a **Cursor-style PEA Agent** (model picker, optional OpenAI in ⚙; rules fallback). Browse-only rows have no built-in calculator yet.
- **Desktop app**: Native window (no separate browser tab) via **pywebview**—double-click `run_pea_desktop.bat` (Windows) or run `python -m pea.desktop` / `pea-desktop` after `pip install -e ".[desktop]"`.

## Quick Start

### 1. Install

```bash
cd PEA
pip install -e .
```

Optional extras:

```bash
# Multi-objective optimizer backend (pymoo NSGA-II)
pip install -e ".[optimize]"

# STEP export for optimized candidate envelopes
pip install -e ".[cad]"
```

Or install dependencies only:

```bash
pip install -r requirements.txt
```

### 2. Run design tools (no API key)

```bash
# List available tools
pea tools

# Topology recommendation
pea tool recommend --v-in 12 --v-out 5 --i-out 2

# Buck converter design
pea tool buck --v-in 12 --v-out 5 --i-out 2 --f-sw 100

# Boost converter design
pea tool boost --v-in 5 --v-out 12 --i-out 1

# SEPIC converter design
pea tool sepic --v-in 12 --v-out 5 --i-out 2

# LLC resonant converter
pea tool llc --v-in 400 --v-out 12 --i-out 20

# DAB (Dual Active Bridge) bidirectional
pea tool dab --v1 400 --v2 48 --p-rated 1000

# Cascade (multi-stage) design
pea tool cascade --v-in 230 --v-out 12 --i-out 20

# Inductor magnetics design
pea tool inductor --inductance 100 --i-peak 5 --i-rms 3 --core-shape EE --material N87

# Transformer magnetics design
pea tool transformer --v-pri 400 --v-sec 12 --power 500 --core-shape ETD --material N87

# Efficiency estimate
pea tool efficiency --v-in 12 --v-out 5 --i-out 2 --rds-on 50 --dcr 30

# Component recommendation
pea tool components --v-in 12 --v-out 5 --i-out 2

# Pareto optimization
pea optimize --v-in-min 36 --v-in 48 --v-in-max 60 --v-out 12 --i-out 20 --summary
```

The Streamlit app also includes a **Pareto Optimizer** workspace. It accepts DC-DC
specifications, generates feasible Buck / Boost / Buck-Boost / SEPIC / Cuk / LLC
candidates, shows the Pareto front, and can export a STEP envelope when the
`[cad]` extra is installed.

### 3. AI chat (requires OpenAI API key)

```bash
# Set your API key
export OPENAI_API_KEY=sk-your-key-here

# Chat with PEA
pea chat "Design a 12V to 5V 2A Buck converter"
```

### 4. Web interface (Streamlit — full Python stack)

```bash
streamlit run app.py
```

Open http://localhost:8501. Use the sidebar for direct calculations, or enter your API key for AI chat.

### 5. Static page or desktop window (`index.html`)

Open `index.html` in a browser, or run the desktop shell (loads the same UI):

```bash
# Optional: install webview extra
pip install -e ".[desktop]"

# From repo root
python -m pea.desktop
# or, after editable install:
pea-desktop
```

**Windows:** double-click `run_pea_desktop.bat` (installs `pywebview` if missing, sets `PYTHONPATH` to the repo root).

The desktop app serves the repo over **http://127.0.0.1** so the **SPICE** tab can load `data/spice_models_json/ui_catalog.json` and open **LTspice** with your netlist + selected vendor model (set `LTSPICE_EXE` if auto-detect fails).

Requires **Edge WebView2** on Windows (usually preinstalled). To build a single-file `.exe`, see the PyInstaller notes in `pea/desktop.py` (bundle the `data/` folder for the model library).

### 6. Run tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

For a **manual** check of the LangChain agent (requires `OPENAI_API_KEY`):

```bash
python scripts/agent_smoke_test.py "Your design question here"
```

## Project structure

Two **separate** user-facing surfaces share the **same Python math** where wired:

| Surface | Role |
|--------|------|
| **`app.py`** + **`pea` CLI** | Streamlit or terminal; call `execute_tool` / `PEAAgent`. |
| **`index.html`** + **`pea.desktop`** | Static UI in the browser or pywebview; calculators in-page (rules/JS); optional OpenAI in the agent strip only. |

When you change equations, update **`pea/tools/calculator.py`** first, then align Streamlit, CLI, LangChain tools, and any mirrored logic in `index.html` if applicable.

```
PEA/
├── pea/                      # Installable Python package (pip install -e .)
│   ├── agent/                # PEAAgent: LLM + tools + optional RAG
│   ├── knowledge/            # Curated RAG chunks + KnowledgeRetriever (Chroma / fallback)
│   ├── tools/
│   │   ├── calculator.py     # Source of truth for design equations + execute_tool
│   │   ├── langchain_tools.py
│   │   └── magnetics_data.py # Core shapes & ferrite material library (Steinmetz params)
│   ├── components/
│   │   ├── __init__.py
│   │   └── schema.py         # Component schema (MOSFET, Diode, Capacitor) + search + auto-recommend
│   ├── optimization.py       # Pareto candidate generation + optional pymoo NSGA-II backend
│   ├── cad.py                # Optional CadQuery STEP envelope export
│   ├── cli.py                # pea console entry point
│   └── desktop.py            # Native window → index.html
├── tests/                    # pytest (calculators, magnetics, components, execute_tool)
├── data/
│   ├── spice_models_json/    # Vendor SPICE as JSON + ui_catalog.json (PEA UI + LTspice workflow)
│   └── raw/                  # Optional PDF extract (not read at runtime; see data/README.md)
├── scripts/
│   ├── extract_pdf.py        # PDF → text for curating knowledge (needs pypdf)
│   └── agent_smoke_test.py   # Manual OpenAI smoke test (not pytest)
├── .streamlit/
│   └── config.toml           # e.g. disable first-run email prompt (tracked)
├── app.py                    # Streamlit
├── index.html                # Static UI
├── run_pea_desktop.bat
├── pyproject.toml
├── requirements.txt
├── CONTRIBUTING.md
├── TESTING.md
└── README.md
```

## Supported Topologies

| Topology | Type | Use when |
|----------|------|----------|
| Buck | Non-isolated | V_out < V_in (step-down) |
| Boost | Non-isolated | V_out > V_in (step-up) |
| Buck-Boost | Non-isolated | Inverting or wide input range |
| SEPIC | Non-isolated | Non-inverting buck-boost, common ground |
| Cuk | Non-isolated | Inverting, continuous input & output current |
| Forward | Isolated | 50-300 W, single-ended |
| Flyback | Isolated | Low-medium power, galvanic isolation |
| LLC Resonant | Isolated | High efficiency, >200 W, ZVS operation |
| **DAB** | Isolated, bidirectional | EV charging, energy storage, V2G, SST |
| **Cascade** | Multi-stage | Extreme ratios, PFC+LLC, Buck+Buck |

## Environment Variables

- `OPENAI_API_KEY`: Required for AI chat (get from [OpenAI](https://platform.openai.com))

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup, tests, code layout, PR expectations, and **keeping README + CONTRIBUTING updated** when user-facing behavior changes.

## License

MIT
